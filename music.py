"""Phase 7 music visualizer: system audio -> 14 band levels + beats.

Pipeline (all on one capture thread, only while the "music" effect runs):
  WASAPI loopback of the default output (soundcard) -> 480-frame blocks at
  48 kHz -> 1024-point Hann FFT (numpy) -> 14 log-spaced band powers
  (40 Hz-16 kHz) -> BandAnalyzer (dB, auto-gain, energy-flux beats) ->
  an immutable snapshot the effect engine reads lock-free each frame.

The DSP and keyboard-mapping maths are pure functions over plain sequences so
they are testable without numpy or soundcard. Both packages are imported
lazily, inside the capture thread only, and only on Windows; without them the
effect reports itself unavailable. PRIVACY: audio is processed in memory only,
block by block; nothing is recorded, stored or sent anywhere.
"""
import importlib.util
import logging
import math
import sys
import threading
import time
from collections import namedtuple

log = logging.getLogger("aether.music")

N_BANDS = 14
F_LO, F_HI = 40.0, 16000.0
RATE = 48000                 # requested loopback rate (WASAPI converts)
HOP = 480                    # 10 ms capture blocks
N_FFT = 1024                 # 21.3 ms window, 46.9 Hz bins
RANGE_DB = 40.0              # dynamic range shown on the bars
REF_FLOOR_DB = -45.0         # auto-gain never amplifies past this (dBFS)
REF_RELEASE_DB_S = 4.0       # auto-gain reference falls this fast
EPS = 1e-12
BEAT_BANDS = 6               # energy flux over 40-520 Hz (kick/snare body)
BEAT_K = 1.5                 # threshold = mean + K * mean abs deviation
BEAT_MIN_FLUX_DB = 6.0
BEAT_MIN_INTERVAL_S = 0.25   # <= 240 BPM
BEAT_STATS_TAU_S = 1.0
STALE_S = 0.25               # snapshot older than this -> bars fall
DEVICE_CHECK_S = 1.0         # default-output change poll
RETRY_S = 2.0                # retry after no device / a failed open

MSG_NO_DEVICE = "No audio output device found."


# ------------------------------------------------------------ band maths ----
def band_edges(n=N_BANDS, lo=F_LO, hi=F_HI):
    """n + 1 geometric (log-spaced) band edges in Hz from lo to hi."""
    return [lo * (hi / lo) ** (k / n) for k in range(n + 1)]


def band_bins(n_fft, rate, edges):
    """[(lo, hi, weight)] per band: rfft bins lo..hi-1 whose centre frequency
    falls in [f_lo, f_hi). A band narrower than one bin gets the bin nearest
    its geometric centre. weight = band width / covered width, so a band's
    power is a density times its real bandwidth (single-bin bass bands are not
    over-counted)."""
    df = rate / float(n_fft)
    top = n_fft // 2
    out = []
    for f_lo, f_hi in zip(edges, edges[1:]):
        lo = max(1, min(top, int(math.ceil(f_lo / df))))
        hi = max(1, min(top + 1, int(math.ceil(f_hi / df))))
        if hi <= lo:
            lo = max(1, min(top, int(round(math.sqrt(f_lo * f_hi) / df))))
            hi = lo + 1
        out.append((lo, hi, (f_hi - f_lo) / (df * (hi - lo))))
    return out


def band_powers(power, bins):
    """Pure reference of what NumpySpectrum computes: weight * sum of the
    power spectrum over each band's bins."""
    return [w * sum(power[lo:hi]) for lo, hi, w in bins]


def _db(p):
    if not p > EPS:              # 0, negative, NaN, denormal hiss
        return 10.0 * math.log10(EPS)
    return 10.0 * math.log10(p)


class BandAnalyzer:
    """Band powers -> (levels 0..1, beat). Levels are dB under an auto-gain
    reference that jumps up to the loudest band instantly and falls
    REF_RELEASE_DB_S, never below REF_FLOOR_DB, showing RANGE_DB of range.
    A beat is a jump in the low-band energy flux (sum of dB rises over the
    BEAT_BANDS lowest bands) above an adaptive threshold (running mean +
    BEAT_K * mean absolute deviation, time constant BEAT_STATS_TAU_S), at
    least BEAT_MIN_FLUX_DB, at most one per BEAT_MIN_INTERVAL_S."""

    def __init__(self, n_bands=N_BANDS):
        self.n = n_bands
        self.ref = REF_FLOOR_DB
        self.prev = None
        self.mean = 0.0
        self.dev = 0.0
        self.since_beat = 1e9

    def feed(self, powers, dt):
        db = [_db(p) for p in powers]
        dt = max(0.0, float(dt))
        self.ref = max(REF_FLOOR_DB, max(db), self.ref - REF_RELEASE_DB_S * dt)
        lo = self.ref - RANGE_DB
        levels = [min(1.0, max(0.0, (d - lo) / RANGE_DB)) for d in db]
        # Flux on ABSOLUTE dB (not the auto-gained levels: a gain jump on the
        # first kick would hide it), clamped at the display floor so hiss and
        # silence never count.
        low = [max(d, lo) for d in db[:BEAT_BANDS]]
        prev = self.prev
        self.prev = low
        flux = 0.0
        if prev is not None:
            for d, q in zip(low, prev):
                if d > q:
                    flux += d - q
        self.since_beat += dt
        beat = (flux >= BEAT_MIN_FLUX_DB and flux > self.mean + BEAT_K * self.dev
                and self.since_beat >= BEAT_MIN_INTERVAL_S)
        if beat:
            self.since_beat = 0.0
        a = 1.0 - math.exp(-dt / BEAT_STATS_TAU_S) if dt > 0 else 0.0
        self.mean += a * (flux - self.mean)
        self.dev += a * (abs(flux - self.mean) - self.dev)
        return levels, beat
