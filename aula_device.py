import logging
import threading
import hid

AULA_VID = 0x2E3C
AULA_PID = 0xC365
# Confirmed from the iface-2 report descriptor (chrome://device-log dump):
#   Usage Page 0xFF1B, Usage 0x91, Report ID 0x01, 63 data bytes (64-byte reports).
#   Only Input + Output reports are declared — there is NO Feature report on this
#   interface, so the config protocol uses Output reports prefixed with 0x01.
VENDOR_USAGE_PAGE = 0xFF1B
VENDOR_USAGE = 0x91
VENDOR_REPORT_ID = 0x01
VENDOR_REPORT_LEN = 64  # 1-byte Report ID + 63 data bytes
PAYLOAD_LEN = 63

CMD_LIGHTING = 0x07  # set lighting (color / effect / brightness)
CMD_SELECT = 0x17    # "select" prelude the driver sends before an effect change
CMD_TRAVEL = 0x21    # analog travel report / actuation family (decimal 33)

TRAVEL_FULL_RAW = 400  # depth raw value at ~4.00mm (units of 0.01mm)

log = logging.getLogger(__name__)


def parse_travel(report):
    """Parse an analog travel report streamed from the vendor interface.

    `report` is a raw hidapi read() result, i.e. it INCLUDES the Report ID at
    index 0 (so the 0x21 command byte is at index 1).

    Returns {"key": (a, b), "depth_mm": float} for the simple per-key travel
    sub-report (subtype 5), else None. Depth is a 16-bit LE value in 0.01mm
    units (0..~400 == 0..4.00mm), confirmed against the driver capture.
    """
    if len(report) < 11 or report[0] != VENDOR_REPORT_ID or report[1] != CMD_TRAVEL:
        return None
    subtype = report[5]
    if subtype == 5:
        depth_raw = report[9] | (report[10] << 8)
        return {"key": (report[7], report[8]), "depth_mm": depth_raw / 100.0}
    return None


def build_select():
    """The 0x17 prelude the Aula driver emits right before switching effect mode.
    Returns [VENDOR_REPORT_ID] + 63 data bytes."""
    data = [0x00] * PAYLOAD_LEN
    data[0] = CMD_SELECT
    data[4] = 0x02
    return [VENDOR_REPORT_ID] + data


def build_lighting(r, g, b, mode=0, brightness=0x04, speed=0x04, direction=0):
    """Build a lighting Output report, reverse-engineered from the Aula WebHID
    driver (sendReport id=0x01, 63-byte payload).

    Data byte layout (index 0 == CMD, i.e. after the Report-ID byte):
      [0]=0x07 cmd   [4]=0x0e len    [5]=mode    [6]=brightness  [7]=speed
      [8..10]=R,G,B  [11]=0xff [12]=0x55 (static template)  [14]=direction

    R/G/B and mode are confirmed against driver captures; brightness/speed
    positions are inferred (constant 0x04 in capture) and need verification.

    Returns a VENDOR_REPORT_LEN-byte list: [VENDOR_REPORT_ID] + 63 data bytes.
    """
    data = [0x00] * PAYLOAD_LEN
    data[0] = CMD_LIGHTING
    data[4] = 0x0E
    data[5] = mode & 0xFF
    data[6] = brightness & 0xFF
    data[7] = speed & 0xFF
    data[8] = r & 0xFF
    data[9] = g & 0xFF
    data[10] = b & 0xFF
    data[11] = 0xFF
    data[12] = 0x55
    data[14] = direction & 0xFF
    return [VENDOR_REPORT_ID] + data


def enumerate_interfaces(vid=AULA_VID, pid=AULA_PID):
    return hid.enumerate(vid, pid)


def find_vendor_interface(vid=AULA_VID, pid=AULA_PID, usage_page=VENDOR_USAGE_PAGE):
    matches = enumerate_interfaces(vid, pid)
    if not matches:
        return None
    vendor = [m for m in matches if m.get("usage_page") == usage_page]
    if vendor:
        return vendor[0]
    log.warning(
        "No 0x%04X usage page found; falling back to highest interface_number. Interfaces: %s",
        usage_page,
        [(m["interface_number"], m["usage_page"]) for m in matches],
    )
    return max(matches, key=lambda m: m["interface_number"])


class AulaDevice:
    """Thread-safe wrapper around a single hidraw handle for the Aula Win60 HE."""

    def __init__(self):
        self._dev = None
        self._info = None
        self._lock = threading.Lock()

    def open(self):
        info = find_vendor_interface()
        if info is None:
            raise IOError("Aula Win60 HE not found")
        dev = hid.device()
        log.info("Opening Aula interface %s", info["interface_number"])
        dev.open_path(info["path"])
        dev.set_nonblocking(False)
        with self._lock:
            self._dev = dev
            self._info = info
        log.info(
            "Opened Aula interface %s (usage_page=0x%04X)",
            info["interface_number"],
            info["usage_page"],
        )
        return info

    def close(self):
        with self._lock:
            if self._dev is not None:
                try:
                    self._dev.close()
                finally:
                    self._dev = None
                    self._info = None

    def is_open(self):
        with self._lock:
            return self._dev is not None

    def info(self):
        with self._lock:
            return dict(self._info) if self._info else None

    def write(self, payload):
        """Output report. payload[0] MUST be the Report ID (use 0x00 if unset)."""
        with self._lock:
            if self._dev is None:
                raise IOError("device not open")
            return self._dev.write(payload)

    def send_feature(self, payload):
        """Feature report. payload[0] MUST be the Report ID."""
        with self._lock:
            if self._dev is None:
                raise IOError("device not open")
            return self._dev.send_feature_report(payload)

    def get_feature(self, report_id, length):
        with self._lock:
            if self._dev is None:
                raise IOError("device not open")
            return self._dev.get_feature_report(report_id, length)

    def read(self, length, timeout_ms=100):
        with self._lock:
            if self._dev is None:
                raise IOError("device not open")
            return self._dev.read(length, timeout_ms=timeout_ms)
