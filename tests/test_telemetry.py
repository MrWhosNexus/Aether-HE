"""Phase 1 key statistics: press segmentation and per-key aggregates.
No HID: Telemetry.feed is driven directly with (device index, mm, t), the
way LiveReader.on_sample calls it (0.0 = the reader cleared the key)."""
from telemetry import Telemetry, peak_percentile, HIST_BINS

W = 46
TODAY = "2026-11-04"


def _tel(tmp_path, **kw):
    kw.setdefault("board", "aula-win60-he")
    kw.setdefault("today", lambda: TODAY)
    kw.setdefault("flush_interval_s", None)
    return Telemetry(str(tmp_path / "stats"), **kw)


def _press(tel, idx, depths, t0=100.0, step=0.01):
    """One press as the reader reports it: the samples, then the clear."""
    t = t0
    for mm in depths:
        tel.feed(idx, mm, t)
        t += step
    tel.feed(idx, 0.0, t)
    return t + step


def test_one_press_records_peak_bin_and_time_to_peak(tmp_path):
    tel = _tel(tmp_path)
    _press(tel, W, [0.31, 1.02, 2.06, 3.25, 2.42, 2.11, 1.72, 1.18, 0.45])
    agg = tel.aggregate(1)[W]
    assert agg["presses"] == 1 and agg["unrated"] == 1
    assert len(agg["hist"]) == HIST_BINS
    assert agg["hist"][32] == 1 and sum(agg["hist"]) == 1
    assert agg["bottom"] == 0 and agg["shallow"] == 0 and agg["barely"] == 0
    assert agg["ttp_ms"] == 30


def test_bottom_out_counts_from_3_30_and_3_40_lands_in_the_last_bin(tmp_path):
    tel = _tel(tmp_path)
    t = _press(tel, W, [1.0, 3.30])
    t = _press(tel, W, [1.0, 3.29], t0=t)
    _press(tel, W, [1.0, 3.40], t0=t)
    agg = tel.aggregate(1)[W]
    assert agg["presses"] == 3 and agg["bottom"] == 2
    assert agg["hist"][33] == 2 and agg["hist"][32] == 1


def test_touch_at_or_below_0_15_is_not_counted(tmp_path):
    tel = _tel(tmp_path)
    _press(tel, W, [0.10, 0.15])
    assert tel.aggregate(1) == {}
    _press(tel, W, [0.10, 0.16])
    assert tel.aggregate(1)[W]["hist"][1] == 1


def test_shallow_attempt_below_actuation_is_not_a_press(tmp_path):
    tel = _tel(tmp_path)
    tel.set_actuation({W: 0.80})
    _press(tel, W, [0.20, 0.50, 0.30])
    agg = tel.aggregate(1)[W]
    assert agg["shallow"] == 1 and agg["presses"] == 0
    assert agg["hist"][5] == 1 and agg["ttp_ms"] == 0 and agg["unrated"] == 0


def test_barely_over_is_within_0_10_above_actuation(tmp_path):
    tel = _tel(tmp_path)
    tel.set_actuation({W: 0.80})
    t = _press(tel, W, [0.50, 0.80])
    t = _press(tel, W, [0.50, 0.90], t0=t)
    _press(tel, W, [0.50, 0.91], t0=t)
    agg = tel.aggregate(1)[W]
    assert agg["presses"] == 3 and agg["barely"] == 2
    assert agg["shallow"] == 0 and agg["unrated"] == 0


def test_forgotten_actuation_makes_presses_unrated(tmp_path):
    tel = _tel(tmp_path)
    tel.set_actuation({W: 0.80})
    tel.forget_actuation([W])
    _press(tel, W, [0.50])
    agg = tel.aggregate(1)[W]
    assert agg["presses"] == 1 and agg["unrated"] == 1 and agg["shallow"] == 0


def test_repress_without_release_splits_into_two_presses(tmp_path):
    tel = _tel(tmp_path)
    _press(tel, W, [0.50, 1.50, 2.00, 1.60, 2.10])
    agg = tel.aggregate(1)[W]
    assert agg["presses"] == 2
    assert agg["hist"][20] == 1 and agg["hist"][21] == 1
    assert agg["ttp_ms"] == 20


def test_small_wobble_does_not_split(tmp_path):
    tel = _tel(tmp_path)
    _press(tel, W, [1.00, 2.00, 1.85, 2.00])
    assert tel.aggregate(1)[W]["presses"] == 1


def test_sample_below_noise_floor_ends_the_press(tmp_path):
    tel = _tel(tmp_path)
    tel.feed(W, 1.0, 1.0)
    tel.feed(W, 2.0, 1.01)
    tel.feed(W, 0.04, 1.02)
    assert tel.aggregate(1)[W]["presses"] == 1


def test_time_to_peak_is_capped_at_one_second(tmp_path):
    tel = _tel(tmp_path)
    tel.feed(W, 0.5, 1.0)
    tel.feed(W, 2.0, 6.0)
    tel.feed(W, 0.0, 6.1)
    assert tel.aggregate(1)[W]["ttp_ms"] == 1000


def test_nothing_is_counted_while_disabled_or_without_a_board(tmp_path):
    off = _tel(tmp_path, enabled=False)
    _press(off, W, [2.0])
    assert off.aggregate(1) == {}
    off.set_enabled(True)
    _press(off, W, [2.0])
    assert off.aggregate(1)[W]["presses"] == 1
    nob = _tel(tmp_path, board=None)
    _press(nob, W, [2.0])
    assert nob.aggregate(1) == {}


def test_abort_open_drops_a_press_in_progress(tmp_path):
    tel = _tel(tmp_path)
    tel.feed(W, 2.0, 1.0)
    tel.abort_open()
    tel.feed(W, 0.0, 1.1)
    assert tel.aggregate(1) == {}


def test_peak_percentile_interpolates_inside_the_bin():
    hist = [0] * HIST_BINS
    hist[5], hist[20] = 10, 90
    assert peak_percentile(hist, 0.10) == 0.6
    assert peak_percentile(hist, 0.50) == 2.04
    assert peak_percentile([0] * HIST_BINS, 0.10) is None


def test_bottom_counts_even_when_the_press_is_below_actuation(tmp_path):
    tel = _tel(tmp_path)
    tel.set_actuation({W: 3.40})
    _press(tel, W, [1.0, 3.35])
    agg = tel.aggregate(1)[W]
    assert agg["bottom"] == 1 and agg["shallow"] == 1 and agg["presses"] == 0
    assert sum(agg["hist"]) == agg["presses"] + agg["shallow"]
