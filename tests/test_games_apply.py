"""Phase 3: apply_profile_to_board, the board half of a game switch.
Actuation/RT to all keys + SOCD through the existing Api paths, skipped when
the read-back says the board already holds it, deferred while offline.
Fakes only: no HID, no keyboard."""
import pytest

from test_stats_api import FakeDriver, _api


class RecordingDriver(FakeDriver):
    def __init__(self):
        super().__init__()
        self.actuation, self.socd = [], []
        self.fail = False

    def set_actuation(self, idxs, mode, travel, rt1, rt2):
        if self.fail:
            raise RuntimeError("link lost")
        self.actuation.append((len(idxs), mode, round(travel, 2), rt1, rt2))

    def set_socd(self, plist):
        self.socd.append(list(plist))


SPEC = {"actuation": 0.8, "rtEnabled": False, "rtPress": 0.05, "rtRelease": 0.05,
        "socd": [{"model": 1, "key1": "A", "key2": "D"}]}


def _a(tmp_path):
    a = _api(tmp_path)
    a.driver = RecordingDriver()
    return a


def _all_keys(a):
    return sorted(set(a.km.index_of_code.values()))


def _read_back(a, mm=0.8, mode=0, rtp=0.05, rtr=0.05, only=None):
    names = [a.km.by_index[i]["name"] for i in (only or _all_keys(a))]
    a.driver.detail = {n: {"travel_mm": mm, "mode": mode, "rt_press_mm": rtp,
                           "rt_release_mm": rtr} for n in names}
    assert a.verify_actuation([])["ok"]


def test_first_apply_writes_all_keys_and_socd(tmp_path):
    a = _a(tmp_path)
    r = a.apply_profile_to_board(SPEC)
    assert r == {"ok": True, "deferred": False, "actuation": "written", "socd": "written"}
    assert a.driver.actuation == [(len(a.km.indices()), 0, 0.8, None, None)]
    assert len(a.driver.socd) == 1 and len(a.driver.socd[0]) == 1


def test_board_that_already_matches_is_not_written(tmp_path):
    a = _a(tmp_path)
    _read_back(a, 0.8)
    a._socd_last = a._socd_key(SPEC["socd"])
    r = a.apply_profile_to_board(SPEC)
    assert r["actuation"] == "unchanged" and r["socd"] == "unchanged"
    assert a.driver.actuation == [] and a.driver.socd == []


def test_a_repeated_apply_is_skipped(tmp_path):
    a = _a(tmp_path)
    a.apply_profile_to_board(SPEC)
    r = a.apply_profile_to_board(SPEC)
    assert r["actuation"] == "unchanged" and r["socd"] == "unchanged"
    assert len(a.driver.actuation) == 1 and len(a.driver.socd) == 1


def test_different_travel_or_partial_read_back_writes(tmp_path):
    a = _a(tmp_path)
    _read_back(a, 1.2)
    assert a.apply_profile_to_board(SPEC)["actuation"] == "written"
    b = _a(tmp_path)
    _read_back(b, 0.8, only=_all_keys(b)[:5])               # most keys unknown
    assert b.apply_profile_to_board(SPEC)["actuation"] == "written"


def test_rapid_trigger_compares_mode_and_pair(tmp_path):
    a = _a(tmp_path)
    _read_back(a, 0.8, mode=13, rtp=0.1, rtr=0.1)
    rt = dict(SPEC, rtEnabled=True, rtPress=0.1, rtRelease=0.1, socd=None)
    assert a.apply_profile_to_board(rt)["actuation"] == "unchanged"
    assert a.apply_profile_to_board(dict(rt, rtRelease=0.2))["actuation"] == "written"
    assert a.driver.actuation[-1] == (len(a.km.indices()), 13, 0.8, 0.1, 0.2)
    assert a.apply_profile_to_board(dict(rt, rtEnabled=False))["actuation"] == "written"
    assert a.driver.actuation[-1][1] == 0


def test_socd_order_or_content_change_is_written(tmp_path):
    a = _a(tmp_path)
    a.apply_profile_to_board(SPEC)
    two = [{"model": 1, "key1": "A", "key2": "D"}, {"model": 1, "key1": "W", "key2": "S"}]
    assert a.apply_profile_to_board(dict(SPEC, socd=two))["socd"] == "written"
    assert a.apply_profile_to_board(dict(SPEC, socd=two[::-1]))["socd"] == "written"
    assert a.apply_profile_to_board(dict(SPEC, socd=[]))["socd"] == "written"   # [] clears


def test_a_manual_socd_write_is_remembered(tmp_path):
    a = _a(tmp_path)
    assert a.set_socd(SPEC["socd"])["ok"]
    assert a.apply_profile_to_board(dict(SPEC, actuation=None))["socd"] == "unchanged"


def test_null_fields_are_left_alone(tmp_path):
    a = _a(tmp_path)
    r = a.apply_profile_to_board({})
    assert r == {"ok": True, "deferred": False, "actuation": "skipped", "socd": "skipped"}
    assert a.driver.actuation == [] and a.driver.socd == []


def test_actuation_is_clamped_to_the_board_range(tmp_path):
    a = _a(tmp_path)
    a.apply_profile_to_board(dict(SPEC, actuation=0.01, socd=None))
    lo = a.board.actuation["travelRange"][0]
    assert a.driver.actuation[-1][2] == pytest.approx(lo)


@pytest.mark.parametrize("bad", ["x", None, {"actuation": "abc"}, {"actuation": -1},
                                 {"actuation": float("nan")}, {"socd": "x"},
                                 {"socd": [{"key1": "A"}]}, {"socd": [{"key1": "A", "key2": "D",
                                                                       "model": 999}]}])
def test_invalid_specs_fail_cleanly(tmp_path, bad):
    a = _a(tmp_path)
    r = a.apply_profile_to_board(bad)
    assert r["ok"] is False and r["error"]
    assert a.driver.actuation == [] and a.driver.socd == []


def test_failed_write_names_the_step_and_is_not_remembered(tmp_path):
    a = _a(tmp_path)
    a.driver.fail = True
    r = a.apply_profile_to_board(SPEC)
    assert r["ok"] is False and r["step"] == "actuation" and "link lost" in r["error"]
    a.driver.fail = False
    assert a.apply_profile_to_board(SPEC)["actuation"] == "written"


def test_offline_apply_is_deferred_and_the_newest_wins(tmp_path):
    a = _a(tmp_path)
    a.dev.open = False
    assert a.apply_profile_to_board(dict(SPEC, actuation=1.0)) == {"ok": True, "deferred": True}
    assert a.apply_profile_to_board(SPEC) == {"ok": True, "deferred": True}
    assert a.driver.actuation == []
    a.dev.open = True
    assert a._connect(resume=False)["ok"] is True
    assert a.driver.actuation == [(len(a.km.indices()), 0, 0.8, None, None)]
    assert a._pending_board is None
    a._connect(resume=False)
    assert len(a.driver.actuation) == 1                     # applied once


def test_reconnect_forgets_what_the_board_holds(tmp_path):
    a = _a(tmp_path)
    a.apply_profile_to_board(SPEC)
    a._connect(resume=False)
    r = a.apply_profile_to_board(SPEC)
    assert r["actuation"] == "written" and r["socd"] == "written"


def test_selecting_another_board_drops_board_state(tmp_path):
    a = _a(tmp_path)
    a.apply_profile_to_board(SPEC)
    a.dev.open = False
    a.apply_profile_to_board(SPEC)
    a._registry = None
    a._remaps, a._deadband_state, a._fn_layer_raw = {}, {}, None
    assert a.select_board("aula-mini60he-pro")["ok"] is True
    assert a._trig_mode == {} and a._socd_last is None and a._pending_board is None
