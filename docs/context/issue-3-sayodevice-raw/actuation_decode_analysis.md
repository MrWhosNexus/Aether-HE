---
name: aula-win60-he-pro-actuation-decode
description: Decoded 24-byte cmd-0x1C payload for SayoDevice Aula boards, from the 0.4mm/2.0mm diff pair (#3 issue-3 follow-up)
metadata:
  node_type: memory
  type: project
---

# SayoDevice per-key analog payload -- DECODED (with caveats)

Captures attached to GitHub issue #3 on 2026-07-06 by Mema133:

- `actuation_0.4mm.pcapng` -- user dragged the actuation slider from 1.0 mm down to 0.4 mm; key 0x2F (47)
- `actuation_2.0mm.pcapng` -- user set actuation to 2.0 mm; key 0x2F (47)

Both captures also include a write for key 0x30 (48), which appears to be the actuation-save (mirror)
write the official app sends whenever you commit. It tracks key 0x2F.

## Field map -- DECODED, golden-tested

The 24-byte cmd-0x1C payload decodes as follows (LE16 = little-endian uint16):

| Bytes | Meaning | Notes |
|---|---|---|
| 0-1 | unknown (LE16; ~33901 in new, ~30882 in original) | likely per-key Hall calibration top; do NOT touch |
| 2-3 | unknown (LE16; always 3) | mode or revision; do NOT touch |
| 4-5 | unknown (LE16; ~33899 in new, ~30882 in original) | likely per-key Hall calibration top |
| 6-7 | unknown (LE16; 40598 in new, 10356 in original) | likely per-key Hall calibration bottom |
| 8-9 | unknown (LE16; always 592 = 0x0250) | fixed or mode flag |
| 10-11 | unknown (LE16; always 0) | reserved |
| **12-13** | **press actuation (LE16, in 0.001 mm)** | **DECODED** -- 400 = 0.4 mm, 2000 = 2.0 mm |
| **14-15** | **release actuation (LE16, in 0.001 mm)** | **DECODED** -- tracks press in fixed mode; diverges in RT |
| 16-17 | unknown (LE16; always 231 = 0x00E7) | fixed; do NOT touch |
| 18-19 | unknown (LE16; always 3850 = 0x0F0A) | fixed; do NOT touch |
| 20-21 | unknown (LE16; 100 in fixed mode, 130 in RT) | possibly sensitivity or RT hysteresis |
| 22-23 | unknown (LE16; 400 in fixed, 130 in RT) | possibly sensitivity or RT hysteresis |

Bytes 0-7 look like per-key Hall-effect ADC calibration top/bottom pairs (the two captures use
different values because the user calibrated the board between the two sessions). Bytes 8-11 and
16-19 are constant across captures -- they are part of the payload schema, not user-settable.

Bytes 20-23 flip between modes:
- Fixed actuation: bytes 20-21 = 100 (0x0064), bytes 22-23 = 400 (0x0190)
- RT mode (original capture): bytes 20-21 = 130 (0x0082), bytes 22-23 = 130 (0x0082)

This is consistent with mode-related metadata. For v0.3.x the app only needs fixed mode (Rapid Trigger
is a separate, harder task -- defer).

## What changes when the user drags the slider (0.4mm capture progression)

Only bytes 12-15 (press/release) and bytes 22-23 change as the user moves the slider. Bytes 0-11,
16-21 stay constant. Confirms the field map.

| Pkt | Bytes 12-15 | Meaning |
|---|---|---|
| 390  | `e803 e803` | 1.0 mm / 1.0 mm |
| 685  | `e803 e803` | 1.0 mm / 1.0 mm (byte 22-23 flipped to 0x0190 mid-drag) |
| 1115 | `e803 9001` | 1.0 mm / 0.4 mm (mid-drag, asymmetric) |
| 1415 | `9001 9001` | 0.4 mm / 0.4 mm (settled) |

## Recipe for `protocol_sayo.build_key_analog(key_idx, press_mm, release_mm=None, calibration=None)`

The builder needs to:

1. Start from a captured payload (the new-capture default `6d8403006b84969e50020000 0000 0000 e7000a0f 64009001` for fixed mode).
2. Override bytes 12-13 with `press_mm * 1000` as LE16, and bytes 14-15 with `release_mm * 1000` as LE16.
3. If `release_mm is None`, copy press_mm into bytes 14-15 (fixed-mode behavior).
4. Bytes 0-11, 16-23 stay verbatim -- they are either per-key calibration (bytes 0-7) or constant schema
   bytes (8-11, 16-23). The app does not have its own calibration, so use the new-capture default for v1.
5. Keep the existing 24-byte length guard; verify the resulting packet matches a captured one for at
   least one (key, press_mm, release_mm) triple.

## Still needs verification (future work, not v0.3.x)

- Whether RT mode (cmd-0x1C with press != release) writes require the trailing cmd-0x0D save.
- What bytes 22-23 mean in RT mode; the RT field map is still unverified beyond "100 = fixed, 130 = RT".
- Why Mema133's in-app capture shows "total report 0" (likely MI_00 boot protocol grabbed by OS keyboard
  class driver -- see the issue-#3 reply thread for the Wireshark workaround).
- Whether different keys use different bytes 0-7 (the new captures only cover keys 0x2F and 0x30, both
  show 0x846D / 0x846B / 0x9E96 -- could be coincidence or a contiguous key pair; needs per-key captures
  to confirm).