#!/usr/bin/env python3
"""Play ONE host effect on the board until killed — for reviewing effects live.

Usage: python play_effect.py <effect> [speed0-100] [dir] [orient]
Close app_web.py first (it holds the HID interface).
"""
import sys, time, signal
import device_state, effects
from aula_device import AulaDevice
import protocol

effect = sys.argv[1] if len(sys.argv) > 1 else "wave"
speed  = float(sys.argv[2]) / 100.0 if len(sys.argv) > 2 else 0.6
direction = int(sys.argv[3]) if len(sys.argv) > 3 else 0
orient = sys.argv[4] if len(sys.argv) > 4 else "v"

# 3-color palette, ~2 tones darker (×0.65) per the user's default preference.
PALETTE = [(166, 0, 130), (0, 130, 166), (166, 104, 0)]
BG = (14, 10, 28)   # dim background so bg-aware effects (striation) read clearly

km = device_state.KeyMap()
dev = AulaDevice(); dev.open()
fx = effects.PerKeyEffectEngine(km, None)

# Build a frame sender bound to this device (+ diff cache for low latency).
_last = {"pkts": None}
def send(frame):
    try:
        pkts = protocol.build_custom_light(frame, slot=0)
        for i, p in enumerate(pkts):
            if _last["pkts"] is None or i >= len(_last["pkts"]) or p != _last["pkts"][i]:
                dev.write(p)
        _last["pkts"] = pkts
    except Exception:
        _last["pkts"] = None
fx._send = send

# Press-reactive effects need live travel; attach a reader for those.
reader = None
if effect in ("reactive", "ripple", "speedres", "cross", "fireworks"):
    reader = device_state.LiveReader(dev, km)
    reader.start()
    fx.get_depths = lambda: {km.index_of_code[c]: mm
                             for c, mm in reader.snapshot().items()
                             if c in km.index_of_code}

dev.write(protocol.build_light(10, 4, 4, (255, 255, 255)))  # custom per-key mode
fx.start(effect, PALETTE, BG, speed, 1.0, direction, orient)
print(f"playing '{effect}' (speed={speed} dir={direction} orient={orient}) — Ctrl-C / kill to stop")

_running = {"go": True}
def _shutdown(*_a):
    _running["go"] = False
signal.signal(signal.SIGTERM, _shutdown)
signal.signal(signal.SIGINT, _shutdown)
try:
    while _running["go"]:
        time.sleep(0.2)
finally:
    fx.stop()
    if reader: reader.stop()
    dev.close()

