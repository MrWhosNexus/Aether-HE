"""SOCD (PRCS) and calibration must match the vendor driver's own encoding.

Spec source: the deobfuscated hed.aulacn.com driver. Vendor code is never
committed (NOTICE.md), so the tests that read it look in the local-only
locations and SKIP when it is absent; the committed evidence they fall back on
is the vendor-driver capture docs/context/hed-aulacn-raw/webhid-capture-win60.json.
Indices in the vendor source are WebHID, which strips the report ID, so vendor
a[n] == hidapi r[n+1].

Ported from the macOS branch and re-pointed at upstream's code where upstream
had already fixed the same defect differently (noted per test).

SOCD — setPrcsData(), agreement.deobf.js:
    a[0]=0x24  a[1]=0x00  a[2..3]=page  a[4]=0x28(40)
    per entry j: a[4j+5]=1, a[4j+6]=model, a[4j+7]=key1.hidCode, a[4j+8]=key2.hidCode
    setPrcsPower(on): a[0]=0x24 a[1]=0x03 a[4]=0x01 a[5]=on
  and wmIndex.deobf.js maps the UI radios prcsModel1..4 to model 0,1,2,3 —
  ZERO-based. Aether shipped the 1-based label straight to the wire, so every
  mode was shifted and "Model 4" was an unimplemented value. That is the
  "SOCD not working" bug.

Calibration — agreement.deobf.js, a[0]=0x21 and a[5] in {8,15}:
    a[6]==0        -> success / stopped
    a[6]==1        -> progress, bitmask a[7:29] (22 bytes), idx = 22*bit + col
    a[6]==2 or 4   -> alertCalibrationFail
  Aether handled 0 and 1 but ignored 2/4, so a failed calibration never ended.

Run: python -m pytest tests/test_vendor_spec_socd_calibration.py
"""
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import device_state
import protocol

import json


def _vendor_source(name):
    """A deobfuscated vendor file, or skip: it is local-only research material."""
    for base in (os.path.join(ROOT, "docs", "context", "hed-aulacn-raw", "driver_deobf"),
                 os.path.join(ROOT, "research", "vendor-reference", "driver_deobf"),
                 os.environ.get("AETHER_VENDOR_DEOBF", "")):
        path = os.path.join(base, name) if base else ""
        if path and os.path.exists(path):
            with open(path, encoding="utf-8", errors="replace") as f:
                return f.read()
    pytest.skip(f"vendor source {name} is not in this checkout (local-only, see NOTICE.md)")


CAPTURE = os.path.join(ROOT, "docs", "context", "hed-aulacn-raw",
                       "webhid-capture-win60.json")
APP_JSX = os.path.join(ROOT, "ui", "runtime_src", "src", "app.jsx")


# ------------------------------------------------- SOCD wire format
def test_prcs_power_matches_vendor():
    """setPrcsPower: a[0]=0x24 a[1]=3 a[4]=1 a[5]=on."""
    on = protocol.build_prcs_power(True)
    off = protocol.build_prcs_power(False)
    # hidapi frame: [report_id, cmd, ...] so body index n == vendor a[n].
    assert on[1] == 0x24 and on[2] == 3 and on[5] == 1 and on[6] == 1
    assert off[6] == 0


def test_prcs_data_header_matches_vendor():
    pkts = protocol.build_prcs([])
    assert len(pkts) == 2, "vendor sends exactly 2 pages (10 entries each)"
    for page, p in enumerate(pkts):
        assert p[1] == 0x24
        assert p[2] == 0x00          # a[1] = 0 -> write data
        assert p[3] == (page >> 8) & 0xFF
        assert p[4] == page & 0xFF
        assert p[5] == 40            # a[4] = 0x28


def test_prcs_entry_layout_matches_vendor():
    pairs = [{"model": 0, "key1_hid": 0x04, "key2_hid": 0x07}]   # A + D
    p = protocol.build_prcs(pairs)[0]
    # vendor a[4j+5..8] -> hidapi p[4j+6..9] for j=0
    assert p[6] == 1, "enable flag"
    assert p[7] == 0, "model (zero-based)"
    assert p[8] == 0x04, "key1 hidCode"
    assert p[9] == 0x07, "key2 hidCode"


def test_twenty_pairs_fit_and_the_twentyfirst_is_refused():
    """Upstream refuses a 21st pair (ValueError) where the Mac branch dropped
    it silently; refusing is the better of the two, so that is what is pinned."""
    pairs = [{"model": 0, "key1_hid": 4, "key2_hid": 7} for _ in range(20)]
    pkts = protocol.build_prcs(pairs)
    assert len(pkts) == 2
    # last entry of page 1 = index 19
    assert pkts[1][4 * 9 + 6] == 1
    with pytest.raises(ValueError):
        protocol.build_prcs(pairs + [pairs[0]])


# ------------------------------------------- SOCD model is ZERO-based
def test_vendor_model_enum_is_zero_based():
    """Read it out of the vendor source so the claim can't rot silently."""
    src = _vendor_source("wmIndex.deobf.js")
    # prcsModel2 -> 0x1 is the unambiguous, un-minified anchor in that file.
    assert re.search(r"prcsModel2'===\S{0,40}\['id'\]&&\(curPrcs\[\S+\]=0x1\)", src), \
        "vendor no longer maps prcsModel2 -> 1; re-derive the SOCD model enum"


def test_vendor_capture_writes_model2_as_wire_value_1():
    """The committed evidence: the vendor driver, with "Model2" picked for
    A + D, wrote the entry `01 01 04 07` — and build_prcs reproduces that
    frame byte for byte from model=1."""
    with open(CAPTURE, encoding="utf-8") as f:
        frames = json.load(f)["frames"]
    mark = next(i for i, fr in enumerate(frames)
                if fr.get("dir") == "MARK"
                and fr.get("label") == "PRCS/SOCD: Apply pair A + D with Model2")
    wrote = next(fr for fr in frames[mark:]
                 if fr.get("dir") == "OUT" and fr.get("hex", "").startswith("24 00 00 00 28"))
    body = [int(x, 16) for x in wrote["hex"].split()]
    assert body[5:9] == [1, 1, 0x04, 0x07], "enable, model, key1 (A), key2 (D)"
    ours = protocol.build_prcs([{"model": 1, "key1_hid": 0x04, "key2_hid": 0x07}])[0]
    assert list(ours[1:1 + len(body)]) == body


def test_ui_sends_the_model_number_and_leaves_the_wire_byte_to_the_driver():
    """The UI shows, stores and SENDS 'Model 1'..'Model 4'. Only the Win60
    driver knows its frame is zero-based; a conversion in the shared UI also
    reached the MINI 60 (which raises on 0) and the magnet board (which sent
    it straight to the keyboard)."""
    src = open(APP_JSX, encoding="utf-8").read()
    assert "model: socdModelOf(p.mode)" in src
    assert "socdWireModel" not in src and "wireModel" not in src


def test_ui_does_not_default_the_mode_with_or():
    """`p.mode || 1` sent the label verbatim and turned a real 0 into 1."""
    src = open(APP_JSX, encoding="utf-8").read()
    assert "p.mode || 1" not in src


def _win60_api():
    import threading

    import app_web
    from drivers import Win60Driver
    from test_keyboard_review import ReadableDevice

    a = app_web.Api.__new__(app_web.Api)
    a._lock = threading.RLock()
    a.km = device_state.KeyMap()
    a.dev = ReadableDevice()
    a.driver = Win60Driver(None, a.dev, a._lock)
    return a


@pytest.mark.parametrize("bad", [-1, 0, 5, 99])
def test_api_refuses_out_of_range_model(bad):
    """The bridge takes the model NUMBER 1..4. Wire 4 was reaching the
    firmware, which accepts and ignores it. The range belongs to the Win60
    (other boards' set_socd take their own byte), so Win60Driver enforces it
    and NOTHING is written."""
    api = _win60_api()
    r = api.set_socd([{"model": bad, "key1": "A", "key2": "D"}])
    assert r["ok"] is False and "out of range" in r["error"]
    assert api.dev.writes == [], "a refused model must not put a frame on the wire"


@pytest.mark.parametrize("number", [1, 2, 3, 4])
def test_win60_writes_model_number_minus_one(number):
    api = _win60_api()
    r = api.set_socd([{"model": number, "key1": "A", "key2": "D"}])
    assert r["ok"] is True
    data = [w for w in api.dev.writes if w[1] == 0x24 and w[2] == 0x00]
    assert data and data[0][6] == 1 and data[0][7] == number - 1


def test_win60_model_2_reproduces_the_vendor_capture():
    """End to end from the bridge: 'Model 2' for A + D is `01 01 04 07`."""
    api = _win60_api()
    assert api.set_socd([{"model": 2, "key1": "A", "key2": "D"}])["ok"]
    data = [w for w in api.dev.writes if w[1] == 0x24 and w[2] == 0x00]
    assert list(data[0][6:10]) == [1, 1, 0x04, 0x07]


def test_game_switch_spec_defaults_to_model_1_and_keeps_the_number():
    import app_web
    a = app_web.Api.__new__(app_web.Api)
    spec = a._board_spec({"socd": [{"key1": "A", "key2": "D"},
                                   {"key1": "W", "key2": "S", "model": 4}]})
    assert [p["model"] for p in spec["socd"]] == [1, 4]


# ------------------- the numbering must not leak into other boards' drivers
def _socd_api(driver):
    import threading

    import app_web
    a = app_web.Api.__new__(app_web.Api)
    a._lock = threading.RLock()
    a.km = device_state.KeyMap()
    a.driver = driver
    return a


@pytest.mark.parametrize("number", [1, 2, 3, 4])
def test_magnet_receives_the_model_number_unchanged(number):
    """drivers/magnet.py passes `model` straight into the frame. It got 1..4
    before the Win60 fix and must still: a zero-based value shifted it."""
    import protocol_magnet as pm
    from drivers.magnet import MagnetDriver

    sent = []
    d = MagnetDriver.__new__(MagnetDriver)
    d.experimental = True
    d._send_all = lambda frames: sent.extend(frames)
    d._require_experimental = lambda feature: None
    api = _socd_api(d)
    assert api.set_socd([{"model": number, "key1": "A", "key2": "D"}])["ok"]
    assert sent == [pm.build_socd(0x04, 0x07, number)]


@pytest.mark.parametrize("number", [1, 2, 3, 4])
def test_mini60_record_takes_every_model_number(number):
    """protocol_mini60 raises on 0 (SOCD_MODES_KNOWN = 1..4): every value the
    UI can send must be one it accepts, unchanged."""
    import protocol_mini60 as p60
    assert p60.key_record_socd(0x04, 0x07, number)[1] == number
    with pytest.raises(ValueError):
        p60.key_record_socd(0x04, 0x07, 0)


def test_mini60_never_took_a_model_from_the_bridge():
    """Why the profile renumbering may assume a Win60: the MINI 60 driver
    refuses the bridge's pairs outright (no key-table index), so no saved
    model was ever written to that board through set_socd."""
    import threading

    import boards
    from drivers.mini60 import Mini60Driver
    from test_keyboard_review import ReadableDevice
    dev = ReadableDevice()
    d = Mini60Driver(boards.load_registry().by_slug("aula-mini60he-pro"), dev,
                     threading.RLock())
    api = _socd_api(d)
    r = api.set_socd([{"model": 1, "key1": "A", "key2": "D"}])
    assert r["ok"] is False and "key1_index" in r["error"]
    assert dev.writes == []


# --------------------------------------------------- calibration
class _FakeDev:
    """Feeds the reader a fixed frame list, then stops its loop.

    The stop event must be set from INSIDE read(), after the frames are
    delivered — setting it beforehand means `while not self._stop.is_set()`
    never runs a single iteration and every assertion trivially fails.
    """
    def __init__(self, frames, stop=None):
        self.frames = list(frames)
        self.stop = stop

    def read(self, n, timeout_ms=0):
        if self.frames:
            return self.frames.pop(0)
        if self.stop is not None:
            self.stop.set()
        return []


class _FakeKM:
    keys = []

    def code_of(self, idx):
        return f"k{idx}"


def _frame(sub, state, tail=()):
    """hidapi frame: r[1]=33, r[6]=sub(8|15), r[7]=state."""
    r = [0] * 64
    r[1] = 33
    r[6] = sub
    r[7] = state
    for i, b in enumerate(tail):
        r[8 + i] = b
    return r


def _run(frames):
    rd = device_state.CalibrationReader(None, _FakeKM())
    rd.dev = _FakeDev(frames, rd._stop)
    rd._run()
    return rd


def _api_with(reader):
    import app_web
    api = app_web.Api.__new__(app_web.Api)
    api.calib_reader = reader
    api._calib_aborted = None
    return api


@pytest.mark.parametrize("sub", [8, 15])
@pytest.mark.parametrize("code", [2, 4])
def test_failure_codes_are_terminal(sub, code):
    """The regression: 2 and 4 were ignored, so the session never ended.

    Upstream ends a session without the firmware's done signal through
    `failed` -> read_calibrated()["aborted"], which the UI already turns into
    a notice + stop. A firmware failure takes that same path (the Mac branch
    set done=True as well; `done` stays False here so a failure can never be
    read as a completed calibration)."""
    tail = [0] * 22
    tail[3] = 1
    # A frame AFTER the failure must not be read: the session is over.
    rd = _run([_frame(sub, code), _frame(sub, 1, tail)])
    assert rd.failed is True, "calibration failure was ignored"
    assert rd.fail_code == code
    assert rd.done is False, "a failed session is not a completed one"
    assert rd.calibrated == set(), "kept reading after the firmware gave up"

    r = _api_with(rd).read_calibrated()
    assert r["done"] is False and r["fail_code"] == code
    assert "calibration failed" in r["aborted"] and str(code) in r["aborted"]


@pytest.mark.parametrize("sub", [8, 15])
@pytest.mark.parametrize("code", [2, 4])
def test_a_fail_code_after_done_does_not_undo_a_completed_calibration(sub, code):
    """The reader keeps draining after `done` until the Api stops it. A frame
    with 2/4 in that window used to set `failed`, and read_calibrated then
    reported a finished calibration as aborted."""
    tail = [0] * 22
    tail[3] = 1
    rd = _run([_frame(sub, 1, tail), _frame(sub, 0), _frame(sub, code)])
    assert rd.done is True
    assert rd.failed is False and rd.fail_code is None
    assert rd.calibrated == {"k3"}
    r = _api_with(rd).read_calibrated()
    assert r["done"] is True
    assert "aborted" not in r and "fail_code" not in r


def test_done_after_a_failure_does_not_revive_the_session():
    rd = _run([_frame(8, 2), _frame(8, 0)])
    assert rd.failed is True and rd.fail_code == 2 and rd.done is False


def test_link_loss_is_not_reported_as_a_firmware_failure():
    """`failed` without a code is upstream's 'reads keep failing' case."""
    rd = device_state.CalibrationReader(None, _FakeKM())
    rd.failed = True
    r = _api_with(rd).read_calibrated()
    assert r["aborted"] == "the keyboard stopped answering"
    assert "fail_code" not in r


@pytest.mark.parametrize("sub", [8, 15])
def test_success_is_not_reported_as_failure(sub):
    rd = _run([_frame(sub, 0)])
    assert rd.done is True and rd.failed is False


def test_progress_bitmask_matches_vendor_indexing():
    """vendor: idx = 22*bit + col over a[7:29] -> hidapi r[8:30]."""
    tail = [0] * 22
    tail[3] = 0b000101          # col 3, bits 0 and 2 -> idx 3 and 47
    rd = _run([_frame(8, 1, tail)])
    assert rd.calibrated == {"k3", "k47"}
    assert rd.failed is False and rd.done is False


def test_retry_clears_a_previous_failure():
    rd = device_state.CalibrationReader(_FakeDev([]), _FakeKM())
    rd.failed = True
    rd.fail_code = 2
    rd.done = True
    rd._stop.set()
    rd.start()                 # start() must reset, or the retry reports stale state
    assert rd.failed is False and rd.fail_code is None and rd.done is False


def test_vendor_source_still_declares_these_failure_codes():
    """If the vendor changes its codes, this test should be what tells us."""
    src = _vendor_source("agreement.deobf.js")
    assert "alertCalibrationFail" in src
    assert re.search(r"0x2===\S{0,20}\[0x6\]\|\|0x4===\S{0,20}\[0x6\]", src), \
        "vendor no longer uses 2/4 as calibration failure codes"


# ------------------------------------------- calibration WRITE path
# reviseKeys(sub, arg) in agreement.deobf.js:
#     a[0]=0x21  a[4]=0x18(24)  a[5]=sub  a[6]=arg
# call sites in wmIndex.deobf.js:
#     start all-key (0x08,0)   stop all-key (0x08,1)
#     start any-key (0x0f,0)   stop any-key (0x10,0)
# The any-key STOP uses a different subcommand from its start — an asymmetry
# that is easy to "tidy" into 0x0f/1 and thereby leave the board calibrating.
@pytest.mark.parametrize("start,any_key,sub,arg", [
    (True,  False, 8,  0),
    (False, False, 8,  1),
    (True,  True,  15, 0),
    (False, True,  16, 0),
])
def test_calibration_frame_matches_vendor(start, any_key, sub, arg):
    f = protocol.build_calibration(start, any_key)
    assert f[1] == 0x21, "cmd"
    assert f[5] == 24, "a[4] length/marker byte"
    assert f[6] == sub, "subcommand"
    assert f[7] == arg, "argument"


def test_any_key_stop_is_not_the_same_subcommand_as_its_start():
    """Guard the asymmetry explicitly: 0x10 stop vs 0x0f start."""
    start = protocol.build_calibration(True, any_key=True)
    stop = protocol.build_calibration(False, any_key=True)
    assert start[6] == 0x0F and stop[6] == 0x10
    assert start[6] != stop[6]


# ------------------------------------------- actuation read (cmd 33 sub 5)
# readTriggerData() in agreement.deobf.js:
#   request : a[0]=0x21 a[4]=0x18 a[5]=0x05 a[6]=row a[7]=col
#   response: matched on a[0]==0x21 && a[5]==0x05, decoded as
#             mode=a[6], travel=a[11]<<8|a[7],
#             interval1=a[13]<<8|a[9], interval2=a[14]<<8|a[10]
#
# Upstream fixed this independently (a588261) and its fix is the one kept:
#   * a NEW protocol.parse_trigger_config holds the vendor decode, and it also
#     reads the row/col the board echoes at a[15]/a[16], so a reply is matched
#     to the key it answers (the Mac fix could book a stale frame on a key);
#   * protocol.parse_trigger_read keeps the travel-STREAM layout, which is a
#     different frame; the Mac branch had rewritten that function in place;
#   * the sweep moved to Win60Driver.read_trigger_config.
# The Mac tests below are re-pointed at that code as a cross-check.
#
# Real Win60 reply at 1.70 mm, captured on macOS 2026-07-24:
#   01 21 00 00 00 0c 05 00 aa aa 00 00 00 00 ...
# Note r[5]==12 (a LENGTH byte), NOT 5 — matching on it never fired.
REAL_REPLY = [0x01, 0x21, 0x00, 0x00, 0x00, 0x0c, 0x05, 0x00, 0xaa, 0xaa,
              0x00, 0x00, 0x00, 0x00] + [0] * 50


def test_trigger_read_decodes_the_real_hardware_reply():
    got = protocol.parse_trigger_config(bytes(REAL_REPLY[1:]))
    assert got["mode"] == 0
    assert got["travel"] == 170, "1.70 mm, the value the board was set to"


def test_trigger_read_high_byte_comes_from_a11_not_a9():
    """Above 2.55 mm the two candidate decodes diverge. a[9] is interval1's LOW
    byte, so the old decode mixed rapid-trigger sensitivity into travel."""
    body = [0] * 63
    body[0] = 0x21
    body[5] = 5
    body[6] = 0
    body[7] = 0x2C        # travel low  (300 = 0x012C -> 3.00 mm)
    body[11] = 0x01       # travel high
    body[9] = 0x63        # interval1 low — must NOT leak into travel
    body[13] = 0x00
    got = protocol.parse_trigger_config(bytes(body))
    assert got["travel"] == 300, "travel high byte must come from a[11]"
    assert got["interval1"] == 0x63


def test_trigger_read_reports_mode_and_the_echoed_key():
    body = [0] * 63
    body[0] = 0x21
    body[5] = 5
    body[6] = 12          # rapid-trigger single
    body[15], body[16] = 2, 3
    got = protocol.parse_trigger_config(bytes(body))
    assert got["mode"] == 12, "a[6] is the trigger MODE, not a row"
    assert (got["row"], got["col"], got["index"]) == (2, 3, 2 * 22 + 3)


def test_config_read_matches_the_subcommand_byte_not_the_length_byte():
    """r[5] is the payload LENGTH; r[6] is the sub-command. A travel-stream
    frame (`01 21 00 00 00 05 01 ...`: length 5, sub 1) must not parse as a
    config reply, and the real reply (length 12, sub 5) must."""
    stream = [0x21, 0x00, 0x00, 0x00, 0x05, 0x01, 0x04, 0x04, 0x63] + [0] * 54
    assert protocol.parse_trigger_config(bytes(stream)) is None
    assert REAL_REPLY[5] == 12 and REAL_REPLY[6] == 5   # why r[5] never matched
    assert protocol.parse_trigger_config(bytes(REAL_REPLY[1:])) is not None


def test_live_reader_length_byte_match_is_left_alone():
    """LiveReader's own `r[5] == 5` is CORRECT and must not be "fixed": travel
    frames carry length 5 with sub-command 1. Two different frames, two
    different bytes that both happen to be 5."""
    src = open(os.path.join(ROOT, "device_state.py"), encoding="utf-8").read()
    live = src[src.index("class LiveReader"):src.index("class CalibrationReader")]
    assert "r[5] == 5" in live, \
        "LiveReader matches the travel frame's LENGTH byte 5 — this is correct"


# ------------------------------------ "all keys" must mean ALL keys
# Upstream's set_trigger_all already uses the keymap's real indices; these pin
# it with the Win60's own index set. With NO keymap upstream keeps the legacy
# `range(key_count)` (the Mac branch swept all 132 slots): Api.km is set for
# every board that connects, so that path is not reachable from the UI and
# upstream's behaviour is left as it is.
WIN60_INDICES = ([22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 36]
                 + [44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 58]
                 + [66, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 80]
                 + [88, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100]
                 + [110, 111, 112, 116, 119, 120, 121, 122])


class _Drv:
    def __init__(self):
        self.calls = []

    def set_actuation(self, idxs, mode, travel, p, r):
        self.calls.append((list(idxs), mode, travel, p, r))


def _trigger_api(km):
    import contextlib

    import app_web

    api = app_web.Api.__new__(app_web.Api)
    api.km = km
    api.driver = _Drv()
    api._trigger_state = {}
    api._act_mm = {}
    api._trig_mode = {}
    api._stats_forget_actuation = lambda idxs: None
    api._reader_paused = contextlib.nullcontext
    return api


def test_set_trigger_all_uses_real_sparse_key_indices():
    """Device indices are row*22+col, so a 61-key board spans 22..122. Sending
    range(64) reached only the 28 keys under 64 — measured on hardware as
    {3.0: 28, 1.7: 33} after a 'set all' to 3.00 mm."""
    class _KM:
        def indices(self):
            return list(WIN60_INDICES)

    api = _trigger_api(_KM())
    res = api.set_trigger_all(3.0)

    assert res["ok"] is True and res["keys"] == 61
    sent = api.driver.calls[0][0]
    assert sent == WIN60_INDICES
    assert len([i for i in sent if i >= 64]) == 33, \
        "the 33 keys above index 64 were the ones being skipped"


def test_the_real_win60_keymap_has_those_indices():
    assert sorted(device_state.KeyMap().indices()) == WIN60_INDICES
