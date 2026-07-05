"""Golden-frame tests for protocol_sayo — every expected packet here was taken
verbatim from the USBPcap captures attached to GitHub issue #3 (Aula WIN 60 HE
Pro / SayoDevice, 8089:0009), staged at docs/context/issue-3-sayodevice-raw/.
If a builder stops matching the captures, it has regressed.

Run: python -m pytest tests/test_protocol_sayo.py  (or run this file directly)
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import protocol_sayo as psy


def P(hexhead):
    """captured packet head (hex) zero-padded to the 1024-byte wire packet."""
    b = bytes.fromhex(hexhead)
    return list(b + b"\x00" * (1024 - len(b)))


# ---- lighting (cmd 0x26): rgb.pcapng frames 19 and 23, byte-for-byte ----
LIGHT_PACKETS = {
    # mode (data[3] of the 0x26 blob): captured packet
    0x01: ("2212c849340026000040ff0100002764000000ff000000ff000000ff00000000"
           "ff00ffffffff0000ffff0000ffff000000aeffff96729672"),
    0x00: ("2212c848340026000040ff0000002764000000ff000000ff000000ff00000000"
           "ff00ffffffff0000ffff0000ffff000000aeffff96729672"),
}

# ---- save (cmd 0x0D): rgb.pcapng frame 21 / actuation.pcapng frame 174 ----
SAVE_PACKET = "2212cb8406000d009672"

# ---- key poll (cmd 0x15): actuation.pcapng frames 22..234 (key 0x2F) ----
POLL_PACKET = "22126b13050015012f"

# ---- per-key analog write (cmd 0x1C): actuation.pcapng frame 128, key 0x2F ----
ANALOG_PACKET = ("221256771c001c2fa2780300a278742850020000d0072c01e7000a0f"
                 "82008200")


def test_lighting_packets_match_capture():
    for mode, hexhead in LIGHT_PACKETS.items():
        got = psy.build_lighting(mode)
        assert len(got) == 1024
        assert got == P(hexhead), f"mode={mode:#x}"


def test_save_packet_matches_capture():
    assert psy.build_save() == P(SAVE_PACKET)


def test_key_poll_matches_capture():
    assert psy.build_key_poll(0x2F) == P(POLL_PACKET)


def test_key_analog_replay_matches_capture():
    got = psy.build_key_analog_raw(0x2F, psy.CAPTURED_ANALOG_PAYLOAD)
    assert got == P(ANALOG_PACKET)


def test_checksum_formula_against_all_captured_packets():
    """The stored checksum of every captured packet must equal the word-sum."""
    import struct
    for hexhead in list(LIGHT_PACKETS.values()) + [SAVE_PACKET, POLL_PACKET,
                                                   ANALOG_PACKET]:
        pkt = P(hexhead)
        stored = struct.unpack_from("<H", bytes(pkt), 2)[0]
        assert psy.checksum(pkt) == stored


def test_packet_header_and_tlv():
    pkt = psy.build_lighting(0x01)
    assert pkt[0] == psy.REPORT_ID_FF12 and pkt[1] == psy.DEFAULT_ECHO
    assert pkt[4] | (pkt[5] << 8) == 52          # TLV length = 48 + 4
    assert pkt[6] == psy.CMD_LIGHTING and pkt[7] == 0x00


def test_analog_payload_length_guard():
    try:
        psy.build_key_analog_raw(0x2F, b"\x00" * 10)
    except ValueError:
        pass
    else:
        raise AssertionError("short analog payload should be rejected")


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
