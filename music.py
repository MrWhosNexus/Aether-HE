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


# ------------------------------------------------------- keyboard layout ----
def grid_layout(pos, n_bands=N_BANDS):
    """{idx: (x_left, y)} -> {idx: (bands, row, n_rows)}.

    Rows are the distinct y values (top first); `row` counts from the BOTTOM
    (0 = space-bar row). Key widths are not in the keymap, so a key spans from
    its x to the next key's x in its row; the last key of a row ends at the
    board's right edge (largest x + the median key pitch). The board width is
    cut into n_bands equal columns; a key takes every column whose centre lies
    in its span (wide keys average several), else the column under its own
    centre."""
    if not pos:
        return {}
    ys = sorted({y for _, y in pos.values()})
    n_rows = len(ys)
    rows = {y: sorted((x, i) for i, (x, yy) in pos.items() if yy == y) for y in ys}
    gaps = sorted(b[0] - a[0] for r in rows.values() for a, b in zip(r, r[1:])
                  if b[0] > a[0])
    pitch = gaps[len(gaps) // 2] if gaps else 1.0
    x0 = min(x for x, _ in pos.values())
    x1 = max(x for x, _ in pos.values()) + pitch
    col_w = (x1 - x0) / n_bands
    centres = [x0 + (b + 0.5) * col_w for b in range(n_bands)]
    out = {}
    for rank, y in enumerate(ys):
        row = n_rows - 1 - rank
        keys = rows[y]
        for k, (x, idx) in enumerate(keys):
            end = keys[k + 1][0] if k + 1 < len(keys) else x1
            bands = tuple(b for b, c in enumerate(centres) if x <= c < end)
            if not bands:
                mid = (x + end) / 2.0
                bands = (max(0, min(n_bands - 1, int((mid - x0) / col_w))),)
            out[idx] = (bands, row, n_rows)
    return out


# ----------------------------------------------------------- availability ----
def availability(platform=None, find_spec=None):
    """(available, reason|None). Never imports numpy/soundcard (find_spec
    only), so it is safe on the UI thread."""
    platform = sys.platform if platform is None else platform
    find_spec = find_spec or importlib.util.find_spec
    if platform != "win32":
        return False, "Music visualizer needs Windows (WASAPI loopback capture)."
    missing = []
    for mod in ("numpy", "soundcard"):
        try:
            if find_spec(mod) is None:
                missing.append(mod)
        except (ImportError, ValueError):
            missing.append(mod)
    if missing:
        return False, ("Music visualizer needs the %s package%s (not installed)."
                       % (" and ".join(missing), "s" if len(missing) > 1 else ""))
    return True, None


# ------------------------------------------------- numpy / soundcard adapters ----
class NumpySpectrum:
    """Block -> band powers. Keeps the newest n_fft mono samples, Hann window,
    rfft, |X|^2 scaled so a full-scale sine's peak bin is 1 (0 dBFS), summed
    per band via a cumulative sum (vectorised band_powers)."""

    def __init__(self, n_fft, bins):
        import numpy as np          # lazy: only on the capture thread
        self._np = np
        self._n = n_fft
        win = np.hanning(n_fft)
        self._win = win
        self._k = (2.0 / float(win.sum())) ** 2
        self._buf = np.zeros(n_fft)
        self._lo = np.array([lo for lo, _, _ in bins])
        self._hi = np.array([hi for _, hi, _ in bins])
        self._w = np.array([w for _, _, w in bins])

    def __call__(self, block):
        np = self._np
        x = np.asarray(block, dtype=float).ravel()
        k = x.size
        if k >= self._n:
            self._buf[:] = x[-self._n:]
        elif k:
            self._buf[:-k] = self._buf[k:]
            self._buf[-k:] = x
        spec = np.fft.rfft(self._buf * self._win)
        p = (spec.real * spec.real + spec.imag * spec.imag) * self._k
        c = np.concatenate(([0.0], np.cumsum(p)))
        return ((c[self._hi] - c[self._lo]) * self._w).tolist()


class SoundcardBackend:
    """WASAPI loopback of the default output through `soundcard`. Every call
    happens on the capture thread: COM is initialised per thread (MTA) here,
    and soundcard is imported here, never on the UI thread."""

    def __init__(self):
        self._sc = None
        self._com = False

    def enter(self):
        # Import FIRST. soundcard's import runs CoInitializeEx(MTA) on the
        # importing thread and treats S_FALSE ("already initialised") as a
        # fatal "Error 0x100000001", so initialising COM ourselves before the
        # first import broke every capture. Later capture threads (the module
        # is cached) still need their own COM init, which is ours below.
        self._sc = self._import()
        self._com = self._co_init()

    @staticmethod
    def _import():
        import soundcard
        return soundcard

    @staticmethod
    def _co_init():
        if sys.platform != "win32":
            return False
        import ctypes
        hr = ctypes.windll.ole32.CoInitializeEx(None, 0)       # COINIT_MULTITHREADED
        return hr in (0, 1)                                    # S_OK / S_FALSE: balance it

    def leave(self):
        if self._com:
            import ctypes
            ctypes.windll.ole32.CoUninitialize()
            self._com = False

    def default_device(self):
        spk = self._sc.default_speaker()
        return (str(spk.id), str(spk.name)) if spk is not None else None

    def open(self, dev_id, rate, frames):
        mic = self._sc.get_microphone(dev_id, include_loopback=True)
        rec = mic.recorder(samplerate=rate, blocksize=frames)
        rec.__enter__()
        return _SoundcardStream(rec, frames)


class _SoundcardStream:
    def __init__(self, rec, frames):
        self._rec = rec
        self._frames = frames

    def read(self):
        data = self._rec.record(numframes=self._frames)
        return data.mean(axis=1) if getattr(data, "ndim", 1) == 2 else data

    def close(self):
        self._rec.__exit__(None, None, None)


# ----------------------------------------------------------- the source ----
MusicSnapshot = namedtuple("MusicSnapshot", "levels beat_seq live")
ZERO_LEVELS = (0.0,) * N_BANDS


class MusicSource:
    """Owns the capture thread. start()/stop() are idempotent and thread-safe;
    snapshot() is lock-free (one tuple read) for the engine; status() feeds
    the music_status bridge. The thread runs only between start() and stop()."""

    def __init__(self, backend_factory=None, spectrum_factory=None,
                 clock=time.monotonic, available=None):
        self._backend_factory = backend_factory or SoundcardBackend
        self._spectrum_factory = spectrum_factory or NumpySpectrum
        self._clock = clock
        self._avail = available
        self._life = threading.Lock()
        self._thread = None
        self._ev = threading.Event()
        self._ev.set()
        self._pub = (ZERO_LEVELS, 0, -1e9)    # (levels, beat_seq, published at)
        self._beats = 0
        self._state = "off"
        self._device = None
        self._error = None

    def availability(self):
        return self._avail if self._avail is not None else availability()

    def running(self):
        th = self._thread
        return th is not None and th.is_alive()

    def start(self):
        with self._life:
            if self.running() and not self._ev.is_set():
                return
            ok, _ = self.availability()
            if not ok:
                self._state = "unavailable"
                return
            ev = threading.Event()
            self._ev = ev
            self._state, self._device, self._error = "starting", None, None
            th = threading.Thread(target=self._loop, args=(ev,),
                                  name="aether-music", daemon=True)
            self._thread = th
            th.start()

    def stop(self):
        with self._life:
            self._ev.set()
            th, self._thread = self._thread, None
            self._state, self._device = "off", None
            self._pub = (ZERO_LEVELS, self._beats, -1e9)
        if th is not None and th is not threading.current_thread():
            th.join(timeout=0.5)

    def snapshot(self):
        levels, seq, at = self._pub
        live = self._state == "listening"
        if not live or self._clock() - at > STALE_S:
            levels = ZERO_LEVELS
        return MusicSnapshot(levels, seq, live)

    def status(self):
        ok, reason = self.availability()
        state = self._state if ok else "unavailable"
        if state == "no_device":
            reason = MSG_NO_DEVICE
        elif state == "error":
            reason = "Audio capture failed: %s" % (self._error or "unknown error")
        return {"available": bool(ok), "reason": reason, "state": state,
                "device": self._device if state == "listening" else None}

    # -- capture thread --
    def _set(self, ev, state, device=None, error=None):
        with self._life:
            if ev is self._ev and not ev.is_set():
                self._state, self._device, self._error = state, device, error

    def _default(self, backend):
        try:
            return backend.default_device()
        except Exception:
            return None

    def _loop(self, ev):
        try:
            backend = self._backend_factory()
            backend.enter()
        except Exception as e:
            log.warning("music capture unavailable: %s", e)
            self._set(ev, "error", error=str(e))
            return
        try:
            bins = band_bins(N_FFT, RATE, band_edges())
            while not ev.is_set():
                dev = self._default(backend)
                if dev is None:
                    self._set(ev, "no_device")
                    ev.wait(RETRY_S)
                    continue
                dev_id, dev_name = dev
                try:
                    stream = backend.open(dev_id, RATE, HOP)
                except Exception as e:
                    log.warning("audio loopback open failed (%s): %s", dev_name, e)
                    self._set(ev, "no_device")
                    ev.wait(RETRY_S)
                    continue
                try:
                    self._capture(ev, backend, stream, dev, bins)
                except Exception as e:
                    log.warning("music capture stopped: %s", e)
                    self._set(ev, "no_device")
                    ev.wait(RETRY_S)
                finally:
                    try:
                        stream.close()
                    except Exception:
                        pass
        finally:
            try:
                backend.leave()
            except Exception:
                pass

    def _capture(self, ev, backend, stream, dev, bins):
        spectrum = self._spectrum_factory(N_FFT, bins)
        an = BandAnalyzer(len(bins))
        self._set(ev, "listening", dev[1])
        next_check = self._clock() + DEVICE_CHECK_S
        while not ev.is_set():
            block = stream.read()
            n = len(block)
            if n:
                levels, beat = an.feed(spectrum(block), n / float(RATE))
                if beat:
                    self._beats += 1
                if not ev.is_set():
                    self._pub = (tuple(levels), self._beats, self._clock())
            else:
                ev.wait(0.005)          # nothing captured: do not spin
            now = self._clock()
            if now >= next_check:
                next_check = now + DEVICE_CHECK_S
                cur = self._default(backend)
                if cur is None or cur[0] != dev[0]:
                    log.info("default audio output changed; re-acquiring")
                    return
