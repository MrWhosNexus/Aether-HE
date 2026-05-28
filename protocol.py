"""Aula WIN60 HE vendor HID protocol — extracted verbatim from the official web
driver (hed.aulacn.com, agreement.min.js, de-obfuscated).

All commands are HID Output reports on Report ID 1 with a 63-byte body; the
first body byte is the command. hidapi's write() wants the Report ID prepended,
so every build_* returns a 64-byte list: [1] + 63 data bytes.

Command map (body[0]):
  1  heartbeat / device-info (body[0]=13 is the info query)
  7  lighting (8 = side lighting)
  9  per-key custom RGB (mode 10)
  20 performance / win-lock / gamepad-mode / sleep / reset
  23 music rhythm
  33 trigger family: actuation, travel-test, poll-rate, key-remap
  36 PRCS / SOCD
  37 switch profile
  38 dead band
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


def build_keymap_table(default_hids, overrides=None, layer_indices=None, fn_layer=False):
    """Full key-remap table (cmd 24), matching the official driver's setKeyValue.

    The board stores a flat table of 4 bytes per key index — [code1, hidCode,
    code3, code4] — so a remap must send EVERY key, not just the changed one, or
    the rest get zeroed. We start from `default_hids` ({index: default_hid}) and
    apply `overrides` ({index: target_hid}) on top, then page it out in 56-byte
    chunks behind a [24, 0|130, page_hi, page_lo, len, ...] header.

    `code1` is the key TYPE: the driver writes 1 for the Fn/layer-shift key
    (`code === "KeyFn"`) and 0 for ordinary keys. `layer_indices` is the set of
    indices whose default type is the layer key — getting this wrong (writing 0
    for the Fn key) makes the firmware treat Fn as a normal key, which breaks the
    function layer (the board gets "stuck" in Fn). A remapped key is always a
    plain key (code1 = 0).

    `fn_layer=True` writes the Fn layer (header byte1 = 130) instead of the base
    layer (byte1 = 0)."""
    overrides = overrides or {}
    layer_indices = set(layer_indices or ())
    max_idx = max(default_hids) if default_hids else 0
    size = (max_idx + 1) * 4
    if size < 528:
        size = 528
    table = bytearray(size)
    for idx, hid in default_hids.items():
        if idx in overrides:
            h = overrides[idx]
            code1 = 0                       # a remapped key is a plain key
        else:
            h = hid
            code1 = 1 if idx in layer_indices else 0
        table[idx * 4] = code1 & 0xFF
        table[idx * 4 + 1] = int(h) & 0xFF  # target HID code
        # code3/code4 left 0
    for idx, hid in overrides.items():       # remapped keys not in defaults
        if idx not in default_hids:
            table[idx * 4 + 1] = int(hid) & 0xFF

    page_size = 56
    packets = []
    total = len(table)
    n_pages = (total + page_size - 1) // page_size
    for page in range(n_pages):
        start = page * page_size
        part = table[start:start + page_size]
        d = _pkt(24)
        d[1] = 130 if fn_layer else 0
        d[2] = (page >> 8) & 0xFF
        d[3] = page & 0xFF
        d[4] = len(part)
        d[5:5 + len(part)] = part
        packets.append(_wrap(d))
    return packets


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


def build_deadband_table(deadband_by_index, default_top=4, default_bottom=5, key_count=132):
    """Set top/bottom dead-band per device index.

    Firmware values are hundredths of a millimeter, matching the official UI's
    integer deadbandTop/deadbandBottom fields.
    """
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


def parse_trigger_read(body):
    """Decode a cmd-33 sub-5 trigger-read response body (without report id)."""
    return {
        "mode": body[6],
        "travel": (body[11] << 8) | body[7],
        "interval1": (body[13] << 8) | body[9],
        "interval2": (body[14] << 8) | body[10],
    }
