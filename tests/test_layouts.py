"""Tests for the layout files under ui/layouts/ (and the live ui/keymap.json).

Guards the two facts that were previously wrong and silently dangerous:
  1. aula-mini60he-pro.json must carry the REAL firmware keyValues (stride-16,
     Esc=0) extracted from the vendor SDK — not the fabricated Win60 stride-22
     numbering (Esc=22) the old scaffold shipped with. Wrong indices mean
     actuation/LED settings land on the wrong keys.
  2. The five hed.aulacn.com (Win60-family) vendor imports must stay faithful
     to the vendor's own config__keys__<PRODUCT>.json tables, all of which
     share VID 0x2E3C / PID 0xC365 and differ only by USB product string.

Run: python -m pytest tests/test_layouts.py
"""
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from validate_keymap import load_keymap, validate_keymap

LAYOUT_DIR = os.path.join(ROOT, "ui", "layouts")
VENDOR_HED = os.path.join(ROOT, "docs", "context", "hed-aulacn-raw", "driver_src")


def _layout_paths():
    return sorted(glob.glob(os.path.join(LAYOUT_DIR, "*.json")))


def _load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------ all layouts
def test_every_layout_passes_strict_validation():
    paths = _layout_paths()
    assert paths, "no layout files found"
    for p in paths:
        load_keymap(p)  # raises KeymapValidationError on any schema violation


def test_every_layout_has_meta_with_provenance():
    for p in _layout_paths():
        data = _load_json(p)
        meta = data.get("_meta")
        assert isinstance(meta, dict), "%s: missing _meta block" % p
        for field in ("board", "vid", "pid"):
            assert meta.get(field), "%s: _meta.%s missing" % (p, field)


# ------------------------------------------- MINI 60 HE PRO (regenerated)
# Ground truth: HFD-D07mGRx8.js layout array `o` + master map `y`, cross-
# confirmed by webhid-capture-2026-07-20.json (61 populated actuation slots).
MINI60_EXPECTED_SLOTS = (
    {0} | set(range(17, 29)) | {92}            # Esc, 1..=, Backspace
    | set(range(32, 45)) | {60}                # Tab, Q..], Backslash
    | {48} | set(range(49, 60)) | {76}         # Caps, A..', Enter
    | {64} | set(range(65, 76))                # LShift, Z../, RShift
    | set(range(80, 88))                       # LCtrl..RCtrl + Fn
)

MINI60_ANCHORS = {
    # keyValue -> (code, hid) — spot checks straight from the SDK master map
    0: ("Escape", 0x29),
    17: ("Digit1", 0x1E),
    28: ("Equal", 0x2E),
    92: ("Backspace", 0x2A),
    32: ("Tab", 0x2B),
    44: ("BracketRight", 0x30),
    60: ("Backslash", 0x31),
    48: ("CapsLock", 0x39),
    59: ("Quote", 0x34),
    76: ("Enter", 0x28),
    64: ("ShiftLeft", 0xE1),
    75: ("ShiftRight", 0xE5),
    80: ("ControlLeft", 0xE0),
    83: ("Space", 0x2C),
    86: ("ContextMenu", 0x65),
    87: ("ControlRight", 0xE4),
}


def _mini60():
    return _load_json(os.path.join(LAYOUT_DIR, "aula-mini60he-pro.json"))


def test_mini60_pro_has_exactly_the_61_firmware_keyvalues():
    data = _mini60()
    got = {int(k["index"]) for k in data["keys"]}
    assert got == MINI60_EXPECTED_SLOTS
    assert len(data["keys"]) == 61


def test_mini60_pro_is_not_the_old_fabricated_win60_numbering():
    data = _mini60()
    by_code = {k["code"]: int(k["index"]) for k in data["keys"]}
    # Old scaffold: Esc=22 (stride 22). Real firmware: Esc=0 (stride 16).
    assert by_code["Escape"] == 0
    assert by_code["Space"] == 83
    assert by_code["KeyFn"] == 85


def test_mini60_pro_anchor_keys_match_the_sdk_master_map():
    data = _mini60()
    by_index = {int(k["index"]): k for k in data["keys"]}
    for kv, (code, hid) in MINI60_ANCHORS.items():
        k = by_index[kv]
        assert k["code"] == code, "keyValue %d: code %r != %r" % (kv, k["code"], code)
        if code != "KeyFn":
            assert int(k["hidCode"], 16) == hid, (
                "keyValue %d: hid %s != 0x%02X" % (kv, k["hidCode"], hid))


def test_mini60_pro_meta_is_fixed():
    meta = _mini60()["_meta"]
    assert meta["pid"].upper() == "80A2"          # was the stale FEFE
    assert meta["provisionalIndices"] is False    # indices are now real
    assert meta["indicesStatus"] == "VERIFIED"
    assert "sonix" not in meta["protocolFamily"]  # falsified hypothesis removed
    assert "protocol_mini60" in meta["protocolFamily"]


def test_mini60_pro_physical_rows_match_the_sdk_layout_array():
    """Left-to-right keyValue order per physical row, verbatim from the vendor
    layout array `o` in HFD-D07mGRx8.js (HFD_SDK_DECODE.md section 13)."""
    expected_rows = [
        [0] + list(range(17, 29)) + [92],           # Esc, 1..=, Backspace
        [32] + list(range(33, 45)) + [60],          # Tab, Q..], Backslash
        [48] + list(range(49, 60)) + [76],          # Caps, A..', Enter
        [64] + list(range(65, 75)) + [75],          # LShift, Z../, RShift
        [80, 81, 82, 83, 84, 86, 87, 85],           # LCtrl..RCtrl, Fn rightmost
    ]
    data = _mini60()
    rows = {}
    for k in data["keys"]:
        rows.setdefault(round(float(k["y"])), []).append(k)
    assert len(rows) == 5
    got_rows = [
        [int(k["index"]) for k in sorted(rows[y], key=lambda k: float(k["x"]))]
        for y in sorted(rows)
    ]
    assert got_rows == expected_rows


# -------------------------------------- hed.aulacn.com Win60-family imports
HED_IMPORTS = {
    # layout file -> (vendor config, expected key count, expected type)
    "aula-win60he-si2825heargb.json": ("config__keys__SI2825HEARGB.json", 61, "us"),
    "aula-win60he-si2825kzheargb.json": ("config__keys__SI2825KZHEARGB.json", 61, "us"),
    "aula-win68he-si2828heargb.json": ("config__keys__SI2828HEARGB.json", 68, "us"),
    "aula-win68he-si2828kzheargb.json": ("config__keys__SI2828KZHEARGB.json", 68, "us"),
    "aula-kp-te153-si2851ukkzheargb.json": ("config__keys__SI2851UKKZHEARGB.json", 69, "uk"),
}


def test_hed_imports_match_vendor_configs_verbatim():
    for fname, (vendor, nkeys, typ) in HED_IMPORTS.items():
        data = _load_json(os.path.join(LAYOUT_DIR, fname))
        src = _load_json(os.path.join(VENDOR_HED, vendor))
        assert data["keys"] == src["keys"], "%s: keys diverged from %s" % (fname, vendor)
        assert data["type"] == src["type"] == typ
        assert len(data["keys"]) == nkeys


def test_hed_imports_share_the_colliding_vid_pid_and_carry_product_string():
    for fname in HED_IMPORTS:
        meta = _load_json(os.path.join(LAYOUT_DIR, fname))["_meta"]
        assert meta["vid"].upper() == "2E3C"
        assert meta["pid"].upper() == "C365"
        assert meta["productString"], "%s: productString missing" % fname
        assert meta["productString"].lower() in fname


def test_win60_import_equals_the_live_hardware_verified_keymap():
    """SI2825HEARGB is the vendor's table for the board Aether already drives;
    it must stay identical to the shipped, hardware-verified ui/keymap.json."""
    live = _load_json(os.path.join(ROOT, "ui", "keymap.json"))
    imp = _load_json(os.path.join(LAYOUT_DIR, "aula-win60he-si2825heargb.json"))
    assert imp["keys"] == live["keys"]
    assert imp["type"] == live["type"]
    assert imp["_meta"]["indicesStatus"] == "VERIFIED"


def test_win68_and_uk_imports_are_marked_provisional():
    for fname in ("aula-win68he-si2828heargb.json",
                  "aula-win68he-si2828kzheargb.json",
                  "aula-kp-te153-si2851ukkzheargb.json"):
        meta = _load_json(os.path.join(LAYOUT_DIR, fname))["_meta"]
        assert meta["indicesStatus"] == "PROVISIONAL", fname
        assert meta["provisionalIndices"] is True, fname


# ================= structural invariants every layout must hold ===========
# Added 2026-07-21 from the coverage audit. These are the layout facts other
# layers ASSUME silently: the firmware's paged tables are 132 slots wide, the
# Fn/layer key is looked up by `code == "KeyFn"`, and the design-code
# alignment in device_state.KeyMap is a positional zip against a fixed
# 61-entry list. None of them was checked anywhere.
import boards                                            # noqa: E402
import device_state                                      # noqa: E402

FIRMWARE_TABLE_SLOTS = 132     # cmd 37 switch / cmd 38 dead band / cmd 33


def test_every_layout_index_fits_the_132_slot_firmware_tables():
    """Key indices ARE offsets into the firmware's 132-entry per-key tables
    (switch profile, dead band, actuation) and into the 22-column keymask.
    An index >= 132 would be silently dropped by the table builders — the
    write would appear to succeed and change nothing."""
    for p in _layout_paths() + [os.path.join(ROOT, "ui", "keymap.json")]:
        idx = [int(k["index"]) for k in _load_json(p)["keys"]]
        assert len(set(idx)) == len(idx), "%s: duplicate key index" % p
        assert min(idx) >= 0, p
        assert max(idx) < FIRMWARE_TABLE_SLOTS, (
            "%s: index %d overflows the %d-slot firmware tables"
            % (p, max(idx), FIRMWARE_TABLE_SLOTS))


def test_every_layout_declares_exactly_one_fn_key():
    """device_state.KeyMap collects `layer_indices` from `code == "KeyFn"`,
    and the firmware keymap table must keep code1=1 on those slots or the
    function layer breaks. Zero Fn keys silently disables the guard; two
    would make the layer ambiguous."""
    for p in _layout_paths() + [os.path.join(ROOT, "ui", "keymap.json")]:
        fn = [k for k in _load_json(p)["keys"] if k.get("code") == "KeyFn"]
        assert len(fn) == 1, "%s: %d KeyFn keys" % (p, len(fn))


def test_every_layout_identity_is_claimed_by_a_registry_entry():
    """A layout's `_meta` vid/pid names the board it was imported FROM.
    Several registry entries deliberately reuse another board's layout (the
    MINI's 2.4GHz dongle, the 1CA2/38A6 siblings), so the rule is not
    "meta == entry" — it is that the identity in the file must belong to
    SOME registry entry that references it. A layout whose identity no
    entry claims is an orphan: imported for a board that is not wired up,
    and therefore never validated against the board it is used for."""
    with open(boards.REGISTRY_PATH, encoding="utf-8") as fh:
        raw = json.load(fh)

    def _hex(v):
        return (v or "").upper().replace("0X", "")

    users = {}
    for b in raw["boards"]:
        users.setdefault(os.path.normpath(b["keymap"]), []).append(b)
    for rel, entries in users.items():
        path = os.path.join(ROOT, rel)
        meta = _load_json(path).get("_meta") or {}
        if not meta.get("vid"):
            assert rel.endswith(os.path.join("ui", "keymap.json")), rel
            continue        # the live Win60 keymap carries no _meta identity
        ids = {(_hex(b["vid"]), _hex(b["pid"])) for b in entries}
        assert (_hex(meta["vid"]), _hex(meta["pid"])) in ids, (
            "%s: _meta identity %s:%s is claimed by no registry entry using it"
            % (rel, meta["vid"], meta["pid"]))


def test_design_code_alignment_is_total_only_at_exactly_61_keys():
    """device_state.KeyMap aligns device keys to the UI's design codes by
    sorting on physical position and `zip`-ing against DESIGN_CODES — a
    hardcoded 61-entry 60% ANSI list. `zip` truncates silently, so the
    alignment is total ONLY for a layout with exactly 61 keys.

    Pinned here as data, because `index_of_code` is the only bridge between
    the UI's per-key surfaces (selection, paint, actuation, SOCD) and device
    indices: for the shipped Win60 the map is total and bijective, while the
    68/69/81-key layouts have MORE keys than there are design codes. Those
    boards therefore cannot be given a correct per-key mapping by the
    positional zip alone — they need per-board design codes. When that lands,
    this test should gain the new expectation rather than be deleted."""
    assert len(device_state.DESIGN_CODES) == 61
    assert len(set(device_state.DESIGN_CODES)) == 61

    live = device_state.KeyMap(os.path.join(ROOT, "ui", "keymap.json"))
    assert len(live.keys) == 61
    assert len(live.index_of_code) == 61          # total
    assert len(live.code_of_index) == 61          # and bijective
    assert set(live.index_of_code) == set(device_state.DESIGN_CODES)
    assert live.index_of_code["Escape"] == 22     # top-left, first design code
    assert set(live.code_of_index) == set(live.by_index)

    oversized = {}
    for p in _layout_paths():
        n = len(_load_json(p)["keys"])
        if n != len(device_state.DESIGN_CODES):
            oversized[os.path.basename(p)] = n
    assert oversized == {
        "aula-f75.json": 81,
        "aula-kp-te153-si2851ukkzheargb.json": 69,
        "aula-win68he-max.json": 68,
        "aula-win68he-si2828heargb.json": 68,
        "aula-win68he-si2828kzheargb.json": 68,
    }, "layout key counts changed — re-check the DESIGN_CODES alignment"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
