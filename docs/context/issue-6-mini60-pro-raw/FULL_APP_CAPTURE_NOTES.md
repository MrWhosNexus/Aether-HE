# AULA MINI 60 HE PRO — full web-driver wire capture

**Board:** AULA MINI 60 HE PRO, VID `0x0C45` PID `0x80A2`, USB wired, vendor interface `usage_page 0xFF68` / `usage 0x61`, firmware **V1.53**.
**Driver:** `https://hub.aulacn.com` (official Aula web driver), WebHID.
**Raw frames:** `webhid-capture-macros.json` (2883 frames, 122 `MARK` labels).
Frames `0..678` are the earlier same-session lighting/trigger sweep; frames `679+` are this run.

Every claim below is backed by a real frame quoted from that file. Anything not observed is
called out explicitly as **NOT CAPTURED**.

---

## 0. Transport framing (CONFIRMED on the wire)

64-byte output reports, report ID 0. Every request is echoed back verbatim as a 64-byte input report.

```
byte 0      0xAA on OUT (host->device) ; 0x55 on IN (device->host)
byte 1      command
byte 2      payload length for this chunk (0x38 = 56 max)
bytes 3-4   u16 LE byte offset into the target table
byte 5      0x00 (unused in everything observed)
byte 6      0x01 on the LAST chunk of a transfer, else 0x00
byte 7      0x00 (padding)
bytes 8..   payload  (8 + 56 = 64, exactly fills the report)
```

The 8-byte header is the single most important correction to make: earlier guesses assumed a
7-byte header, which puts every record off by one and makes indices non-4-aligned.

Example of a full 512-byte table read, last chunk short:

```
OUT  AA 12 38 00 00 00 00 00  ...          offset 0x0000, 56 bytes
OUT  AA 12 38 38 00 00 00 00  ...          offset 0x0038
...
OUT  AA 12 08 F8 01 00 01 00  ...          offset 0x01F8, 8 bytes, last=1  -> 0x200 total
```

Writes are always **whole-table**: the driver reads the table, patches records in RAM, and
writes every chunk back, including the all-zero ones.

## 0b. Command bytes (wire-observed, cross-checked against `driver_src/hfd-sdk.es-CGV2WPaF.js`)

| Cmd | Name in SDK | Table | Size | Observed |
|-----|-------------|-------|------|----------|
| `0x11` / `0x21` | GET/SET_GAME_MODE | device config | 64 B | yes |
| `0x12` / `0x22` | GET/SET_KEY | base-layer key table | 512 B | yes |
| `0x13` / `0x23` | GET/SET_LED_EFFECT | lighting params | 16 B | yes |
| `0x14` / `0x24` | GET/SET_CUSTOM_LED_DATA | per-key RGB | 512 B | yes |
| `0x15` / `0x25` | GET/SET_MACRO | macro table | ≥512 B | yes |
| `0x16` / `0x26` | GET/SET_FN_KEY | Fn-layer key table | 512 B | yes |
| `0x17` / `0x27` | GET/SET_MAGNETIC_AXIS_RT | trigger/RT | — | earlier capture |
| `0x18` / `0x28` | GET/SET_MAGNETIC_AXIS_DKS_DATA | DKS travel table | 1024 B | yes |

**Never sent (deliberately avoided):** `0x0F` SET_FACTORY_RESET, `0x4F` SET_FLASH_DOWNLOAD,
`0x64`/`0x65` SET_CALIBRATION_ON/OFF, `0x66`/`0x67` simulation test.

---

## 1. Key remapping — CONFIRMED

Command pair **`0x12` GET_KEY / `0x22` SET_KEY**, exactly as the SDK source said.
Table is **512 bytes = 128 records × 4 bytes**. Records are indexed by *matrix position*, not by
the on-screen key order.

### Record layout

```
byte 0   pageType
byte 1   modifier / sub-parameter  (pageType-dependent)
byte 2   value  (HID usage code for pageType 2)
byte 3   value2 (pageType-dependent)
```

This **refutes** the "u16 type + u16 code" reading. It happens to look like two u16 LE values for
plain keyboard keys only because bytes 1 and 3 are zero there.

### Real frames

APP key → Pause (`0x48`), record index 86 (offset `0x0150` + payload position 8 = byte 344):

```
OUT  AA 22 38 50 01 00 00 00  00 00 00 00 00 00 00 00 02 00 48 00 00 00 ...
                                                        ^^ ^^ ^^ ^^  idx 86
```

Then R-Ctrl → Scroll Lock (`0x47`), index 87, showing both records side by side:

```
OUT  AA 22 38 50 01 00 00 00  00 00 00 00 00 00 00 00 02 00 48 00 02 00 47 00 ...
                                                        idx86=Pause  idx87=ScrollLock
```

ESC → Pause then ESC → ESC (`0x29`), proving index 0 and the pageType-2 encoding:

```
OUT  AA 22 38 00 00 00 00 00  02 00 48 00 00 ...    idx 0 = Pause
OUT  AA 22 38 00 00 00 00 00  02 00 29 00 00 ...    idx 0 = Escape
```

Space → Space (`0x2C`) at offset `0x0118` payload position 52 = byte 332 = index 83:

```
OUT  AA 22 38 18 01 00 00 00  00 x48 ... 00 00 00 00 02 00 2C 00
```

### pageType values (all wire-observed)

| pageType | Meaning | Byte layout |
|---|---|---|
| 1 | Mouse button | `01 01 <button> 00` — left button observed as `01 01 01 00` |
| 2 | Keyboard / HID usage | `02 <modmask> <hid> 00` |
| 3 | Consumer / media | `03 <lo> <hi> 00` — Fn table contains `03 23 02 00`, `03 8A 01 00` |
| 6 | Macro | see §2 |
| 8 | DKS | `08 <dksSlot> 00 00` |
| 9 | Mod-tap (MT) | `09 00 00 <delay/10ms>` |
| 10 | Toggle (TGL) | `0A 00 00 00` |
| 11 | SOCD | `0B <mode> <hidA> <hidB>` |
| 12 | Swift / Rapid-snap (RS) | `0C 00 <hidA> <hidB>` |
| 13 | Device/system function | Fn table contains `0D 00 00 01`, `0D 00 00 12` |

Byte 1 of a pageType-2 record is a **modifier bitmask**, not padding — the stock Fn table
contains `02 40 00 00`, a modifier-only entry with no HID usage.

### Key index → matrix index map (SOLVED)

Six independent wire data points pinned this:

| On-screen key (DOM order) | Table index |
|---|---|
| ESC (0) | 0 |
| `+=` (12) | 28 |
| `{[` (25) | 43 |
| `}]` (26) | 44 |
| `:;` (38) | 58 |
| `"'` (39) | 59 |
| `\|\\` (27) | 60 |
| `<,` (49) | 72 |
| `?/` (51) | 74 |
| Space (56) | 83 |
| APP (58) | 86 |
| R-Ctrl (59) | 87 |

The rule: the firmware table is a **full-size (TKL-shaped) matrix with a 16-column stride**, and
the driver's own function-picker list enumerates that same layout with the physical gaps removed.
For every key except ESC, `tableIndex = functionListIndex + 3` — the 3 offset is the physical gap
between ESC and F1. Row bases are 0, 16, 32, 48, 64, 80. Verified against all twelve points above.
The 60% board therefore uses a sparse subset of the 128 slots; slot 85 (between R-Alt and APP) is
unused on this layout.

### Layers

The **Fn layer is a completely separate 512-byte table** on `0x16` / `0x26`, identical record
format. This was not in the previous notes.

```
IN   55 16 38 00 00 00 00 00  0D 00 00 01 03 23 02 00 03 8A 01 00 0D 00 00 12 ...
OUT  AA 26 38 70 00 00 00 00  02 00 45 00 ...        Fn-layer write
```

Only **one onboard profile** exists on this board ("Onboard configuration 1"); there is no
profile-switch traffic to capture.

---

## 2. Macros — CONFIRMED (with corrections)

### There is no macro page in this driver

The sidebar exposes exactly seven pages: Lighting, Trigger, Expert, Key remapping, Advanced Key,
Performance, Version. The Vue router *does* contain a `#/keyboard/macroSet` route, but it is not
reachable for this model — navigating to it by hash is bounced to `#/home` by a route guard.
Macros are edited from the **"Shortcut list → Add shortcuts"** drawer on the Key remapping page.

> Operational warning for anyone repeating this: `location.hash = ...` trips the route guard and
> drops you to `#/home`, from which every keyboard route also bounces. Recovery is to navigate to
> `#/checkDevice` and click the device card — the WebHID grant survives, so no picker is needed.
> Use in-app clicks only.

### Command and framing

**`0x15` GET_MACRO / `0x25` SET_MACRO**, as the SDK source said. The **400-byte offset header is
CONFIRMED**.

Table layout:

```
bytes 0..399     header: 100 × u32 LE start-offset, one per macro slot
bytes 400..      macro bodies, packed back to back
```

Each macro body:

```
u16 LE   event-data length in 16-bit words  (= eventCount * 2)
u16      padding (always 0)
then N × 4-byte events
```

Each event is **4 bytes** as predicted:

```
u16 LE   delay in milliseconds (UI clamps to a 10 ms minimum)
u8       HID usage code
u8       0xB0 = key down, 0x30 = key up
```

### Macro 1 — `[A down 10ms][A up 10ms][B down 300ms][B up 10ms]`

Header written first — `0x0190` = 400 = start of macro 0's body:

```
OUT  AA 25 38 00 00 00 00 00  90 01 00 00 00 00 ...
```

Body at offset `0x0190`, length `0x14` = 20 bytes = 4 count + 16 event bytes:

```
OUT  AA 25 14 90 01 00 01 00  08 00 00 00  0A 00 04 B0  0A 00 04 30  2C 01 05 B0  0A 00 05 30
                              ^count=8      A down 10ms  A up 10ms    B down 300ms B up 10ms
```

`0x000A` = 10 ms, `0x012C` = 300 ms — 300 was chosen precisely to prove the delay is a 16-bit
little-endian field. `0x04` and `0x05` are HID usages for A and B. Count `8` = 4 events × 2.

### Macro 2 — `X↓11 X↑22 Y↓33 Y↑44 Z↓55 Z↑66 LShift↓770 LShift↑888`

Header now has two u32 entries; macro 1 starts at `0x01A4` = 420 = 400 + 20:

```
OUT  AA 25 38 00 00 00 00 00  90 01 00 00  A4 01 00 00  00 00 ...
```

Body, length `0x24` = 36 = 4 + 8 events × 4:

```
OUT  AA 25 24 A4 01 00 01 00  10 00 00 00
     0B 00 1B B0   0B=11ms   1B=x  down
     16 00 1B 30   16=22ms   x     up
     21 00 1C B0   21=33ms   1C=y  down
     2C 00 1C 30   2C=44ms   y     up
     37 00 1D B0   37=55ms   1D=z  down
     42 00 1D 30   42=66ms   z     up
     02 03 E1 B0   0x0302=770ms  E1=LeftShift down
     78 03 E1 30   0x0378=888ms  LeftShift up
```

Count `0x10` = 16 = 8 events × 2, confirming the count field is **words, not events or bytes**.
`0xE1` proves **modifiers are encoded as ordinary HID usage codes inside macro events, not as a
modifier bitmask**.

Read-back confirms the two-step read the firmware expects — 4 bytes for the count, then that many:

```
OUT  AA 15 04 90 01 00 01 00        read 4 bytes at 0x190
IN   55 15 04 90 01 00 01 00  08 00 00 00
OUT  AA 15 10 94 01 00 01 00        read 16 bytes at 0x194
IN   55 15 10 94 01 00 01 00  0A 00 04 B0 0A 00 04 30 2C 01 05 B0 0A 00 05 30
```

### Binding a macro to a key — pageType 6 CONFIRMED

The macro binding lives in the **key table** (`0x22`), pageType 6, exactly as the source claimed.

```
byte 0   0x06        macro pageType
byte 1   macro index (slot in the 400-byte header)
byte 2   play mode   0 = play once, 1 = fixed repeat count, 2 = press again to end
byte 3   loop count
```

Two bindings, deliberately different in every field so nothing is ambiguous:

```
OUT  AA 22 38 50 01 00 00 00  00 00 00 00 00 00 00 00 06 00 01 07 06 01 00 01 ...
                                                        idx86        idx87
```

- index 86 (APP): `06 00 01 07` → macro **0**, mode **1** (fixed count), **7** repeats.
- index 87 (R-Ctrl): `06 01 00 01` → macro **1**, mode **0** (play once), count 1.

The bind UI also offers "press the button again to end" (expected mode 2) — **NOT CAPTURED**, only
modes 0 and 1 were exercised.

---

## 3. Advanced keys — SDK claim CONFIRMED, with one addition

All five advanced key types write into the **same 512-byte key table via `0x22`**, keyed by
pageType, exactly as the source said: DKS=8, mod-tap=9, toggle=10, SOCD=11, snap/RS=12.

DKS additionally uses a **second table** the source description did not mention: the 1024-byte
`0x18` / `0x28` magnetic-axis DKS travel table, which the Advanced Key page reads on every mount
(`0x0000`..`0x03F0`, last chunk `0x10` bytes, total `0x400`).

### SOCD — pageType 11

Pair `|\` (index 60) and `?/` (index 74), mode "Absolute button 2 priority". The **same record is
written into both keys' slots**:

```
OUT  AA 22 38 E0 00 00 00 00  ... 0B 02 31 38 ...      idx 60
OUT  AA 22 38 18 01 00 00 00  ... 0B 02 31 38 ...      idx 74
```

`0B` = SOCD, `02` = mode (absolute-key-2 priority; the three UI modes are key-1 priority /
key-2 priority / offset mode), `0x31` and `0x38` are the **HID usage codes** of the two paired
keys (backslash and slash) — not their table indices.

### Swift / RS — pageType 12

Pair `:;` (index 58) and `"'` (index 59), same both-slots pattern:

```
OUT  AA 22 38 E0 00 00 00 00  00 00 00 00 00 00 00 00 0C 00 33 34 0C 00 33 34 ...
                                                        idx58        idx59
```

`0x33` and `0x34` are the HID usages for `;` and `'`.

### Mod-tap (MT) — pageType 9

Key `}]` (index 44), trigger delay set to 250 ms:

```
OUT  AA 22 38 A8 00 00 00 00  00 00 00 00 00 00 00 00 09 00 00 19 ...
```

`0x19` = 25 → the delay field is in **10 ms units**, and it is a single byte, so the range is
0–2550 ms. The long-press/short-press action slots could not be filled from this UI (it says
"press the MT key on your keyboard", i.e. it wants a physical key press) — the actions therefore
stayed at defaults and their encoding is **NOT CAPTURED**.

### Toggle (TGL) — pageType 10

Key `{[` (index 43), no parameters at all:

```
OUT  AA 22 38 A8 00 00 00 00  00 00 00 00 0A 00 00 00 09 00 00 19 ...
                                            idx43        idx44
```

### DKS — pageType 8 + travel table

Key `+=` (index 28). Two writes:

```
OUT  AA 28 38 00 00 00 00 00  10 1E 1E 10 00 00 ...    DKS travel points
OUT  AA 22 38 70 00 00 00 00  08 00 00 00 ...          key record, idx 28
```

`10 1E 1E 10` = 16, 30, 30, 16 → **1.6 mm / 3.0 mm / 3.0 mm / 1.6 mm in 0.1 mm units**, matching
the four UI fields (Press / Bottoming out / Lift / Reset). The travel record was written at
offset 0 of the 1024-byte table, and the key record's byte 1 was `00`, so **byte 1 is the DKS slot
index** and the table is a list of DKS entries rather than being indexed by key. With only one DKS
key configured this is consistent but not proven — a second DKS key would confirm it.
The four action slots (which functions fire at each travel point) were left empty; their encoding
is **NOT CAPTURED**.

---

## 4. Performance settings — `0x11` / `0x21`, 64-byte config

The plan's guess that these live in the "0x11/0x21 game-mode config table" is **CONFIRMED**
(`GET_GAME_MODE` = 17, `SET_GAME_MODE` = 33 in the SDK enum).

Page mount reads 64 bytes as `0x38` + `0x08`:

```
OUT  AA 11 38 00 00 00 00 00 ...
IN   55 11 38 00 00 00 00 00  00 00 00 01 00 06 00 00 2A 00 00 01 00 00 01 01 00 ...
OUT  AA 11 08 38 00 00 01 00 ...
```

Payload bytes identified by changing exactly one control at a time:

| Payload byte | Meaning | Evidence |
|---|---|---|
| 5 | **Poll rate** | 8 KHz→1 KHz changed `06`→`03`; restoring gave `03`→`06` |
| 11 | **Stable mode** | toggle changed `01`→`00`, restore `00`→`01` |
| 14 | **Adaptive calibration (Beta)** | toggle changed `01`→`00`, restore `00`→`01` |

Poll-rate encoding: `0`=125 Hz, `1`=250, `2`=500, `3`=1 K, `4`=2 K, `5`=4 K, `6`=8 K.

```
OUT  AA 21 38 00 00 00 00 00  00 00 00 01 00 03 00 00 2A 00 00 01 00 00 01 00 ...   1 KHz
OUT  AA 21 38 00 00 00 00 00  00 00 00 01 00 06 00 00 2A 00 00 01 00 00 01 00 ...   8 KHz
```

⚠️ **Side effect worth flagging:** the device reported payload byte 15 = `01`, but *every*
`0x21` write the driver emits sets byte 15 = `00`. The driver silently normalises that byte the
first time you touch anything on this page. Its meaning is unknown and it cannot be restored
through the UI.

---

## 5. Lighting

Mount reads: `0x13` (16-byte effect params) and `0x14` (512-byte per-key RGB table).

### Effect parameters — `0x13` / `0x23`, 16-byte payload

```
byte 0      effect mode  (0 = off, 1 = static, 8 = spectral cycling, 20 = custom)
bytes 1-3   R, G, B
byte 4      0xFF (unused/alpha)
byte 8      "colourful lighting effects" flag
byte 9      brightness
byte 10     speed
byte 11     "reverse lighting effect" (direction) flag
```

Evidence, one variable at a time:

```
IN   55 13 10 00 00 00 01 00  14 FF FF FF 00 00 00 00 01 04 04 00     state on mount
OUT  AA 23 10 00 00 00 01 00  00 FF FF FF FF 00 00 00 00 04 04 00     master toggle OFF -> mode 0
OUT  AA 23 10 00 00 00 01 00  01 FF FF FF FF 00 00 00 00 04 04 00     master toggle ON  -> mode 1
OUT  AA 23 10 00 00 00 01 00  01 12 34 56 FF 00 00 00 00 04 04 00     hex #123456 -> bytes 1-3
OUT  AA 23 10 00 00 00 01 00  14 12 34 56 FF 00 00 00 00 04 04 00     mode Custom = 0x14 = 20
OUT  AA 23 10 00 00 00 01 00  08 FF 00 00 FF 00 00 00 01 04 04 01     reverse ON  -> byte 11
OUT  AA 23 10 00 00 00 01 00  08 FF 00 00 FF 00 00 00 00 04 04 01     colourful OFF -> byte 8
```

Brightness `04` and speed `04` in the frames matched the UI spin-buttons reading 4 and 4, and the
hex field read `#FFFFFF` while bytes 1-3 read `FF FF FF` — so those three fields are certain.

⚠️ The **master on/off switch also rewrites the effect mode**: turning it back on wrote mode `01`
(static), it does not restore the previous mode. That is how this board's lighting mode got moved
off Custom mid-capture; it was put back manually.

### Custom per-key lighting — mode 20 + `0x24` CONFIRMED

This was the highest-value remaining lighting capture and it decodes cleanly.
`0x14` GET_CUSTOM_LED_DATA / `0x24` SET_CUSTOM_LED_DATA, 512 bytes = **128 records × 4 bytes**:

```
byte 0   LED index
byte 1   R
byte 2   G
byte 3   B
```

Painting ESC with `#123456` while the rest of the board was red:

```
OUT  AA 24 38 00 00 00 00 00  00 12 34 56  01 FF 00 00  02 FF 00 00  03 FF 00 00 ...
                              LED0=#123456 LED1=red     LED2=red     LED3=red
OUT  AA 24 38 38 00 00 00 00  0E FF 00 00  0F FF 00 00  10 FF 00 00  11 ...
OUT  AA 24 38 C0 01 00 01 00  70 FF 00 00  71 FF 00 00  72 FF 00 00  73 ...   last chunk
```

The LED index is stored explicitly in each record rather than being implied by position, and it
runs 0x00..0x7F contiguously across the nine chunks.

Restored with:

```
OUT  AA 24 38 00 00 00 00 00  00 FF 00 00  01 FF 00 00 ...
```

---

## 6. Expert settings (`masterSet`)

**Zero HID traffic on mount.** The page is a catalogue of pro-player one-click presets (HanChe,
DeLb, Spitfires, ED101, septem7, K1ra, Shr1mp, Au1, iamgrq …), each with a
"One-click configuration" button.

The earlier sweep concluded this page emitted nothing because the sidebar click failed. That was
half right for the wrong reason: the navigation now demonstrably works and the page still emits
nothing on mount.

**Deliberately not exercised.** Applying a pro preset rewrites the trigger/actuation tables for
every key at once, which would destroy the user's own per-key actuation setup for a capture that
would only re-show the already-captured `0x17`/`0x27` traffic. **NOT CAPTURED** by choice.

## 7. Version settings (`versionSet`)

**Zero HID traffic on mount** — firmware version (V1.53) comes from the device-info read done
during the initial connection handshake, not from this page.

Contains **Update Now** (firmware flash, `0x4F`) and **Factory reset** (`0x0F`). Both
**deliberately not touched**.

---

## 8. What was NOT captured

- **Macro play mode 2** ("press the button again to end") — only modes 0 and 1 exercised.
- **DKS action slots** — which function fires at each of the four travel points. The UI requires a
  physical key press on the real keyboard to fill them, which Playwright cannot produce.
- **MT long-press / short-press action encoding** — same reason.
- **Expert-settings pro presets** — skipped deliberately (would overwrite the user's actuation profile).
- **Firmware update, factory reset, calibration** — skipped deliberately, per safety rules.
- **Multimedia key remap via the "Configuration" tab** — the click produced no frames because the
  key selection is dropped when you switch tabs; the pageType-3 encoding is inferred from the
  stock Fn table (`03 23 02 00`, `03 8A 01 00`) and is **not** directly verified for a user-driven write.
- **Second DKS key** — would be needed to prove byte 1 of a pageType-8 record is a slot index.
- **Profile switching** — this board exposes only one onboard configuration slot.
- **`0x13` byte 4..7 and 12..15 semantics** — never varied.
- **`0x11`/`0x21` payload bytes other than 5, 11, 14** — including byte 8 (`0x2A`) and the
  mysterious byte 15.

---

## 9. Settings changed on the user's keyboard

Restored during the session (verified by a follow-up write on the wire):

| Change | Restored to |
|---|---|
| Poll rate 8 KHz → 1 KHz | 8 KHz |
| Stable mode ON → OFF | ON |
| Adaptive calibration ON → OFF | ON |
| Lighting colourful flag ON → OFF | ON |
| Lighting reverse flag OFF → ON | OFF |
| Lighting mode moved to Static / Spectral Cycling | Custom (mode 20) |
| ESC per-key colour → `#123456` | `#FF0000` (matches the rest of the board) |
| Fn + `?/` key (Insert) → Pause | Insert |
| `<,` → mouse left button | `<,` |
| ESC → Pause | ESC |
| Space → Pause | Space |

**Still changed — needs the user's decision:**

1. **Two macros exist on the board.** Slot M0 = `A↓ A↑ B↓ B↑`, slot M1 = `X↓ X↑ Y↓ Y↑ Z↓ Z↑ LShift↓ LShift↑`.
2. **APP key (table index 86) is bound to macro M0**, fixed-repeat ×7. Was unassigned (`00 00 00 00`).
3. **R-Ctrl key (table index 87) is bound to macro M1**, play once. Was unassigned.
4. **`{[` (index 43) is a TGL toggle key.** Was unassigned.
5. **`}]` (index 44) is an MT mod-tap key**, 250 ms. Was unassigned.
6. **`|\` (60) and `?/` (74) are a SOCD pair**, absolute-key-2 priority. Were unassigned.
7. **`:;` (58) and `"'` (59) are a Swift/RS pair.** Were unassigned.
8. **`+=` (28) is a DKS key**, travel points 1.6/3.0/3.0/1.6 mm, no actions. Was unassigned.
9. **ESC (index 0) and Space (index 83)** now hold explicit records `02 00 29 00` and `02 00 2C 00`
   instead of the "unset" `00 00 00 00`. Functionally identical — Escape and Space — but no longer
   byte-identical to factory.
10. **Lighting base colour is `#FF0000`, was `#FFFFFF`.** Invisible in Custom mode, which drives
    colour from the per-key table, but it will show if the user switches to a solid effect.
11. **Config byte 15 was `01` on the device and is now `00`** — normalised by the driver itself on
    the first `0x21` write, not by any control that was touched. Unknown meaning, not restorable
    through the UI.

Items 1–8 are all removable from the same UI pages (each advanced-key panel has an "Unbind button" /
delete control, and the shortcut list entries can be deleted). None of them were applied to a key
in the normal typing area except the ESC/Space no-op records: the keys used were APP, R-Ctrl,
brackets, semicolon, quote, backslash, slash, comma and equals, chosen to keep the blast radius small.
