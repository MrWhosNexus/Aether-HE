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


# ------------------------------------------- update health report (app side)
class _Window:
    def __init__(self, answers):
        self.answers = list(answers)
        self.asked = 0

    def evaluate_js(self, js):
        self.asked += 1
        a = self.answers.pop(0) if self.answers else False
        if isinstance(a, Exception):
            raise a
        return a


def test_health_is_reported_only_once_the_ui_has_rendered(monkeypatch):
    """The updater's swap helper deletes the previous version on this report,
    so a process that is merely alive (blank window, bridge missing) must not
    make it."""
    import app_web
    noted = []
    monkeypatch.setattr(app_web.updater, "macos_health_wanted", lambda: True)
    monkeypatch.setattr(app_web.updater, "macos_note_healthy",
                        lambda: noted.append(1) or True)
    w = _Window([False, RuntimeError("webview not ready"), True])
    assert app_web._report_update_health(w, tries=5, pause=0) is True
    assert w.asked == 3 and noted == [1]

    blank = _Window([False] * 5)
    assert app_web._report_update_health(blank, tries=5, pause=0) is False
    assert noted == [1], "a UI that never rendered was reported healthy"


def test_health_is_not_probed_outside_an_installed_mac_build(monkeypatch):
    import app_web
    monkeypatch.setattr(app_web.updater, "macos_health_wanted", lambda: False)
    monkeypatch.setattr(app_web.updater, "macos_note_healthy",
                        lambda: pytest.fail("reported health from a non-installed build"))
    w = _Window([True])
    assert app_web._report_update_health(w) is False
    assert w.asked == 0


def test_launch_pid_is_recorded_before_the_heavy_imports():
    """An update that hangs importing hid/webview must already have its pid on
    record (the helper also finds it by path; this is the cheap half)."""
    src = open(os.path.join(ROOT, "app_web.py"), encoding="utf-8").read()
    head = src[:src.index("\nimport hid\n")]
    assert "_updater_early.macos_note_launch()" in head
    assert head.index('if __name__ == "__main__":') < head.index("macos_note_launch()")
    for heavy in ("import hid", "import webview", "from aula_device"):
        assert heavy not in head
    # updater itself must stay importable without any of them.
    upd = open(os.path.join(ROOT, "updater.py"), encoding="utf-8").read()
    for heavy in ("import hid", "import webview"):
        assert heavy not in upd


def test_main_records_the_launch_pid_after_the_instance_guard():
    src = open(os.path.join(ROOT, "app_web.py"), encoding="utf-8").read()
    main = src[src.index("def main():"):]
    assert main.index("_selftest()") < main.index("inst.acquire()") \
        < main.index("updater.macos_note_launch()") < main.index("api = Api()")
