#!/usr/bin/env python3
"""Interactive helper to identify the Aula Win60 HE's built-in (firmware) lighting
modes. The firmware reports *which* mode bytes it supports but not their names, so
we set one mode at a time on a vivid color and you tell us what it looks like.

Requires exclusive HID access -- CLOSE app_web.py first (only one process can hold
the vendor interface at a time).

Usage:
    python cycle_modes.py list                 # query the modes the board supports
    python cycle_modes.py <mode> [r g b] [speed] [bright] [dir]
                                               # set one mode (defaults: white, mid)

Examples:
    python cycle_modes.py list
    python cycle_modes.py 1                     # mode 1, white, speed 3, bright 4
    python cycle_modes.py 6 0 255 180 4 4 1     # mode 6, teal, fast, full, dir 1
"""
import sys
import hid

import protocol

VID, PID = 0x2E3C, 0xC365


def _usb_reset():
    """Clear a stuck interface claim (e.g. after app_web.py was SIGKILLed) by
    resetting the device over libusb. No-op if pyusb isn't available."""
    try:
        import usb.core
        dev = usb.core.find(idVendor=VID, idProduct=PID)
        if dev is not None:
            dev.reset()
            return True
    except Exception:
        pass
    return False


def open_device():
    ms = hid.enumerate(VID, PID)
    if not ms:
        raise SystemExit("Aula Win60 HE not found (is it plugged in?)")
    info = max(ms, key=lambda m: m["interface_number"])  # vendor iface = highest (2)
    d = hid.device()
    try:
        d.open_path(info["path"])
    except OSError:
        # Most common cause: a previous holder (app_web.py) left iface 2 claimed.
        # Try a USB reset, then one more open before giving up.
        if _usb_reset():
            import time
            time.sleep(1.5)
            try:
                d.open_path(info["path"])
            except OSError:
                raise SystemExit("open failed even after USB reset -- close app_web.py / replug.")
        else:
            raise SystemExit("open failed -- close app_web.py first (it holds the HID interface).")
    d.set_nonblocking(False)
    return d


def query_modes(d):
    d.write(protocol.build_read_light_list())
    for _ in range(40):
        r = d.read(64, timeout_ms=200)
        info = protocol.parse_light_list(r) if r else None
        if info:
            return info
    return None


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    d = open_device()
    try:
        if sys.argv[1] == "list":
            info = query_modes(d)
            if not info:
                print("No mode-list response from firmware.")
                return
            print("Supported firmware mode bytes:", info["modes"])
            print("  (the driver also adds 10 = per-key Custom)")
            print("max speed:", info["max_speed"], " max brightness:", info["max_brightness"])
            return

        mode = int(sys.argv[1])
        args = sys.argv[2:]
        r, g, b = (int(args[0]), int(args[1]), int(args[2])) if len(args) >= 3 else (255, 255, 255)
        speed = int(args[3]) if len(args) >= 4 else 3
        bright = int(args[4]) if len(args) >= 5 else 4
        direction = int(args[5]) if len(args) >= 6 else 0
        d.write(protocol.build_light(mode, bright, speed, (r, g, b),
                                     direction=direction, power_on=True))
        print(f"set mode={mode} color=({r},{g},{b}) speed={speed} bright={bright} dir={direction}")
        print("-> look at the keyboard and tell me what this effect does.")
    finally:
        d.close()


if __name__ == "__main__":
    main()
