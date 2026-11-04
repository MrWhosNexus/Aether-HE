"""Phase 1 key statistics on disk: day files, merge, prune, clear, flusher,
and the privacy anti-goal (only per-key aggregates ever reach the file)."""
import json
import threading
import time

from telemetry import Telemetry, FIELDS, HIST_BINS
from test_telemetry import _tel, _press, W, TODAY

SLUG = "aula-win60-he"


def _day(tmp_path, date=TODAY):
    return tmp_path / "stats" / f"{date}.json"


def _doc(tmp_path, date=TODAY):
    return json.loads(_day(tmp_path, date).read_text(encoding="utf-8"))


def test_nothing_is_written_until_flush(tmp_path):
    tel = _tel(tmp_path)
    _press(tel, W, [2.0])
    assert not (tmp_path / "stats").exists()
    assert tel.flush() is True
    assert _doc(tmp_path)["boards"][SLUG]["46"]["presses"] == 1


def test_flushes_accumulate_without_double_counting(tmp_path):
    tel = _tel(tmp_path)
    _press(tel, W, [2.0]); tel.flush()
    _press(tel, W, [2.0]); tel.flush()
    assert _doc(tmp_path)["boards"][SLUG]["46"]["presses"] == 2
    assert tel.aggregate(1)[W]["presses"] == 2


def test_aggregate_merges_day_files_and_pending(tmp_path):
    old = _tel(tmp_path, today=lambda: "2026-11-03")
    _press(old, W, [2.0]); old.flush()
    tel = _tel(tmp_path)
    _press(tel, W, [2.0])                      # still pending
    assert tel.aggregate(1)[W]["presses"] == 1
    assert tel.aggregate(2)[W]["presses"] == 2
    assert tel.load_day("2026-11-03")[W]["presses"] == 1


def test_day_rollover_buckets_by_the_day_a_press_ends(tmp_path):
    day = [TODAY]
    tel = _tel(tmp_path, today=lambda: day[0])
    _press(tel, W, [2.0])
    day[0] = "2026-11-05"
    _press(tel, W, [2.0])
    tel.flush()
    assert _doc(tmp_path, TODAY)["boards"][SLUG]["46"]["presses"] == 1
    assert _doc(tmp_path, "2026-11-05")["boards"][SLUG]["46"]["presses"] == 1


def test_prune_deletes_files_90_days_old_and_keeps_newer(tmp_path):
    d = tmp_path / "stats"
    d.mkdir()
    for name in ("2026-08-06.json", "2026-08-07.json", "notes.json", "2026-13-99.json"):
        (d / name).write_text("{}", encoding="utf-8")
    _tel(tmp_path).flush()
    left = sorted(p.name for p in d.iterdir())
    assert left == ["2026-08-07.json", "2026-13-99.json", "notes.json"]


def test_corrupt_day_file_is_ignored_then_rewritten(tmp_path):
    (tmp_path / "stats").mkdir()
    _day(tmp_path).write_text("{not json", encoding="utf-8")
    tel = _tel(tmp_path)
    assert tel.aggregate(1) == {}
    _press(tel, W, [2.0])
    assert tel.flush() is True
    assert _doc(tmp_path)["boards"][SLUG]["46"]["presses"] == 1


def test_foreign_fields_are_dropped_and_never_rewritten(tmp_path):
    (tmp_path / "stats").mkdir()
    rec = {"presses": 3, "hist": [0] * HIST_BINS, "typed": "hello"}
    doc = {"version": 1, "date": TODAY, "log": ["h", "e"],
           "boards": {SLUG: {"46": rec, "abc": {"presses": 9}}}}
    _day(tmp_path).write_text(json.dumps(doc), encoding="utf-8")
    tel = _tel(tmp_path)
    agg = tel.aggregate(1)
    assert set(agg) == {W}
    assert set(agg[W]) == set(FIELDS) | {"hist"} and agg[W]["presses"] == 3
    _press(tel, W, [2.0]); tel.flush()
    text = _day(tmp_path).read_text(encoding="utf-8")
    assert "hello" not in text and "log" not in text and "abc" not in text
    assert _doc(tmp_path)["boards"][SLUG]["46"]["presses"] == 4


def test_clear_removes_day_files_and_pending_only(tmp_path):
    tel = _tel(tmp_path)
    _press(tel, W, [2.0]); tel.flush()
    (tmp_path / "stats" / "notes.txt").write_text("keep", encoding="utf-8")
    _press(tel, W, [2.0])
    assert tel.clear() == 1
    assert tel.aggregate(1) == {}
    assert (tmp_path / "stats" / "notes.txt").exists()


def test_boards_are_kept_apart(tmp_path):
    tel = _tel(tmp_path)
    t = _press(tel, W, [2.0])
    tel.set_board("aula-win68-he")
    t = _press(tel, W, [2.0], t0=t)
    _press(tel, W, [2.0], t0=t)
    tel.flush()
    boards = _doc(tmp_path)["boards"]
    assert boards[SLUG]["46"]["presses"] == 1
    assert boards["aula-win68-he"]["46"]["presses"] == 2
    assert tel.aggregate(1)[W]["presses"] == 2


def test_unwritable_stats_dir_keeps_counts_and_never_raises(tmp_path):
    (tmp_path / "stats").write_text("a file where the folder should be", encoding="utf-8")
    tel = _tel(tmp_path)
    _press(tel, W, [2.0])
    assert tel.flush() is False
    assert tel.aggregate(1)[W]["presses"] == 1
    assert tel.clear() == 0


def test_flusher_writes_on_its_interval(tmp_path):
    tel = _tel(tmp_path, flush_interval_s=0.05)
    try:
        _press(tel, W, [2.0])
        deadline = time.monotonic() + 2.0
        while not _day(tmp_path).exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert _day(tmp_path).exists()
    finally:
        tel.close()


def test_close_flushes_pending(tmp_path):
    tel = _tel(tmp_path)
    _press(tel, W, [2.0])
    tel.close()
    assert _doc(tmp_path)["boards"][SLUG]["46"]["presses"] == 1


def test_concurrent_feed_and_flush_lose_and_duplicate_nothing(tmp_path):
    tel = _tel(tmp_path)

    def typist():
        t = 0.0
        for n in range(400):
            t = _press(tel, (n % 4) + 20, [0.5, 2.0], t0=t)

    th = threading.Thread(target=typist)
    th.start()
    while th.is_alive():
        tel.flush()
    th.join()
    tel.flush()
    keys = _doc(tmp_path)["boards"][SLUG]
    assert sum(k["presses"] for k in keys.values()) == 400


# ---- privacy anti-goal: aggregates only ----------------------------------
def test_day_file_holds_only_per_key_aggregates(tmp_path):
    tel = _tel(tmp_path)
    t = _press(tel, W, [0.4, 1.2, 3.35])
    _press(tel, 47, [0.3, 0.9], t0=t)
    tel.flush()
    doc = _doc(tmp_path)
    assert set(doc) == {"version", "date", "boards"}
    assert doc["version"] == 1 and doc["date"] == TODAY
    for keys in doc["boards"].values():
        for k, rec in keys.items():
            assert k.isdigit()
            assert set(rec) == set(FIELDS) | {"hist"}
            assert all(type(rec[f]) is int for f in FIELDS)
            assert len(rec["hist"]) == HIST_BINS
            assert all(type(v) is int for v in rec["hist"])


def test_day_file_is_identical_whatever_the_order_and_time_of_keystrokes(tmp_path):
    shapes = {46: [0.4, 1.2, 2.0], 47: [0.3, 3.35], 23: [0.5, 0.9]}

    def type_(tel, order, t0):
        t = t0
        for idx in order:
            t = _press(tel, idx, shapes[idx], t0=t)
        tel.flush()

    type_(_tel(tmp_path / "a"), [46, 47, 46, 23, 47, 46], 100.0)
    type_(_tel(tmp_path / "b"), [23, 46, 46, 47, 46, 47], 98765.4321)
    a = (tmp_path / "a" / "stats" / f"{TODAY}.json").read_bytes()
    b = (tmp_path / "b" / "stats" / f"{TODAY}.json").read_bytes()
    assert a == b
