"""Phase 4: telemetry files every press under the actuation its key had, so
auto-tune can use only presses recorded at the CURRENT actuation. The
Phase 1 per-key view (load_day / aggregate / get_stats) is unchanged.
No HID: Telemetry.feed is driven directly."""
import json

from telemetry import Telemetry, bucket_idx, HIST_BINS
from test_telemetry import _tel, _press, W, TODAY

SLUG = "aula-win60-he"


def _doc(tmp_path, date=TODAY):
    p = tmp_path / "stats" / f"{date}.json"
    return json.loads(p.read_text(encoding="utf-8"))


def test_rated_and_unrated_presses_land_in_separate_buckets(tmp_path):
    tel = _tel(tmp_path)
    t = _press(tel, W, [2.0])                       # actuation unknown
    tel.set_actuation({W: 0.80})
    t = _press(tel, W, [2.0], t0=t)
    _press(tel, W, [0.50], t0=t)                    # shallow at 0.80
    b = tel.load_day_buckets(TODAY)
    assert set(b) == {W, (W, 80)}
    assert b[W]["presses"] == 1 and b[W]["unrated"] == 1
    assert b[(W, 80)]["presses"] == 1 and b[(W, 80)]["shallow"] == 1
    assert b[(W, 80)]["unrated"] == 0


def test_load_day_and_aggregate_still_merge_per_key(tmp_path):
    tel = _tel(tmp_path)
    t = _press(tel, W, [2.0])
    tel.set_actuation({W: 0.80})
    t = _press(tel, W, [2.0], t0=t)
    tel.set_actuation({W: 0.50})
    _press(tel, W, [0.30], t0=t)
    day = tel.load_day(TODAY)
    assert set(day) == {W}
    assert day[W]["presses"] == 2 and day[W]["shallow"] == 1
    assert sum(day[W]["hist"]) == 3
    assert tel.aggregate(1)[W] == day[W]


def test_a_changed_actuation_starts_a_new_bucket(tmp_path):
    tel = _tel(tmp_path)
    tel.set_actuation({W: 0.80})
    t = _press(tel, W, [2.0])
    tel.set_actuation({W: 0.55})
    _press(tel, W, [2.0], t0=t)
    b = tel.load_day_buckets(TODAY)
    assert b[(W, 80)]["presses"] == 1 and b[(W, 55)]["presses"] == 1


def test_forgotten_actuation_files_presses_as_unrated(tmp_path):
    tel = _tel(tmp_path)
    tel.set_actuation({W: 0.80})
    tel.forget_actuation([W])
    _press(tel, W, [2.0])
    assert set(tel.load_day_buckets(TODAY)) == {W}


def test_bucket_keys_round_trip_through_the_day_file(tmp_path):
    tel = _tel(tmp_path)
    t = _press(tel, W, [2.0])
    tel.set_actuation({W: 0.80})
    _press(tel, W, [2.0], t0=t)
    tel.flush()
    assert set(_doc(tmp_path)["boards"][SLUG]) == {"46", "46@80"}
    again = _tel(tmp_path)
    b = again.load_day_buckets(TODAY)
    assert b[W]["presses"] == 1 and b[(W, 80)]["presses"] == 1


def test_pending_and_file_counts_of_one_bucket_add_up(tmp_path):
    tel = _tel(tmp_path)
    tel.set_actuation({W: 0.80})
    t = _press(tel, W, [2.0])
    tel.flush()
    _press(tel, W, [2.0], t0=t)
    assert tel.load_day_buckets(TODAY)[(W, 80)]["presses"] == 2
    tel.flush()
    assert _doc(tmp_path)["boards"][SLUG]["46@80"]["presses"] == 2


def test_malformed_bucket_keys_are_dropped(tmp_path):
    (tmp_path / "stats").mkdir()
    rec = {"presses": 1, "hist": [0] * HIST_BINS}
    doc = {"version": 1, "date": TODAY, "boards": {SLUG: {
        "46@80": rec, "46@": rec, "46@1234": rec, "@80": rec, "a@b": rec,
        "46@80@1": rec, "1234": rec}}}
    (tmp_path / "stats" / f"{TODAY}.json").write_text(json.dumps(doc), encoding="utf-8")
    tel = _tel(tmp_path)
    assert set(tel.load_day_buckets(TODAY)) == {(W, 80)}
    tel.set_actuation({W: 0.80})
    _press(tel, W, [2.0])
    tel.flush()
    assert set(_doc(tmp_path)["boards"][SLUG]) == {"46@80"}


def test_pre_split_file_loads_as_the_unknown_actuation_bucket(tmp_path):
    (tmp_path / "stats").mkdir()
    rec = {"presses": 5, "shallow": 2, "barely": 1, "hist": [0] * HIST_BINS}
    doc = {"version": 1, "date": TODAY, "boards": {SLUG: {"46": rec}}}
    (tmp_path / "stats" / f"{TODAY}.json").write_text(json.dumps(doc), encoding="utf-8")
    b = _tel(tmp_path).load_day_buckets(TODAY)
    assert set(b) == {W} and b[W]["shallow"] == 2


def test_actuation_returns_a_copy_in_hundredths(tmp_path):
    tel = _tel(tmp_path)
    tel.set_actuation({W: 0.80, 47: 1.234})
    act = tel.actuation()
    assert act == {W: 80, 47: 123}
    act[W] = 1
    assert tel.actuation()[W] == 80


def test_recent_buckets_lists_days_newest_first(tmp_path):
    old = _tel(tmp_path, today=lambda: "2026-11-02")
    old.set_actuation({W: 0.80})
    _press(old, W, [2.0])
    old.flush()
    tel = _tel(tmp_path)
    days = tel.recent_buckets(3)
    assert [d for d, _ in days] == ["2026-11-04", "2026-11-03", "2026-11-02"]
    assert days[0][1] == {} and days[1][1] == {}
    assert days[2][1][(W, 80)]["presses"] == 1
    assert [d for d, _ in tel.recent_buckets(0)] == [TODAY]


def test_bucket_idx():
    assert bucket_idx(46) == 46 and bucket_idx((46, 80)) == 46
