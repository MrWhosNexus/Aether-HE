#!/usr/bin/env python3
"""list_hid.py — dump every HID interface on this machine for a board submission.

Aether talks to keyboards over raw HID. To add a new board we need to know its
USB vendor/product IDs and which interface exposes the vendor "config" collection
(the one the lighting/actuation commands go to).

Usage:
    python tools/list_hid.py              # list everything (pick out your keyboard)
    python tools/list_hid.py 2E3C         # filter to one vendor id (hex), e.g. Aula
    python tools/list_hid.py 2E3C C365    # filter to one VID + PID (hex)

Copy the WHOLE output into the "HID interface dump" field of the board issue form.
Requires the project deps (`pip install -r requirements.txt`); `hidapi` provides `hid`.
"""
import sys

try:
    import hid
except ImportError:
    sys.exit("Could not import `hid`. Install deps first:  pip install -r requirements.txt")


def parse_hex(arg):
    return int(arg, 16)


def main(argv):
    vid = parse_hex(argv[0]) if len(argv) >= 1 else 0
    pid = parse_hex(argv[1]) if len(argv) >= 2 else 0

    devices = hid.enumerate(vid, pid)
    if not devices:
        scope = "any device" if not vid else f"VID={vid:#06x}" + (f" PID={pid:#06x}" if pid else "")
        print(f"No HID interfaces found for {scope}.")
        print("Tip: unplug other USB devices, replug the keyboard, and re-run.")
        return

    # Group by (vid, pid) so multi-interface boards read clearly.
    by_device = {}
    for d in devices:
        by_device.setdefault((d["vendor_id"], d["product_id"]), []).append(d)

    for (v, p), ifaces in sorted(by_device.items()):
        man = (ifaces[0].get("manufacturer_string") or "").strip()
        prod = (ifaces[0].get("product_string") or "").strip()
        print("=" * 70)
        print(f"VID:PID = {v:04X}:{p:04X}    {man}  {prod}".rstrip())
        print("=" * 70)
        for d in sorted(ifaces, key=lambda x: (x.get("interface_number", -1), x.get("usage_page", 0))):
            up = d.get("usage_page", 0) or 0
            usage = d.get("usage", 0) or 0
            iface = d.get("interface_number", -1)
            star = "  <-- likely VENDOR config collection" if up >= 0xFF00 else ""
            print(f"  interface {iface:>2}  usage_page={up:#06x}  usage={usage:#04x}{star}")
            print(f"             path={d.get('path')}")
        print()

    print("-" * 70)
    print("What to put in the issue form:")
    print("  * USB VID & PID  -> the VID:PID line above for your keyboard")
    print("  * HID dump       -> paste this entire output")
    print("  * The interface marked 'VENDOR config collection' (usage_page >= 0xFF00)")
    print("    is usually the one Aether needs to send lighting/actuation to.")


if __name__ == "__main__":
    main(sys.argv[1:])
