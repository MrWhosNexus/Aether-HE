"""Read real keyboard state: key-index map, per-key actuation, live travel.

Key layout comes from the driver's config (config/keys/<product>.json, bundled as
ui/keymap.json): each key has index, name, code, hidCode, and x/y position. The
device protocol (protocol.py) is used to read per-key trigger values and to
stream live travel after enabling Travel Test.
"""
import logging
import os
import sys
import threading
import time

import protocol

log = logging.getLogger(__name__)

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
        ordered = sorted(self.keys, key=lambda k: (round(float(k["y"]) / 10),
                                                    float(k["x"])))
        self.code_of_index = {}
        self.index_of_code = {}
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

    The firmware streams two report subtypes on cmd 33:
      - **subtype 5**: travel in 0.01 mm — event-driven, **never sends 0.0** on
        release (the root cause of stuck axes).
      - **subtype 3**: raw ADC — event-driven, **does send 0** on release.

    When subtype 3 raw_adc == 0 the key is **immediately released** (popped from
    depths + added to `_released`).  Subtype 5 reports for a released key are
    ignored until a non-zero subtype 3 signals a fresh press, so stale subtype 5
    values can't re-stick the axis.

    A **close+open cycle** (sub 3 → sub 2) runs every 200 ms to keep the stream
    alive.  *snapshot()* still uses a **1 s absolute timeout** as a second-layer
    safety net (no held key can stay event-silent that long).
    """
    def __init__(self, device, keymap, indices=None):
        self.dev = device
        self.km = keymap
        self.indices = list(indices or keymap.indices())
        self.depths = {}          # code -> mm
        self._last_update = {}    # code -> time.monotonic() (incl. close-refresh)
        self._last_stream = {}   # code -> time.monotonic() (real reports only)
        self._trend = {}          # code -> +1 (rising) / -1 (falling) / 0
        self.STUCK_SILENCE_S = 3.0  # remove if trend==-1 and no stream for this long
        self.NOISE_MM = 0.05
        self._depth_lock = threading.Lock()   # guards mutations of self.depths
        self._stop = threading.Event()
        self._thread = None
        self._released = set()     # codes whose release was confirmed by subtype 3 raw_adc=0

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        try:
            self.dev.write(protocol.build_open_trigger_test(self.indices))
        except Exception:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        import traceback
        log.debug("READER thread started")
        try:
            with self.dev._lock:
                if self.dev._dev:
                    self.dev._dev.set_nonblocking(True)
        except Exception as ex:
            log.warning("READER set_nonblocking failed: %s", ex)
        last_cycle = 0.0
        dead = 0   # consecutive dead-handle / failed-read cycles (self-teardown)
        while not self._stop.is_set():
            now = time.time()
            got = False
            updates = {}
            liveness = set()  # codes with subtype-3 non-zero this cycle → force trend=+1
            if now - last_cycle > 0.2:
                last_cycle = now
                # Drain pending sensor readings without stopping the stream
                # so the firmware never misses a subtype-3 raw_adc frame.
                close_reported = set()
                with self.dev._lock:
                    if self.dev._dev:
                        for _ in range(256):
                            r = self.dev._dev.read(64)
                            if not r or len(r) < 11:
                                break
                            if r[1] == 33 and r[5] in (3, 5):
                                idx = r[7] * 22 + r[8]
                                val16 = r[9] | (r[10] << 8)
                                code = self.km.code_of(idx)
                                if not code:
                                    continue
                                if r[5] == 3 and val16 == 0:
                                    if code not in self._released:
                                        # Pre-commit any pending depth so the press
                                        # is captured before release removes it.
                                        if code in updates and updates[code] >= self.NOISE_MM:
                                            with self._depth_lock:
                                                self.depths[code] = updates[code]
                                                self._last_stream[code] = time.monotonic()
                                                self._last_update[code] = time.monotonic()
                                        self._released.add(code)
                                        with self._depth_lock:
                                            self.depths.pop(code, None)
                                            self._last_update.pop(code, None)
                                            self._last_stream.pop(code, None)
                                            self._trend.pop(code, None)
                                        log.debug("subtype3 release code=%s", code)
                                    close_reported.discard(code)
                                    continue
                                if code in self._released:
                                    self._released.discard(code)  # any report = fresh press
                                depth = val16 / 100.0
                                updates[code] = depth
                                close_reported.add(code)
                                got = True
                                if r[5] == 3:
                                    liveness.add(code)
                # ── close-cycle drain ─────────────────────────────────
                # Keys confirmed released (subtype-3 raw_adc=0 → _released)
                # are removed unconditionally.
                # Missing keys with trend=-1 + long silence are stuck → remove.
                # Everything else gets a timer-refresh so shallow keys that
                # happen to skip this batch don't oscillate in/out of depths.
                with self._depth_lock:
                    mono = time.monotonic()
                    for code in list(self.depths.keys()):
                        if code not in close_reported:
                            if code in self._released:
                                log.debug("close-drain remove released code=%s", code)
                                self.depths.pop(code, None)
                                self._last_update.pop(code, None)
                                self._last_stream.pop(code, None)
                                self._trend.pop(code, None)
                            elif (self._trend.get(code, 0) == -1
                                  and (mono - self._last_stream.get(code, mono))
                                      > self.STUCK_SILENCE_S):
                                log.debug("close-drain remove stuck code=%s (trend=-1)", code)
                                self.depths.pop(code, None)
                                self._last_update.pop(code, None)
                                self._last_stream.pop(code, None)
                                self._trend.pop(code, None)
                            else:
                                self._last_update[code] = mono  # timer-refresh
                log.debug("close-drain reported %d keys; depths after=%s",
                          len(close_reported), {k: round(v, 2) for k, v in self.depths.items()})
                try:
                    self.dev.write(protocol.build_open_trigger_test(self.indices))
                except Exception:
                    pass
            try:
                with self.dev._lock:
                    if self.dev._dev is None:
                        dead += 1
                        if dead > 50:
                            break
                        time.sleep(0.02); continue
                    for _ in range(256):
                        r = self.dev._dev.read(64)
                        if not r or len(r) < 11:
                            break
                        if r[1] == 33 and r[5] in (3, 5):
                            idx = r[7] * 22 + r[8]
                            val16 = r[9] | (r[10] << 8)
                            code = self.km.code_of(idx)
                            if not code:
                                continue
                            if r[5] == 3 and val16 == 0:
                                if code not in self._released:
                                    # Pre-commit any pending depth before removal
                                    if code in updates and updates[code] >= self.NOISE_MM:
                                        with self._depth_lock:
                                            self.depths[code] = updates[code]
                                            self._last_stream[code] = time.monotonic()
                                            self._last_update[code] = time.monotonic()
                                    self._released.add(code)
                                    with self._depth_lock:
                                        self.depths.pop(code, None)
                                        self._last_update.pop(code, None)
                                        self._last_stream.pop(code, None)
                                        self._trend.pop(code, None)
                                    log.debug("subtype3 release code=%s", code)
                                continue
                            if code in self._released:
                                self._released.discard(code)  # any report = fresh press
                            depth = val16 / 100.0
                            updates[code] = depth
                            got = True
                            if r[5] == 3:
                                liveness.add(code)
                if updates:
                    with self._depth_lock:
                        mono = time.monotonic()
                        for code, depth in updates.items():
                            if code in self._released:
                                continue  # stale depth for released key
                            if depth < self.NOISE_MM:
                                self.depths.pop(code, None)
                                self._last_update.pop(code, None)
                                self._last_stream.pop(code, None)
                                self._trend.pop(code, None)
                            else:
                                if code in liveness:
                                    self._trend[code] = +1
                                else:
                                    prev = self.depths.get(code)
                                    trend = -1 if (prev is not None and depth < prev) else +1
                                    self._trend[code] = trend
                                self.depths[code] = depth
                                self._last_update[code] = mono
                                self._last_stream[code] = mono
                dead = 0
                if len(self.depths) > 0 or len(self._released) > 0:
                    log.debug("reader state: depths=%s released=%s trend=%s",
                              {k: round(v, 2) for k, v in self.depths.items()},
                              list(self._released),
                              {k: v for k, v in self._trend.items() if k in self.depths})
            except Exception:
                dead += 1
                if dead >= 50:
                    log.warning("READER thread exits after %d consecutive failures", dead)
                    break
                if dead == 1 or dead % 10 == 0:
                    log.debug("READER read failure #%d", dead)
                time.sleep(0.05); continue
            if not got:
                time.sleep(0.002)

    def snapshot(self):
        with self._depth_lock:
            if not self.depths:
                log.debug("snapshot: depths empty")
                return {}
            now = time.monotonic()
            result = {}
            for code, mm in list(self.depths.items()):
                if mm < self.NOISE_MM:
                    self.depths.pop(code, None)
                    self._last_update.pop(code, None)
                    self._last_stream.pop(code, None)
                    self._trend.pop(code, None)
                    continue
                if (self._trend.get(code, 0) == -1
                        and (now - self._last_stream.get(code, now))
                            > self.STUCK_SILENCE_S):
                    log.debug("snapshot removing stuck code=%s (trend=-1, silence=%.1fs)",
                              code, now - self._last_stream.get(code, now))
                    self.depths.pop(code, None)
                    self._last_update.pop(code, None)
                    self._last_stream.pop(code, None)
                    self._trend.pop(code, None)
                    continue
                if now - self._last_update.get(code, 0) < 1.0:
                    result[code] = mm
            return result

    def is_alive(self):
        return self._thread is not None and self._thread.is_alive()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=0.5)
        try:
            self.dev.write(protocol.build_close_trigger_test())
        except Exception:
            pass


class CalibrationReader:
    """Reads the firmware's calibration responses during a calibration session.

    While calibration is active the board streams cmd-33 responses; the driver
    decodes them as: hidapi r[1]==33, r[6] in {8,15}, r[7]==1, then bytes r[8:30]
    are a column-major bitmask — bit `b` of byte `c` means device index `b*22 + c`
    has been calibrated. We collect those into a set of design codes so the UI can
    light each key the moment it's calibrated (i.e. on every press)."""
    def __init__(self, device, keymap, on_change=None):
        self.dev = device
        self.km = keymap
        self.calibrated = set()    # design codes confirmed calibrated
        self.done = False          # firmware signalled calibration complete
        self.on_change = on_change # called(calibrated_set) when it grows (render LEDs)
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self.calibrated = set()
        self.done = False
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        # Sole device owner during calibration. Uses a SHORT blocking read so it
        # parks (releasing the device lock) instead of busy-spinning on it — that
        # busy-spin is what starved writes and froze the UI. Renders LEDs itself,
        # only when the calibrated set changes, so there's no constant traffic.
        if self.on_change:
            try:
                self.on_change(self.calibrated)   # initial dim frame
            except Exception:
                pass
        dead = 0   # consecutive failed reads (dead-handle self-teardown)
        while not self._stop.is_set():
            try:
                r = self.dev.read(64, timeout_ms=40)
            except Exception:
                # Handle closed/unplugged (read raises "device not open") — stop
                # instead of spinning forever with done stuck False.
                dead += 1
                if dead > 50:
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

    def snapshot(self):
        return sorted(self.calibrated)

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=0.5)
        self._thread = None


def read_actuation(device, keymap):
    """Read each key's current actuation (travel mm) via cmd33/sub5. Returns
    {name: mm}. Best-effort; blocks briefly per key."""
    out = {}
    # All handle access goes through the inner-lock-guarded AulaDevice methods
    # (never device._dev directly) so reads can't tear against a reader thread.
    device.set_nonblocking(True)
    for k in keymap.keys:
        idx = int(k["index"])
        rq = [0] * 63
        rq[0] = 33; rq[4] = 24; rq[5] = 5; rq[6] = idx // 22; rq[7] = idx % 22
        try:
            device.write([protocol.REPORT_ID] + rq)
        except Exception:
            break
        t = time.time()
        while (time.time() - t) < 0.04:
            r = device.read(64, timeout_ms=0)
            if r and r[1] == 33 and r[5] == 5:
                parsed = protocol.parse_trigger_read(bytes(r[1:]))
                out[k["name"]] = round(parsed["travel"] / 100.0, 2)
                break
            time.sleep(0.001)
    return out
