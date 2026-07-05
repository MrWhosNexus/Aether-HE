"""Golden-frame tests for protocol_sonix — every expected frame here was taken
verbatim from the USBPcap capture attached to GitHub issue #4 (Aula MINI60HE Max,
0C45:80A1). If a builder stops matching the capture, it has regressed.

Run: python -m pytest tests/test_protocol_sonix.py  (or run this file directly)
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import protocol_sonix as ps


def H(s):
    """hex string (captured frame) -> list[int]."""
    return list(bytes.fromhex(s))


# ---- lighting (cmd 0x23): captured frames, byte-for-byte ----
LIGHT_FRAMES = {
    # (mode, flag): captured 64-byte frame
    (0x0F, 0): "aa231000000001000f90ee90ff000000000504000000aa55" + "00" * 40,
    (0x02, 1): "aa231000000001000290ee90ff000000010504000000aa55" + "00" * 40,
    (0x02, 0): "aa231000000001000290ee90ff000000000504000000aa55" + "00" * 40,
    (0x0D, 1): "aa231000000001000d90ee90ff000000010504000000aa55" + "00" * 40,
    (0x0D, 0): "aa231000000001000d90ee90ff000000000504000000aa55" + "00" * 40,
}


def test_lighting_frames_match_capture():
    for (mode, flag), hexframe in LIGHT_FRAMES.items():
        got = ps.build_light(mode, flag=flag)
        assert len(got) == 64
        assert got == H(hexframe), f"mode={mode:#x} flag={flag}"


def test_lighting_marker_and_cmd():
    f = ps.build_light(ps.LIGHT_MODE_STATIC)
    assert f[0] == 0xAA and f[1] == ps.CMD_LIGHTING
    assert f[22] == 0xAA and f[23] == 0x55  # template marker


# ---- actuation (cmd 0x27): captured frames ----
# Single key (offset 0), fixed actuation 2.00 mm (press == release).
ACT_OFFSET0 = "aa273800000000000001aa00c800c800" + "00" * 48
# Six identical fixed-2.00mm records at table offset 0xA8, 7th truncated at the
# 64-byte frame edge (verbatim from the capture).
ACT_OFFSETA8 = ("aa2738a8000000000001aa00c800c8000001aa00c800c8000001aa00c800c800"
                "0001aa00c800c8000001aa00c800c8000001aa00c800c8000001aa00c800c800")


def test_actuation_single_key_offset0():
    got = ps.build_actuation_frame(0x00, [(True, ps.ACT_MODE_FIXED, 2.00, 2.00)])
    assert got == H(ACT_OFFSET0)


def test_actuation_paged_offset_a8():
    recs = [(True, ps.ACT_MODE_FIXED, 2.00, 2.00)] * 7  # 7th truncates at frame edge
    got = ps.build_actuation_frame(0xA8, recs)
    assert got[:5] == [0xAA, 0x27, 0x38, 0xA8, 0x00]
    assert got == H(ACT_OFFSETA8)


def test_actuation_rapid_trigger_values_be16():
    # 0.50 mm press / 0.80 mm release -> 0x0032 / 0x0050 big-endian (capture had 0x43 mode)
    rec = ps._act_record(True, ps.ACT_MODE_RT, 0.50, 0.80)
    assert rec == [1, 0x43, 0x00, 0x32, 0x00, 0x50, 0x00, 0x00]


def test_mm_to_raw():
    assert ps.mm_to_raw(2.00) == 200
    assert ps.mm_to_raw(0.08) == 8
    assert ps.mm_to_raw(-1) == 0


def test_to_report_prepends_report_id():
    f = ps.build_light(ps.LIGHT_MODE_STATIC)
    assert ps.to_report(f) == [0x00] + f


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
