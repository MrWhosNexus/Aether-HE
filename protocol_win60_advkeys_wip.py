"""WIN60 HE advanced keys (DKS / Mod-Tap / Toggle): proposed packet builders.

SOURCE-ONLY / WIP / NOT WIRED.

Everything in this module is decoded from the vendor web driver
(hed.aulacn.com), de-obfuscated copies in
docs/context/hed-aulacn-raw/driver_deobf/ (agreement.deobf.js,
wmIndex.deobf.js, variable.deobf.js) and cross-checked against
driver_src/dec_agreement/deobfuscated.js. No payload byte here has been seen
on the wire with a real DKS / MT / TGL entry. The only CONFIRMED-BY-CAPTURE
parts are the framing of the read request and of an EMPTY slot write
(docs/context/hed-aulacn-raw/webhid-capture-win60.json frames 74-119 and
2205-2282, where every slot was empty).

Full decode with line citations: docs/context/aula-win60-advanced-keys-decode.md.
Hardware capture plan: docs/context/aula-win60-advanced-keys-capture-checklist.md.

Rules for this module:
  * Pure functions only. No HID, no device, no app imports.
  * Nothing on the drive path (app_web.py, drivers/, protocol.py,
    device_state.py, effects.py) may import it. tests/test_win60_advkeys_wip.py
    enforces that.
  * Wiring it in must sit behind a "wip" capability in
    data/board_registry.json, and only after the capture checklist has
    confirmed the golden frames.

Frames are returned as the 63-byte report BODY (report id excluded), the same
convention as protocol.py (BODY = 63, REPORT_ID = 1). to_report() prefixes
the report id.
"""

REPORT_ID = 1
BODY = 63

# ---- command / framing (agreement.deobf.js L529-550, L204-231) ----
CMD_ADVANCED_KEYS = 0x22        # cmd 34. Write [1]=slot; read request [1]=0x80
READ_FLAG = 0x80                # initAdvancedKeys L532: [0]=0x22, [1]=0x80
WRITE_LEN = 0x32                # setAdvancedKeys L540: [4]=0x32 (50), every slot
READ_REPLY_LEN = 0x28           # capture: replies carry [4]=0x28 (40)
SLOT_COUNT = 40                 # L537 loop < 0x28; wmIndex L461 cap of 40 entries
LAST_SLOT = SLOT_COUNT - 1      # L205/L231: reply index 0x27 ends the read

# ---- entry type byte, body[5] (L206-229 read, L543 write) ----
TYPE_EMPTY = 0
TYPE_DKS = 1
TYPE_MT = 2
TYPE_TGL = 3
TYPE_RS = 4                     # gated by info bit isRS (false on WIN60); not built here
TYPE_RKRT = 5                   # gated by info bit isRKRT (false on WIN60); not built here
TYPE_NAMES = {TYPE_DKS: "DKS", TYPE_MT: "MT", TYPE_TGL: "TGL",
              TYPE_RS: "RS", TYPE_RKRT: "RKRT"}

# ---- keymap binding (agreement L123, L342; wmIndex L456) ----
KEYMAP_TYPE_ADVANCED = 0x17     # keymap entry [0x17, slot, slot, 0]

# ---- DKS (L207-211 read, L543-546 write) ----
DKS_ACTIONS = 4                 # four action keys (rows dksEdit1..4)
DKS_POINTS = 4                  # four trigger points (columns col1..col4)
DKS_ROUTE_OFFSET = 6            # route1..route4 at body[6..9]
DKS_ACTION_OFFSET = 10          # action k at body[10 + 8k .. 17 + 8k]
DKS_ACTION_STRIDE = 8           # [code1, hid, code3, code4, step p1..p4]
DKS_UNIT_MM = 0.1               # wmIndex L1123/L1160/L1164: label = value/10 mm
DKS_UI_MIN_RAW = 1              # index.html L162: dksTrigger min="1"
DKS_UI_MAX_RAW = 36             # index.html L162: max="36" (runtime max = route2)
DKS_DEFAULT_PRESS_RAW = 0x0F    # wmIndex L461/L1123: route1 = route4 = 15 (1.5 mm)
# Step codes per (action, point): wmIndex setDksValue L393-398 (writer) and
# refreshDksButton L1686-1700 (reader). Meaning of each code is INFERRED from
# the editor's drawing: narrow circle = 1, a bar starting here = 2, a bar that
# starts exactly where the previous bar ends = 3, or a point a bar covers = 2.
DKS_STEP_NONE = 0
DKS_STEP_TAP = 1
DKS_STEP_HOLD = 2
DKS_STEP_HOLD_AGAIN = 3

# ---- Mod-Tap (L212-214 read, L547 write) ----
MT_HOLD_OFFSET = 6              # keys[1] = "long press" key (index.html L331)
MT_TAP_OFFSET = 10              # keys[0] = "single click" key (index.html L327)
MT_DURATION_OFFSET = 14
MT_DURATION_UNIT_MS = 10        # wmIndex L1134: label = 10 * value ms
MT_UI_MIN_RAW = 15              # index.html L338: mtRange min="15" (150 ms)
MT_UI_MAX_RAW = 100             # index.html L338: max="100" (1000 ms)

# ---- Toggle (L215-217 read, L547 write) ----
TGL_KEY_OFFSET = 6


def _body():
    return [0] * BODY


def to_report(body):
    """Prefix the report id (protocol.py _wrap convention)."""
    return [REPORT_ID] + list(body)


def _check_slot(slot):
    s = int(slot)
    if not 0 <= s < SLOT_COUNT:
        raise ValueError(f"advanced-key slot must be 0..{LAST_SLOT}")
    return s


def key_entry(hid, code1=0, code3=0, code4=0):
    """A 4-byte vendor key record [code1, hidCode, code3, code4], the same
    shape as a keymap entry. Plain keys AND modifiers are code1 = 0 with the
    HID usage in byte 1 (config__keys.json L5, L64-70: L-Ctrl = 0,E0,0,0).
    An unassigned action is all zero (variable.deobf.js L70 Key defaults)."""
    rec = [int(code1), int(hid), int(code3), int(code4)]
    for b in rec:
        if not 0 <= b <= 0xFF:
            raise ValueError("key record bytes must be 0..255")
    return rec


EMPTY_KEY = (0, 0, 0, 0)


def _as_entry(key):
    if key is None:
        return list(EMPTY_KEY)
    if isinstance(key, int):
        return key_entry(key)
    rec = [int(b) for b in key]
    if len(rec) != 4:
        raise ValueError("a key record is exactly 4 bytes")
    return key_entry(rec[1], rec[0], rec[2], rec[3])


def _write_header(slot):
    b = _body()
    b[0] = CMD_ADVANCED_KEYS
    b[1] = _check_slot(slot)
    b[4] = WRITE_LEN
    return b


# ---------------------------------------------------------------- read

def build_read_advanced_keys():
    """Read request: [0x22, 0x80, 0...]. The board answers with 40 frames,
    one per slot (agreement L529-535). CONFIRMED-BY-CAPTURE (frame 74)."""
    b = _body()
    b[0] = CMD_ADVANCED_KEYS
    b[1] = READ_FLAG
    return b


def parse_advanced_key_reply(body):
    """Decode one read-reply body: [0x22, 0x80, slotHi, slotLo, 0x28, type, ...]
    (agreement L204-231). Returns None for a non-matching frame, otherwise a
    dict with 'slot', 'type' and the type's fields. SOURCE-ONLY for every
    non-empty type."""
    r = list(body or ())
    if len(r) < 42 or r[0] != CMD_ADVANCED_KEYS or r[1] != READ_FLAG:
        return None
    slot = (r[2] << 8) | r[3]
    t = r[5]
    out = {"slot": slot, "type": t, "last": slot == LAST_SLOT}
    if t == TYPE_DKS:
        out["routes"] = r[DKS_ROUTE_OFFSET:DKS_ROUTE_OFFSET + 4]
        actions, steps = [], []
        for k in range(DKS_ACTIONS):
            o = DKS_ACTION_OFFSET + DKS_ACTION_STRIDE * k
            actions.append(r[o:o + 4])
            steps.append(r[o + 4:o + 8])
        out["actions"] = actions
        out["steps"] = steps
    elif t == TYPE_MT:
        out["hold"] = r[MT_HOLD_OFFSET:MT_HOLD_OFFSET + 4]
        out["tap"] = r[MT_TAP_OFFSET:MT_TAP_OFFSET + 4]
        out["duration"] = r[MT_DURATION_OFFSET]
    elif t == TYPE_TGL:
        out["key"] = r[TGL_KEY_OFFSET:TGL_KEY_OFFSET + 4]
    elif t in (TYPE_RS, TYPE_RKRT):
        out["raw"] = r[6:18]
    return out


# ---------------------------------------------------------------- write

def build_empty_slot(slot):
    """Clear one slot: [0x22, slot, 0, 0, 0x32, 0...]. This is how the
    vendor 'deletes' an entry: it drops it from advKeys and rewrites all 40
    slots, so the dropped slot goes out all-zero (agreement L536-550,
    wmIndex L431-443). CONFIRMED-BY-CAPTURE for the framing (frames
    2205-2282, all slots empty)."""
    return _write_header(slot)


def dks_mm_to_raw(mm):
    """DKS travel points are 0.1 mm (NOT the 0.01 mm actuation unit)."""
    raw = int(round(float(mm) / DKS_UNIT_MM))
    if not 1 <= raw <= 0xFF:
        raise ValueError("DKS travel point out of range")
    return raw


def build_dks_slot(slot, routes, actions, steps):
    """DKS entry (type 1). SOURCE-ONLY.

    routes:  four raw bytes in 0.1 mm, wire order route1..route4 =
             press-down point, bottom-out point, release-from-bottom point,
             release-up point (column arrows: index.html L344-356). The
             vendor UI keeps route1 == route4 (wmIndex L1164) and
             route2 == route3 = max travel - 0.4 mm (wmIndex L461).
    actions: up to four key records (int HID usage, a 4-byte record, or None).
    steps:   up to four rows of four step codes (0..3), one row per action,
             one column per trigger point.
    Layout: body[6..9] routes; action k at body[10+8k..17+8k] =
    [code1, hid, code3, code4, step_p1, step_p2, step_p3, step_p4]."""
    b = _write_header(slot)
    b[5] = TYPE_DKS
    rts = [int(v) for v in routes]
    if len(rts) != DKS_POINTS:
        raise ValueError("DKS needs exactly four route bytes")
    for i, v in enumerate(rts):
        if not 0 <= v <= 0xFF:
            raise ValueError("DKS route bytes must be 0..255")
        b[DKS_ROUTE_OFFSET + i] = v
    acts = list(actions or ())
    rows = [list(r) for r in (steps or ())]
    if len(acts) > DKS_ACTIONS or len(rows) > DKS_ACTIONS:
        raise ValueError("DKS has at most four actions")
    for k in range(DKS_ACTIONS):
        o = DKS_ACTION_OFFSET + DKS_ACTION_STRIDE * k
        b[o:o + 4] = _as_entry(acts[k] if k < len(acts) else None)
        row = rows[k] if k < len(rows) else [0, 0, 0, 0]
        if len(row) != DKS_POINTS:
            raise ValueError("each DKS step row has four trigger points")
        for p, code in enumerate(row):
            code = int(code)
            if code not in (DKS_STEP_NONE, DKS_STEP_TAP, DKS_STEP_HOLD,
                            DKS_STEP_HOLD_AGAIN):
                raise ValueError("DKS step code must be 0..3")
            b[o + 4 + p] = code
    return b


def mt_duration_from_ms(ms):
    """Mod-Tap hold threshold: raw = ms / 10 (wmIndex L1134). The vendor
    slider spans 15..100 (150..1000 ms, index.html L338)."""
    raw = int(round(float(ms) / MT_DURATION_UNIT_MS))
    if not 1 <= raw <= 0xFF:
        raise ValueError("MT duration out of range")
    return raw


def build_mt_slot(slot, tap, hold, duration_raw):
    """Mod-Tap entry (type 2). SOURCE-ONLY.
    NOTE the order: HOLD record first (body[6..9], vendor keys[1]), TAP
    record second (body[10..13], keys[0]); duration byte at body[14]
    (agreement L547; mtEdit1 'single click' -> keys[0], mtEdit2 'long press'
    -> keys[1], wmIndex L342 / L569, index.html L327-332)."""
    d = int(duration_raw)
    if not 0 <= d <= 0xFF:
        raise ValueError("MT duration is one byte")
    b = _write_header(slot)
    b[5] = TYPE_MT
    b[MT_HOLD_OFFSET:MT_HOLD_OFFSET + 4] = _as_entry(hold)
    b[MT_TAP_OFFSET:MT_TAP_OFFSET + 4] = _as_entry(tap)
    b[MT_DURATION_OFFSET] = d
    return b


def build_tgl_slot(slot, key):
    """Toggle entry (type 3): one key record at body[6..9]. SOURCE-ONLY
    (agreement L547; tglEdit -> keys[0], wmIndex L342 / L569)."""
    b = _write_header(slot)
    b[5] = TYPE_TGL
    b[TGL_KEY_OFFSET:TGL_KEY_OFFSET + 4] = _as_entry(key)
    return b


def build_advanced_key_table(frames_by_slot=None):
    """The vendor write pass: ALL 40 slots in order 0..39, every slot not in
    `frames_by_slot` written empty (setAdvancedKeys L536-550 always loops the
    full table). `frames_by_slot` maps slot -> a body from build_*_slot for
    that same slot. With no entries this reproduces the captured all-empty
    pass byte-for-byte."""
    frames_by_slot = dict(frames_by_slot or {})
    out = []
    for s in range(SLOT_COUNT):
        f = frames_by_slot.pop(s, None)
        if f is None:
            out.append(build_empty_slot(s))
            continue
        f = list(f)
        if len(f) != BODY or f[0] != CMD_ADVANCED_KEYS or f[1] != s:
            raise ValueError(f"frame for slot {s} is not a slot-{s} write")
        out.append(f)
    if frames_by_slot:
        raise ValueError("slot out of range: %r" % sorted(frames_by_slot))
    return out


def keymap_entry_advanced(slot):
    """Keymap (cmd 0x18) entry that binds a physical key to advanced slot n:
    [0x17, n, n, 0]. SOURCE-ONLY: wmIndex L456 sets code1 = 0x17,
    hidCode = index, code3 = index; agreement setKeyValue L342 writes
    [code1, hidCode, code3, code4]; the keymap read (L123) looks the slot up
    by byte 1. Clearing the binding = writing the key's default entry back
    (agreement L342 else-branch: [0 or 1, defaultHid, 0, 0])."""
    s = _check_slot(slot)
    return [KEYMAP_TYPE_ADVANCED, s, s, 0]
