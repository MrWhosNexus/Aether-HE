"""Phase 7: MusicSource capture-thread lifecycle with a fake loopback backend
and a fake spectrum. Never opens a real audio device, never imports numpy or
soundcard (the numpy-only adapter tests at the bottom skip without numpy)."""
import threading
import time

import pytest

import music

LOUD3 = [1e-4] * 14
LOUD3[3] = 1e-1          # band 3 is 30 dB above the rest


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    monkeypatch.setattr(music, "RETRY_S", 0.02)
    monkeypatch.setattr(music, "DEVICE_CHECK_S", 0.02)


class FakeStream:
    def __init__(self, backend, dev_id):
        self.backend, self.dev_id, self.closed = backend, dev_id, False

    def read(self):
        time.sleep(0.005)
        if self.backend.fail_reads:
            self.backend.fail_reads -= 1
            raise OSError("device unplugged")
        return [0.0] * music.HOP

    def close(self):
        self.closed = True


class FakeBackend:
    def __init__(self, devices=(("spk-a", "Speakers A"),)):
        self.devices = list(devices)       # default_device() pops until one left
        self.opened, self.streams = [], []
        self.entered = self.left = 0
        self.fail_reads = 0
        self.fail_enter = None

    def enter(self):
        if self.fail_enter:
            raise self.fail_enter
        self.entered += 1

    def leave(self):
        self.left += 1

    def default_device(self):
        if not self.devices:
            return None
        return self.devices[0]

    def open(self, dev_id, rate, frames):
        assert (rate, frames) == (music.RATE, music.HOP)
        self.opened.append(dev_id)
        s = FakeStream(self, dev_id)
        self.streams.append(s)
        return s


def _spectrum(powers=LOUD3):
    def factory(n_fft, bins):
        assert n_fft == music.N_FFT and len(bins) == 14
        return lambda block: list(powers)
    return factory


def _source(backend, powers=LOUD3, available=(True, None)):
    return music.MusicSource(backend_factory=lambda: backend,
                             spectrum_factory=_spectrum(powers),
                             available=available)


def _wait(pred, secs=2.0):
    end = time.time() + secs
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.005)
    return False


def test_start_listens_to_the_default_output_and_stop_releases_it():
    be = FakeBackend()
    src = _source(be)
    src.start()
    assert _wait(lambda: src.status()["state"] == "listening")
    assert src.status() == {"available": True, "reason": None,
                            "state": "listening", "device": "Speakers A"}
    assert _wait(lambda: src.snapshot().levels[3] == 1.0)
    snap = src.snapshot()
    assert snap.live is True and max(snap.levels[:3]) < 0.5
    src.stop()
    assert not src.running()
    assert be.streams[0].closed and be.left == 1
    assert src.status()["state"] == "off"
    assert src.snapshot() == music.MusicSnapshot(music.ZERO_LEVELS, src.snapshot().beat_seq, False)


def test_start_is_idempotent_and_stop_is_safe_twice():
    be = FakeBackend()
    src = _source(be)
    src.stop()                                    # never started
    src.start()
    src.start()
    assert _wait(lambda: src.status()["state"] == "listening")
    time.sleep(0.05)
    assert be.opened == ["spk-a"]
    src.stop()
    src.stop()
    assert not src.running()


def test_missing_dependencies_mean_no_thread_and_a_reason():
    be = FakeBackend()
    src = _source(be, available=(False, "Music visualizer needs the numpy package (not installed)."))
    src.start()
    assert not src.running() and be.entered == 0 and be.opened == []
    st = src.status()
    assert st["available"] is False and st["state"] == "unavailable"
    assert st["reason"] == "Music visualizer needs the numpy package (not installed)."
    assert src.snapshot().live is False


def test_no_output_device_is_reported_and_picked_up_when_one_appears():
    be = FakeBackend(devices=())
    src = _source(be)
    src.start()
    assert _wait(lambda: src.status()["state"] == "no_device")
    assert src.status()["reason"] == "No audio output device found."
    assert src.snapshot().live is False
    be.devices.append(("spk-b", "Headphones"))
    assert _wait(lambda: src.status()["state"] == "listening")
    assert src.status()["device"] == "Headphones"
    src.stop()


def test_a_changed_default_output_is_re_acquired():
    be = FakeBackend()
    src = _source(be)
    src.start()
    assert _wait(lambda: be.opened == ["spk-a"])
    be.devices.insert(0, ("spk-b", "USB DAC"))
    assert _wait(lambda: be.opened == ["spk-a", "spk-b"])
    assert be.streams[0].closed
    assert _wait(lambda: src.status()["device"] == "USB DAC")
    src.stop()


def test_a_read_error_closes_the_stream_and_retries():
    be = FakeBackend()
    be.fail_reads = 1
    src = _source(be)
    src.start()
    assert _wait(lambda: len(be.opened) >= 2)
    assert be.streams[0].closed
    assert _wait(lambda: src.status()["state"] == "listening")
    src.stop()


def test_a_failing_backend_reports_an_error_and_never_raises():
    be = FakeBackend()
    be.fail_enter = ImportError("No module named 'soundcard'")
    src = _source(be)
    src.start()
    assert _wait(lambda: not src.running())
    st = src.status()
    assert st["state"] == "error"
    assert st["reason"] == "Audio capture failed: No module named 'soundcard'"


def test_snapshot_goes_dark_when_capture_stalls():
    now = [100.0]
    src = music.MusicSource(backend_factory=FakeBackend, spectrum_factory=_spectrum(),
                            clock=lambda: now[0], available=(True, None))
    src._state = "listening"
    src._pub = ((0.5,) * 14, 3, 100.0)
    assert src.snapshot() == music.MusicSnapshot((0.5,) * 14, 3, True)
    now[0] = 100.0 + music.STALE_S + 0.01
    assert src.snapshot() == music.MusicSnapshot(music.ZERO_LEVELS, 3, True)


def test_beats_advance_the_sequence_number():
    seq = {"k": 0}
    quiet, kick = [1e-3] * 14, [1e-1] * 6 + [1e-3] * 8

    def factory(n_fft, bins):
        def spec(block):
            seq["k"] += 1
            return list(kick if seq["k"] % 40 == 0 else quiet)
        return spec
    src = music.MusicSource(backend_factory=FakeBackend, spectrum_factory=factory,
                            available=(True, None))
    src.start()
    assert _wait(lambda: src.snapshot().beat_seq >= 2, secs=3.0)
    src.stop()


def test_stop_returns_promptly_and_the_thread_ends():
    be = FakeBackend()
    src = _source(be)
    src.start()
    assert _wait(lambda: src.status()["state"] == "listening")
    th = src._thread
    t0 = time.perf_counter()
    src.stop()
    assert time.perf_counter() - t0 < 0.5
    assert _wait(lambda: not th.is_alive())
    assert not any(t.name == "aether-music" and t.is_alive() for t in threading.enumerate())


# --------------------------------------------- numpy adapter (skips without numpy) ----
def test_numpy_spectrum_matches_the_pure_band_powers():
    np = pytest.importorskip("numpy")
    bins = music.band_bins(music.N_FFT, music.RATE, music.band_edges())
    spec = music.NumpySpectrum(music.N_FFT, bins)
    rng = np.random.default_rng(1)
    x = rng.uniform(-0.5, 0.5, music.N_FFT)
    got = spec(x)
    w = np.hanning(music.N_FFT)
    X = np.fft.rfft(x * w)
    power = ((X.real ** 2 + X.imag ** 2) * (2.0 / w.sum()) ** 2).tolist()
    assert got == pytest.approx(music.band_powers(power, bins), rel=1e-9)


def test_numpy_spectrum_puts_a_1_khz_tone_in_its_band():
    np = pytest.importorskip("numpy")
    bins = music.band_bins(music.N_FFT, music.RATE, music.band_edges())
    spec = music.NumpySpectrum(music.N_FFT, bins)
    t = np.arange(music.N_FFT) / music.RATE
    got = spec(np.sin(2 * np.pi * 1000.0 * t))
    peak = max(range(14), key=lambda b: got[b])
    assert peak == 7                                   # 800-1227 Hz
    assert -3.0 < 10 * np.log10(got[7]) < 3.0          # full scale ~ 0 dBFS
    assert all(got[b] < got[7] * 1e-2 for b in range(14) if b != 7)


def test_numpy_spectrum_keeps_the_newest_window_across_blocks():
    np = pytest.importorskip("numpy")
    bins = music.band_bins(music.N_FFT, music.RATE, music.band_edges())
    a = music.NumpySpectrum(music.N_FFT, bins)
    b = music.NumpySpectrum(music.N_FFT, bins)
    x = np.random.default_rng(2).uniform(-1, 1, 3 * music.HOP)
    for k in range(3):
        last = a(x[k * music.HOP:(k + 1) * music.HOP])
    assert last == pytest.approx(b(x[-music.N_FFT:]))      # 1440 samples fed, last 1024 kept
