"""protocol_sayo.py — vendor HID protocol for the SayoDevice-based Aula boards
(VID 0x8089), reverse-engineered from two USBPcap captures of the official app
talking to an Aula WIN 60 HE Pro (8089:0009, CH32V307RBT6 / SI-2825C-CH32-USB-V1.1),
cross-checked against a working third-party script (KBblindtestV3EN.pyw, staged at
docs/context/issue-3-sayodevice-raw/). See data/board_registry.json (slug
`aula-win60he-pro`) and GitHub issue #3.

This is a THIRD transport, different from both `protocol.py` (2E3C) and
`protocol_sonix.py` (0C45). SayoDevice "HID v2" packets:

  [0]=Report ID  [1]=echo  [2..3]=checksum (16-bit LE)  [4..]=TLV commands
  TLV command:   [0..1]=length LE16 (incl. this 4-byte header)  [2]=cmd
                 [3]=index  [4..]=data, zero-padded to a 4-byte multiple
  checksum = sum of all 16-bit LE words of the packet (checksum field zeroed),
             masked to 0xFFFF   (script line 157-159; verified against every
             captured packet's stored checksum)

Two vendor interfaces (script lines 116-138):
  * usage page 0xFF12 — Report ID 0x22, 1024-byte packets (the official app and
    both captures use this one)
  * usage page 0xFF11 — Report ID 0x21, 64-byte packets (management/fallback)

Commands seen in the captures / script:
  * 0x26 lighting     — 48-byte lighting config blob (rgb.pcapng frames 19/23).
                        Only ONE byte differed between the two captured writes:
                        data[3], the effect-mode selector. Everything else is
                        replayed verbatim from the capture; the color-table /
                        brightness field meanings are NOT yet verified.
  * 0x1C key analog   — per-key analog (actuation/rapid-trigger) config write,
                        TLV index = key id, 24-byte payload (actuation.pcapng
                        frame 128, key 0x2F). Payload field semantics UNVERIFIED
                        (only one write in the capture; nothing to diff against),
                        so only a verbatim-replay builder is provided.
  * 0x15 key poll     — repeated 1-byte poll of the selected key while the
                        official app's actuation screen was open (actuation.pcapng
                        frames 22..234; index=1, data=[key id]).
  * 0x0D save         — persist config, data = magic 0x7296 LE (both captures;
                        script line 292-293).
  * 0x0E reboot       — magic 0x7296 + 0x01,0xFE (script line 299; not captured).
  * 0x03 config r/w   — polling-rate/multisampling config block (script only).

build_packet() returns the full wire packet INCLUDING the Report ID byte, so it
can be passed to hidapi write() as-is and asserted byte-for-byte against captures.
"""
import struct

PACKET_SIZE_FF12 = 1024
PACKET_SIZE_FF11 = 64
REPORT_ID_FF12 = 0x22
REPORT_ID_FF11 = 0x21
USAGE_PAGE_FF12 = 0xFF12
USAGE_PAGE_FF11 = 0xFF11

DEFAULT_ECHO = 0x12          # echo byte the official app used in both captures

CMD_CONFIG = 0x03            # read/write config block (reference script)
CMD_SAVE = 0x0D              # persist to flash, data = SAVE_MAGIC
CMD_REBOOT = 0x0E            # reboot, data = SAVE_MAGIC + 01 FE (script only)
CMD_KEY_POLL = 0x15          # poll selected key (actuation screen live read)
CMD_KEY_ANALOG = 0x1C        # per-key analog config write, index = key id
CMD_LIGHTING = 0x26          # lighting config blob

SAVE_MAGIC = 0x7296          # 16-bit LE magic in save/reboot commands

# lighting effect-mode bytes seen in the capture (data[3] of the 0x26 blob);
# the official app toggled 0x01 -> 0x00 when the user changed the RGB effect.
LIGHT_MODE_0 = 0x00
LIGHT_MODE_1 = 0x01

# The 48-byte cmd-0x26 payload captured in rgb.pcapng (frame 19), data[3] (the
# mode byte) zeroed. Bytes [6]=0x27, [7]=0x64(=100, brightness?) and the
# 0xRRGGBBAA-looking groups from [8] on are UNVERIFIED — they never changed
# between the two captured writes, so they are replayed verbatim.
_LIGHT_TEMPLATE = bytes.fromhex(
    "0040ff0000002764"
    "000000ff000000ff000000ff00000000"
    "ff00ffffffff0000ffff0000ffff0000"
    "00aeffff96729672"
)

# The single captured cmd-0x1C payload (actuation.pcapng frame 128, key 0x2F).
# Kept as a reference fixture; field meanings unverified. Plausible-looking
# 16-bit LE values inside it: 0x07D0=2000, 0x012C=300, 0x00E7=231, 0x0082=130
# (candidate travel values in 0.001 mm) — DO NOT rely on this until a second
# capture with different settings confirms which byte is which.
CAPTURED_ANALOG_PAYLOAD = bytes.fromhex(
    "a2780300a278742850020000d0072c01e7000a0f82008200"
)


def checksum(packet):
    """16-bit word-sum checksum over the whole packet with [2..3] zeroed."""
    p = bytearray(packet)
    p[2:4] = b"\x00\x00"
    words = struct.unpack_from(f"<{len(p) // 2}H", p)
    return sum(words) & 0xFFFF


def build_packet(cmds, echo=DEFAULT_ECHO, report_id=REPORT_ID_FF12,
                 packet_size=PACKET_SIZE_FF12):
    """Assemble a full wire packet (Report ID included) from TLV commands.

    `cmds` is a list of (cmd, index, data-bytes) tuples. Layout and checksum
    verified byte-for-byte against every packet in both issue-#3 captures.
    """
    body = b""
    for cmd, index, data in cmds:
        length = len(data) + 4
        body += struct.pack("<HBB", length, cmd & 0xFF, index & 0xFF) + bytes(data)
        while len(body) % 4:
            body += b"\x00"
    packet = bytearray([report_id & 0xFF, echo & 0xFF, 0, 0]) + body
    if len(packet) > packet_size:
        raise ValueError(f"packet too large: {len(packet)} > {packet_size}")
    packet += b"\x00" * (packet_size - len(packet))
    packet[2:4] = struct.pack("<H", checksum(packet))
    return list(packet)


# ---------------- lighting (cmd 0x26) ----------------
def build_lighting(mode, echo=DEFAULT_ECHO):
    """Build the cmd-0x26 lighting packet with effect mode `mode` at data[3].

    Everything except the mode byte is the verbatim captured config blob
    (see _LIGHT_TEMPLATE). build_lighting(1)/(0) reproduce rgb.pcapng frames
    19/23 byte-for-byte.
    """
    data = bytearray(_LIGHT_TEMPLATE)
    data[3] = mode & 0xFF
    return build_packet([(CMD_LIGHTING, 0x00, bytes(data))], echo=echo)


# ---------------- per-key analog / actuation (cmd 0x1C) ----------------
def build_key_analog_raw(key_index, payload, echo=DEFAULT_ECHO):
    """Build a cmd-0x1C per-key analog config write: TLV index = key id,
    24-byte payload. Framing (cmd byte, key-in-index, payload size, checksum)
    is verified against actuation.pcapng frame 128; the payload's internal
    fields are NOT decoded yet, so this only supports verbatim replay."""
    payload = bytes(payload)
    if len(payload) != len(CAPTURED_ANALOG_PAYLOAD):
        raise ValueError(f"analog payload must be {len(CAPTURED_ANALOG_PAYLOAD)} bytes")
    return build_packet([(CMD_KEY_ANALOG, key_index, payload)], echo=echo)


def build_key_poll(key_index, echo=DEFAULT_ECHO):
    """Build the cmd-0x15 selected-key poll the official app streams while its
    actuation screen is open (index=1, data=[key id])."""
    return build_packet([(CMD_KEY_POLL, 0x01, bytes([key_index & 0xFF]))], echo=echo)


# ---------------- save (cmd 0x0D) ----------------
def build_save(echo=DEFAULT_ECHO):
    """Persist the current config (both captures end with this)."""
    return build_packet([(CMD_SAVE, 0x00, struct.pack("<H", SAVE_MAGIC))], echo=echo)
