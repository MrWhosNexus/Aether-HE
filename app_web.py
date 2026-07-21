"""AETHER HE — native webview shell.

Renders the exact Claude Design UI (ui/index.html, the standalone React/Tailwind
prototype) in a GTK/WebKit window, and bridges its on-screen state to the real
keyboard over HID. WebKit has no WebHID, so a small injected JS bridge calls into
this Python `Api` (exposed as window.pywebview.api), and mirrors the rendered
per-key colors to the board's global lighting command.
"""
import json
import logging
import os
import sys
import threading
import time

import hid
import webview

from aula_device import AulaDevice
import boards
import drivers
from drivers import UnsupportedFeature
import effects
import device_state
import gamepad
import updater
from tools import board_submission

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("aether.web")

# When frozen by PyInstaller, ui/ ships next to the exe (or inside _MEIPASS for
# --onefile). sys._MEIPASS is the extraction dir at runtime in onefile mode.
if getattr(sys, "frozen", False):
    HERE = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
else:
    HERE = os.path.dirname(os.path.abspath(__file__))
# Prefer the baked-in-bridge build (ui/runtime_src/build_runtime.py); fall back
# to the raw design bundle so the app still launches if it hasn't been built.
_RUNTIME = os.path.join(HERE, "ui", "index_runtime.html")
_BUNDLE = os.path.join(HERE, "ui", "index.html")
INDEX = _RUNTIME if os.path.exists(_RUNTIME) else _BUNDLE

# Travel raw unit (0.01 mm) — identical on every decoded board (Win60 cmd-33
# values and MINI60 0x27 records both use hundredths of a millimeter), so the
# Api can keep its accumulated per-key state in raw units without importing
# any board's protocol module.
_UNIT_MM = 0.01


def _mm_to_raw(mm):
    return max(0, round(float(mm) / _UNIT_MM))


def _host_engine_max_fps(board):
    """The board's `lighting.hostEngineMaxFps` — the measured sustainable
    host-stream frame rate (MINI 60 HE PRO: 28, from the HARDWARE-VERIFIED
    27.7 fps 0x32 benchmark; Win60: 120). None when the board declares no cap.

    Read from the RAW registry JSON: boards.py's lighting validator emits a
    whitelisted set of keys and that module is frozen (do-not-touch), so this
    passthrough field is fetched here instead of from profile.lighting."""
    slug = getattr(board, "slug", None)
    if not slug:
        return None
    try:
        with open(boards.REGISTRY_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        for b in raw.get("boards", []):
            if b.get("slug") == slug:
                v = (b.get("lighting") or {}).get("hostEngineMaxFps")
                return int(v) if v else None
    except Exception as e:
        log.warning("hostEngineMaxFps lookup failed for %s: %s", slug, e)
    return None


def _lighting_block(board):
    """The JS-facing per-board lighting block: profile.lighting augmented
    with hostEngineMaxFps so the UI reads ONE uniform field for the host
    engine's frame-rate cap on every board."""
    lt = getattr(board, "lighting", None)
    if lt is None:
        return None
    fps = _host_engine_max_fps(board)
    if fps:
        lt = dict(lt)
        lt["hostEngineMaxFps"] = fps
    return lt


class Api:
    # Max distinct input frames retained per capture — bounds submission size so
    # a continuous HE telemetry stream can't balloon the JSON past a sane limit.
    _CAP_MAX_REPORTS = 512
    # Max frames kept per distinct key — bounds a held/repeating key so its jittery
    # analog stream can't flood the capture buffer (and the UI) with one key.
    _CAP_MAX_PER_KEY = 6

    # ---- board submission (in-app) ----
    def list_hid_devices(self):
        """Devices for the submit-a-board picker. Read-only enumeration, collapsed
        by (vid, pid, interface): a keyboard exposes one physical interface as
        several HID usage collections, so raw enumeration lists it many times with
        indistinguishable rows. Group them, keep the first openable path, and list
        every usage_page on that interface so the user can tell them apart."""
        try:
            groups = {}
            order = []
            for d in hid.enumerate():
                iface = d.get("interface_number", -1)
                key = (d.get("vendor_id", 0), d.get("product_id", 0), iface)
                path = d.get("path")
                path = path.decode("utf-8", "replace") if isinstance(path, bytes) else str(path)
                up = f"0x{d.get('usage_page', 0):04x}"
                if key not in groups:
                    order.append(key)
                    groups[key] = {
                        "path": path,  # first path for this interface — any collection reads fine
                        "vid": f"0x{d.get('vendor_id', 0):04x}",
                        "pid": f"0x{d.get('product_id', 0):04x}",
                        "manufacturer": d.get("manufacturer_string") or "",
                        "product": d.get("product_string") or "",
                        "usage_page": up,
                        "usage_pages": [up],
                        "interface_number": iface,
                    }
                elif up not in groups[key]["usage_pages"]:
                    groups[key]["usage_pages"].append(up)
            return {"ok": True, "devices": [groups[k] for k in order]}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _capture_arm_indices(self, vid, pid):
        """If the picked device is the recognized, protocol-known board, return the
        key indices to arm its Travel-Test stream with; else None (stay read-only).

        HE boards emit nothing per-key on the vendor interface until that stream is
        enabled — the same reason the calibration/live-reader tools arm it. We only
        ever write to a board whose protocol we already know (VID/PID matches the
        detected board); unknown hardware is never written to."""
        try:
            if not (self.board and vid and pid):
                return None
            if int(str(vid), 16) != self.board.vid or int(str(pid), 16) != self.board.pid:
                return None
            # Only arm when the active driver actually speaks this board's
            # travel-test protocol — arming a foreign board would write the
            # wrong frames at it (the exact bug this dispatch layer fixes).
            drv = getattr(self, "driver", None)
            if drv is not None and not drv.supports("travel_stream"):
                return None
            return list(self.km.indices()) if self.km else None
        except Exception:
            return None

    def _arm_capture(self, dev, idxs):
        """Arm the Travel-Test stream for a capture, through the active
        board's driver. Swallows failures (the capture then runs unarmed /
        read-only). Legacy fallback (no driver wired, e.g. a bare test Api):
        the historical Win60 frame on the given handle."""
        try:
            drv = getattr(self, "driver", None)
            if drv is not None:
                drv.open_trigger_test(list(idxs))
            else:
                import protocol
                dev.write(protocol.build_open_trigger_test(idxs))
        except Exception:
            pass

    def _disarm_capture(self):
        """Disarm the Travel-Test stream armed by _arm_capture (same routing)."""
        try:
            drv = getattr(self, "driver", None)
            if drv is not None:
                drv.close_trigger_test()
            else:
                import protocol
                self.dev.write(protocol.build_close_trigger_test())
        except Exception:
            pass

    def open_capture(self, path, vid=None, pid=None):
        """Stream input reports from the picked device for a board submission.

        Two modes, chosen by whether we recognize the board:

        - RECOGNIZED + CONNECTED (VID/PID matches the detected board and the app's
          own handle is open): capture through the SAME `self.dev` handle the app
          already uses for live travel — arm the firmware Travel-Test stream, read
          under `self.dev._lock`, disarm on stop. This is the proven path: if the
          app's actuation/live-travel works, this works, because it's the same code.
        - UNKNOWN board: open a fresh handle and stay strictly READ-ONLY (never
          writes) — the safety guarantee for hardware whose protocol we don't know.
        """
        try:
            self.stop_capture()  # idempotent: close any prior capture
            self._cap_buf = []
            self._cap_t0 = time.time()
            self._cap_lock = threading.Lock()
            self._cap_stop = threading.Event()

            arm_indices = self._capture_arm_indices(vid, pid)
            _dev = getattr(self, "dev", None)
            shared = bool(arm_indices) and _dev is not None and _dev.is_open()
            self._cap_shared = shared
            self._cap_armed = shared

            lock = self._cap_lock
            buf = self._cap_buf
            stop_ev = self._cap_stop
            t0 = self._cap_t0

            if shared:
                # Reuse the app's open vendor-interface handle (the live-travel path).
                # Pause any live reader so the two loops don't drain the same handle.
                if self.reader:
                    try: self.reader.stop()
                    except Exception: pass
                    self.reader = None
                dev = self.dev
                self._arm_capture(dev, arm_indices)

                def loop():
                    last_arm = time.time()
                    kept = 0
                    # Dedup by KEY IDENTITY, not by frame. A held/repeating key streams
                    # analog Travel-Test frames whose depth jitters every sample, so a
                    # frame-level filter can't catch them and they flood the buffer/UI.
                    # Keep at most _CAP_MAX_PER_KEY samples per distinct key (row/col),
                    # which captures each key's press without ever flooding on a hold.
                    per_key = {}
                    while not stop_ev.is_set() and kept < self._CAP_MAX_REPORTS:
                        # Re-arm periodically like LiveReader: the firmware stops
                        # streaming after a while, so held/late presses would vanish.
                        if time.time() - last_arm > 0.8:
                            last_arm = time.time()
                            self._arm_capture(dev, arm_indices)
                        got = False
                        try:
                            with dev._lock:
                                if not dev._dev:
                                    break
                                dev._dev.set_nonblocking(True)
                                for _ in range(256):          # bounded drain
                                    r = dev._dev.read(64)
                                    if not r:
                                        break
                                    # Travel sub-report → key identity is (row,col) at
                                    # bytes 7-8; other reports keyed by the whole frame.
                                    if len(r) >= 11 and r[1] == 33 and r[5] == 5:
                                        kid = (r[7], r[8])
                                    else:
                                        kid = bytes(r).hex()
                                    if per_key.get(kid, 0) >= self._CAP_MAX_PER_KEY:
                                        continue              # this key already sampled → skip flood
                                    per_key[kid] = per_key.get(kid, 0) + 1
                                    with lock:
                                        buf.append({"t": int((time.time() - t0) * 1000), "hex": bytes(r).hex()})
                                    kept += 1
                                    got = True
                                    if kept >= self._CAP_MAX_REPORTS:
                                        break
                        except Exception:
                            time.sleep(0.05); continue
                        if not got:
                            time.sleep(0.005)
            else:
                # Unknown board: fresh read-only handle, never written to.
                dev = hid.device()
                dev.open_path(path.encode() if isinstance(path, str) else path)
                dev.set_nonblocking(True)
                self._cap_dev = dev

                def loop():
                    last_hex = None
                    kept = 0
                    while not stop_ev.is_set() and kept < self._CAP_MAX_REPORTS:
                        try:
                            r = dev.read(64, timeout_ms=50)
                        except Exception:
                            break
                        if r:
                            hx = bytes(r).hex()
                            if hx == last_hex:
                                continue  # drop consecutive duplicate telemetry frame
                            last_hex = hx
                            with lock:
                                buf.append({"t": int((time.time() - t0) * 1000), "hex": hx})
                            kept += 1
                        else:
                            time.sleep(0.005)

            self._cap_thread = threading.Thread(target=loop, daemon=True)
            self._cap_thread.start()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def read_capture(self):
        """Drain and return input reports buffered since the last call."""
        try:
            buf = getattr(self, "_cap_buf", None)
            if buf is None:
                return {"ok": True, "reports": [], "count": 0}
            with self._cap_lock:
                out = self._cap_buf[:]
                self._cap_buf.clear()
            return {"ok": True, "reports": out, "count": len(out)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def stop_capture(self):
        try:
            ev = getattr(self, "_cap_stop", None)
            if ev:
                ev.set()
            th = getattr(self, "_cap_thread", None)
            if th:
                th.join(timeout=0.3)
            if getattr(self, "_cap_shared", False):
                # Shared app handle: disarm the stream we armed, but never close it —
                # the app owns self.dev and keeps using it.
                self._disarm_capture()
            else:
                dev = getattr(self, "_cap_dev", None)
                if dev:
                    dev.close()
            self._cap_dev = None
            self._cap_shared = False
            self._cap_armed = False
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def __init__(self):
        # Detect which registered board is connected (by VID/PID); fall back to
        # the registry default (Aula Win60 HE) so behaviour is unchanged when no
        # board is plugged in or the registry can't be read.
        #
        # Multi-board machines: registry.detect() returns whatever HID
        # enumeration lists first, which is arbitrary between runs — with the
        # Win60, the MINI 60 PRO and its (deliberately non-drivable) dongle all
        # attached it has picked different boards on different launches. We
        # rank connected boards instead (drivers.connected_profiles: drivable
        # first, registry order within groups); select_board() overrides.
        self.board = None
        self._registry = None
        try:
            reg = boards.load_registry()
            self._registry = reg
            connected = drivers.connected_profiles(reg)
            if connected:
                self.board = connected[0]
                if len(connected) > 1:
                    log.info("Multiple boards connected: %s — preferring %s",
                             [p.slug for p in connected], self.board.slug)
            else:
                self.board = reg.default
            log.info("Active board: %s (%s)", self.board.name, self.board.vid_pid)
        except Exception as e:
            log.warning("board registry unavailable, using Win60 defaults: %s", e)
            self.board = None
        self._lock = threading.Lock()
        self.dev = AulaDevice(self.board) if self.board else AulaDevice()
        # Per-board protocol driver: EVERY packet the Api emits goes through
        # this object. Boards without a wired protocol get an inert driver
        # whose writes raise UnsupportedFeature (surfaced to the UI as
        # {"ok": False, "unsupported": True}) — never another board's frames.
        self.driver = drivers.get_driver(self.board, self.dev, self._lock)
        self.pad = None
        self._pad_stop = threading.Event()
        self._pad_thread = None
        try:
            self.km = device_state.KeyMap(self.board.keymap) if self.board else device_state.KeyMap()
        except Exception as e:
            self.km = None
            log.warning("keymap load failed: %s", e)
        # Host-driven per-key effect engine (multi-color animated effects),
        # paced to the board's measured stream rate when it declares one.
        self.fx = (effects.PerKeyEffectEngine(
                       self.km, self._send_frame,
                       max_fps=_host_engine_max_fps(self.board))
                   if self.km else None)
        self.reader = None
        self._remaps = {}         # accumulated key remaps: {device_index: target_hid}
        self._pad_map = None      # custom gamepad mappings (list of gamepad.KeyMap)
        self.calib_reader = None  # CalibrationReader active during calibration
        # Captured Fn-layer table from the device — replayed verbatim after every
        # base-layer write so the firmware's existing Fn mappings are preserved
        # (the official driver always writes both layers together; writing base
        # without fn leaves the keyboard stuck in function mode).
        self._fn_layer_raw = None
        # Per-key trigger state, mirroring the driver's setAllTriggerValue model.
        # Every apply re-sends the FULL board grouped by config so the firmware
        # sees an unambiguous full state regardless of mask interpretation.
        self._trigger_state = {}   # idx -> (mode, travel_raw, i1_raw, i2_raw)
        # Per-key dead-band state — preserved across selection changes so applying
        # to one group doesn't reset the others to defaults.
        self._deadband_state = {}  # idx -> (top_raw, bottom_raw)

    # ---- connection ----
    @staticmethod
    def _fail(e):
        """Uniform JS-facing failure dict. UnsupportedFeature additionally
        carries `unsupported`/`feature` so the UI can gate controls per board
        instead of showing a generic error."""
        out = {"ok": False, "error": str(e)}
        if isinstance(e, UnsupportedFeature):
            out["unsupported"] = True
            out["feature"] = e.feature
        return out

    def connect(self):
        try:
            # Driver-specific open + handshake (Win60: heartbeat; MINI60:
            # 0x10 device info + LED-table seed; inert boards: open only).
            info = self.driver.connect()
            # Snapshot the device's Fn-layer table so we can replay it after any
            # base-layer write (see _flush_remaps). Failures here are non-fatal;
            # we just won't be able to preserve the user's Fn customization.
            # read_keymap_layer returns None on partial reads — we treat that
            # as "no snapshot" and skip the Fn-layer write entirely rather than
            # risk wiping the user's customisation with a half-zeroed table.
            # Boards without a keymap protocol simply have no snapshot.
            try:
                self._fn_layer_raw = self.driver.read_keymap_layer(fn_layer=True)
            except UnsupportedFeature:
                self._fn_layer_raw = None
            except Exception as ex:
                log.warning("Fn-layer snapshot failed (will skip Fn write): %s", ex)
                self._fn_layer_raw = None
            return {"ok": True, "iface": info["interface_number"]}
        except Exception as e:
            return self._fail(e)

    def get_board(self):
        """Active board + full registered roster, for the UI's board picker/badge.

        Returns capabilities and `drivable` (whether a protocol is wired yet) so the
        UI can gray out lighting/actuation for layout-only boards.
        """
        try:
            reg = boards.load_registry()
            roster = [
                {"slug": p.slug, "name": p.name, "vidPid": p.vid_pid,
                 "formFactor": p.form_factor, "status": p.status,
                 "capabilities": p.capabilities, "drivable": p.drivable,
                 "issues": list(p.issues)}
                for p in reg.profiles
            ]
        except Exception as e:
            log.warning("get_board roster failed: %s", e)
            roster = []
        b = self.board
        active = None if b is None else {
            "slug": b.slug, "name": b.name, "vidPid": b.vid_pid,
            "formFactor": b.form_factor, "status": b.status,
            "capabilities": b.capabilities, "drivable": b.drivable,
            # per-board data blocks (registry-driven effect table, slider scales,
            # deadzone scope, switch list) so the UI can present exactly what THIS
            # board supports instead of the hardcoded Win60 list. None for boards
            # that declare no block. lighting additionally carries the uniform
            # hostEngineMaxFps field (see _lighting_block).
            "lighting": _lighting_block(b),
            "actuation": getattr(b, "actuation", None),
        }
        return {"active": active, "boards": roster}

    def list_boards(self):
        """Every registered board with its live connection state — for the
        board picker (wave 2). `connected` = attached right now; `active` =
        the board this Api instance is driving."""
        try:
            reg = getattr(self, "_registry", None) or boards.load_registry()
        except Exception as e:
            return {"ok": False, "error": str(e), "boards": []}
        try:
            attached = {(p.vid, p.pid) for p in drivers.connected_profiles(reg)}
        except Exception:
            attached = set()
        active_slug = self.board.slug if self.board else None
        out = [
            {"slug": p.slug, "name": p.name, "vidPid": p.vid_pid,
             "formFactor": p.form_factor, "status": p.status,
             "capabilities": p.capabilities, "drivable": p.drivable,
             "connected": (p.vid, p.pid) in attached,
             "active": p.slug == active_slug}
            for p in reg.profiles
        ]
        return {"ok": True, "boards": out, "active": active_slug}

    def select_board(self, slug):
        """Explicitly switch the active board (overrides auto-detection).
        Tears down the current session (effects, readers, capture, handle),
        rebinds device + driver + keymap, and resets per-board caches. The
        UI should call connect() afterwards."""
        try:
            reg = getattr(self, "_registry", None) or boards.load_registry()
        except Exception as e:
            return {"ok": False, "error": str(e)}
        p = reg.by_slug(str(slug))
        if p is None:
            return {"ok": False, "error": f"unknown board: {slug}"}
        try:
            for teardown in (self.stop_capture, self.stop_multicolor,
                             lambda: self.set_gamepad_capture(False)):
                try:
                    teardown()
                except Exception:
                    pass
            if self.reader:
                try: self.reader.stop()
                except Exception: pass
                self.reader = None
            if self.calib_reader:
                try: self.calib_reader.stop()
                except Exception: pass
                self.calib_reader = None
            try:
                self.dev.close()
            except Exception:
                pass
            self.board = p
            self._registry = reg
            self.dev = AulaDevice(p)
            self.driver = drivers.get_driver(p, self.dev, self._lock)
            try:
                self.km = device_state.KeyMap(p.keymap)
            except Exception as e:
                self.km = None
                log.warning("keymap load failed for %s: %s", p.slug, e)
            self.fx = (effects.PerKeyEffectEngine(
                           self.km, self._send_frame,
                           max_fps=_host_engine_max_fps(p))
                       if self.km else None)
            # per-board caches must not leak across boards
            self._remaps = {}
            self._trigger_state = {}
            self._deadband_state = {}
            self._fn_layer_raw = None
            self._idx2code = None
            log.info("Board selected: %s (%s)", p.name, p.vid_pid)
            return {"ok": True, "active": {
                "slug": p.slug, "name": p.name, "vidPid": p.vid_pid,
                "formFactor": p.form_factor, "status": p.status,
                "capabilities": p.capabilities, "drivable": p.drivable,
                # keep in sync with get_board()'s `active` shape
                "lighting": _lighting_block(p),
                "actuation": getattr(p, "actuation", None),
            }}
        except Exception as e:
            return self._fail(e)

    def read_live(self):
        """Real per-key travel depth (mm), keyed by key name. {} until keys move."""
        return self.reader.snapshot() if self.reader else {}

    def status(self):
        return {"connected": self.dev.is_open()}

    def disconnect(self):
        self.stop_multicolor()
        self.set_gamepad_capture(False)
        self.dev.close()
        return {"ok": True}

    # ---- lighting (fg/bg/mode/brightness/speed/dir/power, per-board dispatch) ----
    def set_light(self, mode, r, g, b, brightness=4, speed=4,
                  bg_r=0, bg_g=0, bg_b=0, direction=0, power_on=True, full_color=0):
        try:
            self.driver.set_lighting(
                int(mode), (int(r), int(g), int(b)),
                bg=(int(bg_r), int(bg_g), int(bg_b)),
                brightness=int(brightness), speed=int(speed),
                direction=int(direction), full_color=int(full_color),
                power_on=bool(power_on))
            return {"ok": True}
        except Exception as e:
            return self._fail(e)

    # back-compat: simple static color
    def set_color(self, r, g, b, brightness=4, mode=0, speed=4):
        return self.set_light(mode, r, g, b, brightness, speed)

    # ---- actuation / trigger ----
    def set_trigger_all(self, travel_mm, rt_press_mm=0.0, rt_release_mm=0.0,
                        key_count=64, mode=0):
        try:
            self.driver.set_actuation(list(range(int(key_count))), int(mode),
                                      float(travel_mm), float(rt_press_mm),
                                      float(rt_release_mm))
            return {"ok": True}
        except Exception as e:
            return self._fail(e)

    def open_analog(self, key_count=64):
        return self.open_analog_codes([])

    def open_analog_codes(self, codes=None):
        try:
            if self.km:
                idxs = self.km.indices_for_codes(codes or []) if codes else self.km.indices()
                if not idxs:
                    idxs = self.km.indices()
                if self.reader:
                    self.reader.stop()
                self.reader = self.driver.make_live_reader(self.km, idxs)
                self.reader.start()
            else:
                self.driver.open_trigger_test(list(range(64)))
            return {"ok": True, "keys": len(idxs) if self.km else 64}
        except Exception as e:
            return self._fail(e)

    def close_analog(self):
        try:
            if self.reader:
                self.reader.stop()
                self.reader = None
            else:
                self.driver.close_trigger_test()
            return {"ok": True}
        except Exception as e:
            return self._fail(e)

    # ---- polling ----
    def set_poll(self, rate):
        try:
            self.driver.set_poll_rate(int(rate))
            return {"ok": True}
        except Exception as e:
            return self._fail(e)

    # ---- per-key actuation (codes from the design's selection) ----
    def _flush_triggers(self, edited_idxs=None):
        """Send one packet per group of (mode, travel, i1, i2) — covering ONLY
        the keys we've explicitly edited. When `edited_idxs` is given, we only
        flush packets for groups that include at least one of those keys; that
        avoids re-sending unrelated groups every time the user touches one key.
        """
        if not self._trigger_state:
            return
        edited = set(edited_idxs) if edited_idxs else None
        groups = {}                                       # cfg -> [idx, ...]
        for idx, cfg in self._trigger_state.items():
            groups.setdefault(cfg, []).append(idx)
        for cfg, idxs in groups.items():
            if edited is not None and not (set(idxs) & edited):
                continue
            mode, travel, i1, i2 = cfg
            log.info("trigger pkt: mode=%d travel=%.2fmm i1=%d i2=%d keys=%d %s",
                     mode, travel * _UNIT_MM, i1, i2,
                     len(idxs), sorted(idxs)[:8])
            self.driver.set_actuation(list(idxs), int(mode),
                                      travel * _UNIT_MM,
                                      i1 * _UNIT_MM,
                                      i2 * _UNIT_MM)
            threading.Event().wait(0.005)

    def set_trigger_codes(self, codes, travel_mm, rt_press_mm=0.0, rt_release_mm=0.0, mode=0):
        if not self.km:
            return {"ok": False, "error": "no keymap"}
        idxs = self.km.indices_for_codes(codes) if codes else []
        if not idxs:
            return {"ok": False, "error": "no keys"}
        cfg = (int(mode),
               _mm_to_raw(travel_mm),
               _mm_to_raw(rt_press_mm),
               _mm_to_raw(rt_release_mm))
        for i in idxs:
            self._trigger_state[i] = cfg
        try:
            self._flush_triggers(edited_idxs=idxs)
            return {"ok": True, "keys": len(idxs), "idxs": sorted(idxs)}
        except Exception as e:
            return self._fail(e)

    def verify_actuation(self, codes):
        """Read-back actuation for the given design codes (one cmd-33/sub-5
        query per key). Returns {design_code: travel_mm}, so callers that key
        by design code (the JS UI, every selection set) get a direct lookup.
        read_actuation() keys by `km.name` (the JSON's display label like
        "Esc", "1!") — those don't match the design codes ("Escape", "1") for
        about half the board, which is why the on-screen values silently
        vanished for a chunk of keys."""
        if not self.km or not self.dev.is_open():
            return {"ok": False, "error": "not connected"}
        try:
            # Driver takes the outer lock itself for the whole read sweep.
            vals_by_name = self.driver.read_actuation(self.km)
            # Build {design_code: mm} for every key we have a mapping for.
            all_by_code = {}
            for design_code, idx in self.km.index_of_code.items():
                name = self.km.by_index[idx]["name"]
                mm = vals_by_name.get(name)
                if mm is not None:
                    all_by_code[design_code] = mm
            if codes:
                out = {c: all_by_code.get(c) for c in codes if c in all_by_code}
            else:
                out = all_by_code
            return {"ok": True, "actuation_mm": out}
        except Exception as e:
            return self._fail(e)

    def set_custom_colors(self, colors_by_code, brightness=4, speed=4):
        """colors_by_code: {design_code: [r,g,b]} for per-key custom RGB."""
        if not self.km:
            return {"ok": False, "error": "no keymap"}
        colors_by_index = {}
        for code, rgb in (colors_by_code or {}).items():
            idx = self.km.index_of_code.get(code)
            if idx is not None and rgb and len(rgb) >= 3:
                colors_by_index[idx] = tuple(int(c) for c in rgb[:3])
        if not colors_by_index:
            return {"ok": False, "error": "no colors"}
        try:
            self.driver.set_per_key_rgb(colors_by_index,
                                        brightness=int(brightness),
                                        speed=int(speed))
            return {"ok": True, "keys": len(colors_by_index)}
        except Exception as e:
            return self._fail(e)

    # ---- dead band / switch profile ----
    def set_deadband_codes(self, codes, top_mm=0.04, bottom_mm=0.05):
        if not self.km:
            return {"ok": False, "error": "no keymap"}
        idxs = self.km.indices_for_codes(codes) if codes else []
        # Scope gate. On a GLOBAL-dead-zone board (MINI 60 HE PRO: the value
        # lives in the 0x11/0x21 config table, there is no per-key record)
        # the NORMAL case is "whole board, nothing selected" — the driver
        # ignores the per-key map entirely and needs only top/bottom. Bailing
        # out on an empty selection here made that case a silent no-op while
        # the UI still flashed a success toast. Per-key boards keep the
        # original "no keys" refusal byte-for-byte.
        scope = getattr(self.driver, "DEADBAND_SCOPE", "per-key")
        if not idxs and scope != "global":
            return {"ok": False, "error": "no keys"}
        top = _mm_to_raw(top_mm)
        bottom = _mm_to_raw(bottom_mm)
        # Preserve previously-set per-key values so applying to one selection
        # doesn't reset everything else to the default. The full-board table is
        # rebuilt from the accumulated state on every send. Boards with a
        # GLOBAL dead zone (driver.DEADBAND_SCOPE == "global") ignore the
        # per-key map and apply top/bottom to the whole board.
        for i in idxs:
            self._deadband_state[i] = (top, bottom)
        try:
            self.driver.set_deadband(dict(self._deadband_state),
                                     top_mm=float(top_mm),
                                     bottom_mm=float(bottom_mm))
            # A global write always covers the whole board, so report the
            # board's key count when nothing was explicitly selected — the UI
            # toast ("whole board · every key") must not claim 0 keys.
            written = len(idxs)
            if scope == "global" and not written:
                try:
                    written = len(self.km.indices())
                except Exception:
                    written = 0
            return {"ok": True, "keys": written, "scope": scope}
        except Exception as e:
            return self._fail(e)

    def _resolve_switch_code(self, switch_id):
        """(firmware axis code, error) for a switch selection.

        Accepts either the registry switch `id` string ("hm1") or a raw int
        code. boards.py validates a per-switch `code` (0..255) on every
        board's `actuation.switches` entry, but nothing ever READ it — the
        code came from a hardcoded Win60 table with a `|| 1` fallback, so
        the first board to declare its own axis ids would silently get
        HM1's byte on every key. This resolves against THE ACTIVE BOARD's
        table and fails closed:

          * board declares switches -> the id must be in that table, and a
            raw code must be one the board declares. Unknown -> error, never
            a default byte on the wire.
          * board declares none (Win60 today when the registry is absent,
            legacy/test profiles) -> int codes pass through exactly as
            before; only an unresolvable string is rejected.
        """
        table = (getattr(self.board, "actuation", None) or {}).get("switches") or ()
        by_id, codes = {}, set()
        for s in table:
            if not isinstance(s, dict) or s.get("code") is None:
                continue
            codes.add(int(s["code"]))
            if s.get("id") is not None:
                by_id[str(s["id"])] = int(s["code"])
        name = getattr(self.board, "name", None) or "this board"
        if isinstance(switch_id, str) and switch_id.strip() not in by_id:
            try:
                switch_id = int(switch_id.strip())
            except (TypeError, ValueError):
                return None, f"unknown switch {switch_id!r} for {name}"
        elif isinstance(switch_id, str):
            return by_id[switch_id.strip()], None
        try:
            code = int(switch_id)
        except (TypeError, ValueError):
            return None, f"invalid switch id {switch_id!r}"
        if codes and code not in codes:
            return None, f"switch code {code} is not declared by {name}"
        return code, None

    def set_switch_codes(self, codes, switch_id=1):
        if not self.km:
            return {"ok": False, "error": "no keymap"}
        idxs = self.km.indices_for_codes(codes) if codes else self.km.indices()
        if not idxs:
            return {"ok": False, "error": "no keys"}
        code, err = self._resolve_switch_code(switch_id)
        if err:
            return {"ok": False, "error": err}
        table = {idx: code for idx in idxs}
        try:
            self.driver.set_switch(table)
            return {"ok": True, "keys": len(idxs), "code": code}
        except Exception as e:
            return self._fail(e)

    # ---- key remap (per-board keymap table) ----
    def _flush_remaps(self):
        # Base layer with our remap overrides, then the Fn layer replayed from
        # the connect-time snapshot (both-layer semantics live in the driver).
        defaults = {i: self.km.by_index[i]["hid"] for i in self.km.by_index}
        self.driver.write_keymap(defaults, dict(self._remaps),
                                 self.km.layer_indices, self._fn_layer_raw)

    def set_remap(self, codes, target_hid):
        """Remap the selected keys to emit `target_hid` (USB HID usage code)."""
        if not self.km:
            return {"ok": False, "error": "no keymap"}
        idxs = self.km.indices_for_codes(codes) if codes else []
        if not idxs:
            return {"ok": False, "error": "no keys selected"}
        try:
            for i in idxs:
                self._remaps[i] = int(target_hid) & 0xFF
            self._flush_remaps()
            return {"ok": True, "keys": len(idxs)}
        except Exception as e:
            return self._fail(e)

    def reset_remap(self, codes):
        """Restore the selected keys (or all, if none) to their default mapping."""
        if not self.km:
            return {"ok": False, "error": "no keymap"}
        try:
            if not codes:
                self._remaps = {}
            else:
                for i in self.km.indices_for_codes(codes):
                    self._remaps.pop(i, None)
            self._flush_remaps()
            return {"ok": True}
        except Exception as e:
            return self._fail(e)

    # ---- SOCD / PRCS ----
    def set_socd(self, pairs):
        """pairs: [{model, key1, key2}] using design codes."""
        if not self.km:
            return {"ok": False, "error": "no keymap"}
        try:
            plist = []
            for p in pairs:
                key1_hid = self.km.hid_for_code(p["key1"])
                key2_hid = self.km.hid_for_code(p["key2"])
                if not key1_hid or not key2_hid:
                    return {"ok": False, "error": f"unknown SOCD key: {p}"}
                plist.append({"model": int(p["model"]), "key1_hid": key1_hid, "key2_hid": key2_hid})
            self.driver.set_socd(plist)
            return {"ok": True}
        except Exception as e:
            return self._fail(e)

    # ---- calibration ----
    def _render_calib(self, calibrated):
        """Paint the board green for calibrated keys, dim elsewhere. Called from
        the reader thread only when the set changes (no constant LED traffic)."""
        if not self.km:
            return
        lit = set()
        for c in calibrated:
            idx = self.km.index_of_code.get(c)
            if idx is not None:
                lit.add(idx)
        colors = {idx: ((0, 255, 0) if idx in lit else (6, 10, 8))
                  for idx in self.km.indices()}
        try:
            self.driver.stream_frame(colors, force=True)
        except UnsupportedFeature:
            pass

    def calibrate(self, start, any_key=False):
        try:
            if start:
                # Lighting keeps running during calibration (user's choice). The
                # calibration reader uses a short blocking read so it shares the
                # device with the lighting engine without busy-spinning the lock.
                self.driver.set_calibration(True, bool(any_key))
                self.calib_reader = self.driver.make_calibration_reader(self.km)
                self.calib_reader.start()
            else:
                if self.calib_reader:
                    self.calib_reader.stop()
                    self.calib_reader = None
                self.driver.set_calibration(False, bool(any_key))
            return {"ok": True}
        except Exception as e:
            return self._fail(e)

    def read_calibrated(self):
        """Design codes confirmed calibrated so far (for the on-screen highlight)."""
        if not self.calib_reader:
            return {"ok": True, "codes": [], "done": False}
        return {"ok": True, "codes": self.calib_reader.snapshot(),
                "done": bool(self.calib_reader.done)}

    # ---- gamepad mode / win-lock ----
    def gamepad_mode(self, on):
        try:
            self.driver.set_gamepad_mode(bool(on))
            return {"ok": True}
        except Exception as e:
            return self._fail(e)

    def set_gamepad_capture(self, on):
        """Stream live analog depth into a Linux uinput virtual gamepad."""
        if not on:
            self._pad_stop.set()
            if self._pad_thread:
                self._pad_thread.join(timeout=0.7)
            self._pad_thread = None
            if self.pad:
                self.pad.close()
            self.pad = None
            return {"ok": True}
        try:
            if self.reader is None and self.km:
                self.reader = self.driver.make_live_reader(self.km)
                self.reader.start()
            if self.pad is None:
                self.pad = gamepad.VirtualGamepad(self._pad_map).open()
            self._pad_stop.clear()
            if not self._pad_thread or not self._pad_thread.is_alive():
                self._pad_thread = threading.Thread(target=self._gamepad_loop, daemon=True)
                self._pad_thread.start()
            return {"ok": True}
        except Exception as e:
            if self.pad:
                self.pad.close()
                self.pad = None
            # Surface a hint for the React UI when the failure is the missing
            # kernel driver, so it can offer the one-click installer.
            msg = str(e)
            need_driver = (sys.platform.startswith("win")
                           and "ViGEmBus" in msg)
            return {"ok": False, "error": msg, "needs_vigembus": need_driver}

    def set_gamepad_map(self, mappings):
        """Set the key→control mappings for the virtual gamepad. Each entry:
        {key, axis, direction, threshold_mm}. Applies live if capture is running.
        A re-open is needed when the set of axes/buttons changes, so we rebuild."""
        try:
            kms = [gamepad.KeyMap(
                       str(m.get("key", "")), str(m.get("axis", "LX")),
                       int(m.get("direction", 1)), float(m.get("threshold_mm", 1.5)))
                   for m in (mappings or []) if m.get("key") and m.get("axis")]
            self._pad_map = kms or None
            if self.pad:                      # live: reopen with new capabilities
                was_on = self._pad_thread and self._pad_thread.is_alive()
                self.set_gamepad_capture(False)
                if was_on:
                    return self.set_gamepad_capture(True)
            return {"ok": True, "count": len(kms)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def gamepad_status(self):
        return {"ok": True,
                "capturing": bool(self._pad_thread and self._pad_thread.is_alive()),
                "evdev": gamepad.EVDEV_AVAILABLE,
                "platform": sys.platform,
                "vigembus": gamepad.vigembus_present() if sys.platform.startswith("win") else None,
                "can_install_vigembus": bool(
                    sys.platform.startswith("win") and gamepad._vigembus_installer_path()
                )}

    def install_vigembus(self):
        """Run the bundled ViGEmBus installer (Windows). Prompts UAC."""
        return gamepad.install_vigembus_driver()

    # ---- launch-on-startup (Windows: HKCU Run) ----
    _AUTOSTART_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
    _AUTOSTART_NAME = "AetherHE"

    def _autostart_target(self):
        """The command Windows should invoke at login.

        Frozen exe → run the exe directly; source checkout → fall back to
        pythonw.exe + app_web.py so dev installs still work.
        """
        if getattr(sys, "frozen", False):
            return f'"{sys.executable}"'
        py = sys.executable.replace("python.exe", "pythonw.exe")
        return f'"{py}" "{os.path.join(HERE, "app_web.py")}"'

    def get_autostart(self):
        if not sys.platform.startswith("win"):
            return {"ok": True, "enabled": False, "supported": False}
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self._AUTOSTART_KEY) as k:
                val, _ = winreg.QueryValueEx(k, self._AUTOSTART_NAME)
                return {"ok": True, "supported": True, "enabled": True, "command": val}
        except FileNotFoundError:
            return {"ok": True, "supported": True, "enabled": False}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ---- settings persistence (JSON in user data dir) ----
    def _settings_path(self):
        if sys.platform.startswith("win"):
            root = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        elif sys.platform == "darwin":
            root = os.path.expanduser("~/Library/Application Support")
        else:
            root = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
        d = os.path.join(root, "AetherHE")
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, "settings.json")

    def load_settings(self):
        try:
            import json
            with open(self._settings_path(), "r", encoding="utf-8") as f:
                return {"ok": True, "settings": json.load(f)}
        except FileNotFoundError:
            return {"ok": True, "settings": None}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def save_settings(self, settings):
        """Persist the UI's settings blob, PRESERVING top-level keys it doesn't own.

        The UI sends the whole blob *it* manages (profiles, theme, sections).
        Writing that verbatim silently dropped keys written by other paths:
        `autoUpdate`, set by set_auto_update() when the user answers the
        first-run prompt, was erased by the next profile/theme save, so the app
        treated them as first-run again and re-prompted on every launch.

        Merging instead of replacing fixes that key and the whole class — any
        future setting written by a different code path survives a UI save.
        A missing or corrupt file is treated as empty rather than failing the
        save, matching the updater's own tolerance for a damaged settings.json.
        """
        try:
            import json
            path = self._settings_path()
            existing = {}
            try:
                with open(path, encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    existing = loaded
            except (OSError, ValueError):
                existing = {}
            merged = dict(existing)
            merged.update(settings or {})
            with open(path, "w", encoding="utf-8") as f:
                json.dump(merged, f, indent=2)
            return {"ok": True, "path": path}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def settings_info(self):
        """Where settings.json lives + whether it exists. UI shows this in the
        Settings tab so users can find / back up / wipe the file."""
        p = self._settings_path()
        return {"ok": True, "path": p, "exists": os.path.exists(p)}

    # ---- board submission (schema-validated file write) ----
    def _submissions_dir(self):
        base = os.path.dirname(self._settings_path())   # <root>/AetherHE
        d = os.path.join(base, "submissions")
        os.makedirs(d, exist_ok=True)
        return d

    def save_submission(self, obj):
        """Validate against aether-board-submission/1 and write to the submissions dir."""
        # Trim stray whitespace on free-text meta fields before validation/save so
        # "Aula " doesn't leak into the slug or the drafted board name.
        meta = obj.get("meta")
        if isinstance(meta, dict):
            for k in ("brand", "model", "form_factor"):
                if isinstance(meta.get(k), str):
                    meta[k] = meta[k].strip()
        errors = board_submission.validate_submission(obj)
        if errors:
            return {"ok": False, "errors": errors}
        try:
            slug = "".join(c for c in (obj.get("meta", {}).get("model", "board")).lower()
                           if c.isalnum() or c == "-") or "board"
            fn = f"board-{slug}-{time.strftime('%Y%m%d-%H%M%S')}.json"
            path = os.path.join(self._submissions_dir(), fn)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(obj, f, indent=2)
            return {"ok": True, "path": path}
        except Exception as e:
            return {"ok": False, "errors": [str(e)]}

    def open_submission_url(self, url):
        """Open the pre-filled GitHub issue in the default browser."""
        try:
            import webbrowser
            webbrowser.open(str(url))
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ---- updates (GitHub Releases, cross-platform) ----
    def app_version(self):
        import version
        return {"ok": True, "version": version.__version__, "kind": updater.platform_kind()}

    def check_update(self):
        """Ask GitHub for the latest release and whether it's newer than us."""
        return updater.check_for_update()

    def get_auto_update(self):
        """Auto-update-on-launch preference. `autoUpdate` is None when never set
        (first run), else a bool. The UI uses None to show the first-run prompt."""
        return {"ok": True, "autoUpdate": updater.get_auto_update(self._settings_path())}

    def set_auto_update(self, on):
        """Persist the auto-update-on-launch preference (merged into settings.json)."""
        try:
            val = updater.set_auto_update(self._settings_path(), bool(on))
            return {"ok": True, "autoUpdate": val}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def apply_update(self, asset_url, asset_name=None):
        """Download + install the update for this OS. On success the caller
        should quit (Windows) or prompt a restart (Flatpak)."""
        res = updater.apply_update(asset_url, asset_name)
        if res.get("ok") and res.get("quit"):
            # Let the bridge return first, then exit so the installer can replace
            # files that are otherwise locked by the running process.
            def _bye():
                threading.Event().wait(0.6)
                os._exit(0)
            threading.Thread(target=_bye, daemon=True).start()
        return res

    def reveal_settings(self):
        """Open the settings folder in the OS file manager."""
        p = self._settings_path()
        d = os.path.dirname(p)
        try:
            if sys.platform.startswith("win"):
                os.startfile(d)
            elif sys.platform == "darwin":
                import subprocess; subprocess.Popen(["open", d])
            else:
                import subprocess; subprocess.Popen(["xdg-open", d])
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def set_autostart(self, on):
        if not sys.platform.startswith("win"):
            return {"ok": False, "error": "autostart is Windows-only"}
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self._AUTOSTART_KEY,
                                0, winreg.KEY_SET_VALUE) as k:
                if on:
                    winreg.SetValueEx(k, self._AUTOSTART_NAME, 0, winreg.REG_SZ,
                                      self._autostart_target())
                else:
                    try: winreg.DeleteValue(k, self._AUTOSTART_NAME)
                    except FileNotFoundError: pass
            return {"ok": True, "enabled": bool(on)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _gamepad_loop(self):
        import time
        while not self._pad_stop.is_set():
            try:
                if self.pad and self.reader:
                    self.pad.update(self.reader.snapshot())
            except Exception as e:
                log.warning("gamepad capture stopped: %s", e)
                break
            time.sleep(1 / 120)

    def send_raw(self, hex_str):
        try:
            payload = [int(x, 16) for x in hex_str.replace(",", " ").split()]
            if len(payload) < 64:
                payload += [0] * (64 - len(payload))
            with self._lock:
                self.dev.write(payload)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ---- host-driven multi-color effects (per-key, driver stream) ----
    def _send_frame(self, colors_by_index):
        """Stream one per-key RGB frame through the board driver. The driver
        owns the diff cache (only changed pages are re-sent) and holds the
        outer lock for the whole frame so a set_light can't slip between
        pages. Failures are swallowed like before (the engine keeps running);
        the driver resets its cache on error."""
        if not self.dev.is_open():
            return
        try:
            self.driver.stream_frame(colors_by_index)
        except Exception:
            pass

    def _ensure_reactive(self, modes):
        """Press-reactive effects need live travel: attach a depth source (and a
        running analog reader). Other effects detach it."""
        if not self.fx:
            return
        if any(m in ("reactive", "ripple", "speedres", "cross", "fireworks") for m in modes):
            if self.reader is None and self.km:
                try:
                    self.reader = self.driver.make_live_reader(self.km)
                    self.reader.start()
                except UnsupportedFeature:
                    self.reader = None
            rdr = self.reader
            km = self.km
            self.fx.get_depths = (lambda: {km.index_of_code[c]: mm
                                           for c, mm in rdr.snapshot().items()
                                           if c in km.index_of_code}) if rdr else None
        else:
            self.fx.get_depths = None

    def get_light_frame(self):
        """Current per-key effect frame keyed by design code — the in-app keyboard
        polls this to mirror the live animation. {} when no host effect is running."""
        if not self.fx or not self.fx.is_running():
            return {}
            
        idx2code = getattr(self, '_idx2code', None)
        if idx2code is None:
            self._idx2code = idx2code = {v: k for k, v in self.km.index_of_code.items()}
            
        out = {}
        # Iterate over the dict directly (thread-safe since fx engine swaps it atomically)
        for idx, rgb in self.fx.last_frame.items():
            code = idx2code.get(idx)
            if code:
                out[code] = rgb
        return out

    def start_multicolor(self, pattern, colors, bg=(0, 0, 0), brightness=80,
                         speed=60, direction=0, orient="v"):
        """Run a host-driven multi-color animated effect. `colors` is a list of
        [r,g,b]; firmware built-in effects only hold one fg+bg, so 2+ colors must
        be animated from the host via per-key RGB."""
        if not self.fx:
            return {"ok": False, "error": "no keymap"}
        try:
            # Put the board into per-key Custom mode (full brightness — the engine
            # bakes brightness into the per-key colors it streams). Boards whose
            # high-rate channel is unproven refuse here (UnsupportedFeature)
            # instead of pretending an animation is running.
            self.driver.begin_host_stream()
            self._ensure_reactive([str(pattern)])
            pal = [tuple(int(c) for c in p[:3]) for p in (colors or []) if p]
            self.fx.start(str(pattern), pal or [(255, 255, 255)],
                          tuple(int(c) for c in (bg or (0, 0, 0))[:3]),
                          float(speed) / 100.0, float(brightness) / 100.0,
                          int(direction), str(orient))
            return {"ok": True, "keys": len(self.fx.indices)}
        except Exception as e:
            return self._fail(e)

    def start_zones(self, zones):
        """Composite multiple effect zones at once. Each zone:
        {codes:[design_code,...], mode, colors:[[r,g,b],...], bg, brightness, speed, direction}."""
        if not self.fx:
            return {"ok": False, "error": "no keymap"}
        try:
            norm = []
            for z in (zones or []):
                idxs = [self.km.index_of_code[c] for c in z.get("codes", [])
                        if c in self.km.index_of_code]
                if not idxs:
                    continue
                norm.append({
                    "indices": idxs,
                    "mode": str(z.get("mode", "wave")),
                    "palette": [tuple(int(c) for c in p[:3]) for p in (z.get("colors") or []) if p]
                               or [(255, 255, 255)],
                    "bg": tuple(int(c) for c in (z.get("bg") or (0, 0, 0))[:3]),
                    "speed": float(z.get("speed", 60)) / 100.0,
                    "bright": float(z.get("brightness", 80)) / 100.0,
                    "direction": int(z.get("direction", 0)),
                    "orient": str(z.get("orient", "v")),
                })
            if not norm:
                return {"ok": False, "error": "no zones"}
            self.driver.begin_host_stream()
            self._ensure_reactive([z["mode"] for z in norm])
            gbg = norm and norm[0].get("bg") or (0, 0, 0)
            self.fx.start_zones(norm, global_bg=gbg)
            return {"ok": True, "zones": len(norm)}
        except Exception as e:
            return self._fail(e)

    def stop_multicolor(self):
        if self.fx and self.fx.is_running():
            self.fx.stop()
            # Hand the LEDs back to the board once the engine is down. The
            # Win60's end_host_stream is the base no-op (it has no stop
            # command — the board keeps the last frame in Custom mode,
            # exactly as before); the MINI 60 PRO sends CLEAR_LED_DATA
            # (0x36) to stop/clear its live 0x32 stream. Failures are
            # swallowed: stop must always succeed from teardown paths.
            try:
                self.driver.end_host_stream()
            except Exception:
                pass
        return {"ok": True}

    # back-compat no-ops (the old global-effect API was removed)
    def stop_effect(self):
        return self.stop_multicolor()

    @staticmethod
    def _hex(h):
        h = h.lstrip("#")
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


# Minimal native injection. The React UI (ui/index_runtime.html) drives ALL HID
# through window.pywebview.api; this only adds one thing the in-page app can't
# do itself: stop a physical keypress from activating the focused WebKit button,
# so pressing keys for Travel Test / Calibration is safe.
# (A floating "PAD off" capture toggle used to live here too; it bypassed React
# state and fought the GAMEPAD tab's own toggle, so it's gone. Use that tab.)
NATIVE_JS = r"""
(() => {
  function isEditable(el) {
    return !!el && !!el.closest('input, textarea, select, [contenteditable="true"]');
  }
  ['keydown', 'keyup', 'keypress'].forEach(type => {
    window.addEventListener(type, e => {
      if (!isEditable(e.target)) { e.preventDefault(); e.stopImmediatePropagation(); }
    }, true);
  });

  console.log('AETHER native shell: key-suppression ready');
})();
"""


def _on_start(window):
    """Inject the small native helper once the React app has mounted, then log a
    one-shot render-state probe so launch issues are visible in the console."""
    import time
    time.sleep(1.5)  # let React mount and pywebview inject its api
    try:
        window.evaluate_js(NATIVE_JS)
    except Exception as e:
        log.warning("native inject failed: %s", e)
    time.sleep(0.8)
    try:
        state = window.evaluate_js("""
          (() => ({
            ready: document.readyState,
            rootChildren: document.getElementById('root') ? document.getElementById('root').children.length : -1,
            react: !!window.React,
            reactDOM: !!window.ReactDOM,
            bridge: !!(window.pywebview && window.pywebview.api),
            errors: (window.__aetherErrors || []).slice(0, 5),
            text: (document.body && document.body.innerText || '').slice(0, 160)
          }))()
        """)
        log.info("Webview render state: %s", state)
    except Exception as e:
        log.warning("render-state probe failed: %s", e)


def main():
    if not os.path.exists(INDEX):
        raise SystemExit(f"UI not found: {INDEX}")
    api = Api()
    # Pass an explicit file:// URI: pywebview only treats a string as a local
    # file when it exists on disk verbatim, and a "?v=" cache-buster query
    # breaks that check (the page then loads as a remote URL — which inside a
    # Flatpak/WebKit sandbox fails with a portal "NotAllowed" error).
    # The mtime goes in the URL fragment, not the query: Edge WebView2 on
    # Windows does not strip query strings from file:// URIs and resolves
    # `index_runtime.html?v=…` as a literal filename → ERR_FILE_NOT_FOUND.
    # Fragments are client-side only and safe on every backend.
    from pathlib import Path
    url = Path(INDEX).as_uri() + f"#v={int(os.path.getmtime(INDEX))}"
    window = webview.create_window(
        "Aether", url, js_api=api,
        width=1340, height=900, min_size=(1160, 800),
        background_color="#07080d",
    )
    webview.start(_on_start, window)


if __name__ == "__main__":
    main()
