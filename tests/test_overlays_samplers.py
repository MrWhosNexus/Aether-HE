"""Phase 6 / Task 3: CPU / RAM / GPU samplers. The GPU probe only ever runs an
INJECTED runner here: no test starts nvidia-smi or any other process."""
import sys
import time

import pytest

import overlays

ROWS = {"cpu": [0], "ram": [1], "gpu": [2], "pomodoro": [3]}


@pytest.fixture(autouse=True)
def _never_spawn_nvidia_smi(monkeypatch):
    def boom(exe):
        raise AssertionError("a test tried to run the real nvidia-smi")
    monkeypatch.setattr(overlays, "_run_nvidia_smi", boom)


def test_cpu_load_from_two_counter_samples():
    assert overlays.cpu_load((100, 1000), (150, 1200)) == pytest.approx(0.75)   # 50 idle of 200
    assert overlays.cpu_load((100, 1000), (300, 1200)) == 0.0                   # all idle
    assert overlays.cpu_load((100, 1000), (100, 1100)) == 1.0                   # no idle
    for prev, cur in ((None, (1, 2)), ((1, 2), None), ((5, 10), (5, 10)), ((5, 10), (4, 9))):
        assert overlays.cpu_load(prev, cur) is None                              # first sample / no time passed


def test_proc_stat_parser():
    text = "cpu  100 5 50 800 20 3 2 0 0 0\ncpu0 1 1 1 1 1 1 1 1\nintr 5\n"
    assert overlays.parse_proc_stat(text) == (820, 980)          # idle + iowait, sum of first 8
    assert overlays.parse_proc_stat("") is None
    assert overlays.parse_proc_stat("cpu  a b c d") is None
    assert overlays.parse_proc_stat("cpu 1 2") is None


def test_meminfo_parser():
    text = "MemTotal:       16000000 kB\nMemFree: 1 kB\nMemAvailable:    4000000 kB\n"
    assert overlays.parse_meminfo(text) == pytest.approx(0.75)
    assert overlays.parse_meminfo("MemTotal: 5 kB") is None
    assert overlays.parse_meminfo("") is None


def test_gpu_output_parser_takes_the_busiest_gpu():
    assert overlays.parse_gpu_output("37\n") == pytest.approx(0.37)
    assert overlays.parse_gpu_output("12\n80\n") == pytest.approx(0.8)
    assert overlays.parse_gpu_output("[N/A]\n 5 \n") == pytest.approx(0.05)
    assert overlays.parse_gpu_output("250") == 1.0
    for junk in ("", "N/A", "No devices were found", None):
        assert overlays.parse_gpu_output(junk) is None


def test_gpu_probe_is_located_once_and_hidden_without_nvidia_smi():
    calls = []
    probe = overlays.GpuProbe(which=lambda n: calls.append(n) or None, runner=lambda e: "50")
    assert calls == ["nvidia-smi"]
    assert not probe.available and probe.read() is None
    assert "not found" in probe.reason and calls == ["nvidia-smi"]       # never looked again


def test_gpu_probe_reads_through_the_injected_runner():
    seen = []
    probe = overlays.GpuProbe(which=lambda n: "C:/x/nvidia-smi.exe",
                              runner=lambda exe: seen.append(exe) or "42\n")
    assert probe.available and probe.reason is None
    assert probe.read() == pytest.approx(0.42) and seen == ["C:/x/nvidia-smi.exe"]


def test_gpu_probe_gives_up_after_three_failures_in_a_row():
    answers = iter(["", "oops", "7", "", "", ""])
    probe = overlays.GpuProbe(which=lambda n: "x", runner=lambda e: next(answers))
    assert probe.read() is None and probe.read() is None
    assert probe.read() == pytest.approx(0.07)                  # a good read resets the count
    assert probe.read() is None and probe.read() is None and probe.available
    assert probe.read() is None
    assert not probe.available and probe.reason == "nvidia-smi is not answering"


def test_gpu_probe_survives_a_runner_that_raises():
    def runner(exe):
        raise OSError("gone")
    probe = overlays.GpuProbe(which=lambda n: "x", runner=runner)
    assert probe.read() is None


def test_nvidia_smi_is_started_without_a_console_window_and_with_a_timeout(monkeypatch):
    got = {}

    class R:
        returncode, stdout = 0, "9\n"

    def fake_run(cmd, **kw):
        got["cmd"], got["kw"] = cmd, kw
        return R()
    monkeypatch.undo()                                          # restore the real _run_nvidia_smi
    monkeypatch.setattr(overlays.subprocess, "run", fake_run)
    assert overlays._run_nvidia_smi("smi") == "9\n"
    assert got["cmd"] == ["smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"]
    assert got["kw"]["timeout"] == overlays.GPU_TIMEOUT_S == 1.5
    assert got["kw"]["creationflags"] == getattr(overlays.subprocess, "CREATE_NO_WINDOW", 0)
    assert got["kw"]["capture_output"] is True


def _sampler(layer, cpu=None, mem=None, gpu=None, gate=None):
    return overlays.Sampler(layer, cpu=cpu or (lambda: None), mem=mem or (lambda: None),
                            gpu=gpu, gate=gate, interval=0.01)


def test_sampler_reads_only_the_enabled_sensors():
    lay = overlays.OverlayLayer(ROWS, [0, 1, 2, 3])
    reads = []
    s = _sampler(lay, cpu=lambda: reads.append("cpu") or (0, 1), mem=lambda: reads.append("ram") or 0.4,
                 gpu=type("G", (), {"read": lambda self: reads.append("gpu") or 0.2})())
    s.sample_once()
    assert reads == []                                          # nothing enabled: nothing read
    lay.set_enabled("ram", True)
    s.sample_once()
    assert reads == ["ram"] and lay.value("ram") == 0.4


def test_sampler_cpu_needs_two_samples_and_forgets_when_switched_off():
    lay = overlays.OverlayLayer(ROWS, [0, 1, 2, 3])
    seq = iter([(0, 100), (50, 200), (60, 300), (0, 1000)])
    s = _sampler(lay, cpu=lambda: next(seq))
    lay.set_enabled("cpu", True)
    s.sample_once()
    assert lay.value("cpu") is None                             # first sample: no delta yet
    s.sample_once()
    assert lay.value("cpu") == pytest.approx(0.5)               # 50 idle of 100
    lay.set_enabled("cpu", False)
    s.sample_once()
    lay.set_enabled("cpu", True)
    s.sample_once()                                             # fresh start: not a delta against a stale sample
    assert lay.value("cpu") is None


def test_sampler_gate_skips_the_whole_tick():
    lay = overlays.OverlayLayer(ROWS, [0, 1, 2, 3])
    lay.set_enabled("ram", True)
    open_ = {"v": False}
    s = _sampler(lay, mem=lambda: 0.9, gate=lambda: open_["v"])
    s.sample_once()
    assert lay.value("ram") is None
    open_["v"] = True
    s.sample_once()
    assert lay.value("ram") == 0.9


def test_sampler_thread_starts_ticks_and_stops():
    lay = overlays.OverlayLayer(ROWS, [0, 1, 2, 3])
    lay.set_enabled("ram", True)
    s = _sampler(lay, mem=lambda: 0.25)
    assert not s.running
    s.start()
    s.start()                                                   # second start is a no-op
    deadline = time.time() + 2
    while lay.value("ram") is None and time.time() < deadline:
        time.sleep(0.01)
    assert s.running and lay.value("ram") == 0.25
    s.stop()
    assert not s.running
    s.stop()                                                    # idempotent


def test_sampler_thread_survives_a_reader_that_raises():
    lay = overlays.OverlayLayer(ROWS, [0, 1, 2, 3])
    lay.set_enabled("ram", True)
    n = {"c": 0}

    def mem():
        n["c"] += 1
        if n["c"] == 1:
            raise RuntimeError("boom")
        return 0.5
    s = _sampler(lay, mem=mem)
    s.start()
    deadline = time.time() + 2
    while lay.value("ram") is None and time.time() < deadline:
        time.sleep(0.01)
    s.stop()
    assert lay.value("ram") == 0.5


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows kernel32 readers")
def test_windows_readers_answer_in_range_without_psutil():
    a = overlays.read_cpu_counters()
    assert a is not None and a[1] > a[0] >= 0
    time.sleep(0.05)
    b = overlays.read_cpu_counters()
    load = overlays.cpu_load(a, b)
    assert load is None or 0.0 <= load <= 1.0
    mem = overlays.read_memory_load()
    assert mem is not None and 0.0 < mem <= 1.0
    assert "psutil" not in sys.modules


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="/proc readers")
def test_linux_readers_answer_from_proc():
    assert overlays.read_cpu_counters() is not None
    assert 0.0 < overlays.read_memory_load() <= 1.0
