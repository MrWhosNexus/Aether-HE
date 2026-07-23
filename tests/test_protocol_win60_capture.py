"""Golden tests for the Win60 HE protocol additions, pinned against the live
WebHID capture of the official vendor driver on a physical WIN 60 HE
(docs/context/hed-aulacn-raw/webhid-capture-win60.json, 8089 frames, 2026-07-21;
analysis in WIN60_CAPTURE_NOTES.md).

Every frame asserted here is a real OUT/IN report from the connected board —
nothing synthetic. Alongside build<->parse symmetry these tests pin ABSOLUTE
byte offsets from the wire, because symmetry alone cannot catch an off-by-one
(that exact bug bit this project).

Covered (all CONFIRMED-BY-CAPTURE):
  * dead band (cmd 38): read request, chunked read reply, and the
    read-modify-write fix — the board's real per-key dead band is 2/2
    (0.02 mm) on its 61 physical keys / 0/0 on empty slots, so the old
    constant 4/5 default fill rewrote every untouched key.
  * macros (cmd 25): 10 x 256 B slots, 8-byte header + 4-byte events,
    including an event split across a chunk boundary, and the keymap binding
    entry [0x10, hid, slot, 0].
  * music rhythm (cmd 23), device info (cmd 13), initInfo capability bitmask
    (cmd 1), readMaxTriggerTravel (cmd 33 sub 4).
"""
import json
import threading
from pathlib import Path

import pytest

import boards
import protocol
from drivers import Win60Driver

CAPTURE = (Path(__file__).resolve().parents[1]
           / "docs" / "context" / "hed-aulacn-raw" / "webhid-capture-win60.json")

with open(CAPTURE, "r", encoding="utf-8") as fh:
    FRAMES = json.load(fh)["frames"]


def _body(frame):
    return [int(x, 16) for x in frame["hex"].split()]


def _outs(pred):
    return [(i, _body(f)) for i, f in enumerate(FRAMES)
            if f["dir"] == "OUT" and pred(_body(f))]


def _ins(pred):
    return [(i, _body(f)) for i, f in enumerate(FRAMES)
            if f["dir"] == "IN" and pred(_body(f))]


def _group(start, pred, count):
    """The next `count` OUT bodies matching pred, from frame index start."""
    got = []
    j = start
    while j < len(FRAMES) and len(got) < count:
        f = FRAMES[j]
        if f["dir"] == "OUT":
            b = _body(f)
            if pred(b):
                got.append(b)
        j += 1
    return got


# Custom per-key light (cmd 9): the two persistent slots. The FIRST 8 IN
# chunks per slot are the mount-time reads — content stored by a PREVIOUS
# session, served back before this session wrote anything (the persistence
# evidence). The FIRST 8 OUT table frames per slot are the vendor's
# palette-switch writes (Custom2 then Custom1), which re-sent those same
# stored tables.
_CL0_READ = [b for _, b in _ins(lambda b: b[0] == 0x09 and b[1] == 0x80)][:8]
_CL1_READ = [b for _, b in _ins(lambda b: b[0] == 0x09 and b[1] == 0x81)][:8]
_CL0_TABLE = protocol.assemble_custom_light_table(
    [protocol.parse_custom_light_chunk(b, 0) for b in _CL0_READ])
_CL1_TABLE = protocol.assemble_custom_light_table(
    [protocol.parse_custom_light_chunk(b, 1) for b in _CL1_READ])
_CL0_WRITE = _outs(lambda b: b[0] == 0x09 and b[1] == 0x00 and b[4] > 0)[:8]
_CL1_WRITE = _outs(lambda b: b[0] == 0x09 and b[1] == 0x01 and b[4] > 0)[:8]

# The board's final dead-band read-back: 5 chunks answering `26 00`, values
# 2/2 on physical keys. The mount read (all zeros = "firmware default", like
# the keymap read) is skipped by taking the LAST complete read.
_DB_READ_CHUNKS = [b for _, b in _ins(lambda b: b[0] == 0x26 and b[1] == 0)][-5:]
_DB_TABLE = protocol.assemble_deadband_table(
    [protocol.parse_deadband_chunk(b) for b in _DB_READ_CHUNKS])
_PHYS = [i for i in range(132) if _DB_TABLE[2 * i] or _DB_TABLE[2 * i + 1]]

# Captured macro payloads (WIN60_CAPTURE_NOTES.md section 5, cross-checked
# against the vendor UI's own recorded event list).
_M1_EVENTS = [(0x04, True, 126), (0x04, False, 202), (0x05, True, 122),
              (0x05, False, 203), (0x06, True, 122), (0x06, False, 0)]
_M2_EVENTS = [(0x14, True, 77), (0x14, False, 108), (0x1A, True, 76),
              (0x1A, False, 109), (0x08, True, 77), (0x08, False, 110),
              (0x15, True, 78), (0x15, False, 109), (0x17, True, 77),
              (0x17, False, 108), (0xE1, True, 92), (0x1E, True, 94),
              (0x1E, False, 93), (0xE1, False, 0)]


# ------------------------------------------------------------ dead band ----
def test_deadband_read_request_matches_capture():
    i, wire = _outs(lambda b: b[0] == 0x26 and b[1] == 0)[0]
    assert protocol.build_read_deadband()[1:] == wire


def test_deadband_read_chunks_assemble_to_264_bytes():
    assert _DB_TABLE is not None and len(_DB_TABLE) == 264
    # chunk framing, absolute offsets: [cmd, 0, page_hi, page_lo, len]
    assert [b[4] for b in _DB_READ_CHUNKS] == [0x3A, 0x3A, 0x3A, 0x3A, 0x20]
    assert [(b[2] << 8) | b[3] for b in _DB_READ_CHUNKS] == [0, 1, 2, 3, 4]


def test_deadband_board_default_is_2_2_not_4_5():
    """THE BUG: the board's real per-key dead band is 2/2 (0.02 mm) on all
    61 physical keys and 0/0 on unpopulated slots — NOT the 4/5 that
    build_deadband_table used to stamp onto every key it wasn't asked
    about."""
    assert len(_PHYS) == 61
    assert all(_DB_TABLE[2 * i] == 2 and _DB_TABLE[2 * i + 1] == 2
               for i in _PHYS)
    # absolute wire offsets inside the read-back table
    assert _DB_TABLE[0] == 0 and _DB_TABLE[1] == 0          # slot 0: no key
    assert _DB_TABLE[44] == 2 and _DB_TABLE[45] == 2        # key 22 (row 1)
    assert _DB_TABLE[2 * 122] == 2 and _DB_TABLE[2 * 122 + 1] == 2  # Fn key
    # the old constant fill disagrees with the wire on every physical key
    legacy_page0 = protocol.build_deadband_table({})[0]
    assert legacy_page0[6] == 4 and legacy_page0[7] == 5    # 4/5 fill


def test_deadband_phys_keys_equal_trigger_keymask():
    """The 61 keys carrying a dead band are exactly the 61 bits of the
    all-keys trigger bitmask the vendor sent (and protocol._keymask
    produces)."""
    _, trig = _outs(lambda b: b[0] == 0x21 and b[4] == 0x18 and b[5] == 0)[0]
    mask = trig[6:28]
    mask_keys = [i for i in range(132) if (mask[i % 22] >> (i // 22)) & 1]
    assert mask_keys == _PHYS
    assert protocol._keymask(_PHYS) == mask


def test_deadband_rmw_reproduces_vendor_write_frames():
    """build_deadband_table(base_table=...) patched at exactly the physical
    keys equals the vendor's captured 0.10/0.25 mm write byte-for-byte —
    and the legacy default fill does NOT match the wire."""
    starts = [i for i, b in _outs(lambda b: b[0] == 0x26 and b[1] == 1
                                  and b[2] == 0 and b[3] == 0)]
    target = None
    for s in starts:
        g = _group(s, lambda b: b[0] == 0x26 and b[1] == 1, 5)
        if any(0x19 in b[5:] for b in g):
            target = g
            break
    assert target is not None
    built = [p[1:] for p in protocol.build_deadband_table(
        {i: (0x0A, 0x19) for i in _PHYS}, base_table=bytes(264))]
    assert built == target
    legacy = [p[1:] for p in protocol.build_deadband_table(
        {i: (0x0A, 0x19) for i in _PHYS})]
    assert legacy != target        # 4/5 fill never matched the wire


def test_deadband_restore_write_matches_capture():
    """The vendor's restore-to-0.02/0.02 write == a (2,2) patch of the
    physical keys over a zero base."""
    starts = [i for i, b in _outs(lambda b: b[0] == 0x26 and b[1] == 1
                                  and b[2] == 0 and b[3] == 0)]
    restore = None
    for s in reversed(starts):
        g = _group(s, lambda b: b[0] == 0x26 and b[1] == 1, 5)
        if any(2 in b[5:] for b in g) and not any(0x0A in b[5:] for b in g):
            restore = g
            break
    assert restore is not None
    built = [p[1:] for p in protocol.build_deadband_table(
        {i: (2, 2) for i in _PHYS}, base_table=bytes(264))]
    assert built == restore


def test_deadband_base_table_param_is_additive():
    """Without base_table the builder's output is byte-identical to what it
    always produced (existing callers see zero change)."""
    old_shape = protocol.build_deadband_table({3: (4, 5), 7: (10, 12)})
    again = protocol.build_deadband_table({3: (4, 5), 7: (10, 12)},
                                          default_top=4, default_bottom=5,
                                          key_count=132)
    assert old_shape == again
    assert old_shape[0][1] == 38 and old_shape[0][2] == 1   # cmd 38, sub 1


# --------------------------------------------------------------- macros ----
def _macro_write_group(slot, header_len_lo):
    starts = [i for i, b in _outs(
        lambda b: b[0] == 0x19 and b[1] == slot and b[2] == 0 and b[3] == 0
        and b[8] == header_len_lo)]
    assert starts, "macro write not found in capture"
    return _group(starts[0], lambda b: b[0] == 0x19 and b[1] == slot, 5)


def test_macro1_packets_match_capture():
    wire = _macro_write_group(0, 0x18)          # 6 events -> 24 B
    built = [p[1:] for p in protocol.build_macro_packets(0, _M1_EVENTS, 1)]
    assert built == wire
    # absolute offsets in chunk 0: header [slot, slot, lenBE16, 0, repeat]
    b0 = wire[0]
    assert b0[5] == 0 and b0[6] == 0            # slot twice
    assert b0[7] == 0x00 and b0[8] == 0x18      # 24 event bytes, BIG-endian
    assert b0[10] == 1                          # repeat: "Operate Once"
    # first event A down, 126 ms BE at payload offset 8
    assert b0[13:17] == [0x04, 0x10, 0x00, 0x7E]


def test_macro2_packets_match_capture_across_chunk_boundary():
    wire = _macro_write_group(1, 0x38)          # 14 events -> 56 B
    built = [p[1:] for p in protocol.build_macro_packets(1, _M2_EVENTS, 3)]
    assert built == wire
    b0, b1 = wire[0], wire[1]
    assert b0[10] == 3                          # repeat: "Operate 3 times"
    # the 13th event (Shift-1 release) splits across the chunk boundary:
    # `1e 00` ends chunk 0, `00 5d` opens chunk 1, then Shift up.
    assert b0[61:63] == [0x1E, 0x00]
    assert b1[5:9] == [0x00, 0x5D, 0xE1, 0x00]


def test_macro_parse_round_trips_captured_table():
    wire = _macro_write_group(1, 0x38)
    table = bytearray(protocol.MACRO_SLOT_BYTES)
    for b in wire:
        page = (b[2] << 8) | b[3]
        table[page * 58:page * 58 + b[4]] = bytes(b[5:5 + b[4]])
    parsed = protocol.parse_macro_table(table)
    assert parsed == {"slot": 1, "repeat_count": 3, "events": _M2_EVENTS}


def test_macro_empty_slot_reads_back_all_ff():
    empties = _ins(lambda b: b[0] == 0x19 and b[1] & 0x80
                   and all(x == 0xFF for x in b[5:5 + b[4]]) and b[4] > 0)
    assert empties, "capture contains all-0xFF empty macro slots"
    assert protocol.parse_macro_table([0xFF] * 256) is None


def test_macro_read_request_layout():
    pkt = protocol.build_read_macro(3)
    assert pkt[0] == 1 and pkt[1] == 0x19 and pkt[2] == 0x83
    with pytest.raises(ValueError):
        protocol.build_read_macro(10)


def test_macro_keymap_binding_entries_seen_on_wire():
    """The keymap write that bound macro 0 to M (slot 96) and macro 1 to N
    (slot 95) carries exactly macro_keymap_entry()'s bytes."""
    starts = [i for i, b in _outs(lambda b: b[0] == 0x18 and b[1] == 0
                                  and b[2] == 0 and b[3] == 0)]
    found = False
    for s in starts:
        table = bytearray(528)
        for b in _group(s, lambda b: b[0] == 0x18 and b[1] == 0, 10):
            page = (b[2] << 8) | b[3]
            table[page * 56:page * 56 + b[4]] = bytes(b[5:5 + b[4]])
        if (list(table[96 * 4:96 * 4 + 4])
                == protocol.macro_keymap_entry(0, 0x10)
                and list(table[95 * 4:95 * 4 + 4])
                == protocol.macro_keymap_entry(1, 0x11)):
            found = True
            break
    assert found
    assert protocol.macro_keymap_entry(1, 0x11) == [0x10, 0x11, 0x01, 0x00]


# --------------------------------------------------- music rhythm (0x17) ----
def test_music_rhythm_matches_capture():
    _, off_wire = _outs(lambda b: b[0] == 0x17 and b[5] == 0)[0]
    _, on_wire = _outs(lambda b: b[0] == 0x17 and b[5] == 1)[0]
    assert protocol.build_music_rhythm(False)[1:] == off_wire
    assert protocol.build_music_rhythm(True)[1:] == on_wire
    # absolute offsets: len 2 at [4], flag duplicated at [5] and [6]
    assert on_wire[4] == 2 and on_wire[5] == 1 and on_wire[6] == 1


def test_vendor_sends_rhythm_off_before_light_writes():
    """Ordering evidence: the vendor driver emits `17 .. 02 00 00`
    immediately around cmd-7 light writes (documented in
    build_music_rhythm's docstring; Aether's light path is deliberately
    unchanged)."""
    light_idx = [i for i, b in _outs(lambda b: b[0] == 0x07 and b[4] == 14)]
    rhythm_idx = [i for i, b in _outs(lambda b: b[0] == 0x17 and b[5] == 0)]
    assert any(any(0 < li - ri <= 4 for ri in rhythm_idx) for li in light_idx)


# ---------------------------------------------------- device info (0x0d) ----
def test_device_info_query_and_parse_match_capture():
    _, req = _outs(lambda b: b[0] == 0x0D)[0]
    assert protocol.build_device_info_query()[1:] == req
    _, fw = _ins(lambda b: b[0] == 0x0D and b[3] == 0)[0]
    _, bd = _ins(lambda b: b[0] == 0x0D and b[3] == 1)[0]
    assert protocol.parse_device_info(fw) == {
        "index": 0, "text": "W669,34,KB,SI,SI2825KZHEARGB,V3.17.07"}
    # the build-date reply carries stale bytes after the NUL — must be cut
    assert protocol.parse_device_info(bd) == {
        "index": 1, "text": "Apr 15 2026,11:20:35"}
    # absolute offsets: ASCII length 0x32 at [4], text from [5]
    assert fw[4] == 0x32 and fw[5] == ord("W")


# ------------------------------------------------ initInfo bitmask (0x01) ----
def test_init_info_capability_bitmask_matches_capture():
    _, wire = _ins(lambda b: b[0] == 0x01)[0]
    # absolute offsets first: flags live at body[17]/body[18]
    assert wire[4] == 0x11 and wire[17] == 0x7F and wire[18] == 0x00
    p = protocol.parse_init_info(wire)
    assert p is not None
    # true on this board
    for k in ("is_prcs", "is_any_key_calibration", "is_custom_light",
              "is_more_switch", "is_poll_rate", "is_dead_band",
              "is_music_rhythm"):
        assert p[k] is True, k
    # false on this board — including gamepad (see registry note: Aether's
    # gamepad feature is host-side virtual; the FIRMWARE gamepad is absent)
    for k in ("is_gamepad", "is_rs", "is_rkrt", "is_high_precision",
              "is_6key_mode", "is_all_and_6key_switch", "is_music_rhythm_on"):
        assert p[k] is False, k
    assert p["tri_mode"] == 0 and p["battery"] == 0 and p["charging"] is False


# ------------------------------------------- readMaxTriggerTravel (33/4) ----
def test_read_max_trigger_travel_matches_capture():
    _, req = _outs(lambda b: b[0] == 0x21 and b[4] == 0x18 and b[5] == 4)[0]
    assert protocol.build_read_max_trigger_travel()[1:] == req
    _, rep = _ins(lambda b: b[0] == 0x21 and b[4] == 6 and b[5] == 4)[0]
    # absolute offsets: numer [7], max = [9]<<8|[6], min [10]
    assert rep[6] == 0x54 and rep[7] == 0x01 and rep[9] == 0x01 and rep[10] == 0x08
    p = protocol.parse_max_trigger_travel(rep)
    assert p["unit_mm"] == protocol.TRIGGER_UNIT_MM == 0.01
    assert p["max_travel_raw"] == 340 and p["min_travel_raw"] == 8
    assert abs(p["max_travel_mm"] - 3.40) < 1e-9
    assert abs(p["min_travel_mm"] - 0.08) < 1e-9
    # high-precision boards divide by 1000 instead
    assert protocol.parse_max_trigger_travel(rep, high_precision=True)["unit_mm"] == 0.001


# ============================================================ driver level ==
class _Handle:
    """Raw-handle stand-in: nonblocking reads pop queued reply frames."""

    def __init__(self):
        self.frames = []

    def set_nonblocking(self, v):
        pass

    def read(self, n):
        return self.frames.pop(0) if self.frames else []


class ReadableDevice:
    """Fake AulaDevice WITH a raw input handle, so the Win60 driver takes
    its read paths. reply_fn(payload) -> reply frames queued on the handle
    (report-id-prefixed, like hidapi on this codebase)."""

    def __init__(self, reply_fn=None):
        self.writes = []
        self.reply_fn = reply_fn
        self._lock = threading.Lock()
        self._dev = _Handle()
        self._is_open = True

    def open(self):
        self._is_open = True
        return {"interface_number": 2, "usage_page": 0xFF1B}

    def close(self):
        self._is_open = False

    def is_open(self):
        return self._is_open

    def write(self, payload):
        self.writes.append(list(payload))
        if self.reply_fn:
            self._dev.frames.extend(self.reply_fn(list(payload)) or [])
        return len(payload)


class WriteOnlyDevice(ReadableDevice):
    """No raw handle at all — the legacy constant-fill dead-band path."""

    def __init__(self):
        super().__init__()
        self._dev = None


def _prefixed(body):
    return [protocol.REPORT_ID] + list(body)


def _capture_reply_fn(payload):
    """Answer read requests with the real captured reply frames."""
    if payload[1] == 0x26 and payload[2] == 0:
        return [_prefixed(b) for b in _DB_READ_CHUNKS]
    if payload[1] == 0x09 and payload[2] in (0x80, 0x81):
        chunks = _CL0_READ if payload[2] == 0x80 else _CL1_READ
        return [_prefixed(b) for b in chunks]
    if payload[1] == 0x09 and payload[2] == 0x20:
        return [_prefixed(_ins(lambda b: b[0] == 0x09 and b[1] == 0)[0][1])]
    if payload[1] == 0x0D:
        fw = _ins(lambda b: b[0] == 0x0D and b[3] == 0)[0][1]
        bd = _ins(lambda b: b[0] == 0x0D and b[3] == 1)[0][1]
        return [_prefixed(fw), _prefixed(bd)]
    if payload[1] == 0x01:
        return [_prefixed(_ins(lambda b: b[0] == 0x01)[0][1])]
    if payload[1] == 0x21 and payload[6] == 4:
        return [_prefixed(
            _ins(lambda b: b[0] == 0x21 and b[4] == 6 and b[5] == 4)[0][1])]
    if payload[1] == 0x19 and payload[2] & 0x80:
        slot = payload[2] & 0x0F
        wire = _macro_write_group(1, 0x38) if slot == 1 else None
        if wire:
            out = []
            for b in wire:
                r = list(b)
                r[1] = 0x80 | slot          # reads echo with [1] = slot|0x80
                out.append(_prefixed(r))
            return out
    return []


def test_driver_set_deadband_is_read_modify_write():
    """THE FIX: setting one key's dead band reads the current table first
    and preserves every other key's 2/2 instead of stamping 4/5 on them."""
    dev = ReadableDevice(_capture_reply_fn)
    d = Win60Driver(None, dev, threading.RLock())
    d.set_deadband({90: (0x0A, 0x19)})
    assert dev.writes[0] == protocol.build_read_deadband()
    expect = protocol.build_deadband_table({90: (0x0A, 0x19)},
                                           base_table=_DB_TABLE)
    assert dev.writes[1:] == expect
    # absolute offsets in the written pages: key 90 patched...
    page3 = dev.writes[1:][3]        # table bytes 174..231
    assert page3[6 + (180 - 174)] == 0x0A and page3[6 + (181 - 174)] == 0x19
    # ...key 91 PRESERVED at the board's real 2/2, not rewritten to 4/5
    assert page3[6 + (182 - 174)] == 2 and page3[6 + (183 - 174)] == 2
    # and slot 0 (no physical key) stays 0/0, not 4/5
    page0 = dev.writes[1:][0]
    assert page0[6] == 0 and page0[7] == 0


def test_driver_set_deadband_aborts_when_read_fails():
    """No reply -> RuntimeError BEFORE any table write (never fall back to
    assumed defaults)."""
    dev = ReadableDevice(reply_fn=None)
    d = Win60Driver(None, dev, threading.RLock())
    d.DEADBAND_READ_TIMEOUT_S = 0.05
    with pytest.raises(RuntimeError):
        d.set_deadband({90: (0x0A, 0x19)})
    table_writes = [w for w in dev.writes if w[1] == 0x26 and w[2] == 1]
    assert table_writes == []


def test_driver_set_deadband_legacy_path_without_raw_handle():
    """A device with no raw input handle keeps the pre-fix behavior
    byte-for-byte (existing callers/tests unchanged)."""
    dev = WriteOnlyDevice()
    d = Win60Driver(None, dev, threading.RLock())
    d.set_deadband({3: (4, 5), 7: (10, 12)})
    assert dev.writes == protocol.build_deadband_table({3: (4, 5), 7: (10, 12)})


def test_driver_read_deadband_table_from_captured_chunks():
    dev = ReadableDevice(_capture_reply_fn)
    d = Win60Driver(None, dev, threading.RLock())
    assert d.read_deadband_table(timeout_s=0.5) == _DB_TABLE


def test_driver_write_macro_emits_capture_identical_packets():
    dev = ReadableDevice()
    d = Win60Driver(None, dev, threading.RLock())
    d.write_macro(1, _M2_EVENTS, repeat_count=3)
    assert dev.writes == protocol.build_macro_packets(1, _M2_EVENTS, 3)
    assert [w[1:] for w in dev.writes] == _macro_write_group(1, 0x38)


def test_driver_read_macro_round_trip():
    dev = ReadableDevice(_capture_reply_fn)
    d = Win60Driver(None, dev, threading.RLock())
    parsed = d.read_macro(1, timeout_s=0.5)
    assert parsed == {"slot": 1, "repeat_count": 3, "events": _M2_EVENTS}


def test_driver_device_info_from_captured_replies():
    dev = ReadableDevice(_capture_reply_fn)
    d = Win60Driver(None, dev, threading.RLock())
    info = d.device_info()
    assert info == {"firmware": "W669,34,KB,SI,SI2825KZHEARGB,V3.17.07",
                    "build_date": "Apr 15 2026,11:20:35"}


def test_driver_read_init_info_and_max_travel():
    dev = ReadableDevice(_capture_reply_fn)
    d = Win60Driver(None, dev, threading.RLock())
    info = d.read_init_info(timeout_s=0.5)
    assert info["is_dead_band"] is True and info["is_gamepad"] is False
    mt = d.read_max_trigger_travel(high_precision=info["is_high_precision"],
                                   timeout_s=0.5)
    assert mt["unit_mm"] == 0.01
    assert mt["max_travel_raw"] == 340 and mt["min_travel_raw"] == 8


def test_driver_set_music_rhythm():
    dev = ReadableDevice()
    d = Win60Driver(None, dev, threading.RLock())
    d.set_music_rhythm(False)
    d.set_music_rhythm(True)
    assert dev.writes == [protocol.build_music_rhythm(False),
                          protocol.build_music_rhythm(True)]


# ================================= custom per-key light slots (cmd 9) ======
# CONFIRMED-BY-CAPTURE: the cmd-9 table is board-persistent Per-key Paint
# storage with TWO slots (vendor UI Custom1/Custom2), read back with
# [1]=0x80|slot and queried for the active slot with [1]=0x20
# (initCustomNumber). This is the Win60's equivalent of the MINI 60 HE
# PRO's persistent 0x24 table.

def test_custom_light_read_requests_match_capture():
    (_, req0), = _outs(lambda b: b[0] == 0x09 and b[1] == 0x80)[:1]
    (_, req1), = _outs(lambda b: b[0] == 0x09 and b[1] == 0x81)[:1]
    assert protocol.build_read_custom_light(0)[1:] == req0
    assert protocol.build_read_custom_light(1)[1:] == req1
    # absolute offsets: bare request, [1] = 0x80|slot, everything else 0
    assert req0[1] == 0x80 and req1[1] == 0x81
    assert all(x == 0 for x in req0[2:]) and all(x == 0 for x in req1[2:])
    for bad in (-1, 2, protocol.CUSTOM_LIGHT_SLOTS):
        with pytest.raises(ValueError):
            protocol.build_read_custom_light(bad)


def test_custom_light_read_chunks_assemble_to_396_bytes():
    assert _CL0_TABLE is not None and len(_CL0_TABLE) == 396
    assert _CL1_TABLE is not None and len(_CL1_TABLE) == 396
    # chunk framing, absolute offsets: 7 x 54 + 18, pages 0..7 BE at [2:4]
    assert [b[4] for b in _CL0_READ] == [0x36] * 7 + [0x12]
    assert [(b[2] << 8) | b[3] for b in _CL0_READ] == list(range(8))
    # absolute wire offsets inside the reassembled table: page-2 payload
    # byte 0 lands at table[108] and reads 0x09 on the wire
    assert _CL0_READ[2][5] == 0x09 and _CL0_TABLE[108] == 0x09
    # key 22 (first physical key, row 1) stored 45/0/184 at table[66..68]
    assert list(_CL0_TABLE[66:69]) == [45, 0, 184]


def test_custom_light_slots_persist_on_board():
    """THE PARITY CRUX: both slots came back NON-ZERO at mount, BEFORE this
    session's first cmd-9 table write — the content was stored by a previous
    session. The cmd-9 table is persistent board storage (the MINI's 0x24
    equivalent), not a volatile stream."""
    first_read_idx = _ins(lambda b: b[0] == 0x09 and b[1] == 0x80)[0][0]
    first_write_idx = _outs(lambda b: b[0] == 0x09 and b[1] in (0, 1)
                            and b[4] > 0)[0][0]
    assert first_read_idx < first_write_idx
    assert any(_CL0_TABLE) and any(_CL1_TABLE)
    # the 61 keys lit in the stored slot-0 palette are exactly the board's
    # 61 physical keys (same set as the dead-band/trigger-mask evidence)
    lit = [i for i in range(132) if any(_CL0_TABLE[3 * i:3 * i + 3])]
    assert lit == _PHYS


def test_custom_light_write_slot1_matches_capture():
    """build_custom_light(slot=1) reproduces the vendor's Custom2 palette
    write byte-for-byte — the slot the capture notes flagged as unused by
    Aether."""
    wire = [b for _, b in _CL1_WRITE]
    colors = protocol.custom_light_colors(_CL1_TABLE)
    built = [p[1:] for p in protocol.build_custom_light(colors, slot=1)]
    assert built == wire
    # absolute offsets: slot byte [1]=1 on every chunk, 54-byte pages,
    # 18-byte tail
    assert all(b[1] == 1 for b in wire)
    assert [b[4] for b in wire] == [0x36] * 7 + [0x12]
    # the write re-sent EXACTLY the stored table read at mount (vendor
    # switches palettes by re-sending the slot's table — no separate
    # "activate slot" command exists)
    assert protocol.assemble_custom_light_table(
        [protocol.parse_custom_light_chunk(
            [0x09, 0x81] + b[2:], 1) for b in wire]) == _CL1_TABLE


def test_custom_light_round_trip_slot0_matches_capture():
    """read -> custom_light_colors -> build_custom_light is byte-exact
    against the vendor's Custom1 restore write."""
    wire = [b for _, b in _CL0_WRITE]
    colors = protocol.custom_light_colors(_CL0_TABLE)
    assert len(colors) == 132
    built = [p[1:] for p in protocol.build_custom_light(colors, slot=0)]
    assert built == wire
    # absolute offsets: page-2 chunk opens with the gradient bytes seen on
    # the wire at payload start [5..7]
    assert wire[2][5:8] == [0x09, 0x99, 0x1A]


def test_custom_number_query_matches_capture():
    (_, req), = _outs(lambda b: b[0] == 0x09 and b[1] == 0x20)[:1]
    assert protocol.build_read_custom_number()[1:] == req
    # absolute offsets: bare `09 20`
    assert req[0] == 0x09 and req[1] == 0x20 and all(x == 0 for x in req[2:])
    (_, rep), = _ins(lambda b: b[0] == 0x09 and b[1] in (0, 1))[:1]
    # the mount reply says slot 0 (Custom1) is active, len byte 0
    assert rep[1] == 0 and rep[4] == 0
    assert protocol.parse_custom_number(rep) == 0


def test_custom_light_parsers_reject_foreign_bodies():
    # a table chunk is not a custom-number reply
    assert protocol.parse_custom_number(_CL0_READ[0]) is None
    # the custom-number reply is not a table chunk (len 0)
    (_, rep), = _ins(lambda b: b[0] == 0x09 and b[1] in (0, 1))[:1]
    assert protocol.parse_custom_light_chunk(rep, 0) is None
    # slot mismatch: slot-1 chunks don't parse as slot 0 and vice versa
    assert protocol.parse_custom_light_chunk(_CL1_READ[0], 0) is None
    assert protocol.parse_custom_light_chunk(_CL0_READ[0], 1) is None
    # incomplete read -> None, never a half-zeroed table
    assert protocol.assemble_custom_light_table(
        [protocol.parse_custom_light_chunk(b, 0)
         for b in _CL0_READ[:7]]) is None


def test_driver_read_per_key_rgb_from_captured_chunks():
    dev = ReadableDevice(_capture_reply_fn)
    d = Win60Driver(None, dev, threading.RLock())
    colors0 = d.read_per_key_rgb(slot=0, timeout_s=0.5)
    assert len(colors0) == 132
    assert colors0[22] == (45, 0, 184)      # absolute: table[66..68]
    assert colors0[0] == (0, 0, 0)          # unpopulated slot stays dark
    colors1 = d.read_per_key_rgb(slot=1, timeout_s=0.5)
    assert colors1[45] == (0, 0, 255)       # Custom2's stored blue block


def test_driver_read_active_custom_slot():
    dev = ReadableDevice(_capture_reply_fn)
    d = Win60Driver(None, dev, threading.RLock())
    assert d.read_active_custom_slot(timeout_s=0.5) == 0


def test_driver_set_per_key_rgb_default_is_byte_identical():
    """REGRESSION GUARD: the default call (no slot, no cumulative) emits
    exactly what it always did — mode-10 light write + slot-0 table."""
    dev = ReadableDevice()
    d = Win60Driver(None, dev, threading.RLock())
    colors = {22: (45, 0, 184), 90: (1, 2, 3)}
    d.set_per_key_rgb(colors)
    expect = ([protocol.build_light(10, 4, 4, (255, 255, 255))]
              + protocol.build_custom_light(colors, slot=0))
    assert dev.writes == expect
    # absolute offsets in the wrapped packets: [0]=report id, [1]=cmd 9,
    # [2]=slot 0
    assert dev.writes[1][1] == 0x09 and dev.writes[1][2] == 0x00


def test_driver_set_per_key_rgb_slot1_targets_second_palette():
    dev = ReadableDevice()
    d = Win60Driver(None, dev, threading.RLock())
    colors = protocol.custom_light_colors(_CL1_TABLE)
    d.set_per_key_rgb(colors, slot=1)
    table_writes = dev.writes[1:]
    assert table_writes == protocol.build_custom_light(colors, slot=1)
    assert all(w[2] == 0x01 for w in table_writes)
    # and those bytes are the captured Custom2 write, byte-for-byte
    assert [w[1:] for w in table_writes] == [b for _, b in _CL1_WRITE]


def test_driver_set_per_key_rgb_cumulative_preserves_stored_colors():
    """MINI-parity Paint semantics: painting ONE key merges into the
    board's stored slot table instead of darkening every other key."""
    dev = ReadableDevice(_capture_reply_fn)
    d = Win60Driver(None, dev, threading.RLock())
    d.set_per_key_rgb({0: (255, 0, 0)}, cumulative=True)
    # read request first, then mode 10, then the merged table
    assert dev.writes[0] == protocol.build_read_custom_light(0)
    assert dev.writes[1] == protocol.build_light(10, 4, 4, (255, 255, 255))
    merged = protocol.custom_light_colors(_CL0_TABLE)
    merged[0] = (255, 0, 0)
    assert dev.writes[2:] == protocol.build_custom_light(merged, slot=0)
    # absolute offsets: key 0 painted at page-0 payload start...
    assert dev.writes[2][6:9] == [255, 0, 0]
    # ...key 22 PRESERVED at its stored 45/0/184 (table[66] = page 1,
    # payload offset 12 -> wrapped packet index 6+12)
    assert dev.writes[3][18:21] == [45, 0, 184]


def test_driver_set_per_key_rgb_cumulative_aborts_when_read_fails():
    """No reply -> RuntimeError BEFORE the mode write or any table write
    (never blind-darken the keys the user didn't touch)."""
    dev = ReadableDevice(reply_fn=None)
    d = Win60Driver(None, dev, threading.RLock())
    d.CUSTOM_READ_TIMEOUT_S = 0.05
    with pytest.raises(RuntimeError):
        d.set_per_key_rgb({0: (255, 0, 0)}, cumulative=True)
    assert dev.writes == [protocol.build_read_custom_light(0)]
