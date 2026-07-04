---
name: aula-win60-he-pro-sayo-protocol-capture
description: Decode of the SayoDevice HID protocol for the Aula WIN 60 HE Pro (8089:0009), from the issue-#3 USBPcap captures + reference script
metadata:
  node_type: memory
  type: project
---

GitHub issue #3 board: **Aula WIN 60 HE Pro**, VID:PID `8089:0009`, **SayoDevice**
silicon (`CH32V307RBT6`, PCB `SI-2825C-CH32-USB-V1.1`) — a third controller family,
unrelated to the 2E3C (`protocol.py`) and 0C45 (`protocol_sonix.py`) transports.

**Sources** (staged at `docs/context/issue-3-sayodevice-raw/`):
- `rgb.pcapng` — official app setting an RGB effect (14 URBs, 4 config packets)
- `actuation.pcapng` — official app changing an actuation setting (~110 config packets)
- `KBblindtestV3EN.pyw` — working third-party script; its `_build_hid_v2_packet`
  (lines 142-161) gave the packet framing + checksum formula, which we then
  verified against every captured packet.

## Packet framing ("SayoDevice HID v2") — CONFIRMED against both captures

```
[0]=Report ID  [1]=echo  [2..3]=checksum LE16  [4..]=TLV commands, zero-pad to packet size
TLV: [0..1]=length LE16 (incl. 4-byte header)  [2]=cmd  [3]=index  [4..]=data (pad to /4)
checksum = sum of all 16-bit LE words of the packet with [2..3] zeroed, & 0xFFFF
```
Interfaces (script lines 116-138): usage page **0xFF12** → Report ID **0x22**,
**1024-byte** packets (what the official app and both captures use); usage page
0xFF11 → Report ID 0x21, 64-byte (management). Echo byte in both captures: `0x12`.
The stored checksum of every captured packet matches the formula.

## Commands seen

| cmd  | meaning | evidence |
|------|---------|----------|
| 0x26 | lighting config, 48-byte blob, index 0 | rgb.pcapng frames 19, 23 |
| 0x0D | save to flash, data = `96 72` (0x7296 LE) | rgb frames 21/25, actuation frame 174; script line 292 |
| 0x15 | poll selected key, index=1, data=[key id] | actuation frames 22..234 (data `2f`) |
| 0x1C | per-key analog (actuation) write, **TLV index = key id**, 24-byte payload | actuation frame 128 (index 0x2F) |
| 0x03 | config block r/w (polling rate byte 22, multisampling byte 32/33) | script only, not in captures |
| 0x0E | reboot, data = 0x7296 + `01 FE` | script only |

## Lighting (cmd 0x26) — DECODED (mode byte), golden-tested

Captured 48-byte payload (frame 19):
`00 40 ff MODE 00 00 27 64 | 000000ff 000000ff 000000ff 00000000 | ff00ffff ffff0000 ffff0000 ffff0000 | 00ae ffff 9672 9672`

Frames 19 vs 23 differ in exactly ONE byte: **data[3]**, `01` → `00`, when the user
changed the RGB effect → data[3] = effect-mode selector (checksum changed c849→c848,
consistent). `data[7]=0x64` (=100) looks like brightness and the `RRGGBBAA`-shaped
groups look like a color table, but they never varied in the capture — **unverified**,
replayed verbatim by `protocol_sayo.build_lighting(mode)`.

## Actuation (cmd 0x1C) — FRAMING CAPTURED, FIELDS NOT DECODED

Single write in the capture (frame 128), key index 0x2F (47), payload:
`a2 78 03 00 a2 78 74 28 50 02 00 00 d0 07 2c 01 e7 00 0a 0f 82 00 82 00`

Plausible LE16 values inside: `0x07D0`=2000, `0x012C`=300, `0x00E7`=231, `0x0082`=130
— candidate travel values in 0.001 mm (2.000 mm actuation / 0.30 mm RT?), and
`0x78A2` twice looks like Hall ADC calibration. With only ONE write there is nothing
to diff, so **no field is confirmed**; `protocol_sayo.build_key_analog_raw()` only
supports verbatim replay and the registry keeps `actuation: false`. The steady
stream of cmd-0x15 polls of the same key (0x2F) around the write is the app's live
travel read for the selected key.

## Registry / status

`data/board_registry.json` slug `aula-win60he-pro`: `protocol: "protocol_sayo"`,
`usage_page: "0xFF12"` (was a placeholder `0xFF00`), `lighting: true`,
`actuation: false`, `status: bringup`. Golden tests: `tests/test_protocol_sayo.py`
(all captured packets reproduced byte-for-byte).

## Still needs verification on real hardware / more captures

- Whether cmd 0x26 with a different mode byte actually changes the effect (and
  what modes exist); brightness / color-table offsets need captures where the user
  changes color and brightness one at a time.
- Cmd 0x1C payload field map — needs 2+ actuation captures with different mm values.
- Key-id numbering (0x2F = which physical key?) — needs per-key captures.
- Whether writes require the trailing cmd-0x0D save to take effect.
