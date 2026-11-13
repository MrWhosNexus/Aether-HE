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


# ---- COMMUNITY-TESTED builders (nieruuu19): shape only, no capture to compare ----
ADV0 = {0x04: 0, 0x07: 0, 0x1A: 0}


def test_key_config_write_frames():
    recs = pm.actuation_records([0x04, 0x07], 1.5, adv_by_key=ADV0)
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
    assert pm.mm_to_um(9, 0.1, 3.3) == 3300


def test_actuation_keeps_the_advanced_key_nibble():
    recs = pm.actuation_records([0x04, 0x07], 1.5, adv_by_key={0x04: pm.ADV_SOCD, 0x07: 6})
    assert (0x04, pm.PROP_MODE, (pm.TOUCH_FIXED << 4) | 8) in recs
    assert (0x07, pm.PROP_MODE, (pm.TOUCH_FIXED << 4) | 6) in recs
    with pytest.raises(KeyError):
        pm.actuation_records([0x04], 1.5)                       # no table: refuse
    with pytest.raises(KeyError):
        pm.actuation_records([0x04], 1.5, adv_by_key={0x07: 0})  # key missing from it
    with pytest.raises(ValueError):
        pm.actuation_records([0x04], 1.5, mode=2, adv_by_key=ADV0)


def test_rapid_trigger_records():
    recs = pm.actuation_records([0x1A], 0.8, mode=pm.MODE_RT_STANDARD, adv_by_key=ADV0,
                                press_mm=0.1, release_mm=0.2)
    assert (0x1A, pm.PROP_MODE, pm.TOUCH_RAPID << 4) in recs
    assert (0x1A, pm.PROP_RT_PRESS, 100) in recs and (0x1A, pm.PROP_RT_RELEASE, 200) in recs
    # Standard RT pins the press dead band 0.01 mm above the actuation point.
    assert (0x1A, pm.PROP_DEAD_TOP, 790) in recs
    assert not [r for r in recs if r[1] == pm.PROP_DEAD_BOTTOM]


def test_standard_rt_dead_band_is_clamped():
    assert pm.standard_rt_dead_um(100) == 90 and pm.standard_rt_dead_um(50) == 50
    assert pm.standard_rt_dead_um(3400) == 3390


def test_continuous_rt_and_fixed_write_the_users_dead_band():
    for mode in (pm.MODE_RT_CONTINUOUS, pm.MODE_FIXED):
        recs = pm.actuation_records([0x1A], 0.8, mode=mode, adv_by_key=ADV0,
                                    dead_by_key={0x1A: (150, 2000)})
        assert (0x1A, pm.PROP_DEAD_TOP, 150) in recs
        assert (0x1A, pm.PROP_DEAD_BOTTOM, 1000) in recs        # clamped to 1.00 mm
    # No stored rapid-trigger pair is written unless one is given.
    recs = pm.actuation_records([0x1A], 0.8, mode=pm.MODE_FIXED, adv_by_key=ADV0)
    assert {r[1] for r in recs} == {pm.PROP_MODE, pm.PROP_ACTUATION, pm.PROP_ACTUATION_2}


def test_deadband_records():
    recs = pm.deadband_records({0x04: (40, 50), 0x07: (40, 50)}, skip_top={0x07})
    assert recs == [(0x04, pm.PROP_DEAD_TOP, 40), (0x04, pm.PROP_DEAD_BOTTOM, 50),
                    (0x07, pm.PROP_DEAD_BOTTOM, 50)]


def test_batched_key_colour_frames():
    recs = [(k, (i, 2, 3)) for i, k in enumerate(pm.KEY_ORDER)]
    frames = pm.build_key_rgb_batch(recs)
    assert [f[1] for f in frames] == [57, 57, 57, 57, 1 + 4 * 12]
    assert all(pm.is_valid(f) and f[2] == pm.CMD_KEY_RGB and f[4] == pm.OP_WRITE for f in frames)
    assert frames[0][5:9] == [pm.KEY_ORDER[0], 0, 2, 3]
    assert frames[4][4 + 49:] == [0xFF] * (64 - 4 - 49)        # 0xFF fill after the records
    # One record is the captured single-key frame.
    assert pm.build_key_rgb_batch([(0x04, (9, 8, 7))]) == [pm.build_key_rgb(0x04, 9, 8, 7)]


# ---- lighting state (palette block layout: the fork's reading of the capture) ----
def test_captured_palette_decodes_to_the_seven_named_colours():
    assert pm.palette_from_block(pm.LIGHT_BLOCK) == [
        (255, 0, 0), (0, 255, 0), (127, 127, 0), (0, 0, 255),
        (127, 0, 127), (0, 127, 127), (127, 127, 127)]


def test_palette_edit_touches_one_slot_only():
    blk = pm.block_with_palette_slot(pm.LIGHT_BLOCK, 3, (1, 2, 3))
    assert pm.palette_from_block(blk)[3] == (1, 2, 3)
    assert blk[16:20] == bytes([3, 2, 1, 0xFF])
    assert blk[:16] == pm.LIGHT_BLOCK[:16] and blk[20:] == pm.LIGHT_BLOCK[20:]
    with pytest.raises(ValueError):
        pm.block_with_palette_slot(pm.LIGHT_BLOCK, 7, (1, 2, 3))


def test_lighting_write_echoes_a_given_block_and_defaults_to_the_capture():
    assert pm.build_lighting(21)[4 + 41] == 2                   # the capture's sleep minutes
    assert bytes(pm.build_lighting(21)[5:41]) == pm.LIGHT_BLOCK
    blk = pm.block_with_palette_slot(pm.LIGHT_BLOCK, 0, (9, 9, 9))
    f = pm.build_lighting(7, block=blk, sleep_min=30, static_mode=3, color_slot=5)
    p = f[4:4 + f[1]]
    assert bytes(p[1:37]) == blk and p[39] == 7 and p[41:44] == [30, 3, 5]
    assert pm.build_lighting(7, color_slot=None)[1] == 43       # a board with no byte 43
    with pytest.raises(ValueError):
        pm.build_lighting(7, block=b"\x00" * 35)


def test_every_firmware_effect_builds_with_its_captured_mode_byte():
    captured = {f[4 + 39] for f in _of(pm.CMD_LIGHTING, 44)}
    assert [e[0] for e in pm.LIGHT_EFFECTS] == list(range(1, 21))
    assert len({e[1] for e in pm.LIGHT_EFFECTS}) == 20
    for byte, _id, _name in pm.LIGHT_EFFECTS:
        assert byte in captured
        assert pm.build_lighting(byte)[4 + 39] == byte


# ---- replies (layouts: COMMUNITY-TESTED) ----
def _reply(cmd, body, magic=0xDC):
    r = [0] * 64
    r[0], r[1], r[2] = magic, len(body), cmd | 0x80
    r[4:4 + len(body)] = body
    return r


def test_reply_body_accepts_only_this_commands_reply():
    r = _reply(pm.CMD_LIGHTING, [0, 1, 2])
    assert pm.reply_body(r, pm.CMD_LIGHTING) == [0, 1, 2]
    assert pm.reply_body([0] + r, pm.CMD_LIGHTING) == [0, 1, 2]     # report id in front
    assert pm.reply_body(_reply(pm.CMD_LIGHTING, [0, 1], magic=0x5C), pm.CMD_LIGHTING) == [0, 1]
    assert pm.reply_body(r, pm.CMD_KEY_CONFIG) is None
    assert pm.reply_body(_reply(pm.CMD_LIGHTING, [0], magic=0xAA), pm.CMD_LIGHTING) is None
    assert pm.reply_body([], pm.CMD_LIGHTING) is None
    bad = list(r); bad[1] = 61
    assert pm.reply_body(bad, pm.CMD_LIGHTING) is None


def test_key_config_reply_records():
    body = [0, 0x04, 8, 0x28, 0, 0x07, 8, 0x10, 0, 0xFF, 0xFF, 0xFF, 0, 0, 0, 0, 0]
    assert pm.parse_key_config_reply(body) == [(0x04, 8, 0x28), (0x07, 8, 0x10)]
    assert pm.split_mode(0x28) == (pm.TOUCH_RAPID, pm.ADV_SOCD)
    assert pm.mode_value(pm.TOUCH_RAPID, pm.ADV_SOCD) == 0x28


def test_version_limits_and_name_replies():
    assert pm.parse_version([0, 1, 0x09, 0x01]) == (1, 0, 9)
    assert pm.parse_version([0, 2, 0x09, 0x01]) is None
    lim = pm.parse_travel_limits([0, 0x25, 10, 100, 0, 0x48, 0x0D])
    assert lim == {"precision_mm": 0.01, "min_mm": 0.1, "max_mm": 3.4}
    assert pm.parse_travel_limits([0, 0x25, 10, 0, 0, 0, 0]) is None
    assert pm.parse_device_name([0, 0x26] + list(b"WIN 68 HE MAX") + [0, 0]) == "WIN 68 HE MAX"


def test_lighting_reply_fields():
    blk = pm.block_with_palette_slot(pm.LIGHT_BLOCK, 2, (5, 6, 7))
    body = [0] + list(blk) + [0x03, 4, 9, 2, 30, 3, 5]
    st = pm.parse_lighting_reply(body)
    assert st["block"] == blk and st["power"] and st["direction"]
    assert (st["brightness"], st["mode"], st["speed"]) == (4, 9, 2)
    assert (st["sleep_min"], st["static_mode"], st["color_slot"]) == (30, 3, 5)
    assert pm.parse_lighting_reply(body[:43])["color_slot"] is None
    assert pm.parse_lighting_reply(body[:42]) is None


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
    """Corrected layout (fork @ 7de05f2): bind at byte 7, zero-based mode at
    byte 8, delay u16. Position binding sends zero value slots."""
    f = pm.build_socd(0x04, 0x07, 4)
    assert pm.is_valid(f) and f[1] == 11 and f[2] == pm.CMD_SOCD
    assert f[4:15] == [1, 4, 7, 0, 0, 0, 0, 0, 3, 0, 0]
    for model in (1, 2, 3, 4):
        p = pm.build_socd(0x04, 0x07, model)[4:15]
        assert p[8] == model - 1 and p[3:7] == [0, 0, 0, 0] and p[7] == 0


def test_socd_value_binding_and_delay():
    p = pm.build_socd(0x04, 0x07, 1, bind=1, delay_ms=10)[4:15]
    assert p == [1, 4, 7, 4, 0, 7, 0, 1, 0, 10, 0]
    p = pm.build_socd(0x04, 0x07, 2, bind=1, value1=0x50, value2=0x4F, delay_ms=999)[4:15]
    assert p == [1, 4, 7, 0x50, 0, 0x4F, 0, 1, 1, 50, 0]        # delay clamped to 50 ms


@pytest.mark.parametrize("model", [0, 5, -1, 255])
def test_socd_refuses_a_model_outside_1_to_4(model):
    with pytest.raises(ValueError):
        pm.build_socd(0x04, 0x07, model)


def test_payload_too_long_is_refused():
    with pytest.raises(ValueError):
        pm.frame(0x23, [0] * 61)
