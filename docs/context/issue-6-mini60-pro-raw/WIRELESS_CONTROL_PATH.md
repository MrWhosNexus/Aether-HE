# How the Aula Hub web driver controls the MINI 60 HE PRO over the 2.4GHz dongle

**Date:** 2026-07-21 · **Scope:** answer "how is the webapp controlling it via the dongle?", find any
wireless control path Aether is missing, and separate *"the vendor doesn't do X"* from *"X is impossible"*.

**Evidence base**
- `webhid-capture-dongle-handshake.json` — 190 frames (two identical 95-frame connect passes), tap
  installed before `open()`, full IN replies. Device 0C45:FEFE, collection usagePage 0xFF60 usage 0x61,
  report id 0, 32-byte reports, productName `"MINI 60 HE PRO Dongle"` (capture meta `devices[0].name`).
- `webhid-capture-dongle-2026-07-20.json` — 133 frames, actuation commit over RF (42-chunk 0x27 write).
- `webhid-capture-2026-07-20.json` / `webhid-capture-macros.json` — wired sessions for comparison.
- `driver_src/` — the unpacked vendor bundle (minified, names intact).

**Labels:** `CONFIRMED-BY-CAPTURE` (byte-matched against a real frame) · `SOURCE-ONLY` (read from vendor
code, never seen on the wire) · `HARDWARE-VERIFIED` (already proven on the physical board by prior tests).

---

## Q1. How does the driver know it is on the dongle?

**Answer: by the USB-level identity of the HID device the user granted — VID/PID/usagePage matched
against a static registry that carries a `wireless: 1` flag — never by the 0x10 reply.** Three separate
idioms exist in the code, all keyed off USB descriptor data:

**(a) The device registry (`index-BZJzwCAk.js`, array `Q1`).** Each product entry hardcodes the flag.
The dongle entry — SOURCE-ONLY (the mechanism), CONFIRMED-BY-CAPTURE (the identity it matches):

```js
{img:[Qe("MINI60PRO/skyBlue")],pName:["MINI 60 HE PRO Dongle"],pId:65278,vId:3141,wireless:1,
 deviceType:1, ... usage:97,usagePage:65376,customDevice:eo,layoutClass:{Info_Class:..., Light_Class:...,
 Trigger_Class:..., Key_Class:..., High_Class:..., Perf_Class:..., Version_Class:...}}
```

versus both wired entries (pId 32930 and 32946): `wireless:0, usage:97, usagePage:65384`, and —
critically — a `Gif_Light_Class` member that the dongle entry **does not have** (see Q3).

Matching at connect (`index-BZJzwCAk.js` device-hub setup):

```js
let g=Q1.find(y=>A.vendorId===y.vId&&A.productId===y.pId&&
               A.collections.some(E=>E.usagePage===y.usagePage&&E.usage===y.usage));
```

**(b) The USB productName string** disambiguates which keyboard sits behind the shared dongle PID
0xFEFE. `info-Ce0byjrM.js` `initDeviceLayout`:

```js
case 65278: switch(this.store.deviceInfo?.pName){
  case"MINI 60 HE PRO Dongle": a=R; break;   // 60-key layout
  case"MINI 68 HE PRO Dongle": a=m; break;
  case"AULA F75 HE Dongle":    a=A; break; } break;
```

The same pName switch appears in `version-BsdmHspf.js` (manual/firmware URL selection) and in the SDK's
`NEED_FULL_DEVICE_IDS` (`hfd-sdk.es-CGV2WPaF.js`): for ambiguous strings like `"3141:65278:2.4G Dongle"`
it builds a *full* device id by additionally reading `manufacturer`/`product` out of the 0x10 reply.
Our dongle's name is specific ("MINI 60 HE PRO Dongle"), so that path is not even taken.

**(c) `pName.includes("Dongle")`** as an ad-hoc guard in `trigger-t6lqQxHu.js` (see Q4, calibration).

**What is NOT used for transport identity:** the 0x10 device-info reply. Over the dongle it returns the
wired keyboard's PID — CONFIRMED-BY-CAPTURE, handshake frame 3:

```
IN  55 10 18 00 00 00 00 00  00 00 00 92 45 0C A2 80 53 01 00 00 66 01 0C 11 02 64 00 00 10 00 00 00
                                         ^^vid   ^^pid=0x80A2  ^ver 1.53         ^^wm ^^battery=0x64
```

The SDK parses it only for version/battery/manufacturer/product (`fn H` in hfd-sdk). So the "identity
paradox" (dongle enumerates as 0xFEFE but reports 0x80A2 inside the protocol) is real and the vendor
simply never relies on the in-protocol PID for anything transport-related. Also no capability bit in any
reply is consulted anywhere.

---

## Q2. How does it choose the frame size?

**Answer: read at call time from the HID report descriptor — `collections[0].outputReports[0]
.items[0].reportCount` — with a fallback of 32, and `chunk = reportCount − 8`. Nothing is keyed off
PID.** The transaction engine (`hfd-sdk.es-CGV2WPaF.js`, fn `m`) — SOURCE-ONLY (code), with the
resulting sizes CONFIRMED-BY-CAPTURE:

```js
const{cmd:a,contentSize:l=24,addrStart:d=0,data:y,timeout:u=500,maxRetries:f=3,headerCount:A=8,...}=t,
D=((c=(s=(i=(r=(o=(e=n?.collections)?.[0])?.outputReports)?.[0])?.items)?.[0])?.reportCount)||32,
_=D-A, g=Math.ceil(l/_);
```

- Wired board advertises 64-byte reports → chunk 56 (0x38). Dongle advertises 32 → chunk 24 (0x18).
- Note the *defaults lean wireless*: `reportCount||32` and `contentSize:24`.
- Capture confirmation: the wireless 0x10 read of the 56-byte info block is paged
  `AA 10 18 00…` / `AA 10 18 18…` / `AA 10 08 30 00 00 01 00` (24+24+8, last-chunk flag set) — frames
  2/4/6 — where wired does it in a single `AA 10 38 …` chunk. The 1008-byte actuation table is 42 chunks
  of 0x18 over RF (dongle capture: first `AA 27 18 00 00 00 00 00`, last `AA 27 18 D8 03 00 01 00`)
  vs 18 chunks of 0x38 wired. `chunk = frameLen − 8` is exactly what the SDK computes.

**The one exception that ignores all of this:** the live-stream class `gifLight-Bulkc0-I.js` *hardcodes*
64-byte frames and 56-byte chunks:

```js
const f=56, ... e=new Uint8Array(64).fill(0); e[0]=170,e[1]=50,e[2]=56, ... await w.sendReport(0,e)
```

If it ever ran against the 32-byte dongle collection, every `sendReport` would fail (report too long).
It never runs there — see Q3.

Two other functions bypass the 8-byte header model with a **4-byte custom header** (`L` builder:
`if(s) return a.set(s,0), o&&a.set(o,s.length), a;`): `0x37` and the wireless branch of `0x35` (Q4/Q6),
both sized `reportCount − 4` = 28 payload bytes on the dongle.

---

## Q3. Does the vendor deliberately disable streaming/animation on wireless?

**Yes — twice over, at the app layer. And a third fact changes the picture: the web app never streams
0x32 at all, even wired.**

**(a) Registry omission (SOURCE-ONLY).** The dongle registry entry (Q1) has **no `Gif_Light_Class`**;
both wired entries load `gifLight-Bulkc0-I.js`. The class that builds 0x32 frames is simply never
instantiated for the dongle device.

**(b) Route gating (SOURCE-ONLY).** `info-Ce0byjrM.js` — the default sidebar has no live-lighting page:

```js
this.deviceRoute=["lightSet","triggerSet","masterSet","keySet","highSet","perfSet","versionSet"]
```

and `getBaseInfo` adds it only when the device is **not wireless AND the app is the Electron desktop
build**:

```js
!((k=this.store.deviceInfo)?.wireless) && x() &&
  (this.deviceRoute=["lightSet","liveGifLightSet","triggerSet","masterSet","keySet","highSet","perfSet","versionSet"])
```

where `x` is `Q` from the main bundle = `Y1` (`index-BZJzwCAk.js`):

```js
function Y1(){return navigator.userAgent.includes("Electron")}
```

So: **wireless → never; browser → never; wired + desktop app → yes.** That is why the vendor capture
over the dongle showed only `0x23` and `0x14`: the effects UI on the dongle is exclusively
firmware-mode select (0x23) plus the persistent-table read on the light page mount (0x14). It also
explains why your *wired web* captures never contained 0x32 either.

**Interpretation — be careful here.** The vendor's omission CONFIRMS intent (they designed the wireless
product without live streaming), but on its own it would prove nothing about firmware capability — after
all they also "disable" 0x32 in the wired web build, where 0x32 is HARDWARE-VERIFIED to work. What makes
the "RF bridge drops 0x32" conclusion solid is your own hardware test (15 s of 0x32 at 23.8 fps, zero
render), which the vendor's design choice is *consistent with*, and one more source fact: the SDK
contains a purpose-built **wireless replacement** for the 0x32 stream (next section) — strong evidence
the vendor knew plain 0x32 does not survive the bridge. Verdict: **Aether's finding stands; nothing was
done wrong. 0x32-over-RF is vendor-abandoned, and almost certainly firmware/bridge-dropped
(HARDWARE-VERIFIED on the drop, SOURCE-ONLY on the why).**

---

## Q4. Wireless-only commands and capabilities

### 4.1 Battery — CONFIRMED-BY-CAPTURE

There is **no dedicated battery command**. Battery rides in the ordinary `0x10 GET_DEVICE_INFO` reply,
payload offsets (payload = frame bytes 8+):

| Payload offset | Field | Dongle capture value | Wired capture value |
|---|---|---|---|
| 16 | `workMode` | 0x02 | 0x0A (meaning of both unproven) |
| 17 | `batteryLevel` | **0x64 = 100 %** | 0x10 (meaningless when wired) |
| 18 | `chargeStatus` | 0x00 | — (`isCharging = [1,2].includes(chargeStatus)`) |

Handshake frame 3 (quoted in Q1) carries all three. Consumer code (`info-Ce0byjrM.js` `getBaseInfo`):

```js
M(a)&&(this.store.deviceInfo.isCharging=[1,2].includes(a?.chargeStatus),
       this.store.deviceInfo.battery=a?.batteryLevel)
```

The toolbar renders the battery/charging widget only when the *registry* flag says wireless
(`index-BZJzwCAk.js` toolbar component): `deviceInfo?.wireless===1 ? <battery/charging UI> : <wired icon>`.
So the wired UI never showed battery because of the flag, not because the field is absent.

**Refresh model:** `getBaseInfo` runs once per device (re)initialisation — no polling interval was found
in the HFD keyboard path (the many `BatteryChange` hits in the bundle belong to obfuscated *mouse* SDKs).
The handshake capture contains two full identical passes 28.7 s apart (t≈35.4 s and t≈64.1 s), which is a
full re-init (0x10+0x12+0x13+0x14), not a battery poll; likely a page/device refresh. A second battery
source exists in 0x37 (below).

### 4.2 `0x37 GET_ALL_LIGHTS_RGB_24G` — wireless LED-state read + battery — SOURCE-ONLY

`hfd-sdk.es-CGV2WPaF.js`, fn `fe` (exported as `getAllLightsRGB24G`), built specifically for the 32-byte
transport: 4-byte custom header, `reportCount − 4` = 28-byte payload chunks, RGB565 colors, and the
**battery level in byte 3 of the first reply packet**:

```js
T[0]=170,T[1]=E.GET_ALL_LIGHTS_RGB_24G,T[2]=S,T[3]=0;          // header AA 37 <seq> 00
...
f.length>0&&(A=f[0][3]);                                        // battery = first reply byte 3
const v=...slice(4)...; p=v[T]<<8|v[T+1];                       // per-LED RGB565 big-endian
I=(p>>11&31)<<3, D=(p>>5&63)<<2, _=(p&31)<<3;                   // → r,g,b
return{allLightsRgb:h,battery:A}
```

**Never called anywhere in the unpacked app chunks** (`grep getAllLightsRGB24G` over `driver_src/*.js`
hits only the SDK). Untested on hardware.

### 4.3 `0x35` wireless live-color stream — SOURCE-ONLY — the missing streaming path

The SDK's `setMusicData` (fn `pe`) is a **transport-branched live-LED writer**. Wired (reportCount 64) it
streams `0x32`; on any other report size it converts to RGB565 and streams **`0x35 SET_MUSIC_DATA`** with
a 4-byte header, explicitly configured as lossy/fire-and-forget:

```js
d=(...reportCount)||32;
if(d===64){ // wired: 0x32, 56-byte chunks of (id,r,g,b) quads, timeout 50
  ... await m(n,{cmd:E.GET_LED_DATA,contentSize:u,timeout:50,data:v,otherHeader:y})
}else{      // NOT 64 → the dongle: RGB565, positional, cmd 0x35
  const S=q({r:a[h+1],g:a[h+2],b:a[h+3]}),[T,p]=j(S); u.push(T,p);   // pack 565
  const f=d-4;                                                        // 28-byte chunks
  p[0]=170,p[1]=E.SET_MUSIC_DATA,p[2]=v,p[3]=l,                       // AA 35 <chunk#> <flag>
  await m(n,{cmd:E.SET_MUSIC_DATA,contentSize:f,maxRetries:0,timeout:5,data:h,
             headerCount:p.length,customHeader:p})                    // no retries, 5 ms timeout
}
```

(`q = (r&248)<<8|(g&252)<<3|(b&248)>>3`, `j` splits hi/lo — same file.) Payload is positional (no LED
ids), 2 bytes/LED → 126 LEDs = 252 bytes = **9 chunks per full frame** vs 21 for a 0x24 table write.

**Also never called by any unpacked app chunk.** This is a vendor-designed wireless streaming protocol
sitting unused in the SDK — the single most valuable untested lead for Aether. Whether the MINI 60 HE
PRO dongle firmware actually forwards/renders 0x35 is UNKNOWN until tried on hardware. (Caveat: the one
page component not in our unpack, `index-BoTcDpHE.js` = liveGifLightSet, could theoretically call it —
but that page is Electron+wired-only per Q3, and the registry's Gif_Light_Class for this board is
`gifLight-Bulkc0-I.js`, which we have in full and which only emits raw 0x32.)

### 4.4 `0xFC GET_24G_DISCONNECT_NOTIFY` — SOURCE-ONLY

Unsolicited IN report; two SDK listeners (`hfd-sdk.es-CGV2WPaF.js`, fns `ee`/`te`, exported as
`start24GDisconnectListener` / `startResetListener`):

```js
i[0]===85 && i[1]===E.GET_24G_DISCONNECT_NOTIFY && i[2]===4   // → 2.4G link lost callback
i[0]===85 && i[1]===E.GET_24G_DISCONNECT_NOTIFY && i[2]===5   // → device reset callback
```

No caller found in the unpacked chunks; the app's bounce to `#/checkDevice` when your link dropped was
plausibly the WebHID `disconnect` event instead. Still a real, cheap robustness signal for Aether.

### 4.5 Pairing — there is NO host-driven pairing for keyboards

The checkDevice "Click here to pair the receiver" flow is **mouse-only**:
- The i18n block is literally `mousePair:{text1:"Mouse cannot connect?",text2:"Click here to pair the receiver",...}` (`index-BZJzwCAk.js`).
- The pairing dialog component (`index-w_ZxFYwL.js`) builds its device list with
  `g.filter(i=>i.deviceType===2&&i.wireless===0)` — deviceType 2 = mice (keyboards are 1), and drives a
  separate obfuscated mouse SDK (`startParing`, `MousePair` ref). The 16-byte magic probe `N8`
  (`[1,0,0,0,8,211,49,94,112,…,114]`) is likewise a mouse-identity probe.

For HFD keyboards, re-pairing is a **firmware Fn-key function bound through the ordinary key table**,
pageType 13 (`HFD-D07mGRx8.js` master key map + i18n `hfdKey`):

| browserValue | FUNC value | Label (EN/CN) | Key-table record |
|---|---|---|---|
| `2-FUNC`..`4-FUNC` | 2–4 | Bluetooth 1/2/3 (蓝牙通道) | `0D 00 00 02..04` |
| `5-FUNC` | 5 | **Reconnect** (无线回连), icon `wirelessRepairing` | `0D 00 00 05` |
| `6-FUNC` | 6 | Fn Layer Toggle | `0D 00 00 06` |
| `7-FUNC` | 7 | **Battery Check** (查询电量), icon `betarySearch` | `0D 00 00 07` |

(Record encoding `[13, v>>16, v>>8, v&255]` per fn `B` in hfd-sdk; the stock Fn table already contains
`0D 00 00 01` / `0D 00 00 12` in the wired macro capture.) SOURCE-ONLY for the specific FUNC values.

### 4.6 Sleep timer — exists, both transports — SOURCE-ONLY (layout CONFIRMED wired)

`sleepTime` is byte 3 of the 64-byte game-mode block (0x11/0x21), minutes, UI range 0–30 step 1
(`perf-DMkZ7goZ.js`: `sleepMin:0,sleepMax:30,sleepSteps:1`; hfd-sdk `Q`: `r[3]=sleepTime`). The wired
capture showed the byte live (`sleepTime=1` in the `AA 21 38 …` frames). Not wireless-*only*, but only
meaningful on battery, and Aether does not currently expose it.

### 4.7 Explicitly absent
No RF-channel select, no link-quality query, no host wake command, no low-power-mode command exist
anywhere in the SDK enum or the app chunks. `singleKeyWake` is declared in the perf page's state and
never read or written — dead code. `workMode` (0x10 payload[16], 0x02 wireless vs 0x0A wired) is parsed
but never consumed; it *may* encode connection mode — unproven.

### 4.8 Wireless restriction on calibration — SOURCE-ONLY (matches shipped i18n)
`trigger-t6lqQxHu.js` `startCalibration`:

```js
if(this.store.deviceInfo?.pName.includes("Dongle")){
  await u.confirm(`${c.global.t("trigger.text14")}`, ... ,{showCancel:!1}); return;
}else{ await this.ServiceDevice?.startCalibration(cb) }
```

with `trigger.text14` = "In wireless mode, the driver does not support real-time calibration status
viewing. Please check the calibration status via the keyboard lighting." So over RF the vendor never
sends `0x64 SET_CALIBRATION_ON` and never expects the `0xFB` stream. (Beware: the caller
`calibrateDevice` still fires `factoryReset(5)` = clear-calibration *before* this guard — vendor bug or
intentional; either way calibration over RF proceeds on-device without host feedback.)

---

## Q5. The connect handshake, frame by frame

The 190-frame capture is **two identical 95-frame passes** (t≈35.4 s, t≈64.1 s). One pass, in order —
all CONFIRMED-BY-CAPTURE:

| Frames | Exchange | Purpose |
|---|---|---|
| 0–1 | `OPEN_CALLED`/`OPENED` | WebHID `device.open()` on the 0xFF60/0x61 collection |
| 2–7 | `0x10` read, 3 chunks (0x18+0x18+0x08, last-chunk flag on 3rd) | `getBaseInfo` → version V1.53, battery 100 %, chargeStatus, vid/pid (returns the WIRED pid 0x80A2) |
| 8–51 | `0x12` read, 22 chunks (21×0x18 + 0x08 = 512 B) | `initDeviceLayout` → base key table; drives key names/icons on the rendered board (frame 33: record `02 00 36 00` = comma key visible at table offset 0x120+8) |
| 52–53 | `0x13` read, 1 chunk (0x10) | light page mount → current effect: reply `01 FF FF FF 00 00 00 00 01 05 04 00` = mode 1 static, white, colorMode 1, brightness 5, speed 4 |
| 54–95 | `0x14` read, 21 chunks (21×0x18 = 504 B, flag on last) | light page mount → per-key RGB table (this board: LEDs 0x00–0x23 red `FF 00 00`, 0x24–0x29 green `00 FF 00`, etc.) |

**Compared with the wired session init** (`webhid-capture-2026-07-20.json`: `0x10 ×1, 0x12 ×10, 0x13 ×1,
0x14 ×9` chunks): the command sequence is **identical**; only the chunk counts differ (32- vs 64-byte
reports). There is no wireless-specific handshake step whatsoever — no COMMUNICATION_START (0x01), no
pairing/session setup, no capability negotiation. `0x11` (game mode) and `0x17` (actuation) are *not*
part of connect on either transport; they load on Performance/Trigger page mounts (dongle capture:
`0x17 ×43` [one retried chunk] + `0x11 ×3` on "NAV: Trigger Settings").

**Timing (RF):** lock-step request/echo, median OUT→IN latency **12 ms** (mean 12.4, min 11, max 19,
n=94), one transaction in flight at a time — ~83 exchanges/s ceiling under the vendor engine. Wired
equivalent: median 4 ms (macros capture, n=1273).

**Dongle reply quirk worth knowing for Aether's parser:** chunks 2 and 3 of the 0x10 reply carry stale
bytes from chunk 1 at fixed frame positions (`0C 11 02 64` reappears at frame bytes 22–25 in frames 5
and 7, where the info table is actually zero). The SDK is immune because it only parses payload offsets
< 29; a naive full-table reassembler would ingest garbage at table offsets 38–41. Trust the header `len`
byte and the offsets you asked for; don't trust the tail of short chunks.

---

## Q6. Is there ANY per-key / animation path over RF?

Ranked by evidence strength:

**(1) `0x24` persistent per-key table — HARDWARE-VERIFIED (works over RF).**
Geometry: 504 B = 21 chunks of 24. Cost model:
- Vendor-style lock-step (wait each echo): 21 × ~12 ms ≈ **252 ms/frame ≈ 4 fps**.
- Aether-style fire-and-forget at your measured ~2 ms/write: 21 × 2 ≈ **42 ms ≈ ~23 fps theoretical
  ceiling** — *if* the firmware repaints atomically and keeps up. Unknowns that matter: (a) whether
  each 0x24 write commits to flash — it is the *persistent* table, so animating through it risks
  flash wear and stutter; (b) tearing, since the table lands in 21 partial updates; (c) no delivery
  guarantee over RF without the echo check. Usable as a last-resort slow-animation fallback, not a
  proper stream.

**(2) `0x35` RGB565 stream (`setMusicData` wireless branch) — SOURCE-ONLY, the designed answer.**
9 chunks × 28 B per full frame, positional, non-persistent, vendor-tuned for lossiness
(`maxRetries:0, timeout:5`). Even lock-step at 12 ms that's ~108 ms/frame ≈ 9 fps; fire-and-forget at
2 ms/write ≈ 18 ms/frame ≈ **up to ~50 fps theoretical**. This is exactly the shape of a stream the
RF bridge was built to carry (the same SDK gives you 0x37 to read the result back, battery included).
**Unverified on hardware — the top-priority experiment.** Note `0x36 CLEAR_LED_DATA` (no payload)
exists to stop/clear streamed data, and the wired 0x32 branch of the very same function proves the two
are the vendor's transport-specific twins.

**(3) `0x41/0x42` bulk animation upload — effectively ruled out for this board.**
Both route to a *second* HID interface found via `O(productId, usagePage=65383 /*0xFF67*/)` with
4104-byte reports (`(reportCount||4104)-8`). The captured dongle exposes only the 0xFF60/32-byte
collection (capture meta), and — decisive — the 0x10 reply advertises
`tftMaxFrames=0, gifMaxFrames=0, ledMaxFrames=0` (payload offsets 22–27, all zero in frames 3/5):
the firmware declares **no stored-animation capacity**. SOURCE-ONLY + CONFIRMED-BY-CAPTURE (the zeros).

**(4) `0x32` over RF — dead.** HARDWARE-VERIFIED dropped; vendor never attempts it (Q3).

---

## Q7 / Deliverable: capabilities Aether is missing wirelessly, ranked

| # | Capability | Value | Status | What it takes |
|---|---|---|---|---|
| 1 | **Battery % + charging status** (0x10 payload[17]/[18]) | High — the one thing the vendor UI visibly has and Aether doesn't | CONFIRMED-BY-CAPTURE | Trivial: parse two bytes Aether already receives in every 0x10 reply; surface in UI when transport is 0xFEFE; refresh on reconnect and/or a slow poll (0x10 is cheap: 3 exchanges ≈ 36 ms) |
| 2 | **Live per-key streaming via 0x35 RGB565** | High — would restore host-engine effects wirelessly (at 5-6-5 color depth), closing the only real feature asymmetry | SOURCE-ONLY, needs hardware trial | Build the 4-byte-header frame (`AA 35 <chunk#> <flag>` + 28 B RGB565, positional by LED id 0..125), stream fire-and-forget, `0x36` to clear. One rainbow-test session decides it. If the dongle drops 0x35 too, fall back to #7 |
| 3 | **Sleep timer** (0x11/0x21 byte 3, 0–30 min) | Medium — battery-relevant setting the vendor exposes on the Performance page | SOURCE-ONLY (byte seen live in wired capture) | Read-modify-write of the game-mode block Aether already handles for dead zones/poll rate |
| 4 | **2.4G disconnect/reset notify (0xFC)** | Medium — clean link-loss UX instead of write timeouts | SOURCE-ONLY | Passive: match `55 FC .. 04/05` in the input-report handler; tear down/reconnect gracefully |
| 5 | **0x37 LED-state + battery read** | Low/medium — verification tool for #2 and a second battery source | SOURCE-ONLY | Same custom-header framing as #2, read side; decode RGB565 + battery byte 3 |
| 6 | **Bindable wireless key functions** (Reconnect=FUNC 5, Battery Check=FUNC 7, BT 1–3=FUNC 2–4) via pageType-13 key records | Low/medium — gives users on-board re-pair/battery without the vendor app | SOURCE-ONLY | Extend Aether's remap encoder with `0D 00 00 <v>` records; no new transport work |
| 7 | **Slow wireless animation fallback over 0x24** | Low — ~4 fps lock-step (up to ~20 fps fire-and-forget, at flash-wear risk) | HARDWARE-VERIFIED transport, cost model estimated | Reuse existing 0x24 writer at reduced FPS; gate behind a warning until flash-commit behavior is understood |
| 8 | **Wireless-mode UX guards** (hide/disable live-stream + live calibration view on RF, mirroring vendor) | Hygiene | Vendor behavior SOURCE-ONLY; 0x32 drop HARDWARE-VERIFIED | Registry flag per transport; Aether already knows which PID it opened |

**Not missing / non-existent:** host-driven pairing (keyboards pair via the on-board Reconnect key
only), RF channel selection, link quality, wake/low-power commands, and stored-animation upload
(firmware advertises zero frames). The connect handshake itself has no wireless-specific steps to
replicate.

**Honest gaps:** the `liveGifLightSet` page component (`index-BoTcDpHE.js`) is not in the unpacked set —
its internals are inferred from the Gif_Light_Class it drives, which we do have in full. Whether the
dongle firmware honors 0x35/0x37, and whether 0x24 writes commit to flash per-write, are open hardware
questions. The obfuscated mouse SDK regions of `index-BZJzwCAk.js` were not fully decoded (deliberately —
they are a different protocol family and irrelevant to this keyboard).
