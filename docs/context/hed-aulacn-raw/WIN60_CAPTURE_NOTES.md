# WIN 60 HE — live WebHID protocol capture (hed.aulacn.com)

**This is the first on-the-wire evidence for this board.** Everything else in
`docs/context/hed-aulacn-raw/` is source-only (deobfuscated `agreement.min.js`).
Every claim below marked CONFIRMED was observed on a physically-connected
Aula **WIN 60 HE**, not read out of the driver source.

- Raw log: `webhid-capture-win60.json` — 8089 frames, `{dir, reportId, hex, t}`
  with `MARK` entries naming the UI action that produced the frames after it.
  `hex` is the **63-byte report body, report ID excluded**.
- Device: `WIN 60 HE`, VID `0x2E3C` PID `0xC365`
- Vendor collection: **usagePage `0xFF1B`, usage `0x91`**, report ID **1**,
  **63 data bytes** in and out (one input report, one output report).
- Firmware string: `W669,34,KB,SI,SI2825KZHEARGB,V3.17.07`, build `Apr 15 2026,11:20:35`
- Capture method: `HIDDevice.prototype.sendReport` wrapper + `inputreport`
  listener installed via Playwright `addInitScript`, so the page-mount traffic
  was captured from the very first frame.

---

## 0. Framing (CONFIRMED)

Both directions use the same envelope:

```
byte 0      command
byte 1      sub-selector / slot / layer / read-flag   (command dependent)
byte 2..3   chunk index, BIG-endian
byte 4      payload length for this chunk
byte 5..    payload
```

- **No `0xAA`/`0x55` magic** — CONFIRMED. Unlike the hub.aulacn.com driver,
  there is no preamble; byte 0 is the command.
- Read requests are the same command with `byte1 |= 0x80` (`18 80`, `19 80`,
  `22 80`, `09 80`) or a dedicated sub value (`25 00`, `26 00`, `24 01`).
- Multi-chunk tables ACK per chunk with an all-zero-payload echo
  (`OUT 09 01 00 03 36 …` → `IN 09 01 00 00 00 …`).
- **The `0x21` family is the exception**: byte 4 is a constant `0x18` (24) and
  the *sub-command is the first payload byte, byte 5*. The declared length is a
  lie — trigger writes actually put data out to byte 35. CONFIRMED.

### Key indexing (CONFIRMED)
- **Tables** (keymap, switch, deadband, per-key light) are indexed
  `slot = row*22 + col`. Verified: keymap slot 90 = physical `Z`, slot 91 = `X`,
  slot 95 = `N`, slot 96 = `M`, slot 122 = `Fn`.
- **Key-select bitmasks** (trigger, travel-test) are 22 bytes, transposed:
  `mask[idx % 22] |= 1 << (idx // 22)`. The all-keys mask for this board is
  `3e 26 3e 1e 1e 1e 3e 1e 1e 3e 3e 3e 3e 00 0e 00 …` = exactly **61 bits set**
  = the 61 physical keys. CONFIRMED, and matches `protocol._keymask()` exactly.

---

## 1. THE TRAVEL UNIT — the headline question. **Aether is CORRECT.**

### `readMaxTriggerTravel` (cmd `0x21`, sub `0x04`) — CONFIRMED

```
OUT  21 00 00 00 18 04 00 00 …
IN   21 00 00 00 06 04 54 01 01 01 08 00 …
          ^^ len=6  ^^sub  ^^  ^^  ^^ ^^
                          [6] [7] [9] [10]
```

Decoded with the driver's own parser (`agreement.deobf.js` L162-167):

| field | source expression | observed | meaning |
|---|---|---|---|
| unit numerator | `r[7]` (0 → 10) | `0x01` = **1** | |
| max travel | `r[9]<<8 \| r[6]` | `0x01<<8 \| 0x54` = **340** | 3.40 mm |
| divisor | `isHighPrecision ? 1000 : 100` | `isHighPrecision = false` → **100** | |
| **triggerUnit** | `unit / divisor` | **1 / 100 = 0.01 mm** | |
| min travel | `r[10]` | `0x08` = **8** | 0.08 mm |

The driver then built its slider from exactly those numbers — read live out of
the page's shadow DOM:

```
<wm-slider id="triggerAll" step="0.01" min="8" max="340" value="170">
   inner: range [8..340],  number box [0.08 .. 3.4 step 0.01],  displaying "1.70"
```

**Verdict: the device-reported unit for this board is 0.01 mm, max 3.40 mm,
min 0.08 mm — byte-for-byte identical to Aether's hardcoded
`TRIGGER_UNIT_MM = 0.01`, min 0.08, max 3.4.** The source-only claim that the
unit is device-reported is CONFIRMED as *mechanism*, but on WIN 60 HE the
reported value happens to equal Aether's constant. **No actuation value Aether
writes to this board is wrong.**

Caveat that still stands: the mechanism is real, so a *different* board in the
family (`isHighPrecision = 1`, or `r[7]` = 4/8/10 giving 0.04 / 0.08 / 0.1 mm)
would break a hardcoded 0.01. Aether should read `0x21`/sub `0x04` on connect
and derive the unit rather than assume it. That is a robustness fix, not a
correctness bug for WIN 60 HE.

### Actuation write (cmd `0x21`, mode in byte 5) — CONFIRMED

Four writes, one variable changed each time, all keys selected:

```
1.00 mm  21 00 00 00 18 00 3e 26 3e 1e 1e 1e 3e 1e 1e 3e 3e 3e 3e 00 0e 00 00 00 00 00 00 00 64 64 01 01 00 00 00 00
3.00 mm  21 00 00 00 18 00 3e 26 3e 1e 1e 1e 3e 1e 1e 3e 3e 3e 3e 00 0e 00 00 00 00 00 00 00 2c 2c 01 01 01 01 00 00
0.08 mm  21 00 00 00 18 00 3e 26 …                                                          08 08 01 01 00 00 00 00
1.70 mm  21 00 00 00 18 00 3e 26 …                                                          aa aa 01 01 00 00 00 00
```

Byte map (report-body indices):

| byte | meaning |
|---|---|
| 0 | `0x21` |
| 4 | `0x18` (constant, **not** the real length) |
| 5 | trigger **mode** |
| 6..27 | 22-byte key-select bitmask |
| 28 | travel LOW (press) |
| 29 | travel LOW (release) |
| 30 | interval1 LOW (RT press sensitivity) |
| 31 | interval2 LOW (RT release sensitivity) |
| 32 | travel HIGH (press) |
| 33 | travel HIGH (release) |
| 34 | interval1 HIGH |
| 35 | interval2 HIGH |

`0x0064 = 100 → 1.00 mm`, `0x012c = 300 → 3.00 mm`, `0x08 = 8 → 0.08 mm`,
`0x00aa = 170 → 1.70 mm`. **Unit 0.01 mm, little-endian split across the
low block (28-31) and high block (32-35). CONFIRMED.**

### Trigger modes (CONFIRMED)
| mode byte 5 | meaning | evidence |
|---|---|---|
| `0x00` | fixed actuation point | RT unchecked |
| `0x0c` (12) | Rapid Trigger, single sensitivity | RT checked → `… 0c … 2c 2c 32 32 01 01` |
| `0x0d` (13) | RT, separate press/release | "separate" checked → `… 0d … 2c 2c 78 23 01 01` |

Mode 12 writes the same value into interval1 and interval2; mode 13 writes them
independently — press 1.20 mm (`0x78`) / release 0.35 mm (`0x23`). CONFIRMED,
and matches Aether's `CLAUDE.md` ("0 = fixed, 12 = RT single, 13 = RT separate").

### Travel test (CONFIRMED framing, stream NOT captured)
```
open   21 00 00 00 18 02 3e 26 3e 1e 1e 1e 3e 1e 1e 3e 3e 3e 3e 00 0e 00 …   (sub 2 + key mask)
close  21 00 00 00 18 03 00 …                                                (sub 3)
```
Matches `build_open_trigger_test` / `build_close_trigger_test` exactly.
**I could not capture the live depth stream** — it only emits while a physical
key is pressed and I have no way to press one. NOT VERIFIED ON THE WIRE.

> ⚠️ Discrepancy in Aether's own note, from the source: `CLAUDE.md` says the
> travel-test stream is "cmd33 **sub5**". The driver's handler
> (`agreement.deobf.js` L159-161) matches on **`body[5] == 0x01`**, not 5:
> `if (r[0]==0x21 && r[5]==0x01) { depth = r[9]<<8 | r[8]; }`.
> Sub `0x05` is `readTriggerData`, a *per-key config read* with a completely
> different payload (see below). The byte offsets in
> `protocol.parse_trigger_read` (row=body[6], col=body[7],
> depth=body[8]|body[9]<<8) are correct; only the discriminator is mislabelled.

### `readTriggerData` (cmd `0x21`, sub `0x05`) — CONFIRMED
One request per key, `[6]=row`, `[7]=col`:
```
OUT  21 00 00 00 18 05 01 00        (row 1, col 0)
IN   21 00 00 00 0c 05 00 aa aa 01 01 00 00 00 00 01 00
                     ^sub  ^  ^^ ^^ ^^ ^^          ^^ ^^
                        mode  travel  intervals    row col
```
Payload len 12: `[mode, travelLo, travelLo, i1, i2, 0,0,0,0, row, col]` —
`aa aa` = 170 = 1.70 mm, confirming the read-back of what we wrote.
The driver issues 61 of these on every mount and on every profile change.

### Reset trigger / calibration — NOT EXERCISED (safety)
`21 00 00 00 18 06` (reset) and `21 00 00 00 18 08/0f …` (calibration start)
were deliberately **not** sent. The Calibration tab was opened and produced only
a `closeTriggerTest` (`21 … 18 03`). The "Start Calibration" button was never
clicked. Aether's `build_reset_trigger` / `build_calibration` remain
source-only.

### Poll rate (cmd `0x21`, sub `0x09`) — CONFIRMED
```
read   OUT 21 00 00 00 01 09 00 00      IN  21 00 00 00 02 09 08     (8 = 8 KHz)
write  OUT 21 00 00 00 00 09 01 08                                   (set 8 KHz)
```
Note `byte4 = 0x00` on the write and `0x01` on the read — **not** `0x18`.
This is byte-identical to `protocol.build_poll_rate` (`d[5]=9; d[6]=1; d[7]=rate`).
Rate codes 1/2/4/8 = 1/2/4/8 KHz. **Changing it restarts the device** — the
page shows "Switch polling rate the device will restart" and then reloads.

### Profile index (cmd `0x21`, sub `0x11`) — read CONFIRMED, write NOT SEEN
The mount ends with `OUT 21 00 00 00 00 11 00 00` (read current onboard preset).
`setProfileIndex` (sub `0x12`) exists in the source but **the UI never sends it**:
clicking Profile 1 / Profile Default instead re-flashes the whole configuration
(keymap, lighting, trigger, deadband). Profiles in this driver are host-side
presets, not device slots. This is worth knowing before Aether implements them.

---

## 2. `initInfo` / heartbeat (cmd `0x01`) — capability bitmask CONFIRMED

The driver sends a bare `01 00 00 …` once per second. The reply is constant on
this board:

```
IN  01 00 00 00 11 00 00 00 00 00 00 00 00 00 01 00 00 7f 00 01 01 00 …
    ^cmd     ^len=17                        ^[14]     ^[17] ^[18]  ^[20]
```

Parsed with the driver's own field offsets (`agreement.deobf.js` L30-34,
`p = body[5..22]`):

| field | expr | byte | value | result |
|---|---|---|---|---|
| `isPrcs` | `p[9]==1` | body[14] | `0x01` | **true** |
| flags1 | `p[12]` | **body[17]** | **`0x7f`** | |
| ↳ `isAnyKeyCalibration` | bit0 | | 1 | true |
| ↳ `isCustomLight` | bit1 | | 1 | true |
| ↳ `isMoreSwitch` | bit2 | | 1 | true |
| ↳ `isPollRate` | bit3 | | 1 | true |
| ↳ `isDeadBand` | bit4 | | 1 | true |
| ↳ `isMusicRhythm` | bit5 | | 1 | true |
| ↳ `isALlAnd6keySwitch` | bit7 | | 0 | false |
| flags2 | `p[13]` | **body[18]** | **`0x00`** | |
| ↳ **`isHighPrecision`** | bit0 | | **0** | **false → divisor 100** |
| ↳ `isGamePad` | bit2 | | 0 | false |
| ↳ `isRS` | bit3 | | 0 | false |
| ↳ `isRKRT` | bit4 | | 0 | false |
| `isMusicRhythmOn` | `p[16]` | body[21] | `0x00` | false |
| `is6KeyMode` | `p[17] & 1` | body[22] | `0x00` | false |
| `triMode` | `body[10]` | body[10] | `0x00` | **USB** |
| charging | `body[8]` | | `0x00` | not charging |
| battery % | `body[9]` | | `0x00` | 0 (wired board, no battery) |

**The capability bitmask is REAL and CONFIRMED on the wire.** Aether currently
guesses features from a static registry; it should read `0x01` on connect and
gate the UI on `body[17]`/`body[18]`. Concretely for WIN 60 HE: PRCS/SOCD,
custom per-key light, poll rate, deadband, music rhythm and per-key calibration
are all supported; **gamepad, RS, RKRT, 6-key mode and high precision are not**.
That last one is the whole reason the 0.01 mm unit is correct here.

Corroboration: the GamePad tab is visible in the UI but clicking Xbox/Classical
produced **zero HID traffic** — consistent with `isGamePad = false`.
`protocol.build_gamepad_mode` is therefore still UNVERIFIED.

### Device info (cmd `0x0d`) — CONFIRMED, new to Aether
```
OUT  0d 00 00 00 …
IN   0d 00 00 00 32 "W669,34,KB,SI,SI2825KZHEARGB,V3.17.07"     ([3]=0 → model/fw string)
IN   0d 00 00 01 32 "Apr 15 2026,11:20:35"                       ([3]=1 → build date)
```
Payload length `0x32` = 50, ASCII. Aether's protocol.py header mentions
"body[0]=13 is the info query" but has no builder or parser for it.

---

## 3. Lighting (cmd `0x07` keyboard / `0x08` ambient) — CONFIRMED, Aether exact

### `readLightList` (cmd `0x0a`) / `readSideLightList` (cmd `0x02`)
```
OUT 0a 00 …   IN 0a 00 00 00 12 02 01 03 09 04 00 0e 0f 06 07 0b 0c 10 08 a5 5a 04 04
OUT 02 00 …   IN 02 00 00 00 04 a5 5a 04 04
```
Payload len 18: 14 mode bytes `[2,1,3,9,4,0,14,15,6,7,11,12,16,8]`, then the
`a5 5a` sentinel, then `maxSpeed = 4`, `maxBrightness = 4`
(driver reads `payload[len-2]` / `payload[len-1]`). The side-light list is
empty (len 4 = sentinel + limits only) → **WIN 60 HE has no ambient LEDs.**
`protocol.parse_light_list` decodes this correctly. CONFIRMED.

Note the firmware does **not** advertise mode 10 (custom) or 100 (music) in the
list — the driver appends them itself when `isCustomLight` / `isMusicRhythm`.

### `initLightValue` (read) / `setDeviceLight` (write)
```
read   OUT 07 01 …           IN 07 00 00 00 0c 0a 04 04 ff ff ff 00 00 00
write  OUT 07 00 00 00 0e 00 03 01 00 00 ff ff 00 00 00 00 …
```
Byte map, every field isolated by changing exactly one control:

| byte | field | evidence |
|---|---|---|
| 4 | `0x0e` = 14 (payload len) | constant |
| 5 | mode | 0/1/2/10/100 as each radio was clicked |
| 6 | brightness (0..4) | 4→0→3 |
| 7 | speed (0..4) | 4→1 |
| 8,9,10 | **foreground** R,G,B | `00 ff 00` then `00 00 ff` |
| 11,12,13 | **background** R,G,B | `ff 00 00` after switching target |
| 14 | direction | 1,2,3,4,5,0 across all six radios |
| 15 | fullColor flag | `01` on, `00` off |
| 16 | (power) | always `00`, never exercised |

**This is byte-for-byte `protocol.build_light`.** CONFIRMED including the
`0..4` brightness/speed range and direction codes
(right 0, left 1, up 2, down 3, spread 4, gather 5).

Mode bytes seen: static 0, breath 1, wave 2, custom 10 (`0x0a`),
music rhythm 100 (`0x64`).

### Music rhythm (cmd `0x17`) — CONFIRMED
The driver brackets **every** light write with a rhythm state write:
```
enter music mode   OUT 17 00 00 00 02 01 01 …   →  IN 17 00 …
leave music mode   OUT 17 00 00 00 02 00 00 …   →  IN 17 00 …
```
Payload len 2, `[5]` and `[6]` both set to 1 (on) or 0 (off). Exactly
`setMusicRhythmState`. Aether has no builder for this; it must send
`17 … 02 00 00` before any non-music light write or the board can stay stuck in
rhythm mode.

### Per-key custom RGB (cmd `0x09`) — CONFIRMED, and Aether is missing a slot
```
read   OUT 09 80 …   →  IN 09 80 00 00 36 …  … IN 09 80 00 07 12 …
       OUT 09 81 …   →  IN 09 81 00 00 36 …  … IN 09 81 00 07 12 …
write  OUT 09 00 00 00 36 <54 bytes>  … OUT 09 00 00 07 12 <18 bytes>
       OUT 09 01 00 00 36 <54 bytes>  … OUT 09 01 00 07 12 <18 bytes>
```
8 chunks: 7 × 54 + 18 = **396 bytes** = 132 keys × RGB. **CONFIRMED — exactly
the 396-byte / 54-byte-page layout `protocol.build_custom_light` uses.**

New information: `byte1` is a **custom slot** — `0x00` = Custom1, `0x01` =
Custom2 (read with `0x80`/`0x81`). The UI exposes both as separate saved
palettes. Aether's `build_custom_light(slot=…)` already supports it but the app
only ever uses slot 0.

Also observed: `OUT 09 20 00 00 …` immediately before the first read — an
undocumented cmd-9 sub `0x20`, answered with `IN 09 00 00 00 00 …`. Purpose
unknown; NOT DECODED.

---

## 4. Key remap (cmd `0x18`) — CONFIRMED, Aether exact

```
read base   OUT 18 80 …    →  IN 18 80 00 00 38 … (10 chunks)
read fn     OUT 18 82 …    →  IN 18 82 00 00 38 …
write base  OUT 18 00 00 00 38 <56 bytes> … OUT 18 00 00 09 18 <24 bytes>
write fn    OUT 18 02 00 00 38 <56 bytes> … OUT 18 02 00 09 18 <24 bytes>
```

9 × 56 + 24 = **528 bytes = 132 slots × 4 bytes**. `byte1`: `0x00` base,
`0x02` Fn, `0x80`/`0x82` = read. **Byte-for-byte `_paged_keymap_packets` /
`build_read_keymap_init`.** CONFIRMED.

Per-slot entry `[type, code, param, 0]`, isolated by diffing consecutive full
table writes:

| action | slot | before → after |
|---|---|---|
| remap **Z → B** | 90 | `00 1d 00 00` → `00 05 00 00` (HID `z`→`b`) |
| remap **X → Esc** | 91 | `00 1b 00 00` → `00 29 00 00` |
| restore | 90/91 | back to `00 1d` / `00 1b` |
| bind **macro 0 to M** | 96 | `00 10 00 00` → **`10 10 00 00`** |
| bind **macro 1 to N** | 95 | `00 11 00 00` → **`10 11 01 00`** |
| Fn key (untouched) | 122 | `01 fa 00 00` |

- `type = 0x00` → plain keyboard key, `code` = HID usage.
- `type = 0x01` → special/layer; the Fn key is `01 fa`. This matches Aether's
  `code1 = 1 for the Fn/layer-shift key` note. CONFIRMED.
- **`type = 0x10` → MACRO**, and **`param` (byte 2) = macro slot index**
  (0 for M, 1 for N). NEW — Aether has no concept of this.

Aether's warning that a remap must rewrite the *entire* table is CONFIRMED: the
driver re-sends all 528 bytes of both layers for a single key change.

One important read-side detail: **the device answered the base-layer read
(`18 80`) with an all-zero 528-byte table** while still having a working
default keymap. So a zero entry means "firmware default", not "unbound". Any
Aether logic that treats the read-back as authoritative will wipe the layout.

---

## 5. MACROS (cmd `0x19`) — fully decoded. **Entirely new to Aether.**

Aether has no macro support at all; this is the first wire evidence.

```
read   OUT 19 80 …  →  IN 19 80 00 00 3a ff ff …  (5 chunks, 0xff = empty slot)
       …  19 81 … 19 89                            (10 macro slots, 0..9)
write  OUT 19 00 00 00 3a <58 bytes> … OUT 19 00 00 04 18 <24 bytes>
```
4 × 58 + 24 = **256 bytes per macro slot**, 10 slots. `byte1` = macro index,
`|0x80` to read. An unused slot reads back as all `0xff`.

### Macro 1 — recorded A↓ A↑ B↓ B↑ C↓ C↑, "Operate Once"
```
19 00 00 00 3a 00 00 00 18 00 01 00 00  04 10 00 7e  04 00 00 ca  05 10 00 7a
                                        05 00 00 cb  06 10 00 7a  06 00 00 00  00 …
```
### Macro 2 — recorded Q W E R T then Shift+1, "Operate 3 times"
```
19 01 00 00 3a 01 01 00 38 00 03 00 00  14 10 00 4d  14 00 00 6c  1a 10 00 4c
                                        1a 00 00 6d  08 10 00 4d  08 00 00 6e
                                        15 10 00 4e  15 00 00 6d  …
19 01 00 01 3a 00 5d e1 00 00 …          (payload continues across the chunk boundary)
```

**Header — 8 bytes at payload start:**

| byte | value M1 / M2 | meaning |
|---|---|---|
| 0 | `00` / `01` | macro index |
| 1 | `00` / `01` | macro index (duplicated) |
| 2..3 | `00 18` / `00 38` | **BIG-endian event-block length**: 24 = 6 events, 56 = 14 events |
| 4 | `00` / `00` | — |
| 5 | `01` / `03` | **repeat count** (UI: "Operate Once" = 1, "Operate 3 times" = 3) |
| 6..7 | `00 00` | — |

**Event — 4 bytes each:**

| byte | meaning |
|---|---|
| 0 | HID usage code (`0x04`=a, `0x05`=b, `0x06`=c, `0x14`=q, `0x1a`=w, `0x08`=e, `0x15`=r, `0x17`=t, `0xe1`=L-Shift) |
| 1 | **`0x10` = key DOWN, `0x00` = key UP** |
| 2..3 | **delay in ms, BIG-endian**, measured *after* this event |

Cross-check against the UI's own recorded list for macro 1
(`0ms A, 126ms A, 202ms B, 122ms B, 203ms C, 122ms C`):
`0x007e = 126`, `0x00ca = 202`, `0x007a = 122`, `0x00cb = 203`, `0x007a = 122`,
`0x0000 = 0`. **Exact.** (The driver shifts delays by one on read —
`agreement.deobf.js` L150-157 — because the stored delay belongs to the
*preceding* event.)

Macro types in the UI map to the repeat field / a mode not yet isolated:
`macroType1` Operate Once → 1, `macroType2` Operate N times → N,
`macroType3` toggle, `macroType4` hold-to-repeat. Only types 1 and 2 were
exercised; **3 and 4 are NOT VERIFIED**.

**A macro is only pushed to the device when it is bound to a key.** Creating and
saving a macro in the editor produced zero HID traffic; clicking the macro in
the key-binding list then wrote all 10 macro slots, both keymap layers, and all
40 advanced-key chunks.

---

## 6. Advanced keys (cmd `0x22`) — framing only. Aether has nothing.

```
read   OUT 22 80 …  →  IN 22 80 00 00 28 00 …   (40 chunks, 0x00..0x27, 40 bytes each = 1600 B)
write  OUT 22 00 00 00 32 …  …  OUT 22 27 00 00 32 …   (40 chunks, 50 bytes each = 2000 B)
```

Note the asymmetry: reads are 40-byte chunks, writes are 50-byte chunks, and
`byte1` carries the chunk number on write (`22 00` … `22 27`) while `byte2..3`
stay zero — the opposite convention from every other paged table. CONFIRMED
framing; **payload NOT decoded** — I could not get the DKS/MT/TGL/RS/RKRT editor
to open (it needs an "add advanced key" flow I did not find, and `isRS`/`isRKRT`
are both false on this board anyway). All writes observed were all-zero
(no advanced keys configured).

---

## 7. PRCS / SOCD (cmd `0x24`) — CONFIRMED, Aether exact

```
read power  OUT 24 02 …  →  IN 24 02 00 00 06 00 00 00 00 fa e5     ([5]=0 → PRCS off)
read data   OUT 24 01 …  →  IN 24 01 00 00 28 00 01 04 07 00 …      (2 chunks × 40 B)
write power OUT 24 03 00 00 01 00
write data  OUT 24 00 00 00 28 01 01 04 07 00 … / OUT 24 00 00 01 28 00 …
```

Entry = 4 bytes, up to 20 entries over 2 chunks of 40 bytes:

| byte | value | meaning |
|---|---|---|
| 0 | `01` | entry present / count |
| 1 | `01` | model index (UI "Model2", zero-based) |
| 2 | `04` | key1 HID (`a`) |
| 3 | `07` | key2 HID (`d`) |

Set A + D with Model2 in the UI → `01 01 04 07`. **Byte-for-byte
`protocol.build_prcs` (`d[j*4+5]=1, +6=model, +7=key1, +8=key2`) and
`build_prcs_power` (`d[1]=3, d[4]=1, d[5]=on`). CONFIRMED.**

Small ambiguity: the *read* returned `00 01 04 07` for the same entry (byte 0 =
`00`), so byte 0 may be an index on read and a present-flag on write. Not
resolved.

---

## 8. Switch profile (cmd `0x25`) — CONFIRMED, Aether exact

```
list    OUT 25 00 …  →  IN 25 00 00 00 06 00 04 01 02 03 05
per-key OUT 25 02 …  →  IN 25 02 00 00 3a 01 01 01 …  (3 chunks: 58+58+16 = 132 bytes)
write   OUT 25 01 00 00 3a <58> / 25 01 00 01 3a <58> / 25 01 00 02 10 <16>
```

The list payload `[00, 04, 01, 02, 03, 05]` lines up with the 4 UI entries
**HM1, HH1, CY1, TC1** → switch ids `1, 2, 3, 5`. Setting all keys to HH1 wrote
`02` everywhere; restoring HM1 wrote `01`. One byte per key, 132 keys.
**Byte-for-byte `protocol.build_switch_table` (cmd 37, `d[1]=1`, 58-byte pages)
with `default_switch=1` matching the device. CONFIRMED.**

---

## 9. Dead band (cmd `0x26`) — CONFIRMED framing; **Aether's defaults are wrong**

```
read   OUT 26 00 …  →  IN 26 00 00 00 3a …  (5 chunks: 58×4 + 32 = 264 bytes)
write  OUT 26 01 00 00 3a … / … / 26 01 00 04 20 …
```
264 bytes = 132 keys × 2 bytes `[top, bottom]`, unit **0.01 mm**:

| action | payload pattern |
|---|---|
| top → 0.10 mm | `0a 00 0a 00 0a 00 …` |
| bottom → 0.25 mm | `0a 19 0a 19 0a 19 …` |
| top → 0.02 mm | `02 19 02 19 …` |
| bottom → 0.02 mm | `02 02 02 02 …` (restored) |

`0x0a = 10 = 0.10 mm`, `0x19 = 25 = 0.25 mm`, `0x02 = 2 = 0.02 mm`. CONFIRMED.
Framing is byte-for-byte `protocol.build_deadband_table` (cmd 38, `d[1]=1`,
58-byte pages).

> ⚠️ **DISAGREEMENT**: `build_deadband_table(default_top=4, default_bottom=5)`.
> The device's actual per-key deadband on this board is **2 / 2** (0.02 mm), as
> read back at mount and confirmed by the UI sliders (`dbTop`/`dbBottom`
> `value="2"`, range `0..100` = 0..1.00 mm). Calling Aether's builder without an
> explicit per-key map silently changes every key's deadband from 0.02/0.02 to
> 0.04/0.05 mm. The defaults should come from the `26 00` read, not a constant.

---

## 10. Win-lock / performance (cmd `0x14`) — CONFIRMED, Aether exact

```
disableShiftTab ON   14 00 00 00 01 00 00 00 00 00 00 00 01 01 00 …
disableShiftTab OFF  14 00 00 00 01 00 00 00 00 00 00 00 01 00 00 …
disableWinKey OFF    14 00 00 00 01 00 00 00 00 00 00 00 00 00 00 …
disableWinKey ON     14 00 00 00 01 00 00 00 00 00 00 00 01 00 00 …
```
`byte4 = 0x01` is a constant, **not** a length — the flags live far past it:
`[12]` = disable Win key, `[13]` = disable Shift+Tab. By extension `[14]`
Alt+Tab and `[15]` Alt+F4 (both present in the UI, not toggled).
**Matches `protocol.build_win_lock` exactly** (`d[4]=1; d[12..15]=flags`).
`d[18] = win_lock_on` was never observed — UNVERIFIED.

Aether's header comment calls cmd 20 "performance / win-lock / gamepad-mode /
sleep / reset". Only the win-lock face was seen. **Sleep timer, gamepad mode and
reset are all UNVERIFIED** — no UI in this driver emitted them, and gamepad is
disabled by the capability mask on this board.

---

## 11. Fn-key state (cmd `0x0e`) — read only, NOT decoded

```
OUT 0e 00 …  →  IN 0e 00 00 00 16 02 22 0e 0a 02 02 22 12 1e 3e 0e 2e 3e 20 20 20
```
Payload length `0x16` = 22 bytes — the same width as the key-select bitmask, so
it is probably a per-column mask of which keys have Fn-layer bindings. Read once
at mount, never written during the session. **NOT VERIFIED.**

---

## 12. Page-mount read sequence (CONFIRMED)

The full connect handshake, in order, from a cold page load:

```
0d ×2        firmware string + build date
0e           Fn key state
19 80 … 19 89   10 macro slots      (5 chunks each)
22 80        advanced keys          (40 chunks × 40 B)
24 02        PRCS power
24 01        PRCS data              (2 chunks × 40 B)
18 80        keymap base            (10 chunks: 9×56 + 24)
18 82        keymap Fn              (10 chunks)
0a           light mode list
02           side light mode list
07 01        current keyboard light value
08 01        current ambient light value
09 20        (undocumented)
09 80 / 09 81   custom light slots 0 and 1  (8 chunks × 54/18 B each)
21 …18 04    readMaxTriggerTravel   ← the unit
21 …18 05 r c   readTriggerData, once per key (61 requests)
21 …01 09    poll rate
25 00 / 25 02   switch list + per-key switches
26 00        dead band              (5 chunks)
21 …00 11    current profile index
```
Everything above happens **before any user interaction**, and the heartbeat
(`01 00 …` every ~1 s) runs throughout. Section navigation itself produces **no**
traffic — every panel renders from this one mount snapshot. Aether can copy this
sequence verbatim as its connect routine.

---

## 13. Summary of Aether disagreements

| # | Item | Verdict |
|---|---|---|
| 1 | **Actuation unit 0.01 mm, min 0.08, max 3.4** | **CORRECT.** Device reports unit=1/divisor=100, max=340, min=8. No values are wrong. |
| 2 | Travel unit is *device-reported*, not fixed | **CONFIRMED mechanism.** Aether should read `21/sub 04` on connect instead of hardcoding, for other boards in the family. |
| 3 | `initInfo` capability bitmask | **CONFIRMED.** `body[17]=0x7f`, `body[18]=0x00`. Aether should gate features on this rather than a static registry. |
| 4 | `build_trigger`, `build_light`, `build_custom_light`, `build_poll_rate`, `build_prcs`, `build_prcs_power`, `build_switch_table`, `build_win_lock`, `_paged_keymap_packets`, `build_read_keymap_init`, `parse_light_list` | **All byte-for-byte correct on the wire.** |
| 5 | `build_deadband_table` defaults 4/5 | **WRONG.** Device default is 2/2. Read `26 00` instead. |
| 6 | `CLAUDE.md`: travel-test stream is "cmd33 sub5" | **MISLABELLED.** The live stream is `body[5]==0x01`; sub `0x05` is the per-key config read. Field offsets in `parse_trigger_read` are right. |
| 7 | Macros (cmd `0x19`) | **Missing entirely.** Fully decoded above — 10 slots × 256 B, 8-byte header + 4-byte events (`code, 0x10/0x00, delayBE16`), bound via keymap `type=0x10, param=slot`. |
| 8 | Music rhythm (cmd `0x17`) | **Missing.** Must be sent (`17 …02 00 00`) before non-music light writes. |
| 9 | Device info (cmd `0x0d`) | **Missing.** Gives firmware string + build date. |
| 10 | Advanced keys (cmd `0x22`) | **Missing.** Framing captured, payload not decoded. |
| 11 | Custom light slot 1 (`09 01` / `09 81`) | Supported by the builder, unused by the app. Two palettes exist. |
| 12 | Profiles | Host-side in this driver — `setProfileIndex` (sub `0x12`) is never sent by the UI. |
| 13 | `build_gamepad_mode` | **UNVERIFIED.** `isGamePad = false` on this board; the UI emitted nothing. |
| 14 | `build_reset_trigger`, `build_calibration`, `build_reset_keyboard` | **UNVERIFIED — deliberately not sent** (destructive). |

---

## 14. What I could not capture, and why

- **Live travel-test depth stream** (`0x21`, `body[5]==0x01`) — requires a
  physical key press; Playwright cannot press the hardware. Framing for
  open/close is confirmed, the stream itself is not.
- **Calibration** (`0x21` sub `0x08`/`0x0f`), **reset trigger** (sub `0x06`),
  **factory reset**, **firmware update** — deliberately skipped per the safety
  rule. The Calibration tab was opened (mount traffic captured, only a
  `closeTriggerTest`); "Start Calibration" was never clicked.
- **Advanced-key payloads** (DKS/MT/TGL/RS/RKRT) — the editor never opened;
  only all-zero table writes were seen.
- **Gamepad mode** — no traffic; `isGamePad = false`.
- **Sleep timer** — no UI in this driver.
- **Macro types 3 and 4** (toggle / hold-to-repeat) and **mouse-event macro
  steps** — not exercised.
- **Key Combination tab** (`keyManu2`) — not exercised.
- **`09 20`** — observed once at mount, meaning unknown.
- **`0x0e` Fn-key-state payload** — read but not decoded (never written).

No frame in `webhid-capture-win60.json` is synthetic. Everything is a real
`sendReport` / `inputreport` on the connected device.

---

## 15. Settings changed on the device (all restored unless noted)

| Setting | Changed to | Restored? |
|---|---|---|
| Lighting mode/brightness/speed/colours | many | ✅ back to mode 10, bri 4, speed 4, fg `FFFFFF`, bg `000000` (verified: `07 00 00 00 0e 0a 04 04 ff ff ff 00 00 00`) |
| Actuation travel (all keys) | 1.00 / 3.00 / 0.08 mm | ✅ back to 1.70 mm (`aa aa`) |
| Rapid Trigger | on, modes 12 and 13 | ✅ off (mode 0) |
| Dead band (all keys) | 0.10 / 0.25 mm | ✅ back to 0.02 / 0.02 |
| Switch profile (all keys) | HH1 | ✅ back to HM1 |
| Keymap Z, X | B, Esc | ✅ back to Z, X |
| Keymap M, N | macro 0, macro 1 | ✅ back to plain M, N |
| Win-lock flags | toggled | ✅ back to original (Win key disabled, others off) |
| Poll rate | 4 KHz | ✅ back to 8 KHz (two device restarts) |
| Profile | Profile 1 | ✅ back to Profile Default |
| **Macro slots 0 and 1** | test macros written to flash | ❌ **NOT deleted** — they are unbound and harmless, but slots 0/1 now hold `A B C` and `Q W E R T !` test macros. Delete them in the driver's Macro tab if you want a clean board. |
| **PRCS / SOCD** | one entry `A + D`, Model2 | ⚠️ the device already had `A + D` configured before the session (mount read `24 01 … 00 01 04 07`); PRCS power stayed off, so behaviour is unchanged. |
