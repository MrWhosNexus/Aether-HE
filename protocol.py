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
        i = int(i)
        # 22 columns x 8 bit-rows is all a byte mask can address; a larger
        # index would set bit 8+ and produce a >255 byte that hidapi rejects
        # (or, masked, silently select the wrong key).
        if not 0 <= i < 22 * 8:
            raise ValueError(f"key index {i} outside the 22x8 key mask")
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
#: The RT interval pair a factory-fresh WIN 60 HE stores on every key, in
#: trigger units. CONFIRMED-BY-CAPTURE: the mount-time readTriggerData reply
#: (webhid-capture-win60.json frame 173, before this session wrote anything)
#: carries interval1 = interval2 = 1, and the vendor's first fixed-mode write
#: (frame 922, `... 64 64 01 01`) echoes exactly that stored pair. The vendor
#: NEVER sends zero intervals in mode 0 — setAnyTriggerValue always copies
#: key.trigger.interval1/2, which readTriggerData filled at mount (agreement
#: deobfuscated.js L1532-1538 / L966-969); frame 1842 ("Rapid Trigger -> OFF")
#: is mode 0 with the previous RT pair `78 78` still in place. Used only as
#: the fallback when a key's stored pair cannot be read back.
TRIGGER_DEFAULT_INTERVAL_RAW = 1


def build_trigger_raw(mode, key_indices, travel_raw, i1_raw, i2_raw):
    """build_trigger() in raw trigger units (0.01 mm on the WIN 60 HE) —
    the form to use when re-sending values READ BACK from the board, so a
    stored pair round-trips byte-for-byte with no mm conversion."""
    travel = int(travel_raw)
    i1 = int(i1_raw)
    i2 = int(i2_raw)
    if not (0 <= travel <= 0xFFFF and 0 <= i1 <= 0xFFFF and 0 <= i2 <= 0xFFFF):
        raise ValueError("trigger values must fit 16 bits")
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


def build_trigger(mode, key_indices, travel_mm, rt_press_mm=0.0, rt_release_mm=0.0):
    """Set actuation (and Rapid Trigger) for the given device key indices.
    interval1 = RT press sensitivity, interval2 = RT release."""
    return build_trigger_raw(mode, key_indices, mm_to_raw(travel_mm),
                             mm_to_raw(rt_press_mm), mm_to_raw(rt_release_mm))


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
    as a normal key, which "sticks" the function layer.

    NOTE: this rebuilds the WHOLE table from the layout, so any binding the
    board holds that Aether did not make (a vendor macro entry `10 <hid>
    <slot> 00`, an advanced key) is zeroed. It is kept only for write-only
    stubs; the driver's remap path composes over the board's read-back via
    compose_base_keymap() + build_base_keymap_raw() instead."""
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


SWITCH_TABLE_BYTES = 132   # one switch-profile id per device index


def build_switch_table(switch_by_index, default_switch=1, key_count=132,
                       base_table=None):
    """Set magnetic switch profile per device index.

    The vendor driver sends a 132-byte table through cmd 37, sub 1, in 58-byte
    pages. Values are switch profile ids from the driver's switch list.

    `base_table` (additive, optional): the board's CURRENT 132-byte table
    (build_read_switch_table() -> assemble_switch_table()) so only the
    requested indices change. Without it every other key is filled with
    `default_switch` — which silently rewrites every key the caller did NOT
    select (select WASD -> TC1, then Space -> HH1 sends WASD back to HM1).
    CONFIRMED-BY-CAPTURE (webhid-capture-win60.json frames 1578-1581): the
    vendor builds the table from each key's own stored `switch` value and
    writes 0 on unpopulated slots, not a constant.
    """
    n = int(key_count)
    if base_table is not None:
        values = [int(v) & 0xFF for v in list(base_table)[:n]]
        values.extend([0] * (n - len(values)))
    else:
        values = [int(default_switch)] * n
    for idx, switch_id in (switch_by_index or {}).items():
        idx = int(idx)
        sid = int(switch_id)
        if not 0 <= sid <= 0xFF:
            raise ValueError(f"switch id {sid} is not a byte")
        if 0 <= idx < len(values):
            values[idx] = sid
    return _paged_table_packets(37, values)


def build_read_switch_list():
    """Ask which switch profiles the firmware offers (driver: initSwitchList,
    cmd 37 [1]=0). CONFIRMED-BY-CAPTURE: OUT `25 00`, answered with
    `25 00 00 00 06 00 04 01 02 03 05` — parse with parse_switch_list()."""
    return _wrap(_pkt(37))


def parse_switch_list(body):
    """Decode the cmd-37 sub-0 reply BODY (report id stripped) into the
    list of switch ids the board supports, or None. Vendor layout
    (agreement.js initSwitchList handler): payload = body[5:5+body[4]],
    count = payload[0]<<8 | payload[1] (BE16), ids = payload[2:2+count].
    The WIN 60 HE answers [1, 2, 3, 5] = HM1, HH1, CY1, TC1."""
    if len(body) < 7 or body[0] != 37 or body[1] != 0:
        return None
    length = body[4]
    if length < 2 or 5 + length > len(body):
        return None
    payload = list(body[5:5 + length])
    count = (payload[0] << 8) | payload[1]
    ids = payload[2:2 + count]
    if len(ids) != count:
        return None
    return ids


def build_read_switch_table():
    """Ask for the current 132-byte per-key switch table (driver:
    initKeySwitch, cmd 37 [1]=2). CONFIRMED-BY-CAPTURE: OUT `25 02`,
    answered with 3 chunks (58 + 58 + 16) shaped like the write pages:
    body = [37, 2, page_hi, page_lo, len, payload...]. Parse each with
    parse_switch_chunk() and reassemble with assemble_switch_table()."""
    d = _pkt(37)
    d[1] = 2
    return _wrap(d)


def parse_switch_chunk(body):
    """Decode one cmd-37 sub-2 read-reply chunk BODY. Returns
    {"page": n, "data": [...]} or None (writes echo with [1]=1, the
    switch LIST reply carries [1]=0)."""
    if len(body) < 6 or body[0] != 37 or body[1] != 2:
        return None
    page = (body[2] << 8) | body[3]
    length = body[4]
    if length == 0 or 5 + length > len(body):
        return None
    return {"page": page, "data": list(body[5:5 + length])}


def assemble_switch_table(chunks):
    """Merge parse_switch_chunk() results into the flat 132-byte table.
    Returns bytes(132) only when every page (0..2, 58-byte stride)
    arrived; None on a partial read so callers refuse to write a
    half-zeroed table."""
    table = bytearray(SWITCH_TABLE_BYTES)
    seen = set()
    for ch in chunks:
        if not ch:
            continue
        start = ch["page"] * 58
        data = ch["data"][:max(0, SWITCH_TABLE_BYTES - start)]
        if not data:
            continue
        table[start:start + len(data)] = bytes(data)
        seen.add(ch["page"])
    n_pages = (SWITCH_TABLE_BYTES + 57) // 58
    return bytes(table) if len(seen) >= n_pages else None


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
            top, bottom = int(pair[0]), int(pair[1])
            # One byte each on the wire; the pager masks with & 0xFF, so an
            # out-of-range value would silently wrap (2.56 mm -> 0.00 mm).
            if not (0 <= top <= 0xFF and 0 <= bottom <= 0xFF):
                raise ValueError(
                    f"dead band {top}/{bottom} for key {idx} outside 0..255 "
                    f"(0.01 mm units)")
            values[idx * 2] = top
            values[idx * 2 + 1] = bottom
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
    if len(prcs_list) > 20:
        # The vendor table is exactly 2 pages x 10 entries; anything past
        # that would be dropped silently while the UI reported success.
        raise ValueError("at most 20 SOCD/PRCS pairs (got %d)" % len(prcs_list))
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
    """Factory reset (driver: resetKeyboard, deobfuscated.js L1477-1486 —
    cmd 20, [4]=1, [5]=1). Wipes every stored setting. SOURCE-ONLY: never
    sent in the capture and refused by dangerous_command_reason()."""
    d = _pkt(20); d[4] = 1; d[5] = 1
    return _wrap(d)


def dangerous_command_reason(body):
    """Why a raw WIN 60 HE report BODY (63 bytes, report id stripped) must
    NOT be sent blind — the Win60 analogue of protocol_mini60.DANGEROUS_CMDS.
    Returns a short reason string, or None if the body is not on the list.

    Unlike the MINI's protocol (where whole command bytes are never-send),
    every destructive Win60 operation shares its command byte with ordinary
    settings, so this matches on the sub-selector too. Evidence, all from
    driver_src/dec_agreement/deobfuscated.js and the capture notes:

      * cmd 20 (0x14), [1]=0, [5]=1 — resetKeyboard (L1477-1486): factory
        reset of every stored setting. The same cmd with [5]=0 is the
        win-lock/perf write (L1455-1474, captured frames 4456-4481) and
        [1]=1/2/3 are sleep-timer/gamepad (L1487-1523): those stay allowed.
      * cmd 33 (0x21), [4]=24, [5]=6 — resetTrigger (build_reset_trigger):
        wipes every key's actuation/RT config. The capture author
        deliberately never sent it (WIN60_CAPTURE_NOTES.md "NOT EXERCISED").
      * cmd 33, [4]=24, [5]=8 [6]=0 / [5]=15 [6]=0 — calibration START
        (reviseKeys; build_calibration). Arming wipes the board's stored
        calibration and leaves it in calibration mode until stopped with
        the matching stop frame; Api.calibrate() is the only path that
        pairs the arm with a reader and the disconnect-disarm contract.
        The stop frames (8/1, 16/0) are harmless and stay allowed.

    No firmware/bootloader command exists in the vendor web driver: its
    "firmware" feature (wmIndex checkFirmwareVersion/downloadFirmware)
    only downloads a separate updater archive listed in
    config__firmware.json — nothing is sent over HID — so there is no
    boot/IAP command byte to list here.
    """
    b = list(body)
    if len(b) < 7:
        return None
    if b[0] == 20 and b[1] == 0 and b[5] == 1:
        return "cmd 20 [5]=1 is resetKeyboard (factory reset)"
    if b[0] == 33 and b[4] == 24:
        if b[5] == 6:
            return "cmd 33 sub 6 is resetTrigger (wipes every key's actuation)"
        if b[5] in (8, 15) and b[6] == 0:
            return ("cmd 33 sub %d/0 arms calibration (wipes stored calibration; "
                    "use the Calibration tab, which disarms on abort)" % b[5])
    return None


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
# macro protocol (protocol_mini60) — do not unify them. 10 slots x 256 bytes
# (deobfuscated.js L1200 reads slots 128..137, L1222 writes slots 0..9 of a
# 256-byte ArrayBuffer), written in 5 chunks (4 x 58 + 24, L1260-1281).
#
# Slot image — 8-byte header, from setMacroValue (L1232-1238):
#   [0] macro index (| 0x80 when the vendor re-sends a macro already used by
#       an earlier key — a "duplicate" flag Aether never sets: one slot per
#       macro, any number of keys may point at it via the keymap)
#   [1] PLAY MODE = MacroKey.type (getMacroType(): 0 = operate once,
#       1 = operate N times, 2 = toggle, 3 = hold-to-repeat). The captured
#       slots read 00/01 here, which an earlier decode mistook for the slot
#       index duplicated — slot 0 was "once" (type 0) and slot 1 "3 times"
#       (type 1), so the bytes were identical under both readings. Only
#       modes 0 and 1 were exercised on the wire; 2 and 3 are NOT VERIFIED.
#   [2..3] event-block length in BYTES, big-endian ([3] = steps * 4 at L1236;
#       [2] is never written by the vendor and stays 0 — 62 events max fit)
#   [4..5] repeat count, big-endian (L1237-1238; "Operate Once" = 1)
#   [6..7] 0
# then 4-byte events (L1248-1251): [hid_code, state<<4 | type, delay_hi,
# delay_lo] — state 1 = key DOWN (0x10), 0 = UP; type 0 = keyboard usage,
# 1 = mouse button (NOT supported here). The delay is big-endian ms and is
# the delay AFTER this event: the vendor stores step[i+1].delay into event i
# (L1244-1247) and shifts it back by one on read (L505-512), because its UI
# keeps each step's delay as the wait BEFORE that step. Aether's event tuples
# use that same UI convention — (delay_before_ms, hid_code, is_down), the
# drivers/base.py contract — and this module converts at the wire.
#
# A macro fires from a key via the keymap entry [0x10, hid_code, macro_slot,
# 0] — see macro_keymap_entry(). An unused slot reads back as all 0xFF
# (never written) or all 0x00 (the vendor writes zeros for empty slots).
MACRO_SLOTS = 10
MACRO_SLOT_BYTES = 256
MACRO_EVENT_DOWN = 0x10
MACRO_EVENT_UP = 0x00
MACRO_MAX_EVENTS = (MACRO_SLOT_BYTES - 8) // 4   # 62
MACRO_MAX_DELAY_MS = 0xFFFF
MACRO_MAX_REPEAT = 0xFFFF
#: Header byte 1 — the vendor's macroType radio (getMacroType()).
MACRO_PLAY_ONCE = 0        # CONFIRMED-BY-CAPTURE (slot 0, count 1)
MACRO_PLAY_REPEAT = 1      # CONFIRMED-BY-CAPTURE (slot 1, count 3)
MACRO_PLAY_TOGGLE = 2      # SOURCE-ONLY (macroType3) — NOT VERIFIED
MACRO_PLAY_HOLD = 3        # SOURCE-ONLY (macroType4) — NOT VERIFIED
MACRO_PLAY_MODES = (MACRO_PLAY_ONCE, MACRO_PLAY_REPEAT,
                    MACRO_PLAY_TOGGLE, MACRO_PLAY_HOLD)
#: Keymap entry type byte that routes a key to a macro slot.
KEYMAP_TYPE_MACRO = 0x10


def validate_macro_events(events):
    """Normalise + validate a macro event list. Accepts tuples
    (delay_before_ms, hid_code, is_down) or dicts {delay, hid, down} (the
    JS bridge shape) and returns a list of tuples. Raises ValueError on a
    bad count, HID usage outside 0..255, or a delay outside 0..65535."""
    out = []
    for ev in list(events or ()):
        if isinstance(ev, dict):
            delay, hid, down = ev.get("delay", 0), ev.get("hid"), ev.get("down")
        else:
            delay, hid, down = ev
        try:
            delay = int(delay)
            hid = int(hid)
        except (TypeError, ValueError):
            raise ValueError("macro event needs integer delay and hid: %r" % (ev,))
        if not 0 <= hid <= 0xFF:
            raise ValueError("macro HID usage must be 0..255, got %d" % hid)
        if not 0 <= delay <= MACRO_MAX_DELAY_MS:
            raise ValueError("macro delay must be 0..%d ms, got %d"
                             % (MACRO_MAX_DELAY_MS, delay))
        out.append((delay, hid, bool(down)))
    if len(out) > MACRO_MAX_EVENTS:
        raise ValueError("macro too long: max %d events" % MACRO_MAX_EVENTS)
    return out


def build_macro_table(slot, events, repeat_count=1, play_mode=MACRO_PLAY_ONCE):
    """Build the 256-byte slot image. `events` = [(delay_before_ms,
    hid_code, is_down), ...] (delay = wait BEFORE the event, the vendor-UI
    and drivers/base.py convention); the wire's delay-after is derived by
    shifting one step, exactly as setMacroValue does (L1244-1247). An
    empty/None `events` builds the all-zero slot the vendor writes for an
    unused slot (deletes it). repeat_count: "Operate Once" = 1, "Operate N
    times" = N. play_mode: header byte 1 (MACRO_PLAY_*)."""
    slot = int(slot)
    if not 0 <= slot < MACRO_SLOTS:
        raise ValueError("macro slot out of range 0..9")
    events = validate_macro_events(events)
    play_mode = int(play_mode)
    if play_mode not in MACRO_PLAY_MODES:
        raise ValueError("macro play mode must be 0..3, got %d" % play_mode)
    repeat_count = int(repeat_count)
    if not 0 <= repeat_count <= MACRO_MAX_REPEAT:
        raise ValueError("macro repeat count must be 0..%d" % MACRO_MAX_REPEAT)
    table = [0] * MACRO_SLOT_BYTES
    if not events:
        return table
    table[0] = slot
    table[1] = play_mode
    n = len(events) * 4
    table[2] = (n >> 8) & 0xFF
    table[3] = n & 0xFF
    table[4] = (repeat_count >> 8) & 0xFF
    table[5] = repeat_count & 0xFF
    off = 8
    for i, (_delay_before, hid_code, is_down) in enumerate(events):
        # wire delay = the NEXT step's wait-before; the last event gets 0
        delay_after = events[i + 1][0] if i + 1 < len(events) else 0
        table[off] = hid_code
        table[off + 1] = MACRO_EVENT_DOWN if is_down else MACRO_EVENT_UP
        table[off + 2] = (delay_after >> 8) & 0xFF
        table[off + 3] = delay_after & 0xFF
        off += 4
    return table


def build_macro_packets(slot, events, repeat_count=1, play_mode=MACRO_PLAY_ONCE):
    """Page a macro slot into its 5 cmd-25 write packets
    ([25, slot, page_hi, page_lo, len, payload...], 58-byte chunks).
    CONFIRMED-BY-CAPTURE byte-for-byte, including events split across the
    chunk boundary."""
    table = build_macro_table(slot, events, repeat_count, play_mode)
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
    (all 0xFF = never written, or a zero event length = the vendor's
    all-zero "unused" image), else {"slot", "play_mode", "repeat_count",
    "events": [(delay_before_ms, hid_code, is_down), ...]} — the delays are
    shifted back from the wire's delay-after exactly as the vendor's read
    handler does (deobfuscated.js L505-512): event 0 waits 0 ms, event i
    waits what the wire stored on event i-1. The last event's wire delay
    (always 0 from the vendor) is dropped. Inverse of build_macro_table().
    Mouse-button events (type nibble 1) are decoded by state only."""
    table = list(table)
    if len(table) < 8:
        return None
    if all(b == 0xFF for b in table):
        return None
    n = ((table[2] << 8) | table[3]) & ~3
    n = min(n, MACRO_SLOT_BYTES - 8)
    if n <= 0:
        return None
    wire = []
    for off in range(8, 8 + n, 4):
        wire.append((table[off], bool((table[off + 1] >> 4) & 1),
                     (table[off + 2] << 8) | table[off + 3]))
    events = []
    prev_after = 0
    for hid, down, after in wire:
        events.append((prev_after, hid, down))
        prev_after = after
    return {"slot": table[0] & 0x7F, "play_mode": table[1],
            "repeat_count": (table[4] << 8) | table[5], "events": events}


def macro_keymap_entry(macro_slot, hid_code):
    """The 4-byte keymap-table entry that binds a macro to a key:
    [type=0x10, original hid code, macro slot, 0]. CONFIRMED-BY-CAPTURE
    (keymap slot 96 `10 10 00 00` = macro 0 on M, slot 95 `10 11 01 00` =
    macro 1 on N; deobfuscated.js L1048-1052 builds exactly these bytes and
    L317-327 reads code3 back as the slot). NOTE: writing this entry means
    rewriting the ENTIRE 528-byte keymap layer, exactly like any other
    remap."""
    return [KEYMAP_TYPE_MACRO, int(hid_code) & 0xFF, int(macro_slot) & 0xFF, 0]


def parse_macro_bindings(table_528):
    """{key index: macro slot} for every type-0x10 entry in a 528-byte keymap
    layer image (the read-back of read_keymap_layer)."""
    out = {}
    t = list(table_528 or ())
    for idx in range(min(len(t) // 4, 132)):
        if t[idx * 4] == KEYMAP_TYPE_MACRO:
            out[idx] = t[idx * 4 + 2]
    return out


def compose_base_keymap(read_back, default_hids, layer_indices=None,
                        overrides=None):
    """Merge a base-layer READ-BACK with the board's known defaults into the
    528-byte image a base-layer write must carry.

    CONFIRMED-BY-CAPTURE (webhid-capture-win60.json frames 123-132): a
    never-written board answers the base-layer read with ALL ZEROS while its
    default keymap works, so a zero entry means "firmware default", not
    "unbound" — and the vendor never writes zeros for a real key (its
    setKeyValue fills every slot from curDevice.keys, L1023-1069). After a
    write the board echoes the written table (frames 7511-7520), so a
    NON-zero entry is board truth (a remap or a macro/advanced binding made
    by any driver) and is kept verbatim.

    `default_hids` {index: hid}, `layer_indices` = Fn-type keys (code1 = 1),
    `overrides` {index: hid} = Aether's own pending plain remaps (applied as
    [0, hid, 0, 0], the same entry build_base_keymap_table writes)."""
    table = bytearray(528)
    rb = bytes(read_back or b"")[:528]
    table[:len(rb)] = rb
    layer_indices = set(layer_indices or ())
    for idx, hid in (default_hids or {}).items():
        idx = int(idx)
        off = idx * 4
        if off + 4 > len(table):
            continue
        if not any(table[off:off + 4]):
            table[off] = 1 if idx in layer_indices else 0
            table[off + 1] = int(hid) & 0xFF
    for idx, hid in (overrides or {}).items():
        off = int(idx) * 4
        if off + 4 <= len(table):
            table[off:off + 4] = bytes([0, int(hid) & 0xFF, 0, 0])
    return table


def build_base_keymap_raw(table_528):
    """Page a ready-made 528-byte BASE-layer image (cmd 24, header [1]=0) —
    the raw counterpart of build_fn_keymap_table for callers that compose
    the table themselves (compose_base_keymap + a macro entry patch)."""
    table = bytearray(528)
    if table_528:
        n = min(len(table_528), 528)
        table[:n] = bytes(table_528[:n])
    return _paged_keymap_packets(table, layer_byte=0)


def parse_trigger_read(body):
    """Decode a cmd-33 LIVE TRAVEL-TEST stream frame body (report id
    stripped) — the frames the vendor handler matches with body[5] == 0x01
    (agreement.js: `r[0]==33 && r[5]==1 -> depth = r[9]<<8 | r[8]`).

    body[i] == r[i+1] for the raw 64-byte report r: row=body[6], col=body[7],
    depth lo/hi = body[8]/body[9], in 0.01 mm units. This is NOT the layout
    of the cmd-33 sub-5 per-key config read-back (readTriggerData) — for
    that reply use parse_trigger_config(); the two frames share a command
    byte and nothing else.
    """
    return {
        "row": body[6],
        "col": body[7],
        "travel": body[8] | (body[9] << 8),
    }


def build_read_trigger_config(index):
    """Ask for one key's stored trigger config (driver: readTriggerData,
    cmd 33 sub 5): OUT `21 00 00 00 18 05 <row> <col>` with row = index // 22,
    col = index % 22. CONFIRMED-BY-CAPTURE (frame 172: `18 05 01 00`)."""
    index = int(index)
    d = _pkt(33)
    d[4] = 24
    d[5] = 5
    d[6] = index // 22
    d[7] = index % 22
    return _wrap(d)


def parse_trigger_config(body):
    """Decode the cmd-33 sub-5 readTriggerData reply BODY (report id
    stripped). Returns None unless the body is that reply.

    CONFIRMED-BY-CAPTURE (webhid-capture-win60.json frame 173, answering the
    row-1/col-0 request):
        21 00 00 00 0c 05 00 aa aa 01 01 00 00 00 00 01 00
                    len sub mode tr tr i1 i2 -- -- -- -- row col
    decoded with the vendor's own field expressions (agreement.js
    readTriggerData): mode = body[6], travel = body[11]<<8 | body[7],
    interval1 = body[13]<<8 | body[9], interval2 = body[14]<<8 | body[10];
    row/col echo at body[15]/body[16], so index = row*22 + col. All travel
    values are in the board's trigger unit (0.01 mm on the WIN 60 HE), so
    `aa` = 170 = 1.70 mm. Note the payload length byte body[4] is 0x0c —
    a reader that tests body[4] (raw r[5]) == 5 never sees this reply.
    """
    if len(body) < 17 or body[0] != 33 or body[5] != 5:
        return None
    row, col = body[15], body[16]
    return {
        "mode": body[6],
        "travel": (body[11] << 8) | body[7],
        "interval1": (body[13] << 8) | body[9],
        "interval2": (body[14] << 8) | body[10],
        "row": row,
        "col": col,
        "index": row * 22 + col,
    }
