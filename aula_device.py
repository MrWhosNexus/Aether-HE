import logging
import sys
import threading
import time
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


class VendorInterfaceUnresolved(IOError):
    """The board enumerated, but no vendor interface could be picked *safely*.

    Distinct from "not found": the hardware is present. Raising instead of
    guessing keeps us honest — a config frame written to the wrong top-level
    collection is a silent no-op at best.
    """


class HidPermissionError(IOError):
    """The OS refused the open. On macOS this is the Input Monitoring (TCC) gate."""


def enumerate_interfaces(vid=AULA_VID, pid=AULA_PID):
    return hid.enumerate(vid, pid)


def find_vendor_interface(vid=AULA_VID, pid=AULA_PID, usage_page=VENDOR_USAGE_PAGE):
    """Pick the vendor-config HID collection for (vid, pid).

    Returns the hidapi enumeration dict, or None if the board isn't present.
    Raises VendorInterfaceUnresolved when the board IS present but no
    deterministic choice exists (see the fallback note below).

    Preferred: the collection whose usage_page matches (0xFF1B on the Win60).
    Windows and macOS hidapi report usage pages per top-level collection, so
    this is the normal path there. Linux hidraw reports usage_page=0 for
    every interface (see docs/context/aula-win60-hidapi-usage-page-quirk.md),
    so fall back to the highest interface_number — and within that interface
    prefer a vendor-defined usage page (0xFF00..0xFFFF) over a generic one, so
    a platform that DOES split an interface into several collections never
    hands us the keyboard/consumer collection that shares its number.
    """
    matches = enumerate_interfaces(vid, pid)
    if not matches:
        return None
    vendor = [m for m in matches if m.get("usage_page") == usage_page]
    if vendor:
        # macOS enumerates one entry per top-level COLLECTION, and collections
        # on one USB interface share a single `path`, so open_path() opens the
        # interface, not the collection. Harmless for these protocols (every
        # frame carries its report id, so writes still route), but a read can
        # surface a sibling collection's reports — say so once.
        if len(vendor) > 1:
            log.warning(
                "%d collections match usage page 0x%04X; using the first. Paths: %s",
                len(vendor), usage_page, [m.get("path") for m in vendor],
            )
        return vendor[0]

    # --- fallback: no usage-page match -------------------------------------
    # "Highest interface_number" only means something where hidapi knows the
    # interface number. Its macOS backend reports -1 for every non-USB
    # transport (measured: 27 of 34 entries), and max() over an all-equal key
    # returns an arbitrary collection dressed up as a deliberate choice.
    # Refuse instead: a wrong interface fails silently. The one exception is
    # the legacy Linux case of a single hidraw node whose usage page is
    # unknown (0) — there is nothing to choose between.
    numbers = [m.get("interface_number", -1) for m in matches]
    if len(set(numbers)) <= 1:
        if len(matches) == 1 and not matches[0].get("usage_page"):
            return matches[0]
        raise VendorInterfaceUnresolved(
            f"{vid:04X}:{pid:04X} is connected but exposes no 0x{usage_page:04X} usage page, "
            f"and its interface numbers are uninformative ({numbers}) — refusing to guess. "
            f"Collections seen: "
            f"{[(hex(m.get('usage_page') or 0), hex(m.get('usage') or 0)) for m in matches]}"
        )
    log.warning(
        "No 0x%04X usage page found; falling back to highest interface_number. Interfaces: %s",
        usage_page,
        [(m.get("interface_number"), m.get("usage_page")) for m in matches],
    )

    def rank(m):
        up = m.get("usage_page") or 0
        return (m.get("interface_number", -1), 0xFF00 <= up <= 0xFFFF, up)

    return max(matches, key=rank)


# macOS Privacy pane deep link for the Input Monitoring list.
INPUT_MONITORING_URL = (
    "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent"
)

# Usage page macOS always puts behind the Input Monitoring (TCC) gate. A vendor
# page (0xFF00+) is normally exempt, which is why the config interfaces open
# without a prompt (measured on the Win60, 0xFF1B) — but a board that exposes
# its vendor collection on the SAME interface as its keyboard collection
# inherits the gate.
_TCC_GATED_USAGE_PAGE = 0x0001  # Generic Desktop (keyboard/keypad/mouse usages)


def _translate_open_error(ex, name, info):
    """Turn hidapi's opaque open failure into something a user can act on.

    hidapi surfaces every macOS open failure as the same bare 'open failed'
    string — kIOReturnNotPermitted (TCC) and kIOReturnExclusiveAccess (another
    process owns the device) are indistinguishable from Python. So this does
    NOT claim which one it was; it names both and gives the one link that
    fixes the common case. Other platforms get the original exception back.
    """
    if sys.platform != "darwin":
        return ex
    gated = info.get("usage_page") == _TCC_GATED_USAGE_PAGE
    return HidPermissionError(
        f"Could not open {name}. macOS did not say why — the two causes are "
        f"Input Monitoring permission (Privacy & Security → Input Monitoring → "
        f"add and enable Aether, then relaunch: {INPUT_MONITORING_URL}) and another "
        f"process already holding the device exclusively"
        + (
            " — and this collection is on the Generic Desktop usage page, which macOS "
            "always gates, so permission is the likely one."
            if gated else "."
        )
    )


class AulaDevice:
    """Thread-safe wrapper around a single hidraw handle for an Aula HE keyboard.

    By default it targets the Aula Win60 HE (back-compat). Pass a `boards.BoardProfile`
    (or anything exposing `.vid`, `.pid`, `.usage_page`, `.name`) to target another
    registered board — its VID/PID drive enumeration and its `usage_page` selects the
    vendor interface (falling back to the highest interface when None / not found).
    """

    def __init__(self, profile=None):
        self._dev = None
        self._info = None
        self._lock = threading.Lock()
        self._profile = profile
        # Liveness bookkeeping (Api.status() proves the link with these).
        # A write to a stale Windows handle (the board re-enumerated: poll-rate
        # change, replug) can "succeed" and go nowhere, so only a REPLY proves
        # the board is there: _last_rx is the monotonic time of the last
        # non-empty read on this handle. dead_events counts handles this
        # object dropped because an I/O call failed underneath it, so the Api
        # can tell "closed by disconnect()" from "died" (and run recovery)
        # even if something reopened the handle in between.
        self._last_rx = 0.0
        self.dead_events = 0

    def _target(self):
        if self._profile is not None:
            return (self._profile.vid, self._profile.pid,
                    self._profile.usage_page or VENDOR_USAGE_PAGE, self._profile.name)
        return AULA_VID, AULA_PID, VENDOR_USAGE_PAGE, "Aula Win60 HE"

    def present(self):
        """True if the board is enumerated right now (no handle is opened).
        Used to follow a restart: the board drops off USB and comes back."""
        vid, pid, usage_page, _ = self._target()
        try:
            return find_vendor_interface(vid, pid, usage_page) is not None
        except Exception:
            return False

    def open(self):
        vid, pid, usage_page, name = self._target()

        # Idempotent re-open. The app auto-connects at launch, so a later Pair
        # click (or the reconnect watchdog) calls straight back in here on a
        # device already held. A SECOND open_path() on a held device fails
        # outright on macOS, so "open the new handle, then close the old one"
        # can never succeed there and Pair did nothing. While the held
        # handle's path is still enumerated, keep it. A handle that stopped
        # answering is not kept alive by this: status() probes it and
        # mark_dead() drops it, after which this opens a fresh one.
        with self._lock:
            if self._dev is not None:
                held = (self._info or {}).get("path")
                try:
                    present = any(m.get("path") == held
                                  for m in enumerate_interfaces(vid, pid))
                except Exception:
                    present = False
                if present:
                    return dict(self._info)
                # The handle outlived the hardware (unplug, or a replug that
                # issued a new path): fall through and open the new one; the
                # old handle is closed below once the new one is stored.
                log.info("%s handle is stale (device re-enumerated); reopening", name)

        info = find_vendor_interface(vid, pid, usage_page)
        if info is None:
            raise IOError(f"{name} not found (VID:PID {vid:04X}:{pid:04X})")
        dev = hid.device()
        log.info("Opening %s interface %s", name, info["interface_number"])
        try:
            dev.open_path(info["path"])
            dev.set_nonblocking(False)
        except Exception as ex:
            # Don't leak the just-opened handle if set_nonblocking (or the
            # open) fails before we store it — a retry would open a second one.
            try:
                dev.close()
            except Exception:
                pass
            err = _translate_open_error(ex, name, info)
            if err is ex:
                raise
            raise err from ex
        with self._lock:
            # A handle can still be held here when its path went away (see
            # the idempotent re-open above) or when two opens raced: never
            # leak the old hidraw/HID handle.
            old = self._dev
            self._dev = dev
            self._info = info
            # A new handle has proven nothing yet: the first status() after
            # an open probes it instead of trusting the old handle's replies.
            self._last_rx = 0.0
        if old is not None:
            try:
                old.close()
            except Exception:
                pass
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

    # ---- liveness ----
    def note_rx(self):
        """Record that the board just answered. Called by every read path,
        including the readers that drain `_dev` directly under `_lock`."""
        self._last_rx = time.monotonic()

    def rx_age(self):
        """Seconds since the board last answered on this object (inf if never)."""
        t = self._last_rx
        return (time.monotonic() - t) if t else float("inf")

    def last_rx(self):
        return self._last_rx

    def _drop_dead_locked(self, why):
        """Close a handle whose I/O just failed (caller holds _lock)."""
        if self._dev is None:
            return
        log.warning("HID handle dead (%s); closing it", why)
        try:
            self._dev.close()
        except Exception:
            pass
        self._dev = None
        self._info = None
        self.dead_events += 1

    def mark_dead(self, why="I/O failure"):
        """Drop the handle because the link is gone (a probe got no answer,
        a reader's reads keep failing). Next status() reports disconnected."""
        with self._lock:
            self._drop_dead_locked(why)

    def info(self):
        with self._lock:
            return dict(self._info) if self._info else None

    def write(self, payload):
        """Output report. payload[0] MUST be the Report ID (use 0x00 if unset).

        hidapi returns -1 (it does not raise) when the OS refuses the write —
        a handle to a board that re-enumerated. That used to be ignored, so
        every caller reported success to the UI. Now a failed write drops the
        handle (mark-dead) and raises IOError."""
        with self._lock:
            if self._dev is None:
                raise IOError("device not open")
            try:
                n = self._dev.write(payload)
            except (IOError, OSError, ValueError) as e:
                self._drop_dead_locked(f"write raised: {e}")
                raise IOError(f"HID write failed: {e}") from e
            if n is not None and n < 0:
                self._drop_dead_locked("write returned -1")
                raise IOError("HID write failed (device gone?)")
            return n

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
            try:
                r = self._dev.read(length, timeout_ms=timeout_ms)
            except (IOError, OSError, ValueError) as e:
                self._drop_dead_locked(f"read raised: {e}")
                raise IOError(f"HID read failed: {e}") from e
        if r:
            self.note_rx()
        return r

    def read_soft(self, length, timeout_ms=100):
        """Like read(), but one failed read raises WITHOUT closing the handle.
        The board throws a transient read error as it enters calibration
        (WIN 60 HE on Windows, 2026-11-04): read() closed the handle, the
        reconnect dropped the CalibrationReader and calibration never saw a
        key. The caller decides when repeated failures mean the link is gone
        (and then calls mark_dead)."""
        with self._lock:
            if self._dev is None:
                raise IOError("device not open")
            try:
                r = self._dev.read(length, timeout_ms=timeout_ms)
            except (IOError, OSError, ValueError) as e:
                raise IOError(f"HID read failed: {e}") from e
        if r:
            self.note_rx()
        return r

    def set_nonblocking(self, flag):
        """Set the handle's blocking mode under the handle lock. Callers must
        never poke self._dev.set_nonblocking directly — that bypasses the lock
        that serialises handle access against the reader threads."""
        with self._lock:
            if self._dev is None:
                raise IOError("device not open")
            return self._dev.set_nonblocking(bool(flag))
