"""Integrity checks on the update download.

The updater hands a downloaded file to the OS to EXECUTE. That makes a
corrupted or tampered download a code-execution path, not a cosmetic bug, so
these tests are about one property: bytes that do not match what GitHub
published must never end up at the destination path.

Everything here is offline — urlopen is replaced with a fake response.
"""
import hashlib
import io
import os

import pytest

import updater

URL = updater.RELEASE_DOWNLOAD_PREFIX + "v9.9.9/AetherHE-Setup.exe"


def _verified(url, size, sha):
    """check_for_update() stub: GitHub's own view of the asset."""
    return lambda *a, **k: {"ok": True, "asset_url": url,
                            "asset_size": size, "asset_sha256": sha}


class _FakeResp:
    """Minimal stand-in for the urlopen context manager."""

    def __init__(self, data, headers=None):
        self._buf = io.BytesIO(data)
        self.headers = headers or {"Content-Length": str(len(data))}

    def read(self, n=-1):
        return self._buf.read(n)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def payload():
    data = b"AETHER-INSTALLER-PAYLOAD" * 500
    return data, hashlib.sha256(data).hexdigest()


def _patch(monkeypatch, data):
    monkeypatch.setattr(updater.urllib.request, "urlopen",
                        lambda req, timeout=None: _FakeResp(data))


def test_good_download_lands_at_dest(tmp_path, monkeypatch, payload):
    data, sha = payload
    _patch(monkeypatch, data)
    dest = str(tmp_path / "AetherHE-Setup.exe")
    out = updater._download(dest=dest, url="https://x/a.exe",
                            expect_size=len(data), expect_sha256=sha)
    assert out == dest
    assert open(dest, "rb").read() == data


def test_hash_mismatch_refuses_and_leaves_nothing_executable(tmp_path, monkeypatch, payload):
    """A tampered body must not appear at dest — not even partially."""
    data, sha = payload
    _patch(monkeypatch, b"EVIL" + data[4:])          # same length, different bytes
    dest = str(tmp_path / "AetherHE-Setup.exe")
    with pytest.raises(updater.IntegrityError):
        updater._download(dest=dest, url="https://x/a.exe",
                          expect_size=len(data), expect_sha256=sha)
    assert not os.path.exists(dest), "unverified file was left where it could be executed"
    assert not os.path.exists(dest + ".part")


def test_size_mismatch_refuses(tmp_path, monkeypatch, payload):
    """Truncated download (connection dropped mid-transfer)."""
    data, sha = payload
    _patch(monkeypatch, data[: len(data) // 2])
    dest = str(tmp_path / "AetherHE-Setup.exe")
    with pytest.raises(updater.IntegrityError):
        updater._download(dest=dest, url="https://x/a.exe",
                          expect_size=len(data), expect_sha256=sha)
    assert not os.path.exists(dest)
    assert not os.path.exists(dest + ".part")


def test_download_is_atomic_no_partial_at_dest(tmp_path, monkeypatch, payload):
    """While bytes are arriving, dest must not exist yet — only dest.part."""
    data, sha = payload
    dest = str(tmp_path / "AetherHE-Setup.exe")
    seen = {}

    def on_progress(done, total):
        seen["dest_exists_midflight"] = os.path.exists(dest)

    _patch(monkeypatch, data)
    updater._download(dest=dest, url="https://x/a.exe", expect_size=len(data),
                      expect_sha256=sha, on_progress=on_progress)
    assert seen.get("dest_exists_midflight") is False
    assert os.path.exists(dest)


def test_missing_digest_still_checks_size(tmp_path, monkeypatch, payload):
    """Older releases carry no digest; the size check must still apply."""
    data, _ = payload
    _patch(monkeypatch, data[:-10])
    dest = str(tmp_path / "AetherHE-Setup.exe")
    with pytest.raises(updater.IntegrityError):
        updater._download(dest=dest, url="https://x/a.exe",
                          expect_size=len(data), expect_sha256=None)
    assert not os.path.exists(dest)


def test_apply_update_refuses_on_integrity_failure(tmp_path, monkeypatch, payload):
    """The refusal must reach the caller as a failure, not a launched installer."""
    data, sha = payload
    _patch(monkeypatch, b"TAMPERED" + data[8:])
    monkeypatch.setattr(updater, "_download_dir", lambda kind: str(tmp_path))
    monkeypatch.setattr(updater, "platform_kind", lambda: "windows")
    monkeypatch.setattr(updater, "check_for_update", _verified(URL, len(data), sha))

    launched = []
    monkeypatch.setattr(updater.subprocess, "Popen",
                        lambda *a, **k: launched.append(a) or object())

    res = updater.apply_update(URL, "AetherHE-Setup.exe",
                               asset_size=len(data), asset_sha256=sha)
    assert res["ok"] is False
    assert "integrity" in res["error"].lower()
    assert not launched, "installer was executed despite a failed integrity check"


# ---- asset metadata plumbing ----
def test_pick_asset_full_extracts_size_and_sha256():
    assets = [{
        "name": "AetherHE-Setup.exe", "state": "uploaded", "size": 123,
        "digest": "sha256:abc123", "browser_download_url": "https://x/s.exe",
    }]
    a = updater._pick_asset_full(assets, "windows")
    assert a["sha256"] == "abc123" and a["size"] == 123


def test_pick_asset_skips_assets_still_uploading():
    """A half-uploaded asset yields a truncated download."""
    assets = [
        {"name": "AetherHE-Setup.exe", "state": "starter",
         "browser_download_url": "https://x/bad.exe", "size": 1, "digest": ""},
        {"name": "Aether-Setup.exe", "state": "uploaded",
         "browser_download_url": "https://x/good.exe", "size": 2, "digest": ""},
    ]
    assert updater._pick_asset_full(assets, "windows")["url"] == "https://x/good.exe"


def test_pick_asset_backwards_compatible_tuple():
    assets = [{"name": "AetherHE-Setup.exe", "state": "uploaded", "size": 1,
               "digest": "sha256:ff", "browser_download_url": "https://x/s.exe"}]
    url, name = updater._pick_asset(assets, "windows")
    assert url == "https://x/s.exe" and name == "AetherHE-Setup.exe"


def test_missing_digest_field_is_none_not_crash():
    assets = [{"name": "AetherHE-Setup.exe", "state": "uploaded", "size": 1,
               "browser_download_url": "https://x/s.exe"}]
    assert updater._pick_asset_full(assets, "windows")["sha256"] is None


def test_apply_update_refuses_when_no_checksum_or_size(monkeypatch):
    """Fall-open guard (audit round 1 #8): if the caller omits size+sha256 AND
    the re-fetch can't repopulate them (rate-limited API host, or a release cut
    between check and apply so the URL differs), apply_update must REFUSE — never
    fall through to executing an unverified installer."""
    import subprocess
    # GitHub's check succeeds but names a DIFFERENT asset_url -> refuse.
    monkeypatch.setattr(updater, "check_for_update",
                        lambda *a, **k: {"ok": True,
                                         "asset_url": "https://other/x.exe",
                                         "asset_size": 123,
                                         "asset_sha256": "deadbeef"})
    seen = {"download": False, "popen": False}
    monkeypatch.setattr(updater, "_download",
                        lambda *a, **k: seen.__setitem__("download", True))
    monkeypatch.setattr(subprocess, "Popen",
                        lambda *a, **k: seen.__setitem__("popen", True))
    r = updater.apply_update(URL)
    assert r["ok"] is False and "unverified" in r["error"]
    assert seen["download"] is False, "must not download without verification data"
    assert seen["popen"] is False, "must not execute an unverified installer"


def test_apply_update_still_installs_with_valid_metadata(monkeypatch):
    """The guard must NOT block a normal verified install: when size+sha256 are
    present, _download runs and the installer launches."""
    import subprocess
    ran = {"download": False, "popen": False}
    monkeypatch.setattr(updater, "_download",
                        lambda *a, **k: ran.__setitem__("download", True))
    monkeypatch.setattr(updater, "_download_dir", lambda kind: ".")
    monkeypatch.setattr(updater, "platform_kind", lambda: "windows")
    monkeypatch.setattr(updater, "check_for_update", _verified(URL, 999, "abc123"))
    monkeypatch.setattr(subprocess, "Popen",
                        lambda *a, **k: ran.__setitem__("popen", True))
    r = updater.apply_update(URL, asset_size=999, asset_sha256="abc123")
    assert r["ok"] is True and ran["download"] and ran["popen"]


# ---- URL pinning / caller metadata is untrusted ----
def _spy(monkeypatch):
    seen = {"check": 0, "download": 0, "popen": 0}
    monkeypatch.setattr(updater, "check_for_update",
                        lambda *a, **k: seen.__setitem__("check", seen["check"] + 1) or {"ok": False})
    monkeypatch.setattr(updater, "_download",
                        lambda *a, **k: seen.__setitem__("download", seen["download"] + 1))
    monkeypatch.setattr(updater.subprocess, "Popen",
                        lambda *a, **k: seen.__setitem__("popen", seen["popen"] + 1))
    monkeypatch.setattr(updater, "platform_kind", lambda: "windows")
    return seen


def test_apply_update_rejects_url_outside_repo_releases(monkeypatch):
    seen = _spy(monkeypatch)
    r = updater.apply_update("https://example.com/AetherHE-Setup.exe",
                             asset_size=1, asset_sha256="ab")
    assert r["ok"] is False and "outside" in r["error"]
    assert seen == {"check": 0, "download": 0, "popen": 0}


@pytest.mark.parametrize("bad", [
    "https://github.com.evil.example/MrWhosNexus/Aether-HE/releases/download/v1/a.exe",
    "http://github.com/MrWhosNexus/Aether-HE/releases/download/v1/a.exe",
    URL.replace("v9.9.9/", "v9.9.9/../../x/"),
    URL + "?x=1",
])
def test_apply_update_rejects_lookalike_urls(monkeypatch, bad):
    seen = _spy(monkeypatch)
    r = updater.apply_update(bad, asset_size=1, asset_sha256="ab")
    assert r["ok"] is False
    assert seen == {"check": 0, "download": 0, "popen": 0}


def test_apply_update_ignores_caller_supplied_hash(tmp_path, monkeypatch):
    evil = b"EVIL" * 100
    real = b"REAL-INSTALLER" * 100
    _patch(monkeypatch, evil)
    monkeypatch.setattr(updater, "_download_dir", lambda kind: str(tmp_path))
    monkeypatch.setattr(updater, "platform_kind", lambda: "windows")
    monkeypatch.setattr(updater, "check_for_update",
                        _verified(URL, len(real), hashlib.sha256(real).hexdigest()))
    launched = []
    monkeypatch.setattr(updater.subprocess, "Popen",
                        lambda *a, **k: launched.append(a) or object())
    r = updater.apply_update(URL, "AetherHE-Setup.exe", asset_size=len(evil),
                             asset_sha256=hashlib.sha256(evil).hexdigest())
    assert r["ok"] is False and "integrity" in r["error"].lower()
    assert not launched


@pytest.mark.parametrize("chk", ["fails", "raises"])
def test_apply_update_fails_closed_when_github_cannot_vouch(tmp_path, monkeypatch, chk):
    """Security review 2026-11-04: with GitHub unreachable or rate-limited the
    caller-supplied size/sha256 must still be ignored. Pins the line that
    discards them (a mutant without it downloaded the served bytes, verified
    them against the caller's own hash and launched them)."""
    evil = b"EVIL" * 100
    _patch(monkeypatch, evil)
    monkeypatch.setattr(updater, "_download_dir", lambda kind: str(tmp_path))
    monkeypatch.setattr(updater, "platform_kind", lambda: "windows")

    def check(*a, **k):
        if chk == "raises":
            raise OSError("offline")
        return {"ok": False, "error": "GitHub rate limit reached"}

    monkeypatch.setattr(updater, "check_for_update", check)
    launched = []
    monkeypatch.setattr(updater.subprocess, "Popen",
                        lambda *a, **k: launched.append(a) or object())
    r = updater.apply_update(URL, "AetherHE-Setup.exe", asset_size=len(evil),
                             asset_sha256=hashlib.sha256(evil).hexdigest())
    assert r["ok"] is False
    assert not launched


def test_apply_update_refuses_percent_encoded_paths_before_any_network(monkeypatch):
    seen = {"check": 0}
    monkeypatch.setattr(updater, "check_for_update",
                        lambda *a, **k: seen.__setitem__("check", seen["check"] + 1) or {})
    r = updater.apply_update(URL.replace("v9.9.9/", "v9.9.9/%2e%2e/%2e%2e/%2e%2e/evil/"))
    assert r["ok"] is False and "outside" in r["error"]
    assert seen["check"] == 0
