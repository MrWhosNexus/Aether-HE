"""Keyboard-function review regressions (Win60 protocol + Api), pinned to
the live capture of the official vendor driver on a physical WIN 60 HE
(docs/context/hed-aulacn-raw/webhid-capture-win60.json).

Bugs these guard:
  * actuation read-back (cmd 33 sub 5): the reply's payload-length byte is
    0x0c, so a reader matching raw r[5] == 5 never saw it, and the old
    stream-frame parser decoded travel from the wrong bytes (1.70 mm read
    back as 4.26 mm). protocol.parse_trigger_config + Win60Driver
    .read_trigger_config use the vendor's own field expressions.
  * switch profile (cmd 37): the write was a constant `1` fill for every
    key not in the patch, silently resetting the other keys' switches on
    every apply. Now read-modify-write over the cmd-37 sub-2 table read
    (CONFIRMED-BY-CAPTURE framing).
  * Api validation: trigger mode / poll code / mm ranges are checked or
    clamped before anything reaches the wire.
"""
import json
import threading
import types
from pathlib import Path

import pytest

import boards
import protocol
import app_web
from drivers import Win60Driver

CAPTURE = (Path(__file__).resolve().parents[1]
           / "docs" / "context" / "hed-aulacn-raw" / "webhid-capture-win60.json")
with open(CAPTURE, "r", encoding="utf-8") as fh:
    FRAMES = json.load(fh)["frames"]


def _body(i):
    return [int(x, 16) for x in FRAMES[i]["hex"].split()]


def _prefixed(body):
    return [protocol.REPORT_ID] + list(body)


# Captured readTriggerData request/reply pairs (frames 172/173 = row 1 col 0,
# 174/175 = row 1 col 1) and the vendor's whole-board switch write of "2"
# (frames 1578/1579/1581, page 0/1/2) plus the mount read (299-301).
_TRIG_REQ_22, _TRIG_REP_22 = _body(172), _body(173)
_TRIG_REQ_23, _TRIG_REP_23 = _body(174), _body(175)
_SW_READ_CHUNKS = [_body(i) for i in (299, 300, 301)]
_SW_WRITE_HH1 = [_body(i) for i in (1578, 1579, 1581)]
_SW_LIST_REPLY = _body(297)


# ------------------------------------------------ trigger config read-back --
def test_trigger_config_request_matches_capture():
    assert protocol.build_read_trigger_config(22)[1:] == _TRIG_REQ_22
    assert protocol.build_read_trigger_config(23)[1:] == _TRIG_REQ_23


def test_trigger_config_reply_decodes_with_vendor_offsets():
    p = protocol.parse_trigger_config(_TRIG_REP_22)
    assert p == {"mode": 0, "travel": 170, "interval1": 1, "interval2": 1,
                 "row": 1, "col": 0, "index": 22}
    assert protocol.parse_trigger_config(_TRIG_REP_23)["index"] == 23
    # absolute wire facts the bug hinged on
    assert _TRIG_REP_22[4] == 0x0C           # payload LENGTH, not the sub byte
    assert _TRIG_REP_22[5] == 5              # the sub-command discriminator
    # the stream-frame layout is NOT this reply: it would read 4.26 mm
    assert protocol.parse_trigger_read(_TRIG_REP_22)["travel"] == 426
    # not a sub-5 reply -> None (a live travel-test frame, body[5] == 1)
    stream = [0x21, 0, 0, 0, 5, 1, 1, 0, 0x50, 0, 0] + [0] * 52
    assert protocol.parse_trigger_config(stream) is None


class _Handle:
    def __init__(self):
        self.frames = []

    def set_nonblocking(self, v):
        pass

    def read(self, n):
        return self.frames.pop(0) if self.frames else []


class ReadableDevice:
    """Fake AulaDevice with a raw handle; reply_fn(payload) -> queued frames."""

    def __init__(self, reply_fn=None):
        self.writes = []
        self.reply_fn = reply_fn
        self._lock = threading.Lock()
        self._dev = _Handle()
        self.nonblock = None

    def open(self):
        return {"interface_number": 2, "usage_page": 0xFF1B}

    def close(self):
        pass

    def is_open(self):
        return True

    def write(self, payload):
        self.writes.append(list(payload))
        if self.reply_fn:
            self._dev.frames.extend(self.reply_fn(list(payload)) or [])
        return len(payload)

    def read(self, n, timeout_ms=0):
        return self._dev.read(n)

    def set_nonblocking(self, v):
        self.nonblock = v


def _win60_profile():
    return boards.load_registry().by_slug("aula-win60-he")


def _trigger_reply(row, col, travel=170, mode=0, i1=1, i2=1):
    """A reply shaped exactly like the captured one, for another key."""
    b = list(_TRIG_REP_22)
    b[6] = mode
    b[7] = b[8] = travel & 0xFF
    b[11] = (travel >> 8) & 0xFF
    b[9], b[10] = i1 & 0xFF, i2 & 0xFF
    b[13], b[14] = (i1 >> 8) & 0xFF, (i2 >> 8) & 0xFF
    b[15], b[16] = row, col
    return _prefixed(b)


def test_win60_read_actuation_decodes_captured_reply_and_ignores_stream_frames():
    def reply(payload):
        if payload[1] == 33 and payload[6] == 5:
            row, col = payload[7], payload[8]
            # a stray live travel-test frame (len 5, sub 1) arrives first —
            # the OLD reader would have booked its depth as the actuation
            junk = _prefixed([0x21, 0, 0, 0, 5, 1, row, col, 0x90, 0x01, 0] + [0] * 52)
            if (row, col) == (1, 0):
                return [junk, _prefixed(_TRIG_REP_22)]
            return [junk, _trigger_reply(row, col, travel=300, mode=13, i1=120, i2=50)]
        return []

    dev = ReadableDevice(reply)
    d = Win60Driver(_win60_profile(), dev, threading.RLock())
    km = types.SimpleNamespace(keys=[{"index": 22, "name": "Tab"},
                                     {"index": 23, "name": "Q"}])
    assert d.read_actuation(km) == {"Tab": 1.7, "Q": 3.0}
    cfg = d.read_trigger_config([22, 23])
    assert cfg[23] == {"mode": 13, "travel": 300, "interval1": 120, "interval2": 50}
    # requests went out per key, through the locked wrapper, nonblocking
    reqs = [w for w in dev.writes if w[1] == 33 and w[6] == 5]
    assert [(w[7], w[8]) for w in reqs] == [(1, 0), (1, 1), (1, 0), (1, 1)]
    assert dev.nonblock is True


def test_win60_read_actuation_never_books_another_keys_reply():
    """A reply echoing a different row/col (stale, or the board answering a
    neighbour) must not be attributed to the key just asked for."""
    def reply(payload):
        if payload[1] == 33 and payload[6] == 5:
            return [_trigger_reply(3, 7, travel=250)]      # wrong key
        return []

    d = Win60Driver(_win60_profile(), ReadableDevice(reply), threading.RLock())
    d.TRIGGER_READ_TIMEOUT_S = 0.005
    km = types.SimpleNamespace(keys=[{"index": 22, "name": "Tab"}])
    assert d.read_actuation(km) == {}


# --------------------------------------------------------- switch profile --
def test_switch_read_request_and_chunks_match_capture():
    assert protocol.build_read_switch_table()[1:] == _body(298)
    assert [b[4] for b in _SW_READ_CHUNKS] == [0x3A, 0x3A, 0x10]
    table = protocol.assemble_switch_table(
        [protocol.parse_switch_chunk(b) for b in _SW_READ_CHUNKS])
    assert table == bytes([1] * 132)
    # partial read -> None, never a half-zeroed table
    assert protocol.assemble_switch_table(
        [protocol.parse_switch_chunk(b) for b in _SW_READ_CHUNKS[:2]]) is None
    # the switch LIST reply is not a table chunk
    assert protocol.parse_switch_chunk(_SW_LIST_REPLY) is None


def test_switch_list_parses_captured_ids():
    assert protocol.build_read_switch_list()[1:] == _body(296)
    assert protocol.parse_switch_list(_SW_LIST_REPLY) == [1, 2, 3, 5]


def test_switch_rmw_reproduces_vendor_write_and_constant_fill_does_not():
    """The vendor's 'all keys -> HH1' write carries 2 on the 61 physical
    keys and 0 on empty slots — a per-key table, not a constant. Patching
    the physical keys over a zero base reproduces it byte-for-byte; the
    legacy default_switch fill never matched the wire."""
    phys = [i for i in range(132)
            if any(b[5 + (i - (b[3] * 58))] == 2 for b in _SW_WRITE_HH1
                   if b[3] * 58 <= i < b[3] * 58 + b[4])]
    assert len(phys) == 61
    built = [p[1:] for p in protocol.build_switch_table(
        {i: 2 for i in phys}, base_table=bytes(132))]
    assert built == _SW_WRITE_HH1
    legacy = [p[1:] for p in protocol.build_switch_table({i: 2 for i in phys})]
    assert legacy != _SW_WRITE_HH1


def test_win60_set_switch_reads_then_patches_only_requested_keys():
    board = bytearray([0] * 132)
    for i in (22, 23, 24, 25):
        board[i] = 5                                        # WASD-ish on TC1

    def reply(payload):
        if payload[1] == 37 and payload[2] == 2:
            chunks = []
            for page, start in enumerate(range(0, 132, 58)):
                part = board[start:start + 58]
                chunks.append(_prefixed([37, 2, 0, page, len(part)] + list(part)
                                        + [0] * (58 - len(part))))
            return chunks
        return []

    dev = ReadableDevice(reply)
    d = Win60Driver(_win60_profile(), dev, threading.RLock())
    d.set_switch({40: 2})                                   # Space -> HH1
    writes = [w for w in dev.writes if w[1] == 37 and w[2] == 1]
    expect = protocol.build_switch_table({40: 2}, base_table=bytes(board))
    assert writes == expect
    merged = b"".join(bytes(w[6:6 + w[5]]) for w in writes)
    assert merged[40] == 2 and [merged[i] for i in (22, 23, 24, 25)] == [5] * 4
    assert merged[0] == 0                                   # empty slot untouched


def test_win60_set_switch_aborts_on_partial_read():
    def reply(payload):
        if payload[1] == 37 and payload[2] == 2:
            return [_prefixed([37, 2, 0, 0, 58] + [1] * 58)]   # page 0 only
        return []

    dev = ReadableDevice(reply)
    d = Win60Driver(_win60_profile(), dev, threading.RLock())
    d.SWITCH_READ_TIMEOUT_S = 0.01
    with pytest.raises(RuntimeError):
        d.set_switch({40: 2})
    assert not [w for w in dev.writes if w[1] == 37 and w[2] == 1]


# ------------------------------------------------------- protocol guards --
def test_protocol_guards():
    with pytest.raises(ValueError):
        protocol.build_prcs([{"model": 1, "key1_hid": 4, "key2_hid": 7}] * 21)
    with pytest.raises(ValueError):
        protocol._keymask([176])
    with pytest.raises(ValueError):
        protocol.build_deadband_table({3: (256, 5)})
    with pytest.raises(ValueError):
        protocol.build_switch_table({3: 300})


# -------------------------------------------------------------- api level --
class _Drv:
    """Records set_actuation / set_poll_rate / set_deadband calls."""
    DEADBAND_SCOPE = "per-key"

    def __init__(self):
        self.calls = []

    def set_actuation(self, *a):
        self.calls.append(("act",) + a)

    def set_poll_rate(self, rate):
        self.calls.append(("poll", rate))

    def set_deadband(self, raw, top_mm=None, bottom_mm=None):
        self.calls.append(("db", raw, top_mm, bottom_mm))


def _api():
    a = app_web.Api.__new__(app_web.Api)
    a._lock = threading.RLock()
    a.board = _win60_profile()
    a.driver = _Drv()
    a._trigger_state = {}
    a._deadband_state = {}
    a.km = types.SimpleNamespace(
        indices=lambda: [0, 22, 131],
        indices_for_codes=lambda codes: [{"KeyA": 22, "KeyB": 131}[c]
                                         for c in codes if c in ("KeyA", "KeyB")])
    return a


def test_api_set_poll_refuses_undefined_codes():
    a = _api()
    assert a.set_poll(8) == {"ok": True}
    assert a.driver.calls == [("poll", 8)]
    for bad in (3, 0, 16, 8000):
        r = a.set_poll(bad)
        assert r["ok"] is False and "poll-rate" in r["error"]
    assert a.driver.calls == [("poll", 8)]                  # nothing else sent


def test_api_set_trigger_codes_validates_mode_and_clamps_ranges():
    a = _api()
    r = a.set_trigger_codes(["KeyA"], 1.5, 0.3, 0.3, mode=5)
    assert r["ok"] is False and not a.driver.calls
    # fixed mode: intervals pass through untouched (UI sends 0)
    a.set_trigger_codes(["KeyA"], 9.9, 0, 0, mode=0)
    assert a.driver.calls[-1] == ("act", [22], 0, pytest.approx(3.4), 0.0, 0.0)
    # RT mode: travel and sensitivities clamped to the registry ranges
    a.set_trigger_codes(["KeyB"], 0.01, 0.0, 7.0, mode=13)
    assert a.driver.calls[-1] == ("act", [131], 13, pytest.approx(0.1),
                                  pytest.approx(0.05), pytest.approx(2.0))
    # raw state is what gets re-flushed later: clamped values, 0.01 mm units
    assert a._trigger_state[131] == (13, 10, 5, 200)


def test_api_set_trigger_all_uses_keymap_indices_not_range_64():
    a = _api()
    assert a.set_trigger_all(1.7) == {"ok": True, "keys": 3}
    assert a.driver.calls == [("act", [0, 22, 131], 0, 1.7, 0.0, 0.0)]
    assert a.set_trigger_all(1.7, mode=7)["ok"] is False


def test_api_set_deadband_codes_clamps_to_registry_range():
    a = _api()
    r = a.set_deadband_codes(["KeyA"], top_mm=3.0, bottom_mm=-1)
    assert r["ok"] is True
    assert a._deadband_state[22] == (50, 0)                 # 0.5 mm cap, 0 floor
    assert a.driver.calls[-1] == ("db", {22: (50, 0)}, 0.5, 0.0)
