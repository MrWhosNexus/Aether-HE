# WIN60 HE advanced keys (DKS / Mod-Tap / Toggle): source decode

Status: **SOURCE-ONLY**, written 2026-11-04 (research track of
`docs/superpowers/specs/2026-11-04-win60-roadmap-design.md`). Nothing here has
been sent to a keyboard. The only parts seen on the wire are the read request
and the **empty**-slot write framing (`hed-aulacn-raw/webhid-capture-win60.json`
and `WIN60_CAPTURE_NOTES.md` section 6). Every payload byte for a real DKS, MT or
TGL entry is decoded from the vendor source only. Lines marked **INFERRED** are
my reading of UI code, not something the source states outright.

Sources (all under `docs/context/hed-aulacn-raw/`):

| short name | file |
|---|---|
| `AG` | `driver_deobf/agreement.deobf.js` (packet layer) |
| `WM` | `driver_deobf/wmIndex.deobf.js` (UI) |
| `VAR` | `driver_deobf/variable.deobf.js` (classes, globals) |
| `HTML` | `driver_src/index.html` |
| `DEV` | `driver_src/config__device.json` |
| `KEYS` | `driver_src/config__keys.json` |
| `DEOBF2` | `driver_src/dec_agreement/deobfuscated.js` at the repo root (a second, readable de-obfuscation used to cross-check `AG`) |

Obfuscated property names left in `WM` were resolved with the string table in
`hed-strings.json` (`wmIndex` table): `0x108`=`code1`, `0x2e3`=`hidCode`,
`0x1bf`=`code3`, `0x33a`=`index`, `0x20a`=`type`, `0x190`=`keys`, `0x485`=`applyTip2`.

Proposed builders: `protocol_win60_advkeys_wip.py` (pure, not wired). Tests:
`tests/test_win60_advkeys_wip.py` (16 tests, SOURCE-ONLY golden frames).

---

## 1. Summary

- **One command, `0x22` (34), carries all five advanced types** (DKS, MT, TGL, RS,
  RKRT) as a **40-slot table, one 63-byte frame per slot**. It is not part of the
  keymap.
- A physical key uses a slot through a **keymap entry `[0x17, slot, slot, 0]`**
  written with the ordinary cmd `0x18` keymap write (base layer `[1]=0x00`, Fn layer
  `[1]=0x02`).
- **DKS, MT and TGL are not gated by `isRS` or `isRKRT`.** Those two info bits only
  remove the RS and RKRT radio buttons from the editor. The Advanced tab itself is
  gated only by the device-config flag `isMech` and by PID `0xC345`. Neither applies to
  the WIN60 (PID `0xC365`). No info-report bit gates DKS/MT/TGL.
- The vendor **always rewrites all 40 slots** (and both keymap layers and the macro
  table) on Apply. A delete is that same full pass with the deleted slot written
  all-zero and the key's `0x17` keymap entry restored to its default.

## 2. Command and framing

| direction | bytes | source |
|---|---|---|
| read request | `22 80 00 00 00 …` (63-byte body) | `AG` L529-535 (`initAdvancedKeys`: `[0]=0x22,[1]=0x80`); `DEOBF2` L1625-1627. **Wire-confirmed** (capture frame 74) |
| read reply ×40 | `22 80 <slotHi> <slotLo> 28 <type> <payload…>` | `AG` L204 (`[0]==0x22 && [1]==0x80`), slot = `[2]<<8 \| [3]`. `[4]=0x28` is wire-confirmed (frames 75-119). Reply for slot `0x27` (39) ends the read (`AG` L205, L231) |
| write ×40 | `22 <slot> 00 00 32 <type> <payload…>` | `AG` L536-550 (`setAdvancedKeys`: loop `slot<0x28`, `[0]=0x22,[1]=slot,[4]=0x32`); `DEOBF2` L1636-1643. **Wire-confirmed for empty slots** (frames 2205-2282) |
| write ack | `IN 22 00 00 00 00 …` seen between some writes | capture frames 2207, 2243 (observed, not used by the driver's handler) |

Notes:
- "Paging" is per slot, not a byte stream. Read replies declare 40 payload bytes
  (`[4]=0x28`); writes declare 50 (`[4]=0x32`) whatever the type (`AG` L540). The
  write puts the slot in `[1]`; the reply puts it in `[2..3]`. That asymmetry is
  wire-confirmed (`WIN60_CAPTURE_NOTES.md` section 6).
- Reply payload offsets are the **same** as write offsets from byte 5 onward (`AG`
  L207-229 reads exactly the bytes L543-549 writes). The longest entry (DKS) ends at
  byte 41, inside the 40-byte reply payload (bytes 5..44).
- The table holds at most 40 entries: `WM` L461 refuses "add" when `advKeys.length >= 0x28`
  (`alertAdvWarning`, "Advanced keys can only add up to 40!").
- The table has **no profile byte**. It is one table per board, as far as the source
  shows.
- The read is sent once at connect, after the macro read and before the keymap read
  (`WM` L1502: `initMacroValue()`, then `initAdvancedKeys()` unless PID is `0xC345`,
  then `initKeyValue('default')` and `initKeyValue('fn')`). The capture's mount sequence
  matches (`WIN60_CAPTURE_NOTES.md` section 12).

## 3. Entry layout (body offsets, report id excluded)

Byte 5 is the type: `0` empty, `1` DKS, `2` MT, `3` TGL, `4` RS, `5` RKRT (`AG` L206,
L543; `DEOBF2` L1647-1662).

A **key record** is the vendor's 4-byte `[code1, hidCode, code3, code4]`, the same shape
as a keymap entry. Plain keys and modifiers are `code1=0` with the HID usage in byte 1:
`A` = `00 04 00 00`, `L-Ctrl` = `00 E0 00 00` (`KEYS` L5, L64-70). An unassigned key is
all-zero (`VAR` L70: `new Key()` defaults; `AdvancedKey.keys = Array(4).fill(new Key())`).
The reader resolves a non-zero record back to a named key with `findFixedKeyByHid(code1, hid)`
(`AG` L211).

### 3.1 DKS (type 1): `AG` L207-211 (read), L543-546 (write); `DEOBF2` L1663-1678

| bytes | field |
|---|---|
| 6, 7, 8, 9 | `route1, route2, route3, route4`: the four trigger points, **0.1 mm units** |
| 10+8k .. 13+8k | action key k (k = 0..3), 4-byte key record |
| 14+8k .. 17+8k | `steps[4k .. 4k+3]`: one step code per trigger point for action k |

The four points in wire order, from the column arrows (`HTML` L344-356: down1, down2,
up1, up2):
1. `route1`: pressing down, past this depth.
2. `route2`: pressing down, bottom-out depth.
3. `route3`: released from bottom-out, coming up past this depth.
4. `route4`: coming up, past this depth.

Units and defaults:
- Units are 0.1 mm. Every label is `(value/10).toFixed(1) + 'mm'` (`WM` L1123, L1160,
  L1164). The trigger slider is `min=1 max=36` (`HTML` L162), and its runtime max is set to
  `route2` (`WM` L1160).
- **The unit differs from the 0.01 mm actuation unit** (cmd 33). It is the same unit as the
  MINI 60 HE PRO DKS table (section 6).
- Defaults when "add" is clicked (`WM` L461): `route1 = route4 = 15` (1.5 mm), and
  `route2 = route3 = maxTriggerTravel*triggerUnit*10 - 4`. On the WIN60 the board reports
  max 340 and unit 1/100 (`WIN60_CAPTURE_NOTES.md` section 13, row 1; `AG` L163-165), which
  gives 3.4 mm, so `34 - 4 = 30` (3.0 mm). **INFERRED** arithmetic from the captured values.
- If the DKS radio is chosen with no current entry, `WM` L1123 uses `route2 = route3 = 0x24`
  (3.6 mm) instead. The "add" path always creates the entry first, so 30 is the expected value.
- The UI can only edit `route1`, and it writes the same value to `route4`
  (`WM` L1164: `route1 = route4 = slider`). `route2` and `route3` stay at their defaults.
  The firmware may accept independent values. That is **not knowable from source**.

Step codes are written by `setDksValue` (`WM` L393-398) and drawn by `refreshDksButton`
(`WM` L1686-1700). There are four action rows and four point columns. Each cell is a
checkbox label that is either a 20 px circle or a bar dragged rightwards toward later points
(`WM` L1140-1155).

| code | when the writer emits it | meaning (**INFERRED**) |
|---|---|---|
| 0 | cell unchecked and not covered by a bar | no event for this key at this point |
| 1 | checked, circle (20 px) | tap: press and release at this point |
| 2 | checked bar that starts here, or an unchecked cell that an earlier bar covers | key held from here (or still held) |
| 3 | checked bar starting at a point where the previous cell's bar was a `2` (back-to-back bars) | release and press again, then keep holding |

A bar snaps so that it ends at the **left edge** of a later point (`setDksBtnWidth`,
`WM` L384-392). That end point is then written as `0` unless its own circle is checked
(`WM` L397, the `offsetLeft+offsetWidth <` comparisons). So a bar from point *i* to point
*j* writes `2` at *i* .. *j*-1 and `0` at *j*. For example, a row-1 bar from column 1 to
column 2 plus a circle at column 4 gives `02 00 00 01`. The decode reads this as "hold from
point 1, release at point 2, tap at point 4" (**INFERRED**).

The last column (`route4`) is only ever `0` or `1` (`WM` L397, last clause). The exact
firmware semantics of 2 and 3 need the capture (checklist step D2).

### 3.2 Mod-Tap (type 2): `AG` L212-214 (read), L547 (write); `DEOBF2` L1679-1689

| bytes | field |
|---|---|
| 6..9 | **hold** key record (vendor `keys[1]`) |
| 10..13 | **tap** key record (vendor `keys[0]`) |
| 14 | `duration` (hold threshold), **10 ms units** |

- Which record is which: `mtEdit1` is labelled "单击触发按键" (single-click key) and fills
  `keys[0]`. `mtEdit2` is labelled "长按触发按键" (long-press key) and fills `keys[1]`
  (`HTML` L327-332; `WM` L342, L569).
- The writer puts `keys[1]` first (`AG` L547). **So the hold record comes before the tap
  record on the wire.** The reader mirrors this: bytes 6..9 go to `keys[1]` and bytes
  10..13 go to `keys[0]` (`AG` L213-214).
- Duration: the slider is `min=15 max=100` (`HTML` L338), labelled `10*value ms`
  (`WM` L1134). That gives 150..1000 ms, default 15 (150 ms) (`WM` L461, L1125).
  `curMtKey.duration = slider.value` (`WM` L1137).

### 3.3 Toggle (type 3): `AG` L215-217 (read), L547 (write); `DEOBF2` L1690-1695

| bytes | field |
|---|---|
| 6..9 | the toggled key record (`keys[0]`, from `tglEdit`; `WM` L342, L569) |

UI text: "持续触发按键，点击开启或关闭", which means "keeps the key held; click to turn on
or off" (`HTML` L305).

### 3.4 RS (4) and RKRT (5), for completeness only

RS writes two key records plus each key's (row, col) position, `index/22, index%22`
(`AG` L547-548). RKRT writes `keys[0]` at bytes 6..9 and `keys[1]` at bytes 12..15
(`AG` L549). Both are hidden on this board (section 5), so they are out of scope and the
WIP module does not build them.

## 4. Binding a slot to a key, and clearing it

- **Bind.** Pick a physical key (`curKey`) and click a list item such as "1#DKS". The UI then
  builds `Key{code1:0x17, hidCode:slot, code3:slot}` (`WM` L455-456) and stores it in
  `recKeys` (base layer) or `fnKeys` (Fn layer, when `keymapFn` is checked; `HTML` L667-670).
  It then asks `applyTip2` and, on OK, clicks Apply.
- **Write.** `setKeyValue` writes `[code1, hidCode, code3, code4]` = `17 <slot> <slot> 00` into
  the 528-byte keymap image at `index*4` (`AG` L342 else-branch; the `0x10`/`0x12` special cases
  don't apply). The image is paged `[0]=0x18,[1]=0x00`, 56 bytes per chunk (`AG` L344-348).
  Fn uses `[1]=0x02` (`AG` L351+).
- **Read back.** The keymap reader recognises `code1 == 0x17` and finds the entry by **byte 1**
  (`advKeys.find(index === byte1)`, `AG` L123-125; `DEOBF2` L339-345).
- **The Apply button sends everything.** `btnApplyKey` runs
  `setKeyValue(); setFnKeyValue(); setMacroValue(); setAdvancedKeys()` in that order
  (`WM` L955-959). Saving in the advanced editor (`btnAdvApply`, `WM` L1168-1189) only updates
  `advKeys` and localStorage, so **it sends nothing over HID**. The one exception is RS, which
  clicks Apply itself. Edits reach the board only on the next Apply.
- **Delete** (trash icon, `WM` L431-443):
  1. Remove the entry from `advKeys`.
  2. Remove every `recKeys`/`fnKeys` entry with `code1 == 0x17 && code3 == slot` (L436-439).
  3. Click Apply.
  4. On the wire, the deleted slot goes out as `22 <slot> 00 00 32 00…` (empty) and the key's
     keymap entry goes back to its default `[0 (or 1 for Fn), defaultHid, 0, 0]` (`AG` L337,
     L342 else-branch).
- **Slot numbering.** A new entry takes the lowest unused slot (`getAdvIndex`, `WM` L402-412).
  The list label is `slot+1 + '#' + type` (`WM` L418). Slots keep their numbers after a delete.

Aether impact: `protocol.compose_base_keymap` already keeps any **non-zero** read-back entry
verbatim. So an Aether keymap write today **preserves** advanced-key bindings made by the vendor
driver. `parse_macro_bindings` ignores type `0x17`, which is correct.

## 5. Gating: what decides whether the UI offers DKS / MT / TGL

The info report (cmd `0x01`, `AG` L30-31) sets:
- From `p[12]`: `isAnyKeyCalibration`, `isCustomLight`, `isMoreSwitch`, `isPollRate`,
  `isDeadBand`, `isMusicRhythm`, `isALlAnd6keySwitch`.
- From `p[13]`: `isHighPrecision` bit0, `isGamePad` bit2, `isRS` bit3, `isRKRT` bit4.

The WIN60 reports `p[12]=0x7f`, `p[13]=0x00` (`WIN60_CAPTURE_NOTES.md` info-report table).

| gate | effect | source |
|---|---|---|
| `isRS` false | removes only the **RS** radio (`label[for="advTypeRadio4"]`) | `WM` L428 (edit) and L461 (add); selectors resolved via `hed-strings.json` `0x38a` |
| `isRKRT` false | removes only the **RKRT** radio (`advTypeRadio5`) | `WM` L428, L461; `0x337` |
| `curDevice.isMech` true | removes the whole **Advanced** tab (`[for=keyManu4]`) | `WM` L1501-1502 |
| PID `0xC345` | hides the Advanced tab and skips `initAdvancedKeys` | `WM` L1502 (`0xc345!==pid && initAdvancedKeys()`), L1515 |

- `isMech` is copied from the device config (`WM` L493). None of the `"pid": "0xC365"` entries in `DEV`
  (the first is L3-13) has an `isMech` field, so it is undefined and falsy.
- **Conclusion: DKS, MT and TGL do not depend on `isRS` or `isRKRT`.** No info-report bit
  gates them. On the WIN60 the vendor UI offers DKS/MT/TGL, reads the table at connect, and
  rewrites all 40 slots on every Apply.
- The earlier capture never opened the editor because the "+" button (`addButton`,
  `WM` L459-461) at the end of the Advanced list was not found
  (`WIN60_CAPTURE_NOTES.md` section 6). The empty-table writes it recorded came from that
  Apply pass.
- Whether the WIN60 **firmware** acts on DKS/MT/TGL is not provable from source. The board does
  answer the 40-slot read, and the driver offers the feature without any capability check.

## 6. Comparison with the MINI 60 HE PRO path (`protocol_mini60.py`)

| aspect | WIN60 HE (this decode, SOURCE-ONLY) | MINI 60 HE PRO (`protocol_mini60.py`, mostly CONFIRMED-BY-CAPTURE) |
|---|---|---|
| framing | no magic; `[0]=cmd`; 63-byte body + report id 1 | `0xAA` magic, payload at offset 8, 64 B wired / 32 B wireless frames (L334-343) |
| where an entry lives | **separate 40-slot table on cmd `0x22`**, one frame per slot, entry data inline | MT/TGL are **4-byte records in the per-key table** (SET_KEY `0x22` / GET_KEY `0x12`, pageTypes 9/10); DKS is a pointer record (pageType 8) into a **separate 1024-byte DKS table** (`0x18` read / `0x28` write, 64×16 B) (L245-301, L1093-1133) |
| cmd `0x22` means | advanced-key table | SET_KEY (keymap). **Same number, different meaning. Do not share code.** |
| binding a key | keymap (cmd `0x18`) entry `[0x17, slot, slot, 0]` | the record itself sits at the key's index: `08 <dksSlot> 00 00`, `09 …`, `0A …` |
| paging | per slot: `[1]=slot`, `[4]=0x32`; read reply `[2..3]=slot`, `[4]=0x28` | byte-offset paged tables, `0x38`/`0x18` stride, last-chunk flag (L996-1015) |
| slot count | 40 entries of any type | DKS 64 slots (63 usable); MT/TGL limited only by the key count |
| key encoding | 4-byte vendor record `[code1, hid, code3, code4]` per key | bare HID usage byte |
| MT | `[hold rec 6..9][tap rec 10..13][duration 14]`, **hold first**, duration ×10 ms (UI 15..100) | `[09][tapHid][holdHid][delay]`, **tap first**, delay unit UNVERIFIED (one sample 0x28, SDK implies ×10 ms) (L1093-1108, L447-454) |
| TGL | key record at 6..9 | `[0A][hid][00][00]` (L1111-1118) |
| DKS points | 4 bytes, 0.1 mm, `route1..4` = press / bottom / release-from-bottom / release-up | 4 bytes, 0.1 mm, same order (makeValue1/2, breakValue1/2), CONFIRMED (L294-301, L461-472) |
| DKS actions | 4 full key records, interleaved with their step rows (8 bytes per action) | 4 HID bytes at 5/7/9/11 |
| DKS events | **per action, per point** step code 0..3 (tap / hold / re-press), 16 bytes | **per point** bitmask, bytes 12..15: low nibble tap bits for actions 1..4, high nibble hold (hold nibble never observed) |
| read-before-write | vendor writes the whole 40-slot table from host state (no RMW) | DKS table whole-table write; key table RMW mandatory |

The two layouts share the DKS idea and the 0.1 mm unit, and nothing else. The bytes, the
binding scheme and the MT order all differ, so a WIN60 implementation cannot reuse the MINI60
builders. The only thing a shared UI should share is a data model like `{points_mm[4],
actions[4], per-point events}`.

## 7. Proposed builders (in `protocol_win60_advkeys_wip.py`, SOURCE-ONLY)

```
build_read_advanced_keys() -> body                     # 22 80 …
parse_advanced_key_reply(body) -> dict | None
build_empty_slot(slot) -> body                         # 22 <slot> 00 00 32 00…
build_dks_slot(slot, routes[4], actions[≤4], steps[≤4][4]) -> body
build_mt_slot(slot, tap, hold, duration_raw) -> body   # hold first on the wire
build_tgl_slot(slot, key) -> body
build_advanced_key_table({slot: body}) -> [40 bodies]  # vendor full pass
keymap_entry_advanced(slot) -> [0x17, slot, slot, 0]
key_entry(hid, code1=0, code3=0, code4=0), dks_mm_to_raw(mm), mt_duration_from_ms(ms), to_report(body)
```

Golden frames (63-byte bodies, trailing zeros omitted). These are the frames the capture
checklist expects:

| case | body |
|---|---|
| D1: DKS slot 0, routes 1.5/3.0/3.0/1.5, action 1 = A, tap at press and at release | `22 00 00 00 32 01 0F 1E 1E 0F 00 04 00 00 01 00 00 01` |
| D2: same entry, row-1 bar from column 1 to column 2, plus the column-4 circle | `22 00 00 00 32 01 0F 1E 1E 0F 00 04 00 00 02 00 00 01` |
| M1: MT slot 1, tap Esc, hold L-Ctrl, 150 ms | `22 01 00 00 32 02 00 E0 00 00 00 29 00 00 0F` |
| T1: TGL slot 2, L-Shift | `22 02 00 00 32 03 00 E1 00 00` |
| empty slot n | `22 <n> 00 00 32` |
| keymap binding to slot n | entry `17 <n> <n> 00` at `key_index*4` of the 528-byte layer |

### Wiring rules (for whoever implements this later)
1. Wire it only behind a `"wip"` capability in `data/board_registry.json` (for example
   `"advancedKeys": "wip"` on the WIN60 entries, following the existing `"macros": "wip"`
   style). This research task deliberately did **not** add one.
2. Do not wire it until the capture checklist confirms D1/M1/T1 byte-for-byte.
3. Any read of the table must run inside `Api._reader_paused()`, because the LiveReader
   discards non-travel reports (see `CLAUDE.md`).
4. Write the advanced table before the keymap that points into it. That is **INFERRED**
   good practice, the reverse of the vendor's order: the vendor writes the keymap first
   (`WM` L959) and doesn't care, because it rewrites both in one pass.
5. Privacy: an entry stores key assignments only, never typed sequences or timings beyond
   the user-chosen MT threshold. That is consistent with the privacy anti-goal.

## 8. Open questions (hardware or user only)

1. Does the WIN60 firmware act on DKS/MT/TGL at all? Source offers them without any gate.
2. What do DKS step codes 2 and 3 do in the firmware, and is `route4 != route1` honoured?
3. Does the firmware accept a **single-slot** write, or does it expect the full 40-slot pass?
   Is a write applied immediately or only after the keymap write?
4. MT duration: is 10 ms per unit right in the firmware (only the UI label says so)? Is a
   duration below 15 accepted?
5. Is `code3` in the `0x17` keymap entry used by the firmware, or only `hidCode`? The vendor
   always writes both equal, and the WIP builder does the same.
6. Are advanced keys per-profile? The source shows no profile byte, so it looks like one
   table per board.
