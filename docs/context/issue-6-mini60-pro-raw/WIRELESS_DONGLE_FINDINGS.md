# MINI 60 HE PRO over the 2.4GHz dongle (0C45:FEFE) — protocol findings

**Date:** 2026-07-20 · **Method:** WebHID tap (Playwright) on `hub.aulacn.com` with the USB-C
cable UNPLUGGED, so the board ran on its 2.4GHz receiver only.

> ⚠️ The in-page capture buffer was LOST when the wireless link dropped and the app bounced to
> `#/checkDevice`. The frames below were read out of the live tap before that and are transcribed
> verbatim; there is no `webhid-capture-*.json` for this session. Treat them as
> **CONFIRMED-BY-CAPTURE (transcribed)** — real observed bytes, but not re-parseable from a file,
> so golden tests must re-capture or hard-code these literals with this caveat noted.

## Headline: the dongle speaks the SAME protocol, at HALF the frame size

Every frame is **32 bytes** (`len=32`) instead of the wired board's 64, with an identical header
and command set:

```
OUT rid=0 len=32  vid=0x0C45 pid=0xFEFE  AA 11 18 00 00 00 00 00 ...   (config read)
OUT rid=0 len=32  vid=0x0C45 pid=0xFEFE  AA 13 10 00 00 00 01 00 ...   (lighting read)
OUT rid=0 len=32  vid=0x0C45 pid=0xFEFE  AA 17 ...                     (actuation table read)
```

Same `0xAA` magic, same `[1]=cmd`, `[2]=len`, `[3..4]` LE16 offset, `[6]` last-chunk flag.
This is **not** a different protocol — it is `protocol_mini60` with `FRAME_LEN = 32`.

**Why the earlier probe wrongly concluded otherwise:** it sent 64-byte frames. The dongle's
`0xFF60` interface has 32-byte reports, so hidapi truncated the write (`n=33` = 1 report-id +
32 data) and the malformed remainder was never answered. The negative result was an artifact of
the wrong frame size, not an incompatible device.

## Lighting (cmd 0x23) — observed frames

Nine modes clicked in the vendor UI, each producing a 32-byte `0x23` write:

| Mode (vendor English) | byte[8] | byte[16] colorMode |
|---|---|---|
| Static | `01` | `00` |
| Reactive Single | `02` | `00` |
| Starry Sky | `04` | `00` |
| Dynamic Breathing | `07` | `00` |
| Spectrum Cycle | `08` | `01` |
| Ripple Spread | `0F` | `01` |
| Mountain Peaks | `11` | `01` |
| Gentle Rain | `12` | `01` |
| Shuttle | `13` | `01` |

Representative frames:
```
AA 23 10 00 00 00 01 00 01 90 EE 90 FF 00 00 00 00 01 01 00 00 00 AA 55   (Static,   colorMode 0)
AA 23 10 00 00 00 01 00 08 90 EE 90 FF 00 00 00 01 01 01 00 00 00 AA 55   (Spectrum, colorMode 1)
AA 23 10 00 00 00 01 00 13 90 EE 90 FF 00 00 00 01 01 01 00 00 00 AA 55   (Shuttle,  colorMode 1)
```

**Mode bytes are identical to the wired board's table** — `0x01` static … `0x13` shuttle — so the
registry's 20-mode table is correct for both transports.

## byte[16] `colorMode` — RESOLVED, and an earlier conclusion was wrong

This byte was an open question all day. The wired capture showed `01` on *every* frame, and an
early hardware probe that sent `00` appeared to no-op, so it was recorded as "must be 1".

The wireless capture shows **both values**, and they correlate exactly with the mode's nature:
fixed-colour modes send `00`, multicolour/random modes send `01`. That matches the SDK source
(`colorMode = randomColor ? 1 : 0`) precisely.

The wired sample was simply taken while the driver sat in a multicolour mode throughout — a
single-valued sample, not a constant. `build_light()` currently hardcodes this byte to `1`, which
means **user-chosen colours are likely ignored in fixed-colour modes**. It should be derived from
the selected mode (registry `modes[].color === false` ⇒ forced-random ⇒ 1).

## Actuation (cmd 0x27) — CAPTURED on the dongle (second session)

A trip change committed through the vendor UI produced:

```
AA 27 18 D8 03 00 01 00 00 00 00 00 ...            (32 bytes)
   ^^ cmd  ^^ len 0x18 = 24-byte payload            (wired: 0x38 = 56)
         ^^^^^ offset 0x03D8 = 984 LE16
                  ^^ [6] last-chunk flag
```

984 + 24 = 1008 = **0x3F0 — the same actuation table size as wired**. So the table geometry is
identical and only the per-frame chunk differs (24 vs 56), exactly as the 32-vs-64 frame size
implies. A second capture file exists for this session:
`webhid-capture-dongle-2026-07-20.json`.

**The rule that falls out:** `chunk = frameLen - 8`. Wired 64 → 0x38; wireless 32 → 0x18.

## What is NOT yet verified wirelessly
- **Per-key RGB (0x24 / 0x32), macros (0x15/0x25), key table (0x12/0x22)** — not exercised.
- **Which vendor interface** the driver used (`0xFF60` 32-byte is the only plausible one, but the
  tap recorded no collection info because the page opened the device before the tap was installed).
- **Reply framing.** No IN frames were captured (same reason), so reply parsing is assumed to
  mirror the wired `0x55` echo.

## Recommended implementation

Parameterise the frame length rather than forking the module: `protocol_mini60` gains a
frame-size argument (64 wired / 32 wireless) threaded through `_frame`/`to_report`, and the
registry's dongle entry points at the same protocol with a `frameLen: 32` (or equivalent)
declaration. Do **not** copy the module — the command set is provably shared, and a fork would
drift.

Promote `aula-mini60he-pro-24g` to drivable **only for lighting** on this evidence, with
actuation/per-key/macros staying `wip` until each is observed or round-tripped on hardware.
