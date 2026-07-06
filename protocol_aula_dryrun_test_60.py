# AI-DRAFTED — UNVERIFIED, needs on-hardware validation.
"""
Best-effort input-side protocol adapter for the Aula "DryRun Test 60"
(registry slug: aula-dryrun-test-60).

Submission facts used:
  - VID/PID          : 0x2E3C / 0xC365
  - Usage page       : 0xFF1B  (vendor-defined)
  - Interface        : 2
  - report_len       : 64      (padded / zero-tail observed)
  - input reports    : 1 sample, hex "01ab00" at t=5 ms
  - output_pcap      : NOT attached -> all host->device traffic is unknown.

This adapter ONLY attempts to parse HID INPUT reports (device -> host).
No OUTPUT / FEATURE commands are invented. Lighting, per-key RGB,
actuation-point tuning and rapid-trigger configuration remain unimplemented
until a human captures and reverse-engineers an output pcap.
"""

from typing import Iterable, List, Optional, Tuple

# ---- Constants inferred (low confidence) --------------------------------

REPORT_LEN = 64           # declared in submission
USAGE_PAGE = 0xFF1B       # vendor page
EXPECTED_REPORT_ID = 0x01 # byte 0 of the only captured report


# ---- Public API ---------------------------------------------------------

def parse_input_report(data: bytes) -> List[Tuple[int, int]]:
    """
    Parse a single HID input report from the device.

    Returns a list of (vendor_scan_code, state) pairs. The semantics of
    state depend on the device, see NOTES in DECODE_NOTES.md.

    The single captured report is `01 ab 00`. We forward (scan, state)
    tuples and tolerate unknown layouts by emitting a sentinel.
    """
    if data is None or len(data) == 0:
        return []

    # Defensive: pad / truncate to declared report length.
    if len(data) < REPORT_LEN:
        data = data + b"\x00" * (REPORT_LEN - len(data))
    elif len(data) > REPORT_LEN:
        data = data[:REPORT_LEN]

    rid = data[0]
    if rid != EXPECTED_REPORT_ID:
        # Unknown report id; surface whole payload as a single opaque event
        # so callers can still log it for human inspection.
        return [(-1, int.from_bytes(data, "little"))]

    events: List[Tuple[int, int]] = []

    # Hypothesis A: byte 1 = vendor scan code, byte 2 = press/release flag.
    scan = data[1]
    state = data[2]
    if scan:
        events.append((scan, state))

    # Hypothesis B (HE-style): byte 1 / byte 2 jointly encode key index and
    # actuation depth. We don't know which is which, so emit both
    # permutations as advisory events when the second byte is non-zero.
    if state:
        events.append((state, scan))

    return events


def parse_capture(
    reports: Iterable[Tuple[int, str]],
) -> List[Tuple[int, int, List[Tuple[int, int]]]]:
    """
    Parse a sequence of (timestamp_ms, hex_string) input reports.

    Returns [(t_ms, report_id, events), ...] for downstream UI logging.
    """
    out: List[Tuple[int, int, List[Tuple[int, int]]]] = []
    for t, hexstr in reports or []:
        try:
            raw = bytes.fromhex(hexstr)
        except (TypeError, ValueError):
            continue
        rid = raw[0] if raw else -1
        out.append((int(t), rid, parse_input_report(raw)))
    return out


def actuation_depth(hex_data: str) -> Optional[int]:
    """
    Heuristic extraction of an actuation-depth byte (0..255) for HE switches.

    Based on the captured `01 ab 00`, byte 1 (0xAB) is the most likely
    candidate for an analog readout. Returns None if the input is unusable.

    THIS IS NOT VALIDATED. Treat as advisory only.
    """
    if not hex_data or len(hex_data) < 4:
        return None
    try:
        raw = bytes.fromhex(hex_data)
    except ValueError:
        return None
    if len(raw) < 2:
        return None
    return raw[1]


def self_test() -> dict:
    """
    Returns a dict describing what this adapter is and isn't able to do,
    for the UI's "experimental" status badge.
    """
    return {
        "input_decoding": "best-effort, 1 capture sample",
        "output_decoding": "NOT IMPLEMENTED — no pcap",
        "lighting": "unknown",
        "per_key_rgb": "unknown",
        "actuation_point_tuning": "unknown",
        "rapid_trigger": "unknown",
        "validation_state": "AI-DRAFTED — UNVERIFIED",
    }