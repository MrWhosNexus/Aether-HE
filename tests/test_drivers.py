"""Tests for the per-board protocol dispatch layer (drivers/).

No hardware: devices are stubs, HID enumeration is injected. Win60 byte
streams are asserted against protocol.py builders (the refactor must be
byte-identical); MINI60 frames against protocol_mini60 builders and a fake
board that serves 0x55 replies from in-memory tables.
"""
import threading
import types

import pytest

import boards
import protocol
import protocol_mini60 as pm
import drivers
from drivers import (UnsupportedFeature, NullDriver, Win60Driver,
                     Mini60Driver, get_driver, connected_profiles)
from drivers import mini60 as mini60_mod


# ---------------------------------------------------------------- stubs ----
class StubDevice:
    """Fake aula_device.AulaDevice: records writes, serves queued replies."""

    def __init__(self, reply_fn=None, start_open=True):
        self.writes = []          # every payload passed to write()
        self.replies = []         # frames returned by read(), FIFO
        self.reply_fn = reply_fn  # fn(report) -> list of reply frames
        self.opens = 0
        self._open = start_open
        self._lock = threading.Lock()
        self._dev = None          # win60 read paths poke _dev; None is safe

    def open(self):
        self.opens += 1
        self._open = True
        return {"interface_number": 2, "usage_page": 0xFF68, "path": b"stub"}

    def close(self):
        self._open = False

    def is_open(self):
        return self._open

    def write(self, payload):
        self.writes.append(list(payload))
        if self.reply_fn:
            self.replies.extend(self.reply_fn(list(payload)) or [])
        return len(payload)

    def read(self, length, timeout_ms=0):
        return self.replies.pop(0) if self.replies else []


class FakeMiniBoard:
    """In-memory MINI 60 HE PRO: answers paged reads from stored tables and
    applies paged writes to them, echoing write frames with the 0x55 ack
    magic exactly like the real firmware does. `frame_len` selects the
    transport (64 = wired USB-C, 32 = the 2.4GHz dongle — the RF bridge is
    transparent to the firmware, so the same tables answer at either
    size)."""

    def __init__(self, prefix_report_id=False, frame_len=pm.FRAME_LEN):
        self.frame_len = frame_len
        self.act_table = bytearray(pm.ACT_TABLE_SIZE)
        self.config = bytearray(pm.CONFIG_TABLE_SIZE)
        self.led_table = bytearray(pm.CUSTOM_LED_TABLE_SIZE)
        self.key_table = bytearray(pm.KEY_TABLE_SIZE)      # 0x12/0x22
        self.macro_table = bytearray(2048)                 # 0x15/0x25
        self.light = pm.build_light(pm.LIGHT_MODE_STATIC,
                                    frame_len=frame_len)   # stored 0x23 block
        self.prefix = prefix_report_id
        self.fail_reads_from = None   # table offset: stop answering (timeout test)

    def _wrap(self, frame):
        return ([0x00] + list(frame)) if self.prefix else list(frame)

    def reply(self, report):
        frame = report[1:]            # strip the 0x00 report id
        if not frame or frame[0] != pm.MAGIC:
            return []
        assert len(frame) == self.frame_len, (
            f"frame of {len(frame)} bytes at a {self.frame_len}-byte-report "
            f"interface — the truncation bug the drivers must never repeat")
        cmd, ln = frame[1], frame[2]
        off = frame[3] | (frame[4] << 8)
        read_tables = {0x17: self.act_table, 0x11: self.config,
                       0x14: self.led_table, 0x12: self.key_table,
                       0x15: self.macro_table}
        if cmd in read_tables:
            if self.fail_reads_from is not None and off >= self.fail_reads_from:
                return []
            t = read_tables[cmd]
            r = [0] * self.frame_len
            r[0], r[1], r[2], r[3], r[4], r[6] = (pm.REPLY_MAGIC, cmd, ln,
                                                  frame[3], frame[4], frame[6])
            chunk = t[off:off + ln]
            r[8:8 + len(chunk)] = list(chunk)
            return [self._wrap(r)]
        if cmd == pm.CMD_DEVICE_INFO:
            # echoes the request header (offset included — the handshake
            # capture shows the real firmware does exactly this); VID/PID
            # ride in the offset-0 reply
            r = [0] * self.frame_len
            r[0], r[1], r[2], r[3], r[4], r[6] = (pm.REPLY_MAGIC, cmd, ln,
                                                  frame[3], frame[4], frame[6])
            if off == 0:
                r[12], r[13], r[14], r[15] = 0x45, 0x0C, 0xA2, 0x80
            return [self._wrap(r)]
        if cmd == pm.CMD_LIGHT_READ:
            # Reply echoes the 0x13 request header with the current lighting
            # block in the same field positions the 0x23 write uses.
            r = list(self.light)
            r[0], r[1], r[2], r[3], r[4] = (pm.REPLY_MAGIC, cmd, ln,
                                            frame[3], frame[4])
            return [self._wrap(r)]
        # writes: apply to the table and echo-ack like the firmware
        write_tables = {0x27: self.act_table, 0x21: self.config,
                        0x24: self.led_table, 0x22: self.key_table,
                        0x25: self.macro_table}
        if cmd in write_tables:
            t = write_tables[cmd]
            for j in range(min(ln, self.frame_len - pm.PAYLOAD_START)):
                if off + j < len(t):
                    t[off + j] = frame[pm.PAYLOAD_START + j]
        elif cmd == pm.CMD_LIGHTING:
            self.light = list(frame)
        echo = list(frame)
        echo[0] = pm.REPLY_MAGIC
        return [self._wrap(echo)]


def _profile(slug, vid, pid, proto, caps=None, name=None):
    return boards.BoardProfile(
        slug=slug, name=name or slug, vid=vid, pid=pid, form_factor="60%",
        usage_page=None, keymap="ui/keymap.json", protocol=proto,
        capabilities=dict(caps or {}), status="test", issues=())


WIN60 = _profile("win60", 0x2E3C, 0xC365, "protocol", name="Aula Win60 HE")
MINI_PRO = _profile("mini60-pro", 0x0C45, 0x80A2, "protocol_mini60",
                    caps={"lighting": True, "actuation": True, "perKeyRgb": True},
                    name="Aula Mini 60 HE Pro (wired)")
MINI_MAX = _profile("mini60-max", 0x0C45, 0x80A1, "protocol_sonix")
# A protocol-less stand-in for NullDriver / non-drivable tests. Historical
# name: the REAL dongle entry became drivable on 2026-07-20 (its slug is
# aula-mini60he-pro-24g in the real registry; this stub's fake slug keeps it
# out of the frameLen lookup) — this stub now models any not-yet-decoded
# board, which is still exactly what NullDriver exists for.
DONGLE = _profile("mini60-pro-24g", 0x0C45, 0xFEFE, None,
                  name="Aula Mini 60 HE Pro (2.4GHz dongle)")


def _mini(board=None):
    board = board or FakeMiniBoard()
    dev = StubDevice(reply_fn=board.reply)
    return Mini60Driver(MINI_PRO, dev, threading.Lock()), dev, board


def _win():
    dev = StubDevice()
    return Win60Driver(WIN60, dev, threading.Lock()), dev


def _frames(dev, cmd=None):
    """MINI frames written to the stub (report id stripped), optionally
    filtered by command byte."""
    out = [w[1:] for w in dev.writes]
    return [f for f in out if cmd is None or f[1] == cmd]


# --------------------------------------------------------------- factory ----
def test_factory_maps_protocol_field():
    dev = StubDevice()
    assert isinstance(get_driver(WIN60, dev), Win60Driver)
    assert isinstance(get_driver(MINI_PRO, dev), Mini60Driver)
    assert isinstance(get_driver(DONGLE, dev), NullDriver)          # protocol null
    assert isinstance(get_driver(MINI_MAX, dev), NullDriver)        # module w/o driver
    assert isinstance(get_driver(None, dev), Win60Driver)           # legacy fallback


def test_null_driver_refuses_every_write_and_sends_nothing():
    dev = StubDevice()
    d = NullDriver(DONGLE, dev)
    ops = [
        lambda: d.set_lighting(0, (255, 0, 0)),
        lambda: d.get_lighting(),
        lambda: d.set_actuation([0], 0, 1.5),
        lambda: d.get_actuation(),
        lambda: d.read_actuation(None),
        lambda: d.set_per_key_rgb({0: (1, 2, 3)}),
        lambda: d.begin_host_stream(),
        lambda: d.stream_frame({0: (1, 2, 3)}),
        lambda: d.set_deadband({}, top_mm=0.1),
        lambda: d.set_switch({0: 1}),
        lambda: d.set_poll_rate(1),
        lambda: d.write_keymap({}, {}, set(), None),
        lambda: d.read_keymap_layer(),
        lambda: d.set_socd([]),
        lambda: d.set_calibration(True),
        lambda: d.make_live_reader(None),
        lambda: d.make_calibration_reader(None),
        lambda: d.open_trigger_test([0]),
        lambda: d.close_trigger_test(),
        lambda: d.set_gamepad_mode(True),
        lambda: d.device_info(),
    ]
    for op in ops:
        with pytest.raises(UnsupportedFeature):
            op()
    assert dev.writes == []          # inert means ZERO bytes on the wire


def test_unsupported_feature_carries_board_and_feature():
    d = NullDriver(DONGLE, StubDevice())
    with pytest.raises(UnsupportedFeature) as ei:
        d.set_lighting(0, (1, 2, 3))
    e = ei.value
    assert e.board == DONGLE.name and e.feature == "lighting"
    assert DONGLE.name in str(e) and "lighting" in str(e)


# ----------------------------------------------------------------- win60 ----
def test_win60_connect_opens_then_heartbeats():
    d, dev = _win()
    info = d.connect()
    assert info["interface_number"] == 2
    assert dev.writes == [protocol.build_heartbeat()]


def test_win60_lighting_bytes_unchanged():
    d, dev = _win()
    d.set_lighting(2, (10, 20, 30), bg=(1, 2, 3), brightness=3, speed=1,
                   direction=1, full_color=0, power_on=True)
    assert dev.writes == [protocol.build_light(2, 3, 1, (10, 20, 30),
                                               (1, 2, 3), 1, 0, True)]


def test_win60_actuation_bytes_unchanged():
    d, dev = _win()
    d.set_actuation([0, 5, 23], 12, 1.5, 0.3, 0.25)
    assert dev.writes == [protocol.build_trigger(12, [0, 5, 23], 1.5, 0.3, 0.25)]


def test_win60_per_key_rgb_bytes_unchanged():
    d, dev = _win()
    colors = {0: (255, 0, 0), 7: (0, 255, 0)}
    d.set_per_key_rgb(colors, brightness=4, speed=4)
    expect = ([protocol.build_light(10, 4, 4, (255, 255, 255))]
              + protocol.build_custom_light(colors, slot=0))
    assert dev.writes == expect


def test_win60_stream_frame_diff_cache():
    d, dev = _win()
    frame = {0: (255, 0, 0)}
    d.stream_frame(frame)
    n_pages = len(protocol.build_custom_light(frame, slot=0))
    assert len(dev.writes) == n_pages           # first frame: all pages
    d.stream_frame(frame)
    assert len(dev.writes) == n_pages           # identical frame: nothing sent
    d.stream_frame({0: (255, 0, 0), 1: (0, 255, 0)})
    assert len(dev.writes) == n_pages + 1       # key 1 lives in page 0 only
    d.stream_frame({0: (255, 0, 0), 1: (0, 255, 0)}, force=True)
    assert len(dev.writes) == 2 * n_pages + 1   # force resends every page


def test_win60_deadband_switch_socd_poll_gamepad_bytes():
    d, dev = _win()
    d.set_deadband({3: (4, 5), 7: (10, 12)})
    assert dev.writes == protocol.build_deadband_table({3: (4, 5), 7: (10, 12)})
    dev.writes.clear()
    d.set_switch({0: 2, 9: 1})
    assert dev.writes == protocol.build_switch_table({0: 2, 9: 1})
    dev.writes.clear()
    plist = [{"model": 1, "key1_hid": 4, "key2_hid": 7}]
    d.set_socd(plist)
    assert dev.writes == [protocol.build_prcs_power(True)] + protocol.build_prcs(plist)
    dev.writes.clear()
    d.set_poll_rate(3)
    assert dev.writes == [protocol.build_poll_rate(3)]
    dev.writes.clear()
    d.set_gamepad_mode(True)
    assert dev.writes == [protocol.build_gamepad_mode(1)]
    dev.writes.clear()
    d.open_trigger_test([0, 1, 2])
    d.close_trigger_test()
    assert dev.writes == [protocol.build_open_trigger_test([0, 1, 2]),
                          protocol.build_close_trigger_test()]


def test_win60_write_keymap_base_then_fn_and_fn_skip():
    d, dev = _win()
    defaults = {0: 0x29, 1: 0x1E}
    fn_raw = bytes([0, 1] * 264)
    d.write_keymap(defaults, {1: 0x04}, set(), fn_raw)
    expect = (protocol.build_base_keymap_table(defaults, {1: 0x04},
                                               layer_indices=set())
              + protocol.build_fn_keymap_table(fn_raw))
    assert dev.writes == expect
    dev.writes.clear()
    d.write_keymap(defaults, {}, set(), None)    # no snapshot -> fn skipped
    assert dev.writes == protocol.build_base_keymap_table(defaults, {},
                                                          layer_indices=set())


def test_win60_write_auto_opens_closed_device():
    d, dev = _win()
    dev.close()
    d.set_poll_rate(1)
    assert dev.opens == 1 and dev.writes


# ---------------------------------------------------------------- mini60 ----
def test_mini60_every_write_is_report_id_prefixed_vendor_frame():
    d, dev, board = _mini()
    d.set_lighting(0, (1, 2, 3))
    d.set_per_key_rgb({0: (9, 9, 9)})
    for w in dev.writes:
        assert w[0] == 0x00 and w[1] == pm.MAGIC and len(w) == 65


def test_mini60_lighting_mode_translation_and_clamps():
    d, dev, board = _mini()
    d.set_lighting(0, (10, 20, 30), brightness=4, speed=4)   # Api static
    assert dev.writes[-1] == pm.to_report(
        pm.build_light(pm.LIGHT_MODE_STATIC, 10, 20, 30, 4, 4))
    d.set_lighting(10, (1, 1, 1))                            # Api custom slot
    assert dev.writes[-1][9] == pm.LIGHT_MODE_CUSTOM
    d.set_lighting(0, (1, 1, 1), power_on=False)             # off = MINI mode 0
    assert dev.writes[-1][9] == 0
    d.set_lighting(0, (1, 1, 1), brightness=99, speed=77)    # clamp to 0..5
    assert dev.writes[-1][18] == 5 and dev.writes[-1][19] == 5
    with pytest.raises(ValueError):
        d.set_lighting(42, (1, 1, 1))                        # out of native range


def test_mini60_get_lighting_parses_stored_block():
    d, dev, board = _mini()
    board.light = pm.build_light(7, 11, 22, 33, brightness=2, speed=3)
    out = d.get_lighting()
    assert out == {"mode": 7, "rgb": [11, 22, 33], "brightness": 2, "speed": 3}


def test_mini60_device_info_round_trip():
    d, dev, board = _mini()
    assert d.device_info() == {"vid": 0x0C45, "pid": 0x80A2,
                               "vidPid": "0C45:80A2"}


def test_mini60_actuation_reads_full_table_before_writing():
    d, dev, board = _mini()
    d.set_actuation([3], 0, 1.5)
    reads = _frames(dev, pm.CMD_ACTUATION_READ)
    writes = _frames(dev, pm.CMD_ACTUATION)
    assert len(reads) == 18 and len(writes) == 18
    # every read precedes every write (strict read-modify-write)
    cmds = [f[1] for f in _frames(dev) if f[1] in (0x17, 0x27)]
    assert cmds == [0x17] * 18 + [0x27] * 18
    # final page carries the last-chunk flag
    assert writes[-1][6] == 0x01 and writes[-1][3] | (writes[-1][4] << 8) == 0x03B8


def test_mini60_actuation_rmw_preserves_other_keys_and_axis():
    board = FakeMiniBoard()
    # pre-existing record at slot 5: axisType 2, flags 3 (RT + rampage),
    # trip 2.00mm, press 1.00mm, release 0.50mm
    board.act_table[40:48] = bytes([2, 3, 200, 0, 100, 0, 50, 0])
    d, dev, _ = _mini(board)
    d.set_actuation([3], 0, 1.5)
    # slot 3 written: axis 0, flags 0, trip 150 LE, RT fields zero
    assert list(board.act_table[24:32]) == [0, 0, 150, 0, 0, 0, 0, 0]
    # slot 5 untouched, byte-identical (axisType kept — the RMW guarantee)
    assert list(board.act_table[40:48]) == [2, 3, 200, 0, 100, 0, 50, 0]


def test_mini60_actuation_rt_modes_and_flag_bits():
    board = FakeMiniBoard()
    board.act_table[40:48] = bytes([2, 3, 200, 0, 100, 0, 50, 0])
    d, dev, _ = _mini(board)
    # RT single (Win60 mode 12): release defaults to press; bit1 preserved
    d.set_actuation([5], 12, 2.0, 0.5)
    assert list(board.act_table[40:48]) == [2, 3, 200, 0, 50, 0, 50, 0]
    # back to fixed: RT bit cleared, rampage bit + sensitivities kept
    d.set_actuation([5], 0, 1.0)
    assert list(board.act_table[40:48]) == [2, 2, 100, 0, 50, 0, 50, 0]
    # RT separate (mode 13)
    d.set_actuation([5], 13, 3.0, 1.25, 0.75)
    assert list(board.act_table[40:48]) == [2, 3, 44, 1, 125, 0, 75, 0]


def test_mini60_actuation_aborts_on_partial_read_without_writing():
    board = FakeMiniBoard()
    board.fail_reads_from = 3 * pm.PAGE      # board goes silent from page 3
    d, dev, _ = _mini(board)
    with pytest.raises(IOError):
        d.set_actuation([3], 0, 1.5)
    assert _frames(dev, pm.CMD_ACTUATION) == []   # never blind-writes


def test_mini60_get_actuation_decodes_populated_slots():
    board = FakeMiniBoard()
    board.act_table[40:48] = bytes([2, 1, 200, 0, 100, 0, 50, 0])
    d, dev, _ = _mini(board)
    out = d.get_actuation()
    assert set(out) == {5}
    assert out[5] == {"rt": True, "travel_mm": 2.0, "rt_press_mm": 1.0,
                      "rt_release_mm": 0.5, "axis_type": 2}


def test_mini60_per_key_rgb_mode20_then_full_table():
    d, dev, board = _mini()
    d.set_per_key_rgb({3: (1, 2, 3)}, brightness=4, speed=4)
    light = _frames(dev, pm.CMD_LIGHTING)
    assert light and light[0][8] == pm.LIGHT_MODE_CUSTOM
    pages = _frames(dev, pm.CMD_SET_CUSTOM_LED)
    assert len(pages) == 9 and pages[-1][6] == 0x01
    assert list(board.led_table[12:16]) == [3, 1, 2, 3]
    # cumulative: a second paint keeps the first key's color
    d.set_per_key_rgb({7: (9, 8, 7)})
    assert list(board.led_table[12:16]) == [3, 1, 2, 3]
    assert list(board.led_table[28:32]) == [7, 9, 8, 7]


def test_mini60_connect_seeds_led_state_from_board():
    board = FakeMiniBoard()
    board.led_table[28:32] = bytes([7, 10, 20, 30])
    d, dev, _ = _mini(board)
    d.connect()
    d.set_per_key_rgb({0: (1, 1, 1)})
    # key 7's stored color survives a paint that didn't mention it
    assert list(board.led_table[28:32]) == [7, 10, 20, 30]


# ------------------------------------------------- mini60 host stream (0x32) ----
def test_mini60_stream_frame_builder_golden_absolute_offsets():
    """Pin the 0x32 frame layout against the DOCUMENTED byte positions with
    ABSOLUTE offsets — not build<->parse symmetry (that class of bug already
    bit this project: a symmetric-but-wrong layout golden-tests clean).
    Layout (HARDWARE-VERIFIED 2026-07-20 + vendor gifLight source):
    [0]=0xAA [1]=0x32 [2]=0x38 [3..4]=LE16 offset [5]=0 [6]=last-chunk
    [7]=0, payload from byte 8 = (keyIndex, R, G, B) quads."""
    colors = [(0, 0, 0)] * pm.CUSTOM_LED_COUNT
    colors[0] = (0x11, 0x22, 0x33)
    colors[3] = (1, 2, 3)
    colors[14] = (40, 50, 60)     # table byte 56 — first record of chunk 2
    colors[125] = (9, 8, 7)       # last record of the table
    frames = mini60_mod.build_stream_frames(pm.build_custom_led_table(colors))

    assert len(frames) == 9                       # 9 chunks x 56 = 504 bytes
    assert all(len(f) == 64 for f in frames)
    # chunk headers, byte by byte, absolute positions
    for n, f in enumerate(frames):
        off = n * 56
        assert f[0] == 0xAA
        assert f[1] == 0x32
        assert f[2] == 0x38                       # 56 payload bytes per chunk
        assert f[3] == off & 0xFF                 # LE16 byte offset...
        assert f[4] == (off >> 8) & 0xFF          # ...low byte FIRST
        assert f[5] == 0
        assert f[6] == (0x01 if n == 8 else 0x00)  # last-chunk flag only on 9th
        assert f[7] == 0
    # LE16 pin with a nonzero high byte: chunk 8 @ 0x01C0 -> [3]=0xC0 [4]=0x01
    assert frames[8][3] == 0xC0 and frames[8][4] == 0x01
    # quads at absolute frame offsets: record k of the table sits at frame
    # byte 8 + (k*4 - chunk_offset), first byte = the key index itself
    assert frames[0][8:12] == [0, 0x11, 0x22, 0x33]      # key 0
    assert frames[0][20:24] == [3, 1, 2, 3]              # key 3 @ 8+12
    assert frames[1][8:12] == [14, 40, 50, 60]           # key 14 leads chunk 2
    assert frames[8][60:64] == [125, 9, 8, 7]            # key 125 ends chunk 9
    # unlit keys still carry their ledId with zero RGB (full-table stream)
    assert frames[0][12:16] == [1, 0, 0, 0]              # key 1


def test_mini60_stream_clear_frame_golden():
    """0x36 CLEAR_LED_DATA: AA 36 18 00 00 00 01 00, rest zero (length 0x18
    = the SDK transaction default for payload-less commands)."""
    f = mini60_mod.build_stream_clear()
    assert f[:8] == [0xAA, 0x36, 0x18, 0x00, 0x00, 0x00, 0x01, 0x00]
    assert f[8:] == [0] * 56 and len(f) == 64


def test_mini60_begin_stream_then_frames_are_write_only_full_frames():
    d, dev, board = _mini()
    d.begin_host_stream()
    light = _frames(dev, pm.CMD_LIGHTING)
    assert len(light) == 1 and light[0][8] == pm.LIGHT_MODE_CUSTOM
    assert light[0][17] == 5                     # full MINI brightness (0..5)
    dev.writes.clear()

    d.stream_frame({0: (255, 0, 0)})
    stream = _frames(dev, mini60_mod.CMD_STREAM_LED)
    assert len(stream) == 9                      # full frame, all 9 chunks
    assert stream[0][8:12] == [0, 255, 0, 0]
    # every write is a report-id-prefixed 65-byte vendor frame
    for w in dev.writes:
        assert w[0] == 0x00 and w[1] == pm.MAGIC and len(w) == 65

    # NO diff cache on this path: the 27.7 fps benchmark measured full
    # 9-chunk frames every time, so an identical frame sends 9 more writes
    # (`force` is signature parity only)
    d.stream_frame({0: (255, 0, 0)})
    assert len(_frames(dev, mini60_mod.CMD_STREAM_LED)) == 18
    d.stream_frame({0: (255, 0, 0)}, force=True)
    assert len(_frames(dev, mini60_mod.CMD_STREAM_LED)) == 27
    # fire-and-forget: the driver never consumed a single queued reply
    assert dev.replies


def test_mini60_stream_does_not_touch_persistent_led_state():
    """0x32 is the LIVE channel: it must never write the flash-backed 0x24
    table or the driver's Per-key Paint mirror."""
    board = FakeMiniBoard()
    board.led_table[28:32] = bytes([7, 10, 20, 30])   # stored paint on key 7
    d, dev, _ = _mini(board)
    d.connect()
    d.begin_host_stream()
    d.stream_frame({7: (255, 255, 255), 3: (1, 1, 1)})
    assert _frames(dev, pm.CMD_SET_CUSTOM_LED) == []  # zero 0x24 frames
    assert list(board.led_table[28:32]) == [7, 10, 20, 30]
    assert d._led_state[7] == (10, 20, 30)            # mirror untouched


def test_mini60_end_host_stream_sends_clear_and_win60_noop():
    d, dev, _ = _mini()
    d.end_host_stream()
    assert dev.writes == [pm.to_report(mini60_mod.build_stream_clear())]
    # Win60: end_host_stream is the base no-op — ZERO bytes (its board keeps
    # the last frame in Custom mode, the pre-existing shipped behavior)
    wd, wdev = _win()
    assert wd.end_host_stream() is None
    assert wdev.writes == []
    # NullDriver: also the safe no-op (stop must be callable from teardown)
    ndev = StubDevice()
    assert NullDriver(DONGLE, ndev).end_host_stream() is None
    assert ndev.writes == []


def test_mini60_stream_guard_blocks_dangerous_frames():
    """The NEVER-SEND guard covers the stream path too (it bypasses _send
    to hold the lock per frame, so pin the guard explicitly)."""
    d, dev, _ = _mini()
    for cmd in sorted(pm.DANGEROUS_CMDS):
        bad = [0] * pm.FRAME_LEN
        bad[0], bad[1] = pm.MAGIC, cmd
        with pytest.raises(RuntimeError):
            d._guard(bad)
    assert dev.writes == []


def test_mini60_deadband_is_global_read_modify_write():
    board = FakeMiniBoard()
    board.config[1] = 1   # gameMode
    board.config[5] = 6   # reportRate
    board.config[11] = 1  # stabilityMode
    d, dev, _ = _mini(board)
    d.set_deadband({0: (4, 5)}, top_mm=0.42, bottom_mm=0.10)
    assert len(_frames(dev, pm.CMD_CONFIG_READ)) == 2
    assert len(_frames(dev, pm.CMD_CONFIG_WRITE)) == 2
    assert board.config[8] == 42 and board.config[9] == 10   # dead zones
    assert board.config[1] == 1 and board.config[5] == 6     # rest preserved
    assert board.config[11] == 1


def test_mini60_reply_matching_skips_junk_frames():
    d, dev, board = _mini()
    junk = [0x99] * 64
    orig = board.reply
    board_replies = lambda rep: ([junk] + orig(rep))
    dev.reply_fn = board_replies
    assert d.device_info()["vid"] == 0x0C45


def test_mini60_handles_report_id_prefixed_replies():
    d, dev, board = _mini(FakeMiniBoard(prefix_report_id=True))
    assert d.device_info()["pid"] == 0x80A2
    assert d.get_lighting()["mode"] == pm.LIGHT_MODE_STATIC


def test_mini60_refuses_dangerous_commands():
    d, dev, _ = _mini()
    for cmd in sorted(pm.DANGEROUS_CMDS):
        bad = [0] * pm.FRAME_LEN
        bad[0], bad[1] = pm.MAGIC, cmd
        with pytest.raises(RuntimeError):
            d._send(bad)
    assert dev.writes == []


# ------------------------------------------------------------ mini60 macros ----
M1_EVENTS = [(10, 0x04, True), (10, 0x04, False),
             (300, 0x05, True), (10, 0x05, False)]
M2_EVENTS = [(11, 0x1B, True), (22, 0x1B, False),
             (33, 0x1C, True), (44, 0x1C, False),
             (55, 0x1D, True), (66, 0x1D, False),
             (770, 0xE1, True), (888, 0xE1, False)]


def test_mini60_supports_macros_feature():
    d, dev, _ = _mini()
    assert d.supports("macros")
    assert "macros" in Mini60Driver.FEATURES


def test_null_driver_refuses_macro_ops():
    dev = StubDevice()
    d = NullDriver(DONGLE, dev)
    ops = [
        lambda: d.list_macros(),
        lambda: d.read_macro(0),
        lambda: d.write_macro(0, M1_EVENTS),
        lambda: d.bind_macro(87, 1),
        lambda: d.unbind_key(87),
    ]
    for op in ops:
        with pytest.raises(UnsupportedFeature) as ei:
            op()
        assert ei.value.feature == "macros"
    assert dev.writes == []


def test_mini60_write_macro_header_then_body():
    d, dev, board = _mini()
    d.write_macro(0, M1_EVENTS)
    # header entry 0 = 400 LE32, body packed at byte 400
    assert list(board.macro_table[0:4]) == [0x90, 0x01, 0x00, 0x00]
    assert list(board.macro_table[400:420]) == pm.encode_macro_events(M1_EVENTS)
    # strict read-modify-write: the header sweep precedes every 0x25 write
    cmds = [f[1] for f in _frames(dev) if f[1] in (0x15, 0x25)]
    assert cmds == [0x15] * 8 + [0x25] * 9
    writes = _frames(dev, 0x25)
    assert writes[-1][6] == 0x01           # body chunk carries the final flag
    assert writes[7][6] == 0x01            # header tail (0x0188) does too
    assert writes[7][2] == 0x08


def test_mini60_write_macro_rmw_preserves_other_slots():
    board = FakeMiniBoard()
    seed = pm.build_macro_table({0: M1_EVENTS})
    board.macro_table[:len(seed)] = bytes(seed)
    d, dev, _ = _mini(board)
    d.write_macro(1, M2_EVENTS)
    got = pm.parse_macro_table(list(board.macro_table))
    assert got == {0: M1_EVENTS, 1: M2_EVENTS}


def test_mini60_write_macro_empty_deletes_slot():
    board = FakeMiniBoard()
    seed = pm.build_macro_table({0: M1_EVENTS, 1: M2_EVENTS})
    board.macro_table[:len(seed)] = bytes(seed)
    d, dev, _ = _mini(board)
    d.write_macro(0, None)
    got = pm.parse_macro_table(list(board.macro_table))
    assert got == {1: M2_EVENTS}
    # macro 1's body was repacked to byte 400
    assert pm.parse_macro_header(list(board.macro_table))[:2] == [0, 400]


def test_mini60_list_and_read_macros_two_step_read():
    board = FakeMiniBoard()
    seed = pm.build_macro_table({0: M1_EVENTS, 1: M2_EVENTS})
    board.macro_table[:len(seed)] = bytes(seed)
    d, dev, _ = _mini(board)
    assert d.list_macros() == {0: M1_EVENTS, 1: M2_EVENTS}
    # the vendor two-step body read: 4-byte count at the offset, then the
    # event bytes at offset+4
    reads = _frames(dev, 0x15)
    assert [(f[2], f[3] | (f[4] << 8)) for f in reads[8:12]] == \
        [(4, 400), (16, 404), (4, 420), (32, 424)]
    assert d.read_macro(1) == M2_EVENTS
    assert d.read_macro(5) is None
    with pytest.raises(ValueError):
        d.read_macro(100)


def test_mini60_write_macro_aborts_on_partial_read():
    board = FakeMiniBoard()
    board.fail_reads_from = 2 * pm.PAGE     # header sweep dies at page 2
    d, dev, _ = _mini(board)
    with pytest.raises(IOError):
        d.write_macro(0, M1_EVENTS)
    assert _frames(dev, 0x25) == []          # never blind-writes


def test_mini60_bind_macro_is_strict_rmw():
    board = FakeMiniBoard()
    board.key_table[5 * 4:5 * 4 + 4] = bytes(pm.key_record_remap(0x29))
    d, dev, _ = _mini(board)
    d.bind_macro(87, 1, play_mode=0, loop_count=1)
    # the captured record, byte for byte
    assert list(board.key_table[87 * 4:87 * 4 + 4]) == [0x06, 0x01, 0x00, 0x01]
    # pre-existing record untouched
    assert list(board.key_table[5 * 4:5 * 4 + 4]) == [0x02, 0x00, 0x29, 0x00]
    # read sweep (10 frames to 512) precedes the write sweep (9 frames to 504)
    cmds = [f[1] for f in _frames(dev) if f[1] in (0x12, 0x22)]
    assert cmds == [0x12] * 10 + [0x22] * 9
    for f in _frames(dev, 0x22):
        assert (f[3] | (f[4] << 8)) + f[2] <= pm.KEY_TABLE_WRITE_SIZE


def test_mini60_unbind_key_clears_record_only():
    board = FakeMiniBoard()
    board.key_table[86 * 4:86 * 4 + 4] = bytes(pm.key_record_macro(0, 1, 7))
    board.key_table[87 * 4:87 * 4 + 4] = bytes(pm.key_record_macro(1, 0, 1))
    d, dev, _ = _mini(board)
    d.unbind_key(86)
    assert list(board.key_table[86 * 4:86 * 4 + 4]) == [0, 0, 0, 0]
    assert list(board.key_table[87 * 4:87 * 4 + 4]) == [0x06, 0x01, 0x00, 0x01]


def test_mini60_bind_aborts_on_partial_read_and_validates_index():
    board = FakeMiniBoard()
    board.fail_reads_from = 3 * pm.PAGE
    d, dev, _ = _mini(board)
    with pytest.raises(IOError):
        d.bind_macro(87, 0)
    assert _frames(dev, 0x22) == []
    d2, dev2, _ = _mini()
    with pytest.raises(ValueError):
        d2.bind_macro(126, 0)    # records 126/127: readable, never writable
    with pytest.raises(ValueError):
        d2.unbind_key(-1)
    with pytest.raises(ValueError):
        d2.bind_macro(0, 100)    # macro slot out of range
    assert dev2.writes == []


def test_mini60_unwired_features_refuse_loudly():
    d, dev, _ = _mini()
    ops = [
        lambda: d.set_socd([]),
        lambda: d.set_calibration(True),
        lambda: d.set_poll_rate(1),
        lambda: d.set_switch({0: 1}),
        lambda: d.write_keymap({}, {}, set(), None),
        lambda: d.read_keymap_layer(),
        lambda: d.open_trigger_test([0]),
        lambda: d.make_live_reader(None),
        lambda: d.set_gamepad_mode(True),
    ]
    for op in ops:
        with pytest.raises(UnsupportedFeature):
            op()
    assert dev.writes == []


# -------------------------------------------- mini60 over the 2.4GHz dongle ----
# One Mini60Driver serves both transports; the registry frameLen (wired 64,
# dongle 32) is the only knob. Golden facts below: WIRELESS_DONGLE_FINDINGS
# .md + webhid-capture-dongle-*.json (2026-07-20), transport HARDWARE-
# VERIFIED on usage_page 0xFF60 (lighting + 0x24 rendered visibly).

def _real(slug):
    return boards.load_registry().by_slug(slug)


def _mini_dongle():
    board = FakeMiniBoard(frame_len=32)
    dev = StubDevice(reply_fn=board.reply)
    d = Mini60Driver(_real("aula-mini60he-pro-24g"), dev, threading.Lock())
    return d, dev, board


def test_frame_len_comes_from_the_board_profile():
    """frame_len_for_profile reads the registry's raw frameLen by slug:
    wired 64 (explicit, for symmetry), dongle 32; unknown slugs and the
    legacy no-profile path default to the wired 64 so nothing changes for
    existing boards."""
    assert mini60_mod.frame_len_for_profile(_real("aula-mini60he-pro")) == 64
    assert mini60_mod.frame_len_for_profile(_real("aula-mini60he-pro-24g")) == 32
    assert mini60_mod.frame_len_for_profile(MINI_PRO) == 64   # stub slug
    assert mini60_mod.frame_len_for_profile(None) == 64
    d, _, _ = _mini()
    assert d.frame_len == 64                                  # wired stub driver
    dd, _, _ = _mini_dongle()
    assert dd.frame_len == 32


def test_dongle_driver_speaks_only_32_byte_frames():
    """Every frame the dongle-profile driver emits is 33 bytes on the wire
    (0x00 report id + 32) — never the wired 64. FakeMiniBoard(frame_len=32)
    asserts this on every reply, modelling the truncation trap: a 64-byte
    frame at the 32-byte-report 0xFF60 interface reads as 'wrong
    protocol'."""
    d, dev, board = _mini_dongle()
    d.connect()
    d.set_lighting(0, (1, 2, 3))
    info = d.device_info()
    for w in dev.writes:
        assert w[0] == 0x00 and w[1] == pm.MAGIC and len(w) == 33
    # the 0x10 sweep pages 3 frames at 32 bytes (0x18/0x18/0x08) and the
    # firmware behind the RF bridge reports the WIRED identity
    assert info == {"vid": 0x0C45, "pid": 0x80A2, "vidPid": "0C45:80A2"}


def test_dongle_lighting_matches_transcribed_capture_bytes():
    """Driver-level golden for the colorMode fix over the dongle: static
    with the capture's colour/levels reproduces the transcribed captured
    frame byte-for-byte (colorMode 0 — HARDWARE-VERIFIED to render a FIXED
    colour), and multicolour modes derive colorMode 1."""
    d, dev, board = _mini_dongle()
    d.set_lighting(0, (0x90, 0xEE, 0x90), brightness=1, speed=1)  # Api static
    static = list(bytes.fromhex(
        "AA2310000000010001" "90EE90FF000000" "000101000000AA55")) + [0] * 8
    assert dev.writes[-1] == [0x00] + static
    assert board.light[8] == 0x01 and board.light[16] == 0x00
    d.set_lighting(8, (0x90, 0xEE, 0x90), brightness=1, speed=1)  # Spectrum
    assert board.light[8] == 0x08 and board.light[16] == 0x01
    d.set_lighting(19, (0x90, 0xEE, 0x90), brightness=1, speed=1)  # Shuttle
    assert board.light[8] == 0x13 and board.light[16] == 0x01


def test_wired_driver_derives_colormode_from_registry():
    """THE user-facing bug fix, wired side: with the REAL board profile
    (which carries the lighting table), fixed-colour modes now send
    colorMode 0 so the user's chosen colour actually applies; forced-random
    modes send 1; custom (20) and lights-off keep the legacy 1 (custom's
    per-key round trip was HARDWARE-VERIFIED with 1)."""
    board = FakeMiniBoard()
    dev = StubDevice(reply_fn=board.reply)
    d = Mini60Driver(_real("aula-mini60he-pro"), dev, threading.Lock())
    assert d.frame_len == 64
    d.set_lighting(0, (255, 0, 0))            # Api static -> mode 1, fixed
    assert board.light[8] == 0x01 and board.light[16] == 0x00
    d.set_lighting(5, (255, 0, 0))            # Snowfall: colour-pickable
    assert board.light[16] == 0x00
    for native, expect in ((6, 1), (8, 1), (15, 1), (17, 1), (18, 1), (19, 1)):
        d.set_lighting(native, (255, 0, 0))   # forced-random modes
        assert board.light[8] == native and board.light[16] == expect
    d.set_lighting(20, (255, 0, 0))           # native custom byte stays 20
    assert board.light[8] == 20 and board.light[16] == 0x01
    d.set_lighting(1, (255, 0, 0), power_on=False)   # lights off -> mode 0
    assert board.light[8] == 0 and board.light[16] == 0x01


def test_wired_driver_sends_native_mode_10_as_colorful_cross():
    """REGRESSION (2026-07-21): mode byte 10 is `colorful-cross` in the MINI
    registry, and the UI's light dispatch now resolves modes against the
    ACTIVE BOARD's table and sends the board's OWN byte. The driver used to
    translate 10 -> 20 (LIGHT_MODE_CUSTOM) unconditionally — a Win60-only
    alias — which silently dropped the board into per-key Custom and
    rendered the stale/black 0x24 table while the UI showed "Colorful Cross"
    selected. A byte the board declares natively must reach the wire."""
    board = FakeMiniBoard()
    dev = StubDevice(reply_fn=board.reply)
    d = Mini60Driver(_real("aula-mini60he-pro"), dev, threading.Lock())
    d.set_lighting(10, (255, 0, 0))
    assert board.light[8] == 10               # NOT 20
    assert board.light[1] == pm.CMD_LIGHTING
    # ...and the alias survives for profiles that declare no mode table, so
    # the legacy Api vocabulary keeps working byte-for-byte there.
    legacy, ldev, lboard = _mini()             # MINI_PRO stub, lighting=None
    legacy.set_lighting(10, (255, 0, 0))
    assert lboard.light[8] == pm.LIGHT_MODE_CUSTOM


def test_wired_driver_mode_zero_still_maps_to_static_everywhere():
    """`_WIN60_MODE_STATIC = 0` must keep translating on BOTH profile kinds:
    the MINI registry declares mode 0 via `offModeByte`, not as a mode, so 0
    is never native and Api mode 0 (Win60 static) still becomes MINI static
    0x01. Guards the latent half of the same trap."""
    for profile in (_real("aula-mini60he-pro"), MINI_PRO):
        board = FakeMiniBoard()
        dev = StubDevice(reply_fn=board.reply)
        Mini60Driver(profile, dev, threading.Lock()).set_lighting(0, (1, 2, 3))
        assert board.light[8] == pm.LIGHT_MODE_STATIC


def test_stub_profile_without_lighting_table_keeps_legacy_colormode():
    """Profiles with no lighting block (legacy / tests) keep byte [16] = 1
    exactly as before the fix — the derivation only activates when the
    registry declares the mode table."""
    d, dev, board = _mini()                   # MINI_PRO stub, lighting=None
    d.set_lighting(0, (10, 20, 30), brightness=4, speed=4)
    assert dev.writes[-1] == pm.to_report(
        pm.build_light(pm.LIGHT_MODE_STATIC, 10, 20, 30, 4, 4))
    assert dev.writes[-1][17] == 0x01         # report byte 17 = frame [16]


def test_dongle_actuation_rmw_pages_42_frames():
    """Actuation over the dongle: strict read-modify-write at the wireless
    paging — 42 x 0x17 reads then 42 x 0x27 writes of 0x18-byte chunks,
    final flag on the 0x03D8 page (the captured vendor pass, golden-pinned
    in tests/test_protocol_mini60.py). RMW must preserve untouched keys
    byte-for-byte across the smaller pages."""
    board = FakeMiniBoard(frame_len=32)
    board.act_table[40:48] = bytes([2, 3, 200, 0, 100, 0, 50, 0])
    dev = StubDevice(reply_fn=board.reply)
    d = Mini60Driver(_real("aula-mini60he-pro-24g"), dev, threading.Lock())
    d.set_actuation([3], 0, 1.5)
    reads = _frames(dev, pm.CMD_ACTUATION_READ)
    writes = _frames(dev, pm.CMD_ACTUATION)
    assert len(reads) == 42 and len(writes) == 42
    cmds = [f[1] for f in _frames(dev) if f[1] in (0x17, 0x27)]
    assert cmds == [0x17] * 42 + [0x27] * 42
    assert all(f[2] == 0x18 for f in writes)
    assert writes[-1][6] == 0x01
    assert (writes[-1][3] | (writes[-1][4] << 8)) == 0x03D8
    # slot 3 written, slot 5 byte-identical (axisType + rampage preserved)
    assert list(board.act_table[24:32]) == [0, 0, 150, 0, 0, 0, 0, 0]
    assert list(board.act_table[40:48]) == [2, 3, 200, 0, 100, 0, 50, 0]
    # abort-on-partial-read holds at the wireless paging too
    board2 = FakeMiniBoard(frame_len=32)
    board2.fail_reads_from = 5 * 0x18
    dev2 = StubDevice(reply_fn=board2.reply)
    d2 = Mini60Driver(_real("aula-mini60he-pro-24g"), dev2, threading.Lock())
    with pytest.raises(IOError):
        d2.set_actuation([3], 0, 1.5)
    assert _frames(dev2, pm.CMD_ACTUATION) == []


def test_dongle_per_key_rgb_21_chunks():
    """Per-key RGB over the dongle (HARDWARE-VERIFIED 2026-07-20: mode 20 +
    solid green across all 126 keys rendered): the 504-byte 0x24 table
    pages as 21 chunks of 0x18, final flag on the 0x01E0 page."""
    d, dev, board = _mini_dongle()
    d.set_per_key_rgb({3: (1, 2, 3)}, brightness=4, speed=4)
    light = _frames(dev, pm.CMD_LIGHTING)
    assert light and light[0][8] == pm.LIGHT_MODE_CUSTOM
    assert light[0][16] == 0x01               # custom keeps the legacy byte
    pages = _frames(dev, pm.CMD_SET_CUSTOM_LED)
    assert len(pages) == 21
    assert all(p[2] == 0x18 for p in pages)
    assert [p[6] for p in pages] == [0] * 20 + [1]
    assert (pages[-1][3] | (pages[-1][4] << 8)) == 0x01E0
    assert list(board.led_table[12:16]) == [3, 1, 2, 3]


def test_dongle_host_stream_refuses_loudly():
    """hostEngine is FALSE on the dongle profile (HARDWARE-VERIFIED
    negative: the RF bridge accepts 0x32 writes and silently drops them —
    23.8 fps of zero-error no-ops with the keyboard dark, and the vendor's
    own app never streams over 2.4GHz). The driver must refuse with
    UnsupportedFeature and ZERO bytes on the wire, never pretend an
    animation is running."""
    d, dev, _ = _mini_dongle()
    with pytest.raises(UnsupportedFeature) as ei:
        d.begin_host_stream()
    assert ei.value.feature == "host_effects"
    with pytest.raises(UnsupportedFeature):
        d.stream_frame({0: (255, 0, 0)})
    assert dev.writes == []
    # end_host_stream stays teardown-safe (stop is called unconditionally)
    d.end_host_stream()
    # the WIRED profile (hostEngine true, 27.7 fps HARDWARE-VERIFIED) and
    # table-less stub profiles keep streaming exactly as before
    wboard = FakeMiniBoard()
    wdev = StubDevice(reply_fn=wboard.reply)
    wd = Mini60Driver(_real("aula-mini60he-pro"), wdev, threading.Lock())
    wd.begin_host_stream()
    assert _frames(wdev, pm.CMD_LIGHTING)[0][8] == pm.LIGHT_MODE_CUSTOM
    sd, sdev, _ = _mini()
    sd.begin_host_stream()
    assert sdev.writes


def test_dongle_deadband_config_rmw_at_32_bytes():
    """Global dead-zone RMW at the wireless paging (structural — the 0x21
    write was never captured over the bridge, which is exactly why the
    capability is 'wip'; the driver path must still be frame-size-correct
    for the bring-up check): 3 read chunks (0x18/0x18/0x10, matching the
    CAPTURED 0x11 paging) and 3 write chunks, other config bytes
    preserved."""
    board = FakeMiniBoard(frame_len=32)
    board.config[1] = 1
    board.config[5] = 6
    dev = StubDevice(reply_fn=board.reply)
    d = Mini60Driver(_real("aula-mini60he-pro-24g"), dev, threading.Lock())
    d.set_deadband({0: (4, 5)}, top_mm=0.42, bottom_mm=0.10)
    reads = _frames(dev, pm.CMD_CONFIG_READ)
    writes = _frames(dev, pm.CMD_CONFIG_WRITE)
    assert [f[2] for f in reads] == [0x18, 0x18, 0x10]
    assert [f[2] for f in writes] == [0x18, 0x18, 0x10]
    assert board.config[8] == 42 and board.config[9] == 10
    assert board.config[1] == 1 and board.config[5] == 6


def test_dongle_factory_routes_to_mini60_driver():
    """The registry's protocol_mini60 on the dongle entry routes through
    the same factory mapping — one driver, two transports."""
    dongle = _real("aula-mini60he-pro-24g")
    dev = StubDevice()
    drv = get_driver(dongle, dev)
    assert isinstance(drv, Mini60Driver)
    assert drv.frame_len == 32
    # and the stub with protocol None still gets the inert NullDriver
    assert isinstance(get_driver(DONGLE, dev), NullDriver)


# ------------------------------------------------------------- detection ----
def _registry():
    return boards.BoardRegistry([WIN60, MINI_MAX, MINI_PRO, DONGLE], "win60")


def _enum(*profiles):
    return lambda: [{"vendor_id": p.vid, "product_id": p.pid} for p in profiles]


def test_detection_prefers_drivable_over_dongle():
    reg = _registry()
    # adverse enumeration order: the non-drivable dongle first
    got = connected_profiles(reg, _enum(DONGLE, MINI_PRO, WIN60))
    assert [p.slug for p in got] == ["win60", "mini60-pro", "mini60-pro-24g"]
    assert got[0].drivable


def test_detection_dongle_only_still_detects_it():
    got = connected_profiles(_registry(), _enum(DONGLE))
    assert [p.slug for p in got] == ["mini60-pro-24g"]


def test_detection_none_connected_or_enum_broken():
    assert connected_profiles(_registry(), lambda: []) == []
    def boom():
        raise OSError("no hid")
    assert connected_profiles(_registry(), boom) == []


# ------------------------------------------------------------- api level ----
import app_web  # noqa: E402  (import placement mirrors the other api tests)


def _api():
    a = app_web.Api.__new__(app_web.Api)
    a._lock = threading.Lock()
    return a


def test_api_unsupported_write_shape():
    a = _api()
    a.driver = NullDriver(DONGLE, StubDevice())
    r = a.set_light(0, 255, 0, 0)
    assert r["ok"] is False and r.get("unsupported") is True
    assert r["feature"] == "lighting" and DONGLE.name in r["error"]
    assert a.set_poll(1)["unsupported"] is True
    assert a.gamepad_mode(True)["unsupported"] is True
    assert a.set_trigger_all(1.5)["unsupported"] is True


def test_api_set_light_routes_through_driver():
    a = _api()
    dev = StubDevice()
    a.driver = Win60Driver(WIN60, dev, a._lock)
    r = a.set_light(2, 10, 20, 30, brightness=3, speed=1)
    assert r == {"ok": True}
    assert dev.writes == [protocol.build_light(2, 3, 1, (10, 20, 30),
                                               (0, 0, 0), 0, 0, True)]


def test_api_start_multicolor_streams_on_mini60():
    """The MINI 60 PRO now has a verified live channel (cmd 0x32): a
    MINI-selected session must START the host engine, not refuse — the
    board is put into Custom mode (20) by begin_host_stream first."""
    a = _api()
    a.km = types.SimpleNamespace(indices=lambda: [0])
    started = {}
    a.fx = types.SimpleNamespace(
        indices=[0, 1], is_running=lambda: False, get_depths=None,
        start=lambda *args, **kw: started.setdefault("args", args))
    d, dev, _ = _mini()
    a.driver = d
    a.reader = None
    r = a.start_multicolor("rain", [[255, 0, 0], [0, 0, 255]])
    assert r == {"ok": True, "keys": 2}       # JS-facing shape unchanged
    assert "args" in started                  # engine actually started
    light = _frames(dev, pm.CMD_LIGHTING)
    assert len(light) == 1 and light[0][8] == pm.LIGHT_MODE_CUSTOM
    assert light[0][17] == 5                  # full brightness (MINI 0..5)


def test_api_start_multicolor_still_refused_without_stream():
    """Boards with no proven high-rate channel keep refusing loudly with
    zero bytes on the wire (the old MINI behavior, now the NullDriver's)."""
    a = _api()
    a.km = types.SimpleNamespace(indices=lambda: [0])
    a.fx = types.SimpleNamespace(indices=[0], is_running=lambda: False)
    dev = StubDevice()
    a.driver = NullDriver(DONGLE, dev)
    a.reader = None
    r = a.start_multicolor("rain", [[255, 0, 0], [0, 0, 255]])
    assert r["ok"] is False and r.get("unsupported") is True
    assert r["feature"] == "host_effects"
    assert dev.writes == []          # no half-configured board state


def test_api_stop_multicolor_clears_mini_stream_and_keeps_shape():
    a = _api()
    d, dev, _ = _mini()
    a.driver = d
    a.fx = types.SimpleNamespace(is_running=lambda: True, stop=lambda: None)
    assert a.stop_multicolor() == {"ok": True}
    clears = _frames(dev, mini60_mod.CMD_CLEAR_LED)
    assert len(clears) == 1
    # nothing runs -> nothing sent (teardown paths call stop unconditionally)
    a2 = _api()
    d2, dev2, _ = _mini()
    a2.driver = d2
    a2.fx = types.SimpleNamespace(is_running=lambda: False, stop=lambda: None)
    assert a2.stop_multicolor() == {"ok": True}
    assert dev2.writes == []


def test_api_capture_never_arms_foreign_protocol(monkeypatch):
    """THE bug this layer fixes: active board = MINI 60 PRO must not get
    Win60 travel-test frames from the capture path — it has no travel
    stream yet, so capture falls back to the read-only fresh-handle mode."""
    a = _api()
    a.board = types.SimpleNamespace(vid=0x0C45, pid=0x80A2)
    a.km = types.SimpleNamespace(indices=lambda: [0, 1])
    d, shared_dev, _ = _mini()
    a.driver = d
    a.dev = shared_dev
    a.reader = None

    class FreshDev:
        def open_path(self, p): pass
        def set_nonblocking(self, v): pass
        def read(self, n, timeout_ms=0): return []
        def close(self): pass
    monkeypatch.setattr(app_web.hid, "device", lambda: FreshDev())
    assert a.open_capture("p", "0x0c45", "0x80a2")["ok"] is True
    assert a._cap_shared is False          # read-only path chosen
    a.stop_capture()
    assert shared_dev.writes == []         # zero frames hit the MINI


def test_api_select_board_switches_driver_and_resets_state():
    a = _api()
    a._registry = None
    a.reader = None
    a.calib_reader = None
    a.fx = None
    a.pad = None
    a._pad_stop = threading.Event()
    a._pad_thread = None
    a.dev = StubDevice()
    a.board = None
    a._remaps = {5: 4}
    a._trigger_state = {1: (0, 150, 0, 0)}
    a._deadband_state = {1: (4, 5)}
    a._fn_layer_raw = b"\x01" * 528

    r = a.select_board("aula-mini60he-pro")
    assert r["ok"] is True
    assert r["active"]["slug"] == "aula-mini60he-pro"
    assert isinstance(a.driver, Mini60Driver)
    assert a.board.vid == 0x0C45 and a.board.pid == 0x80A2
    assert a._remaps == {} and a._trigger_state == {} and a._deadband_state == {}
    assert a._fn_layer_raw is None

    # the REAL dongle entry is drivable since 2026-07-20: same Mini60Driver,
    # frame size retargeted to the registry's frameLen 32
    r2 = a.select_board("aula-mini60he-pro-24g")
    assert r2["ok"] is True and isinstance(a.driver, Mini60Driver)
    assert a.driver.frame_len == 32

    assert a.select_board("nope")["ok"] is False


def test_api_list_boards_marks_connected_and_active(monkeypatch):
    a = _api()
    a._registry = _registry()
    a.board = MINI_PRO
    monkeypatch.setattr(app_web.drivers, "connected_profiles",
                        lambda reg, enumerate_fn=None: [WIN60, MINI_PRO])
    out = a.list_boards()
    assert out["ok"] is True and out["active"] == "mini60-pro"
    by_slug = {b["slug"]: b for b in out["boards"]}
    assert by_slug["win60"]["connected"] is True
    assert by_slug["mini60-pro"]["connected"] is True
    assert by_slug["mini60-pro"]["active"] is True
    assert by_slug["mini60-pro-24g"]["connected"] is False
    assert by_slug["mini60-pro-24g"]["drivable"] is False


def test_api_init_prefers_drivable_board(monkeypatch):
    monkeypatch.setattr(app_web.boards, "load_registry", lambda path=None: _registry())
    monkeypatch.setattr(app_web.drivers, "connected_profiles",
                        lambda reg, enumerate_fn=None: [MINI_PRO, DONGLE])
    a = app_web.Api()
    assert a.board.slug == "mini60-pro"
    assert isinstance(a.driver, Mini60Driver)


def test_api_init_falls_back_to_default_when_nothing_connected(monkeypatch):
    monkeypatch.setattr(app_web.boards, "load_registry", lambda path=None: _registry())
    monkeypatch.setattr(app_web.drivers, "connected_profiles",
                        lambda reg, enumerate_fn=None: [])
    a = app_web.Api()
    assert a.board.slug == "win60"
    assert isinstance(a.driver, Win60Driver)
