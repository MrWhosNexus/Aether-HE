"""KeyMap assigns design codes by each key's layout `code`, not by position.
Positional pairing shifted every code after Insert on the 68-key WIN 68 HE."""
import glob

import device_state as ds

WIN68 = "ui/layouts/aula-win68he-si2828heargb.json"


def _positional(path):
    keys = ds.load_keymap(path)["keys"]
    o = sorted(keys, key=lambda k: (round(float(k["y"]) / 10), float(k["x"])))
    return {int(k["index"]): c for k, c in zip(o, ds.DESIGN_CODES)}


def test_every_61_key_layout_maps_exactly_as_before():
    for f in ["ui/keymap.json"] + glob.glob("ui/layouts/*.json"):
        km = ds.KeyMap(f)
        if len(km.keys) == 61:
            assert km.code_of_index == _positional(f), f


def test_win68_keys_get_their_own_codes():
    km = ds.KeyMap(WIN68)
    expect = {"Tab": 44, "Q": 45, "W": 46, "A": 68, "S": 69, "D": 70, "Space": 116,
              "Fn": 121, "RCtrl": 122, "Ins": 38, "Del": 60, "PgUp": 82, "PgDn": 104,
              "Up": 103, "Left": 124, "Down": 125, "Right": 126, "RShift": 101}
    for code, idx in expect.items():
        assert km.index_of_code[code] == idx, code
    assert len(km.index_of_code) == 68


def test_win68_socd_and_actuation_target_the_right_hid():
    km = ds.KeyMap(WIN68)
    assert km.hid_for_code("A") == 0x04 and km.hid_for_code("D") == 0x07
    assert km.hid_for_code("W") == 0x1A and km.hid_for_code("Del") == 0x4C


def test_win68_layout_covers_every_key_seen_in_the_issue_20_capture():
    # Device indices that produced travel frames in the WIN 68 HE in-app
    # capture attached to issue #20 (65 keys; only the arrows were not pressed).
    seen = {22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 36, 38, 44, 45, 46, 47,
            48, 49, 50, 51, 52, 53, 54, 55, 56, 58, 60, 66, 68, 69, 70, 71, 72, 73, 74,
            75, 76, 77, 78, 80, 82, 88, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 101,
            103, 104, 110, 111, 112, 116, 119, 121, 122}
    km = ds.KeyMap(WIN68)
    assert seen <= set(km.indices())
    assert all(km.code_of(i) for i in seen)


def test_unknown_or_duplicate_code_falls_back_to_positional():
    assert ds.design_codes_for([{"index": 1, "code": "Nope"}]) is None
    assert ds.design_codes_for([{"index": 1, "code": "Escape"},
                                {"index": 2, "code": "Escape"}]) is None


def test_get_board_reports_the_ui_layout():
    import app_web
    api = app_web.Api.__new__(app_web.Api)
    for path, want in (("ui/keymap.json", "60"), (WIN68, "68"),
                       ("ui/layouts/aula-win68he-max.json", "68"),
                       ("ui/layouts/aula-mini60he-pro.json", "60")):
        api.km = ds.KeyMap(path)
        assert api._ui_layout() == want, path
