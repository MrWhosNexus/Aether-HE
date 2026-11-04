"""Phase 4 analytics views: pure functions over telemetry aggregates
(groups, bucket merging, per-key summaries, the 14-day series).
No disk, no HID, no clock."""
import datetime

import pytest

import analytics
import device_state
import telemetry

KM = device_state.KeyMap()
IDX = KM.index_of_code


def _agg(presses=0, shallow=0, barely=0, bottom=0, unrated=0, ttp_ms=0,
         hist=None, press_bin=30, shallow_bin=5):
    a = telemetry.empty_agg()
    a.update(presses=presses, shallow=shallow, barely=barely, bottom=bottom,
             unrated=unrated, ttp_ms=ttp_ms)
    if hist is None:
        a["hist"][press_bin] += presses
        a["hist"][shallow_bin] += shallow
    else:
        for b, n in hist.items():
            a["hist"][b] += n
    return a


# ---------------------------------------------------------------- groups ----
def test_groups_are_disjoint_and_use_real_design_codes():
    seen = []
    for gid, label, codes, _ in analytics.GROUPS:
        assert codes and label
        for c in codes:
            assert c in device_state.DESIGN_CODES, c
        seen.extend(codes)
    assert len(seen) == len(set(seen))
    assert [g[0] for g in analytics.GROUPS] == ["wasd", "letters", "mods", "space"]
    assert len(analytics.GROUPS[1][2]) == 22
    assert analytics.DEEPER_CODES == frozenset(analytics.GROUPS[1][2])
    assert not analytics.DEEPER_CODES & set(analytics.WASD)


# --------------------------------------------------------------- buckets ----
def test_merge_days_merges_every_bucket_per_key():
    d1 = {46: _agg(presses=2, unrated=2), (46, 80): _agg(presses=3)}
    d2 = {(46, 55): _agg(presses=1), (47, 80): _agg(presses=4)}
    m = analytics.merge_days([d1, d2])
    assert m[46]["presses"] == 6 and m[47]["presses"] == 4


def test_rated_at_keeps_only_the_current_actuation():
    d1 = {46: _agg(presses=2, unrated=2), (46, 80): _agg(presses=3),
          (46, 55): _agg(presses=9)}
    d2 = {(46, 80): _agg(presses=1, shallow=1), (47, 80): _agg(presses=4)}
    r = analytics.rated_at([d1, d2], {46: 80})
    assert set(r) == {46}
    assert r[46]["presses"] == 4 and r[46]["shallow"] == 1


# --------------------------------------------------------------- summary ----
def _days(n, today=datetime.date(2026, 11, 4)):
    """[(date, {})] for the last n days, newest first."""
    return [((today - datetime.timedelta(days=k)).isoformat(), {})
            for k in range(n)]


def test_key_summary_percentages_and_averages():
    a = _agg(presses=8, shallow=2, barely=2, bottom=5, unrated=4, ttp_ms=400,
             hist={2: 2, 7: 4, 33: 4})
    s = analytics.key_summary(a)
    assert s["attempts"] == 10
    assert s["bottom_pct"] == 50.0
    assert s["shallow_pct"] == pytest.approx(33.3)          # 2 / (4 rated + 2)
    assert s["barely_pct"] == 50.0                           # 2 / 4 rated
    assert s["avg_peak_mm"] == pytest.approx((2.5 * 2 + 7.5 * 4 + 33.5 * 4) * 0.1 / 10, abs=0.01)
    assert s["avg_ttp_ms"] == 50


def test_key_summary_of_nothing_has_no_divisions_by_zero():
    s = analytics.key_summary(telemetry.empty_agg())
    assert s["bottom_pct"] is None and s["shallow_pct"] is None
    assert s["barely_pct"] is None and s["avg_peak_mm"] is None
    assert s["avg_ttp_ms"] is None and s["presses"] == 0


def test_summarize_window_heat_and_daily_series():
    W, Q = IDX["W"], IDX["Q"]
    days = _days(14)
    days[0] = ("2026-11-04", {(W, 80): _agg(presses=10)})
    days[1] = ("2026-11-03", {Q: _agg(presses=5, unrated=5)})
    days[2] = ("2026-11-02", {(W, 80): _agg(presses=100)})
    out = analytics.summarize(days, KM.code_of, 2)
    assert set(out["keys"]) == {"W", "Q"}
    assert out["keys"]["W"]["presses"] == 10 and out["keys"]["W"]["heat"] == 1.0
    assert out["keys"]["Q"]["heat"] == 0.5
    assert out["totals"]["presses"] == 15
    assert len(out["daily"]) == analytics.DAILY_DAYS
    assert out["daily"][0]["date"] == "2026-10-22"
    assert out["daily"][-1] == {"date": "2026-11-04", "presses": 10,
                                "shallow": 0, "bottom": 0}
    assert out["daily"][-3]["presses"] == 100


def test_summarize_of_no_data():
    out = analytics.summarize(_days(14), KM.code_of, 1)
    assert out["keys"] == {} and out["totals"]["presses"] == 0
    assert all(r["presses"] == 0 for r in out["daily"])
