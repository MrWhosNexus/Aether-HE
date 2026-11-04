"""Status on keys (roadmap Phase 6): CPU / RAM / GPU bars and a Pomodoro timer
painted over the live lighting frame, plus a generic flash(color, ms).

Everything here is host-side and stateless towards the keyboard: `OverlayLayer`
mutates the per-key frame the effect engine is about to stream (no HID, no
extra frame rate), `Sampler` reads system load once a second, and
`OverlayManager` ties them to per-profile toggles in settings.json. It never
sees a keystroke: the only inputs are CPU / memory / GPU load and the clock.
"""
import ctypes
import json
import math
import os
import shutil
import subprocess
import sys
import threading
import time
from collections import namedtuple

IDS = ("cpu", "ram", "gpu", "pomodoro")
LABELS = {"cpu": "CPU", "ram": "RAM", "gpu": "GPU", "pomodoro": "Pomodoro"}
ROW_NAMES = {"cpu": "number row", "ram": "QWERTY row", "gpu": "home row",
             "pomodoro": "shift row"}
# Design codes (device_state.DESIGN_CODES) of each overlay's keys, left to right.
ROW_CODES = {
    "cpu": ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"],
    "ram": ["Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P"],
    "gpu": ["A", "S", "D", "F", "G", "H", "J", "K", "L", "Semi"],
    "pomodoro": ["LShift", "Z", "X", "C", "V", "B", "N", "M", "Comma", "Dot",
                 "Slash", "RShift"],
}
SENSOR_IDS = ("cpu", "ram", "gpu")

TRACK = (14, 14, 22)                 # unlit part of a bar (near black, readable on any effect)
LOAD_STOPS = ((0.0, (0, 210, 80)), (0.65, (255, 170, 0)), (0.9, (255, 30, 30)))
RAM_STOPS = ((0.0, (0, 170, 255)), (0.75, (110, 80, 255)), (0.92, (255, 40, 120)))
POMO_WORK_RGB = (255, 80, 40)
POMO_BREAK_RGB = (0, 220, 120)
PHASE_FLASH_MS = 700
PHASE_FLASH_WINDOW_S = 1.5           # no pulse for a phase change older than this
FLASH_MIN_MS, FLASH_MAX_MS, FLASH_KEEP = 50, 5000, 8
RAINBOW = [(255, 0, 0), (255, 160, 0), (255, 255, 0), (0, 220, 0), (0, 120, 255), (160, 0, 255)]


# ---- colour + bar maths (pure) ----------------------------------------------
def unit(v):
    """float in [0, 1], or None for None / NaN / non-numbers."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:
        return None
    return min(1.0, max(0.0, f))


def mix(a, b, t):
    t = min(1.0, max(0.0, t))
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def ramp(stops, v):
    v = unit(v) or 0.0
    if v <= stops[0][0]:
        return stops[0][1]
    for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
        if v <= p1:
            return mix(c0, c1, (v - p0) / (p1 - p0))
    return stops[-1][1]


def color_for(oid, value):
    return ramp(RAM_STOPS if oid == "ram" else LOAD_STOPS, value)


def bar_levels(value, n):
    """Per-key fill 0..1 for an n-key bar: whole keys light fully, the key at
    the boundary lights partially, so ten keys give a smooth ten-step bar."""
    v = unit(value)
    if v is None:
        return [0.0] * n
    return [min(1.0, max(0.0, v * n - i)) for i in range(n)]


def paint_bar(frame, indices, value, color):
    for idx, lv in zip(indices, bar_levels(value, len(indices))):
        frame[idx] = mix(TRACK, color, lv)

# ---- Pomodoro ----------------------------------------------------------------
PomoState = namedtuple("PomoState", "phase remaining_s progress elapsed_s")


class Pomodoro:
    """Repeating work / break cycle (default 25 / 5 min), driven by the clock
    passed in: no thread. `start(now)` begins a cycle; `state(now)` is pure."""

    def __init__(self, work_s=1500.0, break_s=300.0):
        self.work_s = max(1.0, float(work_s))
        self.break_s = max(1.0, float(break_s))
        self._start = None

    @property
    def running(self):
        return self._start is not None

    def start(self, now):
        self._start = float(now)

    def stop(self):
        self._start = None

    def state(self, now):
        if self._start is None:
            return None
        cycle = self.work_s + self.break_s
        pos = max(0.0, float(now) - self._start) % cycle
        if pos < self.work_s:
            return PomoState("work", self.work_s - pos, pos / self.work_s, pos)
        el = pos - self.work_s
        return PomoState("break", self.break_s - el, el / self.break_s, el)


def phase_color(phase):
    return POMO_BREAK_RGB if phase == "break" else POMO_WORK_RGB


# ---- the compositing layer the effect engine calls -----------------------------
class OverlayLayer:
    """`apply(frame, now)` paints the enabled overlays and live flashes onto the
    engine's per-frame dict. Called on the engine thread; everything else
    (Api threads, the sampler) goes through the lock."""

    def __init__(self, rows, all_indices, pomodoro=None, clock=time.monotonic):
        self.rows = {k: list(v) for k, v in rows.items()}
        self.all = list(all_indices)
        self.pomodoro = pomodoro or Pomodoro()
        self._clock = clock
        self._lock = threading.Lock()
        self._on = {k: False for k in IDS}
        self._val = {k: None for k in SENSOR_IDS}
        self._flashes = []            # (rgb, start, ms)
        self._last_phase = None

    def set_enabled(self, oid, on, now=None):
        if oid not in self._on:
            return
        now = self._clock() if now is None else now
        on = bool(on)
        with self._lock:
            was, self._on[oid] = self._on[oid], on
            if oid == "pomodoro":
                if on and not was:
                    self.pomodoro.start(now)
                if not on:
                    self.pomodoro.stop()
                self._last_phase = None
            elif not on:
                self._val[oid] = None

    def enabled(self, oid):
        return self._on.get(oid, False)

    def any_enabled(self):
        return any(self._on.values())

    def set_value(self, oid, value):
        if oid in self._val:
            with self._lock:
                self._val[oid] = unit(value)

    def value(self, oid):
        return self._val.get(oid)

    def flash(self, rgb, ms, now=None):
        now = self._clock() if now is None else now
        rgb = tuple(min(255, max(0, int(c))) for c in rgb[:3])
        ms = min(FLASH_MAX_MS, max(FLASH_MIN_MS, int(ms)))
        with self._lock:
            self._add_flash(rgb, now, ms)

    def _add_flash(self, rgb, now, ms):
        self._flashes = (self._flashes + [(rgb, now, ms)])[-FLASH_KEEP:]

    def pomodoro_state(self, now=None):
        if not self._on["pomodoro"]:
            return None
        return self.pomodoro.state(self._clock() if now is None else now)

    def apply(self, frame, now=None):
        now = self._clock() if now is None else now
        with self._lock:
            on, vals = dict(self._on), dict(self._val)
            st = self.pomodoro.state(now) if on["pomodoro"] else None
            if st is not None:
                if (self._last_phase is not None and st.phase != self._last_phase
                        and st.elapsed_s < PHASE_FLASH_WINDOW_S):
                    self._add_flash(phase_color(st.phase), now, PHASE_FLASH_MS)
                self._last_phase = st.phase
            self._flashes = [f for f in self._flashes if now - f[1] < f[2] / 1000.0]
            flashes = list(self._flashes)
        for oid in SENSOR_IDS:
            if on[oid] and self.rows.get(oid):
                paint_bar(frame, self.rows[oid], vals[oid], color_for(oid, vals[oid]))
        if st is not None and self.rows.get("pomodoro"):
            paint_bar(frame, self.rows["pomodoro"], st.progress, phase_color(st.phase))
        for rgb, t0, ms in flashes:
            a = 1.0 - (now - t0) / (ms / 1000.0)
            for idx in self.all:
                frame[idx] = mix(frame.get(idx, (0, 0, 0)), rgb, a)

# ---- carrier: a host rendering of the firmware lighting the overlays sit on ----
def carrier_plan(src, indices, bright_max=4):
    """What the host engine should stream while overlays are on but the UI's
    lighting is a firmware mode (static / Full-RGB / per-key paint / off).
    `src` is what Api.set_light / set_custom_colors last saw:
      ("light", {fg, bg, brightness, speed, power_on, full_color, ...}),
      ("custom", {device index: rgb}, brightness) or None.
    Returns {"zones": [...], "bg": rgb, "base": {index: rgb}}."""
    black = {"zones": [], "bg": (0, 0, 0), "base": {}}
    if not src:
        return black
    scale = lambda v: min(1.0, max(0.0, float(v) / float(bright_max or 1)))
    if src[0] == "custom":
        s = scale(src[2])
        return {"zones": [], "bg": (0, 0, 0),
                "base": {int(i): mix((0, 0, 0), tuple(c[:3]), s) for i, c in src[1].items()}}
    p = src[1]
    if not p.get("power_on", True):
        return black
    s = scale(p.get("brightness", bright_max))
    if p.get("full_color"):
        zone = {"indices": list(indices), "mode": "wave", "palette": list(RAINBOW),
                "bg": (0, 0, 0), "speed": 0.5, "bright": s, "direction": 0}
        return {"zones": [zone], "bg": (0, 0, 0), "base": {}}
    fg = mix((0, 0, 0), tuple(p["fg"][:3]), s)
    return {"zones": [], "bg": mix((0, 0, 0), tuple(p.get("bg", (0, 0, 0))[:3]), s),
            "base": {int(i): fg for i in indices}}


# ---- samplers ----------------------------------------------------------------
class _FILETIME(ctypes.Structure):
    _fields_ = [("lo", ctypes.c_uint32), ("hi", ctypes.c_uint32)]


class _MEMSTATUS(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_uint32), ("dwMemoryLoad", ctypes.c_uint32),
                ("ullTotalPhys", ctypes.c_uint64), ("ullAvailPhys", ctypes.c_uint64),
                ("ullTotalPageFile", ctypes.c_uint64), ("ullAvailPageFile", ctypes.c_uint64),
                ("ullTotalVirtual", ctypes.c_uint64), ("ullAvailVirtual", ctypes.c_uint64),
                ("ullAvailExtendedVirtual", ctypes.c_uint64)]


def _read_text(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def parse_proc_stat(text):
    """First 'cpu' line of /proc/stat -> (idle, total) jiffies, or None."""
    for line in (text or "").splitlines():
        parts = line.split()
        if parts and parts[0] == "cpu":
            try:
                nums = [int(x) for x in parts[1:9]]
            except ValueError:
                return None
            if len(nums) < 4:
                return None
            return (nums[3] + (nums[4] if len(nums) > 4 else 0), sum(nums))
    return None


def parse_meminfo(text):
    """/proc/meminfo -> used fraction 0..1, or None."""
    vals = {}
    for line in (text or "").splitlines():
        k, _, rest = line.partition(":")
        bits = rest.split()
        if bits and bits[0].isdigit():
            vals[k.strip()] = int(bits[0])
    total, avail = vals.get("MemTotal"), vals.get("MemAvailable")
    if not total or avail is None:
        return None
    return unit(1.0 - avail / total)


def cpu_load(prev, cur):
    """Load 0..1 between two (idle, total) counter samples, or None."""
    if not prev or not cur:
        return None
    dt = cur[1] - prev[1]
    if dt <= 0:
        return None
    return unit(1.0 - (cur[0] - prev[0]) / dt)


def read_cpu_counters():
    """(idle, total) system CPU counters: GetSystemTimes on Windows, /proc/stat
    on Linux, None elsewhere or on any failure."""
    try:
        if sys.platform.startswith("win"):
            idle, kern, user = _FILETIME(), _FILETIME(), _FILETIME()
            if not ctypes.windll.kernel32.GetSystemTimes(
                    ctypes.byref(idle), ctypes.byref(kern), ctypes.byref(user)):
                return None
            ft = lambda f: (f.hi << 32) | f.lo
            return (ft(idle), ft(kern) + ft(user))   # kernel time includes idle
        if sys.platform.startswith("linux"):
            return parse_proc_stat(_read_text("/proc/stat"))
    except Exception:
        pass
    return None


def read_memory_load():
    """Physical memory in use 0..1: GlobalMemoryStatusEx / /proc/meminfo, else None."""
    try:
        if sys.platform.startswith("win"):
            m = _MEMSTATUS()
            m.dwLength = ctypes.sizeof(m)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
                return None
            return unit(m.dwMemoryLoad / 100.0)
        if sys.platform.startswith("linux"):
            return parse_meminfo(_read_text("/proc/meminfo"))
    except Exception:
        pass
    return None


NVIDIA_SMI_ARGS = ("--query-gpu=utilization.gpu", "--format=csv,noheader,nounits")
GPU_TIMEOUT_S = 1.5


def parse_gpu_output(text):
    """nvidia-smi csv (one utilization % per GPU) -> busiest GPU 0..1, or None."""
    vals = []
    for line in (text or "").splitlines():
        try:
            vals.append(float(line.strip()))
        except ValueError:
            continue
    return unit(max(vals) / 100.0) if vals else None


def _run_nvidia_smi(exe):
    res = subprocess.run([exe, *NVIDIA_SMI_ARGS], capture_output=True, text=True,
                         timeout=GPU_TIMEOUT_S,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return res.stdout if res.returncode == 0 else ""


class GpuProbe:
    """nvidia-smi, located ONCE with `which`; `runner(exe) -> csv text` is
    injectable (tests never start a process). Three failed reads in a row
    switch it off for the session."""
    MAX_FAILS = 3

    def __init__(self, which=shutil.which, runner=None):
        self._exe = which("nvidia-smi")
        self._runner = runner or _run_nvidia_smi
        self._fails = 0

    @property
    def available(self):
        return bool(self._exe) and self._fails < self.MAX_FAILS

    @property
    def reason(self):
        if not self._exe:
            return "nvidia-smi not found (NVIDIA GPU only)"
        if self._fails >= self.MAX_FAILS:
            return "nvidia-smi is not answering"
        return None

    def read(self):
        if not self.available:
            return None
        try:
            v = parse_gpu_output(self._runner(self._exe))
        except Exception:
            v = None
        self._fails = 0 if v is not None else self._fails + 1
        return v


class Sampler:
    """One-second sampling of the ENABLED sensors into the layer. `gate()`
    (e.g. "the keyboard is open") skips a tick entirely, so nothing is read
    and no process starts while there is nothing to draw on."""

    def __init__(self, layer, cpu=None, mem=None, gpu=None, gate=None, interval=1.0):
        self.layer = layer
        self._cpu = cpu if cpu is not None else read_cpu_counters
        self._mem = mem if mem is not None else read_memory_load
        self._gpu = gpu
        self._gate = gate
        self._interval = float(interval)
        self._prev_cpu = None
        self._stop = threading.Event()
        self._stop.set()
        self._thread = None

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive() and not self._stop.is_set()

    def sample_once(self):
        if self._gate is not None and not self._gate():
            return
        lay = self.layer
        if lay.enabled("cpu"):
            cur = self._cpu()
            lay.set_value("cpu", cpu_load(self._prev_cpu, cur))
            self._prev_cpu = cur
        else:
            self._prev_cpu = None
        if lay.enabled("ram"):
            lay.set_value("ram", self._mem())
        if lay.enabled("gpu") and self._gpu is not None:
            lay.set_value("gpu", self._gpu.read())

    def start(self):
        if self.running:
            return
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(self._stop,), daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        th = self._thread
        if th is not None and th is not threading.current_thread():
            th.join(timeout=2.0)
        self._thread = None

    def _run(self, stop_ev):
        while not stop_ev.is_set():
            t0 = time.monotonic()
            try:
                self.sample_once()
            except Exception:
                pass
            stop_ev.wait(max(0.01, self._interval - (time.monotonic() - t0)))

# ---- per-profile preferences (settings.json top-level key "overlays") ---------
PREFS_KEY = "overlays"
MAX_PROFILE_ID = 64


def _read_settings(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def load_prefs(path):
    """{"profiles": {profile id: {overlay id: bool}}, "pomodoro": {...}} with
    anything malformed dropped. The key is Aether-owned: the UI's own settings
    saves merge around it (Api.save_settings keeps unknown top-level keys)."""
    raw = _read_settings(path).get(PREFS_KEY)
    out = {"profiles": {}, "pomodoro": {}}
    if not isinstance(raw, dict):
        return out
    profs = raw.get("profiles")
    if isinstance(profs, dict):
        for pid, tog in profs.items():
            if isinstance(pid, str) and 0 < len(pid) <= MAX_PROFILE_ID and isinstance(tog, dict):
                out["profiles"][pid] = {k: bool(tog.get(k)) for k in IDS}
    pomo = raw.get("pomodoro")
    if isinstance(pomo, dict):
        out["pomodoro"] = {k: pomo[k] for k in ("workMin", "breakMin")
                           if isinstance(pomo.get(k), (int, float)) and not isinstance(pomo.get(k), bool)}
    return out


def toggles_for(prefs, pid):
    return dict({k: False for k in IDS}, **(prefs.get("profiles", {}).get(pid) or {}))


def pomodoro_seconds(prefs):
    """(work_s, break_s): settings workMin / breakMin clamped to 1..180 / 1..60, default 25 / 5."""
    p = prefs.get("pomodoro") or {}
    work = min(180.0, max(1.0, float(p.get("workMin", 25))))
    brk = min(60.0, max(1.0, float(p.get("breakMin", 5))))
    return work * 60.0, brk * 60.0


def save_toggle(path, lock, pid, oid, on):
    """Read-modify-write ONE toggle of one profile; every other settings key is kept."""
    with lock:
        data = _read_settings(path)
        block = data.get(PREFS_KEY) if isinstance(data.get(PREFS_KEY), dict) else {}
        profs = block.get("profiles") if isinstance(block.get("profiles"), dict) else {}
        tog = profs.get(pid) if isinstance(profs.get(pid), dict) else {}
        tog[oid] = bool(on)
        profs[pid] = tog
        block["profiles"] = profs
        data[PREFS_KEY] = block
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)


# ---- manager -------------------------------------------------------------------
class OverlayManager:
    """Toggles (per profile, persisted), availability, the sampler lifecycle and
    the get_overlays payload."""

    def __init__(self, rows, all_indices, settings_path, lock, cpu=None, mem=None,
                 gpu=None, gate=None, clock=time.monotonic, interval=1.0):
        self._path, self._lock = settings_path, lock
        work, brk = pomodoro_seconds(load_prefs(settings_path))
        self.layer = OverlayLayer(rows, all_indices, Pomodoro(work, brk), clock)
        self.gpu = gpu if gpu is not None else GpuProbe()
        cpu = cpu if cpu is not None else read_cpu_counters
        mem = mem if mem is not None else read_memory_load
        self._sensor_ok = {"cpu": cpu() is not None, "ram": mem() is not None}
        self.sampler = Sampler(self.layer, cpu, mem, self.gpu, gate, interval)
        self.pid = None
        self._pref = {k: False for k in IDS}

    def availability(self, oid):
        if len(self.layer.rows.get(oid, [])) != len(ROW_CODES[oid]):
            return False, f"This keyboard has no complete {ROW_NAMES[oid]}"
        if oid in self._sensor_ok and not self._sensor_ok[oid]:
            return False, f"{LABELS[oid]} load is not available on this system"
        if oid == "gpu" and not self.gpu.available:
            return False, self.gpu.reason
        return True, None

    def _apply(self):
        for oid in IDS:
            self.layer.set_enabled(oid, self._pref[oid] and self.availability(oid)[0])
        if any(self.layer.enabled(k) for k in SENSOR_IDS):
            self.sampler.start()
        else:
            self.sampler.stop()

    def follow_profile(self, pid):
        self.pid = pid
        self._pref = toggles_for(load_prefs(self._path), pid)
        self._apply()

    def set(self, oid, on):
        if oid not in IDS:
            return {"ok": False, "error": f"unknown overlay {oid!r}"}
        on = bool(on)
        ok, reason = self.availability(oid)
        if on and not ok:
            return {"ok": False, "error": reason}
        self._pref[oid] = on
        save_toggle(self._path, self._lock, self.pid or "p1", oid, on)
        self._apply()
        return {"ok": True, "id": oid, "on": self.layer.enabled(oid)}

    def any_on(self):
        return self.layer.any_enabled()

    def status(self):
        self._apply()                       # picks up a probe that gave up
        st = self.layer.pomodoro_state()
        rows = []
        for oid in IDS:
            ok, reason = self.availability(oid)
            e = {"id": oid, "label": LABELS[oid], "row": ROW_NAMES[oid],
                 "on": self.layer.enabled(oid), "available": ok, "reason": reason,
                 "value": self.layer.value(oid) if oid in SENSOR_IDS
                 else (st.progress if st else None)}
            if oid == "pomodoro" and st:
                e["phase"], e["remaining_s"] = st.phase, int(math.ceil(st.remaining_s))
            rows.append(e)
        return {"overlays": rows,
                "pomodoro": {"phase": st.phase if st else None,
                             "remaining_s": int(math.ceil(st.remaining_s)) if st else None}}

    def close(self):
        self.sampler.stop()
