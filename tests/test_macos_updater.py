"""macOS asset selection in updater.py.

Before this port `_pick_asset_full` returned None for kind == "macos", so a Mac
user was told a newer release existed with nothing to download. These pin the
asset choice (the arch-tagged .zip, never the .dmg beside it) and where a
manual download lands. The in-place install itself is covered by
tests/test_macos_installer.py.

Run: python -m pytest tests/test_macos_updater.py
"""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import updater


def _asset(name, size=100):
    return {"name": name, "browser_download_url": f"https://example/{name}",
            "size": size, "state": "uploaded",
            "digest": "sha256:" + "ab" * 32}


ASSETS = [
    _asset("AetherHE-Setup.exe"),
    _asset("AetherHE-windows.zip"),
    _asset("AetherHE.flatpak"),
    _asset("AetherHE-macos-arm64.zip"),
    _asset("AetherHE-macos-x86_64.zip"),
]


def test_platform_kind_is_macos_on_darwin(monkeypatch):
    monkeypatch.setattr(updater.sys, "platform", "darwin")
    assert updater.platform_kind() == "macos"


def test_picks_the_running_architecture(monkeypatch):
    """An Intel zip on an arm64 Mac is a broken download, not a fallback."""
    monkeypatch.setattr("platform.machine", lambda: "arm64")
    got = updater._pick_asset_full(ASSETS, "macos")
    assert got["name"] == "AetherHE-macos-arm64.zip"

    monkeypatch.setattr("platform.machine", lambda: "x86_64")
    got = updater._pick_asset_full(ASSETS, "macos")
    assert got["name"] == "AetherHE-macos-x86_64.zip"


def test_falls_back_to_generic_macos_zip(monkeypatch):
    monkeypatch.setattr("platform.machine", lambda: "arm64")
    got = updater._pick_asset_full([_asset("AetherHE-macos.zip")], "macos")
    assert got["name"] == "AetherHE-macos.zip"


def test_dmg_is_never_the_updater_payload(monkeypatch):
    """A release ships a .dmg (first install) next to the .zip. The updater can
    only unpack the zip, and a release with just the .dmg has nothing for it."""
    monkeypatch.setattr("platform.machine", lambda: "arm64")
    both = [_asset("AetherHE-macos-arm64.dmg"), _asset("AetherHE-macos-arm64.zip")]
    assert updater._pick_asset_full(both, "macos")["name"] == "AetherHE-macos-arm64.zip"
    assert updater._pick_asset_full(both[:1], "macos") is None


def test_macos_assets_do_not_leak_to_other_platforms():
    full = ASSETS + [_asset("AetherHE-macos-arm64.dmg")]
    assert updater._pick_asset_full(full, "windows")["name"] == "AetherHE-Setup.exe"
    assert updater._pick_asset_full(full, "flatpak")["name"] == "AetherHE.flatpak"


def test_no_macos_asset_returns_none(monkeypatch):
    """A release with no Mac build must report 'nothing for us', not guess."""
    monkeypatch.setattr("platform.machine", lambda: "arm64")
    win_only = [_asset("AetherHE-Setup.exe"), _asset("AetherHE.flatpak")]
    assert updater._pick_asset_full(win_only, "macos") is None


def test_never_offers_a_windows_or_linux_asset_to_mac(monkeypatch):
    monkeypatch.setattr("platform.machine", lambda: "arm64")
    got = updater._pick_asset_full(ASSETS, "macos")
    assert not got["name"].endswith((".exe", ".flatpak"))


def test_wrong_arch_only_is_not_offered(monkeypatch):
    """arm64 Mac + only an x86_64 asset: the generic fallback must not match it,
    or the user downloads a build that cannot run."""
    monkeypatch.setattr("platform.machine", lambda: "arm64")
    got = updater._pick_asset_full([_asset("AetherHE-macos-x86_64.zip")], "macos")
    assert got is None or "x86_64" not in got["name"], (
        "offered an x86_64 build to an arm64 Mac")


def test_universal2_is_accepted_on_either_arch(monkeypatch):
    """A universal build genuinely runs everywhere — it must not be filtered out
    by the foreign-arch guard."""
    uni = [_asset("AetherHE-macos-universal2.zip")]
    for arch in ("arm64", "x86_64"):
        monkeypatch.setattr("platform.machine", lambda a=arch: a)
        got = updater._pick_asset_full(uni, "macos")
        assert got is not None, f"universal2 rejected on {arch}"


def test_aarch64_alias_matches_arm64_asset(monkeypatch):
    monkeypatch.setattr("platform.machine", lambda: "arm64")
    got = updater._pick_asset_full([_asset("AetherHE-macos-aarch64.zip")], "macos")
    assert got is not None, "aarch64 is the same machine as arm64"


def test_unfinished_upload_is_ignored(monkeypatch):
    monkeypatch.setattr("platform.machine", lambda: "arm64")
    pending = _asset("AetherHE-macos-arm64.zip")
    pending["state"] = "starter"
    assert updater._pick_asset_full([pending], "macos") is None


def test_download_dir_prefers_downloads_folder(monkeypatch, tmp_path):
    """A temp dir is a file the user cannot find; ~/Downloads is where they look."""
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "Downloads").mkdir()
    assert updater._download_dir("macos") == str(tmp_path / "Downloads")


def test_download_dir_falls_back_when_no_downloads_folder(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    got = updater._download_dir("macos")
    assert got != str(tmp_path / "Downloads")
    assert os.path.isdir(got)


def test_macos_apply_update_refuses_without_integrity_metadata(monkeypatch):
    """The fall-open fixed in batch 3 must stay fixed on this platform too."""
    monkeypatch.setattr(updater, "platform_kind", lambda: "macos")
    monkeypatch.setattr(updater, "check_for_update",
                        lambda *a, **k: {"ok": False})
    res = updater.apply_update("https://example/AetherHE-macos-arm64.zip",
                               asset_name="AetherHE-macos-arm64.zip")
    assert res["ok"] is False
    assert "verify" in res["error"]
