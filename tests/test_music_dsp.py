"""Phase 7 music visualizer, pure DSP: band edges/bins, band powers, the
BandAnalyzer (dB, auto-gain, energy-flux beats). Plain lists only: no numpy,
no soundcard, no audio device."""
import math
import random

import pytest

import music


def _p(db):
    """dBFS -> power."""
    return 10.0 ** (db / 10.0)


# ------------------------------------------------------------ band edges ----
def test_fourteen_log_spaced_bands_from_40_hz_to_16_khz():
    e = music.band_edges()
    assert len(e) == 15
    assert e[0] == pytest.approx(40.0) and e[-1] == pytest.approx(16000.0)
    ratios = [b / a for a, b in zip(e, e[1:])]
    assert all(r == pytest.approx(ratios[0]) for r in ratios)
    assert ratios[0] == pytest.approx(400.0 ** (1 / 14))


def test_bins_cover_every_band_at_the_shipping_fft_size():
    bins = music.band_bins(music.N_FFT, music.RATE, music.band_edges())
    assert len(bins) == 14
    assert bins[0][:2] == (1, 2)                  # 46.9 Hz bin is the 40-61 Hz band
    for lo, hi, w in bins:
        assert 1 <= lo < hi <= music.N_FFT // 2 + 1
        assert w > 0
    assert [b[0] for b in bins] == sorted(b[0] for b in bins)


def test_a_band_narrower_than_a_bin_gets_the_nearest_bin():
    bins = music.band_bins(256, 48000, music.band_edges())   # 187.5 Hz bins
    for lo, hi, _ in bins:
        assert hi - lo >= 1 and lo >= 1
    assert bins[0][:2] == (1, 2)


def test_band_powers_weight_the_bin_sum():
    power = [0.0, 1.0, 2.0, 3.0, 4.0]
    assert music.band_powers(power, [(1, 3, 0.5), (3, 5, 2.0)]) == [1.5, 14.0]


# ------------------------------------------------------------- analyzer ----
def test_levels_are_db_under_the_loudest_band():
    an = music.BandAnalyzer(3)
    lv, _ = an.feed([_p(-10), _p(-30), _p(-50)], 0.01)
    assert lv[0] == pytest.approx(1.0)
    assert lv[1] == pytest.approx(0.5)
    assert lv[2] == pytest.approx(0.0)


def test_silence_and_garbage_powers_are_zero_not_nan():
    an = music.BandAnalyzer(4)
    for _ in range(50):
        lv, beat = an.feed([0.0, -1.0, float("nan"), 0.0], 0.01)
        assert lv == [0.0, 0.0, 0.0, 0.0] and beat is False
    assert an.ref == music.REF_FLOOR_DB


def test_auto_gain_lifts_quiet_music_to_full_scale():
    loud = [_p(-10), _p(-25), _p(-40)]
    quiet = [_p(-40), _p(-55), _p(-70)]          # same shape, 30 dB down
    an = music.BandAnalyzer(3)
    for _ in range(100):
        an.feed(loud, 0.01)
    lv, _ = an.feed(quiet, 0.01)
    assert lv[0] < 0.3                           # right after the drop: dim
    for _ in range(800):                         # 8 s at the 4 dB/s release
        lv, _ = an.feed(quiet, 0.01)
    assert lv[0] == pytest.approx(1.0)
    assert lv[1] == pytest.approx(0.625)


def test_auto_gain_never_amplifies_below_the_floor():
    an = music.BandAnalyzer(2)
    for _ in range(2000):
        lv, _ = an.feed([_p(-88), _p(-95)], 0.01)
    assert an.ref == music.REF_FLOOR_DB
    assert lv == [0.0, 0.0]                      # -88 dBFS hiss stays dark


def _kick_track(kicks, blocks=300, n=14):
    """Steady -30 dBFS on every band; a kick lifts the low six to -10 dBFS and
    decays 4 dB per 10 ms block."""
    out = []
    since = None
    for k in range(blocks):
        if k in kicks:
            since = 0
        db = [-30.0] * n
        if since is not None:
            low = max(-30.0, -10.0 - 4.0 * since)
            for b in range(6):
                db[b] = low
            since += 1
        out.append([_p(d) for d in db])
    return out


def test_every_kick_at_120_bpm_is_a_beat():
    kicks = {25, 75, 125, 175, 225, 275}
    an = music.BandAnalyzer()
    beats = [k for k, pw in enumerate(_kick_track(kicks)) if an.feed(pw, 0.01)[1]]
    assert beats == sorted(kicks)


def test_steady_or_slightly_noisy_music_has_no_beats():
    rng = random.Random(7)
    an = music.BandAnalyzer()
    for _ in range(500):
        db = [-30.0 + rng.uniform(-0.5, 0.5) for _ in range(14)]
        assert an.feed([_p(d) for d in db], 0.01)[1] is False


def test_beats_are_at_most_one_per_quarter_second():
    kicks = set(range(10, 300, 10))              # a kick every 100 ms
    an = music.BandAnalyzer()
    beats = [k for k, pw in enumerate(_kick_track(kicks)) if an.feed(pw, 0.01)[1]]
    assert beats and all(b - a >= 25 for a, b in zip(beats, beats[1:]))


def test_analyzer_cost_is_tiny():
    import time
    an = music.BandAnalyzer()
    track = _kick_track({25, 75}, blocks=100)
    t0 = time.perf_counter()
    for pw in track:
        an.feed(pw, 0.01)
    per_block = (time.perf_counter() - t0) / len(track)
    assert per_block < 0.001                     # 100 blocks/s -> < 10 % of a core worst case
