"""protocol_magnet against the frames the vendor driver really sent to a
WIN 68 HE Max (tests/fixtures/magnet_win68max_tx.txt, issue #7): every
CAPTURED builder must reproduce them byte for byte."""
import os

import pytest

import protocol_magnet as pm

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "magnet_win68max_tx.txt")


def _frames():
    out = []
    with open(FIX, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#"):
                out.append(list(bytes.fromhex(line)))
    return out


FRAMES = _frames()


def _of(cmd, length=None):
    return [f for f in FRAMES if f[2] == cmd and (length is None or f[1] == length)]


def test_fixture_is_the_full_capture():
    assert len(FRAMES) == 344 and all(len(f) == 64 for f in FRAMES)


def test_checksum_matches_every_captured_frame():
    for f in FRAMES:
        assert pm.checksum(f) == f[3], bytes(f[:8]).hex(" ")
        assert pm.is_valid(f)


def test_lighting_writes_rebuild_byte_for_byte():
    writes = _of(pm.CMD_LIGHTING, 44)
    assert len(writes) == 59
    for f in writes:
        p = f[4:48]
        assert p[0] == pm.OP_WRITE and bytes(p[1:37]) == pm.LIGHT_BLOCK
        flags, bri, mode, spd, sleep, static, slot = p[37:44]
        assert flags & ~(pm.LIGHT_FLAG_POWER | pm.LIGHT_FLAG_DIRECTION) == 0
        got = pm.build_lighting(mode, brightness=bri, speed=spd,
                                power=bool(flags & pm.LIGHT_FLAG_POWER),
                                direction=bool(flags & pm.LIGHT_FLAG_DIRECTION),
                                sleep_min=sleep, static_mode=static, color_slot=slot)
        assert got == f


def test_lighting_capture_covers_the_decoded_fields():
    p = [f[4:48] for f in _of(pm.CMD_LIGHTING, 44)]
    assert {x[38] for x in p} == {0, 1, 2, 3, 4}                 # brightness sweep
    assert {x[40] for x in p} == {0, 1, 2, 3, 4}                 # speed sweep
    assert {x[39] for x in p} == set(range(0, 22))               # every mode 0..21
    assert {x[41] for x in p} >= {1, 2, 3, 5, 10, 120}           # sleep minutes


def test_single_key_colour_writes_rebuild():
    writes = _of(pm.CMD_KEY_RGB, 5)
    assert len(writes) == 135
    for f in writes:
        assert pm.build_key_rgb(f[5], f[6], f[7], f[8]) == f
    assert {f[5] for f in writes} <= set(pm.KEY_ORDER)


def test_key_config_reads_rebuild_for_every_property():
    reads = _of(pm.CMD_KEY_CONFIG)
    assert len(reads) == 26 * 5
    for prop in range(26):
        assert pm.build_key_config_read(prop) == reads[prop * 5:(prop + 1) * 5]


def test_key_rgb_reads_rebuild():
    assert pm.build_key_rgb_read() == _of(pm.CMD_KEY_RGB, 57)


def test_other_read_requests_rebuild():
    assert pm.build_hello() in FRAMES
    for sub in (0x01, 0x21, 0x22, 0x25, 0x26, 0x76):
        assert pm.build_sys_query(sub) in FRAMES
    assert pm.build_lighting_read() in FRAMES
    assert pm.build_ambient_read() in FRAMES
    assert pm.build_global_travel_read() in FRAMES
    for page in range(3):
        assert pm.build_hid_matrix_read(page) in FRAMES


def test_key_order_is_the_layout_hid_set():
    import device_state
    km = device_state.KeyMap(os.path.join("ui", "layouts", "aula-win68he-max.json"))
    assert sorted(e["hid"] for e in km.by_index.values()) == sorted(pm.KEY_ORDER)


# ---- SOURCE-ONLY builders: shape only (no capture to compare against) ----
def test_key_config_write_frames():
    recs = pm.actuation_records([0x04, 0x07], 1.5)
    frames = pm.build_key_config_write(recs)
    assert len(frames) == 1 and pm.is_valid(frames[0])
    p = frames[0][4:4 + frames[0][1]]
    assert p[0] == pm.OP_WRITE and len(p) == 1 + 4 * 6
    assert p[1:5] == [0x04, pm.PROP_MODE, pm.TOUCH_FIXED << 4, 0]
    assert p[5:9] == [0x04, pm.PROP_ACTUATION, 1500 & 0xFF, 1500 >> 8]
    many = pm.build_key_config_write([(1, 4, 100)] * 30)
    assert [f[1] for f in many] == [57, 57, 9]


def test_actuation_is_clamped_to_the_board_range():
    assert pm.mm_to_um(0.01) == 100 and pm.mm_to_um(9) == 3400


def test_rapid_trigger_records():
    recs = pm.actuation_records([0x1A], 0.8, rapid=True, press_mm=0.1, release_mm=0.2)
    assert (0x1A, pm.PROP_MODE, pm.TOUCH_RAPID << 4) in recs
    assert (0x1A, pm.PROP_RT_PRESS, 100) in recs and (0x1A, pm.PROP_RT_RELEASE, 200) in recs


def test_travel_request_and_reply():
    f = pm.build_travel_request(2)
    assert f[2] == pm.CMD_TRAVEL_MATRIX and f[4:8] == [0x02, 2, 0xFF, 0xFF]
    with pytest.raises(ValueError):
        pm.build_travel_request(0)
    data = [0] * 192
    data[0], data[2], data[5] = 0xDC, pm.TRAVEL_REPLY_CMD, 0x02
    assert pm.is_travel_reply_head(data)
    data[6:8] = [0xD0, 0x07]            # slot 0 of half 2 -> 2.0 mm
    data[8:10] = [10, 0]                # 10 um: noise -> 0
    depths = pm.parse_travel_reply(data, 2)
    assert depths[63] == 2.0 and depths[64] == 0.0 and len(depths) == 63
    with pytest.raises(ValueError):
        pm.parse_travel_reply(data[:100], 1)


def test_socd_frame():
    f = pm.build_socd(0x04, 0x07, 4)
    assert pm.is_valid(f) and f[4:15] == [1, 4, 7, 4, 0, 7, 0, 4, 0, 0, 0]


def test_payload_too_long_is_refused():
    with pytest.raises(ValueError):
        pm.frame(0x23, [0] * 61)
