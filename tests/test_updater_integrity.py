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


REL = "https://github.com/MrWhosNexus/Aether-HE/releases/download/v9.9.9/AetherHE-Setup.exe"


def _release(monkeypatch, url=REL, size=999, sha="abc123", ok=True):
    """check_for_update() as the GitHub API would answer (the ONLY trusted
    source of the asset URL / size / digest)."""
    monkeypatch.setattr(updater, "check_for_update",
                        lambda *a, **k: {"ok": ok, "latest": "9.9.9",
                                         "asset_url": url,
                                         "asset_name": "AetherHE-Setup.exe",
                                         "asset_size": size, "asset_sha256": sha,
                                         "error": None if ok else "offline"})


def test_apply_update_refuses_on_integrity_failure(tmp_path, monkeypatch, payload):
    """The refusal must reach the caller as a failure, not a launched installer."""
    data, sha = payload
    _release(monkeypatch, size=len(data), sha=sha)
    _patch(monkeypatch, b"TAMPERED" + data[8:])
    monkeypatch.setattr(updater, "_download_dir", lambda kind: str(tmp_path))
    monkeypatch.setattr(updater, "platform_kind", lambda: "windows")

    launched = []
    monkeypatch.setattr(updater.subprocess, "Popen",
                        lambda *a, **k: launched.append(a) or object())

    res = updater.apply_update(REL, "AetherHE-Setup.exe",
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
    # The release publishes neither a size nor a digest.
    _release(monkeypatch, size=None, sha=None)
    seen = {"download": False, "popen": False}
    monkeypatch.setattr(updater, "_download",
                        lambda *a, **k: seen.__setitem__("download", True))
    monkeypatch.setattr(subprocess, "Popen",
                        lambda *a, **k: seen.__setitem__("popen", True))
    r = updater.apply_update(REL)
    assert r["ok"] is False and "unverified" in r["error"]
    assert seen["download"] is False, "must not download without verification data"
    assert seen["popen"] is False, "must not execute an unverified installer"


def test_apply_update_still_installs_with_valid_metadata(monkeypatch):
    """The guard must NOT block a normal verified install: when size+sha256 are
    present, _download runs and the installer launches."""
    import subprocess
    _release(monkeypatch)
    ran = {"download": False, "popen": False}
    monkeypatch.setattr(updater, "_download",
                        lambda *a, **k: ran.__setitem__("download", True))
    monkeypatch.setattr(updater, "_download_dir", lambda kind: ".")
    monkeypatch.setattr(updater, "platform_kind", lambda: "windows")
    monkeypatch.setattr(subprocess, "Popen",
                        lambda *a, **k: ran.__setitem__("popen", True))
    r = updater.apply_update(REL, asset_size=999, asset_sha256="abc123")
    assert r["ok"] is True and ran["download"] and ran["popen"]


# ---- the bridge's arguments are never trusted (security plan hole B) ----
def _no_run(monkeypatch):
    import subprocess
    seen = {"download": None, "popen": False}
    monkeypatch.setattr(updater, "_download",
                        lambda url, dest, **k: seen.__setitem__("download", (url, k)))
    monkeypatch.setattr(updater, "_download_dir", lambda kind: ".")
    monkeypatch.setattr(updater, "platform_kind", lambda: "windows")
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: seen.__setitem__("popen", True))
    return seen


def test_forged_url_from_the_ui_is_refused(monkeypatch):
    _release(monkeypatch)
    seen = _no_run(monkeypatch)
    r = updater.apply_update("https://evil.example/AetherHE-Setup.exe",
                             asset_size=10, asset_sha256="0" * 64)
    assert r["ok"] is False
    assert seen["download"] is None and not seen["popen"]


def test_caller_checksum_is_ignored_for_the_releases_own(monkeypatch):
    _release(monkeypatch, size=999, sha="abc123")
    seen = _no_run(monkeypatch)
    updater.apply_update(REL, asset_size=1, asset_sha256="f" * 64)
    url, kw = seen["download"]
    assert url == REL and kw["expect_sha256"] == "abc123" and kw["expect_size"] == 999


def test_release_asset_outside_this_repo_is_refused(monkeypatch):
    _release(monkeypatch, url="https://github.com/someone-else/x/releases/download/v1/AetherHE-Setup.exe")
    seen = _no_run(monkeypatch)
    r = updater.apply_update()
    assert r["ok"] is False and seen["download"] is None


def test_no_verdict_from_github_means_no_install(monkeypatch):
    _release(monkeypatch, ok=False)
    seen = _no_run(monkeypatch)
    r = updater.apply_update(REL)
    assert r["ok"] is False and seen["download"] is None


def test_trusted_asset_url_rules():
    ok = updater._trusted_asset_url
    assert ok(REL)
    for bad in ("http://github.com/MrWhosNexus/Aether-HE/releases/download/v1/a.exe",
                "https://github.com/MrWhosNexus/Aether-HE/releases/download/",
                "https://github.com/MrWhosNexus/Aether-HE/releases/download/../../x/a.exe",
                "https://github.com/MrWhosNexus/Aether-HE/releases/download/v1/a.exe?x=1",
                "https://user@github.com/MrWhosNexus/Aether-HE/releases/download/v1/a.exe",
                "https://github.com.evil/MrWhosNexus/Aether-HE/releases/download/v1/a.exe",
                None, 5):
        assert not ok(bad), bad
