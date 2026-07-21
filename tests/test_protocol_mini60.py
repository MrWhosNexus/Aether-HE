"""Golden-frame tests for protocol_mini60 — every expected frame is parsed
straight out of the WebHID capture of the official hub.aulacn.com driver
driving a real Aula MINI 60 HE PRO (0C45:80A2):

    docs/context/issue-6-mini60-pro-raw/webhid-capture-2026-07-20.json

Builders must reproduce the captured OUT frames BYTE FOR BYTE. If a builder
stops matching the capture, it has regressed.

Layouts are additionally cross-checked against the vendor SDK source decode
(docs/context/issue-6-mini60-pro-raw/HFD_SDK_DECODE.md). Where the capture
cannot discriminate a layout detail (e.g. the actuation record's axisType
byte, which is 0 everywhere in the capture), a structural test pins the
SDK layout explicitly and is marked as such.

Verification tiers used below (mirroring the module docstring):
  golden      — asserted byte-for-byte against literal captured frames.
  structural  — asserted against the SDK layout / HARDWARE-VERIFIED framing
                where no captured frames exist (e.g. SET 0x24).

Run: python -m pytest tests/test_protocol_mini60.py  (or run this file directly)
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import protocol_mini60 as pm

CAPTURE = os.path.join(ROOT, "docs", "context", "issue-6-mini60-pro-raw",
                       "webhid-capture-2026-07-20.json")


def _load_frames():
    with open(CAPTURE, encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, str):          # the capture file is double-JSON-encoded
        data = json.loads(data)
    return data["frames"]


FRAMES = _load_frames()


def fbytes(f):
    return list(bytes.fromhex(f["hex"].replace(" ", "")))


def outs(cmd=None, label=None):
    got = []
    for f in FRAMES:
        if f["dir"] != "OUT":
            continue
        b = fbytes(f)
        if cmd is not None and b[1] != cmd:
            continue
        if label is not None and f["label"] != label:
            continue
        got.append((f, b))
    return got


def ins(cmd):
    return [fbytes(f) for f in FRAMES
            if f["dir"] == "IN" and fbytes(f)[1] == cmd]


def out_at(cmd, label, offset):
    for f, b in outs(cmd, label):
        if (b[3] | (b[4] << 8)) == offset:
            return b
    raise AssertionError(f"no OUT cmd={cmd:#x} label={label!r} offset={offset:#x} in capture")


def reply_after(out_frame_i):
    """The IN frame immediately following capture frame index i."""
    idx = next(n for n, f in enumerate(FRAMES) if f["i"] == out_frame_i)
    for f in FRAMES[idx + 1:]:
        if f["dir"] == "IN":
            return fbytes(f)
    raise AssertionError("no IN reply found")


# ---------------- lighting (cmd 0x23) ----------------
# The 19 mode-change frames, in capture order, are modes 0x01..0x13.
LIGHT_LABELS = [
    "Static constant brightness", "Single-point lighting", "Single extinguish",
    "twinkling stars", "Snowflakes flying everywhere", "A riot of flowers",
    "Dynamic breathing", "Spectral Cycling", "Colorful springs gushing forth",
    "Colorful and diverse", "Go with the flow", "A Twist of Fate",
    "On the verge of exploding", "Kill two birds with one stone",
    "Ripple spread", "Flowing continuously", "Layer upon layer of mountains",
    "Slanting wind and drizzle", "shuttling back and forth",
]


def test_light_mode_frames_match_capture():
    for mode, name in enumerate(LIGHT_LABELS, start=0x01):
        (f, b), = outs(pm.CMD_LIGHTING, f"LIGHT_MODE: {name}")
        assert pm.build_light(mode) == b, f"mode {mode:#04x} ({name})"
        assert pm.LIGHT_MODE_NAMES[mode] == name


def test_light_brightness_and_speed_decrement():
    (_, bri), = outs(pm.CMD_LIGHTING, "BRIGHTNESS_DEC")
    (_, spd), = outs(pm.CMD_LIGHTING, "SPEED_DEC")
    # capture: brightness 0x05 -> 0x04, then speed 0x04 -> 0x03, mode 0x13
    assert pm.build_light(pm.LIGHT_MODE_SHUTTLING, brightness=0x04) == bri
    assert pm.build_light(pm.LIGHT_MODE_SHUTTLING, brightness=0x04, speed=0x03) == spd


def test_every_captured_light_frame_has_active_byte_and_roundtrips():
    all_light = outs(pm.CMD_LIGHTING)
    assert len(all_light) == 21
    for f, b in all_light:
        assert b[16] == 0x01, f"frame i={f['i']} lacks the mandatory [16]=0x01"
        # rebuild from the frame's own fields — layout must explain every byte
        rebuilt = pm.build_light(b[8], r=b[9], g=b[10], b=b[11],
                                 brightness=b[17], speed=b[18], alpha=b[12])
        assert rebuilt == b, f"frame i={f['i']}"


def test_light_marker_and_header():
    f = pm.build_light(pm.LIGHT_MODE_STATIC)
    assert f[0] == 0xAA and f[1] == 0x23 and f[2] == 0x10 and f[6] == 0x01
    assert f[22] == 0xAA and f[23] == 0x55
    assert len(f) == 64


def test_light_mode_custom_constant():
    # structural — mode 20 was never captured with a menu label; it is
    # HARDWARE-VERIFIED as the gate for the 0x24 per-key table.
    assert pm.LIGHT_MODE_CUSTOM == 20
    f = pm.build_light(pm.LIGHT_MODE_CUSTOM)
    assert f[8] == 0x14 and f[16] == 0x01


# ---------------- actuation writes (cmd 0x27) ----------------
def test_actuation_record_origin_is_frame_byte_8():
    # golden — pins the ABSOLUTE record origin against literal captured
    # bytes at known frame indices. A parse<->build symmetry test cannot
    # catch an absolute-offset error, because parse and build would share
    # the same wrong offset and still round-trip.
    #
    # RT_RELEASE_0.75mm page 0xA8: all 7 slots hold the same full record
    # [axisType=0][flags=1][trip 2C 01][press 7D 00][release 4B 00].
    exp = out_at(pm.CMD_ACTUATION, "RT_RELEASE_0.75mm", 0x00A8)
    REC = [0x00, 0x01, 0x2C, 0x01, 0x7D, 0x00, 0x4B, 0x00]
    for k in range(pm.ACT_RECORDS_PER_FRAME):
        base = 8 + k * pm.ACT_RECORD_SIZE
        assert exp[base:base + pm.ACT_RECORD_SIZE] == REC, \
            f"record {k} does not start at frame byte {base}"
    # 7 whole records fill bytes 8..63 exactly — nothing is truncated
    assert 8 + pm.ACT_RECORDS_PER_FRAME * pm.ACT_RECORD_SIZE == pm.FRAME_LEN
    # RT_PRESS_1.25mm page 0: record 0 spans bytes 8..15, release still 0
    exp0 = out_at(pm.CMD_ACTUATION, "RT_PRESS_1.25mm", 0x0000)
    assert exp0[8:16] == [0x00, 0x01, 0x2C, 0x01, 0x7D, 0x00, 0x00, 0x00]
    # fixed actuation: flags byte 0 at [9], trip LE16 at [10..11]
    exp1 = out_at(pm.CMD_ACTUATION, "TRIP_SET_3.00mm", 0x0000)
    assert exp1[8:16] == [0x00, 0x00, 0x2C, 0x01, 0x00, 0x00, 0x00, 0x00]


def test_capture_never_exercises_nonzero_axis_type():
    # golden — documents WHY the pre-SDK byte-9 layout golden-tested clean:
    # with axisType == 0 the two layouts are byte-identical. Every captured
    # 0x27 frame carries 0x00 at every record's axisType byte (8 + 8k), so
    # the capture alone cannot discriminate the layouts; the SDK source
    # (HFD_SDK_DECODE.md §6) settles it.
    all_writes = outs(pm.CMD_ACTUATION)
    assert len(all_writes) == 72
    for f, b in all_writes:
        for k in range(pm.ACT_RECORDS_PER_FRAME):
            assert b[8 + 8 * k] == 0, f"frame i={f['i']} slot {k}"


def test_axis_type_lands_at_record_byte_0_and_survives_roundtrip():
    # structural (SOURCE-ONLY: nonzero axisType never captured) — the switch
    # id must land at record byte 0 WITHOUT displacing flags/travel. The
    # pre-SDK layout would have silently zeroed it on every write.
    f = pm.build_actuation_frame(
        0x0000, [(1, 3.00, 1.25, 0.75, 4), None, (0, 1.20, 0.0, 0.0, 2)])
    assert f[8] == 4 and f[9] == 1                      # axisType, flags
    assert f[10:16] == [0x2C, 0x01, 0x7D, 0x00, 0x4B, 0x00]
    assert f[16:24] == [0] * 8                          # None slot stays zero
    assert f[24] == 2 and f[25] == 0
    assert f[26:28] == [0x78, 0x00]                     # 1.20 mm trip, LE16
    recs = pm.parse_actuation_records(f)
    assert recs[0] == (1, 3.00, 1.25, 0.75, 4)
    assert recs[1] is None
    assert recs[2] == (0, 1.20, 0.0, 0.0, 2)
    assert recs[3:] == [None] * 4


def test_trip_031_offset0():
    # TRIP_INCREASE_0.3_to_0.31, page 0: only slot 0 populated, fixed
    # actuation 0.31 mm -> 1F 00 little-endian at frame bytes [10..11]
    exp = out_at(pm.CMD_ACTUATION, "TRIP_INCREASE_0.3_to_0.31", 0x0000)
    assert exp[8:12] == [0x00, 0x00, 0x1F, 0x00]
    got = pm.build_actuation_frame(0x0000, [(0, 0.31)])
    assert got == exp


def test_trip_300_offset0_little_endian():
    # TRIP_SET_3.00mm: 300 = 0x012C -> 2C 01 on the wire (LE, not BE!)
    exp = out_at(pm.CMD_ACTUATION, "TRIP_SET_3.00mm", 0x0000)
    assert exp[10:12] == [0x2C, 0x01]
    got = pm.build_actuation_frame(0x0000, [(0, 3.00)])
    assert got == exp


def test_trip_full_page_7_records():
    # TRIP_SET_3.00mm page 0xA8: all 7 slots populated
    exp = out_at(pm.CMD_ACTUATION, "TRIP_SET_3.00mm", 0x00A8)
    got = pm.build_actuation_frame(0x00A8, [(0, 3.00)] * 7)
    assert got == exp


def test_trip_sparse_page_slots_3_to_6():
    # TRIP_SET_3.00mm page 0x70: slots 0-2 are unused matrix positions
    exp = out_at(pm.CMD_ACTUATION, "TRIP_SET_3.00mm", 0x0070)
    got = pm.build_actuation_frame(0x0070, [None, None, None] + [(0, 3.00)] * 4)
    assert got == exp


def test_rt_press_sets_flag_and_press_field():
    # RT_PRESS_1.25mm page 0: flags 0x01 at [9], trip 2C 01, press 7D 00
    exp = out_at(pm.CMD_ACTUATION, "RT_PRESS_1.25mm", 0x0000)
    assert exp[9:14] == [0x01, 0x2C, 0x01, 0x7D, 0x00]
    got = pm.build_actuation_frame(0x0000, [(1, 3.00, 1.25)])
    assert got == exp


def test_rt_release_full_page_records_fill_frame_exactly():
    # RT_RELEASE_0.75mm page 0xA8: 7 full RT records, release 4B 00; the
    # 7th record occupies bytes 56..63 COMPLETELY (no truncation — the
    # pre-SDK layout's "truncated reserved byte" was an artifact of the
    # off-by-one origin)
    exp = out_at(pm.CMD_ACTUATION, "RT_RELEASE_0.75mm", 0x00A8)
    got = pm.build_actuation_frame(0x00A8, [(1, 3.00, 1.25, 0.75)] * 7)
    assert got == exp
    assert got[56:64] == [0x00, 0x01, 0x2C, 0x01, 0x7D, 0x00, 0x4B, 0x00]


def test_final_page_carries_final_flag():
    # every write pass ends with an empty page at 0x03B8 with [6]=0x01
    for label in ("TRIP_INCREASE_0.3_to_0.31", "TRIP_SET_3.00mm",
                  "RT_PRESS_1.25mm", "RT_RELEASE_0.75mm"):
        exp = out_at(pm.CMD_ACTUATION, label, 0x03B8)
        assert pm.build_actuation_frame(0x03B8, [], final=True) == exp


def test_every_captured_actuation_write_roundtrips():
    # parse_actuation_records + build_actuation_frame must explain every byte
    # of all 72 captured 0x27 frames (origin errors are caught separately by
    # test_actuation_record_origin_is_frame_byte_8 — round-tripping alone
    # cannot catch them)
    all_writes = outs(pm.CMD_ACTUATION)
    assert len(all_writes) == 72
    for f, b in all_writes:
        offset = b[3] | (b[4] << 8)
        recs = pm.parse_actuation_records(b)
        rebuilt = pm.build_actuation_frame(offset, recs, final=bool(b[6]))
        assert rebuilt == b, f"frame i={f['i']} offset={offset:#x}"


def test_actuation_write_is_acked_with_55_echo():
    (f, b) = outs(pm.CMD_ACTUATION, "TRIP_INCREASE_0.3_to_0.31")[0]
    ack = reply_after(f["i"])
    assert ack[0] == pm.REPLY_MAGIC and ack[1:] == b[1:]


# ---------------- table reads (0x11 / 0x12 / 0x14 / 0x17) ----------------
def test_every_captured_read_request_matches_builder():
    # all paged-read requests are header-only: cmd, length, LE offset, final
    # flag — builder must reproduce every one of them
    count = 0
    for f in FRAMES:
        if f["dir"] != "OUT":
            continue
        b = fbytes(f)
        if b[1] not in (pm.CMD_CONFIG_READ, pm.CMD_KEY_TABLE_READ,
                        pm.CMD_GET_CUSTOM_LED, pm.CMD_ACTUATION_READ):
            continue
        offset = b[3] | (b[4] << 8)
        got = pm.build_table_read(b[1], offset, length=b[2], final=bool(b[6]))
        assert got == b, f"frame i={f['i']} cmd={b[1]:#x}"
        count += 1
    assert count == 4 + 10 + 9 + 90   # 0x11 + 0x12 + 0x14 + 0x17


def test_iter_actuation_reads_matches_driver_sequence():
    # the 18-frame 0x17 sweep before the first write pass (NAV label)
    captured = [b for _, b in outs(pm.CMD_ACTUATION_READ, "NAV: Trigger settings")]
    assert list(pm.iter_actuation_reads()) == captured


def test_config_read_frames_match_capture():
    captured = [b for _, b in outs(pm.CMD_CONFIG_READ, "DEADZONE_TOP_0.42mm")]
    assert pm.build_config_read_frames() == captured


def test_light_read_matches_capture():
    (f, b), = outs(pm.CMD_LIGHT_READ)
    assert pm.build_light_read() == b


# ---------------- per-key RGB / custom LED (GET 0x14, SET 0x24) ----------------
def test_custom_led_read_frames_match_capture():
    # golden — the official driver's light page reads the 504-byte table on
    # mount: 9 pages of 0x38 at 0x0000..0x01C0, last-chunk flag on the final
    # page. The builder must reproduce all 9 captured request frames.
    captured = [b for _, b in outs(pm.CMD_GET_CUSTOM_LED)]
    assert len(captured) == 9
    assert list(pm.build_custom_led_read_frames()) == captured


def test_custom_led_replies_parse_from_capture():
    # golden — reassemble the 9 captured 0x14 replies. The capture board had
    # no custom table stored, so all 126 records decode to (0, 0, 0, 0).
    replies = ins(pm.CMD_GET_CUSTOM_LED)
    assert len(replies) == 9
    recs = pm.parse_custom_led_replies(replies)
    assert len(recs) == pm.CUSTOM_LED_COUNT
    assert all(rec == (0, 0, 0, 0) for rec in recs)


def test_custom_led_write_frames_structure():
    # structural — SET 0x24 has NO captured frames; it is HARDWARE-VERIFIED
    # by a byte-for-byte write/read-back round trip on the physical board
    # (2026-07-20). Pin the framing invariants: chunk size, LE16 offsets,
    # last-chunk flag placement, and payload packing from frame byte 8.
    colors = [((i * 3) % 256, (i * 5) % 256, (255 - i) % 256)
              for i in range(pm.CUSTOM_LED_COUNT)]
    table = pm.build_custom_led_table(colors)
    frames = list(pm.build_custom_led_write_frames(table))
    assert len(frames) == 9
    reassembled = []
    for n, f in enumerate(frames):
        assert len(f) == pm.FRAME_LEN
        assert f[0] == pm.MAGIC and f[1] == pm.CMD_SET_CUSTOM_LED
        assert f[2] == pm.PAGE                         # 0x38 per chunk
        assert (f[3] | (f[4] << 8)) == n * pm.PAGE     # LE16 byte offset
        assert f[5] == 0 and f[7] == 0
        assert f[6] == (0x01 if n == 8 else 0x00)      # flag on final page only
        reassembled += f[8:64]                         # payload from byte 8
    assert reassembled == table                        # covers all 504 bytes


def test_custom_led_table_geometry_and_parse_symmetry():
    # structural — record i is [ledId=i, r, g, b] at byte i*4 (ledId == the
    # firmware key index; HARDWARE-VERIFIED). parse_custom_led_replies must
    # invert the write framing.
    table = pm.build_custom_led_table([(10, 20, 30)] * pm.CUSTOM_LED_COUNT)
    assert len(table) == pm.CUSTOM_LED_TABLE_SIZE == 504
    for i in range(pm.CUSTOM_LED_COUNT):
        assert table[i * 4] == i
        assert table[i * 4 + 1:i * 4 + 4] == [10, 20, 30]
    # simulate the device streaming the same table back in 0x55 reply frames
    replies = []
    for f in pm.build_custom_led_write_frames(table):
        r = list(f)
        r[0] = pm.REPLY_MAGIC
        r[1] = pm.CMD_GET_CUSTOM_LED
        replies.append(r)
    assert pm.parse_custom_led_replies(replies) == \
        [(i, 10, 20, 30) for i in range(pm.CUSTOM_LED_COUNT)]


# ---------------- device info (cmd 0x10) ----------------
def test_device_info_request_and_reply():
    (f, b), = outs(pm.CMD_DEVICE_INFO)
    assert pm.build_device_info() == b
    vid, pid = pm.parse_device_info(reply_after(f["i"]))
    assert (vid, pid) == (0x0C45, 0x80A2)


# ---------------- dead zone via config write (cmd 0x21) ----------------
def test_deadzone_write_reproduces_capture():
    # the official flow: read the game-mode table (0x11), patch the top
    # dead-zone byte (SDK payload offset 8), write it back (0x21).
    # Reproduce it from the captured 0x11 reply, full-page convention.
    reads = outs(pm.CMD_CONFIG_READ, "DEADZONE_TOP_0.42mm")
    page0_reply = reply_after(reads[0][0]["i"])
    assert page0_reply[0] == pm.REPLY_MAGIC and page0_reply[1] == pm.CMD_CONFIG_READ
    payload = page0_reply[8:8 + pm.PAGE]               # full 56-byte page
    assert len(payload) == pm.PAGE
    assert payload[pm.CONFIG_DEADZONE_OFFSET] == 0x00  # before the change

    patched = pm.set_deadzone(payload, 0.42)
    assert patched[pm.CONFIG_DEADZONE_OFFSET] == 0x2A  # 42 * 0.01 mm

    captured_writes = [b for _, b in outs(pm.CMD_CONFIG_WRITE)]
    assert pm.build_config_write_frames(patched) == captured_writes


def test_deadzone_legacy_55_byte_slice_still_supported():
    # the pre-SDK-decode convention passed reply[9:] (55 bytes, table bytes
    # 1..55). It must still produce the identical captured frames — table
    # byte 0 was 0 in the capture and is unparsed by the SDK.
    reads = outs(pm.CMD_CONFIG_READ, "DEADZONE_TOP_0.42mm")
    page0_reply = reply_after(reads[0][0]["i"])
    legacy = page0_reply[9:9 + pm.PAGE]
    assert len(legacy) == pm.PAGE - 1
    patched = pm.set_deadzone(legacy, 0.42)
    assert patched[pm.CONFIG_DEADZONE_OFFSET - 1] == 0x2A
    captured_writes = [b for _, b in outs(pm.CMD_CONFIG_WRITE)]
    assert pm.build_config_write_frames(patched) == captured_writes


def test_set_deadzone_rejects_unverified_width():
    try:
        pm.set_deadzone([0] * pm.PAGE, 2.56)
    except ValueError:
        pass
    else:
        raise AssertionError("dead zone > 2.55 mm must be rejected (single-byte field)")


# ---------------- dangerous commands (0x4F / 0x0F / 0x64) ----------------
def test_no_builders_for_dangerous_commands():
    # the module must recognize the SDK's dangerous commands but expose NO
    # builder for them, and none may ever appear in the capture either.
    assert pm.DANGEROUS_CMDS == {0x4F, 0x0F, 0x64}
    module_cmds = {v for k, v in vars(pm).items()
                   if k.startswith("CMD_") and isinstance(v, int)}
    assert not (module_cmds & pm.DANGEROUS_CMDS)
    for f in FRAMES:
        b = fbytes(f)
        if len(b) >= 2:                # capture contains a few short frames
            assert b[1] not in pm.DANGEROUS_CMDS


# ---------------- unit helpers ----------------
def test_mm_raw_helpers():
    assert pm.mm_to_raw(0.31) == 0x1F
    assert pm.mm_to_raw(3.00) == 0x012C
    assert pm.mm_to_raw(1.25) == 0x7D
    assert pm.mm_to_raw(0.75) == 0x4B
    assert pm.mm_to_raw(-1) == 0
    assert pm.raw_to_mm(31) == 0.31
    assert pm.raw_to_mm(300) == 3.00


def test_record_is_little_endian():
    # SDK layout: [axisType][flags][trip LE16][press LE16][release LE16]
    assert pm._act_record(0, 3.00) == [0, 0, 0x2C, 0x01, 0, 0, 0, 0]
    assert pm._act_record(1, 3.00, 1.25, 0.75) == [0, 1, 0x2C, 0x01, 0x7D, 0, 0x4B, 0]
    assert pm._act_record(1, 3.00, 1.25, 0.75, 4) == [4, 1, 0x2C, 0x01, 0x7D, 0, 0x4B, 0]
    assert pm._act_record(True, 3.00) == pm._act_record(1, 3.00)   # bools OK


def test_to_report_prepends_report_id():
    f = pm.build_light(pm.LIGHT_MODE_STATIC)
    assert pm.to_report(f) == [0x00] + f


# =====================================================================
# Macro + key-table goldens — second capture: the 2026-07-21 full-app
# sweep (2883 frames) that drove the vendor driver's macro editor and
# key remapping UI:
#     docs/context/issue-6-mini60-pro-raw/webhid-capture-macros.json
# Same rules as above: builders must reproduce captured OUT frames BYTE
# FOR BYTE; structural tests are labelled where no captured frames exist.
# =====================================================================
CAPTURE_MACROS = os.path.join(ROOT, "docs", "context",
                              "issue-6-mini60-pro-raw",
                              "webhid-capture-macros.json")


def _load_macro_frames():
    with open(CAPTURE_MACROS, encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, str):          # double-JSON-encoded, like the first
        data = json.loads(data)
    return data["frames"]


FRAMES_M = _load_macro_frames()


def m_outs(cmd=None, label=None):
    got = []
    for f in FRAMES_M:
        if f["dir"] != "OUT":
            continue
        b = fbytes(f)
        if cmd is not None and b[1] != cmd:
            continue
        if label is not None and f["label"] != label:
            continue
        got.append((f, b))
    return got


def m_ins(cmd, label=None):
    got = []
    for f in FRAMES_M:
        if f["dir"] != "IN":
            continue
        b = fbytes(f)
        if b[1] != cmd:
            continue
        if label is not None and f["label"] != label:
            continue
        got.append((f, b))
    return got


def m_out_at(cmd, label, offset):
    for f, b in m_outs(cmd, label):
        if (b[3] | (b[4] << 8)) == offset:
            return b
    raise AssertionError(
        f"no OUT cmd={cmd:#x} label={label!r} offset={offset:#x} in macro capture")


# the two macros the capture stored, straight from the MARK labels
M1_LABEL = ("MACRO-1 SAVE (actual): M1 = [KeyA Press d=10][KeyA Lift d=10]"
            "[KeyB Press d=300][KeyB Lift d=10]")
M2_LABEL = ("MACRO-2 SAVE: M2 = KeyX:Press:11 | KeyX:Lift:22 | KeyY:Press:33"
            " | KeyY:Lift:44 | KeyZ:Press:55 | KeyZ:Lift:66 |"
            " ShiftLeft:Press:770 | ShiftLeft:Lift:888")
BIND1_LABEL = ("MACRO-BIND SAVE: key R-Ctrl/CPT (uiIdx59, tableIdx87) ->"
               " shortcut M1, mode=Play once")
BIND2_LABEL = ("MACRO-BIND-2 SAVE: key APP (uiIdx58, tableIdx86) ->"
               " shortcut M0, mode=Fixed number of times, loop=7")
REMAP2_LABEL = "REMAP-2: click SCROLL in function list"
IDXPROBE_LABEL = "IDXPROBE-SET: uiKey#0 (ESC) -> PAUSE"

M1_EVENTS = [(10, 0x04, True), (10, 0x04, False),
             (300, 0x05, True), (10, 0x05, False)]
M2_EVENTS = [(11, 0x1B, True), (22, 0x1B, False),
             (33, 0x1C, True), (44, 0x1C, False),
             (55, 0x1D, True), (66, 0x1D, False),
             (770, 0xE1, True), (888, 0xE1, False)]


# ---------------- macro writes (cmd 0x25) ----------------
def test_macro1_write_frames_match_capture():
    # golden — one 4-event macro in slot 0: the 400-byte header sweep
    # (7 x 0x38 + 0x08 @ 0x0188 final) then the single body chunk at 0x0190.
    captured = [b for _, b in m_outs(pm.CMD_MACRO_WRITE, M1_LABEL)]
    assert len(captured) == 9
    table = pm.build_macro_table({0: M1_EVENTS})
    assert pm.build_macro_write_frames(table) == captured


def test_macro2_write_frames_match_capture():
    # golden — two macros of DIFFERENT lengths (this is what pinned the
    # words-not-events count field): header now carries two u32 offsets,
    # then both bodies are rewritten, each as its own final-flagged chunk.
    captured = [b for _, b in m_outs(pm.CMD_MACRO_WRITE, M2_LABEL)]
    assert len(captured) == 10
    table = pm.build_macro_table({0: M1_EVENTS, 1: M2_EVENTS})
    assert pm.build_macro_write_frames(table) == captured


def test_macro_record_origin_at_absolute_byte_indices():
    # golden ORIGIN pin — literal captured bytes at absolute frame indices.
    # A build<->parse round trip CANNOT catch an origin off-by-one because
    # both halves would share it (that exact bug bit the actuation table).
    # Body chunk for macro 1 @ 0x01A4: count field at frame byte 8,
    # event 0 at frame byte 12, event 7 at frame byte 40.
    body = m_out_at(pm.CMD_MACRO_WRITE, M2_LABEL, 0x01A4)
    assert body[2] == 0x24                              # 4 + 8*4 bytes
    assert body[8:12] == [0x10, 0x00, 0x00, 0x00]       # count = 0x10 WORDS
    assert body[12:16] == [0x0B, 0x00, 0x1B, 0xB0]      # X down, 11 ms
    assert body[40:44] == [0x78, 0x03, 0xE1, 0x30]      # LShift up, 888 ms
    # header chunk 0: u32 LE offsets at frame bytes 8..15, literally
    # 400 and 420
    head = m_out_at(pm.CMD_MACRO_WRITE, M2_LABEL, 0x0000)
    assert head[8:16] == [0x90, 0x01, 0x00, 0x00, 0xA4, 0x01, 0x00, 0x00]
    # and the encoder reproduces the body bytes at the same origin
    enc = pm.encode_macro_events(M2_EVENTS)
    assert enc == body[8:8 + len(enc)]


def test_macro_encode_decode_round_trip_and_word_count():
    # golden values, structural symmetry: count is WORDS = events*2
    b1 = pm.encode_macro_events(M1_EVENTS)
    assert b1[:4] == [0x08, 0x00, 0x00, 0x00]           # 4 events -> 8 words
    assert len(b1) == 20
    b2 = pm.encode_macro_events(M2_EVENTS)
    assert b2[:4] == [0x10, 0x00, 0x00, 0x00]           # 8 events -> 16 words
    assert len(b2) == 36
    assert pm.decode_macro_events(b1) == M1_EVENTS
    assert pm.decode_macro_events(b2) == M2_EVENTS
    table = pm.build_macro_table({0: M1_EVENTS, 1: M2_EVENTS})
    assert pm.parse_macro_header(table)[:3] == [400, 420, 0]
    assert pm.parse_macro_table(table) == {0: M1_EVENTS, 1: M2_EVENTS}


# ---------------- macro reads (cmd 0x15) ----------------
def test_macro_header_read_frames_match_capture():
    # golden — the 8-frame header sweep the driver sends on page mount
    captured = [b for _, b in m_outs(pm.CMD_MACRO_READ, "NAV: Key remapping")]
    assert len(captured) == 8
    assert pm.build_macro_read_frames() == captured


def test_macro_two_step_body_read_matches_capture():
    # golden — after the M2 save the driver re-reads: header sweep, then
    # per macro a 4-byte count read followed by a count*2-byte body read.
    captured = [b for _, b in m_outs(pm.CMD_MACRO_READ, M2_LABEL)]
    expect = (pm.build_macro_read_frames()
              + [pm.build_macro_count_read(0x0190)]
              + pm.build_macro_body_read_frames(0x0190, 8)
              + [pm.build_macro_count_read(0x01A4)]
              + pm.build_macro_body_read_frames(0x01A4, 16))
    assert captured == expect


def test_macro_read_replies_decode_to_the_saved_macros():
    # golden — decode the captured 0x15 read-back replies:
    # count reply @0x0190 says 8 words; body reply @0x0194 is M1;
    # count @0x01A4 says 16 words; body @0x01A8 is M2.
    def reply_at(offset, label):
        for _, b in m_ins(pm.CMD_MACRO_READ, label):
            if (b[3] | (b[4] << 8)) == offset:
                return b
        raise AssertionError(f"no 0x15 reply @{offset:#x}")
    c1 = reply_at(0x0190, M2_LABEL)
    assert c1[8:10] == [0x08, 0x00]
    b1 = reply_at(0x0194, M2_LABEL)
    assert pm.decode_macro_events(list(c1[8:12]) + list(b1[8:8 + 16])) == M1_EVENTS
    c2 = reply_at(0x01A4, M2_LABEL)
    assert c2[8:10] == [0x10, 0x00]
    b2 = reply_at(0x01A8, M2_LABEL)
    assert pm.decode_macro_events(list(c2[8:12]) + list(b2[8:8 + 32])) == M2_EVENTS
    # and the sparse reassembler explains the header replies too
    header_replies = [b for _, b in m_ins(pm.CMD_MACRO_READ, M2_LABEL)
                      if (b[3] | (b[4] << 8)) < pm.MACRO_HEADER_SIZE]
    tbl = pm.parse_macro_replies(header_replies)
    assert pm.parse_macro_header(tbl)[:3] == [400, 420, 0]


def test_macro_body_read_paging_structural():
    # structural (SOURCE-ONLY: bodies > 0x38 bytes were never captured) —
    # a long body must page like every other table, final flag on the last
    # chunk only.
    frames = pm.build_macro_body_read_frames(0x0190, 40)   # 80 bytes
    assert len(frames) == 2
    assert frames[0][2] == 0x38 and (frames[0][3] | (frames[0][4] << 8)) == 0x0194
    assert frames[0][6] == 0x00
    assert frames[1][2] == 80 - 0x38
    assert (frames[1][3] | (frames[1][4] << 8)) == 0x0194 + 0x38
    assert frames[1][6] == 0x01


# ---------------- key table (0x12 read / 0x22 write) ----------------
def test_key_table_read_frames_match_capture():
    # golden — 512-byte read: 9 x 0x38 @ 0x0000..0x01C0 plus the 8-byte
    # tail @ 0x01F8 with the final flag (the capture contains 49 identical
    # sweeps; pin against the page-mount one).
    captured = [b for _, b in m_outs(pm.CMD_KEY_TABLE_READ, "NAV: Key remapping")]
    assert len(captured) == 10
    assert pm.build_key_table_read_frames() == captured


def test_key_table_macro_bind_writes_match_capture():
    # golden — both captured macro-bind saves, whole 9-frame write sweeps.
    # BIND1: only record 87 populated (06 01 00 01 = macro 1, play once).
    table = [0] * pm.KEY_TABLE_SIZE
    table[87 * 4:87 * 4 + 4] = pm.key_record_macro(1, pm.MACRO_PLAY_ONCE, 1)
    captured = [b for _, b in m_outs(pm.CMD_KEY_TABLE_WRITE, BIND1_LABEL)]
    assert len(captured) == 9
    assert pm.build_key_table_write_frames(table) == captured
    # BIND2: records 86 AND 87 (06 00 01 07 = macro 0, fixed x7 — differs
    # from record 87 in every byte, which is what disambiguated the fields)
    table[86 * 4:86 * 4 + 4] = pm.key_record_macro(0, pm.MACRO_PLAY_REPEAT, 7)
    captured2 = [b for _, b in m_outs(pm.CMD_KEY_TABLE_WRITE, BIND2_LABEL)]
    assert len(captured2) == 9
    assert pm.build_key_table_write_frames(table) == captured2


def test_key_table_remap_writes_match_capture():
    # golden — pageType-2 records: idx 86 -> Pause (0x48), idx 87 ->
    # Scroll Lock (0x47), then the ESC probe adds idx 0 -> Pause.
    table = [0] * pm.KEY_TABLE_SIZE
    table[86 * 4:86 * 4 + 4] = pm.key_record_remap(0x48)
    table[87 * 4:87 * 4 + 4] = pm.key_record_remap(0x47)
    captured = [b for _, b in m_outs(pm.CMD_KEY_TABLE_WRITE, REMAP2_LABEL)]
    assert pm.build_key_table_write_frames(table) == captured
    table[0:4] = pm.key_record_remap(0x48)
    captured2 = [b for _, b in m_outs(pm.CMD_KEY_TABLE_WRITE, IDXPROBE_LABEL)]
    assert pm.build_key_table_write_frames(table) == captured2


def test_key_record_origin_at_absolute_byte_indices():
    # golden ORIGIN pin — records are 4-aligned from frame byte 8 (an
    # off-by-one here mis-indexes every key; build<->parse symmetry alone
    # cannot catch it). Chunk @ 0x0150 of the BIND2 write: record 86 lives
    # at table byte 344 = 0x150 + 8 -> frame bytes 16..19, record 87 at
    # frame bytes 20..23 — the literal captured 06 00 01 07 / 06 01 00 01.
    chunk = m_out_at(pm.CMD_KEY_TABLE_WRITE, BIND2_LABEL, 0x0150)
    assert chunk[16:20] == [0x06, 0x00, 0x01, 0x07]
    assert chunk[20:24] == [0x06, 0x01, 0x00, 0x01]
    # record 0 starts exactly at frame byte 8 of the offset-0 chunk
    chunk0 = m_out_at(pm.CMD_KEY_TABLE_WRITE, IDXPROBE_LABEL, 0x0000)
    assert chunk0[8:12] == [0x02, 0x00, 0x48, 0x00]


def test_key_table_replies_parse_to_bound_records():
    # golden — reassemble a captured 0x12 read sweep (during the BIND2
    # flow, when record 87 already held the first bind) and parse it.
    replies = []
    seen = set()
    for _, b in m_ins(pm.CMD_KEY_TABLE_READ, BIND2_LABEL):
        off = b[3] | (b[4] << 8)
        if off not in seen:
            seen.add(off)
            replies.append(b)
    assert len(replies) == 10
    table = pm.parse_key_table_replies(replies)
    recs = pm.parse_key_table(table)
    assert recs[87] == {"type": "macro", "macro_index": 1,
                        "play_mode": 0, "loop_count": 1}
    assert recs[86] == {"type": "unassigned"}
    assert table[87 * 4:87 * 4 + 4] == [0x06, 0x01, 0x00, 0x01]


def test_key_record_helpers_validate_and_parse():
    # structural — helper validation + parse symmetry
    assert pm.key_record_remap(0x48) == [2, 0, 0x48, 0]
    assert pm.key_record_remap(0x04, modifiers=0x40) == [2, 0x40, 0x04, 0]
    assert pm.key_record_macro(0, 1, 7) == [6, 0, 1, 7]
    assert pm.key_record_unassigned() == [0, 0, 0, 0]
    assert pm.parse_key_record([2, 0x40, 0x04, 0]) == {
        "type": "keyboard", "modifiers": 0x40, "hid_usage": 0x04}
    assert pm.parse_key_record([6, 3, 2, 9]) == {
        "type": "macro", "macro_index": 3, "play_mode": 2, "loop_count": 9}
    assert pm.parse_key_record([0, 0, 0, 0]) == {"type": "unassigned"}
    assert pm.parse_key_record([11, 2, 0x31, 0x38])["type"] == "raw"
    for bad in (lambda: pm.key_record_macro(100),
                lambda: pm.key_record_macro(0, 5),
                lambda: pm.key_record_macro(0, 0, 300)):
        try:
            bad()
        except ValueError:
            pass
        else:
            raise AssertionError("invalid macro record accepted")


def test_key_table_write_rejects_nonzero_tail():
    # structural — the vendor write path covers only records 0..125; a
    # 512-byte table with data in bytes 504..511 must be refused rather
    # than silently truncated.
    table = [0] * pm.KEY_TABLE_SIZE
    table[510] = 1
    try:
        pm.build_key_table_write_frames(table)
    except ValueError:
        pass
    else:
        raise AssertionError("nonzero tail must be rejected")
    # a bare 504-byte write image is accepted as-is
    assert len(pm.build_key_table_write_frames([0] * pm.KEY_TABLE_WRITE_SIZE)) == 9


# ---------------- 504-vs-512 discrepancy (RESOLVED from this capture) ----------------
def test_custom_led_504_not_512_evidence():
    # golden EVIDENCE — FULL_APP_CAPTURE_NOTES.md claims the per-key RGB
    # table is "512 bytes = 128 records"; the captured frames say 504:
    # every 0x24 write and 0x14 read pages exactly 9 x 0x38 = 504 bytes
    # (never an offset >= 0x1F8), and the final write chunk's explicit LED
    # ids run 0x70..0x7D = 112..125. CUSTOM_LED_TABLE_SIZE = 504 stands.
    led_writes = m_outs(pm.CMD_SET_CUSTOM_LED)
    assert led_writes
    covered = set()
    for f, b in led_writes:
        off = b[3] | (b[4] << 8)
        assert b[2] == pm.PAGE
        assert off + b[2] <= pm.CUSTOM_LED_TABLE_SIZE     # never past 504
        assert b[6] == (0x01 if off == 0x01C0 else 0x00)  # final @ 0x01C0
        covered.add(off)
        if off == 0x01C0:
            ids = [b[8 + 4 * k] for k in range(14)]
            assert ids == list(range(0x70, 0x7E))         # 112..125, NOT ..127
    assert covered == set(range(0, pm.CUSTOM_LED_TABLE_SIZE, pm.PAGE))
    for f, b in m_outs(pm.CMD_GET_CUSTOM_LED):
        assert (b[3] | (b[4] << 8)) + b[2] <= pm.CUSTOM_LED_TABLE_SIZE
    # the existing 0x14 read builder also reproduces this capture's sweeps
    sweep = [b for _, b in m_outs(pm.CMD_GET_CUSTOM_LED)][:9]
    assert list(pm.build_custom_led_read_frames()) == sweep
    # contrast: the KEY table genuinely is 512 on reads — its 0x12 sweeps
    # reach the 8-byte tail at 0x01F8 — while its writes stop at 504.
    read_top = max((b[3] | (b[4] << 8)) + b[2]
                   for _, b in m_outs(pm.CMD_KEY_TABLE_READ))
    write_top = max((b[3] | (b[4] << 8)) + b[2]
                    for _, b in m_outs(pm.CMD_KEY_TABLE_WRITE))
    assert read_top == pm.KEY_TABLE_SIZE == 512
    assert write_top == pm.KEY_TABLE_WRITE_SIZE == 504


def test_macro_capture_contains_no_dangerous_commands():
    # the safety rule holds across the second capture too
    for f in FRAMES_M:
        if f["dir"] not in ("OUT", "IN"):
            continue
        b = fbytes(f)
        if len(b) >= 2:
            assert b[1] not in pm.DANGEROUS_CMDS


# =====================================================================
# Wireless (2.4GHz dongle, 0C45:FEFE) goldens — captures taken with the
# USB-C cable UNPLUGGED so the board ran on its receiver only:
#   webhid-capture-dongle-2026-07-20.json   (0x17/0x11 reads + the full
#                                            0x27 write pass)
#   webhid-capture-dongle-handshake.json    (the vendor connect handshake:
#                                            0x10/0x13/0x12/0x14 sweeps
#                                            WITH their 0x55 IN replies)
# Every frame is 32 bytes; payload chunk = frameLen - 8 = 0x18. Builders
# take frame_len=pm.FRAME_LEN_WIRELESS and must reproduce the captured OUT
# frames BYTE FOR BYTE. Lighting 0x23 frames come from the FIRST wireless
# session, whose in-page buffer was lost — those literals are transcribed
# by hand in WIRELESS_DONGLE_FINDINGS.md and are marked
# CONFIRMED-BY-CAPTURE (transcribed) below. The transport itself is
# HARDWARE-VERIFIED (usage_page 0xFF60, usage 0x61, report id 0): lighting
# + the 21-chunk 0x24 table rendered visibly over the dongle, and
# 0x10/0x12/0x13/0x17 answer 0x55 replies on a raw handle.
# =====================================================================
CAPTURE_DONGLE = os.path.join(ROOT, "docs", "context",
                              "issue-6-mini60-pro-raw",
                              "webhid-capture-dongle-2026-07-20.json")
CAPTURE_HANDSHAKE = os.path.join(ROOT, "docs", "context",
                                 "issue-6-mini60-pro-raw",
                                 "webhid-capture-dongle-handshake.json")
W = 32   # pm.FRAME_LEN_WIRELESS, spelled out where it is asserted


def _load_capture(path):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, str):          # double-JSON-encoded, like the others
        data = json.loads(data)
    return data["frames"]


FRAMES_D = _load_capture(CAPTURE_DONGLE)
FRAMES_H = _load_capture(CAPTURE_HANDSHAKE)


def d_outs(cmd=None, label=None, frames=None):
    got = []
    for f in (frames if frames is not None else FRAMES_D):
        if f["dir"] != "OUT":
            continue
        b = fbytes(f)
        if cmd is not None and b[1] != cmd:
            continue
        if label is not None and f["label"] != label:
            continue
        got.append((f, b))
    return got


def h_outs(cmd=None):
    return d_outs(cmd, frames=FRAMES_H)


def h_ins(cmd):
    return [fbytes(f) for f in FRAMES_H
            if f["dir"] == "IN" and fbytes(f)[1] == cmd]


def test_wireless_frame_len_constant_and_page_rule():
    # the headline rule: chunk = frameLen - 8 on both transports
    assert pm.FRAME_LEN_WIRELESS == W == 32
    assert pm.page_size(pm.FRAME_LEN) == pm.PAGE == 0x38
    assert pm.page_size(W) == 0x18
    # PAGE itself is now derived, not hardcoded
    assert pm.PAGE == pm.FRAME_LEN - pm.PAYLOAD_START
    # wired paging constants are unchanged by the parameterisation
    assert pm.ACT_PAGE_OFFSETS == pm.act_page_offsets(pm.FRAME_LEN)
    assert pm.ACT_RECORDS_PER_FRAME == pm.act_records_per_frame(pm.FRAME_LEN) == 7
    assert pm.CUSTOM_LED_PAGE_OFFSETS == pm.custom_led_page_offsets(pm.FRAME_LEN)
    # wireless geometry: 42 actuation pages of 24 ending 0x3D8 (984), and
    # 984 + 24 = 1008 = the SAME table size as wired
    offs = pm.act_page_offsets(W)
    assert len(offs) == 42 and offs[0] == 0 and offs[-1] == 0x03D8
    assert offs[-1] + pm.page_size(W) == pm.ACT_TABLE_SIZE == 0x3F0
    assert pm.act_records_per_frame(W) == 3            # 8 + 3*8 == 32


def test_wireless_capture_is_all_32_byte_fefe_frames():
    # golden — every OUT frame in the dongle capture: len 32, VID:PID
    # 0C45:FEFE, 0xAA magic, and never a dangerous command
    outs32 = d_outs()
    assert outs32
    for f, b in outs32:
        assert f["len"] == 32 and len(b) == 32, f"frame i={f['i']}"
        assert (f["vid"], f["pid"]) == (0x0C45, 0xFEFE)
        assert b[0] == pm.MAGIC
        assert b[1] not in pm.DANGEROUS_CMDS


def test_wireless_actuation_read_sweep_matches_builder():
    # golden — the clean 42-frame 0x17 sweep before the captured write pass
    # (TRIP_STEPPER_UP label): offsets 0x0000..0x03D8 step 0x18, length
    # 0x18, final flag ONLY on the 0x03D8 page
    captured = [b for _, b in d_outs(pm.CMD_ACTUATION_READ, "TRIP_STEPPER_UP")]
    assert len(captured) == 42
    assert list(pm.iter_actuation_reads(frame_len=W)) == captured


def test_wireless_config_read_frames_match_capture():
    # golden — the 0x40-byte game-mode table paged at 32-byte frames:
    # 0x18 @ 0x0000, 0x18 @ 0x0018, 0x10 @ 0x0030 with the final flag —
    # the same generic chunk = frameLen - 8 paging as wired
    captured = [b for _, b in d_outs(pm.CMD_CONFIG_READ)]
    assert len(captured) == 3
    assert pm.build_config_read_frames(frame_len=W) == captured
    assert [b[2] for b in captured] == [0x18, 0x18, 0x10]
    assert [b[6] for b in captured] == [0, 0, 1]


def test_wireless_config_write_frames_mirror_captured_read_paging():
    # structural — no 0x21 was captured on the dongle; the write shape must
    # mirror the CAPTURED 0x11 read paging exactly (same chunk lengths,
    # same offsets, final on the last chunk), payload from byte 8
    payload = list(range(1, pm.PAGE + 1))              # 56 marked bytes
    frames = pm.build_config_write_frames(payload, frame_len=W)
    reads = [b for _, b in d_outs(pm.CMD_CONFIG_READ)]
    assert [(f[2], f[3] | (f[4] << 8), f[6]) for f in frames] == \
        [(b[2], b[3] | (b[4] << 8), b[6]) for b in reads]
    rebuilt = []
    for f in frames:
        rebuilt += f[8:8 + f[2]]
    assert rebuilt == payload + [0] * 8                # zero tail 56..63
    # and the wired shape is untouched by the refactor (byte-identical to
    # the capture-pinned two-frame sequence)
    wired = pm.build_config_write_frames(payload)
    assert [(f[2], f[3] | (f[4] << 8), f[6]) for f in wired] == \
        [(0x38, 0x0000, 0), (0x08, 0x0038, 1)]


def test_wireless_actuation_write_pass_golden():
    # golden — the complete captured 0x27 write pass (a 0.31 mm trip
    # committed through the vendor UI): 42 frames at 0x0000..0x03D8, len
    # 0x18, final flag only on the last
    writes = [b for _, b in d_outs(pm.CMD_ACTUATION, "TRIP_STEPPER_UP")]
    assert len(writes) == 42
    offsets = [b[3] | (b[4] << 8) for b in writes]
    assert offsets == list(pm.act_page_offsets(W))
    assert all(b[2] == 0x18 for b in writes)
    assert [b[6] for b in writes] == [0] * 41 + [1]
    # single-record page 0: fixed actuation 0.31 mm -> 1F 00 LE at [10..11]
    assert pm.build_actuation_frame(0x0000, [(0, 0.31)], frame_len=W) == writes[0]
    # full page 0x90: all 3 slots populated — 3 whole records fill a
    # 32-byte frame exactly (8 + 3*8 == 32)
    assert pm.build_actuation_frame(0x0090, [(0, 0.31)] * 3,
                                    frame_len=W) == writes[6]
    # sparse page 0x78: slots 0-1 are unused matrix positions
    assert pm.build_actuation_frame(0x0078, [None, None, (0, 0.31)],
                                    frame_len=W) == writes[5]
    # final page: empty, final flag set (matches the findings doc's quoted
    # AA 27 18 D8 03 00 01 00 frame)
    assert pm.build_actuation_frame(0x03D8, [], final=True,
                                    frame_len=W) == writes[41]


def test_wireless_actuation_record_origin_absolute():
    # golden ORIGIN pin at 32 bytes — literal captured bytes at absolute
    # frame indices (parse<->build symmetry cannot catch a shared origin
    # error; this class of bug bit the wired decode once already).
    # Page 0x90 carries three identical fixed-actuation records:
    # [axisType=0][flags=0][trip 1F 00][press 00 00][release 00 00]
    page = next(b for _, b in d_outs(pm.CMD_ACTUATION, "TRIP_STEPPER_UP")
                if (b[3] | (b[4] << 8)) == 0x0090)
    REC = [0x00, 0x00, 0x1F, 0x00, 0x00, 0x00, 0x00, 0x00]
    for k in range(3):
        base = 8 + k * pm.ACT_RECORD_SIZE
        assert page[base:base + pm.ACT_RECORD_SIZE] == REC, \
            f"record {k} does not start at frame byte {base}"
    assert 8 + 3 * pm.ACT_RECORD_SIZE == W    # nothing truncated at the edge


def test_wireless_every_actuation_frame_roundtrips():
    # parse + rebuild must explain every byte of every captured 0x27 frame
    # at the wireless frame size (parse_actuation_records sizes its slot
    # count from the frame's own length: 3 slots for 32-byte frames)
    writes = d_outs(pm.CMD_ACTUATION)
    assert writes
    for f, b in writes:
        offset = b[3] | (b[4] << 8)
        recs = pm.parse_actuation_records(b)
        assert len(recs) == 3
        rebuilt = pm.build_actuation_frame(offset, recs, final=bool(b[6]),
                                           frame_len=W)
        assert rebuilt == b, f"frame i={f['i']} offset={offset:#x}"


def test_wireless_lighting_frames_transcribed_golden():
    # golden against HAND-TRANSCRIBED literals — CONFIRMED-BY-CAPTURE
    # (transcribed): the first wireless session's in-page buffer was lost
    # when the link dropped, so these bytes exist only as verbatim
    # transcriptions in WIRELESS_DONGLE_FINDINGS.md, not in a JSON file.
    # They are the frames that RESOLVED colorMode (byte [16]): fixed-colour
    # Static sends 0, multicolour Spectrum/Shuttle send 1 — both values on
    # the same board, correlated with the mode, matching the SDK's
    # `colorMode = randomColor ? 1 : 0`.
    def wire(hexstr):
        b = list(bytes.fromhex(hexstr.replace(" ", "")))
        return b + [0] * (W - len(b))          # transcription covers 24 bytes
    static = wire("AA 23 10 00 00 00 01 00 01 90 EE 90 FF 00 00 00"
                  " 00 01 01 00 00 00 AA 55")
    spectrum = wire("AA 23 10 00 00 00 01 00 08 90 EE 90 FF 00 00 00"
                    " 01 01 01 00 00 00 AA 55")
    shuttle = wire("AA 23 10 00 00 00 01 00 13 90 EE 90 FF 00 00 00"
                   " 01 01 01 00 00 00 AA 55")
    assert pm.build_light(pm.LIGHT_MODE_STATIC, brightness=1, speed=1,
                          color_mode=0, frame_len=W) == static
    assert pm.build_light(pm.LIGHT_MODE_SPECTRAL_CYCLING, brightness=1,
                          speed=1, color_mode=1, frame_len=W) == spectrum
    assert pm.build_light(pm.LIGHT_MODE_SHUTTLING, brightness=1, speed=1,
                          color_mode=1, frame_len=W) == shuttle
    # marker + colorMode land at the same absolute offsets at 32 bytes
    assert static[16] == 0 and spectrum[16] == 1
    assert static[22:24] == [0xAA, 0x55]


def test_wireless_lighting_read_transcribed_golden():
    # CONFIRMED-BY-CAPTURE (transcribed): AA 13 10 00 00 00 01 00 at 32
    # bytes — identical header to the wired 0x13 single read
    expect = [0xAA, 0x13, 0x10, 0, 0, 0, 0x01, 0] + [0] * 24
    assert pm.build_light_read(frame_len=W) == expect


def test_colormode_default_keeps_wired_goldens_byte_identical():
    # the colorMode parameter must default to TODAY'S byte (1) so every
    # legacy caller and wired golden is untouched
    for mode in (pm.LIGHT_MODE_STATIC, pm.LIGHT_MODE_SPECTRAL_CYCLING,
                 pm.LIGHT_MODE_CUSTOM):
        dflt = pm.build_light(mode)
        assert dflt == pm.build_light(mode, color_mode=1, frame_len=64)
        assert dflt[16] == 0x01 and len(dflt) == 64
    # and colorMode 0 changes byte [16] ONLY
    a = pm.build_light(pm.LIGHT_MODE_STATIC)
    b = pm.build_light(pm.LIGHT_MODE_STATIC, color_mode=0)
    assert [i for i in range(64) if a[i] != b[i]] == [16]


def test_frame_builder_refuses_oversize_chunks():
    # the anti-truncation guard: a chunk that cannot fit the frame's
    # payload space must raise, not silently build the malformed frame
    # that misled the first dongle probe (64-byte frame, 32-byte report)
    try:
        pm._frame(pm.CMD_ACTUATION, 0x38, frame_len=W)
    except ValueError:
        pass
    else:
        raise AssertionError("length 0x38 must not fit a 32-byte frame")
    try:
        pm.build_table_read(pm.CMD_ACTUATION_READ, 0, length=pm.PAGE,
                            frame_len=W)
    except ValueError:
        pass
    else:
        raise AssertionError("PAGE-length read must not fit a 32-byte frame")
    # the default read length follows the frame size instead
    f = pm.build_table_read(pm.CMD_ACTUATION_READ, 0, frame_len=W)
    assert f[2] == 0x18 and len(f) == W


def test_wireless_paged_table_shapes_structural():
    # structural (SOURCE-ONLY shapes — 0x12/0x14/0x24 were never captured
    # on the dongle): generic paging at 32 bytes must cover each table
    # exactly, chunk 0x18, final flag on the last chunk only
    key_reads = pm.build_key_table_read_frames(frame_len=W)
    assert len(key_reads) == 22                       # 21 x 0x18 + 8 tail
    assert key_reads[-1][2] == 0x08
    assert (key_reads[-1][3] | (key_reads[-1][4] << 8)) == 0x01F8
    assert [f[6] for f in key_reads] == [0] * 21 + [1]
    led_offs = pm.custom_led_page_offsets(W)
    assert len(led_offs) == 21 and led_offs[-1] + 0x18 == pm.CUSTOM_LED_TABLE_SIZE
    table = pm.build_custom_led_table([(1, 2, 3)] * pm.CUSTOM_LED_COUNT)
    writes = list(pm.build_custom_led_write_frames(table, frame_len=W))
    assert len(writes) == 21
    assert all(len(f) == W for f in writes)
    rebuilt = []
    for f in writes:
        rebuilt += f[8:8 + f[2]]
    assert rebuilt == table                           # covers all 504 bytes


def test_wireless_device_info_paged_sweep_golden():
    # golden (handshake capture) — 0x10 device info is a PAGED read of a
    # 56-byte info blob, which is WHY the wired form is a single 0x38
    # chunk: one rule (chunk = frameLen - 8) explains both transports.
    #   wired:    [AA 10 38 @0 final]
    #   wireless: [AA 10 18 @0, AA 10 18 @0x18, AA 10 08 @0x30 final]
    sweep = [b for _, b in h_outs(pm.CMD_DEVICE_INFO)]
    # the handshake capture repeats the sweep; dedupe to the first pass
    first = sweep[:3]
    assert [(b[2], b[3] | (b[4] << 8), b[6]) for b in first] == \
        [(0x18, 0x0000, 0), (0x18, 0x0018, 0), (0x08, 0x0030, 1)]
    assert pm.build_device_info_frames(frame_len=W) == first
    # wired single-frame shape is unchanged (== the whole wired sweep)
    wired = pm.build_device_info()
    assert wired[:8] == [0xAA, 0x10, 0x38, 0, 0, 0, 1, 0] and len(wired) == 64
    assert pm.build_device_info_frames() == [wired]
    # build_device_info(frame_len) is the VID/PID-bearing offset-0 chunk
    assert pm.build_device_info(frame_len=W) == first[0]


def test_wireless_device_info_reply_reports_wired_identity():
    # golden (handshake capture IN frames) — the offset-0 0x55 reply over
    # the DONGLE parses to the WIRED identity 0x0C45:0x80A2 at the same
    # reply offsets as the wired capture: the RF bridge is transparent and
    # the firmware answers. Callers must not use 0x10 to identify the
    # transport. (fw version at [16..17] = 53 01 = V1.53, matching wired.)
    replies = [r for r in h_ins(pm.CMD_DEVICE_INFO)
               if (r[3] | (r[4] << 8)) == 0 and r[0] == pm.REPLY_MAGIC]
    assert replies
    for r in replies:
        assert len(r) == W
        assert pm.parse_device_info(r) == (0x0C45, 0x80A2)
        assert r[16:18] == [0x53, 0x01]


def test_wireless_handshake_light_read_golden():
    # golden (handshake capture) — upgrades the transcribed 0x13 literal to
    # a file-backed golden: AA 13 10 00 00 00 01 00 at 32 bytes, and the
    # firmware answers it with a 0x55 reply
    reads = [b for _, b in h_outs(pm.CMD_LIGHT_READ)]
    assert reads
    for b in reads:
        assert pm.build_light_read(frame_len=W) == b
    assert h_ins(pm.CMD_LIGHT_READ)          # replied — the collection works


def test_wireless_handshake_key_table_sweep_golden():
    # golden (handshake capture) — the 512-byte 0x12 key-table read at
    # 32-byte frames: 21 x 0x18 (0x0000..0x01E0) + the 0x08 tail @ 0x01F8
    # with the final flag. The capture holds two identical sweeps.
    sweep = [b for _, b in h_outs(pm.CMD_KEY_TABLE_READ)]
    assert len(sweep) == 44
    expect = pm.build_key_table_read_frames(frame_len=W)
    assert len(expect) == 22
    assert sweep[:22] == expect and sweep[22:] == expect


def test_wireless_handshake_custom_led_sweep_golden():
    # golden (handshake capture) — the 504-byte 0x14 per-key RGB read at
    # 32-byte frames: 21 x 0x18, final flag on the 0x01E0 page (504 = 21*24
    # exactly — no short tail, unlike the key table). Two sweeps captured.
    sweep = [b for _, b in h_outs(pm.CMD_GET_CUSTOM_LED)]
    assert len(sweep) == 42
    expect = list(pm.build_custom_led_read_frames(frame_len=W))
    assert len(expect) == 21
    assert expect[-1][2] == 0x18
    assert (expect[-1][3] | (expect[-1][4] << 8)) == 0x01E0
    assert sweep[:21] == expect and sweep[21:] == expect


def test_wireless_handshake_meta_pins_the_transport():
    # the capture's own meta block records the HARDWARE-VERIFIED transport:
    # vendor collection usagePage 0xFF60 usage 0x61, report id 0, 32-byte
    # reports — and that 0x10 reports the wired 0x80A2 identity
    with open(CAPTURE_HANDSHAKE, encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, str):
        data = json.loads(data)
    meta = data["meta"]
    vc = meta["vendorCollection"]
    assert vc["usagePage"] == "0xFF60" and vc["usage"] == "0x61"
    assert vc["reportId"] == 0 and vc["reportBytes"] == 32
    assert meta["frameLen"] == 32 and meta["payloadChunk"] == 24
    assert "0x80A2" in meta["reportedDeviceInfoPid"]


def test_wireless_handshake_contains_no_dangerous_commands():
    # the safety rule holds across the dongle captures too
    for f in FRAMES_H + FRAMES_D:
        if f.get("dir") not in ("OUT", "IN"):
            continue
        b = fbytes(f)
        if len(b) >= 2:
            assert b[1] not in pm.DANGEROUS_CMDS


# ============== registry <-> capture cross-checks (added 2026-07-21) =======
# The registry's MINI lighting block is what the UI's mode grid renders and
# what the driver now resolves native mode bytes against (drivers/mini60
# `_native_modes`). Until now nothing checked that table against the
# CAPTURE it claims to describe — a typo'd or invented byte would have
# reached the wire unchallenged, which is exactly the failure class that
# has bitten this project. Every assertion below is anchored either to a
# labelled captured frame or to a protocol_mini60 constant that is itself
# capture-pinned above.
import boards                                            # noqa: E402

REG = boards.load_registry()
MINI_WIRED = REG.by_slug("aula-mini60he-pro")
MINI_24G = REG.by_slug("aula-mini60he-pro-24g")


def _modes(profile):
    return {m["byte"]: m for m in profile.lighting["modes"]}


def test_registry_mode_table_is_exactly_the_captured_firmware_modes():
    """The 19 firmware effects the vendor UI drove on hardware (mode bytes
    1..19, each with its own labelled 0x23 frame) plus the structural
    per-key custom byte 20 — no more, no less. An extra registry byte would
    be an invented mode the UI offers and the firmware ignores; a missing
    one is a mode the user cannot reach."""
    by_byte = _modes(MINI_WIRED)
    assert sorted(by_byte) == list(range(1, 21))
    assert sorted(pm.LIGHT_MODE_NAMES) == list(range(1, 21))
    captured = {b[8] for _, b in outs(pm.CMD_LIGHTING)}
    assert captured == set(range(1, 20))          # 20 was never captured
    assert set(by_byte) - {pm.LIGHT_MODE_CUSTOM} == captured
    ids = [m["id"] for m in MINI_WIRED.lighting["modes"]]
    names = [m["name"] for m in MINI_WIRED.lighting["modes"]]
    assert len(set(ids)) == len(ids) == 20
    assert len(set(names)) == len(names) == 20


def test_registry_off_and_custom_bytes_match_the_protocol_constants():
    """offModeByte / customModeByte are the two bytes with SEMANTICS
    attached (lights off; gate for the 0x24 per-key table). Both are
    protocol constants, and mode 0 must NOT be listed as a selectable mode
    — the driver's Win60 alias for Api mode 0 depends on 0 not being
    native."""
    lt = MINI_WIRED.lighting
    assert lt["offModeByte"] == 0
    assert lt["customModeByte"] == pm.LIGHT_MODE_CUSTOM == 20
    assert 0 not in _modes(MINI_WIRED)
    off = pm.build_light(lt["offModeByte"])
    assert off[8] == 0 and off[1] == pm.CMD_LIGHTING and off[16] == 0x01


def test_every_registry_mode_byte_builds_a_valid_lighting_frame():
    """Absolute-offset guard: whatever byte the registry declares must land
    at frame byte 8 of a well-formed 0x23 frame — the same offset the
    capture goldens pin — and nowhere else."""
    for byte in sorted(_modes(MINI_WIRED)):
        f = pm.build_light(byte, 0x11, 0x22, 0x33, brightness=5, speed=5)
        assert f[0] == 0xAA and f[1] == pm.CMD_LIGHTING and f[2] == 0x10
        assert f[8] == byte
        assert f[9:12] == [0x11, 0x22, 0x33]
        assert f[16] == 0x01 and f[17] == 5 and f[18] == 5
        assert f[22] == 0xAA and f[23] == 0x55
        assert len(f) == pm.FRAME_LEN


def test_registry_slider_scale_matches_the_captured_frames():
    """MINI sliders are 0..5 (the Win60's are 0..4) — the reason a
    board-neutral slider must read the registry. Every captured brightness
    and speed byte falls inside the declared range, and the top of the
    range was actually observed (5)."""
    lt = MINI_WIRED.lighting
    assert (lt["brightnessMin"], lt["brightnessMax"]) == (0, 5)
    assert (lt["speedMin"], lt["speedMax"]) == (0, 5)
    bri = {b[17] for _, b in outs(pm.CMD_LIGHTING)}
    spd = {b[18] for _, b in outs(pm.CMD_LIGHTING)}
    assert max(bri) == 5                        # top of the scale, on the wire
    assert all(lt["brightnessMin"] <= v <= lt["brightnessMax"] for v in bri)
    assert all(lt["speedMin"] <= v <= lt["speedMax"] for v in spd)


def test_wired_and_dongle_declare_the_same_firmware_mode_table():
    """One keyboard, two transports: the 2.4GHz dongle entry is the SAME
    firmware, so its mode table must be identical byte-for-byte (the
    wireless lighting goldens above are transcriptions of the same 0x23
    frames at 32-byte framing). Only the host-stream capability differs —
    the RF bridge drops 0x32."""
    assert MINI_24G.lighting["modes"] == MINI_WIRED.lighting["modes"]
    for field in ("offModeByte", "customModeByte", "brightnessMax",
                  "speedMax", "modeListSource"):
        assert MINI_24G.lighting[field] == MINI_WIRED.lighting[field], field
    assert MINI_WIRED.lighting["hostEngine"] is True
    assert MINI_24G.lighting["hostEngine"] is False


def test_registry_mode_byte_10_is_native_and_not_the_win60_custom_alias():
    """The trap that produced the colorful-cross bug, pinned as DATA: byte
    10 is a real MINI firmware mode (captured, labelled), while on the
    Win60 byte 10 is `custom`. Any Win60->MINI vocabulary translation must
    therefore be gated on this table, never applied unconditionally."""
    assert _modes(MINI_WIRED)[10]["id"] == "colorful-cross"
    win60_by_byte = {m["byte"]: m["id"]
                     for m in REG.by_slug("aula-win60-he").lighting["modes"]}
    assert win60_by_byte[10] == "custom"          # same byte, other meaning
    assert pm.LIGHT_MODE_CUSTOM != 10
    # the captured frame for byte 10 is a firmware effect, not a per-key gate
    (f, b), = outs(pm.CMD_LIGHTING, "LIGHT_MODE: %s" % LIGHT_LABELS[9])
    assert b[8] == 10 and pm.build_light(10) == b


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception:
            failed += 1
            print(f"FAIL {fn.__name__}")
            traceback.print_exc()
    sys.exit(1 if failed else 0)
