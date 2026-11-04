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
