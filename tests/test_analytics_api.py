"""Phase 4 bridge: get_analytics / get_tune_suggestions over real Telemetry
day buckets, actuation + trigger mode from the (faked) read-back. Applying a
suggestion is the existing set_trigger_codes + verify_actuation path; the
fake driver only records calls. No HID, no keyboard."""
import json

import analytics
import telemetry
from test_stats_api import _api, TODAY
from test_telemetry import _press


def _read_back(a, mm=0.80, mode=0, codes=None, rt=(0.3, 0.3)):
    """Fake firmware read-back of every key (or `codes`) at `mm`."""
    names = {a.km.by_index[i]["name"]: i for i in a.km.indices()}
    want = set(a.km.indices_for_codes(codes)) if codes else set(names.values())
    a.driver.detail = {n: {"travel_mm": mm, "mode": mode,
                           "rt_press_mm": rt[0], "rt_release_mm": rt[1]}
                       for n, i in names.items() if i in want}
    assert a.verify_actuation([])["ok"]


def _type(a, code, n, depths, t0=0.0):
    t = t0
    for _ in range(n):
        t = _press(a.telemetry, a.km.index_of_code[code], depths, t0=t)
    return t


# ---------------------------------------------------------- get_analytics ----
def test_get_analytics_per_code_views_and_daily_series(tmp_path):
    a = _api(tmp_path)
    t = _type(a, "W", 3, [1.0, 3.35])
    _type(a, "Q", 1, [1.0, 2.0], t0=t)
    r = a.get_analytics(7)
    assert r["ok"] and r["enabled"] and r["supported"]
    assert r["days"] == 7 and r["board"] == "aula-win60-he"
    w = r["keys"]["W"]
    assert w["presses"] == 3 and w["bottom"] == 3 and w["bottom_pct"] == 100.0
    assert w["heat"] == 1.0 and r["keys"]["Q"]["heat"] == 0.333
    assert w["avg_peak_mm"] == 3.35
    assert r["totals"]["presses"] == 4
    assert len(r["daily"]) == 14 and r["daily"][-1]["date"] == TODAY
    assert r["daily"][-1]["presses"] == 4


def test_get_analytics_merges_actuation_buckets(tmp_path):
    a = _api(tmp_path)
    t = _type(a, "W", 2, [2.0])
    _read_back(a, 0.80)
    _type(a, "W", 3, [2.0], t0=t)
    assert a.get_analytics(1)["keys"]["W"]["presses"] == 5


def test_get_analytics_clamps_days_and_never_raises(tmp_path):
    a = _api(tmp_path)
    assert a.get_analytics(0)["days"] == 1
    assert a.get_analytics(5000)["days"] == 90
    assert a.get_analytics("x")["days"] == 1
    a.telemetry.recent_buckets = None                    # boom
    r = a.get_analytics(1)
    assert r["ok"] is False and r["error"]


def test_get_analytics_output_is_aggregates_only(tmp_path):
    a = _api(tmp_path)
    _type(a, "W", 2, [1.0, 2.0])
    r = a.get_analytics(1)
    assert set(r) == {"ok", "enabled", "supported", "board", "days", "keys",
                      "totals", "daily"}
    for rec in r["keys"].values():
        assert set(rec) == {"presses", "shallow", "barely", "bottom",
                            "unrated", "attempts", "bottom_pct", "shallow_pct",
                            "barely_pct", "avg_peak_mm", "avg_ttp_ms", "heat"}
    for row in r["daily"]:
        assert set(row) == {"date", "presses", "shallow", "bottom"}
    json.dumps(r)                                        # bridge-serialisable


# --------------------------------------------------- get_tune_suggestions ----
def test_no_read_back_means_no_suggestions(tmp_path):
    a = _api(tmp_path)
    _type(a, "Space", 300, [2.0])
    r = a.get_tune_suggestions()
    assert r["ok"] and r["suggestions"] == [] and r["read_back"] is False
    assert r["min_presses"] == 200 and r["window_days"] == 14


def test_shallow_space_presses_produce_a_suggestion(tmp_path):
    a = _api(tmp_path)
    _read_back(a, 0.80)
    t = _type(a, "Space", 270, [1.0, 3.0])
    _type(a, "Space", 30, [0.30, 0.55], t0=t)
    r = a.get_tune_suggestions()
    assert r["read_back"] is True
    [s] = r["suggestions"]
    assert s["id"] == "group:space" and s["codes"] == ["Space"]
    assert s["direction"] == "shallower"
    assert s["current_mm"] == 0.80 and s["suggested_mm"] == 0.50
    assert s["mode"] == 0
    json.dumps(r)


def test_presses_at_an_old_actuation_do_not_count(tmp_path):
    a = _api(tmp_path)
    _read_back(a, 1.20)
    t = _type(a, "Space", 270, [1.5, 3.0])
    t = _type(a, "Space", 30, [0.30, 0.55], t0=t)
    _read_back(a, 0.80)                                  # user changed it
    _type(a, "Space", 50, [1.5, 3.0], t0=t)
    r = a.get_tune_suggestions()
    assert r["suggestions"] == []
    [n] = [n for n in r["notes"] if n["id"] == "note:space"]
    assert n["kind"] == "data" and "50 of 200" in n["text"]


def test_presses_between_a_write_and_its_read_back_are_ignored(tmp_path):
    a = _api(tmp_path)
    _read_back(a, 0.80)
    assert a.set_trigger_codes(["Space"], 0.50)["ok"]   # fake driver: no HID
    _type(a, "Space", 300, [0.30, 0.45])                 # unrated
    _read_back(a, 0.50)
    assert a.get_tune_suggestions()["suggestions"] == []


def test_rapid_trigger_mode_and_pair_come_from_the_read_back(tmp_path):
    a = _api(tmp_path)
    _read_back(a, 0.80, mode=13, rt=(0.15, 0.25))
    t = _type(a, "Space", 270, [1.0, 3.0])
    _type(a, "Space", 30, [0.30, 0.55], t0=t)
    [s] = a.get_tune_suggestions()["suggestions"]
    assert (s["mode"], s["rt_press_mm"], s["rt_release_mm"]) == (13, 0.15, 0.25)


def test_applying_a_suggestion_is_the_normal_write_plus_read_back(tmp_path):
    a = _api(tmp_path)
    writes = []
    a.driver.set_actuation = lambda idxs, mode, travel, i1, i2: writes.append(
        (sorted(idxs), mode, round(travel, 2), i1, i2))
    _read_back(a, 0.80)
    t = _type(a, "Space", 270, [1.0, 3.0])
    _type(a, "Space", 30, [0.30, 0.55], t0=t)
    [s] = a.get_tune_suggestions()["suggestions"]
    # what the UI's writeActuation does: set_trigger_codes, then read back
    r = a.set_trigger_codes(s["codes"], s["suggested_mm"],
                            s["rt_press_mm"] or 0, s["rt_release_mm"] or 0,
                            s["mode"])
    assert r["ok"]
    assert writes == [([a.km.index_of_code["Space"]], 0, 0.50, None, None)]
    _read_back(a, 0.50)
    assert a.get_tune_suggestions()["suggestions"] == []   # new bucket: 0 presses


def test_unsupported_board_gets_an_empty_ok_answer(tmp_path):
    a = _api(tmp_path, slug="aula-mini60he-pro")
    r = a.get_tune_suggestions()
    assert r["ok"] and r["supported"] is False and r["suggestions"] == []


def test_bridge_methods_without_telemetry_fail_softly(tmp_path):
    a = _api(tmp_path)
    a.telemetry = None
    for r in (a.get_analytics(1), a.get_tune_suggestions()):
        assert r["ok"] is False and r["error"]


def test_get_tune_suggestions_never_raises(tmp_path):
    a = _api(tmp_path)
    a.telemetry.actuation = None                         # boom
    r = a.get_tune_suggestions()
    assert r["ok"] is False and r["error"]


def test_get_tune_suggestions_never_writes(tmp_path):
    a = _api(tmp_path)
    calls = []
    a.driver.set_actuation = lambda *x, **k: calls.append(x)
    _read_back(a, 0.80)
    t = _type(a, "Space", 270, [1.0, 3.0])
    _type(a, "Space", 30, [0.30, 0.55], t0=t)
    assert a.get_tune_suggestions()["suggestions"]
    assert calls == []
