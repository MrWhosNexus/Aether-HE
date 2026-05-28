"""AETHER HE — native webview shell.

Renders the exact Claude Design UI (ui/index.html, the standalone React/Tailwind
prototype) in a GTK/WebKit window, and bridges its on-screen state to the real
keyboard over HID. WebKit has no WebHID, so a small injected JS bridge calls into
this Python `Api` (exposed as window.pywebview.api), and mirrors the rendered
per-key colors to the board's global lighting command.
"""
import logging
import os
import sys
import threading
import time

import webview

from aula_device import AulaDevice
import protocol
import effects
import device_state
import gamepad
import updater

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


class Api:
    def __init__(self):
        self.dev = AulaDevice()
        self._lock = threading.Lock()
        self.pad = None
        self._pad_stop = threading.Event()
        self._pad_thread = None
        try:
            self.km = device_state.KeyMap()
        except Exception as e:
            self.km = None
            log.warning("keymap load failed: %s", e)
        # Host-driven per-key effect engine (multi-color animated effects).
        self.fx = effects.PerKeyEffectEngine(self.km, self._send_frame) if self.km else None
        self._last_pkts = None    # diff cache: only re-send changed pages (latency)
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
    def connect(self):
        try:
            info = self.dev.open()
            # device-info handshake + start live travel reader
            try:
                self.dev.write(protocol.build_heartbeat())
            except Exception:
                pass
            # Snapshot the device's Fn-layer table so we can replay it after any
            # base-layer write (see _flush_remaps). Failures here are non-fatal;
            # we just won't be able to preserve the user's Fn customization.
            # _read_keymap_layer returns None on partial reads — we treat that
            # as "no snapshot" and skip the Fn-layer write entirely rather than
            # risk wiping the user's customisation with a half-zeroed table.
            try:
                self._fn_layer_raw = self._read_keymap_layer(fn_layer=True)
            except Exception as ex:
                log.warning("Fn-layer snapshot failed (will skip Fn write): %s", ex)
                self._fn_layer_raw = None
            return {"ok": True, "iface": info["interface_number"]}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _read_keymap_layer(self, fn_layer=False, timeout_s=1.5):
        """Send initKeyValue and collect the device's response packets, reassembling
        a 528-byte [code1, hidCode, code3, code4] table. Matches the driver's
        cmd-24 [1]=128 (base) / [1]=130 (fn) read flow.

        Returns the complete table only if ALL pages were received; on a partial
        read returns None so the caller can fall back to "don't write Fn" (better
        than writing a half-zeroed table that wipes the user's Fn customization).
        """
        if not self.dev.is_open():
            return None
        # Drain any pending packets first so we only see the response.
        with self.dev._lock:
            try:
                self.dev._dev.set_nonblocking(True)
                while True:
                    r = self.dev._dev.read(64)
                    if not r:
                        break
            except Exception:
                pass
        self._write(protocol.build_read_keymap_init(fn_layer=fn_layer))
        want = 130 if fn_layer else 128
        table = bytearray(528)
        seen = set()
        deadline = time.time() + timeout_s
        n_pages = (528 + 55) // 56
        while time.time() < deadline and len(seen) < n_pages:
            try:
                with self.dev._lock:
                    if not self.dev._dev:
                        break
                    self.dev._dev.set_nonblocking(True)
                    r = self.dev._dev.read(64)
            except Exception:
                break
            if not r or len(r) < 6:
                time.sleep(0.005); continue
            # hidapi's read on this codebase includes the report ID at r[0], so
            # the cmd byte sits at r[1] (matching LiveReader/CalibrationReader,
            # which empirically work). We still scan a small offset range as a
            # safety net for hidapi variants that don't prepend the id.
            base = None
            for off in (1, 0, 4, 5):
                if off + 5 >= len(r):
                    continue
                if r[off] == 24 and r[off + 1] == want:
                    base = off
                    break
            if base is None:
                continue
            page = (r[base + 2] << 8) | r[base + 3]
            ln = min(r[base + 4], 56)
            data_off = base + 5
            start = page * 56
            end = start + ln
            if end > len(table):
                end = len(table); ln = end - start
            if ln <= 0 or data_off + ln > len(r):
                continue
            table[start:end] = bytes(r[data_off:data_off + ln])
            seen.add(page)
        complete = len(seen) >= n_pages
        log.info("keymap snapshot: layer=%s pages=%d/%d complete=%s",
                 "fn" if fn_layer else "base", len(seen), n_pages, complete)
        return bytes(table) if complete else None

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

    def _write(self, payload):
        with self._lock:
            if not self.dev.is_open():
                self.dev.open()
            self.dev.write(payload)

    # ---- lighting (exact driver layout: fg/bg/mode/brightness/speed/dir/power) ----
    def set_light(self, mode, r, g, b, brightness=4, speed=4,
                  bg_r=0, bg_g=0, bg_b=0, direction=0, power_on=True, full_color=0):
        try:
            self._write(protocol.build_light(
                int(mode), int(brightness), int(speed), (int(r), int(g), int(b)),
                (int(bg_r), int(bg_g), int(bg_b)), int(direction), int(full_color),
                bool(power_on)))
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # back-compat: simple static color
    def set_color(self, r, g, b, brightness=4, mode=0, speed=4):
        return self.set_light(mode, r, g, b, brightness, speed)

    # ---- actuation / trigger ----
    def set_trigger_all(self, travel_mm, rt_press_mm=0.0, rt_release_mm=0.0,
                        key_count=64, mode=2):
        try:
            self._write(protocol.build_trigger(int(mode), list(range(int(key_count))),
                        float(travel_mm), float(rt_press_mm), float(rt_release_mm)))
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

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
                self.reader = device_state.LiveReader(self.dev, self.km, idxs)
                self.reader.start()
            else:
                self._write(protocol.build_open_trigger_test(list(range(64))))
            return {"ok": True, "keys": len(idxs) if self.km else 64}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def close_analog(self):
        try:
            if self.reader:
                self.reader.stop()
                self.reader = None
            else:
                self._write(protocol.build_close_trigger_test())
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ---- polling ----
    def set_poll(self, rate):
        try:
            self._write(protocol.build_poll_rate(int(rate))); return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

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
                     mode, travel * protocol.TRIGGER_UNIT_MM, i1, i2,
                     len(idxs), sorted(idxs)[:8])
            self._write(protocol.build_trigger(int(mode), list(idxs),
                                               travel * protocol.TRIGGER_UNIT_MM,
                                               i1 * protocol.TRIGGER_UNIT_MM,
                                               i2 * protocol.TRIGGER_UNIT_MM))
            threading.Event().wait(0.005)

    def set_trigger_codes(self, codes, travel_mm, rt_press_mm=0.0, rt_release_mm=0.0, mode=0):
        if not self.km:
            return {"ok": False, "error": "no keymap"}
        idxs = self.km.indices_for_codes(codes) if codes else []
        if not idxs:
            return {"ok": False, "error": "no keys"}
        cfg = (int(mode),
               protocol.mm_to_raw(travel_mm),
               protocol.mm_to_raw(rt_press_mm),
               protocol.mm_to_raw(rt_release_mm))
        for i in idxs:
            self._trigger_state[i] = cfg
        try:
            self._flush_triggers(edited_idxs=idxs)
            return {"ok": True, "keys": len(idxs), "idxs": sorted(idxs)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def verify_actuation(self, codes):
        """Read-back actuation for the given codes (one cmd-33/sub-5 query per
        key). Used as a sanity check that per-key writes actually stick on the
        firmware: call before and after set_trigger_codes, compare the values."""
        if not self.km or not self.dev.is_open():
            return {"ok": False, "error": "not connected"}
        try:
            with self._lock:
                vals = device_state.read_actuation(self.dev, self.km)
            # Filter to the requested codes if any.
            if codes:
                names_by_code = {c: self.km.by_index[self.km.index_of_code[c]]["name"]
                                 for c in codes if c in self.km.index_of_code}
                out = {c: vals.get(name) for c, name in names_by_code.items()}
            else:
                out = vals
            return {"ok": True, "actuation_mm": out}
        except Exception as e:
            return {"ok": False, "error": str(e)}

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
            self._write(protocol.build_light(10, int(brightness), int(speed), (255, 255, 255)))
            for pkt in protocol.build_custom_light(colors_by_index, slot=0):
                self._write(pkt)
                threading.Event().wait(0.005)
            return {"ok": True, "keys": len(colors_by_index)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ---- dead band / switch profile ----
    def set_deadband_codes(self, codes, top_mm=0.04, bottom_mm=0.05):
        if not self.km:
            return {"ok": False, "error": "no keymap"}
        idxs = self.km.indices_for_codes(codes) if codes else []
        if not idxs:
            return {"ok": False, "error": "no keys"}
        top = round(float(top_mm) / protocol.TRIGGER_UNIT_MM)
        bottom = round(float(bottom_mm) / protocol.TRIGGER_UNIT_MM)
        # Preserve previously-set per-key values so applying to one selection
        # doesn't reset everything else to the default. The full-board table is
        # rebuilt from the accumulated state on every send.
        for i in idxs:
            self._deadband_state[i] = (top, bottom)
        try:
            for pkt in protocol.build_deadband_table(dict(self._deadband_state)):
                self._write(pkt)
                threading.Event().wait(0.005)
            return {"ok": True, "keys": len(idxs)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def set_switch_codes(self, codes, switch_id=1):
        if not self.km:
            return {"ok": False, "error": "no keymap"}
        idxs = self.km.indices_for_codes(codes) if codes else self.km.indices()
        if not idxs:
            return {"ok": False, "error": "no keys"}
        table = {idx: int(switch_id) for idx in idxs}
        try:
            for pkt in protocol.build_switch_table(table):
                self._write(pkt)
                threading.Event().wait(0.005)
            return {"ok": True, "keys": len(idxs)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ---- key remap (cmd 24, full keymap table) ----
    def _flush_remaps(self):
        # Base layer with our remap overrides.
        defaults = {i: self.km.by_index[i]["hid"] for i in self.km.by_index}
        for pkt in protocol.build_base_keymap_table(defaults, self._remaps,
                                                     layer_indices=self.km.layer_indices):
            self._write(pkt)
            threading.Event().wait(0.005)
        # Always follow with the Fn layer — the official driver writes both
        # setKeyValue + setFnKeyValue on every Apply, and writing only the base
        # leaves the firmware treating Fn as held until replug. Replay the
        # snapshot we captured at connect; if the snapshot failed we skip the
        # Fn write rather than risk wiping the user's existing Fn mappings with
        # zeros (the "stuck Fn" symptom is preferable to losing customization).
        if self._fn_layer_raw is not None and any(self._fn_layer_raw):
            for pkt in protocol.build_fn_keymap_table(self._fn_layer_raw):
                self._write(pkt)
                threading.Event().wait(0.005)
        else:
            log.warning("skipping Fn-layer write: no snapshot captured at connect")

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
            return {"ok": False, "error": str(e)}

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
            return {"ok": False, "error": str(e)}

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
            self._write(protocol.build_prcs_power(True))
            for pkt in protocol.build_prcs(plist):
                self._write(pkt)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

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
        for pkt in protocol.build_custom_light(colors, slot=0):
            self._write(pkt)

    def calibrate(self, start, any_key=False):
        try:
            if start:
                # Lighting keeps running during calibration (user's choice). The
                # calibration reader uses a short blocking read so it shares the
                # device with the lighting engine without busy-spinning the lock.
                self._write(protocol.build_calibration(True, bool(any_key)))
                self.calib_reader = device_state.CalibrationReader(self.dev, self.km)
                self.calib_reader.start()
            else:
                if self.calib_reader:
                    self.calib_reader.stop()
                    self.calib_reader = None
                self._write(protocol.build_calibration(False, bool(any_key)))
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def read_calibrated(self):
        """Design codes confirmed calibrated so far (for the on-screen highlight)."""
        if not self.calib_reader:
            return {"ok": True, "codes": [], "done": False}
        return {"ok": True, "codes": self.calib_reader.snapshot(),
                "done": bool(self.calib_reader.done)}

    # ---- gamepad mode / win-lock ----
    def gamepad_mode(self, on):
        try:
            self._write(protocol.build_gamepad_mode(1 if on else 0)); return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

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
                self.reader = device_state.LiveReader(self.dev, self.km)
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
        try:
            import json
            with open(self._settings_path(), "w", encoding="utf-8") as f:
                json.dump(settings, f, indent=2)
            return {"ok": True, "path": self._settings_path()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def settings_info(self):
        """Where settings.json lives + whether it exists. UI shows this in the
        Settings tab so users can find / back up / wipe the file."""
        p = self._settings_path()
        return {"ok": True, "path": p, "exists": os.path.exists(p)}

    # ---- updates (GitHub Releases, cross-platform) ----
    def app_version(self):
        import version
        return {"ok": True, "version": version.__version__, "kind": updater.platform_kind()}

    def check_update(self):
        """Ask GitHub for the latest release and whether it's newer than us."""
        return updater.check_for_update()

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

    # ---- host-driven multi-color effects (per-key, cmd 9) ----
    def _send_frame(self, colors_by_index):
        """Stream one per-key RGB frame. Only re-sends the 54-byte pages that
        actually changed since the last frame — this cuts HID-OUT traffic a lot
        for sparse effects (twinkle/reactive/fireworks), reducing input latency.

        Holds the outer Api lock for the WHOLE frame (single acquire, all 8
        pages written under it). The lock has to be respected here because
        _write() — used by set_light / set_trigger / actuation config — also
        takes it; if the engine doesn't, a set_light packet can slip between
        pages and yank the board out of Custom mode mid-frame, collapsing the
        multi-color stream back to a single firmware effect."""
        if not self.dev.is_open():
            return
        try:
            pkts = protocol.build_custom_light(colors_by_index, slot=0)
            last = self._last_pkts
            with self._lock:
                for i, pkt in enumerate(pkts):
                    if last is None or i >= len(last) or pkt != last[i]:
                        self.dev.write(pkt)
            self._last_pkts = pkts
        except Exception:
            self._last_pkts = None

    def _ensure_reactive(self, modes):
        """Press-reactive effects need live travel: attach a depth source (and a
        running analog reader). Other effects detach it."""
        if not self.fx:
            return
        if any(m in ("reactive", "ripple", "speedres", "cross", "fireworks") for m in modes):
            if self.reader is None and self.km:
                self.reader = device_state.LiveReader(self.dev, self.km)
                self.reader.start()
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
        out = {}
        for idx, rgb in dict(self.fx.last_frame).items():
            code = self.km.code_of(idx)
            if code:
                out[code] = [int(rgb[0]), int(rgb[1]), int(rgb[2])]
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
            # bakes brightness into the per-key colors it streams).
            self._write(protocol.build_light(10, 4, 4, (255, 255, 255)))
            self._last_pkts = None
            self._ensure_reactive([str(pattern)])
            pal = [tuple(int(c) for c in p[:3]) for p in (colors or []) if p]
            self.fx.start(str(pattern), pal or [(255, 255, 255)],
                          tuple(int(c) for c in (bg or (0, 0, 0))[:3]),
                          float(speed) / 100.0, float(brightness) / 100.0,
                          int(direction), str(orient))
            return {"ok": True, "keys": len(self.fx.indices)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

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
            self._write(protocol.build_light(10, 4, 4, (255, 255, 255)))
            self._last_pkts = None
            self._ensure_reactive([z["mode"] for z in norm])
            gbg = norm and norm[0].get("bg") or (0, 0, 0)
            self.fx.start_zones(norm, global_bg=gbg)
            return {"ok": True, "zones": len(norm)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def stop_multicolor(self):
        if self.fx and self.fx.is_running():
            self.fx.stop()
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
    # file when it exists on disk verbatim, and the "?v=" cache-buster query
    # breaks that check (the page then loads as a remote URL — which inside a
    # Flatpak/WebKit sandbox fails with a portal "NotAllowed" error).
    from pathlib import Path
    url = Path(INDEX).as_uri() + f"?v={int(os.path.getmtime(INDEX))}"
    window = webview.create_window(
        "Aether", url, js_api=api,
        width=1340, height=900, min_size=(1160, 800),
        background_color="#07080d",
    )
    webview.start(_on_start, window)


if __name__ == "__main__":
    main()
