"""AETHER HE — native webview shell.

Renders the exact Claude Design UI (ui/index.html, the standalone React/Tailwind
prototype) in a GTK/WebKit window, and bridges its on-screen state to the real
keyboard over HID. WebKit has no WebHID, so a small injected JS bridge calls into
this Python `Api` (exposed as window.pywebview.api), and mirrors the rendered
per-key colors to the board's global lighting command.
"""
import contextlib
import json
import logging
import os
import re
import sys
import threading
import time

# Stdlib-only: installed before the third-party imports below, so a missing
# DLL / broken bundle in the windowed exe leaves a log and an error box
# instead of a process that just vanishes.
import boot
from boot import user_data_dir
if __name__ == "__main__":
    boot.install_file_logging()

import hid
import webview

from aula_device import AulaDevice
import boards
import drivers
from drivers import UnsupportedFeature
import effects
import device_state
import gamepad
import games
import telemetry
import updater
import tray
import single_instance
import analytics
import overlays
import music
from tools import board_submission

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("aether.web")

#: settings.json key for the key-statistics switch (Settings > Key statistics).
STATS_SETTING = "collectKeyStats"

# Serialises Api.save_settings' read-merge-write: the UI's profile saves and
# Python-side writers (games map, stats toggle) run on different pywebview /
# poll threads, and two interleaved merges would drop one writer's keys.
_SETTINGS_LOCK = threading.Lock()
# Serialises the overlay carrier (engine start/stop + firmware restore). Always the
# OUTERMOST lock on its paths: nothing that holds Api._lock or the device lock calls
# into the carrier, and the engine thread never takes it, so fx.stop()'s join is safe.
_CARRIER_LOCK = threading.RLock()


def _stats_default_enabled(settings, platform=None):
    """Whether key statistics collect. A stored bool wins; otherwise ON only
    on Windows (the shipping target), so Linux behaviour is unchanged unless
    the user opts in."""
    if isinstance(settings, dict) and isinstance(settings.get(STATS_SETTING), bool):
        return settings[STATS_SETTING]
    return (platform or sys.platform).startswith("win")


def _clamp_stats_days(days):
    """Bridge `days` argument -> int in 1..telemetry.KEEP_DAYS (non-int -> 1)."""
    if isinstance(days, bool) or not isinstance(days, int):
        return 1
    return max(1, min(telemetry.KEEP_DAYS, days))


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
                            # Idle: 100 Hz is plenty — each pass drains up to
                            # 256 queued reports, so nothing is lost.
                            time.sleep(0.01)
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
            self._cap_thread = None
            if getattr(self, "_cap_shared", False):
                # Shared app handle: disarm the stream we armed, but never close it —
                # the app owns self.dev and keeps using it.
                self._disarm_capture()
                # open_capture paused the shared live reader (set self.reader
                # = None) but left its owners registered. Anyone still
                # claiming it (analog tab / gamepad / reactive effects) would
                # otherwise be stranded on a dead stream, so bring it back.
                self._restore_shared_reader()
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
        # Reentrant so a driver read-modify-write can hold it across the whole
        # op (driver.transaction()) while the per-frame _write re-acquires it.
        self._lock = threading.RLock()
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
        # Who needs the shared live reader running (analog tab / gamepad /
        # reactive effects). The reader stops only when this empties, so
        # turning one consumer off can't strand another's stream.
        self._reader_users = set()
        self._remaps = {}         # accumulated key remaps: {device_index: target_hid}
        self._pad_map = None      # custom gamepad mappings (list of gamepad.KeyMap)
        self.calib_reader = None  # CalibrationReader active during calibration
        self._calibrating = False  # firmware armed in calibration mode (disarm on abort)
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
        # idx -> actuation mm, for the pressure effect. Filled by verify_actuation
        # (firmware read-back) and successful actuation writes; read lock-free
        # (the engine takes dict() copies via _actuation_snapshot).
        self._act_mm = {}
        # idx -> (trigger mode, rt press mm|None, rt release mm|None) from the
        # same read-back / successful writes; with _act_mm it tells
        # apply_profile_to_board whether the board already holds a profile's
        # actuation (skip the flash write). Cleared on every connect.
        self._trig_mode = {}
        self._socd_last = None      # last SOCD pairs written this connection
        self._pending_board = None  # game-profile board apply waiting for connect
        self._init_link_state()
        self.telemetry = self._make_telemetry()
        # Status on keys (overlays.py): the layer rides on the effect engine.
        self._overlays = None
        self._ov_profile = None     # active profile id, fed by games_sync
        self._carrier_on = False    # engine running ONLY to carry overlays
        self._light_src = None      # last firmware-lighting call, for the carrier
        self._ov_attach()
        # Music visualizer (music.py): one capture source for the app's
        # lifetime; the engine starts it only while a "music" zone runs.
        self._music = music.MusicSource()
        self._music_attach()
        self._games = self._make_games()

    # ---- key statistics plumbing ----
    def _make_telemetry(self):
        """Key-statistics collector (no disk or threads until the first
        flush). Never raises: None disables the feature."""
        try:
            s = (self.load_settings() or {}).get("settings")
            return telemetry.Telemetry(
                os.path.join(user_data_dir(), "stats"),
                enabled=_stats_default_enabled(s),
                board=self.board.slug if self.board else None)
        except Exception as e:
            log.warning("key statistics unavailable: %s", e)
            return None

    def _make_games(self):
        """Game detection service (games.py). Reads the cached Discord list;
        no thread until _start_games. Never raises: None disables it."""
        try:
            return games.GameService(
                user_data_dir(),
                lambda: (self.load_settings() or {}).get("settings"),
                self.save_settings)
        except Exception as e:
            log.warning("game detection unavailable: %s", e)
            return None

    def _start_games(self, on_detected=None):
        """main(): start polling (Windows only). `on_detected(name|None)`
        feeds the tray tooltip."""
        g = getattr(self, "_games", None)
        if g is None:
            return False
        g.on_detected = on_detected
        return g.start()

    def _stop_games(self):
        g = getattr(self, "_games", None)
        if g is not None:
            g.stop()


    def _stats_supported(self):
        """Does the active board declare keyStats AND stream live travel?"""
        try:
            board = getattr(self, "board", None)
            drv = getattr(self, "driver", None)
            return bool(board is not None and drv is not None
                        and board.cap("keyStats") is True
                        and drv.supports("travel_stream"))
        except Exception:
            return False

    def _make_live_reader(self, indices=None):
        """The ONLY place live readers are built: attaches the telemetry hook
        (a new reader means the old stream ended, so in-flight presses are
        dropped rather than left open)."""
        if indices is None:
            r = self.driver.make_live_reader(self.km)
        else:
            r = self.driver.make_live_reader(self.km, indices)
        tel = getattr(self, "telemetry", None)
        if tel is not None and self._stats_supported():
            try:
                tel.abort_open()
                r.on_sample = tel.feed
            except Exception:
                pass
        return r

    def _start_stats_reader(self):
        """Claim the shared reader under owner "telemetry" so the travel
        stream runs whenever statistics are on. Never raises."""
        tel = getattr(self, "telemetry", None)
        try:
            if (tel is None or not tel.enabled or not self._stats_supported()
                    or not self.km or not self.dev.is_open()):
                return False
            if self._calibrating:
                # CalibrationReader must be the only drain; the calibrate-off
                # restore starts the stream.
                with self._lock:
                    self._reader_users.add("telemetry")
                return True
            self._acquire_reader("telemetry", self._make_live_reader)
            return True
        except Exception as e:
            log.warning("key statistics reader not started: %s", e)
            try:
                self._release_reader("telemetry")
            except Exception:
                pass
            return False

    def _stats_actuation(self, mm_by_idx):
        """Hand the firmware read-back ({device index: mm}) to telemetry."""
        tel = getattr(self, "telemetry", None)
        if tel is not None and mm_by_idx and self._stats_supported():
            tel.set_actuation(mm_by_idx)

    def _note_actuation(self, mm_by_idx):
        """Remember per-key actuation ({device index: mm}) for the pressure
        effect. Unlike telemetry's copy (which forgets on every write so presses
        read "unrated" until the next read-back) this keeps the WRITTEN value:
        the effect wants the best current guess. Non-finite / out-of-range
        values are dropped."""
        cur = getattr(self, "_act_mm", None)
        if cur is None:
            cur = self._act_mm = {}
        for idx, mm in (mm_by_idx or {}).items():
            try:
                v = float(mm)
            except (TypeError, ValueError):
                continue
            if v == v and 0.0 < v < 100.0:
                cur[idx] = v

    def _actuation_snapshot(self):
        """Copy of the per-key actuation map ({device index: mm})."""
        return dict(getattr(self, "_act_mm", None) or {})

    def _note_trigger_modes(self, idxs, mode, rt_press_mm, rt_release_mm):
        """A successful actuation write: remember each key's trigger mode
        (and RT pair in an RT mode; mode 0 keeps the stored pair, unknown)."""
        cur = getattr(self, "_trig_mode", None)
        if cur is None:
            cur = self._trig_mode = {}
        mode = int(mode)
        rt = ((None, None) if mode == 0
              else (round(float(rt_press_mm), 2), round(float(rt_release_mm), 2)))
        for i in idxs:
            cur[i] = (mode,) + rt

    def _note_read_back_modes(self, detail_by_idx):
        """verify_actuation's per-key trigger detail -> _trig_mode."""
        cur = getattr(self, "_trig_mode", None)
        if cur is None:
            cur = self._trig_mode = {}
        for idx, d in (detail_by_idx or {}).items():
            try:
                cur[idx] = (int(d["mode"]), round(float(d.get("rt_press_mm") or 0.0), 2),
                            round(float(d.get("rt_release_mm") or 0.0), 2))
            except (KeyError, TypeError, ValueError):
                cur.pop(idx, None)

    def _stats_forget_actuation(self, idxs):
        """An actuation write makes the stored read-back stale: forget it."""
        tel = getattr(self, "telemetry", None)
        if tel is not None and idxs and self._stats_supported():
            tel.forget_actuation(idxs)

    _STATS_UNAVAILABLE = {"ok": False, "error": "key statistics are unavailable"}

    def get_stats(self, days=1):
        """Per-key aggregates for the last `days` days, keyed by design code.
        Aggregates only (see telemetry.py): never sequences or timestamps."""
        try:
            tel = getattr(self, "telemetry", None)
            if tel is None:
                return dict(self._STATS_UNAVAILABLE)
            days = _clamp_stats_days(days)
            keys, totals = {}, {"presses": 0, "shallow": 0, "barely": 0, "bottom": 0}
            for idx, agg in tel.aggregate(days).items():
                code = self.km.code_of(idx) if self.km else None
                keys[code or f"idx{idx}"] = agg
                for f in totals:
                    totals[f] += agg[f]
            return {"ok": True, "enabled": tel.enabled,
                    "supported": self._stats_supported(), "board": tel.board,
                    "days": days, "keys": keys, "totals": totals}
        except Exception as e:
            return self._fail(e)

    def clear_stats(self):
        try:
            tel = getattr(self, "telemetry", None)
            if tel is None:
                return dict(self._STATS_UNAVAILABLE)
            return {"ok": True, "deleted": tel.clear()}
        except Exception as e:
            return self._fail(e)

    def set_stats_enabled(self, on):
        try:
            tel = getattr(self, "telemetry", None)
            if tel is None:
                return dict(self._STATS_UNAVAILABLE)
            on = bool(on)
            r = self.save_settings({STATS_SETTING: on})
            if not r.get("ok"):
                return r
            tel.set_enabled(on)
            if on:
                self._start_stats_reader()
            else:
                self._release_reader("telemetry")
                tel.flush()
            return {"ok": True, "enabled": on}
        except Exception as e:
            return self._fail(e)

    # ---- typing analytics + auto-tune (Phase 4; aggregates only) ----
    def get_analytics(self, days=14):
        """Analytics views over the last `days` days (1..90): per design code
        presses / shallow / barely / bottom-out counts and percentages,
        average peak depth, heat 0..1; board totals; and presses per day for
        the last 14 days. Built from telemetry's per-key day aggregates only."""
        try:
            tel = getattr(self, "telemetry", None)
            if tel is None:
                return dict(self._STATS_UNAVAILABLE)
            days = _clamp_stats_days(days)
            km = getattr(self, "km", None)
            code_of = km.code_of if km else (lambda i: None)
            out = analytics.summarize(
                tel.recent_buckets(max(days, analytics.DAILY_DAYS)), code_of, days)
            out.update(ok=True, enabled=tel.enabled,
                       supported=self._stats_supported(), board=tel.board,
                       days=days)
            return out
        except Exception as e:
            return self._fail(e)

    def get_tune_suggestions(self):
        """Actuation auto-tune SUGGESTIONS (never writes anything). Uses only
        presses recorded at each key's current read-back actuation over the
        last analytics.TUNE_WINDOW_DAYS days. Applying one is the UI's normal
        Actuation Apply path (set_trigger_codes + verify_actuation)."""
        try:
            tel = getattr(self, "telemetry", None)
            km = getattr(self, "km", None)
            if tel is None or km is None:
                return dict(self._STATS_UNAVAILABLE)
            out = {"ok": True, "enabled": tel.enabled,
                   "supported": self._stats_supported(),
                   "min_presses": analytics.MIN_PRESSES,
                   "window_days": analytics.TUNE_WINDOW_DAYS,
                   "read_back": False, "suggestions": [], "notes": []}
            if not out["supported"]:
                return out
            act = tel.actuation()
            trig = dict(getattr(self, "_trig_mode", None) or {})
            out["read_back"] = bool(act) and bool(trig)
            days = [d for _, d in tel.recent_buckets(analytics.TUNE_WINDOW_DAYS)]
            out.update(analytics.suggest(analytics.rated_at(days, act), act,
                                         trig, km.index_of_code))
            return out
        except Exception as e:
            return self._fail(e)

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
        if getattr(self, "_restarting", False):
            # set_poll is following the board through its restart and will
            # reopen it itself; a second open from the UI watchdog would race it.
            return {"ok": False, "restarting": True,
                    "error": "the keyboard is restarting"}
        return self._connect()

    def _connect(self, resume=True, verify=False):
        """connect() body. `verify`: prove the fresh handle answers (probe)
        before anything else, and give up on it if not (set_poll uses this
        while the board comes back). `resume`: run _resume_session."""
        try:
            # Driver-specific open + handshake (Win60: heartbeat; MINI60:
            # 0x10 device info + LED-table seed; inert boards: open only).
            info = self.driver.connect()
            # Fresh handle: what the board holds is unknown until the UI's
            # read-back, so the next profile apply writes instead of skipping.
            self._trig_mode = {}
            self._socd_last = None
            if verify and self.driver.probe_link(self._PROBE_TIMEOUT_S) is False:
                try:
                    self.dev.close()
                except Exception:
                    pass
                return {"ok": False, "error": "the keyboard is not answering yet"}
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
            # Any handle death before this connect is now handled: the
            # fresh handle starts a clean slate for status().
            self._dead_seen = getattr(self.dev, "dead_events", 0)
            if resume:
                self._resume_session()
            self._start_stats_reader()
            self._apply_pending_board()
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
            # Keyed by SLUG, not (vid, pid): several registry entries share one
            # VID:PID (the KP-TE153 ships as 2E3C:C365 like the Win60/Win68), so
            # a pair-keyed set marked every sibling "connected" the moment one
            # of them was plugged in. connected_profiles() already resolved the
            # attached device to exactly one profile — trust that answer.
            attached = {p.slug for p in drivers.connected_profiles(reg)}
        except Exception:
            attached = set()
        active_slug = self.board.slug if self.board else None
        out = [
            {"slug": p.slug, "name": p.name, "vidPid": p.vid_pid,
             "formFactor": p.form_factor, "status": p.status,
             "capabilities": p.capabilities, "drivable": p.drivable,
             # `offered` is the registry's own answer to "may the UI advertise
             # this board as selectable?" — a board can be fully drivable and
             # still deliberately not offered (e.g. decoded from a contributor's
             # capture but never run on the physical hardware by anyone). Every
             # UI surface must filter on THIS, not re-derive the rule from
             # `drivable`, or the two drift apart.
             "offered": p.offered,
             "connected": p.slug in attached,
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
            # Disarm calibration and stop both readers (and clear ownership)
            # before closing — same contract as disconnect().
            if self._calibrating:
                try: self.driver.set_calibration(False)
                except Exception: pass
                self._calibrating = False
            self._stop_readers()
            try:
                self.dev.close()
            except Exception:
                pass
            self.board = p
            self._registry = reg
            tel = getattr(self, "telemetry", None)
            if tel is not None:
                tel.set_board(p.slug)
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
            self._ov_attach()
            self._music_attach()
            # per-board caches must not leak across boards
            self._remaps = {}
            self._trigger_state = {}
            self._deadband_state = {}
            self._act_mm = {}
            self._trig_mode = {}
            self._socd_last = None
            self._pending_board = None
            self._fn_layer_raw = None
            self._idx2code = None
            self._light_src = None      # the old board's lighting is not this board's
            self._init_link_state()
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

    # ---- link liveness -------------------------------------------------------
    # After a USB re-enumeration (a poll-rate change restarts the board, a
    # replug, a hub reset) Windows leaves the old HID handle "open": writes are
    # accepted and go nowhere, reads come back empty. status() used to answer
    # dev.is_open(), so the UI's 2.5 s status -> connect() watchdog never fired
    # and the app stayed dead until a manual reconnect (verified on hardware,
    # 0.5.2). status() now PROVES the link: a recent reply is proof; otherwise
    # one cheap heartbeat probe, only when the link is idle.

    #: A reply this recent proves the link (no probe).
    _LINK_QUIET_S = 4.0
    #: Never probe more often than this, whatever the UI's poll rate.
    _PROBE_MIN_INTERVAL_S = 4.0
    #: Per-attempt reply wait for the heartbeat probe.
    _PROBE_TIMEOUT_S = 0.5
    #: How long status() waits for the outer lock before giving up on a
    #: probe. A frame of the effect stream holds it for ~1 ms; a calibration,
    #: macro write or table RMW holds it far longer, and is never interrupted.
    _PROBE_LOCK_WAIT_S = 0.25

    def _init_link_state(self):
        dev = getattr(self, "dev", None)
        self._dead_seen = getattr(dev, "dead_events", 0)
        self._last_probe = 0.0
        self._probe_gate = threading.Lock()
        # Set by _on_link_lost when gamepad capture was running, so the
        # reconnect turns it back on (the UI keeps showing it as on).
        self._resume_gamepad = False

    def _resume_session(self):
        """After a (re)connect, bring back what a lost link tore down. The
        shared live reader comes back for whoever still claims it (analog
        tab / reactive effect / gamepad: _on_link_lost parks it but keeps the
        owners); gamepad capture is re-enabled if it was on. Lighting is the
        UI's job: its effects re-send the current effect when `connected`
        flips back to true. Actuation / RT / SOCD / dead band live in the
        keyboard's flash and need nothing. A manual disconnect() clears the
        owners and the flag, so a normal connect restores nothing. Never
        raises (connect() must still report the open handle)."""
        try:
            self._restore_shared_reader()
        except Exception as e:
            log.warning("live reader not restored after reconnect: %s", e)
        if getattr(self, "_resume_gamepad", False):
            self._resume_gamepad = False
            try:
                r = self.set_gamepad_capture(True)
                if not (r and r.get("ok")):
                    log.warning("gamepad capture not resumed: %s",
                                (r or {}).get("error"))
            except Exception as e:
                log.warning("gamepad capture not resumed: %s", e)

    def status(self):
        dev = getattr(self, "dev", None)
        if dev is None:
            return {"connected": False}
        if getattr(self, "_restarting", False):
            # set_poll owns the link until the board is back (or gives up).
            return {"connected": False, "restarting": True}
        # A handle that died underneath us (a failed write/read dropped it),
        # even if a later driver write reopened it: report the loss once so
        # the UI reconnects and the session state is rebuilt.
        events = getattr(dev, "dead_events", 0)
        if events != getattr(self, "_dead_seen", 0):
            self._on_link_lost("HID I/O failed")
            return {"connected": False}
        if not dev.is_open():
            return {"connected": False}
        if self._probe_link() is False:
            self._on_link_lost("no reply to the heartbeat probe")
            return {"connected": False}
        return {"connected": True}

    def _probe_link(self):
        """True = the board answered recently or now; False = an idle probe
        got no answer (stale handle); None = no verdict (busy, rate-limited,
        or this board has no probe) - the caller then trusts the handle."""
        dev = self.dev
        # Never interleave with calibration (its reader owns the stream and
        # the board is armed) or a board-submission capture borrowing the
        # handle.
        if getattr(self, "_calibrating", False) or getattr(self, "calib_reader", None):
            return None
        cap = getattr(self, "_cap_thread", None)
        if cap is not None and cap.is_alive():
            return None
        rx_age = getattr(dev, "rx_age", None)
        if rx_age is None:
            return None                       # no liveness bookkeeping
        if rx_age() < self._LINK_QUIET_S:
            return True
        now = time.monotonic()
        if now - getattr(self, "_last_probe", 0.0) < self._PROBE_MIN_INTERVAL_S:
            return None
        gate = getattr(self, "_probe_gate", None)
        if gate is None:
            gate = self._probe_gate = threading.Lock()
        if not gate.acquire(blocking=False):
            return None                       # another status() is probing
        try:
            # Only when idle: a multi-packet transaction (calibration arm,
            # macro write, table RMW) holds the outer lock - skip, don't wait.
            if not self._lock.acquire(timeout=self._PROBE_LOCK_WAIT_S):
                return None
            try:
                self._last_probe = time.monotonic()
                if not dev.is_open():
                    return None
                ok = self._run_probe()
            finally:
                self._lock.release()
        finally:
            gate.release()
        if ok:
            dev.note_rx()
        return ok

    def _run_probe(self):
        """One probe; the caller holds the outer lock. With the shared live
        reader running, the reader drains every report (the heartbeat reply
        included) and records the rx itself, so only the request is written
        and the reader is NOT parked: a restart would forget held keys (the
        firmware never re-reports a key held still). Otherwise the driver
        sends the heartbeat and reads the reply itself."""
        dev, drv = self.dev, self.driver
        r = getattr(self, "reader", None)
        alive = getattr(r, "alive", None)
        if r is not None and alive is not None and alive():
            t0 = dev.last_rx()
            attempts = getattr(drv, "PROBE_ATTEMPTS", 1)
            for _ in range(attempts):
                sent = drv.ping_link()
                if sent is None:
                    return None
                if not sent:
                    return False
                deadline = time.monotonic() + self._PROBE_TIMEOUT_S
                while time.monotonic() < deadline:
                    if dev.last_rx() != t0:
                        return True
                    time.sleep(0.01)
            return False
        # No live reader: a wedged/exited one is parked and re-created by
        # _reader_paused, so it cannot eat the reply either.
        with self._reader_paused():
            return drv.probe_link(self._PROBE_TIMEOUT_S)

    def _park_readers(self, attrs=("reader", "calib_reader")):
        """Stop the readers named in `attrs` but keep their owners registered
        (unlike _stop_readers) so a reconnect can bring the stream back."""
        stopping = []
        with self._lock:
            for attr in attrs:
                r = getattr(self, attr, None)
                if r is not None:
                    setattr(self, attr, None)
                    stopping.append(r)
        for r in stopping:            # joins outside the lock (see _release_reader)
            try:
                r.stop()
            except Exception:
                pass

    def _on_link_lost(self, why):
        """The board stopped answering: tear the session down so nothing keeps
        streaming into a dead handle, and close it so status() says
        disconnected and the UI's watchdog reconnects. Runs OUTSIDE the outer
        lock (status() released it): the teardown paths take it themselves,
        and the readers' joins must not happen under it."""
        log.warning("Keyboard link lost (%s); closing the handle", why)
        try:
            self.stop_capture()
        except Exception:
            pass
        try:
            self.stop_multicolor()
        except Exception:
            pass
        try:
            th = getattr(self, "_pad_thread", None)
            if getattr(self, "pad", None) is not None or th is not None:
                if th is not None and th.is_alive():
                    self._resume_gamepad = True
                self.set_gamepad_capture(False)
        except Exception:
            pass
        if getattr(self, "_calibrating", False):
            # Nothing to disarm on a gone board; try anyway in case the
            # handle is merely stale.
            try:
                self.driver.set_calibration(False)
            except Exception:
                pass
            self._calibrating = False
        self._park_readers()
        try:
            self.dev.close()
        except Exception:
            pass
        self._dead_seen = getattr(self.dev, "dead_events", 0)

    # ---- shared-reader lifecycle -------------------------------------------
    def _acquire_reader(self, who, make):
        """Register `who` as needing the shared live reader; start it (via
        `make`) if it isn't already running. Returns the reader, or None when
        there is no keymap to read.

        Reader lifecycle runs under the outer RLock: pywebview dispatches API
        calls on worker threads, so an analog-tab open racing an effect start
        could otherwise both see `reader is None` and start TWO readers on one
        handle (one of them leaked). Lock order stays outer -> inner: reader
        threads only ever take the device's inner lock, so stop()/join() under
        the outer lock cannot deadlock."""
        with self._lock:
            self._reader_users.add(who)
            if getattr(self, "_calibrating", False):
                # CalibrationReader is the sole drain: a LiveReader started now
                # (e.g. the UI re-sending a press-reactive effect as calibration
                # starts) would discard every calibration report. The owner stays
                # registered; calibrate(False) restores the stream.
                return None
            if self.reader is None and self.km:
                self.reader = make()
                self.reader.start()
            return self.reader

    def _release_reader(self, who):
        """Drop `who`; stop the shared reader only when nobody else needs it —
        so turning gamepad capture off can't strand the analog tab's stream."""
        # Detach under the lock, but JOIN outside it: the calibration reader's
        # on_change renders through driver.stream_frame, which takes this same
        # outer lock — joining it while holding the lock would stall the join.
        r = None
        with self._lock:
            self._reader_users.discard(who)
            if not self._reader_users and self.reader is not None:
                r, self.reader = self.reader, None
        if r is not None:
            try:
                r.stop()
            except Exception:
                pass

    def _restore_shared_reader(self):
        """Re-create the shared live reader if it is gone but still claimed
        (open_capture pauses it while a board-submission capture borrows the
        handle). The reactive-effect depth source (_ensure_reactive) resolves
        self.reader on every call, so it picks the new instance up by itself.
        Never raises."""
        try:
            if getattr(self, "_calibrating", False):
                return      # CalibrationReader owns the stream until it ends
            if not self._reader_users or self.reader is not None or not self.km:
                return
            if not self.dev.is_open():
                return
            self.reader = self._make_live_reader()
            self.reader.start()
        except Exception as e:
            log.warning("could not restore live reader after capture: %s", e)

    @contextlib.contextmanager
    def _reader_paused(self):
        """Park the shared live reader while the driver READS from the handle
        (a read-modify-write of a board table, the actuation read-back).

        Two consumers draining one HID handle steal each other's reports:
        the LiveReader drains up to 256 reports per pass and drops every
        frame that is not a travel-test sample, so with the Actuation tab's
        Travel Test on, a press-reactive effect running or gamepad capture
        active, a keymap / switch / dead-band read-back loses pages and the
        RMW aborts (remap fails), or the mode-0 trigger read-back misses and
        falls back to the factory RT pair. The single-active-reader rule in
        docs/context/lifecycle-locking-design.md (fix B.2) is enforced here:
        the reader stops for the span, its owners stay registered, and it is
        re-created afterwards (_restore_shared_reader). Holds the outer lock
        for the span so no other bridge call can start a reader in between;
        the LiveReader only ever takes the inner lock, so the join is safe.
        No reader running -> no-op."""
        with self._lock:
            if getattr(self, "_calibrating", False):
                # A read-back now would eat the calibration reports (and the
                # CalibrationReader would eat its replies).
                raise RuntimeError("Calibration in progress - finish it first")
            paused = None
            r = getattr(self, "reader", None)
            if r is not None:
                self.reader = None
                try:
                    r.stop()
                except Exception:
                    pass
                paused = r
            try:
                yield
            finally:
                if paused is not None:
                    self._restore_shared_reader()

    def _stop_readers(self):
        """Stop and clear BOTH readers and all ownership. Every disconnect /
        board-switch path runs this so no reader thread is left spinning on a
        handle that is about to close."""
        stopping = []
        with self._lock:
            self._reader_users.clear()
            for attr in ("reader", "calib_reader"):
                r = getattr(self, attr, None)
                if r is not None:
                    setattr(self, attr, None)
                    stopping.append(r)
        for r in stopping:            # joins happen outside the lock (see above)
            try:
                r.stop()
            except Exception:
                pass

    def disconnect(self):
        with _CARRIER_LOCK:
            if getattr(self, "_carrier_on", False):
                # The engine is only carrying overlays: put the firmware
                # lighting back (while the handle is still open) so the board
                # is not left frozen on the last overlay frame.
                try:
                    self._carrier_stop()
                except Exception as e:
                    log.warning("carrier release on disconnect failed: %s", e)
            self.stop_multicolor()
        self.set_gamepad_capture(False)
        self._resume_gamepad = False      # the user's choice: restore nothing
        # Disarm calibration BEFORE closing the handle — otherwise the board is
        # left in calibration mode (its stored calibration already wiped) with
        # no way to recover on reconnect.
        if self._calibrating:
            try:
                self.driver.set_calibration(False)
            except Exception:
                pass
            self._calibrating = False
        tel = getattr(self, "telemetry", None)
        if tel is not None:
            try:
                tel.abort_open()
                tel.flush()
            except Exception as e:
                log.warning("key statistics flush failed: %s", e)
        self._stop_readers()
        self.dev.close()
        return {"ok": True}

    # ---- lighting (fg/bg/mode/brightness/speed/dir/power, per-board dispatch) ----
    def set_light(self, mode, r, g, b, brightness=4, speed=4,
                  bg_r=0, bg_g=0, bg_b=0, direction=0, power_on=True, full_color=0):
        try:
            p = {"mode": int(mode), "fg": (int(r), int(g), int(b)),
                 "bg": (int(bg_r), int(bg_g), int(bg_b)),
                 "brightness": int(brightness), "speed": int(speed),
                 "direction": int(direction), "full_color": int(full_color),
                 "power_on": bool(power_on)}
            self._light_src = ("light", p)
            if self._overlay_active():
                # Status overlays are on: the host engine carries this lighting
                # (the firmware gets it back when the overlays go off).
                self._carrier_start()
                return {"ok": True}
            self.driver.set_lighting(
                p["mode"], p["fg"], bg=p["bg"], brightness=p["brightness"],
                speed=p["speed"], direction=p["direction"],
                full_color=p["full_color"], power_on=p["power_on"])
            return {"ok": True}
        except Exception as e:
            return self._fail(e)

    # back-compat: simple static color
    def set_color(self, r, g, b, brightness=4, mode=0, speed=4):
        return self.set_light(mode, r, g, b, brightness, speed)

    # ---- actuation / trigger ----
    #: Trigger MODE bytes the decoded protocols accept (Win60 cmd 33 byte
    #: sub[0], CONFIRMED-BY-CAPTURE for all three; the MINI driver maps 12/13
    #: onto its RT flag). Anything else would program an undefined mode.
    _TRIGGER_MODES = (0, 12, 13)

    def _clamp_mm(self, range_key, mm):
        """Clamp a millimetre value to the active board's declared
        `actuation.<range_key>` ([min, max], registry) when it declares one;
        pass-through otherwise. The UI sliders already stay in range, but
        values also arrive from settings.json profiles and any bridge caller,
        and the firmware ranges (WIN 60 HE: 0.08..3.40 mm travel) are what
        readMaxTriggerTravel reports — never send it something outside."""
        mm = float(mm)
        rng = (getattr(self.board, "actuation", None) or {}).get(range_key)
        if rng:
            lo, hi = float(rng[0]), float(rng[1])
            mm = min(hi, max(lo, mm))
        return mm

    def set_trigger_all(self, travel_mm, rt_press_mm=0.0, rt_release_mm=0.0,
                        key_count=64, mode=0):
        """Whole-board trigger write. With a keymap loaded the board's REAL
        indices are used (Win60 indices run to 131 with a 22-column stride,
        so `range(64)` covered barely half the keys); `key_count` only
        matters for the legacy no-keymap path. Fixed mode (0) passes no RT
        intervals so the driver preserves each key's stored pair (the
        vendor never sends 0/0 — see Win60Driver.set_actuation)."""
        try:
            mode = int(mode)
            if mode not in self._TRIGGER_MODES:
                return {"ok": False, "error": f"invalid trigger mode {mode}"}
            km = getattr(self, "km", None)
            idxs = list(km.indices()) if km else list(range(int(key_count)))
            self._stats_forget_actuation(idxs)
            if mode == 0:
                # Mode 0 reads each key's stored RT pair back first.
                with self._reader_paused():
                    self.driver.set_actuation(idxs, 0, float(travel_mm), None, None)
            else:
                self.driver.set_actuation(idxs, mode,
                                          float(travel_mm), float(rt_press_mm),
                                          float(rt_release_mm))
            # Per-key edits resend whole groups from _trigger_state: record
            # this write there too, or the next single-key flush would put
            # a stale group (e.g. keys set before a game switch) back.
            cfg = ((0, _mm_to_raw(travel_mm), None, None) if mode == 0 else
                   (mode, _mm_to_raw(travel_mm), _mm_to_raw(rt_press_mm),
                    _mm_to_raw(rt_release_mm)))
            for i in idxs:
                self._trigger_state[i] = cfg
            self._note_actuation({i: float(travel_mm) for i in idxs})
            self._note_trigger_modes(idxs, mode, rt_press_mm, rt_release_mm)
            return {"ok": True, "keys": len(idxs)}
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
                with self._lock:
                    # The analog tab needs a reader over THESE indices, so
                    # replace any existing one; register as an owner so
                    # gamepad/reactive turning off can't stop it out from
                    # under the tab. If another owner (reactive effect,
                    # gamepad) already shares the reader it needs the WHOLE
                    # board, so the replacement must cover every key — a
                    # subset would silently blind the running effect.
                    others = self._reader_users - {"analog"}
                    self._reader_users.add("analog")
                    if self._calibrating:
                        # Sole-drain rule (see _acquire_reader); the
                        # calibrate-off restore brings the stream back.
                        return {"ok": True, "keys": 0, "deferred": "calibrating"}
                    if others and len(idxs) < len(self.km.indices()):
                        idxs = self.km.indices()
                    old, self.reader = self.reader, None
                    if old:
                        old.stop()       # LiveReader only takes the inner lock
                    self.reader = self._make_live_reader(idxs)
                    self.reader.start()
            else:
                self.driver.open_trigger_test(list(range(64)))
            return {"ok": True, "keys": len(idxs) if self.km else 64}
        except Exception as e:
            return self._fail(e)

    def close_analog(self):
        try:
            if "analog" in self._reader_users or self.reader is not None:
                # Drop the analog claim; the reader stops only if gamepad /
                # reactive don't still need it.
                self._release_reader("analog")
            else:
                self.driver.close_trigger_test()
            return {"ok": True}
        except Exception as e:
            return self._fail(e)

    # ---- polling ----
    #: Poll-rate codes the decoded protocol accepts: 1/2/4/8 = 1/2/4/8 kHz
    #: (Win60 cmd 33 sub 9, CONFIRMED-BY-CAPTURE; the vendor's own read
    #: handler rejects anything else). The write RESTARTS the keyboard, so an
    #: undefined code is refused here rather than sent.
    _POLL_CODES = (1, 2, 4, 8)

    #: The poll-rate write RESTARTS the keyboard. Measured on a WIN 60 HE:
    #: it drops off USB ~1.05 s after the write and re-enumerates ~0.35 s
    #: later; the old handle then returns -1 on write and raises on read.
    #: set_poll follows it through: wait (bounded) for the drop, then for
    #: the board to come back and answer, and reopen it.
    _POLL_RESTART_TIMEOUT_S = 8.0
    _POLL_DROP_WAIT_S = 3.0
    _POLL_STEP_S = 0.1

    def set_poll(self, rate):
        try:
            code = int(rate)
        except (TypeError, ValueError):
            code = None
        if code not in self._POLL_CODES:
            return {"ok": False,
                    "error": f"invalid poll-rate code {rate} "
                             f"(expected one of {list(self._POLL_CODES)})"}
        if getattr(self, "_restarting", False):
            return {"ok": False, "restarting": True,
                    "error": "the keyboard is already restarting"}
        self._restarting = True
        try:
            try:
                self.driver.set_poll_rate(code)
            except Exception as e:
                return self._fail(e)
            back = self._follow_restart()
            # `restarted` tells the UI the link was cycled: it treats
            # `reconnected` like a fresh connect (re-sends lighting), and a
            # False like a lost link (its watchdog reconnects later).
            return {"ok": True, "restarted": True, "reconnected": back}
        finally:
            self._restarting = False

    def _follow_restart(self):
        """After a write that restarts the keyboard: tear the session down
        now (the handle is about to go stale), wait for the board to drop off
        USB and come back, reopen + verify it, then resume the session. True
        if it is back within _POLL_RESTART_TIMEOUT_S."""
        dev = getattr(self, "dev", None)
        if dev is None:
            return False
        self._on_link_lost("the poll-rate change restarts the keyboard")
        present = getattr(dev, "present", None)
        t0 = time.monotonic()
        deadline = t0 + self._POLL_RESTART_TIMEOUT_S
        if present is not None:
            # Reopening before the drop would grab the old instance, which
            # dies a moment later.
            drop_by = t0 + self._POLL_DROP_WAIT_S
            while time.monotonic() < drop_by and present():
                time.sleep(self._POLL_STEP_S)
        while time.monotonic() < deadline:
            if present is None or present():
                r = self._connect(resume=False, verify=True)
                if r.get("ok"):
                    self._resume_session()
                    log.info("keyboard back after the poll-rate restart (%.1f s)",
                             time.monotonic() - t0)
                    return True
            time.sleep(self._POLL_STEP_S)
        log.warning("keyboard not back %.0f s after the poll-rate restart",
                    self._POLL_RESTART_TIMEOUT_S)
        return False

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
            log.info("trigger pkt: mode=%d travel=%.2fmm i1=%s i2=%s keys=%d %s",
                     mode, travel * _UNIT_MM,
                     "keep" if i1 is None else i1, "keep" if i2 is None else i2,
                     len(idxs), sorted(idxs)[:8])
            # Fixed mode carries no intervals of its own: None tells the
            # driver to keep each key's STORED RT pair (read-modify-write),
            # which is what the vendor driver sends in mode 0.
            self.driver.set_actuation(list(idxs), int(mode),
                                      travel * _UNIT_MM,
                                      None if i1 is None else i1 * _UNIT_MM,
                                      None if i2 is None else i2 * _UNIT_MM)
            threading.Event().wait(0.005)

    def set_trigger_codes(self, codes, travel_mm, rt_press_mm=0.0, rt_release_mm=0.0, mode=0):
        if not self.km:
            return {"ok": False, "error": "no keymap"}
        idxs = self.km.indices_for_codes(codes) if codes else []
        if not idxs:
            return {"ok": False, "error": "no keys"}
        mode = int(mode)
        if mode not in self._TRIGGER_MODES:
            return {"ok": False, "error": f"invalid trigger mode {mode}"}
        travel_mm = self._clamp_mm("travelRange", travel_mm)
        if mode != 0:
            # RT sensitivities are only meaningful (and only range-checked)
            # in a rapid-trigger mode.
            rt_press_mm = self._clamp_mm("rtRange", rt_press_mm)
            rt_release_mm = self._clamp_mm("rtRange", rt_release_mm)
            cfg = (mode,
                   _mm_to_raw(travel_mm),
                   _mm_to_raw(rt_press_mm),
                   _mm_to_raw(rt_release_mm))
        else:
            # Fixed mode: the UI sends 0/0, but the vendor driver never
            # writes zero intervals — it re-sends each key's stored pair
            # (CONFIRMED-BY-CAPTURE frame 1842). None = "keep stored"; the
            # driver reads the pair back and preserves it per key.
            cfg = (0, _mm_to_raw(travel_mm), None, None)
        for i in idxs:
            self._trigger_state[i] = cfg
        self._stats_forget_actuation(idxs)
        try:
            if mode == 0:
                # The driver reads each key's stored RT pair back before the
                # mode-0 write; the live reader must not eat those replies.
                with self._reader_paused():
                    self._flush_triggers(edited_idxs=idxs)
            else:
                self._flush_triggers(edited_idxs=idxs)
            self._note_actuation({i: travel_mm for i in idxs})
            self._note_trigger_modes(idxs, mode, rt_press_mm, rt_release_mm)
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
            # Driver takes the outer lock itself for the whole read sweep;
            # the live reader is parked so it can't consume the replies.
            # Drivers that can (Win60) also return each key's trigger mode
            # and stored RT pair from the SAME sweep, so the UI can draw the
            # board from what the firmware holds, not from what it asked for.
            detail_fn = getattr(self.driver, "read_trigger_detail", None)
            detail = None
            with self._reader_paused():
                if detail_fn is not None:
                    try:
                        detail = detail_fn(self.km)
                    except UnsupportedFeature:
                        detail = None
                if detail is not None:
                    vals_by_name = {n: d["travel_mm"] for n, d in detail.items()}
                else:
                    vals_by_name = self.driver.read_actuation(self.km)
            # Build {design_code: mm} for every key we have a mapping for.
            all_by_code, trig_by_code, act_by_idx, trig_by_idx = {}, {}, {}, {}
            for design_code, idx in self.km.index_of_code.items():
                name = self.km.by_index[idx]["name"]
                mm = vals_by_name.get(name)
                if mm is not None:
                    all_by_code[design_code] = mm
                    act_by_idx[idx] = mm
                if detail is not None and name in detail:
                    trig_by_code[design_code] = dict(detail[name])
                    trig_by_idx[idx] = detail[name]
            self._stats_actuation(act_by_idx)
            self._note_actuation(act_by_idx)
            self._note_read_back_modes(trig_by_idx)
            wanted = (lambda c: c in codes) if codes else (lambda c: True)
            out = {c: v for c, v in all_by_code.items() if wanted(c)}
            res = {"ok": True, "actuation_mm": out}
            if detail is not None:
                res["trigger"] = {c: v for c, v in trig_by_code.items() if wanted(c)}
            return res
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
            self._light_src = ("custom", dict(colors_by_index), int(brightness), int(speed))
            if self._overlay_active():
                self._carrier_start()
                return {"ok": True, "keys": len(colors_by_index)}
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
        # Registry deadzoneRange (0..0.5 mm on every decoded board); the wire
        # field is one byte per value, so an unclamped 2.56 mm would wrap.
        top_mm = self._clamp_mm("deadzoneRange", top_mm)
        bottom_mm = self._clamp_mm("deadzoneRange", bottom_mm)
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
            with self._reader_paused():           # RMW: reads the table first
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
            with self._reader_paused():           # RMW: reads the table first
                self.driver.set_switch(table)
            return {"ok": True, "keys": len(idxs), "code": code}
        except Exception as e:
            return self._fail(e)

    # ---- key remap (per-board keymap table) ----
    def _flush_remaps(self, restore_indices=()):
        # Read-modify-write over the board's current base layer: only our
        # remap overrides and the keys being reset (`restore_indices`)
        # change; bindings made outside Aether (vendor macros, advanced
        # keys) survive. Then the Fn layer is replayed (the driver aborts
        # before writing anything if no Fn table can be had).
        defaults = {i: self.km.by_index[i]["hid"] for i in self.km.by_index}
        # The RMW reads both keymap layers back; park the live reader so a
        # running press-reactive effect / Travel Test can't eat the pages
        # (a lost page = "keymap read failed" and the remap is refused).
        with self._reader_paused():
            self.driver.write_keymap(defaults, dict(self._remaps),
                                     self.km.layer_indices, self._fn_layer_raw,
                                     restore_indices=list(restore_indices))

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
                restore = set(self._remaps)
                self._remaps = {}
            else:
                restore = set(self.km.indices_for_codes(codes))
                for i in restore:
                    self._remaps.pop(i, None)
            # The reset keys must be named explicitly: with a read-modify-
            # write the old override would otherwise survive on the board.
            self._flush_remaps(restore_indices=restore)
            return {"ok": True}
        except Exception as e:
            return self._fail(e)

    # ---- SOCD / PRCS ----
    @staticmethod
    def _socd_key(pairs):
        """Comparable form of a set_socd pair list (order kept: it is the
        slot order on the board)."""
        return tuple((int(p["model"]), str(p["key1"]), str(p["key2"])) for p in pairs)


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
            self._socd_last = self._socd_key(pairs)
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
                # CalibrationReader must be the sole drain, so park the shared
                # stats/analog reader (owners kept) until calibration ends.
                # Flag first: from here no other path may start a LiveReader
                # or do a read-back (_acquire_reader / _reader_paused check it).
                with self._lock:
                    self._calibrating = True   # disconnect() must disarm on abort
                self._park_readers(("reader",))
                try:
                    self.driver.set_calibration(True, bool(any_key))
                except Exception:
                    self._calibrating = False
                    self._restore_shared_reader()
                    raise
                self.calib_reader = self.driver.make_calibration_reader(self.km)
                self.calib_reader.start()
            else:
                if self.calib_reader:
                    self.calib_reader.stop()
                    self.calib_reader = None
                self.driver.set_calibration(False, bool(any_key))
                self._calibrating = False
                self._restore_shared_reader()
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
            # Release our claim on the shared reader; it stops only if the
            # analog tab / reactive effects don't still need it.
            self._release_reader("gamepad")
            return {"ok": True}
        try:
            # Open the virtual pad FIRST: it is the thing most likely to fail
            # (no /dev/uinput access, no ViGEmBus), and a failure must not
            # leave the analog stream armed on our behalf.
            if self.pad is None:
                self.pad = gamepad.VirtualGamepad(self._pad_map).open()
            self._acquire_reader("gamepad", self._make_live_reader)
            self._pad_stop.clear()
            if not self._pad_thread or not self._pad_thread.is_alive():
                self._pad_thread = threading.Thread(target=self._gamepad_loop,
                                                    name="aether-gamepad", daemon=True)
                self._pad_thread.start()
            return {"ok": True}
        except Exception as e:
            if self.pad:
                self.pad.close()
                self.pad = None
            # Drop the reader claim too, or a failed enable would keep the
            # travel-test stream running with nobody consuming it.
            self._release_reader("gamepad")
            # Surface a hint for the React UI when the failure is the missing
            # kernel driver, so it can offer the one-click installer. Only when
            # the vgamepad backend is actually loaded — with the package itself
            # missing, running the driver installer would not help.
            msg = str(e)
            need_driver = (sys.platform.startswith("win")
                           and gamepad.EVDEV_AVAILABLE
                           and "ViGEmBus" in msg)
            return dict(self._fail(e), needs_vigembus=need_driver)

    def set_gamepad_map(self, mappings):
        """Set the key→control mappings for the virtual gamepad. Each entry:
        {key, axis, direction, threshold_mm}. Applies live if capture is running.
        A re-open is needed when the set of axes/buttons changes, so we rebuild."""
        try:
            kms = [gamepad.KeyMap(
                       str(m.get("key", "")), str(m.get("axis", "LX")),
                       int(m.get("direction", 1)), float(m.get("threshold_mm", 1.5)))
                   for m in (mappings or []) if m.get("key") and m.get("axis")]
            bad = sorted({k.axis for k in kms if k.axis not in gamepad.KNOWN_AXES})
            if bad:
                return {"ok": False, "error": f"unknown gamepad control(s): {', '.join(bad)}"}
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
        # --autostart marks the sign-in launch; whether it shows a window is
        # the Settings-tab "Start minimized" toggle (settings.json), read by
        # main() — not baked into this command, so flipping the toggle needs
        # no registry rewrite.
        flag = tray.AUTOSTART_FLAG
        if getattr(sys, "frozen", False):
            return f'"{sys.executable}" {flag}'
        py = sys.executable.replace("python.exe", "pythonw.exe")
        return f'"{py}" "{os.path.join(HERE, "app_web.py")}" {flag}'

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
        return os.path.join(user_data_dir(), "settings.json")

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
            with _SETTINGS_LOCK:
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

    # ---- tray mini mode ----
    def get_tray_prefs(self):
        """Settings-tab state: whether a tray backend exists on this platform
        (the toggle hides otherwise) and the persisted "Start minimized" flag."""
        return {"ok": True, "supported": tray.backend_supported(),
                "startMinimized": tray.start_minimized_pref(self._settings_path())}

    def set_start_minimized(self, on):
        """Persist "Start minimized": every launch (double-click, Start on
        launch) then begins hidden in the tray with the effects running."""
        try:
            val = tray.set_start_minimized_pref(self._settings_path(), bool(on))
            return {"ok": True, "startMinimized": val}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def tray_sync(self, state):
        """The React app's mirror of what the tray panel shows: current
        pattern/speed, connection, board name and this board's effect list.
        Pushed by app.jsx on every change; tray.TrayApi.get_state reads it, so
        the panel never has to evaluate JS in the (hidden) main window."""
        if not isinstance(state, dict):
            return {"ok": False, "error": "state must be an object"}
        cur = dict(getattr(self, "_tray_state", None) or {})
        cur.update({
            "pattern": state.get("pattern"),
            "speed": state.get("speed", cur.get("speed", 60)),
            "connected": bool(state.get("connected")),
            "board": state.get("board"),
            "effects": [
                {"id": str(e.get("id")), "label": str(e.get("label") or e.get("id")),
                 "icon": str(e.get("icon") or "")}
                for e in (state.get("effects") or []) if isinstance(e, dict) and e.get("id")
            ],
        })
        self._tray_state = cur
        return {"ok": True}

    # ---- games: detection + per-game profiles (games.py) ----
    #
    # Python decides WHICH profile should be active (debounced); app.jsx polls
    # games_status(), switches the profile like the profile menu does (its
    # lighting effects then follow) and hands the profile's actuation / RT /
    # SOCD to apply_profile_to_board. games_sync reports the active profile
    # back, so a manual switch during a game cancels the revert.
    _GAMES_OFF = {"ok": False, "error": "game detection is unavailable"}

    def games_status(self):
        try:
            g = getattr(self, "_games", None)
            if g is None:
                return {"ok": True, "available": False, "autoSwitch": False,
                        "detected": [], "foreground": None, "active": None,
                        "games": [], "switch": None, "detectable": None}
            return g.status()
        except Exception as e:
            return self._fail(e)

    def list_running_games(self):
        """Running user programs for the "add a game" picker. Built on demand,
        never stored or logged."""
        try:
            g = getattr(self, "_games", None)
            if g is None:
                return dict(self._GAMES_OFF)
            return {"ok": True, "programs": g.running()}
        except Exception as e:
            return self._fail(e)

    def set_game_profile(self, game_id, profile_id=None):
        """Map a game to a profile id, or unmap it (None): unmapping a
        program you added removes it."""
        try:
            g = getattr(self, "_games", None)
            if g is None:
                return dict(self._GAMES_OFF)
            return g.set_profile(game_id, profile_id)
        except Exception as e:
            return self._fail(e)

    def add_custom_game(self, exe_path, name=None):
        try:
            g = getattr(self, "_games", None)
            if g is None:
                return dict(self._GAMES_OFF)
            return g.add_custom(exe_path, name)
        except Exception as e:
            return self._fail(e)

    def refresh_detectable(self):
        """Download Discord's game list now (HTTPS, 5 MB cap). Nothing is
        uploaded."""
        try:
            g = getattr(self, "_games", None)
            if g is None:
                return dict(self._GAMES_OFF)
            return g.refresh_detectable()
        except Exception as e:
            return self._fail(e)

    def set_games_auto_switch(self, on):
        try:
            g = getattr(self, "_games", None)
            if g is None:
                return dict(self._GAMES_OFF)
            return g.set_auto(bool(on))
        except Exception as e:
            return self._fail(e)

    def games_sync(self, state):
        """app.jsx -> Python: {activeProfile, profiles: [{id, name}], handledSeq}."""
        self._ov_follow(state)      # overlays are per profile; never raises
        try:
            g = getattr(self, "_games", None)
            if g is None:
                return {"ok": True}
            return g.sync(state)
        except Exception as e:
            return self._fail(e)


    def _board_spec(self, spec):
        """Validate apply_profile_to_board's argument. ValueError if bad."""
        if not isinstance(spec, dict):
            raise ValueError("profile spec must be an object")
        out = {"actuation": None, "mode": 0, "rtPress": None, "rtRelease": None,
               "socd": None}
        a = spec.get("actuation")
        if a is not None:
            a = float(a)
            if not (a == a) or not 0.0 < a <= 10.0:
                raise ValueError("invalid actuation")
            out["actuation"] = round(self._clamp_mm("travelRange", a), 2)
            if spec.get("rtEnabled"):
                out["mode"] = 13
                out["rtPress"] = round(self._clamp_mm("rtRange", float(spec.get("rtPress", 0.05))), 2)
                out["rtRelease"] = round(self._clamp_mm("rtRange", float(spec.get("rtRelease", 0.05))), 2)
        pairs = spec.get("socd")
        if pairs is not None:
            if not isinstance(pairs, list) or len(pairs) > 16:
                raise ValueError("invalid SOCD list")
            norm = []
            for p in pairs:
                if not isinstance(p, dict):
                    raise ValueError("invalid SOCD pair")
                k1, k2, model = p.get("key1"), p.get("key2"), int(p.get("model", 1))
                if not (isinstance(k1, str) and isinstance(k2, str) and 0 < len(k1) <= 32
                        and 0 < len(k2) <= 32 and 0 <= model <= 255):
                    raise ValueError("invalid SOCD pair")
                norm.append({"model": model, "key1": k1, "key2": k2})
            out["socd"] = norm
        return out

    def _board_has_actuation(self, spec):
        """True only when the last read-back/write says EVERY key already has
        this travel and trigger mode (and RT pair in RT mode)."""
        km = getattr(self, "km", None)
        if not km:
            return False
        # EVERY key the keymap has, not just the design-coded ones: boards
        # with more keys than DESIGN_CODES must not be skipped on a partial
        # check. A missing cache entry below counts as a mismatch.
        idxs = set(km.indices())
        act = getattr(self, "_act_mm", None) or {}
        trig = getattr(self, "_trig_mode", None) or {}
        if not idxs:
            return False
        for i in idxs:
            mm, t = act.get(i), trig.get(i)
            if mm is None or t is None or t[0] != spec["mode"]:
                return False
            if abs(mm - spec["actuation"]) > 0.005:
                return False
            if spec["mode"] != 0 and (t[1] is None or t[2] is None
                                      or abs(t[1] - spec["rtPress"]) > 0.005
                                      or abs(t[2] - spec["rtRelease"]) > 0.005):
                return False
        return True

    def _apply_board_spec(self, spec):
        """Write a validated spec through the normal paths, skipping what the
        board already holds (flash wear)."""
        out = {"ok": True, "deferred": False, "actuation": "skipped", "socd": "skipped"}
        if spec["actuation"] is not None:
            if self._board_has_actuation(spec):
                out["actuation"] = "unchanged"
            else:
                r = self.set_trigger_all(spec["actuation"], spec["rtPress"] or 0.0,
                                         spec["rtRelease"] or 0.0, mode=spec["mode"])
                if not r.get("ok"):
                    return {**r, "step": "actuation"}
                out["actuation"] = "written"
        if spec["socd"] is not None:
            if self._socd_key(spec["socd"]) == getattr(self, "_socd_last", None):
                out["socd"] = "unchanged"
            else:
                r = self.set_socd(spec["socd"])
                if not r.get("ok"):
                    return {**r, "step": "socd", "actuation": out["actuation"]}
                out["socd"] = "written"
        return out

    def apply_profile_to_board(self, spec):
        """A game switch's board half: {actuation, rtEnabled, rtPress,
        rtRelease, socd: [{model, key1, key2}]} from the profile app.jsx just
        switched to (null fields are left alone). Actuation/RT go to ALL keys
        via set_trigger_all, SOCD via set_socd; anything the board already
        holds is skipped. While disconnected the spec is kept and applied on
        the next connect (the newest one wins)."""
        try:
            norm = self._board_spec(spec)
            dev = getattr(self, "dev", None)
            if dev is None or not dev.is_open():
                self._pending_board = norm
                return {"ok": True, "deferred": True}
            self._pending_board = None
            return self._apply_board_spec(norm)
        except Exception as e:
            return self._fail(e)

    def _apply_pending_board(self):
        """connect(): apply a game profile that arrived while offline. Never
        raises (connect must still report the open handle)."""
        spec = getattr(self, "_pending_board", None)
        if spec is None:
            return
        self._pending_board = None
        try:
            r = self._apply_board_spec(spec)
            if not r.get("ok"):
                log.warning("game profile not applied after connect: %s", r.get("error"))
        except Exception as e:
            log.warning("game profile not applied after connect: %s", e)

    # ---- advanced keys + per-key remap (MINI 60 HE PRO family) ----
    #
    # These are the JS-facing bridge for the driver's key-table operations. The
    # driver already does strict read-modify-write and refuses boards that lack
    # the capability, so this layer only translates arguments and shapes errors
    # the way the rest of the Api does.
    #
    # Key INDEX, not HID usage: a record's position in the 512-byte key table is
    # the physical matrix slot, and an unbound record reads back all-zero — so
    # there is no way to search the table for "the key that currently sends
    # 0x04". The UI passes design codes; we resolve them through the active
    # board's keymap here, and refuse loudly if that resolution fails rather
    # than writing to a guessed slot.
    def _key_indices(self, codes):
        """Design codes -> firmware key indices via the active board's keymap."""
        if not self.km:
            raise ValueError("no keymap loaded for the active board")
        idxs = self.km.indices_for_codes(codes if isinstance(codes, (list, tuple)) else [codes])
        if not idxs or len(idxs) != len(codes if isinstance(codes, (list, tuple)) else [codes]):
            raise ValueError(f"could not resolve every key: {codes!r}")
        return idxs

    def _adv(self, fn, *args, **kwargs):
        """Run a driver op, mapping failures to the Api's usual result shape."""
        drv = getattr(self, "driver", None)
        if drv is None:
            return {"ok": False, "error": "not connected"}
        try:
            result = fn(drv, *args, **kwargs)
            return {"ok": True, "result": result}
        except UnsupportedFeature as e:
            return {"ok": False, "error": str(e), "unsupported": True,
                    "feature": getattr(e, "feature", None)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def read_key_records(self):
        """Every non-empty key-table record, decoded (remaps + advanced keys)."""
        return self._adv(lambda d: d.read_key_records())

    def set_key_remap(self, code, hid_usage, modifiers=0):
        try:
            idx = self._key_indices([code])[0]
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        return self._adv(lambda d: d.set_key_remap(idx, int(hid_usage), int(modifiers)))

    def set_advanced_socd(self, code_a, code_b, hid_a, hid_b, mode=3):
        """SOCD pair. `mode` is a RAW byte: only 0x03 has ever been observed on
        the wire, so the UI offers only that one — see the registry note."""
        try:
            ia, ib = self._key_indices([code_a, code_b])
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        return self._adv(lambda d: d.set_advanced_socd(ia, ib, int(hid_a), int(hid_b), int(mode)))

    def set_advanced_rs(self, code_a, code_b, hid_a, hid_b):
        try:
            ia, ib = self._key_indices([code_a, code_b])
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        return self._adv(lambda d: d.set_advanced_rs(ia, ib, int(hid_a), int(hid_b)))

    def set_advanced_mt(self, code, delay, tap_hid=0, hold_hid=0):
        """`delay` is the RAW byte — its unit is unverified (one sample, 0x28),
        so nothing here converts it to milliseconds."""
        try:
            idx = self._key_indices([code])[0]
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        return self._adv(lambda d: d.set_advanced_mt(idx, int(delay), int(tap_hid), int(hold_hid)))

    def set_advanced_tgl(self, code, hid_usage=0):
        try:
            idx = self._key_indices([code])[0]
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        return self._adv(lambda d: d.set_advanced_tgl(idx, int(hid_usage)))

    def clear_advanced_key(self, code):
        try:
            idx = self._key_indices([code])[0]
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        return self._adv(lambda d: d.clear_advanced_key(idx))

    # ---- macros (feature "macros"; Win60: cmd-25 slots + cmd-24 type-0x10 binds) ----
    #
    # The driver owns the wire (slot images, keymap read-modify-write); this
    # layer translates design codes <-> key indices, JS event dicts <->
    # driver tuples, and keeps macro NAMES, which the firmware does not store,
    # in settings.json under `macroNames` (merged, so UI profile saves keep it).
    MACRO_NAMES_KEY = "macroNames"
    MACRO_NAME_MAX = 32

    def _keymap_context(self):
        """Keymap context a whole-layer bind needs to compose its write (see
        Win60Driver.bind_macro): the board's default hid per index, the
        Fn-type indices, Aether's pending plain remaps and the connect-time
        Fn snapshot."""
        km = getattr(self, "km", None)
        if not km:
            return {}
        return {
            "default_hids": {i: km.by_index[i]["hid"] for i in km.by_index},
            "layer_indices": set(km.layer_indices),
            "overrides": dict(getattr(self, "_remaps", None) or {}),
            "fn_layer_raw": getattr(self, "_fn_layer_raw", None),
        }

    def _macro_names(self):
        r = self.load_settings()
        s = r.get("settings") if r.get("ok") else None
        names = (s or {}).get(self.MACRO_NAMES_KEY) if isinstance(s, dict) else None
        return dict(names) if isinstance(names, dict) else {}

    def _set_macro_name(self, slot, name):
        names = self._macro_names()
        if name:
            names[str(int(slot))] = name
        else:
            names.pop(str(int(slot)), None)
        r = self.save_settings({self.MACRO_NAMES_KEY: names})
        if not r.get("ok"):
            raise RuntimeError("could not persist macro name: %s" % r.get("error"))

    @staticmethod
    def _macro_events_json(events):
        return [{"delay": int(d), "hid": int(h), "down": bool(down)}
                for d, h, down in events]

    @staticmethod
    def _macro_events(events, drv):
        """JS event dicts [{delay, hid, down}] (or tuples) -> the driver's
        (delay_before_ms, hid, is_down) tuples, validated against the
        driver's own limits (slot count/size, hid 0..255, delay range)."""
        out = []
        for ev in list(events or ()):
            if isinstance(ev, dict):
                delay, hid, down = ev.get("delay", 0), ev.get("hid"), ev.get("down")
            else:
                delay, hid, down = ev
            try:
                delay, hid = int(delay), int(hid)
            except (TypeError, ValueError):
                raise ValueError("macro event needs integer delay and hid: %r" % (ev,))
            if not 0 <= hid <= 0xFF:
                raise ValueError("macro HID usage must be 0..255, got %d" % hid)
            if not 0 <= delay <= drv.MACRO_MAX_DELAY_MS:
                raise ValueError("macro delay must be 0..%d ms, got %d"
                                 % (drv.MACRO_MAX_DELAY_MS, delay))
            out.append((delay, hid, bool(down)))
        if len(out) > drv.MACRO_MAX_EVENTS:
            raise ValueError("macro too long: max %d events" % drv.MACRO_MAX_EVENTS)
        return out

    @staticmethod
    def _macro_slot(slot, drv):
        if not drv.supports("macros"):
            raise UnsupportedFeature(drv.name, "macros")
        slot = int(slot)
        if not 0 <= slot < drv.MACRO_SLOTS:
            raise ValueError("macro slot must be 0..%d" % (drv.MACRO_SLOTS - 1))
        return slot

    @staticmethod
    def _macro_playback(play_mode, repeat_count, drv):
        if play_mode is not None:
            play_mode = int(play_mode)
            if play_mode not in drv.MACRO_PLAY_MODES:
                raise ValueError("play mode must be one of %s"
                                 % (list(drv.MACRO_PLAY_MODES),))
        if repeat_count is not None:
            repeat_count = int(repeat_count)
            if not 1 <= repeat_count <= drv.MACRO_MAX_REPEAT:
                raise ValueError("repeat count must be 1..%d" % drv.MACRO_MAX_REPEAT)
        return play_mode, repeat_count

    def _macro_json(self, slot, m, names):
        events = m["events"] if isinstance(m, dict) else list(m or [])
        out = {"slot": int(slot), "name": names.get(str(int(slot)), ""),
               "events": self._macro_events_json(events)}
        if isinstance(m, dict):
            out["play_mode"] = int(m.get("play_mode", 0))
            out["repeat_count"] = int(m.get("repeat_count", 1))
        return out

    def _macro_bindings_by_code(self):
        """{design code: slot} from the board's base layer (raises)."""
        binds = self.driver.read_macro_bindings()
        out = {}
        for idx, slot in binds.items():
            code = self.km.code_of(int(idx)) if self.km else None
            out[code or ("idx%d" % idx)] = int(slot)
        return out

    def list_macros(self):
        """Every stored macro + which keys point at one:
        {ok, macros: [{slot, name, play_mode, repeat_count, events}],
         bindings: {code: slot} | null, bindings_error?, slots, max_events}."""
        drv = getattr(self, "driver", None)
        if drv is None:
            return {"ok": False, "error": "not connected"}
        try:
            names = self._macro_names()
            with self._reader_paused():           # 10 slot reads + keymap read
                stored = drv.list_macros()
                macros = [self._macro_json(s, m, names) for s, m in sorted(stored.items())]
                out = {"ok": True, "macros": macros,
                       "slots": drv.MACRO_SLOTS,
                       "max_events": drv.MACRO_MAX_EVENTS,
                       "max_delay_ms": drv.MACRO_MAX_DELAY_MS,
                       "max_repeat": drv.MACRO_MAX_REPEAT,
                       "play_modes": list(drv.MACRO_PLAY_MODES)}
                try:
                    out["bindings"] = self._macro_bindings_by_code()
                except UnsupportedFeature:
                    out["bindings"] = None
                except Exception as e:
                    out["bindings"] = None
                    out["bindings_error"] = str(e)
            return out
        except Exception as e:
            return self._fail(e)

    def read_macro(self, slot):
        drv = getattr(self, "driver", None)
        if drv is None:
            return {"ok": False, "error": "not connected"}
        try:
            slot = self._macro_slot(slot, drv)
            with self._reader_paused():
                m = drv.read_macro(slot)
            return {"ok": True,
                    "macro": None if m is None else self._macro_json(slot, m, self._macro_names())}
        except Exception as e:
            return self._fail(e)

    def save_macro(self, slot, name, events, play_mode=0, repeat_count=1):
        """Validate + store one macro slot. `events` = [{delay, hid, down}]
        (delay = ms BEFORE the event); an empty list deletes the slot (use
        delete_macro to also release the keys pointing at it)."""
        drv = getattr(self, "driver", None)
        if drv is None:
            return {"ok": False, "error": "not connected"}
        try:
            slot = self._macro_slot(slot, drv)
            evs = self._macro_events(events, drv)
            if not evs:
                raise ValueError("a macro needs at least one event")
            play_mode, repeat_count = self._macro_playback(
                0 if play_mode is None else play_mode,
                1 if repeat_count is None else repeat_count, drv)
            name = str(name or "").strip()[:self.MACRO_NAME_MAX]
            drv.write_macro(slot, evs, play_mode=play_mode, repeat_count=repeat_count)
            self._set_macro_name(slot, name)
            return {"ok": True, "slot": slot, "events": len(evs)}
        except Exception as e:
            return self._fail(e)

    def delete_macro(self, slot):
        """Erase a slot (all-zero image, as the vendor writes for unused
        slots) and restore every key that pointed at it to its default."""
        drv = getattr(self, "driver", None)
        if drv is None:
            return {"ok": False, "error": "not connected"}
        try:
            slot = self._macro_slot(slot, drv)
            released = []
            with self._lock, self._reader_paused():
                try:
                    binds = drv.read_macro_bindings()
                except UnsupportedFeature:
                    binds = {}
                ctx = self._keymap_context()
                for idx, s in binds.items():
                    if int(s) == slot:
                        drv.unbind_key(int(idx), **ctx)
                        released.append(self.km.code_of(int(idx)) if self.km else int(idx))
                drv.write_macro(slot, None)
            self._set_macro_name(slot, "")
            return {"ok": True, "slot": slot, "released": released}
        except Exception as e:
            return self._fail(e)

    def bind_macro(self, code, slot, play_mode=None, repeat_count=None):
        """Point the key at design code `code` to macro slot `slot`. With
        `play_mode`/`repeat_count` the slot's header is updated too (they
        live in the slot on the Win60, not in the keymap entry)."""
        drv = getattr(self, "driver", None)
        if drv is None:
            return {"ok": False, "error": "not connected"}
        try:
            idx = self._key_indices([code])[0]
            slot = self._macro_slot(slot, drv)
            play_mode, repeat_count = self._macro_playback(play_mode, repeat_count, drv)
            with self._reader_paused():           # keymap RMW (+ slot read)
                drv.bind_macro(idx, slot, play_mode, repeat_count, **self._keymap_context())
            return {"ok": True, "code": code, "index": idx, "slot": slot}
        except Exception as e:
            return self._fail(e)

    def unbind_macro(self, code):
        """Restore the key at design code `code` to its plain default entry."""
        drv = getattr(self, "driver", None)
        if drv is None:
            return {"ok": False, "error": "not connected"}
        try:
            idx = self._key_indices([code])[0]
            with self._reader_paused():           # keymap RMW
                drv.unbind_key(idx, **self._keymap_context())
            return {"ok": True, "code": code, "index": idx}
        except Exception as e:
            return self._fail(e)

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

    def update_progress(self):
        """Download progress for the in-flight update: {phase, done, total, pct}.
        Polled by the UI while apply_update() runs — the installer asset is ~20 MB,
        and without this the window looks frozen for the whole download."""
        return {"ok": True, **updater.get_progress()}

    def apply_update(self, asset_url, asset_name=None, asset_size=None, asset_sha256=None):
        """Download + install the update for this OS. On success the caller
        should quit (Windows) or prompt a restart (Flatpak).

        asset_size/asset_sha256 come from check_update(); updater re-fetches them
        if omitted, so the download is verified either way."""
        res = updater.apply_update(asset_url, asset_name, asset_size, asset_sha256)
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
        # ~120 Hz sampling of the live reader. VirtualGamepad.update() is a
        # no-op on an unchanged frame, so an idle board costs a dict copy and
        # a tuple compare per tick — no uinput/ViGEm traffic. Event.wait (not
        # time.sleep) so set_gamepad_capture(False) returns promptly.
        stop = self._pad_stop
        while not stop.wait(1 / 120):
            try:
                pad, reader = self.pad, self.reader
                if pad is not None and reader is not None:
                    pad.update(reader.snapshot())
            except Exception as e:
                log.warning("gamepad capture stopped: %s", e)
                break

    #: One hex byte token for send_raw: "1f", "0x1F", "7". Three-digit
    #: tokens ("100") are rejected here rather than masked or passed as a
    #: >255 value that hidapi would refuse mid-report.
    _HEX_BYTE = re.compile(r"^(?:0[xX])?[0-9a-fA-F]{1,2}$")

    def send_raw(self, hex_str):
        """Developer console: send one raw output report. The hex string is
        the FULL report (report id first, e.g. "01 07 00 00 00 0e ..."),
        zero-padded to 64 bytes. Every token must be a byte; the frame then
        goes through the active driver's never-send guard (Win60:
        protocol.dangerous_command_reason — factory reset, trigger reset,
        blind calibration arm; MINI: DANGEROUS_CMDS) instead of straight to
        the handle, so a typo can't brick or wipe the board."""
        try:
            tokens = str(hex_str or "").replace(",", " ").split()
            if not tokens:
                return {"ok": False, "error": "empty report"}
            payload = []
            for t in tokens:
                if not self._HEX_BYTE.match(t):
                    return {"ok": False,
                            "error": f"invalid hex byte {t!r} (expected 00..ff)"}
                payload.append(int(t, 16))
            if len(payload) > 64:
                return {"ok": False,
                        "error": f"report too long: {len(payload)} bytes (max 64)"}
            payload += [0] * (64 - len(payload))
            self.driver.send_raw(payload)          # guarded per board
            return {"ok": True}
        except Exception as e:
            return self._fail(e)

    # ---- status on keys: CPU / RAM / GPU bars, Pomodoro, flash (overlays.py) ----
    #
    # The layer is composited by the effect engine onto whatever it streams
    # (`fx.overlay`), so it works over every host effect. When the active
    # lighting is a FIRMWARE mode (static / Full-RGB / per-key paint / off) the
    # host engine is switched on as a "carrier" that reproduces it (see
    # overlays.carrier_plan) and switched off again, restoring the firmware
    # lighting with one write, when the last overlay goes off.
    def _ov_attach(self):
        """(Re)build the overlay manager for the current keymap + engine."""
        old = getattr(self, "_overlays", None)
        if old is not None:
            try:
                old.close()
            except Exception:
                pass
        self._overlays = None
        self._carrier_on = False
        try:
            if not (getattr(self, "fx", None) and getattr(self, "km", None)):
                return
            rows = {oid: self.km.indices_for_codes(codes)
                    for oid, codes in overlays.ROW_CODES.items()}
            mgr = overlays.OverlayManager(
                rows, self.fx.indices, self._settings_path(), _SETTINGS_LOCK,
                gpu=overlays.GpuProbe(), gate=lambda: self.dev.is_open())
            self._overlays = mgr
            self.fx.overlay = mgr.layer
            mgr.follow_profile(self._ov_profile_id())
        except Exception as e:
            log.warning("status-on-keys unavailable: %s", e)
            self._overlays = None

    def _ov_profile_id(self):
        pid = getattr(self, "_ov_profile", None)
        if isinstance(pid, str) and pid:
            return pid
        try:
            with open(self._settings_path(), "r", encoding="utf-8") as f:
                pid = json.load(f).get("activeProfile")
        except Exception:
            pid = None
        return pid if isinstance(pid, str) and 0 < len(pid) <= overlays.MAX_PROFILE_ID else "p1"

    def _ov_follow(self, state):
        """games_sync calls this on every profile change (and at start-up)."""
        try:
            pid = state.get("activeProfile") if isinstance(state, dict) else None
            if (not isinstance(pid, str) or not 0 < len(pid) <= overlays.MAX_PROFILE_ID
                    or pid == getattr(self, "_ov_profile", None)):
                return
            self._ov_profile = pid
            mgr = getattr(self, "_overlays", None)
            if mgr is not None:
                mgr.follow_profile(pid)
                self._overlay_sync()
        except Exception as e:
            log.warning("overlay profile follow failed: %s", e)

    def _ov_supported(self):
        """Overlays need the host engine: a keymap, a driver that streams
        per-key frames, and a board whose registry does not forbid it."""
        try:
            if getattr(self, "_overlays", None) is None or not getattr(self, "fx", None):
                return False
            if not self.driver.supports("host_effects"):
                return False
            lt = getattr(self.board, "lighting", None) or {}
            return lt.get("hostEngine") is not False
        except Exception:
            return False

    def _stop_overlays(self):
        """main(): stop the sampler thread on the way out."""
        mgr = getattr(self, "_overlays", None)
        if mgr is not None:
            mgr.close()

    # ---- music visualizer (Phase 7) ----
    def _music_attach(self):
        """Hand the app's MusicSource to the current engine (a new engine is
        built per board)."""
        fx = getattr(self, "fx", None)
        if fx is not None:
            fx.music = getattr(self, "_music", None)

    def music_status(self):
        """{ok, available, reason, state, device} for the Lighting tab. Never
        opens an audio device (availability is a find_spec check); state is
        off | starting | listening | no_device | error | unavailable."""
        try:
            src = getattr(self, "_music", None)
            if src is None:
                ok, reason = music.availability()
                return {"ok": True, "available": ok, "reason": reason,
                        "state": "off" if ok else "unavailable", "device": None}
            return dict(src.status(), ok=True)
        except Exception as e:
            return self._fail(e)

    def get_overlays(self):
        """Dashboard "Status on keys" tile. -> {ok, supported, overlays:[{id,
        label, row, on, available, reason, value}], pomodoro:{phase,
        remaining_s}}; unsupported boards answer supported:false."""
        try:
            if not self._ov_supported():
                return {"ok": True, "supported": False, "overlays": [],
                        "pomodoro": {"phase": None, "remaining_s": None}}
            return dict(self._overlays.status(), ok=True, supported=True)
        except Exception as e:
            return self._fail(e)

    def set_overlay(self, overlay_id, on):
        """Turn one overlay on/off for the ACTIVE profile (persisted).
        -> {ok, id, on}."""
        try:
            if not self._ov_supported():
                return {"ok": False, "error": "status on keys needs a board with host effects"}
            res = self._overlays.set(str(overlay_id), bool(on))
            if not res.get("ok"):
                return res
            self._overlay_sync()
            return {"ok": True, "id": res["id"], "on": res["on"]}
        except Exception as e:
            return self._fail(e)

    def flash(self, color, ms=600):
        """Flash the whole board `color` ([r, g, b]) fading out over `ms`
        (50..5000). Needs the host engine to be streaming (a host effect or an
        overlay); firmware-only lighting answers ok:false."""
        try:
            if not (isinstance(color, (list, tuple)) and len(color) >= 3):
                return {"ok": False, "error": "color must be [r, g, b]"}
            rgb = tuple(int(c) for c in color[:3])
            fx = getattr(self, "fx", None)
            if not (self._ov_supported() and fx is not None and fx.is_running()):
                return {"ok": False, "error": "flash needs a host effect or a status overlay running"}
            self._overlays.layer.flash(rgb, int(ms))
            return {"ok": True}
        except (TypeError, ValueError) as e:
            return {"ok": False, "error": f"bad flash arguments: {e}"}
        except Exception as e:
            return self._fail(e)

    def _overlay_active(self):
        """Overlays on AND drawable (supported board, at least one toggle on)."""
        mgr = getattr(self, "_overlays", None)
        return bool(mgr is not None and mgr.any_on() and self._ov_supported())

    def _bright_max(self):
        lt = getattr(self.board, "lighting", None) or {}
        return int(lt.get("brightnessMax", 4) or 4)

    def _overlay_sync(self):
        """Reconcile the engine with the toggles. Overlays on and nothing
        streaming -> start the carrier; every overlay off while the carrier
        runs -> stop it and give the firmware lighting back. A host effect the
        UI started is never touched: the layer simply stops drawing."""
        try:
            fx = getattr(self, "fx", None)
            if fx is None or getattr(self, "_overlays", None) is None:
                return
            with _CARRIER_LOCK:
                if self._overlay_active():
                    if not fx.is_running() and self.dev.is_open():
                        self._carrier_start()
                elif getattr(self, "_carrier_on", False):
                    self._carrier_stop()
        except Exception as e:
            log.warning("overlay carrier sync failed: %s", e)

    def _carrier_start(self):
        """Stream a host rendering of the last firmware lighting (black when
        none is known) with the overlay layer on top."""
        with _CARRIER_LOCK:
            plan = overlays.carrier_plan(getattr(self, "_light_src", None), self.fx.indices,
                                         self._bright_max())
            self.driver.begin_host_stream()
            self.fx.start_zones(plan["zones"], global_bg=plan["bg"], base=plan["base"])
            self._carrier_on = True

    def _carrier_stop(self):
        """Stop the carrier and re-send the firmware lighting the UI last asked
        for: one set_lighting (or per-key table) write, the same bytes the UI
        itself would have sent."""
        with _CARRIER_LOCK:
            self._carrier_on = False
            self.fx.stop()
            try:
                self.driver.end_host_stream()
            except Exception:
                pass
            src = getattr(self, "_light_src", None)
            if not src or not self.dev.is_open():
                return
            if src[0] == "light":
                p = src[1]
                self.driver.set_lighting(p["mode"], p["fg"], bg=p["bg"], brightness=p["brightness"],
                                         speed=p["speed"], direction=p["direction"],
                                         full_color=p["full_color"], power_on=p["power_on"])
            elif src[0] == "custom":
                self.driver.set_per_key_rgb(dict(src[1]), brightness=src[2], speed=src[3])


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
        if any(m in effects.PRESS_REACTIVE for m in modes):
            try:
                self._acquire_reader("reactive", self._make_live_reader)
            except UnsupportedFeature:
                pass
            if self.reader is None and not self._calibrating:
                self.fx.get_depths = None
                self.fx.get_actuation = None
                return
            # While calibrating the reader is deferred: get_depths resolves
            # self.reader per call, so the effect wakes when it is restored.
            km = self.km

            def get_depths():
                # Resolve the reader on EVERY call (never capture it): the
                # analog tab replaces self.reader with a new instance, and a
                # captured, stopped reader would leave the effect deaf.
                rdr = self.reader
                if rdr is None:
                    return {}
                by_idx = getattr(rdr, "snapshot_by_index", None)
                if by_idx is not None:
                    return by_idx()          # one dict copy, no remap
                idx_of = km.index_of_code
                return {idx_of[c]: mm for c, mm in rdr.snapshot().items()
                        if c in idx_of}

            self.fx.get_depths = get_depths
            # The pressure effect also needs each key's actuation point.
            self.fx.get_actuation = self._actuation_snapshot
        else:
            self.fx.get_depths = None
            self.fx.get_actuation = None
            self._release_reader("reactive")

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
            pal = [tuple(int(c) for c in p[:3]) for p in (colors or []) if p]
            bg_rgb = tuple(int(c) for c in (bg or (0, 0, 0))[:3])
            # One engine, several threads (pywebview calls, games_sync's overlay
            # follow): the carrier lock serialises every start/stop of it.
            with _CARRIER_LOCK:
                self.driver.begin_host_stream()
                self._ensure_reactive([str(pattern)])
                self.fx.start(str(pattern), pal or [(255, 255, 255)], bg_rgb,
                              float(speed) / 100.0, float(brightness) / 100.0,
                              int(direction), str(orient))
                self._carrier_on = False
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
            gbg = norm and norm[0].get("bg") or (0, 0, 0)
            with _CARRIER_LOCK:         # see start_multicolor
                self.driver.begin_host_stream()
                self._ensure_reactive([z["mode"] for z in norm])
                self.fx.start_zones(norm, global_bg=gbg)
                self._carrier_on = False
            return {"ok": True, "zones": len(norm)}
        except Exception as e:
            return self._fail(e)

    def stop_multicolor(self):
        with _CARRIER_LOCK:           # serialised with the carrier and the starters
            self._carrier_on = False  # the engine (carrier or not) goes down
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
        boot.show_error(f"Aether HE could not start: UI not found\n\n{INDEX}")
        raise SystemExit(f"UI not found: {INDEX}")
    # One instance: a second launch while Aether sits in the tray used to die
    # in WebView2 (0x8007139F: profile folder held by the other process).
    # Now it asks the running instance to show its window, then exits.
    inst = single_instance.SingleInstance()
    if not inst.acquire():
        res = inst.poke_existing()
        if res == single_instance.SHOWN:
            log.info("Aether is already running — brought its window up")
        elif res == single_instance.UNRESPONSIVE:
            log.warning("Aether is already running but not responding")
            inst.notify_unresponsive(tray.APP_NAME)
        else:
            log.warning("Aether is already running but could not be reached")
            inst.notify_unreachable(tray.APP_NAME)
        return
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
    # Tray residency: closing the window hides it and the effect engine keeps
    # streaming; `--minimized` (the autostart entry) starts hidden. The React
    # app in a hidden WebView2 still runs — it is what applies tray changes —
    # but Chromium throttles hidden-page timers to 1 Hz, which would turn the
    # 70 ms lighting debounce into a one-second lag on the tray's speed
    # slider. This documented WebView2 switch keeps timers at full rate.
    # Hidden start = --minimized, or the Settings toggle on a sign-in
    # (--autostart) launch. A launch from a shortcut always shows the window.
    minimized = tray.start_hidden(sys.argv[1:], api._settings_path())
    if sys.platform.startswith("win"):
        extra = "--disable-background-timer-throttling"
        cur = os.environ.get("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "")
        if extra not in cur:
            os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = (cur + " " + extra).strip()
    tray_ctl = tray.TrayController(api, webview)
    # Game detection polls from here on (Windows only); the tray tooltip
    # names the detected game.
    api._start_games(tray_ctl.set_game)
    window = webview.create_window(
        "Aether", url, js_api=api,
        width=1340, height=900, min_size=(1160, 800),
        background_color="#07080d", hidden=minimized,
    )
    tray_ctl.main_window = window
    tray_ctl.main_visible = not minimized
    window.events.closing += tray_ctl.on_main_closing
    # Never hang the controller (or any window) on a PUBLIC Api attribute:
    # pywebview publishes every public attribute of js_api to the page by
    # walking it recursively on each load. `api.tray` led it through
    # main_window.native into the whole WinForms/.NET object graph —
    # thousands of failing lookups ending in "maximum recursion depth
    # exceeded" on every start (seen in a 0.5.2 user log).
    # Never pop a DevTools window at launch. pywebview ships
    # OPEN_DEVTOOLS_IN_DEBUG=True, and its Edge/Chromium backend does
    # `if _state['debug'] and OPEN_DEVTOOLS_IN_DEBUG: OpenDevToolsWindow()`,
    # so anything that flips debug on — a stray env var, a future edit, a
    # packaged build — silently gives every user a debugger window next to the
    # app. Turn the setting off and pass debug explicitly rather than relying on
    # the default staying False.
    try:
        webview.settings['OPEN_DEVTOOLS_IN_DEBUG'] = False
    except Exception:
        pass  # older pywebview without the settings dict
    # AETHER_DEBUG=1 re-enables the inspector for development.
    debug = os.environ.get("AETHER_DEBUG") == "1"
    # private_mode=False comes from main: it gives the webview a persistent
    # profile so localStorage survives a restart. Kept — only `debug` is
    # overridden here, because debug=True is what pops the DevTools window.
    def _boot(w):
        # The tray icon needs no GUI loop of ours (pystray runs detached), but
        # it must exist before the first close and — when starting minimized —
        # before there is anything else on screen to reach the app through.
        if not tray_ctl.start() and minimized:
            log.warning("no tray backend; start-minimized ignored, showing the window")
            tray_ctl.show_main()
        _on_start(w)

    # A later launch pokes us: bring the window up (and drop the panel).
    # Armed BEFORE webview.start so a double-click during the 1–2 s boot
    # isn't lost; a poke that lands before the window exists just logs.
    def _on_poke():
        tray_ctl.hide_panel()
        return tray_ctl.show_main()
    inst.listen(_on_poke)

    # Aether's OWN WebView2 profile. pywebview's default is the shared
    # %LOCALAPPDATA%\pywebview folder — every pywebview app and every older
    # Aether build (the installer's autostart entry, for one) open the same
    # one, and WebView2 refuses a folder another process holds with different
    # options (0x8007139F). localStorage moves with it: setup-done/zoom/
    # auto-connect flags reset once; settings.json is untouched.
    storage = os.path.join(os.path.dirname(api._settings_path()), "webview")
    try:
        webview.start(_boot, window, debug=debug, private_mode=False,
                      storage_path=storage)
    finally:
        # pystray's detached message loop is a NON-daemon thread: if the GUI
        # loop ends by any path other than tray → Exit (hide-on-close failed
        # and the window really closed, an exception inside webview.start),
        # the process would linger with a live tray icon. exit() is idempotent.
        try:
            tray_ctl.exit()
        except Exception:
            pass
        api._stop_games()
        api._stop_overlays()
        inst.release()


if __name__ == "__main__":
    main()
