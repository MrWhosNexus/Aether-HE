"""Virtual gamepad fed by analog key depth.

The Aula Win60 HE is a Hall-effect board: each key reports continuous travel
(0.0 mm released .. ~4.0 mm bottomed-out). This module turns that travel into
analog gamepad axes/buttons, so e.g. pressing W deeper = more throttle.

Backends:
- Linux: python-evdev / uinput. Needs write access to /dev/uinput
  (see 99-uinput.rules); join the 'input' group.
- Windows: vgamepad + ViGEmBus (virtual Xbox 360 pad). Install ViGEmBus from
  https://github.com/nefarius/ViGEmBus once per machine.

Public API (kept stable so app_web.py doesn't need to know the backend):
  EVDEV_AVAILABLE  -> True if ANY backend is usable (legacy name)
  KeyMap, DEFAULT_DRIVING_MAP
  VirtualGamepad(mappings).open() / .is_open() / .update(depths) / .close()
"""
import logging
import os
import sys
from dataclasses import dataclass

log = logging.getLogger(__name__)

MAX_TRAVEL_MM = 4.0

# --- backend probing --------------------------------------------------------

_BACKEND = None   # "evdev" | "vgamepad" | None

try:
    if sys.platform.startswith("linux"):
        from evdev import UInput, ecodes as e, AbsInfo  # noqa: F401
        from evdev.uinput import UInputError  # noqa: F401
        _BACKEND = "evdev"
except Exception:
    pass

if _BACKEND is None:
    try:
        import vgamepad as _vg
        _BACKEND = "vgamepad"
    except Exception:
        _vg = None

# Legacy flag — app_web.py / UI use this to know whether gamepad capture works.
EVDEV_AVAILABLE = _BACKEND is not None


# --- ViGEmBus auto-installer (Windows only) --------------------------------
#
# vgamepad imports cleanly even when the ViGEmBus kernel driver isn't present;
# the failure only shows up when VX360Gamepad() is constructed. We ship the
# official ViGEmBus installer alongside the app so the user can install the
# driver in one click without leaving the app.

def _vigembus_installer_path():
    """Find the bundled ViGEmBus_Setup.exe.

    PyInstaller --onedir puts data files under sys._MEIPASS; in source the
    installer lives in vendor/ next to gamepad.py.
    """
    here = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    p = os.path.join(here, "vendor", "ViGEmBus_Setup.exe")
    return p if os.path.exists(p) else None


def install_vigembus_driver():
    """Run the bundled ViGEmBus installer with UAC elevation. Returns
    {"ok": bool, "error": str, "exit_code": int}. Windows only.
    """
    if not sys.platform.startswith("win"):
        return {"ok": False, "error": "ViGEmBus is Windows-only"}
    setup = _vigembus_installer_path()
    if not setup:
        return {"ok": False, "error": "ViGEmBus_Setup.exe not bundled with this build"}
    try:
        import ctypes
        SEE_MASK_NOCLOSEPROCESS = 0x40
        SEE_MASK_NOASYNC = 0x100
        class SHELLEXECUTEINFOW(ctypes.Structure):
            _fields_ = [
                ("cbSize", ctypes.c_ulong), ("fMask", ctypes.c_ulong),
                ("hwnd", ctypes.c_void_p), ("lpVerb", ctypes.c_wchar_p),
                ("lpFile", ctypes.c_wchar_p), ("lpParameters", ctypes.c_wchar_p),
                ("lpDirectory", ctypes.c_wchar_p), ("nShow", ctypes.c_int),
                ("hInstApp", ctypes.c_void_p), ("lpIDList", ctypes.c_void_p),
                ("lpClass", ctypes.c_wchar_p), ("hkeyClass", ctypes.c_void_p),
                ("dwHotKey", ctypes.c_ulong), ("hIcon", ctypes.c_void_p),
                ("hProcess", ctypes.c_void_p),
            ]
        sei = SHELLEXECUTEINFOW()
        sei.cbSize = ctypes.sizeof(sei)
        sei.fMask = SEE_MASK_NOCLOSEPROCESS | SEE_MASK_NOASYNC
        sei.lpVerb = "runas"      # UAC elevation
        sei.lpFile = setup
        sei.lpParameters = "/quiet /norestart"   # ViGEmBus uses WiX → MSI flags
        sei.nShow = 1
        if not ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(sei)):
            err = ctypes.windll.kernel32.GetLastError()
            # 1223 == ERROR_CANCELLED (user declined UAC)
            return {"ok": False, "error": f"installer launch failed (code {err})"}
        ctypes.windll.kernel32.WaitForSingleObject(sei.hProcess, 0xFFFFFFFF)
        code = ctypes.c_ulong(0)
        ctypes.windll.kernel32.GetExitCodeProcess(sei.hProcess, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(sei.hProcess)
        return {"ok": code.value == 0, "exit_code": code.value,
                "error": "" if code.value == 0 else f"installer exited {code.value}"}
    except Exception as ex:
        return {"ok": False, "error": f"{type(ex).__name__}: {ex}"}


def vigembus_present():
    """Cheap probe — try to instantiate a virtual pad and immediately reset.
    Returns True if the driver is installed and accepting clients."""
    if _BACKEND != "vgamepad" or _vg is None:
        return False
    try:
        p = _vg.VX360Gamepad()
        try: p.reset(); p.update()
        except Exception: pass
        return True
    except Exception:
        return False


@dataclass(frozen=True)
class KeyMap:
    """Map one physical key's analog depth onto a gamepad control.

    axis:      'LX','LY','RX','RY','LT','RT' (analog) or
               'BTN_A','BTN_B','BTN_X','BTN_Y','BTN_LB','BTN_RB' (digital)
    direction: +1/-1, only meaningful for signed stick axes (e.g. A=-1, D=+1).
    threshold_mm: depth past which a digital button registers as pressed.
    """
    key: str
    axis: str
    direction: int = 1
    threshold_mm: float = 1.5


DEFAULT_DRIVING_MAP = [
    KeyMap("A", "LX", direction=-1),
    KeyMap("D", "LX", direction=+1),
    KeyMap("W", "RT"),
    KeyMap("S", "LT"),
    KeyMap("Space", "BTN_A", threshold_mm=1.0),
]

_STICK_AXES = {"LX", "LY", "RX", "RY"}
_TRIG_AXES = {"LT", "RT"}
_BTN_AXES = {"BTN_A", "BTN_B", "BTN_X", "BTN_Y", "BTN_LB", "BTN_RB"}


# --- shared ----------------------------------------------------------------

class VirtualGamepad:
    """Façade that dispatches to the available backend."""

    def __init__(self, mappings=None, max_travel_mm=MAX_TRAVEL_MM):
        if _BACKEND is None:
            raise RuntimeError(
                "No virtual-gamepad backend available. "
                "Install python-evdev (Linux) or vgamepad + ViGEmBus (Windows)."
            )
        self.mappings = list(mappings or DEFAULT_DRIVING_MAP)
        self.max_travel = max_travel_mm
        self._impl = None

    def open(self):
        self._impl = (
            _EvdevPad(self.mappings, self.max_travel)
            if _BACKEND == "evdev"
            else _VgamepadPad(self.mappings, self.max_travel)
        )
        self._impl.open()
        return self

    def is_open(self):
        return self._impl is not None and self._impl.is_open()

    def update(self, depths):
        if self._impl is not None:
            self._impl.update(depths)

    def close(self):
        if self._impl is not None:
            try:
                self._impl.close()
            finally:
                self._impl = None


# --- Linux / uinput backend -------------------------------------------------

class _EvdevPad:
    def __init__(self, mappings, max_travel):
        self.mappings = mappings
        self.max_travel = max_travel
        self._ui = None
        self._axis_code = {
            "LX": (e.ABS_X, False), "LY": (e.ABS_Y, False),
            "RX": (e.ABS_RX, False), "RY": (e.ABS_RY, False),
            "LT": (e.ABS_Z, True), "RT": (e.ABS_RZ, True),
        }
        self._btn_code = {
            "BTN_A": e.BTN_SOUTH, "BTN_B": e.BTN_EAST,
            "BTN_X": e.BTN_NORTH, "BTN_Y": e.BTN_WEST,
            "BTN_LB": e.BTN_TL,   "BTN_RB": e.BTN_TR,
        }

    def open(self):
        cap = {
            e.EV_KEY: sorted({self._btn_code[m.axis] for m in self.mappings
                              if m.axis in self._btn_code}),
            e.EV_ABS: [],
        }
        used_axes = {m.axis for m in self.mappings if m.axis in self._axis_code}
        for ax in used_axes:
            code, is_trig = self._axis_code[ax]
            lo, hi = (0, 255) if is_trig else (-32767, 32767)
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
                "join the 'input' group. "
                f"[{type(ex).__name__}: {ex}]"
            ) from ex
        log.info("Virtual gamepad (evdev) created: %s", self._ui.device.path)

    def is_open(self):
        return self._ui is not None

    def update(self, depths):
        if self._ui is None:
            return
        axis_val = {}
        for m in self.mappings:
            depth = max(0.0, min(self.max_travel, depths.get(m.key, 0.0)))
            frac = depth / self.max_travel
            if m.axis in self._axis_code:
                code, is_trig = self._axis_code[m.axis]
                if is_trig:
                    axis_val[code] = axis_val.get(code, 0) + int(frac * 255)
                else:
                    axis_val[code] = axis_val.get(code, 0) + int(m.direction * frac * 32767)
            elif m.axis in self._btn_code:
                self._ui.write(e.EV_KEY, self._btn_code[m.axis],
                               1 if depth >= m.threshold_mm else 0)
        for code, val in axis_val.items():
            val = max(-32767, min(32767, val))
            self._ui.write(e.EV_ABS, code, val)
        self._ui.syn()

    def close(self):
        if self._ui is not None:
            try:
                self._ui.close()
            finally:
                self._ui = None


# --- Windows / vgamepad backend (virtual Xbox 360 pad via ViGEmBus) ---------

class _VgamepadPad:
    def __init__(self, mappings, max_travel):
        self.mappings = mappings
        self.max_travel = max_travel
        self._pad = None
        # Button enums resolved lazily after import.
        self._btn_enum = None

    def _btn(self, axis):
        b = self._btn_enum
        return {
            "BTN_A":  b.XUSB_GAMEPAD_A,
            "BTN_B":  b.XUSB_GAMEPAD_B,
            "BTN_X":  b.XUSB_GAMEPAD_X,
            "BTN_Y":  b.XUSB_GAMEPAD_Y,
            "BTN_LB": b.XUSB_GAMEPAD_LEFT_SHOULDER,
            "BTN_RB": b.XUSB_GAMEPAD_RIGHT_SHOULDER,
        }[axis]

    def open(self):
        try:
            self._pad = _vg.VX360Gamepad()
            self._btn_enum = _vg.XUSB_BUTTON
            self._pad.update()
        except Exception as ex:
            raise PermissionError(
                "vgamepad failed to create a virtual pad. "
                "Make sure ViGEmBus is installed "
                "(https://github.com/nefarius/ViGEmBus). "
                f"[{type(ex).__name__}: {ex}]"
            ) from ex
        log.info("Virtual gamepad (vgamepad/ViGEmBus) created")

    def is_open(self):
        return self._pad is not None

    def update(self, depths):
        if self._pad is None:
            return
        # Accumulate analog values, then push one update().
        lx = ly = rx = ry = 0.0
        lt = rt = 0.0
        for m in self.mappings:
            depth = max(0.0, min(self.max_travel, depths.get(m.key, 0.0)))
            frac = depth / self.max_travel
            if m.axis in _STICK_AXES:
                v = m.direction * frac
                if   m.axis == "LX": lx += v
                elif m.axis == "LY": ly += v
                elif m.axis == "RX": rx += v
                elif m.axis == "RY": ry += v
            elif m.axis in _TRIG_AXES:
                if m.axis == "LT": lt += frac
                else:              rt += frac
            elif m.axis in _BTN_AXES:
                btn = self._btn(m.axis)
                if depth >= m.threshold_mm:
                    self._pad.press_button(button=btn)
                else:
                    self._pad.release_button(button=btn)
        clamp = lambda x: max(-1.0, min(1.0, x))
        self._pad.left_joystick_float(x_value_float=clamp(lx),
                                      y_value_float=clamp(ly))
        self._pad.right_joystick_float(x_value_float=clamp(rx),
                                       y_value_float=clamp(ry))
        self._pad.left_trigger_float(value_float=max(0.0, min(1.0, lt)))
        self._pad.right_trigger_float(value_float=max(0.0, min(1.0, rt)))
        self._pad.update()

    def close(self):
        if self._pad is not None:
            try:
                self._pad.reset()
                self._pad.update()
            except Exception:
                pass
            self._pad = None


if __name__ == "__main__":
    import time
    logging.basicConfig(level=logging.INFO)
    print(f"backend = {_BACKEND}")
    pad = VirtualGamepad().open()
    print("Sweeping throttle (W) 0->4mm, then steering A/D.")
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
