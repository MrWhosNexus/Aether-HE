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
