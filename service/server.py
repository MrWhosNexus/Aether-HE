"""AETHER `/aether/*` loopback service.

Wraps the existing `app_web.Api` (the pywebview HID bridge) in a plain HTTP
server so the nexus workspace panel can drive the real keyboard. Spec:
nexus/docs/brainstorm/2026-07-04-aether-port-spec.md §4.

Design constraints honoured here:
  * Reuse the driver unchanged — every route is a thin pass-through to an
    existing Api method; the JSON envelope is whatever that method returns.
  * stdlib only (http.server). High-rate streams are exposed both as the
    polled GET routes the renderer already uses (analog/live, light/frame,
    calibrate/state) and as one SSE channel (GET /aether/stream) that pushes
    travel (33ms), light_frame (50ms) and calibration (80ms) events.
  * Binds 127.0.0.1 only. Loopback callers only; the nexus Electron backend
    fronts this with its own x-nexus-token gate.
  * Graceful with no keyboard attached: board detect falls back to the
    registry default (driver behaviour), /aether/board always answers with
    connected:false, and /aether/connect returns {ok:false, error} instead
    of crashing.
  * SOCD models 2-4 are rejected server-side (spec fix F1): only model 1
    has a verified firmware round-trip.

Run:  venv-web\Scripts\python.exe service\server.py  [--port 8672]
"""
import json
import logging
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from app_web import Api  # noqa: E402  (driver reused verbatim)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("aether.service")

DEFAULT_PORT = int(os.environ.get("AETHER_SERVICE_PORT", "8672"))

api = Api()
_start_ts = time.time()


def _codes_from_query(qs):
    raw = (qs.get("codes") or [""])[0]
    return [c for c in raw.split(",") if c] if raw else []


# ---- route table -----------------------------------------------------------
# (method, path) -> fn(body, qs) returning a JSON-serialisable object.
# Paths mirror renderer/src/panels/aether/service.ts 1:1.

def _board(_b, _q):
    out = api.get_board()
    out["connected"] = api.dev.is_open()
    # Explicit no-board shape: detection fell back to the registry default
    # (or nothing) and the device is not open.
    if not out["connected"] and out.get("active") is None:
        out["board"] = None
    return out


def _socd(b, _q):
    pairs = b.get("pairs") or []
    bad = [p for p in pairs if int(p.get("model", 1)) != 1]
    if bad:
        return {"ok": False,
                "error": "SOCD models 2-4 are unverified on this firmware; "
                         "only model 1 (first press wins) is supported"}
    return api.set_socd(pairs)


ROUTES = {
    # health / identity
    ("GET", "/aether/health"): lambda b, q: {"ok": True, "service": "aether",
                                             "pid": os.getpid(),
                                             "uptime_s": round(time.time() - _start_ts, 1)},
    # board / connection
    ("GET", "/aether/board"): _board,
    ("POST", "/aether/connect"): lambda b, q: api.connect(),
    ("POST", "/aether/disconnect"): lambda b, q: api.disconnect(),
    ("GET", "/aether/status"): lambda b, q: api.status(),
    # lighting
    ("POST", "/aether/light"): lambda b, q: api.set_light(
        b.get("mode", 0), b.get("r", 255), b.get("g", 255), b.get("b", 255),
        b.get("brightness", 4), b.get("speed", 4),
        b.get("bg_r", 0), b.get("bg_g", 0), b.get("bg_b", 0),
        b.get("direction", 0), b.get("power_on", True), b.get("full_color", 0)),
    ("POST", "/aether/light/multicolor"): lambda b, q: api.start_multicolor(
        b.get("pattern", "wave"), b.get("colors") or [],
        tuple(b.get("bg") or (0, 0, 0)), b.get("brightness", 80),
        b.get("speed", 60), b.get("direction", 0), b.get("orient", "v")),
    ("POST", "/aether/light/zones"): lambda b, q: api.start_zones(b.get("zones") or []),
    ("POST", "/aether/light/custom"): lambda b, q: api.set_custom_colors(
        b.get("colors_by_code") or {}, b.get("brightness", 4), b.get("speed", 4)),
    ("POST", "/aether/light/stop"): lambda b, q: api.stop_multicolor(),
    ("GET", "/aether/light/frame"): lambda b, q: api.get_light_frame(),
    # actuation / trigger
    ("POST", "/aether/trigger"): lambda b, q: api.set_trigger_codes(
        b.get("codes") or [], b.get("travel_mm", 2.0),
        b.get("rt_press_mm", 0.0), b.get("rt_release_mm", 0.0), b.get("mode", 0)),
    ("POST", "/aether/deadband"): lambda b, q: api.set_deadband_codes(
        b.get("codes") or [], b.get("top_mm", 0.04), b.get("bottom_mm", 0.05)),
    ("POST", "/aether/switch"): lambda b, q: api.set_switch_codes(
        b.get("codes") or [], b.get("switch_id", 1)),
    ("POST", "/aether/poll"): lambda b, q: api.set_poll(b.get("rate", 1)),
    ("GET", "/aether/actuation"): lambda b, q: api.verify_actuation(_codes_from_query(q)),
    # analog / travel test
    ("POST", "/aether/analog/open"): lambda b, q: api.open_analog_codes(b.get("codes") or []),
    ("POST", "/aether/analog/close"): lambda b, q: api.close_analog(),
    ("GET", "/aether/analog/live"): lambda b, q: api.read_live(),
    # calibration
    ("POST", "/aether/calibrate"): lambda b, q: api.calibrate(
        bool(b.get("start")), bool(b.get("any_key", False))),
    ("GET", "/aether/calibrate/state"): lambda b, q: api.read_calibrated(),
    # SOCD (model 1 only — spec F1)
    ("POST", "/aether/socd"): _socd,
    # keymap
    ("POST", "/aether/remap"): lambda b, q: api.set_remap(
        b.get("codes") or [], b.get("target_hid", 0)),
    ("POST", "/aether/remap/reset"): lambda b, q: api.reset_remap(b.get("codes") or []),
    # gamepad
    ("POST", "/aether/gamepad/map"): lambda b, q: api.set_gamepad_map(b.get("map") or []),
    ("POST", "/aether/gamepad/capture"): lambda b, q: api.set_gamepad_capture(bool(b.get("on"))),
    ("POST", "/aether/gamepad/install-driver"): lambda b, q: api.install_vigembus(),
    ("GET", "/aether/gamepad/status"): lambda b, q: api.gamepad_status(),
    # settings / persistence
    ("GET", "/aether/settings"): lambda b, q: api.load_settings(),
    ("POST", "/aether/settings"): lambda b, q: api.save_settings(b),
    ("GET", "/aether/settings/info"): lambda b, q: api.settings_info(),
    ("POST", "/aether/settings/reveal"): lambda b, q: api.reveal_settings(),
    # app / updates / autostart
    ("GET", "/aether/version"): lambda b, q: api.app_version(),
    ("GET", "/aether/update/check"): lambda b, q: api.check_update(),
    ("POST", "/aether/update/apply"): lambda b, q: api.apply_update(
        b.get("asset_url"), b.get("asset_name")),
    ("GET", "/aether/autostart"): lambda b, q: api.get_autostart(),
    ("POST", "/aether/autostart"): lambda b, q: api.set_autostart(bool(b.get("enabled"))),
}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "AetherService/1.0"

    def log_message(self, fmt, *args):  # route access logs through logging
        log.debug("%s " + fmt, self.address_string(), *args)

    def _json(self, status, obj):
        payload = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _dispatch(self, method):
        url = urlparse(self.path)
        if url.path == "/aether/stream" and method == "GET":
            return self._sse()
        fn = ROUTES.get((method, url.path))
        if fn is None:
            return self._json(404, {"ok": False, "error": f"no route: {method} {url.path}"})
        body = {}
        if method == "POST":
            try:
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}") if n else {}
            except Exception as e:
                return self._json(400, {"ok": False, "error": f"bad json body: {e}"})
        try:
            out = fn(body, parse_qs(url.query))
            self._json(200, out if out is not None else {"ok": True})
        except Exception as e:
            log.exception("handler failed: %s %s", method, url.path)
            self._json(500, {"ok": False, "error": str(e)})

    def _sse(self):
        """Combined push stream: travel @33ms, light_frame @50ms, calibration
        @80ms — replaces the standalone app's three JS polling intervals."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        def emit(obj):
            self.wfile.write(f"data: {json.dumps(obj)}\n\n".encode("utf-8"))
            self.wfile.flush()

        last_frame = last_calib = 0.0
        try:
            emit({"type": "hello", "connected": api.dev.is_open()})
            while True:
                now = time.time()
                if api.reader:
                    emit({"type": "travel", "depths": api.read_live()})
                if api.fx and api.fx.is_running() and now - last_frame >= 0.05:
                    emit({"type": "light_frame", "frame": api.get_light_frame()})
                    last_frame = now
                if api.calib_reader and now - last_calib >= 0.08:
                    st = api.read_calibrated()
                    emit({"type": "calibration", "codes": st.get("codes", []),
                          "done": st.get("done", False)})
                    last_calib = now
                time.sleep(0.033)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass  # client went away

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")


def main():
    port = DEFAULT_PORT
    argv = sys.argv[1:]
    if "--port" in argv:
        port = int(argv[argv.index("--port") + 1])
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    srv.daemon_threads = True
    b = api.board
    log.info("aether service on http://127.0.0.1:%d (board: %s, connected: %s)",
             port, b.name if b else None, api.dev.is_open())
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            api.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    main()
