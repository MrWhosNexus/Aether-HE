# HFD SDK Protocol Decode — Aula MINI 60 HE PRO (and HFD-family HE boards)

Source-mined protocol reference for the vendor WebHID driver at https://hub.aulacn.com.

**Provenance**
- Source bundles: `docs/context/issue-6-mini60-pro-raw/driver_src/` (minified, names intact)
  - `hfd-sdk.es-CGV2WPaF.js` — the HID SDK (all wire builders/parsers live here)
  - `HFD-D07mGRx8.js` — layouts, firmware key-index map, switch (axis) list
  - `light-BPRaNowv.js`, `trigger-t6lqQxHu.js`, `key-DVJ2ycL_.js`, `high-B56jYPrN.js`,
    `perf-DMkZ7goZ.js`, `version-BsdmHspf.js`, `info-Ce0byjrM.js`, `gifLight-Bulkc0-I.js`,
    `index-BZJzwCAk.js` (device registry)
- Wire cross-check: `webhid-capture-2026-07-20.json` (457 frames, MINI 60 HE PRO wired,
  VID 0x0C45 PID 0x80A2, usagePage 0xFF68 usage 0x61, report ID 0)

**Verification labels used throughout**
- `CONFIRMED-BY-CAPTURE` — byte-for-byte matched against at least one real frame in the capture.
- `SOURCE-ONLY` — read from driver code; never observed on the wire. Treat as plausible, not proven.

Commands actually observed on the wire in the capture (OUT and matching IN echo):
`0x10, 0x11, 0x12, 0x13, 0x14, 0x17, 0x21, 0x23, 0x27`. Everything else in this document is SOURCE-ONLY.

---

## 1. Transport and framing — CONFIRMED-BY-CAPTURE

64-byte reports, report ID 0, no leading report-ID byte in the payload.

Request frame builder (`hfd-sdk.es-CGV2WPaF.js`, fn `L`):

```js
a[0] = 170,                 // 0xAA
a[1] = n,                   // command byte
a[2] = t,                   // content length OF THIS CHUNK (0x38 for a full page)
a[3] = e & 255,             // offset LE16 low  (byte offset into the logical table)
a[4] = e >> 8 & 255,        // offset LE16 high
// bytes 5..7: normally 0, except:
a[6] = c ? 1 : 0            // LAST-CHUNK flag: 1 on the final chunk of a transfer
// payload starts at byte 8:
o && a.set(o, 8)
```

Reply parser (fn `Z`):

```js
if (n[0] !== 85) return ... // 0x55
cmd = n[1]; lenOrType = n[2]; addr = n[3] | n[4] << 8; data = n.slice(8);
```

Transaction engine (fn `m`): chunk size = `reportCount - 8` = **56 (0x38)** for this board's
64-byte reports. Large tables are paged: chunk *k* goes out with offset `k*0x38` in bytes 3..4.
Default response timeout 500 ms, up to 3 retries per chunk; the reply is matched purely on
`reply[1] == expected cmd`. The engine waits for each chunk's echo before sending the next.

Capture example (dead-zone write, 64-byte game-mode table in 2 chunks — note byte 2 and the
last-chunk flag at byte 6):

```
AA 21 38 00 00 00 00 00 | <56 payload bytes>      <- chunk 0, offset 0x0000, flag=0
AA 21 08 38 00 00 01 00 | <8 payload bytes>       <- chunk 1, offset 0x0038, flag=1
```

The previously-established anchor "`[6]=0x01` in lighting frames" is simply this last-chunk flag
(a 16-byte lighting write fits in one chunk, which is therefore also the last).

GET requests are the same frame with no payload; the device streams the table back in 0x55
frames using the same `[2]=len [3..4]=offset` paging.

---

## 2. Complete command table — from `hfd-sdk.es-CGV2WPaF.js`, enum `E`

This is the SDK's entire command constant table, verbatim (decimal in source, hex added).

| Hex | Dec | SDK name | Direction/notes | Verified |
|-----|-----|----------|-----------------|----------|
| 0x01 | 1 | `COMMUNICATION_START` | defined, **never referenced** by SDK code | SOURCE-ONLY |
| 0x02 | 2 | `COMMUNICATION_END` | defined, never referenced | SOURCE-ONLY |
| 0x0F | 15 | `SET_FACTORY_RESET` | **DANGEROUS** — see §12 | SOURCE-ONLY |
| 0x10 | 16 | `GET_DEVICE_INFO` | 56-byte info block, §3 | CONFIRMED-BY-CAPTURE |
| 0x11 | 17 | `GET_GAME_MODE` | 64-byte settings block, §4 | CONFIRMED-BY-CAPTURE |
| 0x12 | 18 | `GET_KEY` | 512B key table (126×4), §5 | CONFIRMED-BY-CAPTURE |
| 0x13 | 19 | `GET_LED_EFFECT` | 16B lighting block, §8 | CONFIRMED-BY-CAPTURE |
| 0x14 | 20 | `GET_CUSTOM_LED_DATA` | 504B per-key RGB (126×4), §9 | CONFIRMED-BY-CAPTURE |
| 0x15 | 21 | `GET_MACRO` | macro storage read, §11 | SOURCE-ONLY |
| 0x16 | 22 | `GET_FN_KEY` | 512B FN-layer key table, §5 | SOURCE-ONLY |
| 0x17 | 23 | `GET_MAGNETIC_AXIS_RT` | 1008B actuation table (126×8), §6 | CONFIRMED-BY-CAPTURE |
| 0x18 | 24 | `GET_MAGNETIC_AXIS_DKS_DATA` | 1024B DKS table (64×16), §7 | SOURCE-ONLY |
| 0x1B | 27 | `GET_LIGHT_BOX` | 24B logo/side-light block, §10 | SOURCE-ONLY |
| 0x1C | 28 | `GET_DEFAULT_FN_KEY_MATRIX` | 512B factory FN layer (`maxRetries:1`, may be unsupported) | SOURCE-ONLY |
| 0x1F | 31 | `GET_DEFAULT_KEY_MATRIX` | defined, never referenced | SOURCE-ONLY |
| 0x21 | 33 | `SET_GAME_MODE` | write of §4 block | CONFIRMED-BY-CAPTURE |
| 0x22 | 34 | `SET_KEY` | write of §5 table (504B) | SOURCE-ONLY |
| 0x23 | 35 | `SET_LED_EFFECT` | write of §8 block | CONFIRMED-BY-CAPTURE |
| 0x24 | 36 | `SET_CUSTOM_LED_DATA` | write of §9 per-key RGB | SOURCE-ONLY |
| 0x25 | 37 | `SET_MACRO` | macro storage write, §11 | SOURCE-ONLY |
| 0x26 | 38 | `SET_FN_KEY` | write FN-layer key table | SOURCE-ONLY |
| 0x27 | 39 | `SET_MAGNETIC_AXIS_RT` | write of §6 actuation table | CONFIRMED-BY-CAPTURE |
| 0x28 | 40 | `SET_MAGNETIC_AXIS_DKS_DATA` | write of §7 DKS table | SOURCE-ONLY |
| 0x2A | 42 | `SET_DOT_MATRIX_MODE` | 8B dot-matrix screen config (screen boards only) | SOURCE-ONLY |
| 0x2B | 43 | `SET_LIGHT_BOX` | write of §10 block | SOURCE-ONLY |
| 0x30 | 48 | `SET_KEYBOARD_CUSTOM_FUNCTION_ON` | defined, never referenced | SOURCE-ONLY |
| 0x31 | 49 | `SET_KEYBOARD_CUSTOM_FUNCTION_OFF` | defined, never referenced | SOURCE-ONLY |
| 0x32 | 50 | `GET_LED_DATA` | despite the name, used to **stream live per-key RGB** (§9.3) | SOURCE-ONLY |
| 0x33 | 51 | `GET_ALL_LIGHTS_RGB` | query current color of all LEDs (send 504B of ids, get 504B back) | SOURCE-ONLY |
| 0x34 | 52 | `SET_TEMPORARY_COMMAND_DATA` | date/time + PC-stats push to screen boards | SOURCE-ONLY |
| 0x35 | 53 | `SET_MUSIC_DATA` | music-visualizer color stream (RGB565), has a checksum variant | SOURCE-ONLY |
| 0x36 | 54 | `CLEAR_LED_DATA` | clears streamed LED data (no payload) | SOURCE-ONLY |
| 0x37 | 55 | `GET_ALL_LIGHTS_RGB_24G` | wireless variant of 0x33, RGB565 packed | SOURCE-ONLY |
| 0x40 | 64 | `SET_LED_BOOT_ANIMATION` | defined, never referenced | SOURCE-ONLY |
| 0x41 | 65 | `SET_LED_USER_ANIMATION` | bulk upload user LED animation (large-report dongle path) | SOURCE-ONLY |
| 0x42 | 66 | `SET_LED_DATA` | bulk upload GIF lighting frames | SOURCE-ONLY |
| 0x4F | 79 | `SET_FLASH_DOWNLOAD` | **DANGEROUS — firmware flash entry.** Never referenced by this SDK build; DO NOT SEND | SOURCE-ONLY |
| 0x50 | 80 | `SET_TFT_USER_ANIMATION` | TFT screen animation upload | SOURCE-ONLY |
| 0x51 | 81 | `SET_TFT_BUILT_IN_INDEX` | select built-in TFT animation | SOURCE-ONLY |
| 0x60 | 96 | `GET_MAGNETIC_AXIS_KEY_STATUS` | defined, never referenced | SOURCE-ONLY |
| 0x64 | 100 | `SET_CALIBRATION_ON` | **CAUTION** — starts calibration mode, §12 | SOURCE-ONLY |
| 0x65 | 101 | `SET_CALIBRATION_OFF` | ends calibration mode | SOURCE-ONLY |
| 0x66 | 102 | `SET_SIMULATION_TEST_ON` | key-travel test mode (streams 0xFB reports) | SOURCE-ONLY |
| 0x67 | 103 | `SET_SIMULATION_TEST_OFF` | ends test mode | SOURCE-ONLY |
| 0xFA | 250 | `GET_DEVICE_NOTIFY` | unsolicited device-state notification (IN only) | SOURCE-ONLY |
| 0xFB | 251 | `GET_MAGNETIC_AXIS_CALIBRATION_DATA` | unsolicited calibration/test stream (IN only), §12 | SOURCE-ONLY |
| 0xFC | 252 | `GET_24G_DISCONNECT_NOTIFY` | IN only; `data[2]==4` → 2.4G disconnected, `data[2]==5` → device reset | SOURCE-ONLY |
| 0xFD | 253 | `GET_TFT_STATE_NOTIFY` | defined, never referenced | SOURCE-ONLY |

Source quote (enum `E`):

```js
E = { COMMUNICATION_START: 1, COMMUNICATION_END: 2, SET_FACTORY_RESET: 15,
  GET_DEVICE_INFO: 16, GET_GAME_MODE: 17, GET_KEY: 18, GET_LED_EFFECT: 19,
  GET_CUSTOM_LED_DATA: 20, GET_MACRO: 21, GET_FN_KEY: 22, GET_MAGNETIC_AXIS_RT: 23,
  GET_MAGNETIC_AXIS_DKS_DATA: 24, GET_LIGHT_BOX: 27, GET_DEFAULT_FN_KEY_MATRIX: 28,
  GET_DEFAULT_KEY_MATRIX: 31, SET_GAME_MODE: 33, SET_KEY: 34, SET_LED_EFFECT: 35,
  SET_CUSTOM_LED_DATA: 36, SET_MACRO: 37, SET_FN_KEY: 38, SET_MAGNETIC_AXIS_RT: 39,
  SET_MAGNETIC_AXIS_DKS_DATA: 40, SET_DOT_MATRIX_MODE: 42, SET_LIGHT_BOX: 43,
  SET_KEYBOARD_CUSTOM_FUNCTION_ON: 48, SET_KEYBOARD_CUSTOM_FUNCTION_OFF: 49,
  GET_LED_DATA: 50, GET_ALL_LIGHTS_RGB: 51, SET_TEMPORARY_COMMAND_DATA: 52,
  SET_MUSIC_DATA: 53, CLEAR_LED_DATA: 54, GET_ALL_LIGHTS_RGB_24G: 55,
  SET_LED_BOOT_ANIMATION: 64, SET_LED_USER_ANIMATION: 65, SET_LED_DATA: 66,
  SET_FLASH_DOWNLOAD: 79, SET_TFT_USER_ANIMATION: 80, SET_TFT_BUILT_IN_INDEX: 81,
  GET_MAGNETIC_AXIS_KEY_STATUS: 96, SET_CALIBRATION_ON: 100, SET_CALIBRATION_OFF: 101,
  SET_SIMULATION_TEST_ON: 102, SET_SIMULATION_TEST_OFF: 103, GET_DEVICE_NOTIFY: 250,
  GET_MAGNETIC_AXIS_CALIBRATION_DATA: 251, GET_24G_DISCONNECT_NOTIFY: 252,
  GET_TFT_STATE_NOTIFY: 253 }
```

---

## 3. GET_DEVICE_INFO (0x10) — CONFIRMED-BY-CAPTURE

Request: `AA 10 38 00 00 00 01 00 ...` (read 56 bytes). Reply payload (offsets into `data = frame[8..]`),
from fn `H`:

| Payload offset | Field | Notes |
|---|---|---|
| 4–5 | `vid` LE16 | capture: `45 0C` = 0x0C45 ✓ |
| 6–7 | `pid` LE16 | capture: `A2 80` = 0x80A2 ✓ |
| 8–9 | `version` | `((b8&0x0F) + ((b8>>4)*10) + b9*100)/100`; capture `53 01` → **V1.53** |
| 12–13 | `manufacturer` LE16 | capture: 0x0166 |
| 14–15 | `product` LE16 | capture: 0x110C |
| 16 | `workMode` | capture: 0x0A |
| 17 | `batteryLevel` | capture: 0x10 (wired — likely meaningless) |
| 18 | `chargeStatus` | 1 or 2 = charging (per `getBaseInfo` in info-Ce0byjrM.js) |
| 20–21 | `axisInfo` LE16 | capture: 0x000F — plausibly a supported-axis bitmask (ids 0–3), unproven |
| 22–23 | `tftMaxFrames` LE16 | 0 on this board |
| 24–25 | `gifMaxFrames` LE16 | 0 |
| 26–27 | `ledMaxFrames` LE16 | 0 |
| 28 | `tftDirection` | 0 |

Payload bytes 0–3 exist on the wire (capture shows `00 00 00 92` before the VID) but are not
parsed by the SDK — meaning of byte 3 (0x92) unknown.

---

## 4. Game mode / global settings (GET 0x11, SET 0x21) — CONFIRMED-BY-CAPTURE

64-byte block, two chunks. Payload offsets, from fns `J` (read) and `Q` (write):

```js
r[1] = gameMode; r[3] = sleepTime; r[4] = keyDelay; r[5] = reportRate;
r[7] = tftDisplayTime; r[8] = topDeadZone * 100; r[9] = bottomDeadZone * 100;
r[11] = stabilityMode; r[14] = autoCalibration;
```

| Payload offset | Field | Units / values |
|---|---|---|
| 1 | gameMode | 0/1 |
| 3 | sleepTime | minutes, UI range 0–30 (`perf-DMkZ7goZ.js`) |
| 4 | keyDelay | |
| 5 | reportRate | 0=125Hz 1=250 2=500 3=1k 4=2k 5=4k 6=8k (`perf-DMkZ7goZ.js` roiOptions) |
| 7 | tftDisplayTime | screen boards only |
| 8 | **topDeadZone** ×100 (0.01 mm) | UI range 0–0.5 mm (`trigger` dieMin/dieMax) |
| 9 | **bottomDeadZone** ×100 | same range |
| 11 | stabilityMode | 0/1 |
| 14 | autoCalibration | 0/1 ("adaptive calibration") |

Capture cross-check (`DEADZONE_TOP_0.42mm`): `AA 21 38 00 ...` payload
`00 00 00 01 00 06 00 00 2A 00 00 01 00 00 01` → topDeadZone byte 8 = 0x2A = 42 → 0.42 mm ✓;
also shows reportRate=6 (8 kHz), sleepTime=1, stabilityMode=1, autoCalibration=1.

**IMPORTANT for implementers:** the dead zones are GLOBAL (in this table), not per-key. The
UI's read-modify-write pattern is mandatory: always `GET 0x11`, mutate, `SET 0x21` the whole
64 bytes — a partial write zeroes every other setting (report rate, sleep, calibration flags).

---

## 5. Key remap tables (GET 0x12 / SET 0x22; FN layer GET 0x16 / SET 0x26; factory FN 0x1C)

GET 0x12 CONFIRMED-BY-CAPTURE (reads observed); record semantics SOURCE-ONLY (no remap was
performed during capture).

Table: **126 records × 4 bytes = 504 bytes** (read requested as 512). Record for key index *k*
lives at byte `k*4`:

```
[0] pageType   [1] param1   [2] param2   [3] param3
```

`pageType` enum (`W` in hfd-sdk, cross-referenced by `highDataToIcon` in high-B56jYPrN.js):

```js
W = { DEFAULT:0, MOUSE:1, KEYBOARD:2, CONSUMER_KEY:3, SYSTEM_KEY:4, EXTRA_FUNCTION:5,
      MACRO:6, CB:7, DKS:8, MT:9, TGL:10, SOCD:11, RS:12, FUNC:13 };
```

Per-type record encodings (fn `B` in hfd-sdk):

| pageType | Encoding `[b0,b1,b2,b3]` |
|---|---|
| 0 DEFAULT | `[0,0,0,0]` — key keeps its factory function |
| 1 MOUSE | `[1, param1 (button set, default 1), value, 0]` |
| 2 KEYBOARD | `[2, modifier, hidUsage, 0]` — b2 is the USB HID usage code |
| 3 CONSUMER_KEY | `[3, usage & 0xFF, usage >> 8, 0]` |
| 6 MACRO | `[6, macroId, behaviorMode, clickCount]` (from `setMACROToDevice`, key-DVJ2ycL_.js) |
| 8 DKS | `[8, dksIndex, 0, 0]` — points into the 0x28 DKS table |
| 9 MT (mod-tap) | `[9, tapHid, holdHid, time_ms/10]` (`param3: sliderValue/10`, default 400 ms → 40) |
| 10 TGL (toggle) | `[10, hidUsage, 0, 0]` |
| 11 SOCD | `[11, behaviorMode, hidA, hidB]` — written to BOTH keys of the pair |
| 12 RS (snap keys) | `[12, 0, hidA, hidB]` — written to both keys |
| 13 FUNC | `[13, v>>16, v>>8, v&0xFF]` — driver-internal FN functions |

MACRO `behaviorMode` UI options are 0/1/2 (`MACROOptions` in key-DVJ2ycL_.js — play n times /
play while held / toggle; exact label semantics are i18n keys, unverified).
SOCD `behaviorMode` UI values are `3, 1, 2, 4` (`SOCDOptions` in high-B56jYPrN.js; label
strings are i18n keys — typical meanings are last-wins/A-priority/B-priority/neutral, unverified).

The FN-layer table (0x16/0x26) has the identical 126×4 format (fns `ue`/`he`).
Writes are always full-table: the driver reads 0x12, patches the edited keys, writes all 504
bytes back with 0x22.

---

## 6. Actuation / rapid-trigger table (GET 0x17 / SET 0x27) — CONFIRMED-BY-CAPTURE

**126 records × 8 bytes = 1008 bytes** (18 chunks of 0x38). Record for key index *k* at byte `k*8`.
From fns `Ne` (read) / `Re` (write):

```js
r[a]   = axisType;                    // switch model id (see §6.2)
r[a+1] = flags;                       // bit0 = isWholeFast (RT enable), bit1 = isRampageMode
r[a+2..3] = triggerKeyStroke * 100;   // LE16, 0.01 mm — actuation point ("trip")
r[a+4..5] = pressRT * 100;            // LE16, 0.01 mm — rapid-trigger press sensitivity
r[a+6..7] = releaseRT * 100;          // LE16, 0.01 mm — rapid-trigger release sensitivity
```

| Record offset | Field | Verified against capture |
|---|---|---|
| 0 | axisType (switch id) | observed 0 |
| 1 | flags: bit0 RT enable ("whole-stroke fast"), bit1 "rampage mode" | `RT_PRESS_1.25mm` frame shows flags 0→1 when RT set ✓ |
| 2–3 | trip, LE16 ×0.01 mm | `TRIP_SET_3.00mm` → `2C 01` at record offset 2 ✓ |
| 4–5 | RT press, LE16 ×0.01 mm | `RT_PRESS_1.25mm` → `7D 00` at offset 4 ✓ |
| 6–7 | RT release, LE16 ×0.01 mm | `RT_RELEASE_0.75mm` frames present ✓ |

**Correction to the earlier capture-only analysis:** records are packed from **frame byte 8**
(the standard payload start), not byte 9, and travel is at **record offset 2–3**, not 1. The
absolute frame positions coincide for key 0 (frame bytes 10–11), which is why the earlier
off-by-one reading still matched; the SDK layout above is now confirmed by decoding the capture's
`TRIP_SET_3.00mm` / `RT_PRESS_1.25mm` frames with it (key 0 = ESC decodes to exactly 3.00 mm /
1.25 mm, all other records intact).

Dead zones are NOT in this table — they are global, in game mode (§4).

UI ranges (`trigger-t6lqQxHu.js` `Trigger_Data`): travel 0.10–3.40 mm step 0.01 (default 1.2 mm);
RT 0.01–3.40 mm step 0.01; dead zones 0–0.5 mm. Max travel is clamped per switch model.
Setting `rtPress`/`rtRelease` in the UI also forces `isWholeFast = true` (`setRTPress`/`setRTRelease`).
Write pattern is read-modify-write of the whole 1008-byte table.

`isRampageMode` (bit1) is defined in the SDK but never set anywhere in the driver UI — SOURCE-ONLY,
purpose unknown.

### 6.2 Switch (axis) models — `HFD-D07mGRx8.js` export `a`

```js
[{label:"灰木轴/形意轴/咏春轴", id:1, maxTravel:3.3}, {label:"黑皇轴", id:4, maxTravel:3.4},
 {label:"磁玉Pro", id:2, maxTravel:3.3}, {label:"万磁王轴", id:3, maxTravel:3.3},
 {label:"灵云轴", id:5, maxTravel:3.4}, {label:"烟云轴", id:0, maxTravel:3.4},
 {label:"风云轴", id:7, maxTravel:3.4}]
```

| id | Name (CN) | Max travel |
|---|---|---|
| 0 | 烟云轴 (Smoke Cloud) | 3.4 mm |
| 1 | 灰木轴/形意轴/咏春轴 (Gray Wood / Xingyi / Wing Chun) | 3.3 mm |
| 2 | 磁玉 Pro (Magnetic Jade Pro) | 3.3 mm |
| 3 | 万磁王轴 (Magneto) | 3.3 mm |
| 4 | 黑皇轴 (Black King) | 3.4 mm |
| 5 | 灵云轴 (Spirit Cloud) | 3.4 mm |
| 7 | 风云轴 (Wind Cloud) | 3.4 mm |

Changing a key's switch model = write `axisType` in its RT record (`setAxisInfo`, trigger page).
Capture board reported axisType 0 for all keys.

---

## 7. DKS (dynamic keystroke) table (GET 0x18 / SET 0x28) — SOURCE-ONLY

**64 slots × 16 bytes = 1024 bytes.** A key is bound to a slot via its key-table record
`[8, slotIndex, 0, 0]` (§5). Slot layout from fns `Oe`/`Ge`:

| Offset | Field | Units |
|---|---|---|
| 0 | makeValue1 | 0.1 mm (UI: `pressProcess[0] * 10`; default 1.6 mm → 16) |
| 1 | makeValue2 | 0.1 mm (deep press point, default 3.0 mm → 30) |
| 2 | breakValue1 | 0.1 mm (release point 1) |
| 3 | breakValue2 | 0.1 mm (release point 2) |
| 4 | 0 | |
| 5 | action1 | HID usage of bound key 1 |
| 6 | 0 | |
| 7 | action2 | HID usage 2 |
| 8 | 0 | |
| 9 | action3 | HID usage 3 |
| 10 | 0 | |
| 11 | action4 | HID usage 4 |
| 12–15 | trigger-point bitmasks, one byte per trigger point TP0..TP3 | low nibble = "tap" bits for action1..4, high nibble = "hold" bits |

Bitmask decode (fn `Oe`): for byte `C` at offset 12+tp, `single = C & 0x0F`, `hold = C >> 4`;
bit *n* set in `single` → action *n+1* taps at that trigger point; in `hold` → action holds.
The driver writes `makeValue1=pressProcess[0]*10, makeValue2=pressProcess[1]*10,
breakValue1=pressProcess[1]*10, breakValue2=pressProcess[0]*10` (`setDKSToDevice`,
high-B56jYPrN.js) — i.e. break points mirror the make points.

The UI allocates the first free slot in 0..62 (`[...Array(63).keys()].find(...)`) — slot 63
appears reserved/unused by the driver.

---

## 8. Lighting effect block (GET 0x13 / SET 0x23) — CONFIRMED-BY-CAPTURE

16-byte payload (single chunk). From fn `ye` (write) / `Te` (read):

```js
e[0]=mode; e[1]=red; e[2]=green; e[3]=blue; e[4]=255; e[5..7]=secondary RGB;
e[8]=colorMode; e[9]=brightness; e[10]=speed; e[11]=direction; e[12]=effectModeType;
e[14]=170; e[15]=85;   // 0xAA 0x55 trailer
```

Absolute frame bytes (matches the established anchor exactly):

| Frame byte | Payload | Field | Capture check |
|---|---|---|---|
| 8 | 0 | mode | `01`=static … `13`=dynamic18 ✓ |
| 9–11 | 1–3 | primary RGB | `90 EE 90` ✓ |
| 12 | 4 | constant 0xFF (SDK hardcodes 255; unnamed — "alpha" in earlier notes) | `FF` ✓ |
| 13–15 | 5–7 | secondary RGB (unused on this board, 0) | `00 00 00` ✓ |
| 16 | 8 | **colorMode** (0 = fixed color, 1 = random/colorful; see note) | `01` ✓ |
| 17 | 9 | brightness 0–5 | `05`, dec→`04` on BRIGHTNESS_DEC ✓ |
| 18 | 10 | speed 0–5 | `04`, dec→`03` on SPEED_DEC ✓ |
| 19 | 11 | direction 0/1 | |
| 20 | 12 | effectModeType (driver always sends 0) | |
| 22–23 | 14–15 | 0xAA 0x55 trailer | ✓ |

**Mode values** (`light-BPRaNowv.js` `effectMode` list): `0` = off (write), `1` = static,
`2`–`19` (0x02–0x13) = dynamic1…dynamic18, `20` (0x14) = **custom per-key** (§9),
`21` = off as reported by some boards on read (`changeEffectToPage` maps 21→0).
Direction is only meaningful for modes `10, 11, 12, 16, 18`; modes `6` and `8` are
forced-random-color; speed is ignored for modes `1` and `20` (fn `lightDisabled`).

**colorMode note / open question:** per source, `colorMode = randomColor ? 1 : 0` — 1 means
"colorful/random" and 0 means "use the fixed RGB in bytes 9–11". The capture only ever shows
`colorMode=1` (every frame, including static), and the earlier hardware experiment found the
board no-ops when byte 16 is 0. These two facts are in tension. Do not assume colorMode=0
works for fixed colors on this board until re-tested (suggested test: mode=1, colorMode=0,
RGB=pure red — if the board ignores it, treat colorMode=1 as required and accept that the
fixed RGB still takes effect alongside it, which is what the capture frames imply).

---

## 9. Per-key RGB — YES, supported on this board

### 9.1 Persistent per-key colors (GET 0x14 / SET 0x24)

GET 0x14 CONFIRMED-BY-CAPTURE (the light page reads it on mount); SET 0x24 SOURCE-ONLY.

**126 records × 4 bytes = 504 bytes**: `[ledId, red, green, blue]` at `ledId*4`, and
**ledId == firmware key index (keyValue)** — the light page indexes `allCustomData[keyValue]`
directly (`light-BPRaNowv.js` `setCustomLight`). Write is the full 504-byte table with 0x24.
These colors only display when the effect mode is **20** (custom); the flow is:
`SET 0x23 mode=20` → `SET 0x24 with the color table`.

```js
// _e (setCustomLEDData): for i in 0..125: r[i*4]=i; r[i*4+1..3]=red,green,blue
```

### 9.2 Query live LED colors (0x33 / 0x37) — SOURCE-ONLY

0x33: send the 504-byte id table as payload, receive 504 bytes of `[ledId,r,g,b]` back.
0x37 (wireless): custom 4-byte header `AA 37 <seq> 00`, reply is RGB565 (2 bytes/LED,
`((p>>11&31)<<3, (p>>5&63)<<2, (p&31)<<3)`), battery level in reply byte 3 of first packet.

### 9.3 Live streaming per-key RGB (0x32) — SOURCE-ONLY, exact frames in source

`gifLight-Bulkc0-I.js` builds raw 64-byte frames for real-time animation — a second,
independent confirmation of the whole framing model:

```js
e[0]=170; e[1]=50; e[2]=56; e[3]=o*56 & 255; e[4]=o*56>>8 & 255; e[5]=0;
e[6]= (o === lastChunk) ? 1 : 0; e[7]=0;
// payload from byte 8: repeated quads (keyValue, r, g, b), 56 bytes per frame
await device.sendReport(0, e)
```

I.e. cmd 0x32 with a stream of `(keyIndex, R, G, B)` quads, paged by 0x38, last-chunk flag set
on the final frame. The driver sends these fire-and-forget in a loop (~frame delay
`3000/speed` ms). `CLEAR_LED_DATA` (0x36, no payload) stops/clears.

---

## 10. Light box / logo lighting (GET 0x1B / SET 0x2B) — SOURCE-ONLY

24-byte payload: `[0]=mode, [1..3]=RGB, [9]=brightness, [10]=speed` (fns `ve`/`Se`).
Used for boards with side/logo LEDs ("灯箱"). Untested on MINI 60 HE PRO.

---

## 11. Macros (GET 0x15 / SET 0x25) — SOURCE-ONLY

Macro storage is an address-space read/written via the offset field (bytes 3–4), not a fixed
table. Layout (fns `Ue`/`Le`):

- Bytes 0–399: **directory** — 100 slots × 4-byte LE32 absolute address of each macro's data
  (0 = empty slot).
- From byte 400: **macro blobs**, each `4-byte header + n*4 action bytes`.
  - Header: `[0..1] = actionCount*2 LE16, [2..3] = 0`.
  - Action (4 bytes): `[0..1] delay ms LE16, [2] keyCode (HID usage or mouse button),
    [3] flags`: `0x90` = keyboard/mouse press, `0x10` = keyboard/mouse release,
    `0xB0` = press (other types), `0x30` = release (other types); read side:
    `isPress = b3 & 0x80, actionType = (b3>>4)&7`.
- `macroSpaceSize: 512` bytes advertised in device info handler (hard cap on this family).
- A key triggers a macro via key-table record `[6, macroId, behaviorMode, clickCount]` (§5).

---

## 12. DANGEROUS / DO-NOT-SEND commands

| Cmd | Name | Why dangerous | Frame shape (for recognition, NOT for sending) |
|---|---|---|---|
| **0x4F** | `SET_FLASH_DOWNLOAD` | Firmware flash entry point. Never called by this driver build — a malformed send could brick the board. **Aether must never emit 0x4F.** | unknown payload |
| **0x0F** | `SET_FACTORY_RESET` | Wipes settings. Parameter rides in **byte 2** (the length slot!): `AA 0F <param> 00 00 00 00 00`. `param=255` (`RESET_ALL`) = full factory reset; `param=5` (`CLEAR_CALIBRATION`) = wipe calibration data. Fire-and-forget, no reply awaited (fn `k`; enum `X={CLEAR_CALIBRATION:5, RESET_ALL:255}`). | `AA 0F FF 00 ...` / `AA 0F 05 00 ...` |
| **0x64/0x65** | calibration on/off | Enters live calibration; the vendor UI **clears calibration first** (`factoryReset(5)` in `calibrateDevice`, trigger-t6lqQxHu.js) — i.e. once started, the board's stored calibration is gone until the procedure completes. Do not fire casually. | `AA 64 00 00 00 00 00 00` |
| 0x66/0x67 | simulation test on/off | Streams 0xFB travel reports; benign but changes device mode. Always pair ON with OFF. | `AA 66 00 ...` |
| 0x30/0x31 | custom function on/off | Never referenced; unknown effect. Avoid. | |

Calibration/test stream (IN, unsolicited, cmd 0xFB — fn `V`):

```
[0]=0x55 [1]=0xFB [2]=keyValue [3]=calibrationStatus (1=success)
[4..5]=maxValue LE16  [6..7]&0x7FFF=minValue  [8..9]=currentValue (raw ADC)
[10..11]=keyStroke (0.01mm)  [12..13]=maxStroke
```

Device notify (IN, 0xFA): `[2]` = state type, payload app-specific.
2.4G notify (IN, 0xFC): `[2]==4` dongle disconnected, `[2]==5` device reset.

---

## 13. Key index model (the "matrix mapping")

There is **one firmware key index (`keyValue`) per physical key**, and it indexes *every*
per-key table identically: key table (§5, ×4), FN table (×4), RT/actuation (§6, ×8),
custom LED (§9, ×4), live stream quads. All tables have 126 slots.

`keyValue` is NOT computed at runtime — it comes from static per-board layout arrays in
`HFD-D07mGRx8.js` (each entry: `{x, y, width, height, keyValue, row, col}`). The numbering
follows a full-size matrix with a **stride of 16 per physical row** (visible in the master map
`y`/`D`: 0=Esc, 1–12=F1–F12; 16=Backquote, 17–28=Digit1…Equal; 32=Tab, 33–44=Q…RBracket;
48=CapsLock, 49–59=A…Quote; 64=LShift, 65–74=Z…Slash; 80=LCtrl…), with high codes for
navigation/oversize keys. Do not derive indices arithmetically for UI rows — use the table.

### MINI 60 HE PRO key map (layout array `o`, 62 keys, from `HFD-D07mGRx8.js`)

| Physical row | keyValues (left→right) |
|---|---|
| 0 (Esc/number) | 0 (Esc), 17 18 19 20 21 22 23 24 25 26 27 28 (1…=), 92 (Backspace) |
| 1 (Tab) | 32 (Tab), 33–44 (Q W E R T Y U I O P [ ]), 60 (Backslash) |
| 2 (Caps) | 48 (Caps), 49–59 (A S D F G H J K L ; '), 76 (Enter) |
| 3 (Shift) | 64 (LShift), 65–74 (Z X C V B N M , . /), 75 (RShift) |
| 4 (bottom) | 80 (LCtrl), 81 (LWin), 82 (LAlt), 83 (Space), 84 (RAlt), 86 (App), 87 (RCtrl), 85 (Fn) |

Selected other codes from the master map (`y` export `D`): 1–12 F1–F12, 13 VolUp, 14 VolDn,
15 Mute, 29–31/45–47/61–63/77–79/93–95 numpad, 88 ←, 89 ↓, 90 ↑, 91 →, 96 NumpadEqual,
99 PrintScreen, 100 ScrollLock, 101 RWin, 102 Pause, 103 Insert, 104 Home, 105 PgUp,
106 Delete, 107 End, 108 PgDn, 109 Pad-, 110 Pad+.

Each map entry also carries `browserValue` = `"<hidUsage>-<PAGE>"` (e.g. `"4-KEYBOARD"` for A,
`"225-KEYBOARD"` for LShift) — the HID usage that goes into `param2` of a KEYBOARD remap record.

Layout selection (`info-Ce0byjrM.js` `initDeviceLayout`): PID 10018/10019/10020 → 68-key layout
(`r`); PID 10025 → F75 layout (`t`); everything else including MINI 60 HE PRO → 60-key layout
(`o`); dongles select by product name string.

---

## 14. Device registry — all boards this driver drives (from `index-BZJzwCAk.js`)

Entries confirmed to use THIS HFD protocol (they load `info-Ce0byjrM.js` / the layouts above):

| Product | VID | PID | Notes |
|---|---|---|---|
| **MINI 60 HE PRO** | 0x0C45 (3141) | **0x80A2 (32930)** | the capture board; usagePage 0xFF68, usage 0x61 |
| MINI 60 HE PRO (alt) | 0x0C45 | **0x80B2 (32946)** | same product string, second HW rev |
| MINI60HE MAX | 0x0C45 | 0x80A1 (32929) | usagePage 0xFF68 usage 0x61 |
| MINI 68 HE | 0x38A6 (14502) | 0x2722 (10018) | 68 layout; light page disabled for this PID |
| MINI 68 HE PRO | 0x38A6 | 0x2723 (10019) | |
| MINI68 HE MAX | 0x38A6 | 0x2724 (10020) | |
| AULA F75 HE | 0x38A6 | 0x2729 (10025) | F75 layout |
| MINI 60/68 HE PRO Dongle, AULA F75 HE Dongle | 0x0C45 | 0xFEFE (65278) | 2.4G; usagePage 0xFF60 (65376), usage 0x61; identified by product-name string |
| MINI60HE/MINI68HE MAX Dongle | 0x0C45 | 0xFEFC (65276) | usagePage 0xFF80/0xFF60 by model |

Wired HFD keyboards use usagePage **0xFF68 (65384), usage 0x61 (97)**; SDK's device-open helper
defaults to usagePage 65383 with `VALID_USAGE_PAGES = [65384, 65408, 65376, 65280, 65281, 65307]`
(class `z` statics, hfd-sdk).

The full registry also contains many NON-HFD Aula/partner devices (different protocol modules —
do not assume this protocol applies): AG60/63/75 family (VID 14502, usagePage 65456),
F87/F108 ProV2 family, HERO 68/84/99 HE (VID 14126 PID 4158, usagePage 65376),
WIN 60/68 HE (VID 11836 PID 50021, usagePage 65307), plus mice (usagePage 65448/65308/65282).
For Aether's registry, the safe additions with the SAME protocol are exactly the table above.

---

## 15. Command sequences the vendor driver uses (recipes)

- **Connect / identify:** `GET 0x10` (device info) → `GET 0x11` (game mode) → `GET 0x12` (keys)
  → per-page reads. No COMMUNICATION_START handshake is ever sent (capture confirms: first
  frame is 0x10).
- **Set actuation point for keys K:** `GET 0x17` → set `trip` in records K → `SET 0x27` (full 1008 B).
- **Set RT press/release:** same, also set flags bit0=1.
- **Set dead zones:** `GET 0x11` → patch payload bytes 8/9 → `SET 0x21` (full 64 B).
- **Set effect lighting:** `SET 0x23` (16 B, trailer AA 55). No preceding read required.
- **Set per-key colors:** `SET 0x23` with mode=20, then `GET 0x14` → patch → `SET 0x24` (504 B).
- **Remap a key:** `GET 0x12` → patch record → `SET 0x22` (504 B). FN layer: 0x16/0x26.
- **Bind SOCD pair (A,B):** patch key records of BOTH A and B to `[11, mode, hidA, hidB]` → `SET 0x22`.
- **Bind DKS:** allocate slot in 0x18 table → `SET 0x28` (1024 B) → patch key record `[8, slot]` → `SET 0x22`.

## 16. Honest gaps / not fully decoded

- `colorMode` (frame byte 16 of 0x23) tension between source semantics and the observed
  "must be 1" behavior — see §8 note; needs one controlled hardware test.
- Device-info payload bytes 0–3 (capture shows `00 00 00 92`) are unparsed by the SDK; unknown.
- `axisInfo` bitmask interpretation (0x000F on this board) is an inference, unverified.
- `isRampageMode` (RT flags bit1), `CB` pageType 7, `SYSTEM_KEY`/`EXTRA_FUNCTION` record
  encodings (fn `B` has no case writing them), and enum entries never referenced
  (0x01, 0x02, 0x1F, 0x30, 0x31, 0x40, 0x4F, 0x60, 0xFD) have no usable source semantics.
- SOCD/MACRO behaviorMode label meanings are i18n keys not present in the unpacked chunks.
- `SET_MUSIC_DATA` v1 (fn `me`) is the only frame with a checksum: 32-byte report,
  `byte[31] = sum(bytes[0..30]) & 0xFF` — quirk of that path only; nothing else is checksummed.
