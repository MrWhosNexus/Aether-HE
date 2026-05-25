"""Virtual gamepad fed by analog key depth (Linux / uinput via python-evdev).

The Aula Win60 HE is a Hall-effect board: each key reports continuous travel
(0.0 mm released .. ~4.0 mm bottomed-out). This module turns that travel into
analog gamepad axes/buttons, so e.g. pressing W deeper = more throttle.

Requires write access to /dev/uinput (see 99-uinput.rules). On permission
failure, VirtualGamepad.open() raises PermissionError with a clear hint.
"""
import logging
from dataclasses import dataclass

try:
    from evdev import UInput, ecodes as e, AbsInfo
    from evdev.uinput import UInputError
    EVDEV_AVAILABLE = True
except Exception:  # pragma: no cover - evdev missing
    EVDEV_AVAILABLE = False
    UInputError = Exception

log = logging.getLogger(__name__)

MAX_TRAVEL_MM = 4.0  # full key travel; depth is clamped to this

# Logical axis -> (ecode, is_trigger). Sticks are signed; triggers are 0..255.
_STICK_MIN, _STICK_MAX = -32767, 32767
_TRIG_MIN, _TRIG_MAX = 0, 255


@dataclass(frozen=True)
class KeyMap:
    """Map one physical key's analog depth onto a gamepad control.

    axis: one of 'LX','LY','RX','RY','LT','RT'  -> analog axis
          or 'BTN_A','BTN_B','BTN_X','BTN_Y','BTN_LB','BTN_RB' -> digital button
    direction: +1 or -1, only meaningful for signed stick axes (e.g. A=-1, D=+1).
    threshold_mm: for buttons, depth past which the button is "pressed".
    """
    key: str
    axis: str
    direction: int = 1
    threshold_mm: float = 1.5


_AXIS_ECODE = {}
_BTN_ECODE = {}


def _init_ecode_tables():
    if not EVDEV_AVAILABLE:
        return
    _AXIS_ECODE.update({
        "LX": (e.ABS_X, False),
        "LY": (e.ABS_Y, False),
        "RX": (e.ABS_RX, False),
        "RY": (e.ABS_RY, False),
        "LT": (e.ABS_Z, True),
        "RT": (e.ABS_RZ, True),
    })
    _BTN_ECODE.update({
        "BTN_A": e.BTN_SOUTH,
        "BTN_B": e.BTN_EAST,
        "BTN_X": e.BTN_NORTH,
        "BTN_Y": e.BTN_WEST,
        "BTN_LB": e.BTN_TL,
        "BTN_RB": e.BTN_TR,
    })


# A sensible default for driving games: WASD steer/throttle, Space = handbrake.
DEFAULT_DRIVING_MAP = [
    KeyMap("A", "LX", direction=-1),
    KeyMap("D", "LX", direction=+1),
    KeyMap("W", "RT"),            # right trigger = throttle (deeper = faster)
    KeyMap("S", "LT"),            # left trigger  = brake
    KeyMap("Space", "BTN_A", threshold_mm=1.0),
]


class VirtualGamepad:
    def __init__(self, mappings=None, max_travel_mm=MAX_TRAVEL_MM):
        if not EVDEV_AVAILABLE:
            raise RuntimeError("python-evdev not installed (pip install evdev)")
        _init_ecode_tables()
        self.mappings = list(mappings or DEFAULT_DRIVING_MAP)
        self.max_travel = max_travel_mm
        self._ui = None

    def open(self):
        cap = {
            e.EV_KEY: sorted({_BTN_ECODE[m.axis] for m in self.mappings
                              if m.axis in _BTN_ECODE}),
            e.EV_ABS: [],
        }
        used_axes = {m.axis for m in self.mappings if m.axis in _AXIS_ECODE}
        for ax in used_axes:
            code, is_trig = _AXIS_ECODE[ax]
            lo, hi = (_TRIG_MIN, _TRIG_MAX) if is_trig else (_STICK_MIN, _STICK_MAX)
            cap[e.EV_ABS].append(
                (code, AbsInfo(value=0, min=lo, max=hi, fuzz=0, flat=0, resolution=0))
            )
        if not cap[e.EV_KEY]:
            del cap[e.EV_KEY]
        try:
            self._ui = UInput(cap, name="Aula Win60 HE Virtual Gamepad",
                              vendor=0x2E3C, product=0xC365, version=1)
        except (PermissionError, OSError, UInputError) as ex:
            raise PermissionError(
                "No write access to /dev/uinput. Install 99-uinput.rules and "
                "join the 'input' group (see README). "
                f"[{type(ex).__name__}: {ex}]"
            ) from ex
        log.info("Virtual gamepad created: %s", self._ui.device.path)
        return self

    def is_open(self):
        return self._ui is not None

    def update(self, depths):
        """Push the current frame. depths: {key_name: depth_mm}."""
        if self._ui is None:
            return
        # Accumulate signed stick axes from opposing keys; triggers/buttons direct.
        axis_val = {}
        for m in self.mappings:
            depth = max(0.0, min(self.max_travel, depths.get(m.key, 0.0)))
            frac = depth / self.max_travel
            if m.axis in _AXIS_ECODE:
                code, is_trig = _AXIS_ECODE[m.axis]
                if is_trig:
                    axis_val[code] = axis_val.get(code, 0) + int(frac * _TRIG_MAX)
                else:
                    axis_val[code] = axis_val.get(code, 0) + int(m.direction * frac * _STICK_MAX)
            elif m.axis in _BTN_ECODE:
                self._ui.write(e.EV_KEY, _BTN_ECODE[m.axis],
                               1 if depth >= m.threshold_mm else 0)
        for code, val in axis_val.items():
            val = max(_STICK_MIN, min(_STICK_MAX, val))
            self._ui.write(e.EV_ABS, code, val)
        self._ui.syn()

    def close(self):
        if self._ui is not None:
            try:
                self._ui.close()
            finally:
                self._ui = None


if __name__ == "__main__":
    # Self-test: sweep the right trigger (throttle) and steer left/right.
    import time
    logging.basicConfig(level=logging.INFO)
    pad = VirtualGamepad().open()
    print("Sweeping throttle (W) 0->4mm, then steering A/D. Watch with `evtest`.")
    try:
        for mm in [0, 1, 2, 3, 4, 0]:
            pad.update({"W": mm})
            print(f"throttle depth={mm}mm")
            time.sleep(0.4)
        for key in ("A", "D"):
            pad.update({key: 4.0})
            print(f"steer {key} full")
            time.sleep(0.6)
        pad.update({})
    finally:
        pad.close()
