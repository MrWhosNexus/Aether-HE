#!/usr/bin/env bash
# Capture Aula Win60 HE vendor traffic for protocol mapping.
#
# The official Aula web driver (WebHID in Chrome) sends config commands as HID
# Output reports on the vendor interface (iface 2). This script snoops the USB
# bus with usbmon and prints the data bytes of every frame to/from the keyboard,
# so you can diff packets between known setting changes.
#
# Usage:
#   sudo ./capture.sh [seconds]      # default 60s
#
# If the keyboard was unplugged/replugged, re-check its address first:
#   lsusb -d 2e3c:                   # "Bus 003 Device 0NN" -> BUS=3 DEV=NN
set -euo pipefail

BUS=3      # usbmon instance == USB bus number (Bus 003 -> 3)
DEV=13     # USB device address (lsusb "Device 013" -> 13)
DUR="${1:-60}"

if [[ $EUID -ne 0 ]]; then
  echo "Run with sudo (usbmon capture needs root)." >&2
  exit 1
fi

modprobe usbmon

echo "=================================================================="
echo " Capturing usbmon${BUS}, device ${DEV}, for ${DUR}s."
echo " NOW: in the Aula web driver, change ONE setting at a time,"
echo "      pausing ~1s between each, e.g. for RGB:"
echo "        1) solid RED   full brightness"
echo "        2) solid GREEN full brightness"
echo "        3) solid BLUE  full brightness"
echo "        4) brightness  -> minimum"
echo " Each step's Output report(s) print below as: time  endpoint  hexdata"
echo "=================================================================="

# usb.capdata = the report payload; filter to just our device, both directions.
tshark -i "usbmon${BUS}" -a "duration:${DUR}" \
  -Y "usb.device_address==${DEV} && usb.capdata" \
  -T fields \
  -e frame.time_relative \
  -e usb.endpoint_address \
  -e usb.capdata
