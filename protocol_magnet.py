"""protocol_magnet.py — packet builders for the Aula WIN 68 HE Max (USB 1CA2:1901).

The board is driven by Aula's web driver magnet.aulastar.com (protocol 1.0.9,
firmware App V1.1.4, hardware V4.4.8 per the driver's own log). Packet
builders only: no I/O, no device access. drivers/magnet.py sends them.

PROVENANCE (markers as in data/board_registry.json):
  CONFIRMED-BY-CAPTURE — tests/fixtures/magnet_win68max_tx.txt holds the 344
  distinct frames the vendor driver sent to a real WIN 68 HE Max (console log
  of its WebHID sendReport, issue #7, contributed by nieruuu19). Every
  builder marked CAPTURED below reproduces those frames byte for byte
  (tests/test_protocol_magnet.py):
    * framing: 64-byte output report, report id 0x00 (WebHID id 0)
      [0]=0x5C magic, [1]=payload length, [2]=command, [3]=checksum,
      [4:4+len]=payload, rest filled (0x00; 0xFF for command 0x2A);
    * checksum = (53 + f[0] + f[1] + f[2] + f[len+3]) & 0xFF, i.e. the seed,
      the three header bytes and the LAST payload byte (all 344 frames);
    * payload byte 0 is the operation: 0x00 read, 0x01 write;
    * 0x18 lighting write (59 frames), 0x2A single-key colour write (135),
      and the read requests 0x18/0x19/0x23/0x29/0x2A/0x2B/0x00/0x01.
  COMMUNITY-TESTED (nieruuu19) — adapted from the contributor fork
  (nieruuu19/Aether-HE protocol_sparkplay.py @ 7de05f2). The fork's author
  ran these on their own WIN 68 HE Max (issue #7); no capture of them
  exists, so they are an owner's report, not a byte-for-byte proof:
  0x23 WRITES (per-key mode / actuation / rapid trigger / dead band), the
  0x2C SOCD frame, palette edits inside the 0x18 write, the batched 0x2A
  colour write, and the layout of every REPLY (the capture holds only what
  the driver sent). drivers/magnet.py sends them by default.
  SOURCE-ONLY — read from the fork's code and nothing else: the firmware
  effect NAMES (bytes 1..20 are captured, their names are not), and the
  0x12 live travel matrix, which drivers/magnet.py only polls with
  AETHER_EXPERIMENTAL=magnet.

KEY IDENTITY: the board names a key by its vendor key id, which is the key's
default HID usage (Esc 0x29, 1 0x1E, ..., Fn 0x01) = the layout's hidCode.
The device index Aether uses (layout `index`, the matrix slot row*21+col,
21..119) only appears in the live travel matrix.
"""

REPORT_ID = 0x00
FRAME_LEN = 64
MAGIC = 0x5C
CHECKSUM_SEED = 53

OP_READ = 0x00
OP_WRITE = 0x01

CMD_SYS = 0x00
CMD_HELLO = 0x01
CMD_TRAVEL_MATRIX = 0x12
CMD_LIGHTING = 0x18
CMD_AMBIENT = 0x19
CMD_KEY_CONFIG = 0x23
CMD_GLOBAL_TRAVEL = 0x29
CMD_KEY_RGB = 0x2A
CMD_HID_MATRIX = 0x2B
CMD_SOCD = 0x2C

RECORDS_PER_FRAME = 14                 # 4-byte key records in one 57-byte payload
RECORD_PAYLOAD_LEN = 1 + 4 * RECORDS_PER_FRAME

# The 68 vendor key ids in the order the driver walks them (every 0x23 / 0x2A
# read in the capture uses exactly this order). CAPTURED.
KEY_ORDER = (
    0x29, 0x1E, 0x1F, 0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x2D, 0x2E, 0x2A,
    0x49, 0x2B, 0x14, 0x1A, 0x08, 0x15, 0x17, 0x1C, 0x18, 0x0C, 0x12, 0x13, 0x2F, 0x30,
    0x31, 0x4C, 0x39, 0x04, 0x16, 0x07, 0x09, 0x0A, 0x0B, 0x0D, 0x0E, 0x0F, 0x33, 0x34,
    0x28, 0x4B, 0xE1, 0x1D, 0x1B, 0x06, 0x19, 0x05, 0x11, 0x10, 0x36, 0x37, 0x38, 0xE5,
    0x52, 0x4E, 0xE0, 0xE3, 0xE2, 0x2C, 0xE6, 0x01, 0xE4, 0x50, 0x51, 0x4F,
)

# ---- lighting (0x18) ---------------------------------------------------- CAPTURED
# Write payload (44 bytes): [0]=0x01, [1:37]=palette block, [37]=flags,
# [38]=brightness 0-4, [39]=mode 0-21, [40]=speed 0-4, [41]=sleep minutes,
# [42]=static colour (0-6 = palette slot, 7 = spectrum), [43]=effect colour
# (0 = spectrum, 1-7 = palette slot 0-6). The block is byte-identical in all
# 59 captured writes: 4 zero bytes, 7 palette slots of (B, G, R, 0xFF), 4 zero
# bytes. LIGHT_BLOCK decodes to red, green, yellow, blue, magenta, cyan, white
# (the capture's values; the slot layout is the fork's reading of it).
LIGHT_BLOCK = bytes.fromhex(
    "000000000000"
    "ffff00ff00ff007f7fffff0000ff7f007fff7f7f00ff7f7f7fff0000"
    "0000")
LIGHT_FLAG_POWER = 0x01                # CAPTURED (0 = lights off)
LIGHT_FLAG_DIRECTION = 0x02            # CAPTURED (log: 方向 true)
LIGHT_FLAG_SUPER_RESPONSE = 0x10       # SOURCE-ONLY (fork)
LIGHT_MODE_STATIC = 0                  # log: 灯光模式 0 with 静态灯效模式
LIGHT_MODE_CUSTOM = 21                 # per-key colours (driver reads RGB after selecting it)
LIGHT_MODE_MAX = 21
LIGHT_LEVEL_MAX = 4
LIGHT_READ_PAYLOAD = bytes([0] * 5) + b"\xff" * 28 + bytes([0] * 10)   # CAPTURED (len 43)
LIGHT_BLOCK_LEN = 36
LIGHT_SLEEP_CAPTURED = 2               # what the frame carries when the board's state is unknown
PALETTE_SLOTS = 7
PALETTE_OFFSET = 4                     # first slot inside the block (payload byte 5)
STATIC_SPECTRUM = 7                    # payload[42]: CAPTURED value, meaning from the fork
EFFECT_SPECTRUM = 0                    # payload[43]: CAPTURED value, meaning from the fork

# Firmware effects. The mode BYTES are CONFIRMED-BY-CAPTURE (the vendor driver
# selected every mode 0..21). The NAMES are SOURCE-ONLY: they are the fork's
# list (its registry entry, from the vendor bundle's effect order) and nobody
# has matched a name to what a board shows. (byte, registry id, name).
LIGHT_EFFECTS = (
    (1, "fw-rippling-water", "Rippling Water"),
    (2, "fw-tide-flux", "Tide Flux"),
    (3, "fw-soft-ripples", "Soft Ripples"),
    (4, "fw-spinning-storm", "Spinning Storm"),
    (5, "fw-lucky-rainbow", "Lucky Rainbow"),
    (6, "fw-glowing-rainbow", "Glowing Rainbow"),
    (7, "fw-radiant-glow", "Radiant Glow"),
    (8, "fw-shifting-panes", "Shifting Panes"),
    (9, "fw-wave-shift", "Wave Shift"),
    (10, "fw-shape-shift", "Shape Shift"),
    (11, "fw-sine-wave", "Sine Wave"),
    (12, "fw-smooth-flow", "Smooth Flow"),
    (13, "fw-blooming-flowers", "Blooming Flowers"),
    (14, "fw-colorful-pattern", "Colorful Pattern"),
    (15, "fw-heavy-rain", "Heavy Rain"),
    (16, "fw-eternal-pulse", "Eternal Pulse"),
    (17, "fw-traceless-steps", "Traceless Steps"),
    (18, "fw-snow-blossoms", "Snow Blossoms"),
    (19, "fw-laser-beam", "Laser Beam"),
    (20, "fw-water-ripples", "Water Ripples"),
)
LIGHT_EFFECT_MIN = 1
LIGHT_EFFECT_MAX = 20


def checksum(pkt):
    """CAPTURED: seed + magic + length + command + last payload byte."""
    n = pkt[1] & 0xFF
    t = CHECKSUM_SEED + (pkt[0] & 0xFF) + n + (pkt[2] & 0xFF)
    if 0 < n <= FRAME_LEN - 4:
        t += pkt[n + 3] & 0xFF
    return t & 0xFF


def frame(cmd, payload, fill=0x00):
    """One 64-byte frame (no report id)."""
    payload = [int(b) & 0xFF for b in payload]
    if len(payload) > FRAME_LEN - 4:
        raise ValueError(f"payload too long: {len(payload)} > {FRAME_LEN - 4}")
    pkt = [fill & 0xFF] * FRAME_LEN
    pkt[0] = MAGIC
    pkt[1] = len(payload)
    pkt[2] = cmd & 0xFF
    pkt[4:4 + len(payload)] = payload
    pkt[3] = checksum(pkt)
    return pkt


def to_report(pkt):
    """Prefix the report id for hidapi's write()."""
    return [REPORT_ID] + list(pkt)


def is_valid(pkt):
    """True for a well-formed 64-byte frame with a correct checksum."""
    return (len(pkt) == FRAME_LEN and pkt[0] == MAGIC
            and pkt[1] <= FRAME_LEN - 4 and pkt[3] == checksum(pkt))


def _clamp(v, lo, hi):
    return max(lo, min(hi, int(v)))


def build_lighting(mode, brightness=4, speed=3, power=True, direction=False,
                   sleep_min=None, static_mode=0, color_slot=0, super_response=False,
                   block=None):
    """CAPTURED lighting write.

    `block` is the 36-byte palette block to send; None sends the capture's
    (LIGHT_BLOCK). `sleep_min` None sends the capture's 2 minutes. A caller
    that has read the board's state passes both back so a write does not
    reset them. `color_slot` None leaves payload byte 43 out (a board whose
    own reply is 43 bytes long has no such field)."""
    block = bytes(LIGHT_BLOCK if block is None else block)
    if len(block) != LIGHT_BLOCK_LEN:
        raise ValueError(f"palette block must be {LIGHT_BLOCK_LEN} bytes, got {len(block)}")
    flags = ((LIGHT_FLAG_POWER if power else 0)
             | (LIGHT_FLAG_DIRECTION if direction else 0)
             | (LIGHT_FLAG_SUPER_RESPONSE if super_response else 0))
    payload = ([OP_WRITE] + list(block)
               + [flags, _clamp(brightness, 0, LIGHT_LEVEL_MAX), _clamp(mode, 0, LIGHT_MODE_MAX),
                  _clamp(speed, 0, LIGHT_LEVEL_MAX),
                  _clamp(LIGHT_SLEEP_CAPTURED if sleep_min is None else sleep_min, 0, 255),
                  _clamp(static_mode, 0, 255)])
    if color_slot is not None:
        payload.append(_clamp(color_slot, 0, 255))
    return frame(CMD_LIGHTING, payload)


def palette_from_block(block):
    """The 7 stored colours of a palette block as (r, g, b). Layout from the
    fork; it decodes the captured block to R, G, Y, B, M, C, W."""
    block = bytes(block)
    out = []
    for i in range(PALETTE_SLOTS):
        o = PALETTE_OFFSET + 4 * i
        out.append((block[o + 2], block[o + 1], block[o]))
    return out


def block_with_palette_slot(block, slot, rgb):
    """COMMUNITY-TESTED (nieruuu19): `block` with one palette slot replaced.
    Every other byte is kept as it was."""
    if not 0 <= int(slot) < PALETTE_SLOTS:
        raise ValueError(f"palette slot must be 0..{PALETTE_SLOTS - 1}")
    out = bytearray(block)
    if len(out) != LIGHT_BLOCK_LEN:
        raise ValueError(f"palette block must be {LIGHT_BLOCK_LEN} bytes, got {len(out)}")
    r, g, b = (int(v) & 0xFF for v in list(rgb)[:3])
    o = PALETTE_OFFSET + 4 * int(slot)
    out[o:o + 4] = bytes([b, g, r, 0xFF])
    return bytes(out)


def build_lighting_read():
    """CAPTURED read request for the lighting settings."""
    return frame(CMD_LIGHTING, LIGHT_READ_PAYLOAD)


def build_ambient_read():
    """CAPTURED read request for the ambient (side) light settings."""
    return frame(CMD_AMBIENT, LIGHT_READ_PAYLOAD)


# ---- per-key colour (0x2A) ------------------------------------------------- CAPTURED
def build_key_rgb(key_id, r, g, b):
    """CAPTURED single-key colour write: [0x01, key id, r, g, b], 0xFF fill."""
    return frame(CMD_KEY_RGB, [OP_WRITE, key_id, r, g, b], fill=0xFF)


def build_key_rgb_batch(records):
    """COMMUNITY-TESTED (nieruuu19): several keys per frame, [0x01] +
    (key id, r, g, b) records, up to 14 per frame, the payload exactly as
    long as its records, 0xFF fill. The vendor driver wrote one key per
    frame in the capture (build_key_rgb); this is the form the fork sends."""
    recs = [(int(k) & 0xFF, int(r) & 0xFF, int(g) & 0xFF, int(b) & 0xFF)
            for k, (r, g, b) in records]
    out = []
    for i in range(0, len(recs), RECORDS_PER_FRAME):
        payload = [OP_WRITE]
        for rec in recs[i:i + RECORDS_PER_FRAME]:
            payload += list(rec)
        out.append(frame(CMD_KEY_RGB, payload, fill=0xFF))
    return out


def build_key_rgb_read(key_ids=KEY_ORDER):
    """CAPTURED per-key colour read requests: [0x00] + (key, 0, 0, 0) records,
    14 per frame, unused records (0xFF, 0, 0, 0), 0xFF fill."""
    return _record_frames(CMD_KEY_RGB, [(k, 0, 0, 0) for k in key_ids],
                          pad=(0xFF, 0, 0, 0), fill=0xFF)


# ---- per-key config (0x23) ---------------------------------------------------
def build_key_config_read(prop, key_ids=KEY_ORDER):
    """CAPTURED read requests for one property of every key: [0x00] +
    (key, prop, 0, 0) records, 14 per frame, unused records (FF, FF, FF, 00)."""
    return _record_frames(CMD_KEY_CONFIG, [(k, prop, 0, 0) for k in key_ids],
                          pad=(0xFF, 0xFF, 0xFF, 0x00), fill=0x00)


# Property ids. The capture READS properties 0..25 of every key (CAPTURED
# requests) but never writes one; ids, meanings and the write frame are
# COMMUNITY-TESTED (nieruuu19).
PROP_REMAP = 0x00
PROP_ACTUATION = 0x04                  # micrometres
PROP_ACTUATION_2 = 0x05                # the fork writes the same value here too
PROP_MODE = 0x08                       # (touch mode << 4) | advanced-key type
PROP_RT_PRESS = 0x14                   # micrometres
PROP_RT_RELEASE = 0x15                 # micrometres
PROP_DEAD_TOP = 0x16                   # press dead band, micrometres
PROP_DEAD_BOTTOM = 0x17                # release dead band, micrometres
TOUCH_GLOBAL = 0                       # the key follows the board-wide table
TOUCH_FIXED = 1
TOUCH_RAPID = 2
ADV_NONE = 0
ADV_SOCD = 8                           # advanced-key nibble of a key in a SOCD pair
TRAVEL_MIN_MM = 0.10                   # driver log: 最小行程 0.10
TRAVEL_MAX_MM = 3.40                   # driver log: 最大行程 3.40
DEAD_MAX_UM = 1000
DEAD_DEFAULT_UM = 200                  # the fork's value for a key whose own is unknown
STANDARD_RT_DEAD_GAP_UM = 10           # Standard RT: press dead band = actuation - 0.01 mm
STANDARD_RT_DEAD_MIN_UM = 50
STANDARD_RT_DEAD_MAX_UM = 3390
# The app's trigger modes (Api._TRIGGER_MODES).
MODE_FIXED = 0
MODE_RT_STANDARD = 12
MODE_RT_CONTINUOUS = 13


def build_key_config_write(records):
    """COMMUNITY-TESTED (nieruuu19): [0x01] + (key, prop, lo, hi) records, 14
    per frame, the payload exactly as long as its records (the fork's
    LayoutDataPack)."""
    out = []
    recs = [(k & 0xFF, p & 0xFF, int(v) & 0xFFFF) for k, p, v in records]
    for i in range(0, len(recs), RECORDS_PER_FRAME):
        payload = [OP_WRITE]
        for k, p, v in recs[i:i + RECORDS_PER_FRAME]:
            payload += [k, p, v & 0xFF, v >> 8]
        out.append(frame(CMD_KEY_CONFIG, payload))
    return out


def mm_to_um(mm, lo_mm=TRAVEL_MIN_MM, hi_mm=TRAVEL_MAX_MM):
    return int(round(max(lo_mm, min(hi_mm, float(mm))) * 1000))


def mode_value(touch, adv):
    """Property 0x08: touch mode in the high nibble, advanced-key type in the low."""
    return ((int(touch) & 0x0F) << 4) | (int(adv) & 0x0F)


def split_mode(value):
    """(touch mode, advanced-key type) of a property 0x08 value."""
    return (int(value) >> 4) & 0x0F, int(value) & 0x0F


def standard_rt_dead_um(travel_um):
    """Standard RT pins the press dead band 0.01 mm above the actuation point
    (the fork, after the vendor driver)."""
    return _clamp(int(travel_um) - STANDARD_RT_DEAD_GAP_UM,
                  STANDARD_RT_DEAD_MIN_UM, STANDARD_RT_DEAD_MAX_UM)


def dead_um(um):
    return _clamp(um, 0, DEAD_MAX_UM)


def actuation_records(key_ids, travel_mm, mode=MODE_FIXED, adv_by_key=None,
                      press_mm=None, release_mm=None, dead_by_key=None,
                      lo_mm=TRAVEL_MIN_MM, hi_mm=TRAVEL_MAX_MM):
    """COMMUNITY-TESTED (nieruuu19) records for one trigger write.

    `mode` is the app's trigger mode: 0 fixed, 12 Standard rapid trigger,
    13 Continuous rapid trigger. Standard and Continuous are the same touch
    mode on the wire; the press dead band tells them apart (Standard pins it
    just above the actuation point, Continuous keeps the user's).

    `adv_by_key` {key id: advanced-key nibble} is REQUIRED for every key: the
    mode property carries the key's advanced binding (SOCD, macro, ...) in
    its low nibble, and writing 0 there drops it. A missing key raises
    KeyError; the caller reads the board first.

    `press_mm` / `release_mm` None leaves the stored rapid-trigger pair
    alone. `dead_by_key` {key id: (top um, bottom um)} is written for fixed
    and Continuous keys that have an entry; Standard RT writes its own top."""
    mode = int(mode)
    if mode not in (MODE_FIXED, MODE_RT_STANDARD, MODE_RT_CONTINUOUS):
        raise ValueError(f"unknown trigger mode {mode}")
    if adv_by_key is None:
        raise KeyError("adv_by_key is required: read the board's key modes first")
    act = mm_to_um(travel_mm, lo_mm, hi_mm)
    rapid = mode != MODE_FIXED
    touch = TOUCH_RAPID if rapid else TOUCH_FIXED
    recs = []
    for k in key_ids:
        recs += [(k, PROP_MODE, mode_value(touch, adv_by_key[k])),
                 (k, PROP_ACTUATION, act), (k, PROP_ACTUATION_2, act)]
        if mode == MODE_RT_STANDARD:
            recs.append((k, PROP_DEAD_TOP, standard_rt_dead_um(act)))
        elif dead_by_key and k in dead_by_key:
            top, bottom = dead_by_key[k]
            recs += [(k, PROP_DEAD_TOP, dead_um(top)), (k, PROP_DEAD_BOTTOM, dead_um(bottom))]
        if rapid and press_mm is not None and release_mm is not None:
            recs += [(k, PROP_RT_PRESS, int(round(max(0.01, float(press_mm)) * 1000))),
                     (k, PROP_RT_RELEASE, int(round(max(0.01, float(release_mm)) * 1000)))]
    return recs


def deadband_records(dead_by_key, skip_top=()):
    """COMMUNITY-TESTED (nieruuu19): (key, 0x16, top um), (key, 0x17, bottom um)
    per key, 0..1000 um. Keys in `skip_top` (Standard RT, whose top is pinned
    to the actuation point) get only the bottom record."""
    recs = []
    for k, (top, bottom) in dead_by_key.items():
        if k not in skip_top:
            recs.append((k, PROP_DEAD_TOP, dead_um(top)))
        recs.append((k, PROP_DEAD_BOTTOM, dead_um(bottom)))
    return recs


def _record_frames(cmd, records, pad, fill):
    out = []
    for i in range(0, len(records), RECORDS_PER_FRAME):
        chunk = list(records[i:i + RECORDS_PER_FRAME])
        chunk += [pad] * (RECORDS_PER_FRAME - len(chunk))
        payload = [OP_READ]
        for rec in chunk:
            payload += list(rec)
        out.append(frame(cmd, payload, fill=fill))
    return out


# ---- other captured read requests -----------------------------------------------
def build_hello():
    """CAPTURED first frame the driver sends."""
    return frame(CMD_HELLO, [0x01, 0x02, 0x03, 0x04, 0xFF, 0xFF])


def build_sys_query(sub):
    """CAPTURED system query [sub, 0xFF, 0xFF] (subs 0x01 0x21 0x22 0x25 0x26 0x76 seen)."""
    return frame(CMD_SYS, [sub, 0xFF, 0xFF])


def build_global_travel_read():
    """CAPTURED read of the global actuation / dead zones."""
    return frame(CMD_GLOBAL_TRAVEL, [0] * 15)


def build_hid_matrix_read(page):
    """CAPTURED HID-matrix read, two layer pages per frame ([0, 2p, 2p+1])."""
    return frame(CMD_HID_MATRIX, [0x00, 2 * page, 2 * page + 1])


# ---- replies ------------------------------------------- COMMUNITY-TESTED (nieruuu19)
# The capture holds only what the vendor driver SENT. Every reply layout below
# is the fork's, which its author ran against their board.
REPLY_MAGICS = (MAGIC, MAGIC | 0x80)
PROTOCOL_SOCD_V4 = (1, 0, 7)           # first protocol version with the 11-byte SOCD frame


def strip_report_id(report):
    """A read may or may not carry the report id (0x00) in front."""
    r = list(report or [])
    if len(r) == FRAME_LEN + 1 and r[0] == REPORT_ID:
        r = r[1:]
    return r


def reply_body(report, cmd):
    """The payload of a reply to `cmd`, or None when `report` is not one:
    magic 0x5C or 0xDC, command (bit 7 ignored) = `cmd`, and a length that
    fits the report."""
    r = strip_report_id(report)
    if len(r) < 5 or r[0] not in REPLY_MAGICS:
        return None
    if (r[2] & 0x7F) != (cmd & 0x7F):
        return None
    n = r[1]
    if n < 1 or n > FRAME_LEN - 4 or len(r) < 4 + n:
        return None
    return r[4:4 + n]


def parse_key_config_reply(body):
    """[(key id, property, value)] from a 0x23 reply body: 4-byte records
    (key, prop, lo, hi) from body[1]; padding (key 0 / 0xFF, prop 0xFF) is
    skipped."""
    out = []
    for i in range(1, len(body) - 3, 4):
        key, prop = body[i], body[i + 1]
        if key in (0x00, 0xFF) or prop == 0xFF:
            continue
        out.append((key, prop, body[i + 2] | (body[i + 3] << 8)))
    return out


def parse_version(body):
    """(major, minor, patch) from a CMD_SYS sub 1 reply body, or None."""
    if len(body) < 4 or body[1] != 0x01:
        return None
    return (body[3] & 0x0F, (body[2] >> 4) & 0x0F, body[2] & 0x0F)


def parse_travel_limits(body):
    """{"precision_mm", "min_mm", "max_mm"} from a CMD_SYS sub 0x25 reply
    body, or None (also for a reply whose range is empty)."""
    if len(body) < 7 or body[1] != 0x25:
        return None
    lo = (body[3] | (body[4] << 8)) / 1000.0
    hi = (body[5] | (body[6] << 8)) / 1000.0
    if not 0 < lo < hi:
        return None
    return {"precision_mm": body[2] / 1000.0, "min_mm": lo, "max_mm": hi}


def parse_device_name(body):
    """The device name from a CMD_SYS sub 0x26 reply body, or None."""
    if len(body) < 3 or body[1] != 0x26:
        return None
    raw = bytes(body[2:34]).split(b"\x00", 1)[0]
    return raw.decode("utf-8", "ignore").strip() or None


def parse_lighting_reply(body):
    """The board's lighting state from a 0x18 reply body, or None when the
    body is too short to hold it (< 43 bytes). `block` (payload 1..36) and
    `sleep_min` / `static_mode` / `color_slot` are what a write must send
    back to leave them unchanged; `color_slot` is None on a 43-byte reply."""
    if len(body) < 43:
        return None
    flags = body[37]
    return {
        "block": bytes(body[1:37]),
        "power": bool(flags & LIGHT_FLAG_POWER),
        "direction": bool(flags & LIGHT_FLAG_DIRECTION),
        "super_response": bool(flags & LIGHT_FLAG_SUPER_RESPONSE),
        "brightness": body[38],
        "mode": body[39],
        "speed": body[40],
        "sleep_min": body[41],
        "static_mode": body[42],
        "color_slot": body[43] if len(body) > 43 else None,
    }


# ---- live travel matrix (0x12) ------------------------------------------ SOURCE-ONLY
TRAVEL_COLS = 21
TRAVEL_HALF_KEYS = 63                  # 3 rows x 21 columns per half
TRAVEL_REPLY_CMD = CMD_TRAVEL_MATRIX | 0x80
TRAVEL_REPLY_LEN = 132                 # 6-byte header + 63 x u16
TRAVEL_UM_MIN = 30
TRAVEL_UM_MAX = 4500


def build_travel_request(half):
    """SOURCE-ONLY: ask for one half (1 = rows 0-2, 2 = rows 3-5) of the
    6x21 depth matrix."""
    if half not in (1, 2):
        raise ValueError("half must be 1 or 2")
    return frame(CMD_TRAVEL_MATRIX, [0x02, half, 0xFF, 0xFF])


def is_travel_reply_head(report):
    """SOURCE-ONLY: first report of a 0x12 reply (magic 0x5C or 0xDC,
    command 0x92, sub-command 0x02 at [5])."""
    return (len(report) >= 6 and report[0] in (MAGIC, MAGIC | 0x80)
            and report[2] == TRAVEL_REPLY_CMD and report[5] == 0x02)


def parse_travel_reply(data, half):
    """SOURCE-ONLY: {device index: mm} from a reassembled reply (>= 132
    bytes: the head report followed by its continuation reports). Values
    outside 30..4500 um read as 0 (a key at rest)."""
    if len(data) < TRAVEL_REPLY_LEN:
        raise ValueError("short travel reply")
    base = (half - 1) * TRAVEL_HALF_KEYS
    out = {}
    for i in range(TRAVEL_HALF_KEYS):
        um = data[6 + 2 * i] | (data[7 + 2 * i] << 8)
        out[base + i] = um / 1000.0 if TRAVEL_UM_MIN <= um <= TRAVEL_UM_MAX else 0.0
    return out


# ---- SOCD (0x2C) --------------------------------------- COMMUNITY-TESTED (nieruuu19)
SOCD_MODELS = (1, 2, 3, 4)             # the app's "Model N": last input, key 1, key 2, neutral
SOCD_DELAY_MAX_MS = 50
SOCD_BIND_POSITION = 0                 # pair the two physical keys
SOCD_BIND_VALUES = 1                   # pair two key values


def build_socd(key1_id, key2_id, model, bind=SOCD_BIND_POSITION, delay_ms=0,
               value1=None, value2=None):
    """COMMUNITY-TESTED (nieruuu19), protocol 1.0.7 and later:
    [1, key1, key2, value1 u16, value2 u16, bind, mode, delay u16].

    `model` is the app's Model 1..4; the wire mode is model - 1 (0 last input
    priority, 1 key 1 priority, 2 key 2 priority, 3 neutral). Anything else
    raises ValueError. Position binding sends zero in both value slots; value
    binding sends the two key ids unless `value1` / `value2` say otherwise.
    `delay_ms` is clamped to 0..50."""
    model = int(model)
    if model not in SOCD_MODELS:
        raise ValueError(f"SOCD model must be 1..4, got {model}")
    k1, k2 = int(key1_id) & 0xFF, int(key2_id) & 0xFF
    bind = SOCD_BIND_VALUES if int(bind) else SOCD_BIND_POSITION
    if bind == SOCD_BIND_POSITION:
        v1 = v2 = 0
    else:
        v1 = (k1 if value1 is None else int(value1)) & 0xFFFF
        v2 = (k2 if value2 is None else int(value2)) & 0xFFFF
    delay = _clamp(delay_ms, 0, SOCD_DELAY_MAX_MS)
    return frame(CMD_SOCD, [OP_WRITE, k1, k2, v1 & 0xFF, v1 >> 8, v2 & 0xFF, v2 >> 8,
                            bind, model - 1, delay & 0xFF, delay >> 8])
