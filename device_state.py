"""Read real keyboard state: key-index map, per-key actuation, live travel.

Key layout comes from the driver's config (config/keys/<product>.json, bundled as
ui/keymap.json): each key has index, name, code, hidCode, and x/y position. The
device protocol (protocol.py) is used to read per-key trigger values and to
stream live travel after enabling Travel Test.
"""
import os
import sys
import threading
import time

import protocol

HERE = os.path.dirname(os.path.abspath(__file__))
KEYMAP_PATH = os.path.join(HERE, "ui", "keymap.json")

# Keymaps may originate from untrusted submitters, so they are parsed through a
# strict, fail-closed validator (tools/validate_keymap.py) rather than a bare
# json.load. A malformed/malicious file raises KeymapValidationError, which the
# caller treats as "no board" instead of crashing or trusting bad data.
sys.path.insert(0, os.path.join(HERE, "tools"))
from validate_keymap import load_keymap, KeymapValidationError  # noqa: E402

# The design's data-code values (keyboard.jsx KB_ROWS), in physical row order.
# The keymap's own `code` field is the browser event-code (KeyW/ControlLeft/…),
# which does NOT match these — so we align by physical x/y position instead.
DESIGN_CODES = [
    "Escape", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "Minus", "Equal", "Backspace",
    "Tab", "Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P", "Lbr", "Rbr", "Bsl",
    "Caps", "A", "S", "D", "F", "G", "H", "J", "K", "L", "Semi", "Quot", "Enter",
    "LShift", "Z", "X", "C", "V", "B", "N", "M", "Comma", "Dot", "Slash", "RShift",
    "LCtrl", "LWin", "LAlt", "Space", "RAlt", "Menu", "RCtrl", "Fn",
]

# Layout `code` (the web KeyboardEvent.code the vendor key tables use) ->
# design code. Keys are mapped BY NAME: the old positional pairing of the
# sorted keys with DESIGN_CODES only fits the 61-key Win60; on the 68-key
# WIN 68 HE it shifted every code from Insert on (Tab read as Q, A wrote to
# Delete's slot, Space/arrows/Fn got none).
WEB_TO_DESIGN = {
    "Escape": "Escape", "Backquote": "Grave",
    **{f"Digit{d}": str(d) for d in range(10)},
    "Minus": "Minus", "Equal": "Equal", "Backspace": "Backspace",
    "Tab": "Tab", **{f"Key{c}": c for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"},
    "BracketLeft": "Lbr", "BracketRight": "Rbr", "Backslash": "Bsl",
    "CapsLock": "Caps", "Semicolon": "Semi", "Quote": "Quot", "Enter": "Enter",
    "ShiftLeft": "LShift", "Comma": "Comma", "Period": "Dot", "Slash": "Slash",
    "ShiftRight": "RShift", "ControlLeft": "LCtrl", "MetaLeft": "LWin",
    "AltLeft": "LAlt", "Space": "Space", "AltRight": "RAlt", "MetaRight": "RWin",
    "ContextMenu": "Menu", "ControlRight": "RCtrl", "KeyFn": "Fn",
    "Insert": "Ins", "Delete": "Del", "Home": "Home", "End": "End",
    "PageUp": "PgUp", "PageDown": "PgDn",
    "ArrowUp": "Up", "ArrowLeft": "Left", "ArrowDown": "Down", "ArrowRight": "Right",
    **{f"F{n}": f"F{n}" for n in range(1, 13)},
    "IntlBackslash": "IntlBsl", "IntlRo": "IntlRo", "PrintScreen": "PrtSc",
    "ScrollLock": "ScrLk", "Pause": "Pause",
}


def design_codes_for(keys):
    """{device index: design code} by each key's layout `code`, or None when
    any key has an unknown or duplicate code (the caller then falls back to
    the positional mapping)."""
    out, seen = {}, set()
    for k in keys:
        d = WEB_TO_DESIGN.get(k.get("code"))
        if d is None or d in seen:
            return None
        seen.add(d)
        out[int(k["index"])] = d
    return out


class KeyMap:
    def __init__(self, path=KEYMAP_PATH):
        # Validated, size-capped, fail-closed load. Raises KeymapValidationError
        # on any malformed/oversized/malicious input — never trusts the file.
        data = load_keymap(path)
        self.keys = data["keys"]
        self.by_name = {}
        self.by_index = {}
        # Indices whose key TYPE (code1) is the Fn/layer-shift key. The firmware
        # keymap table must keep code1=1 for these or the function layer breaks.
        self.layer_indices = set()
        for k in self.keys:
            idx = int(k["index"])
            hid = k.get("hidCode", "0")
            entry = {"index": idx, "name": k["name"],
                     "hid": int(hid, 16) if isinstance(hid, str) else int(hid or 0),
                     "x": float(k.get("x", 0)), "y": float(k.get("y", 0))}
            self.by_name[k["name"]] = entry
            self.by_index[idx] = entry
            if k.get("code") == "KeyFn":
                self.layer_indices.add(idx)

        # Align device keys to design codes by physical position (row, then col).
        self.code_of_index = {}
        self.index_of_code = {}
        by_code = design_codes_for(self.keys)
        if by_code is not None:
            for idx, code in by_code.items():
                self.code_of_index[idx] = code
                self.index_of_code[code] = idx
        else:
            # Legacy: a layout with a key code we do not know. Positional
            # pairing (only right for the 61-key Win60 order).
            ordered = sorted(self.keys, key=lambda k: (round(float(k["y"]) / 10),
                                                        float(k["x"])))
            for k, code in zip(ordered, DESIGN_CODES):
                idx = int(k["index"])
                self.code_of_index[idx] = code
                self.index_of_code[code] = idx

    def indices(self):
        return [int(k["index"]) for k in self.keys]

    def index_of(self, name):
        e = self.by_name.get(name)
        return e["index"] if e else None

    def name_of(self, index):
        e = self.by_index.get(index)
        return e["name"] if e else None

    def code_of(self, index):
        return self.code_of_index.get(index)

    def indices_for_codes(self, codes):
        return [self.index_of_code[c] for c in codes if c in self.index_of_code]

    def hid_for_code(self, code):
        idx = self.index_of_code.get(code)
        return self.by_index[idx]["hid"] if idx is not None else 0


class LiveReader:
    """Background reader: enables Travel Test and tracks live per-key depth (mm).

    Shares the AulaDevice handle; uses short non-blocking reads under the device
    lock so GUI writes aren't starved.
    """
    def __init__(self, device, keymap, indices=None):
        self.dev = device
        self.km = keymap
        self.indices = list(indices or keymap.indices())
        self.depths = {}          # code -> mm   (bounded: one entry per key)
        self._depths_idx = {}     # device index -> mm, same data for the
                                  # effect engine (skips a per-frame code->index
                                  # remap of the whole snapshot at 60 fps)
        # The firmware's travel-test stream is event-driven on depth change.
        # A key held at constant depth produces no further reports, so any
        # time-based "haven't heard from this key in N ms → released" rule
        # makes held keys vanish from the UI. Instead we trust the firmware's
        # next report: cache the last reported depth and clear an entry when a
        # fresh report arrives at or below the firmware's noise floor.
        self.NOISE_MM = 0.05
        # ...but on release the firmware usually stops reporting MID-TRAVEL
        # (last frame 0.07-0.98 mm in a WIN 60 HE capture, 2026-11-03) and
        # never sends the ~0 frame, so the rule above alone left released
        # keys stuck partway down. A held key's last report moved DOWN (or was
        # its only one); a released key's last report moved UP. So a key whose
        # last report was upward motion is cleared after this much silence.
        # The firmware's own gap between frames of one moving key reaches
        # ~140 ms, so a shorter window would flicker mid-release.
        self.RELEASE_SILENCE_S = 0.15
        # A quick or light tap often reports only DOWNWARD frames (the gap
        # between frames of one moving key reaches ~140 ms, longer than the
        # tap), so the rule above never fires and the key sticks forever.
        # Such a key is cleared after STALE_S of silence unless the OS says it
        # is still down (`is_key_down(idx)`: True / False / None = unknown ->
        # keep). Held keys stay; a partial press held perfectly flat below the
        # actuation point disappears after STALE_S and returns on the next
        # movement.
        self.STALE_S = 1.0
        self.is_key_down = None
        # A tap that starts and ends between two UI polls (33 ms) would be
        # cleared before anyone saw it. Presses shorter than TAP_HOLD_S stay
        # visible at their peak depth until TAP_HOLD_S after their release.
        self.TAP_HOLD_S = 0.12
        self._flash = {}          # device index -> (code, peak mm, until)
        # Optional per-sample consumer (Api attaches telemetry.Telemetry.feed):
        # called (device index, mm, t) for every mapped travel report and
        # (device index, 0.0, t) when the release-silence rule clears a key.
        # Set it before start(); it runs on this thread, so it must be cheap.
        self.on_sample = None
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        th = self._thread
        if th is not None and th.is_alive():
            if not self._stop.is_set():
                return                      # already running
            # A previous stop() timed out on the join (thread wedged in a
            # read). Give it one more bounded chance to exit before replacing
            # it, so two drains never race on the same handle.
            th.join(timeout=0.5)
            if th.is_alive():
                return
        try:
            self.dev.write(protocol.build_open_trigger_test(self.indices))
        except Exception:
            return
        self._stop = threading.Event()      # per-run flag (never clear() a
                                            # flag an old thread may still poll)
        self._thread = threading.Thread(target=self._run, args=(self._stop,),
                                        daemon=True)
        self._thread.start()

    def _run(self, stop_ev=None):
        if stop_ev is None:
            stop_ev = self._stop
        try:
            with self.dev._lock:
                if self.dev._dev:
                    self.dev._dev.set_nonblocking(True)
        except Exception:
            pass
        # Hoisted out of the hot loop: the re-arm packet is constant, and the
        # index->design-code map is a plain dict lookup (no method call per
        # report; the firmware can stream hundreds of reports a second).
        open_pkt = protocol.build_open_trigger_test(self.indices)
        code_of_index = getattr(self.km, "code_of_index", None)
        code_of = (code_of_index.get if isinstance(code_of_index, dict)
                   else self.km.code_of)
        depths = self.depths
        depths_idx = self._depths_idx
        noise = self.NOISE_MM
        release_silence = self.RELEASE_SILENCE_S
        on_sample = self.on_sample
        lifting = {}   # device index -> (monotonic time of its last report, code)
                       # for keys whose last report moved UP (see __init__)
        seen = {}      # device index -> (time of its last report, code) for
                       # every key with a depth (STALE_S rule)
        pressed = {}   # device index -> (time of its first report, peak mm)
        flash = self._flash
        stale_s = self.STALE_S
        tap_hold = self.TAP_HOLD_S
        is_down = self.is_key_down
        last_stale = 0.0

        def _cleared(idx, code, t):
            first = pressed.pop(idx, None)
            seen.pop(idx, None)
            if first is not None and t - first[0] < tap_hold:
                flash[idx] = (code, first[1], t + tap_hold)
        last_open = 0.0
        dead = 0   # consecutive dead-handle / failed-read cycles (self-teardown)
        while not stop_ev.is_set():
            # Re-arm the travel-test stream periodically. Actuation/dead-band
            # config writes (also cmd 33) can stop the stream, so without this the
            # live depth silently dies a moment after entering the Actuation tab.
            now = time.monotonic()
            if now - last_open > 0.8:
                last_open = now
                try:
                    self.dev.write(open_pkt)
                except Exception:
                    pass
            # Drain the WHOLE hidraw backlog each cycle, keeping only the latest
            # depth per key. The board streams travel reports faster than a
            # one-read-per-loop pace can consume, so reading a single report at a
            # time lags reality — on a quick release the loop is still chewing
            # through stale "pressed" reports and shows a high value instead of 0.
            got = False
            heard = False   # ANY report this pass (a heartbeat reply too)
            try:
                with self.dev._lock:
                    if self.dev._dev is None:
                        # Handle closed (disconnect) — normally _stop is set too,
                        # but self-terminate as a backstop so we never spin
                        # forever on a dead handle.
                        dead += 1
                        if dead > 50:
                            break
                        time.sleep(0.02); continue
                    for _ in range(256):          # bounded drain
                        r = self.dev._dev.read(64)
                        if r:
                            heard = True
                        if not r or len(r) < 11:
                            break
                        # hidapi read includes Report ID at [0]; travel sub-report:
                        # [1]=33, [5]=5, [7]=row, [8]=col -> device index = row*22 +
                        # col (W=46 -> (2,2), confirmed).
                        if r[1] == 33 and r[5] == 5:
                            idx = r[7] * 22 + r[8]
                            depth = (r[9] | (r[10] << 8)) / 100.0
                            code = code_of(idx)   # e.g. "W","LCtrl","1"
                            if code:
                                if depth < noise:
                                    depths.pop(code, None)
                                    depths_idx.pop(idx, None)
                                    lifting.pop(idx, None)
                                    _cleared(idx, code, now)
                                else:
                                    seen[idx] = (now, code)
                                    first = pressed.get(idx)
                                    if first is None:
                                        pressed[idx] = (now, depth)
                                    elif depth > first[1]:
                                        pressed[idx] = (first[0], depth)
                                    prev = depths_idx.get(idx)
                                    if prev is not None and depth < prev:
                                        lifting[idx] = (now, code)
                                    else:
                                        lifting.pop(idx, None)
                                    depths[code] = depth
                                    depths_idx[idx] = depth
                                if on_sample is not None:
                                    try:
                                        on_sample(idx, depth, now)
                                    except Exception:
                                        pass
                                got = True
                dead = 0   # a clean drain -> the handle is alive
            except Exception:
                # Persistent read failure (e.g. mid-stream unplug) -> stop
                # instead of spinning ~20 Hz forever on a dead handle, and
                # tell the device so Api.status() reports the link down.
                dead += 1
                if dead > 50:
                    mark = getattr(self.dev, "mark_dead", None)
                    if mark is not None:
                        try:
                            mark("live reader: reads keep failing")
                        except Exception:
                            pass
                    break
                time.sleep(0.05); continue
            # Released keys whose last report was mid-travel: clear once the
            # stream has stayed silent for them (see RELEASE_SILENCE_S).
            if lifting:
                t_now = time.monotonic()
                for idx, (t_last, code) in list(lifting.items()):
                    if t_now - t_last > release_silence:
                        depths.pop(code, None)
                        depths_idx.pop(idx, None)
                        del lifting[idx]
                        _cleared(idx, code, t_now)
                        if on_sample is not None:
                            try:
                                on_sample(idx, 0.0, t_now)
                            except Exception:
                                pass
            # Keys silent for STALE_S that the OS does not report as down
            # (a tap whose release was never reported). Checked ~4x a second.
            if seen and is_down is not None:
                t_now = time.monotonic()
                if t_now - last_stale > 0.25:
                    last_stale = t_now
                    for idx, (t_last, code) in list(seen.items()):
                        if t_now - t_last <= stale_s:
                            continue
                        try:
                            down = is_down(idx)
                        except Exception:
                            down = None
                        if down is False:
                            depths.pop(code, None)
                            depths_idx.pop(idx, None)
                            lifting.pop(idx, None)
                            pressed.pop(idx, None)
                            seen.pop(idx, None)
                            if on_sample is not None:
                                try:
                                    on_sample(idx, 0.0, t_now)
                                except Exception:
                                    pass
                        else:
                            seen[idx] = (t_now, code)   # re-check in STALE_S
            if flash:
                t_now = time.monotonic()
                for idx, (_c, _mm, until) in list(flash.items()):
                    if t_now > until or idx in depths_idx:
                        flash.pop(idx, None)
            # This reader drains EVERY report off the shared handle (a probe's
            # heartbeat reply included), so it is the one that must record
            # that the board answered (Api.status liveness).
            if heard:
                note = getattr(self.dev, "note_rx", None)
                if note is not None:
                    note()
            # Nothing pending → sleep briefly so we don't busy-spin the lock;
            # when reports are flowing, loop straight back to stay real-time.
            if not got:
                time.sleep(0.002)

    def alive(self):
        """True while the drain thread runs (it self-exits on a dead handle)."""
        th = self._thread
        return th is not None and th.is_alive() and not self._stop.is_set()

    def snapshot(self):
        # Last-reported depth per key. No time-based decay — the firmware
        # stops reporting while a key is held flat, so any decay rule would
        # erase held-key visibility. Release is handled in _run by clearing
        # the cache when a fresh report drops below NOISE_MM.
        # dict(d) copies atomically under the GIL — safe against the reader
        # thread mutating it; iterating d.items() from another thread is NOT.
        out = dict(self.depths)
        if self._flash:
            for code, mm, _until in list(self._flash.values()):
                out.setdefault(code, mm)
        return out

    def snapshot_by_index(self):
        """Same data as snapshot() keyed by DEVICE INDEX — the effect engine's
        native key, so press-reactive effects don't remap every frame."""
        out = dict(self._depths_idx)
        if self._flash:
            for idx, (_code, mm, _until) in list(self._flash.items()):
                out.setdefault(idx, mm)
        return out

    def stop(self):
        self._stop.set()
        th = self._thread
        if th is not None and th is not threading.current_thread():
            th.join(timeout=0.5)
            if not th.is_alive():
                self._thread = None
        self.depths.clear()
        self._depths_idx.clear()
        self._flash.clear()
        try:
            self.dev.write(protocol.build_close_trigger_test())
        except Exception:
            pass


# HID usage -> Windows virtual-key, for the keys a 60/65/68 % board has.
_HID_TO_VK = {
    **{0x04 + i: 0x41 + i for i in range(26)},            # A-Z
    **{0x1E + i: 0x31 + i for i in range(9)}, 0x27: 0x30,  # 1-9, 0
    0x28: 0x0D, 0x29: 0x1B, 0x2A: 0x08, 0x2B: 0x09, 0x2C: 0x20,
    0x2D: 0xBD, 0x2E: 0xBB, 0x2F: 0xDB, 0x30: 0xDD, 0x31: 0xDC,
    0x33: 0xBA, 0x34: 0xDE, 0x35: 0xC0, 0x36: 0xBC, 0x37: 0xBE,
    0x38: 0xBF, 0x39: 0x14,
    **{0x3A + i: 0x70 + i for i in range(12)},            # F1-F12
    0x49: 0x2D, 0x4A: 0x24, 0x4B: 0x21, 0x4C: 0x2E, 0x4D: 0x23, 0x4E: 0x22,
    0x4F: 0x27, 0x50: 0x25, 0x51: 0x28, 0x52: 0x26,
    0xE0: 0xA2, 0xE1: 0xA0, 0xE2: 0xA4, 0xE3: 0x5B,
    0xE4: 0xA3, 0xE5: 0xA1, 0xE6: 0xA5, 0xE7: 0x5C,
}


def make_os_key_probe(keymap, get_state=None):
    """`is_key_down(device index)` for LiveReader's stale rule: True/False
    from the OS key state, None when unknown (no mapping - Fn, a remapped
    key reads as its default - or not Windows). Reads the current up/down
    state only; nothing is recorded. Returns None off Windows."""
    if get_state is None:
        if sys.platform != "win32":
            return None
        import ctypes
        get_state = ctypes.windll.user32.GetAsyncKeyState
    vk_of = {}
    for idx in keymap.indices():
        try:
            vk = _HID_TO_VK.get(int(keymap.by_index[idx]["hid"]))
        except Exception:
            vk = None
        if vk:
            vk_of[idx] = vk

    def is_key_down(idx):
        vk = vk_of.get(idx)
        if vk is None:
            return None
        return bool(get_state(vk) & 0x8000)
    return is_key_down


class CalibrationReader:
    """Reads the firmware's calibration responses during a calibration session.

    While calibration is active the board streams cmd-33 responses; the driver
    decodes them as: hidapi r[1]==33, r[6] in {8,15}, r[7]==1, then bytes r[8:30]
    are a column-major bitmask — bit `b` of byte `c` means device index `b*22 + c`
    has been calibrated. We collect those into a set of design codes so the UI can
    light each key the moment it's calibrated (i.e. on every press).

    r[7] is the session state (vendor a[6]; WebHID strips the report id, so
    vendor a[n] == hidapi r[n+1]): 0 = finished, 1 = progress, 2 or 4 = the
    firmware FAILED the calibration (the vendor driver shows
    alertCalibrationFail and leaves calibration mode for exactly these two)."""

    #: r[7] values with which the firmware ends a session as failed.
    FAIL_CODES = (2, 4)

    def __init__(self, device, keymap, on_change=None):
        self.dev = device
        self.km = keymap
        self.calibrated = set()    # design codes confirmed calibrated
        self.done = False          # firmware signalled calibration complete
        self.failed = False        # session over WITHOUT a normal finish:
                                   # reads kept failing, or the firmware said so
        self.fail_code = None      # the firmware's failure code (2/4), else None
        self.on_change = on_change # called(calibrated_set) when it grows (render LEDs)
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self.calibrated = set()
        self.done = False
        # Reset too, or a retry after a failed run reports the OLD failure.
        self.failed = False
        self.fail_code = None
        self._stop = threading.Event()      # per-run flag (see LiveReader.start)
        self._thread = threading.Thread(target=self._run, args=(self._stop,),
                                        daemon=True)
        self._thread.start()

    def _run(self, stop_ev=None):
        # Sole device owner during calibration. Uses a SHORT blocking read so it
        # parks (releasing the device lock) instead of busy-spinning on it — that
        # busy-spin is what starved writes and froze the UI. Renders LEDs itself,
        # only when the calibrated set changes, so there's no constant traffic.
        if stop_ev is None:
            stop_ev = self._stop
        if self.on_change:
            try:
                self.on_change(self.calibrated)   # initial dim frame
            except Exception:
                pass
        dead = 0   # consecutive failed reads (dead-handle self-teardown)
        # read_soft: a transient read error (the board throws one as it
        # enters calibration) must not close the handle under us.
        read = getattr(self.dev, "read_soft", None) or self.dev.read
        while not stop_ev.is_set():
            try:
                r = read(64, timeout_ms=40)
            except Exception:
                # Handle closed/unplugged (read raises "device not open") — stop
                # instead of spinning forever with done stuck False. ~2.5 s of
                # failures = the link is really gone: tell the device so
                # Api.status() reports it (and the UI ends calibration).
                dead += 1
                if dead > 50:
                    self.failed = True
                    mark = getattr(self.dev, "mark_dead", None)
                    if mark is not None:
                        try:
                            mark("calibration reader: reads keep failing")
                        except Exception:
                            pass
                    break
                time.sleep(0.05); continue
            dead = 0
            if not r or len(r) < 30:
                continue
            if r[1] == 33 and r[6] in (8, 15):
                if r[7] == 1:
                    before = len(self.calibrated)
                    mask = r[8:30]                 # 22 bytes, one per column
                    for col, byte in enumerate(mask):
                        for bit in range(6):       # 6 rows
                            if (byte >> bit) & 1:
                                code = self.km.code_of(bit * 22 + col)
                                if code:
                                    self.calibrated.add(code)
                    if len(self.calibrated) != before and self.on_change:
                        try:
                            self.on_change(self.calibrated)
                        except Exception:
                            pass
                elif r[7] == 0:                    # firmware: calibration complete
                    self.done = True
                elif r[7] in self.FAIL_CODES and not self.done:
                    # (Not after `done`: the session already completed, and a
                    # late frame carrying 2/4 must not turn that success into
                    # "aborted" - the loop keeps draining until it is stopped.)
                    # The firmware gave up on the session. This used to be
                    # ignored, so `done` never came and the UI waited on a
                    # session the board had already abandoned. Not `done`:
                    # the keys are NOT calibrated. Api.read_calibrated turns
                    # `failed` into `aborted`, which ends the UI's session.
                    self.failed = True
                    self.fail_code = r[7]
                    break

    def snapshot(self):
        return sorted(self.calibrated)

    def stop(self):
        self._stop.set()
        th = self._thread
        if th is not None and th is not threading.current_thread():
            th.join(timeout=0.5)
        self._thread = None


# The old module-level read_actuation() sweep was removed: it filtered on raw
# r[5] == 5 (the payload LENGTH byte — 0x0c on the real readTriggerData reply,
# 5 only on a live travel-test frame) and decoded travel at the stream-frame
# offsets, so it never saw a config reply and could book live depth as the
# stored actuation. The working read-back is Win60Driver.read_trigger_config
# / read_actuation (protocol.parse_trigger_config, CONFIRMED-BY-CAPTURE).
