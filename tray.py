"""System-tray residency for Aether HE.

Closing the main window no longer quits: the window hides, the process stays
resident behind a tray icon and the host effect engine keeps streaming frames
to the board. The tray icon opens a compact "mini mode" panel (its own small
frameless webview: Open Aether HE on top, effect picker + speed slider in the
middle, Exit Aether HE at the bottom); its right-click menu carries the same
Open/Exit entries for keyboard/screen-reader users.

The main React app stays the single source of truth for lighting state. The
panel never talks to the board directly: `TrayApi.set_effect/set_speed` push
into the (possibly hidden) main window via `window.__aetherTraySet`, whose
React handler updates `pattern`/`speed` exactly as a click in the Lighting
tab would — the same per-board dispatch table decides host engine vs
firmware mode, and the change is persisted to settings.json by the normal
save path. The app reports its current state back through `Api.tray_sync`,
so `TrayApi.get_state` is a plain read of Python-held data.

pystray is optional: when it is missing (Linux without an X display, a
trimmed install) `TrayController.available` is False and closing the window
quits, exactly as before.
"""
import json
import logging
import os
import sys
import threading

log = logging.getLogger("aether.tray")

HERE = os.path.dirname(os.path.abspath(__file__))
PANEL_HTML = os.path.join(HERE, "ui", "tray_panel.html")
ICON_PNG = os.path.join(HERE, "ui", "assets", "logo.png")

APP_NAME = "Aether HE"
PANEL_W, PANEL_H = 320, 470
MINIMIZED_FLAG = "--minimized"


def wants_minimized(argv):
    """True when the process was launched to start straight into the tray
    (the Windows autostart entry passes this so login doesn't pop the window)."""
    return MINIMIZED_FLAG in (argv or [])


def panel_position(screen_w, screen_h, cursor=None, w=PANEL_W, h=PANEL_H, margin=12):
    """Top-left corner for the mini panel: anchored above/left of the cursor
    (the tray icon sits under it on Windows), clamped to the screen so the
    panel never opens off-screen. No cursor → bottom-right corner, above a
    typical taskbar."""
    if cursor is None:
        x = screen_w - w - margin
        y = screen_h - h - 56
    else:
        cx, cy = cursor
        x = cx - w // 2
        y = cy - h - margin
    x = max(margin, min(x, screen_w - w - margin))
    y = max(margin, min(y, screen_h - h - margin))
    return int(x), int(y)


def _cursor_pos():
    if not sys.platform.startswith("win"):
        return None
    try:
        import ctypes
        from ctypes import wintypes
        pt = wintypes.POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        return int(pt.x), int(pt.y)
    except Exception:
        return None


def _load_pystray():
    """Import pystray lazily: on Linux without a display the import itself
    raises (it picks an X11/AppIndicator backend at import time)."""
    try:
        import pystray  # noqa: F401
        from PIL import Image  # noqa: F401
        return pystray, Image
    except Exception as e:
        log.info("tray unavailable: %s", e)
        return None, None


class TrayApi:
    """js_api of the mini panel. Every method is a small, JSON-friendly call —
    pywebview runs each on its own thread, so nothing here blocks."""

    def __init__(self, controller):
        self._c = controller

    def get_state(self):
        st = self._c.state()
        return {"ok": True, **st}

    def set_effect(self, effect_id):
        return self._c.push({"pattern": str(effect_id)})

    def set_speed(self, value):
        try:
            v = max(0, min(100, int(round(float(value)))))
        except (TypeError, ValueError):
            return {"ok": False, "error": "speed must be a number 0-100"}
        return self._c.push({"speed": v})

    def open_main(self):
        self._c.show_main()
        self._c.hide_panel()
        return {"ok": True}

    def hide_panel(self):
        self._c.hide_panel()
        return {"ok": True}

    def exit_app(self):
        # Run the teardown off the bridge thread so the panel's own destroy
        # doesn't deadlock the call that requested it.
        threading.Thread(target=self._c.exit, name="aether-tray-exit", daemon=True).start()
        return {"ok": True}


class TrayController:
    """Owns the tray icon, the mini panel window and the app-level lifecycle
    decisions (hide-on-close vs. real exit).

    `api` is the main `Api` (for tray state + board teardown); `main_window`
    is set by main() once pywebview created it. `webview_mod` is injectable
    for tests."""

    def __init__(self, api, webview_mod=None):
        self.api = api
        self.webview = webview_mod
        self.main_window = None
        self.panel = None
        self.icon = None
        self.available = False
        self._exiting = False
        self._lock = threading.Lock()
        self._pystray = None
        self._Image = None

    # ---- lifecycle -------------------------------------------------------
    def start(self):
        """Create and run the tray icon (detached: pystray owns its own message
        loop thread; pywebview keeps the main thread). Returns availability."""
        pystray, Image = _load_pystray()
        if not pystray:
            return False
        try:
            image = Image.open(ICON_PNG)
            menu = pystray.Menu(
                pystray.MenuItem(f"Open {APP_NAME}", self._on_open, default=False),
                pystray.MenuItem("Mini mode", self._on_panel, default=True, visible=True),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(f"Exit {APP_NAME}", self._on_exit),
            )
            self.icon = pystray.Icon("aether-he", image, APP_NAME, menu)
            self._pystray, self._Image = pystray, Image
            self.icon.run_detached()
            self.available = True
        except Exception as e:
            log.warning("tray icon failed, closing the window will quit: %s", e)
            self.available = False
        return self.available

    def on_main_closing(self):
        """`window.events.closing` handler. Returning False cancels the close
        (pywebview convention) — we hide instead so the effects keep running.
        A real exit (tray → Exit) sets `_exiting` first and lets it through."""
        if self._exiting or not self.available:
            return True
        try:
            self.main_window.hide()
            self._notify_hidden()
        except Exception as e:
            log.warning("hide-on-close failed, quitting instead: %s", e)
            return True
        return False

    def exit(self):
        """Full teardown: stop the host engine (the board keeps its last frame),
        release the HID handle, drop the icon and destroy every window so
        `webview.start()` returns and the process ends."""
        with self._lock:
            if self._exiting:
                return
            self._exiting = True
        try:
            self.api.stop_multicolor()
        except Exception:
            pass
        try:
            self.api.disconnect()
        except Exception:
            pass
        if self.icon is not None:
            try:
                self.icon.visible = False
                self.icon.stop()
            except Exception:
                pass
        for w in (self.panel, self.main_window):
            if w is None:
                continue
            try:
                w.destroy()
            except Exception:
                pass

    # ---- state bridge ----------------------------------------------------
    def state(self):
        st = dict(getattr(self.api, "_tray_state", None) or {})
        st.setdefault("effects", [])
        st.setdefault("pattern", None)
        st.setdefault("speed", 60)
        st.setdefault("connected", False)
        st.setdefault("board", None)
        st["appName"] = APP_NAME
        return st

    def push(self, patch):
        """Apply {pattern?, speed?} through the main window's React handler.
        Optimistically mirror it into the cached state so the panel reflects
        the change immediately even before the app's tray_sync echo lands."""
        w = self.main_window
        if w is None:
            return {"ok": False, "error": "main window not ready"}
        cur = dict(getattr(self.api, "_tray_state", None) or {})
        cur.update(patch)
        self.api._tray_state = cur
        js = f"window.__aetherTraySet && window.__aetherTraySet({json.dumps(patch)})"
        try:
            w.evaluate_js(js)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _notify_hidden(self):
        """Tell the app it went to the tray (it pauses its preview polls on
        document.hidden already; this is a hook for anything else)."""
        w = self.main_window
        if w is None:
            return
        try:
            w.evaluate_js("window.dispatchEvent(new CustomEvent('aether:tray', {detail:{hidden:true}}))")
        except Exception:
            pass

    # ---- windows ---------------------------------------------------------
    def show_main(self):
        w = self.main_window
        if w is None:
            return
        try:
            w.show()
        except Exception as e:
            log.warning("show main failed: %s", e)

    def show_panel(self):
        wv = self.webview
        if wv is None:
            return
        pos = self._panel_pos()
        with self._lock:
            if self.panel is None:
                try:
                    from pathlib import Path
                    self.panel = wv.create_window(
                        f"{APP_NAME} — mini mode", Path(PANEL_HTML).as_uri(),
                        js_api=TrayApi(self),
                        width=PANEL_W, height=PANEL_H, x=pos[0], y=pos[1],
                        resizable=False, frameless=True, easy_drag=False,
                        on_top=True, background_color="#07080d",
                    )
                    return
                except Exception as e:
                    log.warning("mini panel failed: %s", e)
                    self.panel = None
                    return
        try:
            self.panel.move(*pos)
            self.panel.show()
            self.panel.evaluate_js("window.__aetherPanelRefresh && window.__aetherPanelRefresh()")
        except Exception as e:
            log.warning("mini panel show failed: %s", e)

    def hide_panel(self):
        p = self.panel
        if p is None:
            return
        try:
            p.hide()
        except Exception:
            pass

    def _panel_pos(self):
        sw, sh = 1920, 1080
        try:
            scr = self.webview.screens[0]
            sw, sh = scr.width, scr.height
        except Exception:
            pass
        return panel_position(sw, sh, _cursor_pos())

    # ---- menu callbacks (pystray calls these on its own thread) ----------
    def _on_open(self, icon=None, item=None):
        self.hide_panel()
        self.show_main()

    def _on_panel(self, icon=None, item=None):
        self.show_panel()

    def _on_exit(self, icon=None, item=None):
        self.exit()
