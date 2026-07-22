"""Aula WIN60 HE vendor HID protocol — extracted verbatim from the official web
driver (hed.aulacn.com, agreement.min.js, de-obfuscated).

All commands are HID Output reports on Report ID 1 with a 63-byte body; the
first body byte is the command. hidapi's write() wants the Report ID prepended,
so every build_* returns a 64-byte list: [1] + 63 data bytes.

Command map (body[0]):
  1  heartbeat / device-info (body[0]=13 is the info query)
  7  lighting (8 = side lighting)
  9  per-key custom RGB (mode 10) — 2 PERSISTENT slots ([1]=0/1 write,
     0x80/0x81 read back, 0x20 = which slot is active)
  13 device info: firmware string ([3]=0) + build date ([3]=1)
  20 performance / win-lock / gamepad-mode / sleep / reset
  23 music rhythm
  25 macros (10 slots x 256 B, bound via keymap entry type 0x10)
  33 trigger family: actuation, travel-test, poll-rate, key-remap
  36 PRCS / SOCD
  37 switch profile
  38 dead band (write [1]=1; read request [1]=0, 264-byte table back)

Wire provenance: everything marked CONFIRMED-BY-CAPTURE below was verified
frame-by-frame against a live capture of the official driver on a physical
WIN 60 HE (docs/context/hed-aulacn-raw/webhid-capture-win60.json, 2026-07-21;
analysis in WIN60_CAPTURE_NOTES.md). Anything marked SOURCE-ONLY comes from
the de-obfuscated driver source alone and has not been seen on the wire.
"""

REPORT_ID = 1
BODY = 63
TRIGGER_UNIT_MM = 0.01   # travel/interval values are in 0.01 mm steps


def _pkt(cmd):
    data = [0] * BODY
    data[0] = cmd
    return data


def _wrap(data):
    return [REPORT_ID] + data


def mm_to_raw(mm):
    return max(0, round(mm / TRIGGER_UNIT_MM))


def _keymask(indices):
    """22-byte bitmask: byte[i%22] |= 1<<(i//22) — the driver's key-select form."""
    mask = [0] * 22
    for i in indices:
        mask[i % 22] |= 1 << (i // 22)
    return mask


# ---------------- lighting (cmd 7) ----------------
def build_read_light_list():
    """Ask the firmware which lighting modes it supports (driver: readLightList).
    Response echoes cmd 10; parse with parse_light_list()."""
    d = _pkt(10)
    return _wrap(d)


def build_read_side_light_list():
    """Same, for the side/edge LEDs (driver: readSideLightList, cmd 2)."""
    d = _pkt(2)
    return _wrap(d)


def parse_light_list(report):
    """Decode a light-list response. `report` is a raw hidapi read() result,
    so it INCLUDES the report id at [0] and the echoed cmd at [1].

    Driver layout (body, i.e. report[1:]): body[0]=cmd(10 or 2), body[4]=length,
    body[5:5+length]=payload; within the payload the last two bytes are
    maxSpeed,maxBrightness and the rest (minus 4 trailing) are the mode bytes.
    Returns {"modes": [...], "max_speed": n, "max_brightness": n} or None.
    """
    if len(report) < 6 or report[1] not in (10, 2):
        return None
    length = report[5]
    # The device length byte is untrusted: a corrupt/short frame with an
    # oversized length would make payload[length-1] index past the slice.
    # Require the full payload to be present (matches parse_custom_light_chunk
    # et al.), so the fixed-index reads below are always in bounds.
    if 6 + length > len(report):
        return None
    payload = report[6:6 + length]
    if len(payload) < 4:
        return None
    return {
        "modes": list(payload[:length - 4]),
        "max_speed": payload[length - 2],
        "max_brightness": payload[length - 1],
    }


def build_light(mode, brightness, speed, fg, bg=(0, 0, 0),
                direction=0, full_color=0, power_on=True, side=False):
    d = _pkt(8 if side else 7)
    d[4] = 14
    d[5] = mode & 0xFF
    d[6] = brightness & 0xFF
    d[7] = speed & 0xFF
    d[8], d[9], d[10] = (c & 0xFF for c in fg)
    d[11], d[12], d[13] = (c & 0xFF for c in bg)
    d[14] = direction & 0xFF
    d[15] = full_color & 0xFF
    d[16] = 0 if power_on else 1
    return _wrap(d)


def build_custom_light(colors_by_index, slot=0, total_bytes=396):
    """Build cmd-9 per-key RGB packets for custom lighting mode 10.

    The official driver sends a 396-byte RGB table in 54-byte chunks. Each key's
    RGB starts at index*3. `colors_by_index` maps device key index -> (r,g,b).

    CONFIRMED-BY-CAPTURE: the cmd-9 table is BOARD-PERSISTENT storage, not a
    volatile stream — at mount (webhid-capture-win60.json frames 151-169,
    before this session wrote anything) the board served back non-zero tables
    written in a PREVIOUS session, and the firmware renders effect mode 10
    from the stored table at power-on. There are two flash-backed slots
    (`slot` 0 = the vendor UI's "Custom1", 1 = "Custom2"); writing a slot's
    table also makes that slot the displayed one (the vendor UI switches
    palettes by re-sending the full table to the chosen slot — no separate
    "activate" command exists in source or capture). This builder reproduces
    the captured writes of BOTH slots byte-for-byte (frames 753-767 slot 1,
    774-788 slot 0). Read a slot back with build_read_custom_light(); read
    which slot is active with build_read_custom_number().
    """
    table = [0] * total_bytes
    for idx, rgb in colors_by_index.items():
        off = int(idx) * 3
        if off + 2 >= total_bytes:
            continue
        table[off], table[off + 1], table[off + 2] = (int(c) & 0xFF for c in rgb)
    packets = []
    chunk = 54
    for page, start in enumerate(range(0, total_bytes, chunk)):
        part = table[start:start + chunk]
        d = _pkt(9)
        d[1] = int(slot) & 0xFF
        d[2] = (page >> 8) & 0xFF
        d[3] = page & 0xFF
        d[4] = len(part)
        d[5:5 + len(part)] = part
        packets.append(_wrap(d))
    return packets


# ---------------- per-key custom RGB read-back (cmd 9) ----------------
CUSTOM_LIGHT_TABLE_BYTES = 396   # 132 keys x RGB
CUSTOM_LIGHT_CHUNK = 54          # 7 x 54 + 18 = 396, pages 0..7
CUSTOM_LIGHT_SLOTS = 2           # vendor UI "Custom1" / "Custom2", both stored


def build_read_custom_light(slot=0):
    """Ask the firmware to stream back one stored per-key color slot
    (driver: initCustomLightValue). CONFIRMED-BY-CAPTURE: OUT `09 80`
    (slot 0) / `09 81` (slot 1), answered with 8 chunks shaped like the
    write pages: [9, 0x80|slot, page_hi, page_lo, len, rgb...]
    (7 x 54 + 18 = 396 bytes). Parse each reply chunk with
    parse_custom_light_chunk() and reassemble with
    assemble_custom_light_table()."""
    slot = int(slot)
    if not 0 <= slot < CUSTOM_LIGHT_SLOTS:
        raise ValueError("custom light slot out of range 0..%d"
                         % (CUSTOM_LIGHT_SLOTS - 1))
    d = _pkt(9)
    d[1] = 0x80 | slot
    return _wrap(d)


def parse_custom_light_chunk(body, slot):
    """Decode one cmd-9 read-reply chunk BODY (63 bytes, report id already
    stripped — i.e. exactly the capture's `hex` field) for `slot`. Returns
    {"page": n, "data": [...]} or None if the body isn't a read chunk for
    that slot (write ACKs / the 09-20 reply carry [1] < 0x80 and len 0)."""
    if len(body) < 6 or body[0] != 9 or body[1] != (0x80 | (int(slot) & 1)):
        return None
    page = (body[2] << 8) | body[3]
    length = body[4]
    if length == 0 or 5 + length > len(body):
        return None
    return {"page": page, "data": list(body[5:5 + length])}


def assemble_custom_light_table(chunks):
    """Merge parse_custom_light_chunk() results into the flat 396-byte table.
    Returns bytes(396) only when every page (0..7, 54-byte stride) arrived;
    None on a partial read so callers refuse to treat a half-zeroed table as
    the board's stored colors."""
    table = bytearray(CUSTOM_LIGHT_TABLE_BYTES)
    seen = set()
    for ch in chunks:
        if not ch:
            continue
        start = ch["page"] * CUSTOM_LIGHT_CHUNK
        data = ch["data"][:max(0, CUSTOM_LIGHT_TABLE_BYTES - start)]
        if not data:
            continue
        table[start:start + len(data)] = bytes(data)
        seen.add(ch["page"])
    n_pages = ((CUSTOM_LIGHT_TABLE_BYTES + CUSTOM_LIGHT_CHUNK - 1)
               // CUSTOM_LIGHT_CHUNK)
    return bytes(table) if len(seen) >= n_pages else None


def custom_light_colors(table):
    """Decode a 396-byte custom-light table into {device index: (r, g, b)}
    for ALL 132 slots (zeros included), so that
    build_custom_light(custom_light_colors(t), slot=s) reproduces the wire
    bytes exactly — verified byte-for-byte against the captured slot-0 and
    slot-1 writes."""
    table = list(table)
    return {i: (table[3 * i], table[3 * i + 1], table[3 * i + 2])
            for i in range(len(table) // 3)}


def build_read_custom_number():
    """Ask which custom slot is currently active/displayed (driver:
    initCustomNumber). CONFIRMED-BY-CAPTURE: OUT `09 20`, answered with
    `09 <slot> 00 00 00` — the vendor handler checks the Custom1/Custom2
    radio from reply body[1]. Sent by the vendor at every mount, right
    before reading both slots."""
    d = _pkt(9)
    d[1] = 0x20
    return _wrap(d)


def parse_custom_number(body):
    """Decode the reply to build_read_custom_number(): returns the active
    slot (0 or 1) or None. NOTE: cmd-9 table-write ACKs have the identical
    shape `09 <slot> ... len=0` — semantically consistent (the last-written
    slot IS the active one), but drain pending input before relying on this
    as a query reply."""
    if len(body) < 5 or body[0] != 9 or body[1] not in (0, 1):
        return None
    if body[4] != 0:          # a table chunk, not a bare slot echo
        return None
    return body[1]


# ---------------- actuation / trigger (cmd 33) ----------------
def build_trigger(mode, key_indices, travel_mm, rt_press_mm=0.0, rt_release_mm=0.0):
    """Set actuation (and Rapid Trigger) for the given device key indices.
    interval1 = RT press sensitivity, interval2 = RT release."""
    travel = mm_to_raw(travel_mm)
    i1 = mm_to_raw(rt_press_mm)
    i2 = mm_to_raw(rt_release_mm)
    sub = [0] * 31
    sub[0] = mode & 0xFF
    mask = _keymask(key_indices)
    for j in range(22):
        sub[1 + j] = mask[j]
    sub[23] = travel & 0xFF
    sub[24] = travel & 0xFF
    sub[25] = i1 & 0xFF
    sub[26] = i2 & 0xFF
    sub[27] = (travel >> 8) & 0xFF
    sub[28] = (travel >> 8) & 0xFF
    sub[29] = (i1 >> 8) & 0xFF
    sub[30] = (i2 >> 8) & 0xFF
    d = _pkt(33)
    d[4] = 24
    d[5:5 + 31] = sub
    return _wrap(d)


def build_open_trigger_test(key_indices):
    """Enable live analog travel streaming for the given keys (cmd 33, sub 2)."""
    d = _pkt(33); d[4] = 24; d[5] = 2
    mask = _keymask(key_indices)
    d[6:6 + 22] = mask
    return _wrap(d)


def build_close_trigger_test():
    d = _pkt(33); d[4] = 24; d[5] = 3
    return _wrap(d)


def build_reset_trigger():
    d = _pkt(33); d[4] = 24; d[5] = 6
    return _wrap(d)


def build_poll_rate(rate):
    """rate is the device's poll code (the driver sends pollRate directly)."""
    d = _pkt(33); d[5] = 9; d[6] = 1; d[7] = rate & 0xFF
    return _wrap(d)


def build_remap(index):
    d = _pkt(33); d[4] = 24; d[5] = 7
    d[6] = index // 22
    d[7] = index % 22
    return _wrap(d)


def build_base_keymap_table(default_hids, overrides=None, layer_indices=None):
    """Base-layer key table (cmd 24, header [1]=0), matching the driver's setKeyValue.

    The board stores a flat table of 4 bytes per key index — [code1, hidCode,
    code3, code4] — so a remap must send EVERY key, not just the changed one, or
    the rest get zeroed. We start from `default_hids` ({index: default_hid}) and
    apply `overrides` ({index: target_hid}) on top.

    `code1` is the key TYPE: 1 for the Fn/layer-shift key (`code === "KeyFn"`),
    0 for ordinary keys. Writing 0 for the Fn key makes the firmware treat Fn
    as a normal key, which "sticks" the function layer."""
    overrides = overrides or {}
    layer_indices = set(layer_indices or ())
    table = bytearray(528)
    for idx, hid in default_hids.items():
        if idx in overrides:
            h = overrides[idx]
            code1 = 0                       # a remapped key is a plain key
        else:
            h = hid
            code1 = 1 if idx in layer_indices else 0
        if idx * 4 + 1 < len(table):
            table[idx * 4] = code1 & 0xFF
            table[idx * 4 + 1] = int(h) & 0xFF
    for idx, hid in overrides.items():
        if idx not in default_hids and idx * 4 + 1 < len(table):
            table[idx * 4 + 1] = int(hid) & 0xFF
    return _paged_keymap_packets(table, layer_byte=0)


def build_fn_keymap_table(raw_528):
    """Fn-layer key table (cmd 24, header [1]=2), matching the driver's setFnKeyValue.

    `raw_528` is a 528-byte bytes/bytearray to send verbatim — typically captured
    from `read_keymap_layer(fn=True)` on connect so the device's existing Fn
    mappings are preserved across base-layer writes."""
    table = bytearray(528)
    if raw_528:
        n = min(len(raw_528), 528)
        table[:n] = bytes(raw_528[:n])
    return _paged_keymap_packets(table, layer_byte=2)


def _paged_keymap_packets(table, layer_byte):
    """Page a 528-byte keymap table into 56-byte chunks under [24, layer, page_hi, page_lo, len, ...]."""
    page_size = 56
    packets = []
    n_pages = (len(table) + page_size - 1) // page_size
    for page in range(n_pages):
        start = page * page_size
        part = table[start:start + page_size]
        d = _pkt(24)
        d[1] = layer_byte & 0xFF
        d[2] = (page >> 8) & 0xFF
        d[3] = page & 0xFF
        d[4] = len(part)
        d[5:5 + len(part)] = list(part)
        packets.append(_wrap(d))
    return packets


def build_read_keymap_init(fn_layer=False):
    """Ask the firmware to stream the keymap table back (driver's initKeyValue).
    Response: a series of cmd-24 packets with [1]=128 (base) or 130 (fn)."""
    d = _pkt(24)
    d[1] = 130 if fn_layer else 128
    return _wrap(d)


# Back-compat shim: old name kept so existing imports/tests don't break.
def build_keymap_table(default_hids, overrides=None, layer_indices=None, fn_layer=False):
    if fn_layer:
        return build_fn_keymap_table(bytes(528))
    return build_base_keymap_table(default_hids, overrides, layer_indices)


def build_revise(a, b):
    d = _pkt(33); d[4] = 24; d[5] = a & 0xFF; d[6] = b & 0xFF
    return _wrap(d)


def build_calibration(start, any_key=False):
    """Start/stop key calibration (driver: reviseKeys). all-key=8/0 start, 8/1
    stop; any-key=15/0 start, 16/0 stop."""
    if any_key:
        return build_revise(15 if start else 16, 0)
    return build_revise(8, 0 if start else 1)


# ---------------- switch profile / dead band (cmd 37 / 38) ----------------
def _paged_table_packets(cmd, values, page_size=58):
    packets = []
    for page, start in enumerate(range(0, len(values), page_size)):
        part = values[start:start + page_size]
        d = _pkt(cmd)
        d[1] = 1
        d[2] = (page >> 8) & 0xFF
        d[3] = page & 0xFF
        d[4] = len(part)
        d[5:5 + len(part)] = [int(v) & 0xFF for v in part]
        packets.append(_wrap(d))
    return packets


def build_switch_table(switch_by_index, default_switch=1, key_count=132):
    """Set magnetic switch profile per device index.

    The vendor driver sends a 132-byte table through cmd 37, sub 1, in 58-byte
    pages. Values are switch profile ids from the driver's switch list.
    """
    values = [int(default_switch)] * int(key_count)
    for idx, switch_id in (switch_by_index or {}).items():
        idx = int(idx)
        if 0 <= idx < len(values):
            values[idx] = int(switch_id)
    return _paged_table_packets(37, values)


DEADBAND_TABLE_BYTES = 264   # 132 keys x [top, bottom], 0.01 mm units


def build_deadband_table(deadband_by_index, default_top=4, default_bottom=5,
                         key_count=132, base_table=None):
    """Set top/bottom dead-band per device index.

    Firmware values are hundredths of a millimeter, matching the official UI's
    integer deadbandTop/deadbandBottom fields.

    `base_table` (additive, optional): a full 264-byte [top, bottom]*132 table
    to start from — typically the device's CURRENT table obtained via
    build_read_deadband() — so only the requested indices change. Without it
    every key is filled with default_top/default_bottom, which CONFIRMED-BY-
    CAPTURE does NOT match this board: the WIN 60 HE's real per-key dead band
    is 2/2 (0.02 mm) on its 61 physical keys and 0/0 on unpopulated slots
    (webhid-capture-win60.json frames 7690-7695), so a constant fill silently
    rewrites every untouched key. Prefer read-modify-write (the Win60 driver
    does); the constant-default path is kept for callers that pass explicit
    defaults deliberately.
    """
    if base_table is not None:
        values = [int(v) & 0xFF for v in list(base_table)[:int(key_count) * 2]]
        values.extend([0] * (int(key_count) * 2 - len(values)))
    else:
        values = []
        for _ in range(int(key_count)):
            values.extend([int(default_top), int(default_bottom)])
    for idx, pair in (deadband_by_index or {}).items():
        idx = int(idx)
        if 0 <= idx < int(key_count):
            top, bottom = pair
            values[idx * 2] = int(top)
            values[idx * 2 + 1] = int(bottom)
    return _paged_table_packets(38, values)


def build_read_deadband():
    """Ask for the current 264-byte dead-band table (cmd 38, [1]=0).

    CONFIRMED-BY-CAPTURE: OUT `26 00 00 ...` is answered with 5 chunks
    (4 x 58 + 32 bytes) shaped like the write pages: body =
    [38, 0, page_hi, page_lo, len, payload...]. Parse each reply chunk with
    parse_deadband_chunk() and reassemble with assemble_deadband_table().
    """
    return _wrap(_pkt(38))


def parse_deadband_chunk(body):
    """Decode one cmd-38 read-reply chunk BODY (63 bytes, report id already
    stripped — i.e. exactly the capture's `hex` field). Returns
    {"page": n, "data": [...]} or None if the body isn't a read chunk
    (writes echo with [1]=1; read chunks carry [1]=0)."""
    if len(body) < 6 or body[0] != 38 or body[1] != 0:
        return None
    page = (body[2] << 8) | body[3]
    length = body[4]
    if length == 0 or 5 + length > len(body):
        return None
    return {"page": page, "data": list(body[5:5 + length])}


def assemble_deadband_table(chunks):
    """Merge parse_deadband_chunk() results into the flat 264-byte table.
    Returns bytes(264) only when every page (0..4, 58-byte stride) arrived;
    None on a partial read so callers refuse to write a half-zeroed table."""
    table = bytearray(DEADBAND_TABLE_BYTES)
    seen = set()
    for ch in chunks:
        if not ch:
            continue
        start = ch["page"] * 58
        data = ch["data"][:max(0, DEADBAND_TABLE_BYTES - start)]
        if not data:
            continue
        table[start:start + len(data)] = bytes(data)
        seen.add(ch["page"])
    n_pages = (DEADBAND_TABLE_BYTES + 57) // 58
    return bytes(table) if len(seen) >= n_pages else None


# ---------------- SOCD / PRCS (cmd 36) ----------------
def build_prcs_power(on):
    d = _pkt(36); d[1] = 3; d[4] = 1; d[5] = 1 if on else 0
    return _wrap(d)


def build_prcs(prcs_list):
    """prcs_list: list of dicts {model, key1_hid, key2_hid}. Up to 20, sent as
    two packets of 10. Returns a list of payloads."""
    out = []
    for page in range(2):
        d = _pkt(36); d[1] = 0; d[2] = (page >> 8) & 0xFF; d[3] = page & 0xFF; d[4] = 40
        for j in range(10):
            idx = page * 10 + j
            if idx < len(prcs_list):
                p = prcs_list[idx]
                d[j * 4 + 5] = 1
                d[j * 4 + 6] = p["model"] & 0xFF
                d[j * 4 + 7] = p["key1_hid"] & 0xFF
                d[j * 4 + 8] = p["key2_hid"] & 0xFF
        out.append(_wrap(d))
    return out


# ---------------- misc (cmd 20) ----------------
def build_gamepad_mode(mode):
    """Switch the keyboard's built-in gamepad mode (cmd 20, sub 3)."""
    d = _pkt(20); d[1] = 3; d[4] = 1; d[5] = mode & 0xFF
    return _wrap(d)


def build_win_lock(disable_win=False, disable_shift_tab=False,
                   disable_alt_tab=False, disable_alt_f4=False, win_lock_on=True):
    d = _pkt(20); d[4] = 1
    d[12] = 1 if disable_win else 0
    d[13] = 1 if disable_shift_tab else 0
    d[14] = 1 if disable_alt_tab else 0
    d[15] = 1 if disable_alt_f4 else 0
    d[18] = 1 if win_lock_on else 0
    return _wrap(d)


def build_reset_keyboard():
    d = _pkt(20); d[4] = 1; d[5] = 1
    return _wrap(d)


def build_heartbeat():
    return _wrap(_pkt(1))


# ---------------- music rhythm (cmd 23 / 0x17) ----------------
def build_music_rhythm(on):
    """Enter/leave music-rhythm lighting state (driver: setMusicRhythmState).

    CONFIRMED-BY-CAPTURE: OUT `17 00 00 00 02 01 01` (on) /
    `17 00 00 00 02 00 00` (off); payload length 2, body[5] and body[6] both
    carry the flag. The vendor driver brackets EVERY non-music light write
    with `build_music_rhythm(False)` first, so a board left in rhythm mode by
    the official driver can't get stuck there. Aether's current light path
    (Win60Driver.set_lighting) does NOT send this and has worked on hardware
    as-is, so its ordering is deliberately unchanged; if a board is ever
    observed stuck in music mode after a light write, send
    build_music_rhythm(False) immediately before the cmd-7 write to mirror
    the vendor ordering.
    """
    d = _pkt(23)
    d[4] = 2
    d[5] = 1 if on else 0
    d[6] = 1 if on else 0
    return _wrap(d)


# ---------------- device info (cmd 13 / 0x0d) ----------------
def build_device_info_query():
    """Ask for the device-info strings (cmd 13). CONFIRMED-BY-CAPTURE: the
    vendor driver sends this twice at mount; replies carry body[3]=0 (model /
    firmware string, e.g. "W669,34,KB,SI,SI2825KZHEARGB,V3.17.07") and
    body[3]=1 (build date, e.g. "Apr 15 2026,11:20:35")."""
    return _wrap(_pkt(13))


def parse_device_info(body):
    """Decode a cmd-13 reply BODY (63 bytes, report id stripped). Returns
    {"index": 0|1, "text": str} — index 0 = model/firmware string,
    1 = build date — or None. Text is ASCII, cut at the first NUL (the
    firmware leaves stale bytes after the terminator; CONFIRMED-BY-CAPTURE
    on the build-date reply)."""
    if len(body) < 6 or body[0] != 13:
        return None
    length = body[4]
    raw = bytes(body[5:5 + length])
    if b"\x00" in raw:
        raw = raw.split(b"\x00", 1)[0]
    return {"index": body[3], "text": raw.decode("ascii", errors="replace")}


# ---------------- initInfo / heartbeat reply (cmd 1) ----------------
def parse_init_info(body):
    """Decode the cmd-1 initInfo/heartbeat reply BODY (63 bytes, report id
    stripped — i.e. exactly the capture's `hex` field).

    CONFIRMED-BY-CAPTURE (WIN60_CAPTURE_NOTES.md §2): the capability bitmask
    is real — flags1 = body[17], flags2 = body[18], field offsets from the
    vendor driver's own parser (p = body[5..22]). On the WIN 60 HE
    body[17]=0x7f, body[18]=0x00: PRCS/custom-light/poll-rate/dead-band/
    music-rhythm/any-key-calibration all True; gamepad/RS/RKRT/6-key-mode/
    high-precision all False. tri_mode: 0 = USB, 1 = 2.4G. battery is 0 on
    this wired board.

    is_high_precision selects the travel divisor (1000 vs 100) — see
    parse_max_trigger_travel(). Callers should gate features on these bits
    rather than static registry flags where possible.
    """
    # body[4] == 0x11 (payload len 17) is constant on the wire and doubles as
    # a guard against mistaking a report-id-prefixed frame (leading 0x01) for
    # an initInfo body.
    if len(body) < 23 or body[0] != 1 or body[4] != 0x11:
        return None
    flags1 = body[17]
    flags2 = body[18]
    return {
        "charging": bool(body[8]),
        "battery": body[9],
        "tri_mode": body[10],
        "is_prcs": body[14] == 1,
        "is_any_key_calibration": bool(flags1 & 0x01),
        "is_custom_light": bool(flags1 & 0x02),
        "is_more_switch": bool(flags1 & 0x04),
        "is_poll_rate": bool(flags1 & 0x08),
        "is_dead_band": bool(flags1 & 0x10),
        "is_music_rhythm": bool(flags1 & 0x20),
        "is_all_and_6key_switch": bool(flags1 & 0x80),
        "is_high_precision": bool(flags2 & 0x01),
        "is_gamepad": bool(flags2 & 0x04),
        "is_rs": bool(flags2 & 0x08),
        "is_rkrt": bool(flags2 & 0x10),
        "is_music_rhythm_on": bool(body[21]),
        "is_6key_mode": bool(body[22] & 0x01),
    }


# ---------------- readMaxTriggerTravel (cmd 33, sub 4) ----------------
def build_read_max_trigger_travel():
    """Ask the firmware for its travel unit and travel range (driver:
    readMaxTriggerTravel). CONFIRMED-BY-CAPTURE: OUT `21 00 00 00 18 04`."""
    d = _pkt(33)
    d[4] = 24
    d[5] = 4
    return _wrap(d)


def parse_max_trigger_travel(body, high_precision=False):
    """Decode the cmd-33 sub-4 reply BODY (63 bytes, report id stripped).

    CONFIRMED-BY-CAPTURE: IN `21 00 00 00 06 04 54 01 01 01 08` on the
    WIN 60 HE decodes (with the vendor driver's own field expressions) to
    unit numerator body[7] (0 means 10), max travel body[9]<<8 | body[6],
    min travel body[10]. Divisor is 1000 when the initInfo
    is_high_precision bit is set, else 100 — pass that bit in. On this board
    that yields unit 0.01 mm, max 3.40 mm, min 0.08 mm — byte-identical to
    Aether's hardcoded TRIGGER_UNIT_MM/min/max, so the constants are CORRECT
    here; use this reader on OTHER boards in the family instead of assuming.
    Returns None if the body isn't a sub-4 reply.
    """
    if len(body) < 11 or body[0] != 33 or body[5] != 4:
        return None
    numer = body[7] if body[7] != 0 else 10
    divisor = 1000 if high_precision else 100
    unit_mm = numer / divisor
    max_raw = (body[9] << 8) | body[6]
    min_raw = body[10]
    return {
        "unit_numerator": numer,
        "divisor": divisor,
        "unit_mm": unit_mm,
        "max_travel_raw": max_raw,
        "min_travel_raw": min_raw,
        "max_travel_mm": max_raw * unit_mm,
        "min_travel_mm": min_raw * unit_mm,
    }


# ---------------- macros (cmd 25 / 0x19) ----------------
# CONFIRMED-BY-CAPTURE, and a COMPLETELY DIFFERENT format from the MINI 60's
# macro protocol (protocol_mini60) — do not unify them. 10 slots x 256 bytes,
# written in 5 chunks (4 x 58 + 24). Slot image: 8-byte header
# [slot, slot, event_bytes_hi, event_bytes_lo, 0, repeat_count, 0, 0]
# (event length BIG-endian), then 4-byte events
# [hid_code, 0x10 down | 0x00 up, delay_ms_hi, delay_ms_lo] (delay BE,
# measured after the event). A macro fires from a key via the keymap entry
# [0x10, hid_code, macro_slot, 0] — see macro_keymap_entry(). An unused slot
# reads back as all 0xFF.
MACRO_SLOTS = 10
MACRO_SLOT_BYTES = 256
MACRO_EVENT_DOWN = 0x10
MACRO_EVENT_UP = 0x00
MACRO_MAX_EVENTS = (MACRO_SLOT_BYTES - 8) // 4   # 62


def build_macro_table(slot, events, repeat_count=1):
    """Build the 256-byte slot image. `events` is a sequence of
    (hid_code, is_down, delay_ms) tuples; delay is the ms measured AFTER the
    event (BE16 on the wire). repeat_count: UI "Operate Once" = 1,
    "Operate N times" = N (macro types 3/4 — toggle / hold — are NOT
    VERIFIED and not built here)."""
    slot = int(slot)
    if not 0 <= slot < MACRO_SLOTS:
        raise ValueError("macro slot out of range 0..9")
    events = list(events or ())
    if len(events) > MACRO_MAX_EVENTS:
        raise ValueError("macro too long: max %d events" % MACRO_MAX_EVENTS)
    table = [0] * MACRO_SLOT_BYTES
    table[0] = slot
    table[1] = slot
    n = len(events) * 4
    table[2] = (n >> 8) & 0xFF
    table[3] = n & 0xFF
    table[5] = int(repeat_count) & 0xFF
    off = 8
    for hid_code, is_down, delay_ms in events:
        delay = max(0, int(delay_ms))
        table[off] = int(hid_code) & 0xFF
        table[off + 1] = MACRO_EVENT_DOWN if is_down else MACRO_EVENT_UP
        table[off + 2] = (delay >> 8) & 0xFF
        table[off + 3] = delay & 0xFF
        off += 4
    return table


def build_macro_packets(slot, events, repeat_count=1):
    """Page a macro slot into its 5 cmd-25 write packets
    ([25, slot, page_hi, page_lo, len, payload...], 58-byte chunks).
    CONFIRMED-BY-CAPTURE byte-for-byte, including events split across the
    chunk boundary."""
    table = build_macro_table(slot, events, repeat_count)
    packets = []
    chunk = 58
    for page, start in enumerate(range(0, MACRO_SLOT_BYTES, chunk)):
        part = table[start:start + chunk]
        d = _pkt(25)
        d[1] = int(slot) & 0xFF
        d[2] = (page >> 8) & 0xFF
        d[3] = page & 0xFF
        d[4] = len(part)
        d[5:5 + len(part)] = part
        packets.append(_wrap(d))
    return packets


def build_read_macro(slot):
    """Ask for one macro slot back (cmd 25, [1] = slot | 0x80). The reply is
    5 chunks shaped like the write pages with [1] = slot | 0x80; an empty
    slot reads back all 0xFF. CONFIRMED-BY-CAPTURE."""
    slot = int(slot)
    if not 0 <= slot < MACRO_SLOTS:
        raise ValueError("macro slot out of range 0..9")
    d = _pkt(25)
    d[1] = 0x80 | slot
    return _wrap(d)


def parse_macro_chunk(body, slot):
    """Decode one cmd-25 read-reply chunk BODY for `slot`. Returns
    {"page": n, "data": [...]} or None."""
    if len(body) < 6 or body[0] != 25 or body[1] != (0x80 | (int(slot) & 0x0F)):
        return None
    page = (body[2] << 8) | body[3]
    length = body[4]
    if length == 0 or 5 + length > len(body):
        return None
    return {"page": page, "data": list(body[5:5 + length])}


def parse_macro_table(table):
    """Decode a 256-byte macro slot image. Returns None for an empty slot
    (all 0xFF), else {"slot", "repeat_count", "events": [(hid_code, is_down,
    delay_ms), ...]}. Inverse of build_macro_table()."""
    table = list(table)
    if len(table) < 8:
        return None
    if all(b == 0xFF for b in table):
        return None
    n = ((table[2] << 8) | table[3]) & ~3
    n = min(n, MACRO_SLOT_BYTES - 8)
    events = []
    for off in range(8, 8 + n, 4):
        events.append((table[off],
                       table[off + 1] == MACRO_EVENT_DOWN,
                       (table[off + 2] << 8) | table[off + 3]))
    return {"slot": table[0], "repeat_count": table[5], "events": events}


def macro_keymap_entry(macro_slot, hid_code):
    """The 4-byte keymap-table entry that binds a macro to a key:
    [type=0x10, original hid code, macro slot, 0]. CONFIRMED-BY-CAPTURE
    (keymap slot 96 `10 10 00 00` = macro 0 on M, slot 95 `10 11 01 00` =
    macro 1 on N). NOTE: writing this entry means rewriting the ENTIRE
    528-byte keymap layer, exactly like any other remap."""
    return [0x10, int(hid_code) & 0xFF, int(macro_slot) & 0xFF, 0]


def parse_trigger_read(body):
    """Decode a cmd-33 sub-5 trigger-read response body (without report id).

    body[i] == r[i+1] for the raw 64-byte report r. Per the hardware-verified
    sub-5 travel layout (see device_state.LiveReader): r[7]=row, r[8]=col,
    r[9]/r[10]=depth lo/hi. In body terms row=body[6], col=body[7],
    depth lo/hi = body[8]/body[9]. travel is in 0.01 mm units.
    """
    return {
        "row": body[6],
        "col": body[7],
        "travel": body[8] | (body[9] << 8),
    }
