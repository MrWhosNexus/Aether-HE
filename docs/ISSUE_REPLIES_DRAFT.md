# Board-submission issue replies — DRAFT, DO NOT POST

Generated 2026-07-21. Nothing here has been posted. No `gh` command was run.
A human reviews each section and posts it manually.

Every claim below was checked against `data/board_registry.json`,
`data/boards.json`, `docs/context/`, and the golden tests. Provenance words are
used in the repo's strict sense:

- **HARDWARE-VERIFIED** — round-tripped on the physical board.
- **CONFIRMED-BY-CAPTURE** — matches labelled frames from the vendor driver, never
  run against that board by Aether.
- **SOURCE-ONLY** — read out of vendor driver source. Gated `wip` in the registry,
  never advertised as working.

Two rules were applied while writing these:

1. A board with layout + identity only is **not** described as supported.
2. Boards that share a VID, a PID, or a marketing name are **not** treated as the
   same board. That inference was falsified repeatedly on 2026-07-20 (`0C45:80A1`
   vs `0C45:80A2`; the `FEFE` / `FEFC` dongles vs their wired boards; the `38A6`
   family; the `80B2` alt PID). Several replies below exist mainly to stop a
   contributor reading someone else's win as their own.

No timelines are promised anywhere. Do not add any.

**Issue → board map used here**

| Issue | Board as identified from the underside label | VID:PID | Registry slug | Drivable today |
|---|---|---|---|---|
| #1 | Aula MINI60HE Max (closed as duplicate of #4) | `0C45:80A1` | `aula-mini60he-max` | no |
| #3 | Aula WIN 60 HE Pro (SayoDevice CH32V307RBT6) | `8089:0009` | `aula-win60he-pro` | lighting only, work in progress |
| #4 | Aula MINI60HE Max | `0C45:80A1` | `aula-mini60he-max` | no |
| #5 | Aula Win60 HE Max | `1CA2:1902` | `aula-win60he-max` | no |
| #6 | Aula MINI 60 HE PRO (wired + 2.4 GHz dongle) | `0C45:80A2` / `0C45:FEFE` | `aula-mini60he-pro`, `-24g` | **yes** |
| #7 | Aula win68 HE Max | `1CA2:1901` | `aula-win68he-max` | no |
| #8 | Aula F75 Tri-Mode | `258A:010C` | `aula-f75-tri-mode` | no |

---

## Shared block: how to capture (paste into the replies that ask for one)

Several replies reference this. Keep it identical everywhere so contributors can
compare notes.

> ### Getting the bytes
>
> **First, the dead end, so nobody loses an evening to it:** `chrome://device-log`
> and `edge://device-log` do **not** work for this. Those pages log OS-level
> hardware events (USB hotplug, HID enumeration, errors). They deliberately do not
> echo WebHID API calls, so no `sendReport` line will ever appear there even with
> the keyboard connected and the driver actively writing to it. This has already
> cost one contributor real time.
>
> **Option A — the browser wrapper (works, this is how every decoded board here was
> decoded).** If your board's driver is a website (Chrome or Edge, WebHID):
>
> 1. Open the driver page. Open DevTools (F12) → Console.
> 2. Paste this **before** you click Connect:
>
> ```js
> (() => {
>   const hex = d => [...new Uint8Array(d.buffer ?? d)].map(b => b.toString(16).padStart(2, '0')).join(' ');
>   for (const fn of ['sendReport', 'sendFeatureReport']) {
>     const orig = HIDDevice.prototype[fn];
>     HIDDevice.prototype[fn] = function (id, data) {
>       console.log(`${fn} id=0x${id.toString(16)} ${hex(data)}`);
>       return orig.call(this, id, data);
>     };
>   }
> })();
> ```
>
> 3. Connect the board, then change **one setting at a time**. Before each change,
>    type a label into the console so the frames can be attributed later, e.g.
>    `console.log('MARK solid red')`, `console.log('MARK brightness up')`,
>    `console.log('MARK actuation 2.0mm')`. Those MARK lines are what make a capture
>    decodable instead of a wall of hex.
> 4. Right-click the console → Save as, and attach the file here.
>
> **Option B — Wireshark + USBPcap** (Windows), or `usbmon` + Wireshark (Linux), if
> the driver is a native app rather than a website. Start the capture, reproduce one
> action, stop, attach the `.pcapng`.
>
> **Option C — in-app submission** (read-only). Aether's Settings → Submit your board
> packages device identity, the HID descriptor and a short input capture into a JSON
> file you can attach. It never writes to a board whose protocol has not been
> decoded. It does not capture what the vendor driver sends, so it complements
> A or B rather than replacing them.
>
> Even one clean single-action capture ("set solid red", nothing else) is useful.

---

## Issue #1 — Aula MINI60HE Max (`0C45:80A1`)

**Status check before posting:** #1 was closed as a duplicate of #4. If it is still
closed, post nothing here and post the #4 reply instead. This text is only for the
case where #1 has been reopened or the submitter asks for a status there.

### Text to post

Quick status, since this one is tracked as a duplicate of #4 and the work happens
there.

Your board is `0C45:80A1`, registry slug `aula-mini60he-max`. Aether identifies it,
opens its `0xFF68` vendor collection and draws its layout. It is listed under
"Recognised, but not drivable yet" in the README, and lighting and actuation stay
switched off. Full detail, including what the capture already proved and what is
still missing, is in #4.

---

## Issue #3 — Aula WIN 60 HE Pro, SayoDevice (`8089:0009`)

Contributor: Mema133. Sources: `docs/context/issue-3-sayodevice-raw/`
(`rgb.pcapng`, `actuation.pcapng`, `actuation_0.4mm.pcapng`, `actuation_2.0mm.pcapng`,
`KBblindtestV3EN.pyw`).

Facts this reply rests on: registry slug `aula-win60he-pro`, `protocol_sayo`,
`usage_page 0xFF12`, `capabilities.lighting: true`, `capabilities.actuation: false`,
`status: bringup`. `tests/test_protocol_sayo.py` reproduces every captured packet
byte for byte. There is no `build_key_analog` builder in `protocol_sayo.py` yet, so
actuation genuinely is not wired, and the README support table shows lighting as
🚧 rather than ✅ because nobody has ever run a byte at this board from Aether.

### Text to post

Status update for the WIN 60 HE Pro specifically. This board is `8089:0009`,
SayoDevice silicon (CH32V307RBT6, PCB SI-2825C). It is a different controller
family from the Aula Win60 HE (`2E3C:C365`) despite the near-identical name, so
none of the Win60 protocol work transfers to it. Everything below is about your
board only.

**What works now**

- Identification and layout. Aether detects `8089:0009`, opens the vendor
  collection on usage page `0xFF12` (Report ID `0x22`, 1024-byte packets; the
  `0xFF11` / Report ID `0x21` / 64-byte collection is the management fallback) and
  draws the board.
- Framing and checksum are decoded and golden-tested against **every** packet in
  your `rgb.pcapng` and `actuation.pcapng`: `[0]` report ID, `[1]` echo,
  `[2..3]` LE16 checksum, then TLV commands. That is CONFIRMED-BY-CAPTURE.
- Lighting command `0x26` carries the effect selector at payload byte 3. Your two
  RGB frames differ in exactly that one byte, and the checksum delta agrees, so the
  selector is CONFIRMED-BY-CAPTURE.

**What is not proven, and is therefore gated**

- Nothing on this board has ever been round-tripped on hardware. Nobody working on
  Aether owns a WIN 60 HE Pro. That is why the README shows lighting as
  work-in-progress rather than supported: the packets are right against your
  capture, but "right against a capture" is not "observed changing your LEDs".
- Brightness and the colour table inside the `0x26` payload never varied during the
  capture, so they are replayed verbatim and are unverified. Byte 7 (`0x64` = 100)
  looks like brightness and the `RRGGBBAA`-shaped groups look like a colour table.
  Looks like is not decoded.
- **Actuation is off.** Command `0x1C` framing is captured, and from your 0.4 mm /
  2.0 mm diff pair the payload field map is now written up in
  `docs/context/issue-3-sayodevice-raw/actuation_decode_analysis.md`: bytes 12-13 =
  press point, bytes 14-15 = release point, both LE16 in 0.001 mm units (400 = 0.4 mm,
  2000 = 2.0 mm), tracking together in fixed mode. Bytes 0-7 look like per-key Hall
  calibration and bytes 8-11 / 16-19 are constant schema. That analysis is not yet a
  typed builder in `protocol_sayo.py`, and the registry still has
  `actuation: false`, so the app will not write actuation to your board. Thank you
  for the diff pair; it is the reason the field map exists at all.

**What would help next, in order of value**

1. A capture where you change **one** lighting property at a time: colour only,
   then brightness only, then effect only, with a `MARK` line before each. That
   converts the `0x26` payload from verbatim replay into real fields.
2. A rapid-trigger capture: switch to RT mode and set press and release to
   different values. Your existing pair is fixed-mode only, so whatever flips RT on
   (bytes 20-23 are the candidates) is still unknown.
3. Per-key captures so key numbering can be pinned down. The capture shows key id
   `0x2F` (47) but which physical key that is has never been confirmed. Changing
   actuation on two or three named keys, one at a time, settles it.
4. Whether a write takes effect without the trailing `0x0D` save command.

On the in-app capture reporting "total report 0": that is most likely the OS
holding the boot-keyboard interface (MI_00), not a fault on your side. Use
Wireshark + USBPcap for now, which is what produced the captures that worked.

<!-- paste the shared "Getting the bytes" block here -->

---

## Issue #4 — Aula MINI60HE Max (`0C45:80A1`)

Registry: slug `aula-mini60he-max`, `protocol: "protocol_sonix"`,
`capabilities.lighting: "wip"`, `capabilities.actuation: "wip"`,
`perKeyRgb: false`, `offerInUi: false`, `status: bringup`. Golden tests:
`tests/test_protocol_sonix.py`.

The important thing this reply must not do is let the MINI 60 HE PRO result in #6
read as a result for this board. Same VID, adjacent PID, same usage page, and the
PRO decode was tested against this protocol on hardware and **falsified**.

### Text to post

Status for the MINI60HE Max, `0C45:80A1`. Reading carefully matters here because a
different board in the same VID range was fully decoded this cycle and it is
**not** your board.

**What changed for your board**

- Identification, vendor interface and layout: Aether detects `0C45:80A1`, opens
  usage page `0xFF68`, and draws `ui/layouts/aula-mini60he-max.json`.
- Your USBPcap capture produced a real decode of the `0xAA`-framed vendor protocol,
  now in `protocol_sonix.py` and golden-tested byte for byte: `[0]=0xAA [1]=cmd
  [2]=len [3..4]=LE16 page offset`; lighting `0x23` reproduces all five captured
  frames exactly; actuation `0x27` uses 8-byte per-key records
  `[enable][mode][press BE16][release BE16][0][0]` in 0.01 mm units, paged in
  56-byte pages. That is CONFIRMED-BY-CAPTURE.
- What is still unverified inside that decode: only the single-frame actuation
  encoding is confirmed. The full multi-frame table mapping across the 18 page
  offsets is not. And the capture was over the USB cable, so it says nothing about
  the wireless paths on this tri-mode board.

**Why the flags are still off**

Lighting and actuation are marked `wip` and your board is not offered as selectable
anywhere in the app. `wip` here means exactly one thing: decoded, but never proven
on the physical hardware. No frame from Aether has ever reached a MINI60HE Max.

**Why we will not flip them by family reasoning**

The MINI 60 HE PRO (`0C45:80A2`) was decoded and hardware-verified this cycle. The
obvious hypothesis was that it spoke your `protocol_sonix`: same vendor, adjacent
PID, same `0xFF68` usage page. That hypothesis was **tested on hardware and
falsified**. The PRO ignores `protocol_sonix` frames because they default byte 16 to
0 while every real PRO lighting frame sets it to `0x01`, and the PRO is
little-endian where your capture is big-endian. Shared VID, shared usage page and
shared byte order have each been wrong for that family in turn. So the #6 result is
not your result, and equally the PRO's failure says nothing bad about your capture,
which still stands on its own evidence.

**Also new, if you use the 2.4 GHz receiver**

There is now an identity-only entry for `0C45:FEFC`, the shared dongle PID for the
MINI60HE MAX and MINI68HE MAX, taken from the vendor driver's own device registry.
It is SOURCE-ONLY: Aether can name that receiver, and nothing more. The wired
decode does not transfer to it. That is not caution for its own sake, it is what
happened on the PRO: its dongle turned out to speak the same protocol at **32-byte
frames** instead of 64, and an early 64-byte probe was silently truncated by the
HID layer and wrongly read as "different protocol".

**What would help**

- Bring-up on your actual hardware, with you driving. The first step is confirming
  the key index stride from travel/actuation reports, then one careful lighting
  write. Nothing gets written to your board without you asking for it.
- If you use the 2.4 GHz receiver, a separate capture taken **over the dongle**,
  with the USB cable unplugged. On the PRO, plugging the cable in switches the
  board to wired mode and leaves the receiver enumerated but hollow, so a capture
  with the cable in produces a false negative.

<!-- paste the shared "Getting the bytes" block here -->

---

## Issue #5 — Aula Win60 HE Max (`1CA2:1902`)

Registry: slug `aula-win60he-max`, `protocol: null`, all capabilities `false`,
`offerInUi: false`, `status: planned`, layout `ui/layouts/aula-win60he-max.json`.

### Text to post

Status for the Win60 HE Max, `1CA2:1902`. Short version: **identification and
layout only**, and that has not changed this cycle. The protocol is still undecoded,
so lighting and actuation are switched off and the board is not offered as a
selectable option anywhere in the app.

What Aether does with it today: detects the VID/PID, names it, draws its 60% layout,
and lists it under "Recognised, but not drivable yet" so the app can explain itself
rather than pretend the keyboard is not there.

**One thing worth flagging, because the names collide badly.** Several boards were
decoded or added this cycle with names close to yours, and none of them is your
board:

- Aula Win60 HE (`2E3C:C365`) is fully supported. Different controller family from
  yours. Same marketing name, different silicon.
- Aula WIN 60 HE Pro (`8089:0009`, SayoDevice) is in bring-up. Also not yours.
- Aula WIN 68 HE and Aula KP-TE153 were added this cycle. Those are `2E3C:C365`
  boards, distinguished from the Win60 HE only by USB product string. Not your
  `1CA2` family.

"Win60 HE" spans three different controllers, and "Max" spans two different product
lines. That is why nothing above unblocks you.

**What is needed, concretely:** one protocol capture from whatever app you use to
control the board today (AULA HUB, or the `magnet` web driver). A single
"set solid colour" trace is enough to start.

There is a reasonable chance your trace also unblocks the WIN 68 HE MAX in #7,
since you share vendor `1CA2` and the same product line. Treat that as a hypothesis
rather than a promise. Same-vendor inferences have been falsified four separate
times on this project, and the two boards are driven through different web portals,
which is exactly the kind of difference that turns out to matter.

<!-- paste the shared "Getting the bytes" block here -->

---

## Issue #6 — Aula MINI 60 HE PRO (`0C45:80A2` wired, `0C45:FEFE` dongle)

This is the one board in this list that genuinely moved to supported. Everything
claimed here is HARDWARE-VERIFIED unless labelled otherwise, per the registry
entries `aula-mini60he-pro` and `aula-mini60he-pro-24g` and
`docs/context/issue-6-mini60-pro-raw/`.

### Text to post

Big update, and it is a good one. The MINI 60 HE PRO is decoded and verified on
hardware, over **both** of its transports. Specifics, with what was proven how.

**Wired, `0C45:80A2`, product string `KEYBOARD MINI 60 HE PRO`, vendor collection
usage page `0xFF68` usage `0x61`, 64-byte frames.** All HARDWARE-VERIFIED:

- Lighting: write `0x23`, read back `0x13`. All 20 firmware modes with proper
  English names, brightness and speed on a 0..5 scale.
- Actuation and rapid trigger: write `0x27`, read back `0x17`. A 1.23 mm trip was
  written, read back exactly, and the whole 126-record table restored byte for
  byte. The board's stored records also decode to exactly the values that had been
  set through the vendor UI, which confirms the record layout from a second
  direction.
- Per-key RGB: effect mode 20 plus a 504-byte `0x24` table of 126 × `[led,r,g,b]`,
  round-tripped byte for byte. This was nearly missed, and the reason is worth
  recording: the vendor lighting page never sent a per-key table during the
  capture, so per-key RGB was initially written off as unsupported. Absence from a
  capture is not absence from the firmware.
- Host-driven effects: Aether's own animation engine streams to this board over
  `0x32` at a measured 27.7 fps sustained with zero write errors. Note there are
  two per-key commands and picking the wrong one was the whole problem: `0x24` is
  the persistent flash-backed table at 6.4 fps (fine for Per-key Paint, unusable
  for animation), `0x32` is the live stream.
- Dead zone: supported, but **global scope**. Dead zones live in the `0x11`/`0x21`
  game-mode table as whole-board values, not per key, so a per-key dead-zone
  control is not something this hardware can do.
- Gamepad: **not available**. There is no board-side gamepad command anywhere in
  the vendor SDK for this board.
- SOCD, macros and calibration are SOURCE-ONLY: the commands were read out of the
  vendor SDK but never captured or exercised. They are gated `wip` and the UI will
  not drive them.

**2.4 GHz receiver, `0C45:FEFE`, product string `MINI 60 HE PRO Dongle`, usage page
`0xFF60`, 32-byte frames.** Same protocol, half the frame size:

- HARDWARE-VERIFIED over RF: lighting mode and colour, the persistent per-key
  table, and actuation (42 pages read, a 1.77 mm trip written, read back exactly,
  table restored byte-identical). Rapid trigger rides the same records.
- **Host-driven effects do not work over 2.4 GHz.** This is a verified negative,
  not an untested assumption: `0x32` writes are accepted by the RF bridge and
  silently dropped (a 15 second sweep at a steady 23.8 fps of no-ops left the
  keyboard dark), and a capture of the vendor's own app driving effects over the
  dongle contains only firmware-effect commands. Aether refuses host effects on the
  wireless profile so it cannot silently animate nothing. Firmware effects work
  fine wirelessly.
- Dead zone, SOCD, macros and calibration stay `wip` over RF because none of them
  was ever observed working across the bridge.
- **Transport gotcha worth knowing as a user:** with the USB-C cable plugged in the
  board runs wired and the receiver still enumerates but has nothing behind it.
  Aether therefore always prefers the wired entry when both are attached. If you
  ever test something over the dongle, unplug the cable or you will get a false
  negative.

**Alt PID `0x80B2`.** The vendor driver lists a second PID with the same product
name, a second hardware revision. There is no capture from it, so it is
identity-only: recognised and named, protocol `null`, everything off. The
`80A1`-versus-`80A2` lesson applies verbatim, so same product name does not get
promoted to same protocol without its own capture.

**What would still help, none of it blocking**

1. If you happen to have the `0x80B2` revision, a capture from it.
2. A dead-zone change made through the vendor app **over the dongle**, captured.
   That single write is the only thing keeping wireless dead zone gated.
3. Colours in fixed-colour modes: a byte that had been assumed constant turned out
   to be the colour mode selector, which means user-chosen colours were likely
   being ignored in fixed-colour modes before the fix. If anything still looks
   wrong there on your unit, say so and it gets looked at directly.

<!-- paste the shared "Getting the bytes" block here if 1 or 2 are being attempted -->

---

## Issue #7 — Aula win68 HE Max (`1CA2:1901`)

Contributor: hallbyte. This supersedes `docs/HALLBYTE_REPLY_DRAFT.md`, which is
still accurate about the device-log dead end but predates this cycle's registry
work. Registry: slug `aula-win68he-max`, `protocol: null`, all capabilities
`false`, `offerInUi: false`, `status: planned`.

### Text to post

Status for the WIN 68 HE MAX, `1CA2:1901`. Still **identification and layout only**.
The protocol is undecoded, so lighting and actuation stay off and the board is not
offered as a selectable option in the app. What does work: Aether detects it, names
it, and draws the 65% layout from your photos, and it is listed under "Recognised,
but not drivable yet" so the app explains itself instead of going quiet.

**Please read this part, the naming is genuinely misleading.** An entry called
"Aula WIN 68 HE" was added this cycle and it is **not your board**. That one is
`2E3C:C365`, the same USB identity as the Aula Win60 HE, told apart only by USB
product string. Yours is `1CA2:1901`, a different vendor and a different controller
family. Nothing from that work reaches your keyboard. Separately, your layout file
is currently reused as a placeholder drawing for a few unrelated 68-key entries
from another vendor's driver list, which is a placeholder for the picture only and
implies nothing about protocol.

**About the log you posted earlier:** that was `edge://device-log`, and that surface
only records OS-level hardware events. It does not echo WebHID calls by design, so
`sendReport` lines will never show up there no matter what the driver is doing.
That is a dead end in the tool, not a mistake on your side, and it is why the
capture instructions below start with the console wrapper instead.

**What is needed:** one capture of what AULA HUB (or the `magnet` web driver) sends
when you change a single setting. Setting one solid colour is enough to start.

Your board and the Win60 HE Max in #5 share vendor `1CA2` and the same product
line, so one capture from either of you may well unblock both. That is a hypothesis
worth stating, not a promise: the two boards are driven through different web
portals, and same-vendor inferences have been falsified four separate times on this
project.

The photos and screenshots you already posted confirmed the layout is right. The
protocol bytes are the only thing missing.

<!-- paste the shared "Getting the bytes" block here -->

---

## Issue #8 — Aula F75 Tri-Mode (`258A:010C`)

Registry: slug `aula-f75-tri-mode`, `protocol: null`, all capabilities `false`,
`offerInUi: false`, `status: planned`, layout `ui/layouts/aula-f75.json`.

### Text to post

Status for the F75 Tri-Mode, `258A:010C`. **Identification and layout only**, and
that is unchanged this cycle. Aether detects the board, names it, draws its 75%
layout, and lists it under "Recognised, but not drivable yet". The protocol is
undecoded, so lighting and actuation are switched off and the board is not offered
as a selectable option in the app.

**One clarification, because an entry with your board's name appeared this cycle.**
A board called "AULA F75 HE" was added at `38A6:2729`, read out of another vendor
driver's device list. It is a different silicon family from your `258A:010C`
tri-mode board and it is identity-only itself, with no capture and nothing driven.
Your layout file is being reused as its placeholder drawing, which is about the
picture on screen and nothing else. Likewise a dongle PID (`0C45:FEFE`) is shared
by several MINI and F75 receivers in that other family; it is not your board's
receiver.

**What would help, concretely**

1. The name and download link of the app you use to control the board today, plus
   whether it is a website or a native application.
2. Which mode you use it in. Tri-mode boards usually only accept configuration over
   one transport, and on another board here the receiver went completely hollow the
   moment the USB cable was connected, which produced a spurious "no protocol"
   result. **Capture over the USB cable first**, and mention which mode the board
   was in.
3. One capture of a single setting change. Solid colour is the easiest.

<!-- paste the shared "Getting the bytes" block here -->

---

## Reviewer checklist before posting

- [ ] Confirm which issues are actually open. #1 is recorded as closed as a
      duplicate of #4; skip its section unless it was reopened.
- [ ] Paste the shared "Getting the bytes" block into #3, #4, #5, #7, #8 (and #6
      only if the optional follow-ups are being attempted).
- [ ] Check contributor handles against the live issues. Only Mema133 (#3) and
      hallbyte (#7) are named in repo docs; the others are unnamed here on purpose.
- [ ] Confirm no reply promises a date. There are none in this draft; keep it that
      way.
- [ ] Confirm no reply describes a layout-and-identity-only board (#1, #4, #5, #7,
      #8) as supported.
