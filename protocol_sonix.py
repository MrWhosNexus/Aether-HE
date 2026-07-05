"""protocol_sonix.py — vendor HID protocol for the SONiX-based Aula boards
(VID 0x0C45), reverse-engineered from a USBPcap capture of the official
`hub.aulacn.com` WebHID driver talking to an Aula MINI60HE Max (0C45:80A1).
See data/board_registry.json (slug `aula-mini60he-max`) and GitHub issue #4.

This is a DIFFERENT transport from the Aula Win60 (`protocol.py`):
  * Frames are 64 bytes on an **interrupt OUT endpoint** (no HID Report ID in the
    capture), every frame prefixed with magic **0xAA**:
        [0]=0xAA  [1]=command  [2]=length  [3..4]=16-bit LE offset  ...payload
  * The vendor "config" HID collection is at usage page **0xFF68** (not 0xFF1B).

Decoded commands (verified against the capture; see tests/test_protocol_sonix.py
for golden frames):
  * 0x23 lighting  — color + mode + brightness/speed, ends with the 0xAA55 marker.
  * 0x27 actuation — per-key actuation / rapid-trigger records, 16-bit BIG-endian
    values in 0.01 mm units.

hidapi's write() expects a leading Report ID byte; these frames have no Report ID,
so call `to_report(frame)` to prepend 0x00 before writing. The build_* functions
return the raw 64-byte vendor frame (what appears on the wire) so they can be
asserted byte-for-byte against captures.
"""

MAGIC = 0xAA
FRAME_LEN = 64
TRIGGER_UNIT_MM = 0.01

CMD_LIGHTING = 0x23
CMD_ACTUATION = 0x27

# lighting effect mode bytes seen in the capture (byte[8])
LIGHT_MODE_STATIC = 0x02

# actuation record mode byte (byte 1 of each 8-byte record)
ACT_MODE_FIXED = 0xAA   # fixed actuation point (press == release)
ACT_MODE_RT = 0x43      # rapid-trigger (separate press / release), seen as 0x43


def mm_to_raw(mm):
    """Travel in mm -> firmware units (0.01 mm), clamped non-negative."""
    return max(0, round(mm / TRIGGER_UNIT_MM))


def _frame(cmd, length):
    f = [0] * FRAME_LEN
    f[0] = MAGIC
    f[1] = cmd & 0xFF
    f[2] = length & 0xFF
    return f


def to_report(frame, report_id=0x00):
    """Prepend the Report ID byte hidapi.write() expects (these frames have none)."""
    return [report_id & 0xFF] + list(frame)


# ---------------- lighting (cmd 0x23) ----------------
def build_light(mode, r=0x90, g=0xEE, b=0x90, brightness=0x05, speed=0x04,
                flag=0, alpha=0xFF):
    """Build a 0x23 lighting frame.

    Layout (byte indices into the 64-byte frame), from the capture:
      [6]=0x01  [8]=mode  [9..12]=R,G,B,alpha  [16]=flag
      [17]=brightness  [18]=speed  [22..23]=0xAA,0x55 (template marker)

    Defaults reproduce the captured color/brightness/speed so a bare
    build_light(mode) matches the wire frames byte-for-byte.
    """
    f = _frame(CMD_LIGHTING, 0x10)
    f[6] = 0x01
    f[8] = mode & 0xFF
    f[9], f[10], f[11], f[12] = r & 0xFF, g & 0xFF, b & 0xFF, alpha & 0xFF
    f[16] = flag & 0xFF
    f[17] = brightness & 0xFF
    f[18] = speed & 0xFF
    f[22] = 0xAA
    f[23] = 0x55
    return f


# ---------------- actuation / rapid-trigger (cmd 0x27) ----------------
def _act_record(enabled, mode, press_mm, release_mm):
    """8-byte per-key actuation record: [enable][mode][press BE16][release BE16][0][0].
    Values are 0.01 mm, big-endian (capture: 2.00 mm -> 00 c8; 0.50 mm -> 00 32)."""
    p = mm_to_raw(press_mm)
    rel = mm_to_raw(release_mm)
    return [1 if enabled else 0, mode & 0xFF,
            (p >> 8) & 0xFF, p & 0xFF,
            (rel >> 8) & 0xFF, rel & 0xFF, 0x00, 0x00]


def build_actuation_frame(offset, records):
    """Build one 0x27 actuation frame writing `records` at table byte `offset`.

    `records` is a list of (enabled, mode, press_mm, release_mm) tuples. Records
    are packed from byte 9 and the frame is capped at 64 bytes (the firmware's
    last record per frame is truncated — matches the capture). `offset` is the
    16-bit LE table offset at bytes [3..4] (the driver pages by 0x38 = 56).

    NOTE: single-frame encoding (header + record shape + 0.01 mm BE16 values) is
    confirmed against the capture. The multi-frame *table* paging across keys is
    PROVISIONAL — confirm the cross-frame key alignment on hardware before relying
    on it for a full-board write.
    """
    f = _frame(CMD_ACTUATION, 0x38)
    f[3] = offset & 0xFF
    f[4] = (offset >> 8) & 0xFF
    body = []
    for rec in records:
        body.extend(_act_record(*rec))
    # pack from byte 9, truncate at the 64-byte frame boundary
    for i, v in enumerate(body):
        if 9 + i >= FRAME_LEN:
            break
        f[9 + i] = v
    return f
