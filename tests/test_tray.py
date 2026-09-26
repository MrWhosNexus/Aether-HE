"""Tray residency (tray.py + the Api/main hooks in app_web.py).

No pystray, no display: everything the icon/panel would do is exercised
through TrayController's public surface with stub windows.
"""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import tray  # noqa: E402


class StubWindow:
    def __init__(self):
        self.hidden = False
        self.destroyed = False
        self.js = []
        self.pos = None

    def hide(self): self.hidden = True
    def show(self): self.hidden = False
    def destroy(self): self.destroyed = True
    def move(self, x, y): self.pos = (x, y)
    def evaluate_js(self, js):
        self.js.append(js)
        return None


class StubApi:
    def __init__(self):
        self.calls = []
        self._tray_state = None

    def stop_multicolor(self): self.calls.append("stop"); return {"ok": True}
    def disconnect(self): self.calls.append("disconnect"); return {"ok": True}


class StubIcon:
    def __init__(self):
        self.visible = True
        self.stopped = False

    def stop(self): self.stopped = True


def make(available=True):
    api = StubApi()
    c = tray.TrayController(api, webview_mod=None)
    c.main_window = StubWindow()
    c.available = available
    return api, c


# ---- argv / geometry ------------------------------------------------------

def test_minimized_flag_parsing():
    assert tray.wants_minimized(["--minimized"])
    assert tray.wants_minimized(["--foo", "--minimized"])
    assert not tray.wants_minimized([])
    assert not tray.wants_minimized(None)


def test_panel_position_anchors_above_cursor_and_clamps():
    w, h = tray.PANEL_W, tray.PANEL_H
    # Centre of a 1920x1080 screen: panel centred on the cursor, above it.
    x, y = tray.panel_position(1920, 1080, cursor=(960, 700))
    assert x == 960 - w // 2 and y == 700 - h - 12
    # Tray corner (bottom-right): never off-screen.
    x, y = tray.panel_position(1920, 1080, cursor=(1900, 1070))
    assert x + w <= 1920 - 12 and y + h <= 1080 - 12 and x >= 12 and y >= 12
    # Top-left cursor: clamped to the margin.
    assert tray.panel_position(1920, 1080, cursor=(0, 0)) == (12, 12)
    # No cursor: bottom-right, above a taskbar.
    x, y = tray.panel_position(1920, 1080)
    assert x == 1920 - w - 12 and y == 1080 - h - 56


# ---- close-to-tray --------------------------------------------------------

def test_close_hides_when_tray_available():
    api, c = make(available=True)
    assert c.on_main_closing() is False        # cancel the close
    assert c.main_window.hidden is True
    assert any("aether:tray" in j for j in c.main_window.js)


def test_close_quits_when_no_tray_backend():
    api, c = make(available=False)
    assert c.on_main_closing() is True
    assert c.main_window.hidden is False


def test_close_quits_when_exiting():
    api, c = make(available=True)
    c._exiting = True
    assert c.on_main_closing() is True


def test_close_falls_back_to_quit_if_hide_raises():
    api, c = make(available=True)

    def boom(): raise RuntimeError("no window")
    c.main_window.hide = boom
    assert c.on_main_closing() is True


# ---- exit -----------------------------------------------------------------

def test_exit_tears_down_in_order_and_is_idempotent():
    api, c = make()
    c.icon = StubIcon()
    c.panel = StubWindow()
    c.exit()
    assert api.calls == ["stop", "disconnect"]      # engine first, then handle
    assert c.icon.stopped and c.icon.visible is False
    assert c.panel.destroyed and c.main_window.destroyed
    # A second exit (menu + panel button racing) does nothing more.
    c.exit()
    assert api.calls == ["stop", "disconnect"]
    # And the close handler now lets the window go.
    assert c.on_main_closing() is True


def test_exit_survives_api_errors():
    api, c = make()
    api.stop_multicolor = lambda: (_ for _ in ()).throw(RuntimeError("x"))
    api.disconnect = lambda: (_ for _ in ()).throw(RuntimeError("y"))
    c.exit()
    assert c.main_window.destroyed


# ---- state bridge ---------------------------------------------------------

def test_push_evaluates_react_hook_with_json_and_mirrors_state():
    api, c = make()
    api._tray_state = {"pattern": "wave", "speed": 60, "effects": []}
    r = c.push({"pattern": "radar"})
    assert r == {"ok": True}
    js = c.main_window.js[-1]
    assert "window.__aetherTraySet" in js
    payload = json.loads(js[js.index("(", js.index("__aetherTraySet(")) + 1:-1])
    assert payload == {"pattern": "radar"}
    assert api._tray_state["pattern"] == "radar"
    assert api._tray_state["speed"] == 60


def test_push_without_window_fails_cleanly():
    api, c = make()
    c.main_window = None
    assert c.push({"speed": 10})["ok"] is False


def test_tray_api_speed_clamps_and_validates():
    api, c = make()
    t = tray.TrayApi(c)
    assert t.set_speed(250) == {"ok": True}
    assert api._tray_state["speed"] == 100
    assert t.set_speed(-3) == {"ok": True}
    assert api._tray_state["speed"] == 0
    assert t.set_speed("41.6") == {"ok": True}
    assert api._tray_state["speed"] == 42
    assert t.set_speed("fast")["ok"] is False


def test_tray_api_effect_and_open_and_state_defaults():
    api, c = make()
    t = tray.TrayApi(c)
    c.main_window.hidden = True
    assert t.set_effect("ripple") == {"ok": True}
    assert api._tray_state["pattern"] == "ripple"
    st = t.get_state()
    assert st["ok"] and st["appName"] == "Aether HE"
    assert st["effects"] == [] and st["connected"] is False
    assert t.open_main() == {"ok": True}
    assert c.main_window.hidden is False


def test_api_tray_sync_normalises_effect_list():
    import app_web
    api = app_web.Api.__new__(app_web.Api)     # no HID / registry side effects
    r = api.tray_sync({
        "pattern": "wave", "speed": 33, "connected": 1, "board": "Aula Win60 HE",
        "effects": [{"id": "wave", "label": "Wave", "icon": "〰"}, {"label": "no id"},
                    "junk", {"id": "rain"}],
    })
    assert r == {"ok": True}
    st = api._tray_state
    assert st["pattern"] == "wave" and st["speed"] == 33 and st["connected"] is True
    assert st["board"] == "Aula Win60 HE"
    assert st["effects"] == [{"id": "wave", "label": "Wave", "icon": "〰"},
                             {"id": "rain", "label": "rain", "icon": ""}]
    assert api.tray_sync("nope")["ok"] is False
    # The controller reads exactly this.
    c = tray.TrayController(api)
    assert c.state()["effects"][1]["id"] == "rain"


def test_autostart_command_starts_minimized(monkeypatch):
    import app_web
    api = app_web.Api.__new__(app_web.Api)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\Apps\AetherHE\AetherHE.exe")
    assert api._autostart_target() == r'"C:\Apps\AetherHE\AetherHE.exe" --minimized'
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\py\python.exe")
    cmd = api._autostart_target()
    assert cmd.startswith(r'"C:\py\pythonw.exe" "') and cmd.endswith('app_web.py" --minimized')


def test_ui_bundle_carries_tray_hook_and_panel_exists():
    html = open(os.path.join(ROOT, "ui", "index_runtime.html"), encoding="utf-8").read()
    assert "__aetherTraySet" in html and "tray_sync" in html
    panel = open(tray.PANEL_HTML, encoding="utf-8").read()
    for name in ("get_state", "set_effect", "set_speed", "open_main", "exit_app", "hide_panel"):
        assert name in panel, name
        assert callable(getattr(tray.TrayApi, name))
    assert os.path.exists(tray.ICON_PNG)
