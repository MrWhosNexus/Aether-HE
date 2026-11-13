"""AULA F75 HE (38A6:2729 wired, 0C45:FEFE "AULA F75 HE Dongle").

The board is driven by the existing protocol_mini60 / Mini60Driver. Its
evidence is CONTRIBUTOR read-backs (xpLayA fork @ 9a70ec6, firmware V1.55),
committed under tests/fixtures/f75/ - not a vendor capture, and no
maintainer owns the board. These tests replay those read-backs through
fakes; nothing here opens a device.

What is pinned:
  * the 80-key layout, key by key, against the board's own 0x12 key table;
  * registry identity, frame sizes and the shared-dongle-PID discrimination;
  * the stored state decodes (lighting mode 11 / brightness 5 / speed 3,
    all-zero actuation table);
  * the writes nobody ran on an F75 (dead zone, macros) are refused with
    zero frames on the wire unless the `f75` experimental flag is on;
  * battery is read over the dongle only.
"""
import json
import os
import threading

import pytest

import boards
import protocol_mini60 as pm
from drivers import UnsupportedFeature, Mini60Driver, get_driver, connected_profiles
from drivers import mini60 as mini60_mod

from test_drivers import StubDevice, FakeMiniBoard

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures", "f75")
WIRED, DONGLE = "aula-f75-he", "aula-f75-he-24g"
F_ROW = set(range(1, 13))          # F1-F12: base records empty on the board
FN_SLOT = 85


def _fix(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return json.load(f)


def _layout():
    with open(os.path.join(ROOT, "ui", "layouts", "aula-f75he.json"),
              encoding="utf-8") as f:
        return json.load(f)


def _profile(slug):
    return boards.load_registry().by_slug(slug)


class FakeF75(FakeMiniBoard):
    """FakeMiniBoard loaded with the contributor's read-backs, answering
    0x10 with the F75's real reply bytes."""

    def __init__(self, frame_len=pm.FRAME_LEN):
        super().__init__(frame_len=frame_len)
        b = _fix("backup.json")
        self.act_table[:] = bytes.fromhex(b["act_table"])
        self.key_table[:] = bytes.fromhex(b["key_table"])
        self.led_table[:] = bytes.fromhex(b["led_table"])
        self.config[:] = bytes.fromhex(b["config_table"])
        self.light = list(b["light_raw"])[:frame_len]
        self.info0 = list(bytes.fromhex(_fix("dongle_info.json")["reply"]))

    def reply(self, report):
        frame = report[1:]
        if frame and frame[0] == pm.MAGIC and frame[1] == pm.CMD_DEVICE_INFO \
                and (frame[3] | (frame[4] << 8)) == 0:
            r = [0] * self.frame_len
            n = min(len(self.info0), self.frame_len)
            r[:n] = self.info0[:n]
            r[2], r[6] = frame[2], frame[6]
            return [r]
        return super().reply(report)


def _drv(slug, flag=False):
    p = _profile(slug)
    board = FakeF75(frame_len=mini60_mod.frame_len_for_profile(p))
    dev = StubDevice(reply_fn=board.reply)
    d = get_driver(p, dev, threading.RLock())
    d.experimental_f75 = flag          # instance attribute: no global leak
    return d, dev, board


def _writes(dev):
    return [w[1:] for w in dev.writes if len(w) > 1 and w[1] == pm.MAGIC]


# ------------------------------------------------------------ layout ----
def test_layout_is_80_unique_keys_on_the_stride_16_matrix():
    keys = _layout()["keys"]
    idx = [int(k["index"]) for k in keys]
    assert len(keys) == 80 and len(set(idx)) == 80
    assert max(idx) < pm.KEY_WRITABLE_RECORDS
    by_name = {k["name"]: int(k["index"]) for k in keys}
    # the anchors the review named, straight from the vendor layout
    assert by_name["Esc"] == 0 and [by_name[f"F{n}"] for n in range(1, 13)] == list(range(1, 13))
    assert (by_name["Back"], by_name["Enter"], by_name["\\|"]) == (92, 76, 60)
    assert (by_name["Del"], by_name["PgUp"], by_name["PgDn"], by_name["End"]) == (106, 105, 108, 107)
    assert (by_name["Lt"], by_name["Dn"], by_name["Up"], by_name["Rt"]) == (88, 89, 90, 91)
    assert by_name["Fn"] == FN_SLOT


def test_layout_matches_the_boards_own_key_table_key_by_key():
    """Every layout key outside F1-F12 and Fn must sit on the slot where the
    board's 0x12 table holds that key's HID usage as a plain record
    [02 00 usage 00]. A wrong index would light, remap or set the actuation
    of a different key than the one drawn."""
    table = bytes.fromhex(_fix("backup.json")["key_table"])
    assert len(table) == pm.KEY_TABLE_SIZE
    checked = 0
    for k in _layout()["keys"]:
        i = int(k["index"])
        rec = table[i * 4:i * 4 + 4]
        if i in F_ROW:
            assert rec == b"\x00\x00\x00\x00", f"{k['name']}: F-row record not empty"
            continue
        if i == FN_SLOT:
            # firmware holds usage 0xAF; the layout keeps Aether's 0xfa
            assert rec == bytes([2, 0, 0xAF, 0]) and k["code"] == "KeyFn"
            continue
        assert rec == bytes([2, 0, int(k["hidCode"], 16), 0]), (
            f"{k['name']} (index {i}): layout hidCode {k['hidCode']} but the "
            f"board's key table holds {rec.hex()}")
        checked += 1
    assert checked == 67


def test_no_two_layout_keys_share_a_usage_and_no_drawn_slot_is_foreign():
    """The other direction: each HID usage in the layout is unique, and it is
    stored at exactly ONE of the layout's slots - so no key is drawn on a
    slot that belongs to another key."""
    table = bytes.fromhex(_fix("backup.json")["key_table"])
    keys = [k for k in _layout()["keys"]
            if int(k["index"]) not in F_ROW and int(k["index"]) != FN_SLOT]
    usages = [int(k["hidCode"], 16) for k in keys]
    assert len(set(usages)) == len(usages)
    slot_of = {}
    for i in range(pm.KEY_TABLE_SIZE // 4):
        rec = table[i * 4:i * 4 + 4]
        if rec[0] == 2 and rec[2]:
            slot_of.setdefault(rec[2], []).append(i)
    for k in keys:
        assert slot_of[int(k["hidCode"], 16)] == [int(k["index"])], k["name"]
    # 30 populated slots lie outside the layout (shared full-size defaults)
    drawn = {int(k["index"]) for k in _layout()["keys"]}
    extra = [i for i in range(pm.KEY_TABLE_SIZE // 4)
             if any(table[i * 4:i * 4 + 4]) and i not in drawn]
    assert len(extra) == 30


def test_layout_rows_are_drawn_left_to_right_without_overlap():
    rows = {}
    for k in _layout()["keys"]:
        rows.setdefault(int(k["y"]), []).append((int(k["x"]), int(k["width"]), k["name"]))
    assert [len(rows[y]) for y in sorted(rows)] == [13, 15, 15, 14, 14, 9]
    for y, row in rows.items():
        row.sort()
        for (x0, w0, n0), (x1, _, n1) in zip(row, row[1:]):
            assert x0 + w0 <= x1, f"row y={y}: {n0} overlaps {n1}"


def test_keytable_before_fixture_equals_the_backup():
    assert _fix("keytable_before.json")["key_table"] == _fix("backup.json")["key_table"]


# ---------------------------------------------------------- registry ----
def test_both_entries_use_the_he_layout_and_the_mini_protocol():
    for slug, fl, up in ((WIRED, 64, 0xFF68), (DONGLE, 32, 0xFF60)):
        p = _profile(slug)
        assert p.protocol == "protocol_mini60" and p.drivable and p.offered
        assert p.usage_page == up
        assert os.path.basename(p.keymap) == "aula-f75he.json"
        assert mini60_mod.frame_len_for_profile(p) == fl
        assert p.status == "bringup"                 # no maintainer hardware
        for cap in ("lighting", "actuation", "perKeyRgb", "rapidTrigger",
                    "remap", "advancedKeys", "socd"):
            assert p.cap(cap) is True, (slug, cap)
        for cap in ("deadzone", "macros", "calibration"):
            assert p.cap(cap) == "wip", (slug, cap)
        assert p.cap("gamepad") is False
    assert (_profile(WIRED).vid, _profile(WIRED).pid) == (0x38A6, 0x2729)
    assert _profile(WIRED).lighting["hostEngine"] is True
    assert _profile(DONGLE).lighting["hostEngine"] is False


def test_entries_say_community_tested_not_verified():
    with open(boards.REGISTRY_PATH, encoding="utf-8") as f:
        raw = {b["slug"]: b for b in json.load(f)["boards"]}
    for slug in (WIRED, DONGLE):
        blob = json.dumps(raw[slug])
        assert "COMMUNITY-TESTED (xpLayA read-backs)" in raw[slug]["_note"]
        assert "not maintainer-verified" in raw[slug]["_note"]
        assert "HARDWARE-VERIFIED" not in blob
        assert "UNVERIFIED" in raw[slug]["lighting"]["_note"]   # mode names
    assert "COMMUNITY-TESTED (nieruuu19)" in raw["aula-win68he-max"]["_offerNote"]


def test_tri_mode_is_a_different_board_and_keeps_its_own_layout():
    tri = _profile("aula-f75-tri-mode")
    assert (tri.vid, tri.pid) == (0x258A, 0x010C)
    assert os.path.basename(tri.keymap) == "aula-f75.json"
    assert not tri.drivable and not tri.offered


def test_shared_dongle_pid_is_split_by_product_string():
    reg = boards.load_registry()
    assert reg.by_ids(0x0C45, 0xFEFE, "AULA F75 HE Dongle").slug == DONGLE
    assert reg.by_ids(0x0C45, 0xFEFE, "aula f75 he dongle ").slug == DONGLE
    assert reg.by_ids(0x0C45, 0xFEFE, "MINI 60 HE PRO Dongle").slug == "aula-mini60he-pro-24g"
    # unknown / missing string: unchanged fallback to the MINI's dongle
    assert reg.by_ids(0x0C45, 0xFEFE).slug == "aula-mini60he-pro-24g"
    assert reg.by_ids(0x0C45, 0xFEFE, "something else").slug == "aula-mini60he-pro-24g"


def test_wired_f75_outranks_its_dongle_when_both_are_attached():
    reg = boards.load_registry()
    devs = [{"vendor_id": 0x0C45, "product_id": 0xFEFE, "product_string": "AULA F75 HE Dongle"},
            {"vendor_id": 0x38A6, "product_id": 0x2729, "product_string": "AULA F75 HE"}]
    assert [p.slug for p in connected_profiles(reg, lambda: devs)] == [WIRED, DONGLE]


# ------------------------------------------------------------ driver ----
def test_driver_is_the_mini60_driver_at_the_right_frame_size():
    for slug, fl in ((WIRED, 64), (DONGLE, 32)):
        d, _, _ = _drv(slug)
        assert type(d) is Mini60Driver and d.frame_len == fl


def test_stored_state_decodes_from_the_contributor_backup():
    for slug in (WIRED, DONGLE):
        d, dev, _ = _drv(slug)
        assert d.device_info() == {"vid": 0x38A6, "pid": 0x2729, "vidPid": "38A6:2729"}
        assert d.get_lighting() == {"mode": 11, "rgb": [255, 255, 255],
                                    "brightness": 5, "speed": 3}
        # all-zero 0x17 table = factory state: a valid read, no records
        assert d.get_actuation() == {}
        assert all(len(f) == d.frame_len for f in _writes(dev))


def test_backup_lighting_block_matches_the_raw_frame():
    b = _fix("backup.json")
    assert b["light_raw"] == _fix("light_before.json")
    assert b["device_info"]["vidPid"] == "38A6:2729"
    assert set(bytes.fromhex(b["act_table"])) == {0}
    assert len(bytes.fromhex(b["act_table"])) == pm.ACT_TABLE_SIZE
    assert set(bytes.fromhex(_fix("act_before.json"))) == {0}
    assert set(bytes.fromhex(_fix("dks_before.json")["dks_table"])) == {0}


def test_actuation_write_touches_only_the_chosen_key():
    """The contributor's round trip, replayed: 1.50 mm on W (index 34)."""
    d, _, board = _drv(WIRED)
    d.set_actuation([34], 0, 1.5)
    got = d.get_actuation()
    assert list(got) == [34] and got[34]["travel_mm"] == pytest.approx(1.5)
    assert not got[34]["rt"]


def test_dongle_refuses_host_streaming_and_wired_allows_it():
    d, dev, _ = _drv(DONGLE)
    before = len(dev.writes)
    with pytest.raises(UnsupportedFeature):
        d.begin_host_stream()
    with pytest.raises(UnsupportedFeature):
        d.stream_frame({0: (255, 0, 0)})
    assert len(dev.writes) == before
    w, wdev, _ = _drv(WIRED)
    w.begin_host_stream()
    w.stream_frame({0: (255, 0, 0)})
    assert any(f[1] == mini60_mod.CMD_STREAM_LED for f in _writes(wdev))


def test_live_travel_is_not_offered():
    for slug in (WIRED, DONGLE):
        assert not _drv(slug)[0].supports("travel_stream")


# ----------------------------------------------- experimental gating ----
@pytest.mark.parametrize("slug", [WIRED, DONGLE])
def test_unrun_writes_are_refused_with_nothing_on_the_wire(slug):
    d, dev, _ = _drv(slug, flag=False)
    assert not d.supports("deadband") and not d.supports("macros")
    for feat in ("lighting", "actuation", "per_key_rgb", "key_remap",
                 "advanced_keys", "socd"):
        assert d.supports(feat), feat
    calls = [lambda: d.set_deadband({}, top_mm=0.2),
             lambda: d.write_macro(0, [(10, 4, True), (10, 4, False)]),
             lambda: d.bind_macro(34, 0),
             lambda: d.list_macros(),
             lambda: d.read_macro(0)]
    for call in calls:
        with pytest.raises(UnsupportedFeature):
            call()
    assert dev.writes == []


@pytest.mark.parametrize("slug", [WIRED, DONGLE])
def test_flag_turns_the_unrun_writes_on(slug):
    d, dev, board = _drv(slug, flag=True)
    assert d.supports("deadband") and d.supports("macros")
    d.set_deadband({}, top_mm=0.2)
    assert any(f[1] == 0x21 for f in _writes(dev))
    d.write_macro(0, [(10, 4, True), (10, 4, False)])
    assert any(f[1] == 0x25 for f in _writes(dev))


def test_flag_is_off_by_default_and_never_gates_the_mini():
    assert Mini60Driver.experimental_f75 is False
    assert set(Mini60Driver.UNVERIFIED_FEATURES_BY_SLUG) == {WIRED, DONGLE}
    for slug in ("aula-mini60he-pro", "aula-mini60he-pro-24g"):
        p = _profile(slug)
        d = get_driver(p, StubDevice(), threading.RLock())
        assert d.supports("macros") and d.supports("deadband")


# ----------------------------------------------------------- battery ----
def test_battery_is_read_over_the_dongle_only():
    d, dev, _ = _drv(DONGLE)
    assert d.device_status() == {"battery": 100, "charging": False,
                                 "workMode": 2, "wireless": True,
                                 "firmware": "1.55"}
    w, wdev, _ = _drv(WIRED)
    assert w.device_status() is None
    assert wdev.writes == []            # wired: not even asked


def test_mini_wired_profile_reports_no_battery():
    p = _profile("aula-mini60he-pro")
    dev = StubDevice(reply_fn=FakeMiniBoard().reply)
    assert get_driver(p, dev, threading.RLock()).device_status() is None
