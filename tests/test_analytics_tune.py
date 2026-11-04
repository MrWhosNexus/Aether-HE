"""Phase 4 actuation auto-tune: suggestions only, from presses recorded at
each key's current actuation. Pure functions; no disk, no HID, no clock."""
import pytest

import analytics
from test_analytics_views import _agg, IDX


# -------------------------------------------------------------- evaluate ----
def test_too_few_presses_suggest_nothing():
    assert analytics.evaluate(_agg(presses=199, shallow=100), 80, True) is None


def test_shallow_attempts_suggest_p10_minus_0_1_rounded_down():
    # 30 of 300 attempts peak in 0.50-0.60 -> p10 = 0.60 -> 0.50 mm
    v = analytics.evaluate(_agg(presses=270, shallow=30), 80, False)
    assert v["kind"] == "shallower" and v["target_raw"] == 50
    assert v["p10_mm"] == pytest.approx(0.60)
    assert v["shallow_pct"] == 10.0 and v["presses"] == 270


def test_exactly_5_percent_shallow_is_not_enough():
    assert analytics.evaluate(_agg(presses=380, shallow=20), 80, False) is None


def test_shallower_is_at_least_one_step_below_the_current_point():
    # p10 lands deep (0.9 mm bin), so p10 - 0.1 >= current: one 0.05 step.
    v = analytics.evaluate(_agg(presses=280, shallow=20,
                                hist={7: 20, 9: 280}), 80, False)
    assert v["kind"] == "shallower" and v["target_raw"] == 75


def test_shallower_never_goes_below_0_30():
    v = analytics.evaluate(_agg(presses=250, shallow=50, shallow_bin=2), 80, False)
    assert v["kind"] == "shallower" and v["target_raw"] == 30


def test_at_the_floor_there_is_nothing_shallower():
    v = analytics.evaluate(_agg(presses=250, shallow=50, shallow_bin=2), 30, False)
    assert v["kind"] == "floor"
    v = analytics.evaluate(_agg(presses=250, shallow=50, shallow_bin=2), 25, False)
    assert v["kind"] == "floor"


def test_barely_over_suggests_deeper_on_letters_only():
    a = _agg(presses=300, barely=60)                  # 20 %
    assert analytics.evaluate(a, 80, False) is None
    v = analytics.evaluate(a, 80, True)
    assert v["kind"] == "deeper" and v["target_raw"] == 90


def test_lots_of_barely_over_suggests_0_2_deeper():
    v = analytics.evaluate(_agg(presses=300, barely=90), 80, True)   # 30 %
    assert v["kind"] == "deeper" and v["target_raw"] == 100


def test_exactly_15_percent_barely_is_not_enough():
    assert analytics.evaluate(_agg(presses=300, barely=45), 80, True) is None


def test_deeper_is_clamped_to_3_40():
    v = analytics.evaluate(_agg(presses=300, barely=90), 335, True)
    assert v["kind"] == "deeper" and v["target_raw"] == 340
    assert analytics.evaluate(_agg(presses=300, barely=90), 340, True) is None


def test_shallow_and_barely_together_is_mixed():
    v = analytics.evaluate(_agg(presses=300, shallow=30, barely=60), 80, True)
    assert v["kind"] == "mixed"


def test_unrated_presses_do_not_count_toward_the_minimum():
    assert analytics.evaluate(_agg(presses=300, shallow=30, unrated=150), 80, False) is None


# --------------------------------------------------------------- suggest ----
ALL = list(IDX.values())


def _ready(act=80, mode=(0, 0.3, 0.3)):
    return {i: act for i in ALL}, {i: mode for i in ALL}


def _spread(codes, **kw):
    """Spread one aggregate's counts evenly over `codes` (integer parts)."""
    n = len(codes)
    out = {}
    for c in codes:
        out[IDX[c]] = _agg(**{k: v // n for k, v in kw.items()})
    return out


def test_group_suggestion_from_summed_counts_covers_its_members():
    letters = analytics.GROUPS[1][2]
    rated = _spread(letters, presses=22 * 12, shallow=22 * 2)   # 12 each: < 200
    act, trig = _ready()
    out = analytics.suggest(rated, act, trig, IDX)
    [s] = out["suggestions"]
    assert s["id"] == "group:letters" and s["scope"] == "group"
    assert s["group"] == "letters" and s["direction"] == "shallower"
    assert sorted(s["codes"]) == sorted(letters)
    assert s["current_mm"] == 0.80 and s["suggested_mm"] == 0.45   # p10 0.57
    assert s["mode"] == 0 and s["rt_press_mm"] is None and s["rt_release_mm"] is None
    assert s["presses"] == 264 and s["shallow"] == 44
    assert "did not type" in s["detail"] and "0.80 → 0.45" in s["title"]


def test_per_key_suggestion_when_the_group_is_fine():
    letters = analytics.GROUPS[1][2]
    rated = _spread(letters, presses=22 * 300)
    rated[IDX["Q"]] = _agg(presses=300, barely=60)
    act, trig = _ready()
    out = analytics.suggest(rated, act, trig, IDX)
    [s] = out["suggestions"]
    assert s["id"] == "key:Q" and s["scope"] == "key" and s["group"] is None
    assert s["codes"] == ["Q"] and s["direction"] == "deeper"
    assert s["suggested_mm"] == 0.90


def test_no_key_gets_two_suggestions():
    letters = analytics.GROUPS[1][2]
    rated = _spread(letters, presses=22 * 300, shallow=22 * 30)
    rated[IDX["Q"]] = _agg(presses=300, barely=200)       # alone: deeper
    act, trig = _ready()
    out = analytics.suggest(rated, act, trig, IDX)
    codes = [c for s in out["suggestions"] for c in s["codes"]]
    assert len(codes) == len(set(codes))
    assert [s["id"] for s in out["suggestions"]] == ["group:letters"]


def test_wasd_never_gets_a_deeper_suggestion():
    rated = _spread(analytics.WASD, presses=4 * 300, barely=4 * 150)
    act, trig = _ready()
    assert analytics.suggest(rated, act, trig, IDX)["suggestions"] == []


def test_mixed_group_actuation_falls_back_to_per_key():
    letters = analytics.GROUPS[1][2]
    rated = _spread(letters, presses=22 * 12, shallow=22 * 2)
    rated[IDX["E"]] = _agg(presses=300, shallow=30)
    act, trig = _ready()
    act[IDX["Q"]] = 120                                    # group not uniform
    out = analytics.suggest(rated, act, trig, IDX)
    assert [s["id"] for s in out["suggestions"]] == ["key:E"]


def test_different_trigger_modes_split_the_group():
    letters = analytics.GROUPS[1][2]
    rated = _spread(letters, presses=22 * 12, shallow=22 * 2)
    act, trig = _ready()
    trig[IDX["Q"]] = (13, 0.3, 0.3)
    assert analytics.suggest(rated, act, trig, IDX)["suggestions"] == []


def test_fixed_mode_ignores_the_stored_rt_pair_when_grouping():
    letters = analytics.GROUPS[1][2]
    rated = _spread(letters, presses=22 * 12, shallow=22 * 2)
    act, trig = _ready()
    trig[IDX["Q"]] = (0, 0.1, 0.9)
    [s] = analytics.suggest(rated, act, trig, IDX)["suggestions"]
    assert s["id"] == "group:letters"


def test_rapid_trigger_keys_keep_their_mode_and_pair():
    rated = {IDX["Space"]: _agg(presses=300, shallow=30)}
    act, trig = _ready(mode=(13, 0.15, 0.2))
    [s] = analytics.suggest(rated, act, trig, IDX)["suggestions"]
    assert s["id"] == "group:space"
    assert (s["mode"], s["rt_press_mm"], s["rt_release_mm"]) == (13, 0.15, 0.2)


def test_keys_without_a_read_back_get_nothing():
    rated = {IDX["Space"]: _agg(presses=300, shallow=30)}
    act, trig = _ready()
    del trig[IDX["Space"]]
    assert analytics.suggest(rated, act, trig, IDX)["suggestions"] == []
    act, trig = _ready()
    del act[IDX["Space"]]
    assert analytics.suggest(rated, act, trig, IDX)["suggestions"] == []


def test_other_keys_are_judged_per_key_and_sorted_by_affected_presses():
    rated = {IDX["Enter"]: _agg(presses=300, shallow=20),
             IDX["1"]: _agg(presses=300, shallow=40)}
    act, trig = _ready()
    out = analytics.suggest(rated, act, trig, IDX)
    assert [s["id"] for s in out["suggestions"]] == ["key:1", "key:Enter"]
    assert out["suggestions"][0]["label"] == "1"


def test_notes_explain_waiting_floor_and_mixed():
    act, trig = _ready()
    rated = {IDX["Space"]: _agg(presses=120)}
    notes = {n["id"]: n for n in analytics.suggest(rated, act, trig, IDX)["notes"]}
    assert notes["note:space"]["kind"] == "data"
    assert "120 of 200" in notes["note:space"]["text"]
    assert notes["note:letters"]["kind"] == "data"

    act, trig = _ready(act=30)
    rated = {IDX["Space"]: _agg(presses=250, shallow=50, shallow_bin=2)}
    notes = {n["id"]: n for n in analytics.suggest(rated, act, trig, IDX)["notes"]}
    assert notes["note:space"]["kind"] == "floor" and "0.30 mm" in notes["note:space"]["text"]

    act, trig = _ready()
    rated = _spread(analytics.GROUPS[1][2], presses=22 * 300, shallow=22 * 30,
                    barely=22 * 60)
    out = analytics.suggest(rated, act, trig, IDX)
    assert out["suggestions"] == []
    notes = {n["id"]: n for n in out["notes"]}
    assert notes["note:letters"]["kind"] == "mixed"


def test_suggested_values_respect_the_hard_limits():
    act, trig = _ready()
    for a in (8, 30, 80, 200, 335, 340):
        for agg in (_agg(presses=300, shallow=90, shallow_bin=1),
                    _agg(presses=300, barely=100)):
            v = analytics.evaluate(agg, a, True)
            if v and "target_raw" in v:
                assert analytics.MIN_RAW <= v["target_raw"] <= analytics.MAX_RAW
                assert v["target_raw"] >= analytics.FLOOR_RAW


def test_output_is_aggregates_only():
    rated = {IDX["Space"]: _agg(presses=300, shallow=30)}
    act, trig = _ready()
    out = analytics.suggest(rated, act, trig, IDX)
    allowed = {"id", "scope", "group", "label", "codes", "direction",
               "current_mm", "suggested_mm", "mode", "rt_press_mm",
               "rt_release_mm", "presses", "attempts", "shallow", "barely",
               "shallow_pct", "barely_pct", "p10_mm", "score", "title", "detail"}
    for s in out["suggestions"]:
        assert set(s) == allowed
