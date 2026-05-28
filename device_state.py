"""Read real keyboard state: key-index map, per-key actuation, live travel.

Key layout comes from the driver's config (config/keys/<product>.json, bundled as
ui/keymap.json): each key has index, name, code, hidCode, and x/y position. The
device protocol (protocol.py) is used to read per-key trigger values and to
stream live travel after enabling Travel Test.
"""
import json
import os
import threading
import time

import protocol

HERE = os.path.dirname(os.path.abspath(__file__))
KEYMAP_PATH = os.path.join(HERE, "ui", "keymap.json")

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
        data = json.load(open(path))
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
    """
    def __init__(self, device, keymap, indices=None):
        self.dev = device
        self.km = keymap
        self.indices = list(indices or keymap.indices())
        self.depths = {}          # code -> mm
        # Timestamp of the most recent report for each code. Used to decay
        # stale readings to 0: on a fast key release the firmware sometimes
        # stops reporting before the depth reaches zero, leaving the cached
        # value stuck high. If we don't hear from a key for STALE_S we treat
        # it as released. 35 ms is short enough to catch a fast release
        # (humans can release within ~50 ms) and long enough that ordinary
        # poll-rate gaps at 8 kHz don't trigger false zeros.
        self._last_seen = {}
        self.STALE_S = 0.035
        self._stop = threading.Event()
        self._thread = None

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
        try:
            with self.dev._lock:
                if self.dev._dev:
                    self.dev._dev.set_nonblocking(True)
        except Exception:
            pass
        last_open = 0.0
        while not self._stop.is_set():
            # Re-arm the travel-test stream periodically. Actuation/dead-band
            # config writes (also cmd 33) can stop the stream, so without this the
            # live depth silently dies a moment after entering the Actuation tab.
            now = time.time()
            if now - last_open > 0.8:
                last_open = now
                try:
                    self.dev.write(protocol.build_open_trigger_test(self.indices))
                except Exception:
                    pass
            # Drain the WHOLE hidraw backlog each cycle, keeping only the latest
            # depth per key. The board streams travel reports faster than a
            # one-read-per-loop pace can consume, so reading a single report at a
            # time lags reality — on a quick release the loop is still chewing
            # through stale "pressed" reports and shows a high value instead of 0.
            got = False
            try:
                with self.dev._lock:
                    if not self.dev._dev:
                        time.sleep(0.02); continue
                    for _ in range(256):          # bounded drain
                        r = self.dev._dev.read(64)
                        if not r or len(r) < 11:
                            break
                        # hidapi read includes Report ID at [0]; travel sub-report:
                        # [1]=33, [5]=5, [7]=row, [8]=col -> device index = row*22 +
                        # col (W=46 -> (2,2), confirmed).
                        if r[1] == 33 and r[5] == 5:
                            idx = r[7] * 22 + r[8]
                            depth = (r[9] | (r[10] << 8)) / 100.0
                            code = self.km.code_of(idx)   # e.g. "W","LCtrl","1"
                            if code:
                                self.depths[code] = depth
                                self._last_seen[code] = time.time()
                                got = True
            except Exception:
                time.sleep(0.05); continue
            # Nothing pending → sleep briefly so we don't busy-spin the lock;
            # when reports are flowing, loop straight back to stay real-time.
            if not got:
                time.sleep(0.002)

    def snapshot(self):
        # Decay stale readings to 0. A fast release can outrun the firmware's
        # report cadence, so a key whose last report was longer than STALE_S
        # ago is treated as released — this keeps the depth indicator from
        # being stuck high after a quick keypress. ALSO snap to 0 (and clear
        # the cached depth) once we treat it as released, so the very next
        # report — even if it lands inside STALE_S — can't reintroduce the
        # stale value (the firmware sometimes emits a single trailing
        # "still pressed" packet a fraction of a second after a fast release).
        now = time.time()
        out = {}
        stale_keys = []
        for code, mm in self.depths.items():
            if (now - self._last_seen.get(code, 0.0)) > self.STALE_S:
                out[code] = 0.0
                stale_keys.append(code)
            else:
                out[code] = mm
        for code in stale_keys:
            self.depths[code] = 0.0
        return out

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
        while not self._stop.is_set():
            try:
                r = self.dev.read(64, timeout_ms=40)
            except Exception:
                time.sleep(0.05); continue
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
    device._dev.set_nonblocking(True)
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
            r = device._dev.read(64)
            if r and r[1] == 33 and r[5] == 5:
                parsed = protocol.parse_trigger_read(bytes(r[1:]))
                out[k["name"]] = round(parsed["travel"] / 100.0, 2)
                break
            time.sleep(0.001)
    return out
