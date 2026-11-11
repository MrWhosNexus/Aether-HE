"""macOS OS-integration: gamepad capability reporting + LaunchAgent autostart.

The gamepad assertions exist because the honest-refusal contract is easy to
regress into a friendly lie: the pre-port message told a macOS user to "install
python-evdev (Linux) or vgamepad + ViGEmBus (Windows)", neither of which can
ever work there. `supported=False, installable=False` is the pair that stops the
UI offering an install button for a platform gate.

Run: python -m pytest tests/test_macos_integration.py
"""
import os
import plistlib
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import gamepad


# ------------------------------------------------------ gamepad capability
def test_backend_status_reports_live_backend(monkeypatch):
    monkeypatch.setattr(gamepad, "_BACKEND", "evdev")
    st = gamepad.backend_status()
    assert st == {"backend": "evdev", "supported": True, "reason": "", "installable": False}


def test_macos_is_unsupported_and_not_installable(monkeypatch):
    """The load-bearing pair: a platform gate must never look like a missing dep."""
    monkeypatch.setattr(gamepad, "_BACKEND", None)
    monkeypatch.setattr(gamepad.sys, "platform", "darwin")
    st = gamepad.backend_status()
    assert st["supported"] is False
    assert st["installable"] is False, "macOS must not offer an install action"
    assert "entitlement" in st["reason"]
    assert "Nothing to install" in st["reason"]


def test_windows_without_vigembus_is_installable(monkeypatch):
    """Contrast case — proves `installable` actually discriminates."""
    monkeypatch.setattr(gamepad, "_BACKEND", None)
    monkeypatch.setattr(gamepad.sys, "platform", "win32")
    st = gamepad.backend_status()
    assert st["supported"] is False and st["installable"] is True


def test_linux_without_uinput_is_installable(monkeypatch):
    monkeypatch.setattr(gamepad, "_BACKEND", None)
    monkeypatch.setattr(gamepad.sys, "platform", "linux")
    assert gamepad.backend_status()["installable"] is True


def test_constructing_a_pad_on_macos_refuses_without_install_advice(monkeypatch):
    monkeypatch.setattr(gamepad, "_BACKEND", None)
    monkeypatch.setattr(gamepad.sys, "platform", "darwin")
    with pytest.raises(RuntimeError) as ei:
        gamepad.VirtualGamepad()
    msg = str(ei.value)
    assert "entitlement" in msg
    # The old message named these; on macOS they are false leads.
    assert "python-evdev" not in msg and "ViGEmBus" not in msg


def test_macos_reason_records_the_measured_entitlement(monkeypatch):
    """Pin the specific entitlement so a future reader can re-verify the claim."""
    assert "com.apple.developer.hid.virtual.device" in gamepad.MACOS_UNSUPPORTED_REASON


# ------------------------------------------------------------- autostart
@pytest.fixture
def api(monkeypatch, tmp_path):
    """An Api instance with HOME redirected, so we never touch the real
    ~/Library/LaunchAgents."""
    monkeypatch.setenv("HOME", str(tmp_path))
    import app_web
    a = app_web.Api.__new__(app_web.Api)      # no __init__: no device, no threads
    return a


def test_launch_agent_path_is_under_home(api, tmp_path):
    p = api._launch_agent_path()
    assert p.startswith(str(tmp_path))
    assert p.endswith("/Library/LaunchAgents/io.github.mrwhosnexus.AetherHE.plist")


def test_autostart_absent_when_no_plist(api, monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    assert api.get_autostart() == {"ok": True, "supported": True, "enabled": False}


def test_autostart_enable_writes_runatload_plist(api, monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    calls = []

    class _R:
        returncode = 0
        stderr = b""

    # _set_autostart_macos imports subprocess locally, so patch the module itself.
    monkeypatch.setattr(__import__("subprocess"), "run",
                        lambda *a, **k: (calls.append(a[0]), _R())[1])

    res = api.set_autostart(True)
    assert res["ok"] and res["enabled"] is True

    with open(api._launch_agent_path(), "rb") as f:
        pl = plistlib.load(f)
    assert pl["Label"] == "io.github.mrwhosnexus.AetherHE"
    assert pl["RunAtLoad"] is True
    assert pl["KeepAlive"] is False, "a login item must not respawn after the user quits"
    assert pl["ProgramArguments"], "argv must not be empty"
    # bootout-then-bootstrap, so a changed argv actually replaces the loaded copy.
    verbs = [c[1] for c in calls]
    assert verbs == ["bootout", "bootstrap"]


def test_autostart_roundtrip_reports_enabled(api, monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(__import__("subprocess"), "run",
                        lambda *a, **k: type("R", (), {"returncode": 0, "stderr": b""})())
    api.set_autostart(True)
    got = api.get_autostart()
    assert got["enabled"] is True and got["command"]


def test_inert_plist_reads_as_disabled(api, monkeypatch):
    """A plist with RunAtLoad false exists but does nothing — don't call it 'on'."""
    monkeypatch.setattr(sys, "platform", "darwin")
    p = api._launch_agent_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f:
        plistlib.dump({"Label": "x", "RunAtLoad": False, "ProgramArguments": ["/bin/true"]}, f)
    assert api.get_autostart()["enabled"] is False


def test_autostart_disable_removes_plist(api, monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(__import__("subprocess"), "run",
                        lambda *a, **k: type("R", (), {"returncode": 0, "stderr": b""})())
    api.set_autostart(True)
    assert os.path.exists(api._launch_agent_path())
    res = api.set_autostart(False)
    assert res["ok"] and res["enabled"] is False
    assert not os.path.exists(api._launch_agent_path())


def test_bootstrap_failure_still_reports_install_but_not_active(api, monkeypatch):
    """Writing the plist and activating it are separate failures — say which."""
    monkeypatch.setattr(sys, "platform", "darwin")

    def _run(argv, **k):
        rc = 0 if argv[1] == "bootout" else 1
        return type("R", (), {"returncode": rc, "stderr": b"Load failed: 5"})()

    monkeypatch.setattr(__import__("subprocess"), "run", _run)
    res = api.set_autostart(True)
    assert res["ok"] and res["enabled"] is True
    assert res["active_now"] is False
    assert "next login" in res["note"]
    assert os.path.exists(api._launch_agent_path())
