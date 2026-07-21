"""protocol_mini60.py — vendor HID protocol for the Aula MINI 60 HE PRO
(VID 0x0C45, PID 0x80A2 over USB-C wired, AND VID 0x0C45, PID 0xFEFE over
the 2.4GHz dongle — same protocol, half the frame size; see FRAME SIZES).

Sources, in order of authority:

  1. docs/context/issue-6-mini60-pro-raw/HFD_SDK_DECODE.md — decode of the
     official hub.aulacn.com driver SDK source (hfd-sdk.es-CGV2WPaF.js et al).
     This is the layout authority for every table in this module.
  2. docs/context/issue-6-mini60-pro-raw/webhid-capture-2026-07-20.json —
     WebHID capture of that driver driving the real board (457 frames).
     Golden tests replay it byte-for-byte (tests/test_protocol_mini60.py).
  3. docs/context/issue-6-mini60-pro-raw/webhid-capture-dongle-2026-07-20.json
     + WIRELESS_DONGLE_FINDINGS.md — WebHID capture of the same driver
     driving the same board over its 2.4GHz dongle (0C45:FEFE), USB-C cable
     unplugged. The JSON (second session) holds a full 0x17 sweep, a 0x11
     read and a complete 0x27 write pass; the first session's 0x23/0x13
     lighting frames were transcribed by hand before the in-page buffer was
     lost (CONFIRMED-BY-CAPTURE (transcribed) — real observed bytes, no
     re-parseable file).
  4. Direct hardware experiments on the physical board (noted per-claim).

FRAME SIZES (the wireless finding, 2026-07-20): the dongle speaks this SAME
protocol with an IDENTICAL header and command set, at HALF the frame size —
32 bytes instead of 64. The payload chunk is always frameLen - 8 (wired
0x38 = 56, wireless 0x18 = 24) and table geometry is unchanged (the dongle's
captured actuation write ends at offset 0x03D8 + 24 = 0x3F0, the same
1008-byte table as wired). Every builder and paging helper therefore takes a
`frame_len` parameter DEFAULTING TO THE WIRED 64, so all existing call sites
are byte-identical; pass FRAME_LEN_WIRELESS (32) for the dongle. NEVER
hardcode a frame size when driving hardware — size frames from the board
profile. An earlier probe concluded the dongle spoke a different protocol
because it sent 64-byte frames at the dongle's 32-byte-report 0xFF60
interface: hidapi truncated the write (n = 33 = report id + 32) and the
malformed frame was never answered. The negative result was an artifact of
the wrong frame size, not an incompatible device.

DONGLE DRIVABILITY CAVEAT (2026-07-20, hardware probe): although the
protocol is CONFIRMED-BY-CAPTURE, no raw hidapi collection on 0C45:FEFE
answers it yet. Correctly sized 32-byte 0x13 queries got: iface 2 (0xFFFF)
write rejected (-1); iface 3 (0xFF60, the QMK/VIA raw-HID signature) write
ACCEPTED (33) but NO reply — it absorbs arbitrary reports and does nothing,
a black hole that also produced a fake 23.8 fps "streaming benchmark" with
zero errors while the keyboard stayed dark (accepted-but-ignored is NOT
working — judge only on a valid 0x55 reply); iface 4 (0xFF59) has 64-byte
reports and replies `0F 01 01 11 ...`, a different protocol. Either the
vendor page holds a collection not yet identified or there is an
uncaptured handshake/pairing step. Until that is resolved the dongle
registry entry stays protocol: null / non-drivable.

Verification labels used on every claim below and in the function docstrings:
  CONFIRMED-BY-CAPTURE — byte-for-byte matched against real captured frames.
  HARDWARE-VERIFIED    — exercised on the physical board (e.g. write/read-back
                         round trip), but no captured frames exist for it.
  SOURCE-ONLY          — read from the vendor SDK source; never observed on
                         the wire. Plausible, not proven.

Vendor interface: usage page 0xFF68, usage 0x61, output/input report ID 0.

This is the SAME 0xAA envelope family as protocol_sonix (MINI60HE Max,
0C45:80A1) but a DIFFERENT device with different field semantics:
  * the actuation-table travel values are 16-bit LITTLE-endian here
    (the Max used big-endian — do not copy protocol_sonix's byte order);
  * the per-key actuation record layout is the HFD SDK's
    [axisType][flags][trip][rtPress][rtRelease] (see below);
  * lighting frame byte [16] is the SDK's colorMode (= randomColor ? 1 : 0).
    CORRECTION 2026-07-20: this byte was long recorded as "must be 1"
    because every wired-capture frame carried 1 and an early hardware probe
    that sent 0 appeared to no-op — a single-valued sample mistaken for a
    constant. The WIRELESS capture shows BOTH values, correlated exactly
    with the mode's nature: fixed-colour modes (Static 0x01, Reactive
    Single 0x02, Starry Sky 0x04, Dynamic Breathing 0x07) send 0;
    multicolour/random modes (Spectrum 0x08, Ripple 0x0F, Mountains 0x11,
    Rain 0x12, Shuttle 0x13) send 1 — matching the SDK source precisely.
    build_light() now takes color_mode as a parameter, DEFAULTING to 1 so
    legacy callers stay byte-identical with the wired capture; drivers
    should derive it from the selected mode (registry modes[].color ===
    false => forced-random => 1). See HFD_SDK_DECODE.md §8 +
    WIRELESS_DONGLE_FINDINGS.md.

Frame envelope (64 bytes wired / 32 bytes wireless, no HID Report ID; use
to_report() to prepend the 0x00 byte hidapi.write() expects) —
CONFIRMED-BY-CAPTURE on both transports and matching the SDK frame builder
exactly:

    [0]    0xAA on requests; replies echo the request frame with 0x55 here
    [1]    command
    [2]    content length of THIS chunk (wired: 0x08 / 0x10 / 0x38 observed;
           wireless: 0x10 / 0x18 observed)
    [3..4] 16-bit LITTLE-endian table byte offset (tables page by the
           payload chunk = frameLen - 8: 0x38 wired, 0x18 wireless)
    [5]    0 (SDK writes 0)
    [6]    LAST-CHUNK flag: 0x01 on the final chunk of a transfer.
           Single-chunk commands (0x10, 0x13, 0x23) always carry 0x01;
           paged commands carry it only on the last page.
    [7]    0 (SDK writes 0)
    [8..]  payload — chunk size is frameLen - 8 (wired 56 = 0x38, wireless
           24 = 0x18), so a full page fits EXACTLY in the frame tail. (An
           earlier capture-only reading placed the payload at [9..] with a
           phantom "truncated last byte"; the SDK source settles it at
           [8..].)

Commands used by this module (SDK names from the driver's command enum):

  0x10 GET_DEVICE_INFO       CONFIRMED-BY-CAPTURE — single empty frame; the
                             reply carries VID/PID LE16 at reply[12..13] /
                             reply[14..15] (45 0C / A2 80 in the capture).
                             Further fields exist (fw version at [16..17],
                             etc. — HFD_SDK_DECODE.md §3) but only VID/PID
                             are parsed here.
  0x11 GET_GAME_MODE         CONFIRMED-BY-CAPTURE — paged read of the
                             64-byte global settings table (report rate,
                             sleep, DEAD ZONES, calibration flags). See
                             build_config_read_frames / set_deadzone.
  0x12 GET_KEY               CONFIRMED-BY-CAPTURE — 512-byte (128×4) key
                             table read as 9×0x38 + 0x08 @0x1F8. Record
                             semantics are now CONFIRMED-BY-CAPTURE from the
                             2026-07-21 macro capture (see the "Key table"
                             section below) and the 0x12/0x22 read-modify-
                             write path is HARDWARE-VERIFIED (2026-07-20:
                             512-byte read, 11 records zeroed, written back,
                             read-back byte-identical for the other 117).
  0x13 GET_LED_EFFECT        CONFIRMED-BY-CAPTURE — single 16-byte read of
                             the 0x23 lighting block.
  0x14 GET_CUSTOM_LED_DATA   CONFIRMED-BY-CAPTURE — paged read of the
                             504-byte per-key RGB table (the light page
                             reads it on mount; the captured table was all
                             zero). See build_custom_led_read_frames.
  0x15 GET_MACRO             CONFIRMED-BY-CAPTURE (webhid-capture-macros
                             .json) — paged read of the 400-byte macro
                             offset header, then per-macro two-step body
                             reads (4-byte count, then count*2 bytes).
  0x17 GET_MAGNETIC_AXIS_RT  CONFIRMED-BY-CAPTURE — paged read of the
                             1008-byte actuation table; same record layout
                             as 0x27. The official driver reads the whole
                             table back before every 0x27 write pass.
  0x21 SET_GAME_MODE         CONFIRMED-BY-CAPTURE — write-back of the 0x11
                             table (read-modify-write is MANDATORY: a
                             partial write zeroes every other setting).
  0x22 SET_KEY               CONFIRMED-BY-CAPTURE (webhid-capture-macros
                             .json) — whole-table write of the key table.
                             NOTE: the vendor driver writes only the first
                             504 bytes (records 0..125) in 9×0x38 chunks —
                             the 8-byte tail readable via 0x12 is NEVER
                             written. See build_key_table_write_frames.
  0x23 SET_LED_EFFECT        CONFIRMED-BY-CAPTURE — see build_light().
  0x24 SET_CUSTOM_LED_DATA   HARDWARE-VERIFIED (write + 0x14 read-back
                             round-tripped byte-for-byte across all 126
                             keys on the physical board, 2026-07-20); no
                             captured frames. See
                             build_custom_led_write_frames().
  0x25 SET_MACRO             CONFIRMED-BY-CAPTURE (webhid-capture-macros
                             .json) — 400-byte header sweep + one final-
                             flagged chunk per macro body. See
                             build_macro_write_frames().
  0x27 SET_MAGNETIC_AXIS_RT  CONFIRMED-BY-CAPTURE — see
                             build_actuation_frame().

=========================== DO NOT SEND — EVER ===========================
The SDK defines the following commands. Aether must NEVER emit them; this
module deliberately provides NO builders for them, and none may be added.
All three are SOURCE-ONLY (never observed on the wire) — which makes them
MORE dangerous, not less: their exact behavior is unproven.

  0x4F SET_FLASH_DOWNLOAD   Firmware-flash entry point. Never called even
                            by the vendor driver build. A malformed send
                            could BRICK the board.
  0x0F SET_FACTORY_RESET    Wipes settings. The parameter rides in byte 2
                            (the length slot!): 0xFF = full factory reset,
                            0x05 = wipe stored calibration data. Fire-and-
                            forget — the SDK does not even await a reply.
  0x64 SET_CALIBRATION_ON   Starts calibration mode. The vendor UI clears
                            the stored calibration FIRST, i.e. once this
                            fires the board's calibration is gone until a
                            full calibration procedure completes.
                            (0x65 SET_CALIBRATION_OFF ends the mode but
                            does not restore anything.)

If a frame with byte[1] in {0x4F, 0x0F, 0x64} is ever about to leave this
codebase, that is a bug in the caller. See HFD_SDK_DECODE.md §12.
==========================================================================

Actuation table (commands 0x17/0x27): 0x3F0 = 1008 bytes = 126 records of
8 bytes, paged in 18 chunks of 0x38 bytes at offsets 0x0000..0x03B8.
Records pack into the frame from byte 8; each chunk holds EXACTLY 7 whole
records (8 + 7*8 = 64 — nothing is truncated).

Per-key 8-byte record (offsets within the record), per the SDK write fn:
    [0]    axisType — switch (axis) model id. CONFIRMED-BY-CAPTURE only as
           always 0x00 (the capture board used axis id 0, "Smoke Cloud");
           nonzero ids (1..5, 7 — HFD_SDK_DECODE.md §6.2) are SOURCE-ONLY.
    [1]    flags — bit0 = rapid-trigger enable ("whole-stroke fast");
           CONFIRMED-BY-CAPTURE (flipped 0->1 exactly when RT was engaged).
           bit1 = "rampage mode", SOURCE-ONLY, never set by the vendor UI.
    [2..3] trip / actuation travel, LE16, 0.01 mm units
           (0.31 mm -> 1F 00; 3.00 mm -> 2C 01)   CONFIRMED-BY-CAPTURE
    [4..5] rapid-trigger press sensitivity, LE16, 0.01 mm
           (1.25 mm -> 7D 00)                     CONFIRMED-BY-CAPTURE
    [6..7] rapid-trigger release sensitivity, LE16, 0.01 mm
           (0.75 mm -> 4B 00)                     CONFIRMED-BY-CAPTURE

LAYOUT CORRECTION (2026-07-20): an earlier capture-only decode packed the
record from frame byte 9 as [rtEnable][trip][press][release][reserved].
That layout produces byte-identical frames whenever axisType == 0 — true
for every frame in the capture, which is why it golden-tested clean — but
it silently ZEROES the key's switch type the moment axisType is nonzero.
The SDK source (authority) packs from byte 8 with axisType first; this
module now follows the SDK. The golden tests still reproduce every captured
0x27 frame byte-for-byte, and additionally pin the byte-8 origin against
literal captured bytes.

Not every record slot is populated even with all keys selected — the zero
slots are unused matrix positions. Dead zones are NOT in this record: they
are GLOBAL, in the 0x11/0x21 game-mode table (see set_deadzone).

Per-key RGB table (commands 0x14/0x24): 0x1F8 = 504 bytes = 126 records of
4 bytes: [ledId, red, green, blue] at byte ledId*4, where ledId == the
firmware key index (same index space as every other per-key table).
HARDWARE-VERIFIED: effect mode 20 (custom) + a full 504-byte 0x24 write,
read back via 0x14, round-tripped byte-for-byte across all 126 keys.
The colors only display while the 0x23 effect mode is LIGHT_MODE_CUSTOM
(20); the vendor flow is SET 0x23 mode=20, then SET 0x24 with the table.
504-vs-512 DISCREPANCY RESOLVED (2026-07-21): FULL_APP_CAPTURE_NOTES.md
claims this table is "512 bytes = 128 records", but the captured frames in
webhid-capture-macros.json refute that reading: every 0x24 write and 0x14
read pages exactly 9×0x38 = 504 bytes (offsets 0x0000..0x01C0, final flag
on the 0x01C0 chunk), and the last chunk's explicit LED ids run 0x70..0x7D
= 112..125 — the table ends at record 125. 504 stands; the notes' "runs
0x00..0x7F" is an off-by-two in prose, not on the wire (pinned by
test_custom_led_504_not_512_evidence).

Key table (0x12 GET_KEY / 0x22 SET_KEY) — CONFIRMED-BY-CAPTURE
(webhid-capture-macros.json) + HARDWARE-VERIFIED read-modify-write
(2026-07-20). 512 bytes = 128 records × 4 bytes, indexed by MATRIX
position (TKL-shaped, 16-column stride; this 60% board populates a sparse
subset and slots 126..127 are never written by the vendor driver — reads
are 512 bytes, writes are 504). Record layout:

    [0] pageType   [1] sub-parameter   [2] value   [3] value2

  pageType 0  unassigned            00 00 00 00
  pageType 2  keyboard remap        02 <modifier bitmask> <HID usage> 00
  pageType 6  macro bind            06 <macroIdx> <playMode> <loopCount>
              playMode: 0 = play once, 1 = fixed repeat count,
              2 = press-again-to-end (NOT CAPTURED — modes 0/1 observed:
              real records 06 00 01 07 and 06 01 00 01, different in every
              field, disambiguate all four bytes)
  pageType 1/3/8/9/10/11/12/13 (mouse/consumer/DKS/MT/TGL/SOCD/RS/system)
              exist in the same table — documented in
              FULL_APP_CAPTURE_NOTES.md §1, not implemented here.

A separate Fn-layer table with the same record format lives on 0x16/0x26
(CONFIRMED-BY-CAPTURE; no builders here — out of scope for macros).

Macro table (0x15 GET_MACRO / 0x25 SET_MACRO) — CONFIRMED-BY-CAPTURE
(webhid-capture-macros.json, two macros of different lengths):

    bytes 0..399   header: 100 × u32 LE body start offset, one per macro
                   slot; 0 = empty slot. The first stored macro's entry is
                   literally 90 01 00 00 = 400 = the first body byte.
    bytes 400..    bodies, packed back to back.

  Body:  u16 LE count of event data in 16-bit WORDS (= eventCount * 2 —
         observed 8 for a 4-event macro and 0x10 for an 8-event macro),
         u16 padding = 0, then N × 4-byte events.
  Event: [u16 LE delay ms][HID usage][0xB0 = key down | 0x30 = key up].
         Modifiers are ordinary HID usages here, NOT a bitmask (LeftShift
         captured as 0xE1). Delay is 16-bit LE (proven with 300 = 2C 01
         and 770 = 02 03).

  Write flow (vendor, reproduced byte-for-byte): page the 400-byte header
  (7×0x38 + 0x08 @0x0188 with the final flag), then ONE final-flagged
  chunk per macro body at its header offset. Read flow: header sweep, then
  per macro a 4-byte count read at the body offset followed by a
  count*2-byte read at offset+4.

The build_* functions return the raw vendor frame (exactly what appears on
the wire — 64 bytes by default, `frame_len` bytes when overridden) so they
can be asserted byte-for-byte against the captures. The board acknowledges
every OUT frame by echoing it back with 0x55 in byte [0].
"""

MAGIC = 0xAA
REPLY_MAGIC = 0x55
FRAME_LEN = 64                   # wired USB-C (0C45:80A2) — the default everywhere
FRAME_LEN_WIRELESS = 32          # 2.4GHz dongle (0C45:FEFE) — CONFIRMED-BY-CAPTURE
                                 # (webhid-capture-dongle-2026-07-20.json: every
                                 # frame len=32; chunk 0x18 = 32 - 8)
PAYLOAD_START = 8                # payload origin within the frame (SDK fn L)
PAGE = FRAME_LEN - PAYLOAD_START # wired paging stride 0x38 — DERIVED, the rule
                                 # is chunk = frameLen - 8 (wireless: 0x18)
TRIGGER_UNIT_MM = 0.01


def page_size(frame_len=FRAME_LEN):
    """Payload chunk size for a frame length: frameLen - 8 (wired 64 ->
    0x38 = 56, wireless 32 -> 0x18 = 24). CONFIRMED-BY-CAPTURE on both
    transports — this is THE rule that fell out of the dongle capture
    (WIRELESS_DONGLE_FINDINGS.md)."""
    fl = int(frame_len)
    if fl <= PAYLOAD_START:
        raise ValueError(f"frame length {frame_len} leaves no payload space")
    return fl - PAYLOAD_START

CMD_DEVICE_INFO = 0x10           # GET_DEVICE_INFO
CMD_CONFIG_READ = 0x11           # GET_GAME_MODE (global settings; dead zones live here)
CMD_KEY_TABLE_READ = 0x12        # GET_KEY (126x4 remap table; semantics SOURCE-ONLY)
CMD_TABLE12_READ = CMD_KEY_TABLE_READ   # legacy alias (pre-SDK-decode name)
CMD_LIGHT_READ = 0x13            # GET_LED_EFFECT
CMD_GET_CUSTOM_LED = 0x14        # GET_CUSTOM_LED_DATA (per-key RGB table)
CMD_TABLE14_READ = CMD_GET_CUSTOM_LED   # legacy alias (pre-SDK-decode name)
CMD_MACRO_READ = 0x15            # GET_MACRO (header + two-step body reads)
CMD_ACTUATION_READ = 0x17        # GET_MAGNETIC_AXIS_RT
CMD_CONFIG_WRITE = 0x21          # SET_GAME_MODE
CMD_KEY_TABLE_WRITE = 0x22       # SET_KEY (writes records 0..125 only)
CMD_LIGHTING = 0x23              # SET_LED_EFFECT
CMD_SET_CUSTOM_LED = 0x24        # SET_CUSTOM_LED_DATA (per-key RGB write)
CMD_MACRO_WRITE = 0x25           # SET_MACRO (header sweep + per-body chunks)
CMD_ACTUATION = 0x27             # SET_MAGNETIC_AXIS_RT

# NEVER-SEND commands, listed for recognition only (see module docstring).
# No builder exists for these and none may be added.
DANGEROUS_CMDS = frozenset({0x4F, 0x0F, 0x64})   # flash / factory reset / calibration-on

# table geometry (sizes cross-checked SDK source <-> captured paging sequences)
CONFIG_TABLE_SIZE = 0x40         # 0x11 / 0x21
KEY_TABLE_SIZE = 0x200           # 0x12 read: 512 bytes = 128 records x 4
TABLE12_SIZE = KEY_TABLE_SIZE    # legacy alias

# key table (0x12 read / 0x22 write) — CONFIRMED-BY-CAPTURE geometry:
# reads cover all 512 bytes; the vendor driver's writes cover only the
# first 126 records (504 bytes, 9 pages of 0x38) — bytes 504..511 are
# readable but never written on the wire.
KEY_RECORD_SIZE = 4
KEY_RECORD_COUNT = 128                                   # read space
KEY_WRITABLE_RECORDS = 126                               # write space
KEY_TABLE_WRITE_SIZE = KEY_WRITABLE_RECORDS * KEY_RECORD_SIZE   # 504 = 0x1F8

# key-record pageTypes (byte 0). Only UNASSIGNED / KEYBOARD / MACRO have
# builders here; the rest are listed for parser recognition only
# (CONFIRMED-BY-CAPTURE values, FULL_APP_CAPTURE_NOTES.md §1).
KEY_PAGE_UNASSIGNED = 0
KEY_PAGE_MOUSE = 1
KEY_PAGE_KEYBOARD = 2
KEY_PAGE_CONSUMER = 3
KEY_PAGE_MACRO = 6
KEY_PAGE_DKS = 8
KEY_PAGE_MOD_TAP = 9
KEY_PAGE_TOGGLE = 10
KEY_PAGE_SOCD = 11
KEY_PAGE_RS = 12
KEY_PAGE_SYSTEM = 13

# macro table (0x15 / 0x25) — CONFIRMED-BY-CAPTURE geometry
MACRO_SLOTS = 100                # 400-byte header = 100 u32 LE offsets
MACRO_HEADER_SIZE = MACRO_SLOTS * 4      # 0x190; first body starts here
MACRO_EVENT_SIZE = 4
MACRO_EVENT_DOWN = 0xB0          # event byte 3: key down
MACRO_EVENT_UP = 0x30            # event byte 3: key up
MACRO_PLAY_ONCE = 0              # bind playMode 0 (CONFIRMED-BY-CAPTURE)
MACRO_PLAY_REPEAT = 1            # bind playMode 1, fixed count (CONFIRMED)
MACRO_PLAY_UNTIL_PRESSED = 2     # "press again to end" — NOT CAPTURED
ACT_TABLE_SIZE = 0x3F0           # 0x17 / 0x27: 126 records * 8 bytes — IDENTICAL on
                                 # the dongle (captured write ends 0x3D8 + 24 = 0x3F0)
ACT_RECORD_SIZE = 8


def act_records_per_frame(frame_len=FRAME_LEN):
    """Whole 8-byte records per frame: (frameLen - 8) // 8 — wired 7
    (8 + 7*8 == 64), wireless 3 (8 + 3*8 == 32). Nothing is ever truncated
    at the frame edge on either transport (CONFIRMED-BY-CAPTURE)."""
    return page_size(frame_len) // ACT_RECORD_SIZE


def act_page_offsets(frame_len=FRAME_LEN):
    """Actuation-table page offsets for a frame length: wired 18 pages of
    0x38 (0x0000..0x03B8), wireless 42 pages of 0x18 (0x0000..0x03D8) —
    the wireless sweep is CONFIRMED-BY-CAPTURE (both the 0x17 reads and the
    0x27 write pass in webhid-capture-dongle-2026-07-20.json)."""
    return tuple(range(0, ACT_TABLE_SIZE, page_size(frame_len)))


ACT_RECORDS_PER_FRAME = act_records_per_frame()  # wired 7 (legacy constant)
ACT_PAGE_OFFSETS = act_page_offsets()            # wired 18 pages, 0x0000..0x03B8

# per-key RGB (custom LED) table geometry — HARDWARE-VERIFIED (see docstring)
CUSTOM_LED_COUNT = 126
CUSTOM_LED_RECORD_SIZE = 4       # [ledId, r, g, b] at byte ledId*4
CUSTOM_LED_TABLE_SIZE = CUSTOM_LED_COUNT * CUSTOM_LED_RECORD_SIZE   # 504 = 0x1F8
TABLE14_SIZE = CUSTOM_LED_TABLE_SIZE    # legacy alias


def custom_led_page_offsets(frame_len=FRAME_LEN):
    """Per-key RGB table page offsets: wired 9 pages of 0x38
    (0x0000..0x01C0), wireless 21 pages of 0x18 (0x0000..0x01E0 — the
    final page is a full 24 bytes since 504 = 21 * 24). Wireless paging is
    a frameLen-8 shape inference; 0x14/0x24 were never captured on the
    dongle, but the 0x32 stream using this exact paging is
    HARDWARE-VERIFIED over the dongle (2026-07-20 benchmark)."""
    return tuple(range(0, CUSTOM_LED_TABLE_SIZE, page_size(frame_len)))


CUSTOM_LED_PAGE_OFFSETS = custom_led_page_offsets()   # wired 9 pages, 0x0000..0x01C0

# dead-zone position: SDK game-mode table payload offset 8 = topDeadZone*100
# (0.01 mm units); payload offset 9 = bottomDeadZone (SOURCE-ONLY, 0 in capture).
CONFIG_DEADZONE_OFFSET = 8       # offset within the FULL 56-byte page payload
                                 # (frame byte 16 of the offset-0 page;
                                 #  legacy 55-byte reply[9:] slices use 7 — see set_deadzone)

# lighting effect mode bytes (frame byte [8]), in the driver's menu order —
# modes 0x01..0x13 were each captured with their menu label (CONFIRMED-BY-CAPTURE).
LIGHT_MODE_STATIC = 0x01             # Static constant brightness
LIGHT_MODE_SINGLE_POINT = 0x02       # Single-point lighting
LIGHT_MODE_SINGLE_EXTINGUISH = 0x03  # Single extinguish
LIGHT_MODE_TWINKLING_STARS = 0x04    # twinkling stars
LIGHT_MODE_SNOWFLAKES = 0x05         # Snowflakes flying everywhere
LIGHT_MODE_RIOT_OF_FLOWERS = 0x06    # A riot of flowers
LIGHT_MODE_DYNAMIC_BREATHING = 0x07  # Dynamic breathing
LIGHT_MODE_SPECTRAL_CYCLING = 0x08   # Spectral Cycling
LIGHT_MODE_COLORFUL_SPRINGS = 0x09   # Colorful springs gushing forth
LIGHT_MODE_COLORFUL_DIVERSE = 0x0A   # Colorful and diverse
LIGHT_MODE_GO_WITH_THE_FLOW = 0x0B   # Go with the flow
LIGHT_MODE_TWIST_OF_FATE = 0x0C      # A Twist of Fate
LIGHT_MODE_VERGE_OF_EXPLODING = 0x0D # On the verge of exploding
LIGHT_MODE_KILL_TWO_BIRDS = 0x0E     # Kill two birds with one stone
LIGHT_MODE_RIPPLE_SPREAD = 0x0F      # Ripple spread
LIGHT_MODE_FLOWING = 0x10            # Flowing continuously
LIGHT_MODE_MOUNTAINS = 0x11          # Layer upon layer of mountains
LIGHT_MODE_SLANTING_WIND = 0x12      # Slanting wind and drizzle
LIGHT_MODE_SHUTTLING = 0x13          # shuttling back and forth
LIGHT_MODE_CUSTOM = 0x14             # 20 — per-key RGB from the 0x24 table.
                                     # HARDWARE-VERIFIED (no captured menu frame;
                                     # confirmed on the board 2026-07-20).

LIGHT_MODE_NAMES = {
    LIGHT_MODE_STATIC: "Static constant brightness",
    LIGHT_MODE_SINGLE_POINT: "Single-point lighting",
    LIGHT_MODE_SINGLE_EXTINGUISH: "Single extinguish",
    LIGHT_MODE_TWINKLING_STARS: "twinkling stars",
    LIGHT_MODE_SNOWFLAKES: "Snowflakes flying everywhere",
    LIGHT_MODE_RIOT_OF_FLOWERS: "A riot of flowers",
    LIGHT_MODE_DYNAMIC_BREATHING: "Dynamic breathing",
    LIGHT_MODE_SPECTRAL_CYCLING: "Spectral Cycling",
    LIGHT_MODE_COLORFUL_SPRINGS: "Colorful springs gushing forth",
    LIGHT_MODE_COLORFUL_DIVERSE: "Colorful and diverse",
    LIGHT_MODE_GO_WITH_THE_FLOW: "Go with the flow",
    LIGHT_MODE_TWIST_OF_FATE: "A Twist of Fate",
    LIGHT_MODE_VERGE_OF_EXPLODING: "On the verge of exploding",
    LIGHT_MODE_KILL_TWO_BIRDS: "Kill two birds with one stone",
    LIGHT_MODE_RIPPLE_SPREAD: "Ripple spread",
    LIGHT_MODE_FLOWING: "Flowing continuously",
    LIGHT_MODE_MOUNTAINS: "Layer upon layer of mountains",
    LIGHT_MODE_SLANTING_WIND: "Slanting wind and drizzle",
    LIGHT_MODE_SHUTTLING: "shuttling back and forth",
    LIGHT_MODE_CUSTOM: "Custom (per-key RGB)",
}


def mm_to_raw(mm):
    """Travel in mm -> firmware units (0.01 mm), clamped non-negative."""
    return max(0, round(mm / TRIGGER_UNIT_MM))


def raw_to_mm(raw):
    """Firmware units (0.01 mm) -> travel in mm."""
    return round(raw * TRIGGER_UNIT_MM, 2)


def to_report(frame, report_id=0x00):
    """Prepend the Report ID byte hidapi.write() expects (these frames have none)."""
    return [report_id & 0xFF] + list(frame)


def _frame(cmd, length, offset=0, final=False, frame_len=FRAME_LEN):
    """One empty `frame_len`-byte vendor frame. Refuses a content length
    that cannot fit the frame's payload space — sending an over-length
    frame is exactly the mistake that made an earlier probe conclude the
    dongle spoke a different protocol (64-byte frame, 32-byte report,
    hidapi truncation, no reply)."""
    if length > page_size(frame_len):
        raise ValueError(
            f"chunk length {length:#04x} exceeds the {frame_len}-byte "
            f"frame's payload space ({page_size(frame_len):#04x}) — size "
            f"frames from the board profile")
    f = [0] * frame_len
    f[0] = MAGIC
    f[1] = cmd & 0xFF
    f[2] = length & 0xFF
    f[3] = offset & 0xFF             # LITTLE-endian table offset
    f[4] = (offset >> 8) & 0xFF
    f[6] = 0x01 if final else 0x00   # last-chunk flag
    return f


# ---------------- device info (cmd 0x10) ----------------
DEVICE_INFO_SIZE = 0x38   # the info blob is 56 bytes: wired reads it as ONE
                          # 0x38 chunk; the dongle pages it 0x18+0x18+0x08
                          # (CONFIRMED-BY-CAPTURE on both transports)


def build_device_info_frames(frame_len=FRAME_LEN):
    """The cmd-0x10 device-info read (first transaction of the driver's
    init sequence) as a PAGED read of the 56-byte info blob — the shape
    that explains both captures with one rule (chunk = frameLen - 8):
      wired    -> [AA 10 38 00 00 00 01]                    (single, final)
      wireless -> [AA 10 18 @0, AA 10 18 @0x18, AA 10 08 @0x30 final]
    CONFIRMED-BY-CAPTURE on both transports
    (webhid-capture-dongle-handshake.json holds the wireless sweep and its
    0x55 replies). The firmware answers each chunk; VID/PID ride in the
    offset-0 reply (parse_device_info)."""
    return list(_iter_paged_read_frames(CMD_DEVICE_INFO, DEVICE_INFO_SIZE,
                                        frame_len=frame_len))


def build_device_info(frame_len=FRAME_LEN):
    """The FIRST frame of the 0x10 device-info read — the whole read on the
    wired board (AA 10 38 00 00 00 01, rest zero — CONFIRMED-BY-CAPTURE)
    and the VID/PID-bearing chunk of the wireless sweep (the firmware
    replies per chunk — CONFIRMED-BY-CAPTURE). Use
    build_device_info_frames() for the full vendor-faithful sweep."""
    return build_device_info_frames(frame_len)[0]


def parse_device_info(reply):
    """Extract (vid, pid) from the OFFSET-0 0x10 reply — both 16-bit
    LITTLE-endian at reply[12..13] / reply[14..15] (wired capture:
    45 0C A2 80 = 0x0C45, 0x80A2). CONFIRMED-BY-CAPTURE on both transports
    — the dongle's offset-0 reply carries the SAME bytes at the SAME
    offsets, and notably reports the WIRED keyboard identity 0x80A2 even
    over the 0xFEFE receiver (the RF bridge is transparent; the firmware
    answers). Further reply fields (fw version at [16..17] — 53 01 = V1.53
    on both transports — work mode, …) are decoded in HFD_SDK_DECODE.md §3
    but not parsed here."""
    vid = reply[12] | (reply[13] << 8)
    pid = reply[14] | (reply[15] << 8)
    return vid, pid


# ---------------- generic paged table reads (0x11 / 0x12 / 0x14 / 0x17) ----------------
def build_table_read(cmd, offset, length=None, final=False, frame_len=FRAME_LEN):
    """Build one empty paged-read request frame. Every captured read request
    (0x11, 0x12, 0x14, 0x17 and the 0x13 single) is header-only: magic, cmd,
    length, LE offset, and the last-chunk flag on the last page.
    CONFIRMED-BY-CAPTURE on both transports. `length` defaults to the
    frame's full payload chunk (frameLen - 8)."""
    if length is None:
        length = page_size(frame_len)
    return _frame(cmd, length, offset, final, frame_len=frame_len)


def build_light_read(frame_len=FRAME_LEN):
    """Build the single 0x13 lighting-config read (length 0x10, final).
    CONFIRMED-BY-CAPTURE wired; the dongle sends the IDENTICAL header at
    32 bytes (AA 13 10 00 00 00 01 00 — CONFIRMED-BY-CAPTURE (transcribed),
    WIRELESS_DONGLE_FINDINGS.md)."""
    return _frame(CMD_LIGHT_READ, 0x10, final=True, frame_len=frame_len)


def iter_actuation_reads(frame_len=FRAME_LEN):
    """Yield the cmd-0x17 read frames covering the whole 0x3F0-byte
    actuation table (wired: 18 x 0x38; wireless: 42 x 0x18), last-chunk
    flag on the last page — exactly the sequence the official driver sends
    before every actuation write pass. CONFIRMED-BY-CAPTURE on BOTH
    transports (the wireless sweep is golden-tested against
    webhid-capture-dongle-2026-07-20.json)."""
    offsets = act_page_offsets(frame_len)
    last = offsets[-1]
    for off in offsets:
        yield build_table_read(CMD_ACTUATION_READ, off, page_size(frame_len),
                               final=(off == last), frame_len=frame_len)


def build_config_read_frames(frame_len=FRAME_LEN):
    """The cmd-0x11 frames reading the 0x40-byte game-mode table. Wired:
    0x38 @ 0x0000 then 0x08 @ 0x0038 final (CONFIRMED-BY-CAPTURE). Wireless:
    0x18 @ 0x0000, 0x18 @ 0x0018, 0x10 @ 0x0030 final — CONFIRMED-BY-CAPTURE
    (webhid-capture-dongle-2026-07-20.json frames 44-46). Both are the same
    generic paging with chunk = frameLen - 8."""
    return list(_iter_paged_read_frames(CMD_CONFIG_READ, CONFIG_TABLE_SIZE,
                                        frame_len=frame_len))


# ---------------- global config write / dead zone (cmd 0x21) ----------------
def set_deadzone(config_payload, mm):
    """Return a copy of the game-mode page-0 payload with the TOP dead zone
    patched in (SDK: payload offset 8 = topDeadZone*100; offset 9 is
    bottomDeadZone, untouched here). Units 0.01 mm; capture: 0.42 mm -> 0x2A
    at frame byte 16 of the offset-0 page. CONFIRMED-BY-CAPTURE.

    Accepts either payload convention (see build_config_write_frames):
      * 56 bytes — the full page, reply[8:64]: patches offset 8;
      * 55 bytes — legacy slice, reply[9:64]:  patches offset 7
        (same wire byte; the slice starts one byte into the table).

    The field is a single byte per the SDK source (SOURCE-ONLY for values
    above the captured 0x2A); the UI range is 0-0.5 mm, and values above
    2.55 mm are rejected rather than guessed at."""
    raw = mm_to_raw(mm)
    if raw > 0xFF:
        raise ValueError("dead zone > 2.55 mm: field is a single byte")
    payload = list(config_payload)
    if len(payload) == PAGE:
        payload[CONFIG_DEADZONE_OFFSET] = raw
    elif len(payload) == PAGE - 1:
        payload[CONFIG_DEADZONE_OFFSET - 1] = raw   # legacy reply[9:] slice
    else:
        raise ValueError(f"config payload must be {PAGE - 1} or {PAGE} bytes")
    return payload


def build_config_write_frames(config_payload, frame_len=FRAME_LEN):
    """Build the cmd-0x21 frames writing the game-mode table back. Wired:
    the 0x38-byte payload @ 0x0000, then the empty 0x08 @ 0x0038 final frame
    (matches the captured DEADZONE_TOP_0.42mm sequence byte-for-byte).
    CONFIRMED-BY-CAPTURE. Wireless: the same table paged as 0x18 @ 0x0000,
    0x18 @ 0x0018, 0x10 @ 0x0030 final — structural (no 0x21 was captured on
    the dongle) but mirroring its CONFIRMED-BY-CAPTURE 0x11 read paging
    exactly. Both shapes are one rule: page the full 0x40-byte table with
    chunk = frameLen - 8, final flag on the last chunk.

    `config_payload` must be the page read back via 0x11 (most fields in
    this table are undecoded and must be replayed verbatim — a partial
    write zeroes them), optionally patched with set_deadzone(). Two input
    conventions are accepted:
      * 56 bytes — the full page payload, reply[8:64] (preferred; packs
        from frame byte 8 exactly as the SDK does);
      * 55 bytes — the legacy reply[9:64] slice (pre-SDK-decode convention;
        table byte 0 is then written as 0, which matched the capture —
        the SDK does not parse that byte and it read back 0).

    KNOWN LIMIT (SOURCE-ONLY risk): table bytes 56..63 are written as zero
    (the wired capture's second chunk is empty). They were zero in every
    captured read and the SDK parses no field there, matching the captured
    write."""
    payload = list(config_payload)
    if len(payload) == PAGE - 1:
        payload = [0] + payload      # legacy slice starts at table byte 1
    elif len(payload) != PAGE:
        raise ValueError(f"config payload must be {PAGE - 1} or {PAGE} bytes")
    payload += [0] * (CONFIG_TABLE_SIZE - len(payload))   # zero tail 56..63
    return list(_iter_paged_write_frames(CMD_CONFIG_WRITE, payload,
                                         frame_len=frame_len))


# ---------------- lighting (cmd 0x23) ----------------
def build_light(mode, r=0x90, g=0xEE, b=0x90, brightness=0x05, speed=0x04,
                alpha=0xFF, color_mode=1, frame_len=FRAME_LEN):
    """Build a 0x23 lighting frame. CONFIRMED-BY-CAPTURE (21 wired frames +
    9 wireless frames, the latter transcribed — WIRELESS_DONGLE_FINDINGS.md).

    Layout (absolute byte indices, identical at both frame sizes):
      [6]=0x01 (last-chunk flag)  [8]=mode  [9..12]=R,G,B,alpha
      [16]=colorMode  [17]=brightness  [18]=speed  [22..23]=0xAA,0x55 marker

    [16] colorMode — the SDK's `randomColor ? 1 : 0`. CORRECTION 2026-07-20:
    this byte was previously HARDCODED to 1 ("must be 1") because every
    wired-capture frame carried 1 — a single-valued sample mistaken for a
    constant. The wireless capture shows BOTH values, correlated exactly
    with the mode: fixed-colour modes (0x01/0x02/0x04/0x07) send 0,
    multicolour modes (0x08/0x0F/0x11/0x12/0x13) send 1. With the byte
    pinned to 1, user-chosen colours are likely IGNORED in fixed-colour
    modes. The default stays 1 so legacy callers reproduce the wired
    capture byte-for-byte; drivers should pass the mode-derived value
    (registry lighting.modes[].color === false => forced-random => 1,
    otherwise 0).

    For per-key RGB pass mode=LIGHT_MODE_CUSTOM (20), then write the color
    table with build_custom_led_write_frames().

    Defaults reproduce the captured color/brightness/speed so a bare
    build_light(mode) matches the captured wired mode-change frames
    byte-for-byte (brightness 0x05 -> 0x04 on the captured BRIGHTNESS_DEC,
    speed 0x04 -> 0x03 on SPEED_DEC)."""
    f = _frame(CMD_LIGHTING, 0x10, final=True, frame_len=frame_len)
    f[8] = mode & 0xFF
    f[9], f[10], f[11], f[12] = r & 0xFF, g & 0xFF, b & 0xFF, alpha & 0xFF
    f[16] = color_mode & 0xFF
    f[17] = brightness & 0xFF
    f[18] = speed & 0xFF
    f[22] = 0xAA
    f[23] = 0x55
    return f


# ---------------- per-key RGB / custom LED table (0x14 read, 0x24 write) ----------------
def build_custom_led_table(colors):
    """Build the 504-byte custom-LED table from 126 (r, g, b) triples,
    indexed by firmware key index: record i is [i, r, g, b] at byte i*4
    (ledId == key index — HARDWARE-VERIFIED by write/read-back round trip)."""
    colors = list(colors)
    if len(colors) != CUSTOM_LED_COUNT:
        raise ValueError(f"need exactly {CUSTOM_LED_COUNT} (r, g, b) triples")
    table = [0] * CUSTOM_LED_TABLE_SIZE
    for i, (r, g, b) in enumerate(colors):
        base = i * CUSTOM_LED_RECORD_SIZE
        table[base] = i
        table[base + 1] = r & 0xFF
        table[base + 2] = g & 0xFF
        table[base + 3] = b & 0xFF
    return table


def build_custom_led_read_frames(frame_len=FRAME_LEN):
    """Yield the cmd-0x14 read frames covering the whole 504-byte per-key
    RGB table (wired: 9 pages of 0x38, offsets 0x0000..0x01C0; wireless:
    21 pages of 0x18), last-chunk flag on the final page — exactly the
    sequence the official driver's light page sends on mount.
    CONFIRMED-BY-CAPTURE wired; the wireless paging is the frameLen-8 shape
    (0x14 not captured on the dongle)."""
    return _iter_paged_read_frames(CMD_GET_CUSTOM_LED, CUSTOM_LED_TABLE_SIZE,
                                   frame_len=frame_len)


def build_custom_led_write_frames(table, frame_len=FRAME_LEN):
    """Yield the cmd-0x24 frames writing a full 504-byte per-key RGB
    table: payload packs from frame byte 8, frameLen-8 bytes per chunk,
    LE16 byte offset at [3..4], last-chunk flag on the final page (wired:
    9 x 0x38; wireless: 21 x 0x18).

    HARDWARE-VERIFIED wired, NOT capture-golden: no 0x24 frames exist in
    the capture. Framing and payload placement were verified on the
    physical board (2026-07-20) by sending this exact sequence with effect
    mode 20 and reading the table back via 0x14 — it round-tripped
    byte-for-byte across all 126 keys. The chunking mirrors the
    CONFIRMED-BY-CAPTURE 0x14 read paging and the SDK's transaction engine
    (HFD_SDK_DECODE.md §1, §9). The wireless shape is UNVERIFIED for 0x24
    itself (the capability stays 'wip' on the dongle), but the 0x32 stream
    sharing this exact paging is HARDWARE-VERIFIED over the dongle.

    `table` is the raw 504-byte table ([ledId, r, g, b] per record — use
    build_custom_led_table()). The colors display only while the 0x23
    effect mode is LIGHT_MODE_CUSTOM (20)."""
    table = list(table)
    if len(table) != CUSTOM_LED_TABLE_SIZE:
        raise ValueError(f"custom LED table must be {CUSTOM_LED_TABLE_SIZE} bytes")
    return _iter_paged_write_frames(CMD_SET_CUSTOM_LED, table,
                                    frame_len=frame_len)


def parse_custom_led_replies(replies):
    """Reassemble 0x14 read replies into the 504-byte table and decode it to
    a list of 126 (ledId, r, g, b) tuples (record i at byte i*4).
    CONFIRMED-BY-CAPTURE for the framing (reply [2]=chunk length,
    [3..4]=LE16 offset, data from byte 8); record semantics
    HARDWARE-VERIFIED (the captured table itself was all zero — the board
    had no custom table stored)."""
    table = [0] * CUSTOM_LED_TABLE_SIZE
    for reply in replies:
        if reply[0] != REPLY_MAGIC or reply[1] != CMD_GET_CUSTOM_LED:
            raise ValueError("not a 0x14 custom-LED read reply")
        length = reply[2]
        off = reply[3] | (reply[4] << 8)
        for j in range(length):
            # bound by the reply's own length, not the wired FRAME_LEN —
            # dongle replies are 32-byte frames
            if off + j < CUSTOM_LED_TABLE_SIZE and PAYLOAD_START + j < len(reply):
                table[off + j] = reply[PAYLOAD_START + j]
    return [tuple(table[i * CUSTOM_LED_RECORD_SIZE:
                        (i + 1) * CUSTOM_LED_RECORD_SIZE])
            for i in range(CUSTOM_LED_COUNT)]


# ---------------- actuation / rapid trigger (cmd 0x27) ----------------
def _act_record(rt_flags, trip_mm, rt_press_mm=0.0, rt_release_mm=0.0,
                axis_type=0):
    """8-byte per-key record, SDK layout:
    [axisType][flags][trip LE16][RT press LE16][RT release LE16].
    All travel values 0.01 mm, LITTLE-endian (capture: 0.31 mm -> 1F 00;
    3.00 mm -> 2C 01; 1.25 mm -> 7D 00; 0.75 mm -> 4B 00).

    `rt_flags`: bit0 = rapid-trigger enable (CONFIRMED-BY-CAPTURE); bit1 =
    SDK "rampage mode" (SOURCE-ONLY). Booleans work (True -> 1).
    `axis_type`: switch model id, default 0 (the only value ever captured);
    nonzero ids per HFD_SDK_DECODE.md §6.2 are SOURCE-ONLY."""
    t = mm_to_raw(trip_mm)
    p = mm_to_raw(rt_press_mm)
    rel = mm_to_raw(rt_release_mm)
    return [axis_type & 0xFF,
            int(rt_flags) & 0xFF,
            t & 0xFF, (t >> 8) & 0xFF,
            p & 0xFF, (p >> 8) & 0xFF,
            rel & 0xFF, (rel >> 8) & 0xFF]


def build_actuation_frame(offset, records, final=False, frame_len=FRAME_LEN):
    """Build one 0x27 frame writing `records` at actuation-table byte `offset`.
    CONFIRMED-BY-CAPTURE on BOTH transports (reproduces all 72 captured
    wired 0x27 frames AND the dongle capture's complete 42-frame write pass;
    the byte-8 record origin is additionally pinned against literal captured
    bytes in the tests).

    `records` is a list of up to act_records_per_frame(frame_len) entries
    (wired 7, wireless 3), each either None (leave the 8-byte slot zero —
    unused matrix positions stay zero in the capture) or a
    (rt_flags, trip_mm[, rt_press_mm[, rt_release_mm[, axis_type]]])
    tuple. `axis_type` defaults to 0, which reproduces every captured frame
    (the capture board used switch id 0 throughout); pass a nonzero switch
    id (SOURCE-ONLY, HFD_SDK_DECODE.md §6.2) to change a key's switch model
    WITHOUT zeroing it — the pre-SDK layout of this module would have
    silently written 0 here.

    Records pack from frame byte 8; a page holds exactly whole records on
    both transports (8 + 7*8 = 64 wired, 8 + 3*8 = 32 wireless — nothing is
    truncated at the frame edge).

    `offset` is the LE16 table offset at [3..4]; the driver pages the whole
    0x3F0-byte table at act_page_offsets(frame_len) with `final=True` on
    the last page (0x03B8 wired / 0x03D8 wireless). Set fields you don't
    want active to 0 — the captured fixed-actuation frames carry flags=0
    and zero press/release, and the RT frames leave not-yet-set fields
    at 0."""
    per_frame = act_records_per_frame(frame_len)
    if len(records) > per_frame:
        raise ValueError(f"at most {per_frame} records per {frame_len}-byte frame")
    f = _frame(CMD_ACTUATION, page_size(frame_len), offset, final,
               frame_len=frame_len)
    for slot, rec in enumerate(records):
        if rec is None:
            continue
        base = PAYLOAD_START + slot * ACT_RECORD_SIZE
        f[base:base + ACT_RECORD_SIZE] = _act_record(*rec)
    return f


def parse_actuation_records(frame):
    """Decode the record slots of a 0x27 write or 0x17 read-reply frame
    into (rt_flags, trip_mm, rt_press_mm, rt_release_mm, axis_type) tuples;
    all-zero slots decode to None. Records start at frame byte 8 (SDK
    layout — see module docstring). The slot count comes from the frame's
    own length ((len - 8) // 8: 7 for 64-byte frames, 3 for 32-byte ones),
    so wired callers see the exact pre-parameterisation behaviour. Inverse
    of build_actuation_frame's record packing:
    build_actuation_frame(offset, parse_actuation_records(f)) reproduces f
    for every captured frame on both transports."""
    out = []
    slots = (len(frame) - PAYLOAD_START) // ACT_RECORD_SIZE
    for slot in range(slots):
        base = PAYLOAD_START + slot * ACT_RECORD_SIZE
        raw = frame[base:base + ACT_RECORD_SIZE]
        if not any(raw):
            out.append(None)
            continue
        out.append((raw[1],
                    raw_to_mm(raw[2] | (raw[3] << 8)),
                    raw_to_mm(raw[4] | (raw[5] << 8)),
                    raw_to_mm(raw[6] | (raw[7] << 8)),
                    raw[0]))
    return out


# ---------------- generic paging (shared by key table + macros) ----------------
def _iter_paged_read_frames(cmd, size, frame_len=FRAME_LEN):
    """Header-only read frames covering `size` table bytes in frameLen-8
    chunks (0x38 wired / 0x18 wireless), short tail chunk if size is not a
    multiple, final flag on the last chunk — exactly the vendor driver's
    paging for every table read observed (0x11/0x12/0x14/0x15/0x17).
    CONFIRMED-BY-CAPTURE on both transports (wireless: the 0x11 and 0x17
    sweeps in webhid-capture-dongle-2026-07-20.json)."""
    page = page_size(frame_len)
    off = 0
    while off < size:
        ln = min(page, size - off)
        yield build_table_read(cmd, off, ln, final=(off + ln >= size),
                               frame_len=frame_len)
        off += page


def _iter_paged_write_frames(cmd, data, base=0, frame_len=FRAME_LEN):
    """Write frames carrying `data` in frameLen-8 chunks starting at table
    byte `base`, payload from frame byte 8, final flag on the last chunk —
    the vendor chunking for 0x21/0x22/0x24/0x25 writes.
    CONFIRMED-BY-CAPTURE (wired; the dongle's 0x27 write pass follows the
    same chunk rule at 0x18)."""
    page = page_size(frame_len)
    data = list(data)
    size = len(data)
    off = 0
    while off < size:
        ln = min(page, size - off)
        f = _frame(cmd, ln, base + off, final=(off + ln >= size),
                   frame_len=frame_len)
        for j, v in enumerate(data[off:off + ln]):
            f[PAYLOAD_START + j] = v & 0xFF
        yield f
        off += page


# ---------------- key table (0x12 read / 0x22 write) ----------------
def key_record_remap(hid_usage, modifiers=0):
    """4-byte pageType-2 record: plain keyboard remap.
    [02][modifier bitmask][HID usage][00]. CONFIRMED-BY-CAPTURE
    (e.g. 02 00 48 00 = Pause, 02 00 47 00 = Scroll Lock; the stock Fn
    table carries a modifier-only 02 40 00 00, proving byte 1 is a
    modifier bitmask, not padding)."""
    return [KEY_PAGE_KEYBOARD, int(modifiers) & 0xFF, int(hid_usage) & 0xFF, 0]


def key_record_macro(macro_index, play_mode=MACRO_PLAY_ONCE, loop_count=1):
    """4-byte pageType-6 record binding a macro slot to this key:
    [06][macroIdx][playMode][loopCount]. CONFIRMED-BY-CAPTURE with two
    records differing in every field (06 00 01 07 = macro 0, fixed x7;
    06 01 00 01 = macro 1, play once). playMode 2 ("press again to end")
    is NOT CAPTURED — accepted but unverified."""
    idx = int(macro_index)
    if not 0 <= idx < MACRO_SLOTS:
        raise ValueError(f"macro index must be 0..{MACRO_SLOTS - 1}")
    mode = int(play_mode)
    if mode not in (MACRO_PLAY_ONCE, MACRO_PLAY_REPEAT, MACRO_PLAY_UNTIL_PRESSED):
        raise ValueError("play mode must be 0 (once), 1 (repeat) or 2 (toggle)")
    loops = int(loop_count)
    if not 0 <= loops <= 0xFF:
        raise ValueError("loop count is a single byte (0..255)")
    return [KEY_PAGE_MACRO, idx, mode, loops]


def key_record_unassigned():
    """The 4-byte UNASSIGNED record (00 00 00 00). CONFIRMED-BY-CAPTURE —
    keys the vendor UI shows as unbound read back as all-zero records."""
    return [0, 0, 0, 0]


def parse_key_record(record):
    """Decode one 4-byte key-table record to a dict. Fully decoded for the
    pageTypes this module builds (unassigned / keyboard / macro,
    CONFIRMED-BY-CAPTURE); other pageTypes are recognized but returned
    with their raw bytes only."""
    b0, b1, b2, b3 = (int(x) & 0xFF for x in record[:KEY_RECORD_SIZE])
    if b0 == KEY_PAGE_UNASSIGNED and not (b1 or b2 or b3):
        return {"type": "unassigned"}
    if b0 == KEY_PAGE_KEYBOARD:
        return {"type": "keyboard", "modifiers": b1, "hid_usage": b2}
    if b0 == KEY_PAGE_MACRO:
        return {"type": "macro", "macro_index": b1, "play_mode": b2,
                "loop_count": b3}
    return {"type": "raw", "page_type": b0, "bytes": [b0, b1, b2, b3]}


def parse_key_table(table):
    """Split a 512-byte (or 504-byte) key table into per-record dicts:
    {record index: parse_key_record(...)}."""
    table = list(table)
    if len(table) not in (KEY_TABLE_SIZE, KEY_TABLE_WRITE_SIZE):
        raise ValueError(
            f"key table must be {KEY_TABLE_WRITE_SIZE} or {KEY_TABLE_SIZE} bytes")
    return {i: parse_key_record(table[i * KEY_RECORD_SIZE:
                                      (i + 1) * KEY_RECORD_SIZE])
            for i in range(len(table) // KEY_RECORD_SIZE)}


def build_key_table_read_frames(frame_len=FRAME_LEN):
    """The cmd-0x12 read frames covering the full 512-byte key table.
    Wired: 9 pages of 0x38 at 0x0000..0x01C0 plus the 8-byte tail at 0x01F8
    with the last-chunk flag — the exact sequence the official driver sends
    on every key-remap page mount. CONFIRMED-BY-CAPTURE (49 identical
    sweeps in webhid-capture-macros.json). Wireless: the frameLen-8 shape
    (22 frames), NOT captured — 0x12 was never observed on the dongle."""
    return list(_iter_paged_read_frames(CMD_KEY_TABLE_READ, KEY_TABLE_SIZE,
                                        frame_len=frame_len))


def build_key_table_write_frames(table, frame_len=FRAME_LEN):
    """The cmd-0x22 frames writing the key table back: frameLen-8 chunks
    (wired: 9 x 0x38 at 0x0000..0x01C0), final flag on the last chunk — the
    vendor driver writes only records 0..125 (504 bytes) and NEVER touches
    the 8-byte tail that 0x12 reads. CONFIRMED-BY-CAPTURE (15 write sweeps,
    including both macro binds, reproduced byte-for-byte); the surrounding
    read-modify-write flow is additionally HARDWARE-VERIFIED (2026-07-20).
    Wireless shape (21 x 0x18) is NOT captured — 0x22 was never observed on
    the dongle.

    `table` is the full 512-byte table as read via 0x12 (preferred — the
    read-modify-write contract) or a bare 504-byte write image. Passing a
    512-byte table with nonzero data in bytes 504..511 raises: those bytes
    cannot be written by the captured vendor path and silently dropping
    them would break the read-modify-write guarantee. (They read back zero
    on the real board.)"""
    table = list(table)
    if len(table) == KEY_TABLE_SIZE:
        if any(table[KEY_TABLE_WRITE_SIZE:]):
            raise ValueError(
                "key-table bytes 504..511 are nonzero but the vendor write "
                "path never writes them — refusing to drop data silently")
        table = table[:KEY_TABLE_WRITE_SIZE]
    elif len(table) != KEY_TABLE_WRITE_SIZE:
        raise ValueError(
            f"key table must be {KEY_TABLE_WRITE_SIZE} or {KEY_TABLE_SIZE} bytes")
    return list(_iter_paged_write_frames(CMD_KEY_TABLE_WRITE, table,
                                         frame_len=frame_len))


def parse_key_table_replies(replies):
    """Reassemble 0x12 read replies into the raw 512-byte table.
    CONFIRMED-BY-CAPTURE framing (reply [2] = chunk length, [3..4] = LE16
    offset, data from byte 8)."""
    table = [0] * KEY_TABLE_SIZE
    for reply in replies:
        if reply[0] != REPLY_MAGIC or reply[1] != CMD_KEY_TABLE_READ:
            raise ValueError("not a 0x12 key-table read reply")
        # bound by the reply's own payload space (frame-size agnostic)
        length = min(reply[2], len(reply) - PAYLOAD_START)
        off = reply[3] | (reply[4] << 8)
        for j in range(length):
            if off + j < KEY_TABLE_SIZE:
                table[off + j] = reply[PAYLOAD_START + j]
    return table


# ---------------- macros (0x15 read / 0x25 write) ----------------
def encode_macro_events(events):
    """Encode a macro body from a list of (delay_ms, hid_usage, is_down)
    events: u16 LE count in 16-bit WORDS (= len(events) * 2), u16 padding,
    then 4-byte events [delay LE16][usage][0xB0 down | 0x30 up].
    CONFIRMED-BY-CAPTURE — reproduces both captured bodies byte-for-byte
    (the words-not-events count was pinned by two macros of different
    lengths: 8 for 4 events, 0x10 for 8 events; the 16-bit LE delay by
    300 -> 2C 01 and 770 -> 02 03; LeftShift rode as HID usage 0xE1,
    proving modifiers are NOT a bitmask inside events)."""
    events = list(events)
    if not events:
        raise ValueError("a macro needs at least one event")
    words = len(events) * 2
    if words > 0xFFFF:
        raise ValueError("macro too long: the count field is u16")
    body = [words & 0xFF, (words >> 8) & 0xFF, 0, 0]
    for delay_ms, usage, is_down in events:
        d = int(delay_ms)
        if not 0 <= d <= 0xFFFF:
            raise ValueError("event delay must fit u16 milliseconds")
        u = int(usage)
        if not 0 <= u <= 0xFF:
            raise ValueError("event HID usage is a single byte")
        body += [d & 0xFF, (d >> 8) & 0xFF, u,
                 MACRO_EVENT_DOWN if is_down else MACRO_EVENT_UP]
    return body


def decode_macro_events(body):
    """Inverse of encode_macro_events: a full body (count + padding +
    events) -> list of (delay_ms, hid_usage, is_down). Raises on a
    truncated body or an event-type byte that is neither 0xB0 nor 0x30.
    CONFIRMED-BY-CAPTURE against the read-back replies."""
    body = list(body)
    if len(body) < 4:
        raise ValueError("macro body shorter than its 4-byte count header")
    words = body[0] | (body[1] << 8)
    if words % 2:
        raise ValueError(f"macro word count {words} is odd (events are 2 words)")
    n = words // 2
    need = 4 + n * MACRO_EVENT_SIZE
    if len(body) < need:
        raise ValueError(f"macro body truncated: need {need}, got {len(body)}")
    events = []
    for k in range(n):
        base = 4 + k * MACRO_EVENT_SIZE
        delay = body[base] | (body[base + 1] << 8)
        usage = body[base + 2]
        kind = body[base + 3]
        if kind == MACRO_EVENT_DOWN:
            is_down = True
        elif kind == MACRO_EVENT_UP:
            is_down = False
        else:
            raise ValueError(f"unknown macro event type byte 0x{kind:02X}")
        events.append((delay, usage, is_down))
    return events


def macro_body_size(words):
    """Body byte size for a stored word count: 4-byte header + words*2."""
    return 4 + int(words) * 2


def build_macro_table(macros_by_slot):
    """Build the full macro table from {slot: [events]}: the 400-byte u32
    LE offset header (empty slots stay 0) followed by the bodies packed
    back to back in slot order from byte 400. CONFIRMED-BY-CAPTURE — the
    captured tables ({0: M1} then {0: M1, 1: M2}) are reproduced
    byte-for-byte, including the literal 90 01 00 00 first entry.
    NOTE (SOURCE-ONLY edge): a populated slot AFTER an empty one was never
    captured — the vendor UI always packs slots densely from 0."""
    header = [0] * MACRO_HEADER_SIZE
    bodies = []
    off = MACRO_HEADER_SIZE
    for slot in sorted(macros_by_slot):
        s = int(slot)
        if not 0 <= s < MACRO_SLOTS:
            raise ValueError(f"macro slot must be 0..{MACRO_SLOTS - 1}")
        body = encode_macro_events(macros_by_slot[slot])
        base = s * 4
        header[base] = off & 0xFF
        header[base + 1] = (off >> 8) & 0xFF
        header[base + 2] = (off >> 16) & 0xFF
        header[base + 3] = (off >> 24) & 0xFF
        bodies += body
        off += len(body)
    return header + bodies


def parse_macro_header(table):
    """The 100 u32 LE body offsets from a macro table (or bare 400-byte
    header); 0 = empty slot. CONFIRMED-BY-CAPTURE."""
    table = list(table)
    if len(table) < MACRO_HEADER_SIZE:
        raise ValueError(f"macro header needs {MACRO_HEADER_SIZE} bytes")
    return [table[i * 4] | (table[i * 4 + 1] << 8)
            | (table[i * 4 + 2] << 16) | (table[i * 4 + 3] << 24)
            for i in range(MACRO_SLOTS)]


def parse_macro_table(table):
    """Full macro table -> {slot: [(delay_ms, hid_usage, is_down), ...]}
    for every populated slot. Inverse of build_macro_table."""
    table = list(table)
    out = {}
    for slot, off in enumerate(parse_macro_header(table)):
        if off == 0:
            continue
        if off + 4 > len(table):
            raise ValueError(f"macro slot {slot} offset {off} out of range")
        words = table[off] | (table[off + 1] << 8)
        out[slot] = decode_macro_events(table[off:off + macro_body_size(words)])
    return out


def build_macro_read_frames(frame_len=FRAME_LEN):
    """The cmd-0x15 frames reading the 400-byte macro OFFSET HEADER
    (wired: 7 pages of 0x38 + the 8-byte tail at 0x0188 with the last-chunk
    flag) — exactly what the official driver sends on every key-remap page
    mount. Bodies are then fetched per macro with build_macro_count_read /
    build_macro_body_read_frames. CONFIRMED-BY-CAPTURE (wired; 0x15 was
    never observed on the dongle)."""
    return list(_iter_paged_read_frames(CMD_MACRO_READ, MACRO_HEADER_SIZE,
                                        frame_len=frame_len))


def build_macro_count_read(offset, frame_len=FRAME_LEN):
    """Step 1 of the vendor's two-step body read: the 4-byte count read at
    the macro's header offset (capture: AA 15 04 90 01 00 01 00).
    CONFIRMED-BY-CAPTURE (wired)."""
    return build_table_read(CMD_MACRO_READ, offset, 4, final=True,
                            frame_len=frame_len)


def build_macro_body_read_frames(offset, words, frame_len=FRAME_LEN):
    """Step 2: read `words`*2 event bytes starting at offset+4 (capture:
    AA 15 10 94 01 00 01 00 after a count of 8, AA 15 20 A8 01 00 01 00
    after a count of 0x10). Single-chunk reads are CONFIRMED-BY-CAPTURE
    (wired); bodies over one chunk page like every other table
    (SOURCE-ONLY — the captured macros were short)."""
    page = page_size(frame_len)
    nbytes = int(words) * 2
    frames = []
    off = 0
    while off < nbytes:
        ln = min(page, nbytes - off)
        frames.append(build_table_read(CMD_MACRO_READ, offset + 4 + off, ln,
                                       final=(off + ln >= nbytes),
                                       frame_len=frame_len))
        off += page
    return frames


def build_macro_write_frames(table, frame_len=FRAME_LEN):
    """The cmd-0x25 write sequence for a full macro table (from
    build_macro_table): the 400-byte header paged (wired: 7 x 0x38 + 0x08 @
    0x0188, final flag on the tail), then per stored body its chunk(s) at
    its header offset, in slot order. CONFIRMED-BY-CAPTURE (wired) —
    reproduces both captured save sequences byte-for-byte (9 frames for
    one macro, 10 for two; the vendor rewrites every body on each save,
    which is what makes read-modify-write mandatory in the driver).
    Bodies longer than one chunk page with the final flag on their last
    chunk (SOURCE-ONLY — never captured). 0x25 was never observed on the
    dongle."""
    table = list(table)
    if len(table) < MACRO_HEADER_SIZE:
        raise ValueError(f"macro table needs at least {MACRO_HEADER_SIZE} bytes")
    frames = list(_iter_paged_write_frames(CMD_MACRO_WRITE,
                                           table[:MACRO_HEADER_SIZE],
                                           frame_len=frame_len))
    for slot, off in enumerate(parse_macro_header(table)):
        if off == 0:
            continue
        if off + 4 > len(table):
            raise ValueError(f"macro slot {slot} offset {off} out of range")
        words = table[off] | (table[off + 1] << 8)
        body = table[off:off + macro_body_size(words)]
        if len(body) != macro_body_size(words):
            raise ValueError(f"macro slot {slot} body truncated")
        frames += list(_iter_paged_write_frames(CMD_MACRO_WRITE, body, base=off,
                                                frame_len=frame_len))
    return frames


def parse_macro_replies(replies):
    """Reassemble cmd-0x15 read replies (header sweep and/or body chunks)
    into a sparse table image: {table byte offset: value} folded into a
    list long enough to hold the highest byte seen. Convenience for tests
    and read paths; the driver's transaction layer does its own
    reassembly. CONFIRMED-BY-CAPTURE framing."""
    chunks = {}
    top = MACRO_HEADER_SIZE
    for reply in replies:
        if reply[0] != REPLY_MAGIC or reply[1] != CMD_MACRO_READ:
            raise ValueError("not a 0x15 macro read reply")
        length = min(reply[2], len(reply) - PAYLOAD_START)
        off = reply[3] | (reply[4] << 8)
        chunks[off] = list(reply[PAYLOAD_START:PAYLOAD_START + length])
        top = max(top, off + length)
    table = [0] * top
    for off, data in chunks.items():
        table[off:off + len(data)] = data
    return table
