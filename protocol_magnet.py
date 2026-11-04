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
  SOURCE-ONLY — from the contributor fork (nieruuu19/Aether-HE
  protocol_sparkplay.py), never seen in a capture, so drivers/magnet.py only
  sends them in its experimental mode: 0x23 WRITES (per-key mode/actuation/
  rapid trigger), 0x12 live travel matrix, 0x2C SOCD.

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
# Write payload (44 bytes): [0]=0x01, [1:37]=LIGHT_BLOCK, [37]=flags,
# [38]=brightness 0-4, [39]=mode 0-21, [40]=speed 0-4, [41]=sleep minutes,
# [42]=static sub-mode, [43]=colour slot. LIGHT_BLOCK is byte-identical in all
# 59 captured writes (the fork reads it as a 28-byte colour palette at [7:35];
# not decoded here, sent as captured).
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
                   sleep_min=2, static_mode=0, color_slot=0, super_response=False):
    """CAPTURED lighting write."""
    flags = ((LIGHT_FLAG_POWER if power else 0)
             | (LIGHT_FLAG_DIRECTION if direction else 0)
             | (LIGHT_FLAG_SUPER_RESPONSE if super_response else 0))
    payload = ([OP_WRITE] + list(LIGHT_BLOCK)
               + [flags, _clamp(brightness, 0, LIGHT_LEVEL_MAX), _clamp(mode, 0, LIGHT_MODE_MAX),
                  _clamp(speed, 0, LIGHT_LEVEL_MAX), _clamp(sleep_min, 0, 255),
                  _clamp(static_mode, 0, 255), _clamp(color_slot, 0, 255)])
    return frame(CMD_LIGHTING, payload)


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


# Property ids — SOURCE-ONLY (fork). The capture reads properties 0..25 of
# every key but never writes one, so none of these is confirmed.
PROP_REMAP = 0x00
PROP_ACTUATION = 0x04                  # micrometres
PROP_ACTUATION_2 = 0x05                # the fork writes the same value here too
PROP_MODE = 0x08                       # (touch mode << 4) | advanced-key type
PROP_RT_PRESS = 0x14                   # micrometres
PROP_RT_RELEASE = 0x15                 # micrometres
TOUCH_FIXED = 1
TOUCH_RAPID = 2
TRAVEL_MIN_MM = 0.10                   # driver log: 最小行程 0.10
TRAVEL_MAX_MM = 3.40                   # driver log: 最大行程 3.40


def build_key_config_write(records):
    """SOURCE-ONLY: [0x01] + (key, prop, lo, hi) records, 14 per frame, the
    payload exactly as long as its records (the fork's LayoutDataPack)."""
    out = []
    recs = [(k & 0xFF, p & 0xFF, int(v) & 0xFFFF) for k, p, v in records]
    for i in range(0, len(recs), RECORDS_PER_FRAME):
        payload = [OP_WRITE]
        for k, p, v in recs[i:i + RECORDS_PER_FRAME]:
            payload += [k, p, v & 0xFF, v >> 8]
        out.append(frame(CMD_KEY_CONFIG, payload))
    return out


def mm_to_um(mm):
    return int(round(max(TRAVEL_MIN_MM, min(TRAVEL_MAX_MM, float(mm))) * 1000))


def actuation_records(key_ids, travel_mm, rapid=False, press_mm=0.05, release_mm=0.05):
    """SOURCE-ONLY records for fixed actuation, or single rapid trigger with
    separate press/release distances (the fork's minimal path; its dead-zone
    rewrites are deliberately not ported)."""
    act = mm_to_um(travel_mm)
    mode = ((TOUCH_RAPID if rapid else TOUCH_FIXED) & 0x03) << 4
    recs = []
    for k in key_ids:
        recs += [(k, PROP_MODE, mode), (k, PROP_ACTUATION, act), (k, PROP_ACTUATION_2, act)]
        if rapid:
            recs += [(k, PROP_RT_PRESS, int(round(max(0.01, float(press_mm)) * 1000))),
                     (k, PROP_RT_RELEASE, int(round(max(0.01, float(release_mm)) * 1000)))]
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


# ---- SOCD (0x2C) --------------------------------------------------------- SOURCE-ONLY
def build_socd(key1_id, key2_id, model):
    """SOURCE-ONLY (fork SOCDV4Pack): [1, k1, k2, k1, 0, k2, 0, mode, 0, 0, 0]."""
    k1, k2 = key1_id & 0xFF, key2_id & 0xFF
    return frame(CMD_SOCD, [OP_WRITE, k1, k2, k1, 0, k2, 0, int(model) & 0xFF, 0, 0, 0])
