"""WIN60 HE advanced keys (DKS / MT / TGL): golden frames for the WIP builders.

SOURCE-ONLY. Every non-empty golden frame below is decoded from the vendor
driver source (docs/context/hed-aulacn-raw/driver_deobf/agreement.deobf.js
setAdvancedKeys L536-550, read handler L204-231; wmIndex.deobf.js editor
L393-461, L1122-1189) and is UNVERIFIED ON HARDWARE. Only the read request
and the all-empty write pass are pinned against the live capture
(webhid-capture-win60.json). The checklist that will confirm the rest is
docs/context/aula-win60-advanced-keys-capture-checklist.md.

Run: python -m pytest -q -p no:cacheprovider tests/test_win60_advkeys_wip.py
"""
import ast
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import protocol_win60_advkeys_wip as adv     # noqa: E402

CAPTURE = (Path(ROOT) / "docs" / "context" / "hed-aulacn-raw"
           / "webhid-capture-win60.json")


def _hex(body):
    return " ".join(f"{b:02x}" for b in body)


def _golden(prefix_hex):
    """A 63-byte body: the given leading bytes, zero-padded."""
    head = [int(x, 16) for x in prefix_hex.split()]
    return head + [0] * (adv.BODY - len(head))


# ---------------------------------------------------------------- framing


def test_read_request_matches_capture():
    """SOURCE-ONLY builder, framing CONFIRMED-BY-CAPTURE (frame 74):
    OUT 22 80 00..."""
    assert adv.build_read_advanced_keys() == _golden("22 80")
    if CAPTURE.exists():
        frames = json.loads(CAPTURE.read_text(encoding="utf-8"))["frames"]
        assert frames[74]["dir"] == "OUT"
        assert frames[74]["hex"] == _hex(adv.build_read_advanced_keys())


def test_empty_table_pass_matches_capture():
    """SOURCE-ONLY builder, framing CONFIRMED-BY-CAPTURE (frames 2205-2282):
    the vendor rewrites all 40 slots, [1]=slot, [4]=0x32, empty = all zero."""
    table = adv.build_advanced_key_table()
    assert len(table) == 40
    assert table[0] == _golden("22 00 00 00 32")
    assert table[39] == _golden("22 27 00 00 32")
    if not CAPTURE.exists():
        pytest.skip("capture file not present")
    frames = json.loads(CAPTURE.read_text(encoding="utf-8"))["frames"]
    outs = [f["hex"] for f in frames
            if f.get("dir") == "OUT" and f.get("hex", "").startswith("22 ")
            and not f["hex"].startswith("22 80")]
    first_pass = outs[:40]
    assert first_pass == [_hex(b) for b in table]


def test_report_id_prefix():
    """SOURCE-ONLY: 64-byte report = report id 1 + 63-byte body."""
    rep = adv.to_report(adv.build_empty_slot(5))
    assert len(rep) == 64 and rep[:6] == [1, 0x22, 5, 0, 0, 0x32]


# ---------------------------------------------------------------- DKS


def test_dks_golden_frame():
    """SOURCE-ONLY, unverified on hardware. Slot 0, vendor default routes
    1.5 / 3.0 / 3.0 / 1.5 mm (0x0F 0x1E 0x1E 0x0F), action 1 = A (HID 0x04)
    tapped at the press point and at the release point (steps 1 0 0 1).
    This is checklist step D1's expected frame."""
    body = adv.build_dks_slot(
        0, routes=[0x0F, 0x1E, 0x1E, 0x0F], actions=[0x04],
        steps=[[1, 0, 0, 1]])
    assert body == _golden(
        "22 00 00 00 32 01 0f 1e 1e 0f"
        " 00 04 00 00 01 00 00 01")


def test_dks_hold_bar_golden_frame():
    """SOURCE-ONLY, unverified on hardware. Checklist step D2: a row-1 bar
    from point 1 to point 2 writes 2 at point 1 and 0 at point 2 (the bar
    ends at the next point's left edge, wmIndex setDksBtnWidth L384-392 /
    setDksValue L397), plus the point-4 circle."""
    body = adv.build_dks_slot(
        0, routes=[0x0F, 0x1E, 0x1E, 0x0F], actions=[0x04],
        steps=[[2, 0, 0, 1]])
    assert body == _golden(
        "22 00 00 00 32 01 0f 1e 1e 0f"
        " 00 04 00 00 02 00 00 01")


def test_dks_four_actions_layout():
    """SOURCE-ONLY: action k lives at body[10+8k .. 17+8k] =
    [code1, hid, code3, code4, step p1..p4] (agreement L546)."""
    body = adv.build_dks_slot(
        3, routes=[10, 34, 34, 10],
        actions=[0x04, 0x05, (0, 0xE0, 0, 0), 0x07],
        steps=[[1, 0, 0, 0], [2, 2, 0, 0], [0, 3, 0, 1], [0, 0, 0, 1]])
    assert body == _golden(
        "22 03 00 00 32 01 0a 22 22 0a"
        " 00 04 00 00 01 00 00 00"
        " 00 05 00 00 02 02 00 00"
        " 00 e0 00 00 00 03 00 01"
        " 00 07 00 00 00 00 00 01")
    assert len(body) == 63 and all(b == 0 for b in body[42:])


def test_dks_mm_helper_uses_tenth_mm():
    """SOURCE-ONLY: DKS points are 0.1 mm (wmIndex L1160/L1164 value/10)."""
    assert adv.dks_mm_to_raw(1.5) == 0x0F
    assert adv.dks_mm_to_raw(3.0) == 0x1E
    with pytest.raises(ValueError):
        adv.dks_mm_to_raw(0)


def test_dks_rejects_bad_input():
    """SOURCE-ONLY guards: four routes, step codes 0..3, slot 0..39."""
    with pytest.raises(ValueError):
        adv.build_dks_slot(0, routes=[1, 2, 3], actions=[], steps=[])
    with pytest.raises(ValueError):
        adv.build_dks_slot(0, routes=[15, 30, 30, 15], actions=[4],
                           steps=[[4, 0, 0, 0]])
    with pytest.raises(ValueError):
        adv.build_dks_slot(40, routes=[15, 30, 30, 15], actions=[], steps=[])


# ---------------------------------------------------------------- MT / TGL


def test_mt_golden_frame_hold_before_tap():
    """SOURCE-ONLY, unverified on hardware. Slot 1, tap = Esc (0x29),
    hold = L-Ctrl (0xE0), 150 ms (raw 0x0F). HOLD record comes FIRST on the
    wire (agreement L547 writes keys[1] at body[6..9]). Checklist step M1."""
    body = adv.build_mt_slot(1, tap=0x29, hold=0xE0,
                             duration_raw=adv.mt_duration_from_ms(150))
    assert body == _golden(
        "22 01 00 00 32 02"
        " 00 e0 00 00"
        " 00 29 00 00"
        " 0f")


def test_mt_duration_unit_is_10ms():
    """SOURCE-ONLY: labMtTime = 10 * value ms (wmIndex L1134)."""
    assert adv.mt_duration_from_ms(150) == 15
    assert adv.mt_duration_from_ms(1000) == 100


def test_tgl_golden_frame():
    """SOURCE-ONLY, unverified on hardware. Slot 2, toggled key =
    L-Shift (0xE1) at body[6..9]. Checklist step T1."""
    assert adv.build_tgl_slot(2, 0xE1) == _golden(
        "22 02 00 00 32 03 00 e1 00 00")


# ---------------------------------------------------------------- table / keymap


def test_table_places_entries_and_clears_the_rest():
    """SOURCE-ONLY: a delete is the full 40-slot pass with that slot empty."""
    dks = adv.build_dks_slot(0, [15, 30, 30, 15], [0x04], [[1, 0, 0, 1]])
    tgl = adv.build_tgl_slot(2, 0xE1)
    table = adv.build_advanced_key_table({0: dks, 2: tgl})
    assert table[0] == dks and table[2] == tgl
    assert table[1] == adv.build_empty_slot(1)
    with pytest.raises(ValueError):
        adv.build_advanced_key_table({1: dks})       # slot mismatch


def test_keymap_binding_entry():
    """SOURCE-ONLY: binding = keymap entry [0x17, slot, slot, 0]
    (wmIndex L456, agreement L342 / L123)."""
    assert adv.keymap_entry_advanced(0) == [0x17, 0, 0, 0]
    assert adv.keymap_entry_advanced(1) == [0x17, 1, 1, 0]
    with pytest.raises(ValueError):
        adv.keymap_entry_advanced(40)


# ---------------------------------------------------------------- read parse


def _reply_from_write(body):
    """Read replies use the write's payload offsets with a different header:
    [0x22, 0x80, slotHi, slotLo, 0x28, ...] (agreement L204-229)."""
    r = list(body)
    slot = r[1]
    r[1], r[2], r[3], r[4] = 0x80, 0, slot, 0x28
    return r


def test_parse_reply_roundtrips_each_type():
    """SOURCE-ONLY: the reader parses the same offsets the writer fills."""
    d = adv.parse_advanced_key_reply(_reply_from_write(
        adv.build_dks_slot(0, [15, 30, 30, 15], [0x04], [[1, 0, 0, 1]])))
    assert d["type"] == adv.TYPE_DKS and d["routes"] == [15, 30, 30, 15]
    assert d["actions"][0] == [0, 4, 0, 0] and d["steps"][0] == [1, 0, 0, 1]
    m = adv.parse_advanced_key_reply(_reply_from_write(
        adv.build_mt_slot(1, tap=0x29, hold=0xE0, duration_raw=15)))
    assert m["tap"] == [0, 0x29, 0, 0] and m["hold"] == [0, 0xE0, 0, 0]
    assert m["duration"] == 15 and m["slot"] == 1
    t = adv.parse_advanced_key_reply(_reply_from_write(
        adv.build_tgl_slot(39, 0xE1)))
    assert t["key"] == [0, 0xE1, 0, 0] and t["last"] is True


def test_parse_captured_empty_reply():
    """CONFIRMED-BY-CAPTURE shape (frame 75): IN 22 80 00 00 28 00 ..."""
    d = adv.parse_advanced_key_reply(_golden("22 80 00 00 28"))
    assert d == {"slot": 0, "type": 0, "last": False}
    assert adv.parse_advanced_key_reply(_golden("18 80")) is None


# ---------------------------------------------------------------- isolation


def test_module_is_pure_and_not_on_drive_path():
    """The WIP module imports nothing, and no drive-path module imports it."""
    src = Path(ROOT, "protocol_win60_advkeys_wip.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    assert not [n for n in ast.walk(tree)
                if isinstance(n, (ast.Import, ast.ImportFrom))]
    drive = [Path(ROOT, n) for n in ("app_web.py", "protocol.py",
                                     "device_state.py", "effects.py", "tray.py")]
    drive += list(Path(ROOT, "drivers").glob("*.py"))
    for p in drive:
        if p.exists():
            assert "protocol_win60_advkeys_wip" not in p.read_text(
                encoding="utf-8", errors="replace"), p
