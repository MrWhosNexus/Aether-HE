# Board layouts

Per-board `keymap.json` files. Each file carries a `_meta` block (board, VID/PID,
protocol family, provenance, status). The live app still loads `ui/keymap.json`
for the default board; the registry (`data/board_registry.json`) points other
boards at files here.

**`index` semantics:** a key's `index` is the **firmware per-key index** — the
value the board's per-key protocol paths address actuation/RT, remap, and LED
tables with. It is NOT a universal constant across protocol families:

- **Win60 family** (`protocol.py`, hed.aulacn.com boards): stride-22 matrix,
  `index = row*22 + col`, Esc = 22. Verified on hardware for the Aula Win60 HE.
- **HFD family** (`protocol_mini60`, hub.aulacn.com boards): stride-16 matrix
  `keyValue`, Esc = 0. One keyValue indexes every 126-slot per-key table
  (key/FN remap ×4 B, actuation/RT ×8 B, custom LED ×4 B).

Never carry indices from one family to the other — that exact mistake shipped
fabricated Win60 indices in the old `aula-mini60he-pro.json` scaffold and would
have sent actuation settings to the wrong keys.

## Index status legend

- **VERIFIED** — indices proven against ground truth: either round-tripped on
  hardware, or extracted from the vendor's own SDK table AND cross-confirmed by
  a wire capture.
- **PROVISIONAL** — best available data (vendor config or carried-over
  hypothesis); must be confirmed from per-key travel reports at bring-up before
  lighting/actuation will address the right keys. Files with
  `provisionalIndices: true` fall here.

## Files

| File | Board | VID:PID | Size | Indices | Source |
|------|-------|---------|------|---------|--------|
| `aula-mini60he-pro.json` | Aula MINI 60 HE PRO (wired) | 0C45:80A2 | 60% | **VERIFIED** | vendor SDK layout array `o` + master map `y` (`docs/context/issue-6-mini60-pro-raw/driver_src/HFD-D07mGRx8.js`), cross-confirmed by `webhid-capture-2026-07-20.json` (the 61 populated actuation slots match exactly). Regenerated 2026-07-20 — replaces the fabricated stride-22 scaffold. |
| `aula-win60he-si2825heargb.json` | Aula WIN 60 HE (`SI2825HEARGB`) | 2E3C:C365 | 60% | **VERIFIED** | vendor config `docs/context/hed-aulacn-raw/driver_src/config__keys__SI2825HEARGB.json`; data-identical to the live, hardware-verified `ui/keymap.json`. |
| `aula-win60he-si2825kzheargb.json` | Aula WIN 60 HE (`SI2825KZHEARGB`) | 2E3C:C365 | 60% | **VERIFIED** | vendor config (byte-identical to the SI2825HEARGB file). |
| `aula-win68he-si2828heargb.json` | Aula WIN 68 HE (`SI2828HEARGB`) | 2E3C:C365 | 65% | PROVISIONAL | vendor config `config__keys__SI2828HEARGB.json` — authoritative source, not yet round-tripped on hardware. Adds Ins/Del/PgUp/PgDn + arrows, drops Menu, R-Shift moves 100→101. |
| `aula-win68he-si2828kzheargb.json` | Aula WIN 68 HE (`SI2828KZHEARGB`) | 2E3C:C365 | 65% | PROVISIONAL | vendor config (byte-identical to the SI2828HEARGB file). |
| `aula-kp-te153-si2851ukkzheargb.json` | Aula KP-TE153 (`SI2851UKKZHEARGB`) | 2E3C:C365 | 65% ISO (UK) | PROVISIONAL | vendor config `config__keys__SI2851UKKZHEARGB.json` — UK ISO: tall Enter at index 58, Non-US `#` (79), IntlBackslash (89), IntlRo (99), `type: "uk"`. |
| `aula-mini60he-max.json` | Aula MINI60HE Max | 0C45:80A1 | 60% | PROVISIONAL | scaffold from issue #4 (+#1 dup); Win60-carryover indices. |
| `aula-win60he-max.json` | Aula Win60 HE Max | 1CA2:1902 | 60% | PROVISIONAL | scaffold from issue #5; Win60-carryover indices. |
| `aula-win60he-pro.json` | Aula WIN 60 HE Pro (SayoDevice) | 8089:0009 | 60% | PROVISIONAL | scaffold from issue #3; Win60-carryover indices. |
| `aula-win68he-max.json` | Aula win68 HE Max | 1CA2:1901 | 65% | PROVISIONAL | scaffold from issue #7; standard ANSI 65% guess — verify against issue photos at bring-up. |
| `aula-f75.json` | Aula F75 Tri-Mode | 258A:010C | 75% | PROVISIONAL | scaffold from issue #8. |

All files pass `python tools/validate_keymap.py ui/layouts/*.json` and are
covered by `tests/test_layouts.py` (slot sets, HID anchors, vendor-verbatim
checks).

## The VID/PID collision (WIN 60 vs WIN 68 vs KP-TE153) — REGISTRY GAP

Every hed.aulacn.com board above reports the **same VID 0x2E3C / PID 0xC365**.
The vendor driver tells them apart **only by USB product string**
(`SI2825HEARGB`, `SI2828HEARGB`, `SI2825KZHEARGB`, `SI2828KZHEARGB`,
`SI2851UKKZHEARGB` — see `docs/context/hed-aulacn-raw/driver_src/config__device.json`).

Aether's registry (`data/board_registry.json` / `boards.py`) currently keys on
(VID, PID) alone, so **it cannot distinguish these boards**: a WIN 68 HE (65%)
owner plugging in today matches the `aula-win60-he` entry and silently gets the
60% keymap — per-key writes to the 7 extra keys are impossible and R-Shift
(index 101 on the 68) would be addressed as 100. The registry needs a
product-string discriminator before the SI2828/SI2851 files can be
auto-selected. (Registry change is owned elsewhere — do not wire these files in
from here.)

## Geometry

`x/y/width/height` are drawing coordinates preserved from each file's source:
the hed imports and Win60-derived scaffolds use the Win60 grid (35 px keycap,
38 px pitch); `aula-mini60he-pro.json` uses the HFD vendor grid (50 px keycap,
55 px pitch). Scales are internally consistent per file; consumers must not
assume one global pixel scale across files.
