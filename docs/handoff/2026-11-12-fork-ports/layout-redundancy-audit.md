# Layout, drivability and redundancy audit (Agent C)

Scope: every board in `data/board_registry.json` at `origin/main` `f38e69a` (v0.6.5) except the WIN 68 HE Max and F75 HE ports. Read-only; nothing was edited, committed or pushed.

## How this was checked, and what was not

- **Vendor key tables are not in main** (`/research/` is git-ignored). I diffed against the owner's local copies in `~/aether-macos/docs/context/hed-aulacn-raw/driver_src/config__keys__*.json`.
- **Issue attachments were not downloaded** (#20, #25, #4, #3). Downloading needs the owner's go-ahead. The #20 check uses the copy pinned in `tests/test_layouts.py:314-336` and `tests/test_keymap_by_name.py:39-48`.
- `device_state.KeyMap` and `Api._ui_layout` were executed against every layout file. No test suite was run.
- The MINI60HE Max finding rests on the golden frames in `tests/test_protocol_sonix.py`, not on the original #4 capture.

## 1. Layout audit

| Board (slug) | Layout file | Keys | Verdict |
|---|---|---|---|
| aula-win60-he | `ui/keymap.json` | 61 | CORRECT |
| aula-win68-he | `aula-win68he-si2828heargb.json` | 68 | CORRECT |
| aula-kp-te153 | `aula-kp-te153-si2851ukkzheargb.json` | 69 | File CORRECT vs vendor; on-screen drawing WRONG |
| aula-mini60he-pro (wired) | `aula-mini60he-pro.json` | 61 | CORRECT |
| aula-mini60he-pro-24g | same file | 61 | CORRECT (same keyboard) |
| aula-mini60he-pro-80b2 | same file | 61 | UNVERIFIABLE (no capture from this PID) |
| aula-mini60he-max | `aula-mini60he-max.json` | 61 | WRONG (indices) |
| aula-mini60he-max-24g | same file | 61 | WRONG (inherits the above) |
| aula-win60he-max | `aula-win60he-max.json` | 61 | UNVERIFIABLE, indices probably wrong |
| aula-win60he-pro (Sayo) | `aula-win60he-pro.json` | 61 | UNVERIFIABLE (indices) |
| aula-mini68he / -pro / -max | `aula-win68he-max.json` (placeholder) | 68 | WRONG (wrong family's indices) |
| aula-f75-tri-mode | `aula-f75.json` | 81 | WRONG |

### CORRECT

**WIN 60 HE.** `ui/keymap.json` is key-for-key identical to vendor `config__keys__SI2825HEARGB.json` (61 keys, index, code, HID, x/y/size, order). Stride 22 holds (Esc = 22). All 61 map by name.

**WIN 68 HE Standard — the PR #31 fix holds.**
- The layout is identical to vendor `config__keys__SI2828HEARGB.json` on all 68 keys, and to the #20 table pinned in the tests (index, code, HID).
- All 65 indices that produced travel frames in the #20 capture are in the layout and get a design code.
- `KeyMap` now maps all 68 by name (`device_state.py:41-72`): Tab = 44, Q = 45, A = 68, D = 70, Ins = 38, Del = 60, R-Shift = 101, Fn = 121, R-Ctrl = 122, arrows 103/124/125/126.
- `_ui_layout()` returns "68", and `KB_ROWS_68` (`ui/runtime_src/src/keyboard.jsx:42-69`) matches the vendor row order, including R-Alt, Fn, R-Ctrl after Space.
- Still unconfirmed on hardware: the three arrow keys below Up (124-126) were not pressed in the #20 capture.

**MINI 60 HE Pro, wired and dongle.** The 61 indices are exactly the 61 populated actuation slots in `docs/context/issue-6-mini60-pro-raw/webhid-capture-2026-07-20.json` (I reassembled the `AA 27` table: 1008 bytes, 61 non-empty records). Row order matches `HFD_SDK_DECODE.md:492-496`, including the bottom row 84, 86, 87, 85 (Fn rightmost). Sharing one file between the two transports is legitimate.

### WRONG

**KP-TE153 (ISO, 69 keys) — the drawing, not the file.**
- The file matches vendor `config__keys__SI2851UKKZHEARGB.json` on all 69 keys, and all 69 map by name.
- The board has **Home** at index 38 where the WIN 68 has Ins. `_UI68_CODES` requires `Ins` (`app_web.py:858-865`), so `_ui_layout()` returns **"60"**.
- Result: the 61-key Win60 drawing is shown. Ten keys cannot be selected at all: Home, Del, PgUp, PgDn, four arrows, IntlBackslash (89), IntlRo (99).
- The drawing also shows Menu and `/?`, which this layout does not have.
- The `\|` key drawn above Enter addresses index 79, which is physically the `#~` key on the home row.
- Fix spec:
  1. Add a `KB_ROWS_69_ISO` row set in `keyboard.jsx`: Home at top right, ISO Enter spanning rows 2-3 at index 58, `#~` (code `Bsl`, index 79) left of Enter, short L-Shift plus `IntlBsl` (89), `IntlRo` (99) where `/?` sits.
  2. Register it in `LAYOUTS` (`keyboard.jsx:75`).
  3. Make `_ui_layout()` return "69" when `IntlBsl` is present. Better: put an explicit `uiLayout` field in each registry entry instead of inferring from key codes.
- Vendor-table oddity to confirm with an owner: index 99 is `IntlRo` / HID 0x87 (a Japanese key) where a UK board has `/?` (0x38). The table has no Slash key at all. This is either a vendor data error or a real firmware quirk; it changes the SOCD and remap HID for that key.

**MINI60HE Max (0C45:80A1) — indices are the wrong family.**
- The file is a byte-copy of the Win60 key list (stride 22, Esc = 22), labelled "Win60 hypothesis".
- The vendor driver registry lists 80A1 as an HFD board on the 60-key layout `o` (`HFD_SDK_DECODE.md:506-508, 520`), which is stride 16, Esc = 0.
- The #4 golden frames agree: the "single key" actuation write is at table offset 0 (slot 0 = Esc in HFD; no key sits at slot 0 in stride 22).
- Fix spec: point `data/board_registry.json:213` and the dongle entry's `keymap` at `ui/layouts/aula-mini60he-pro.json`, add `0C45:80A1` handling to the layout-identity test (`tests/test_layouts.py:236-262`), and delete `aula-mini60he-max.json`.

**MINI 68 HE / Pro / Max (38A6:2722/2723/2724) — placeholder from another family.** They draw `aula-win68he-max.json` (magnet family, 21 slots per row). These are HFD boards (stride 16). Nothing is driven (protocol null), so the harm is cosmetic today. Fix spec: generate `aula-mini68he.json` from vendor layout array `r` in `HFD-D07mGRx8.js` plus master map `y`, the same way `aula-mini60he-pro.json` was built; the source is in the owner's local `issue-6-mini60-pro-raw/driver_src/`.

**F75 Tri-Mode (258A:010C) — `aula-f75.json`.**
- Index 22 is a second `Esc` / `Escape` / HID 0x29 at the start of the number row. It should be `` `~ `` / `Backquote` / HID 0x35.
- Because of that duplicate code, `design_codes_for` returns None and `KeyMap` falls back to the positional zip (`device_state.py:105-112`): the first 61 of 81 keys get Win60 codes, so F1 reads as "1", F2 as "2", and so on.
- `_ui_layout()` returns "60"; there is no 75% drawing.
- Indices are stride-22 guesses with no evidence.
- Fix spec: change index 22 to Backquote/0x35, add a 75% row set, and replace indices once #8 supplies a capture. The F75 HE agent shares this file and should be told.

### UNVERIFIABLE

**WIN 60 HE Max (1CA2:1902).** Physical 60% ANSI geometry is plausible. Indices are Win60 stride 22, but this is the same vendor and interface as the WIN 68 HE Max (issue #25: "Spark WIN 60 HE MAX", interface 2, usage page 0xFFA0, driver magnet.aulastar.com), whose table uses 21 slots per row. Missing evidence: the magnet key table for 1902.

**WIN 60 HE Pro (Sayo, 8089:0009).** Same 61-key copy. Sayo addresses keys by a "key id" whose numbering is unknown; the only observed id is 0x2F (`docs/context/aula-win60-he-pro-sayo-protocol-capture.md:56, 80`). Missing evidence: actuation writes on two or three named keys.

**MINI 60 HE Pro alt PID 80B2.** Layout presumably identical; no capture from that PID.

### Boards sharing a layout file

| File | Used by | Assessment |
|---|---|---|
| `aula-mini60he-pro.json` | 80A2, FEFE, 80B2 | Correct for the first two; inferred for 80B2 |
| `aula-mini60he-max.json` | 80A1, FEFC | Wrong for both |
| `aula-win68he-max.json` | 1CA2:1901 plus the three MINI 68 boards | Wrong for the MINI 68s |
| `aula-f75.json` | F75 Tri-Mode, F75 HE | Wrong for both (see above) |

## 2. Drivability

| Board | Drivable today | Evidence | Blocker | Smallest unblocker |
|---|---|---|---|---|
| WIN 60 HE | Everything | Captured and hardware-verified | None | — |
| WIN 68 HE | Lighting, per-key RGB, actuation, RT, SOCD, calibration, key stats | Layout and travel captured (#20); owner claims in #12 and #27 that it works | Deadzone, gamepad, macros are "wip"; no settings round-trip | One run of `docs/HARDWARE_TEST_CHECKLIST.md` by a #27 or #20 owner |
| KP-TE153 | Same code path as WIN 68 when plugged in; not offered | Source only | Wrong drawing; SOCD HID remap unverified; no owner | An owner; none has filed an issue |
| MINI 60 HE Pro wired | Everything except calibration and gamepad | Captured and hardware-verified | Calibration "wip" | Calibration capture |
| MINI 60 HE Pro dongle | Same, minus host streaming; deadzone "wip" | Captured and hardware-verified over RF | RF drops host streams (firmware limit) | — |
| MINI60HE Max | Nothing (NullDriver) | Captured (#4) | Wired to the mis-decoded `protocol_sonix`; wrong layout | No new evidence needed for lighting: see section 4. An owner test (#4 volunteered) for the rest |
| MINI60/68HE Max dongle (FEFC) | Nothing | Source only | No capture; usage page varies by model | A handshake capture over the dongle |
| MINI 60 HE Pro 80B2 | Nothing | Source only | No capture | One `0x10` device-info reply from that PID |
| MINI 68 HE / Pro / Max | Nothing | Source only | No capture, placeholder layout | Layout from vendor array `r`; one capture from any of the three |
| WIN 60 HE Max | Nothing | HID dump (#5, #25); in-app capture of 512 travel reports attached to #25 | protocol null, usage page null | The #25 attachment: check it against `protocol_magnet` travel parsing and infer the stride from the three keys pressed. Then set usage page 0xFFA0. Issues #19 and #25 are not linked in the registry (only #5) |
| WIN 60 HE Pro (Sayo) | Nothing (NullDriver), despite `lighting: true` | Lighting captured; actuation framing captured | No driver class; key ids unknown | A `SayoDriver` for lighting only. `Logs.zip` posted on #3 (2026-07-27) has not been looked at. Branch `feat/sayo-actuation-decode` holds an unmerged actuation decode |
| F75 Tri-Mode | Nothing | None | No capture, no HID dump | #8 owner: HID dump plus one "set colour" capture |

## 3. Redundancy

### Layout files

| Path | Why redundant | Safe to remove? |
|---|---|---|
| `ui/layouts/aula-win60he-si2825heargb.json` | Key list identical to `ui/keymap.json`; no registry entry uses it | Yes, with edits to `tests/test_layouts.py:159, 191` and `ui/layouts/README.md:37` |
| `ui/layouts/aula-win60he-si2825kzheargb.json` | Identical to the above; unused | Yes; `tests/test_layouts.py:160`, README:38 |
| `ui/layouts/aula-win68he-si2828kzheargb.json` | Identical keys to the SI2828HEARGB file; unused | Yes; `tests/test_layouts.py:162, 199, 305`, README:40 |
| `ui/layouts/aula-mini60he-max.json` | Win60 copy with wrong indices | Yes, once the registry points at the Pro file |
| `ui/layouts/aula-win60he-max.json`, `aula-win60he-pro.json` | Byte-copies of the Win60 key list | Keep until real tables exist; they are referenced |

### Registry

- No duplicate VID:PID entries. The three MINI 68 entries, `aula-f75-he` and `aula-mini60he-max-24g` are identity-only, source-only placeholders; keep them only if "recognised but not drivable" is wanted.
- `aula-win60he-pro` advertises `lighting: true` and status "bringup" while its driver is `NullDriver` (`drivers/__init__.py:16`).

### Superseded protocol helpers

- `protocol_sonix.py` — a mis-parse of the HFD protocol (section 4). Referenced by `boards.py:17`, `drivers/__init__.py:13`, `drivers/base.py:392`, both `.spec` files, the flatpak manifest, `tests/test_protocol_sonix.py`, `tests/test_boards.py`, `tests/test_drivers.py`, `tests/test_packaging.py`. Remove only together with repointing 80A1 to `protocol_mini60`.
- `protocol_win60_advkeys_wip.py` — imported only by its own test. Keep if the advanced-keys decode is still planned; otherwise dead.

### Legacy code at the repo root

- `main.py` (41 KB), `keyboard_widget.py`, `theme.py` — the old CustomTkinter UI. `CLAUDE.md:19` calls it legacy; nothing in the packaged app imports it. Safe to remove with the `customtkinter` note in `requirements.txt:33`.
- `cycle_modes.py`, `play_effect.py`, `capture_analog.js` — standalone dev scripts, referenced only from docs. `capture.sh` is asserted by `tests/test_packaging.py`; check before removing.
- `AETHER_WIRING_AUDIT_PROMPT.md`, `PHASE_3_OPUS_HANDOFF_PROMPT.md` — one-off agent prompts. The first has no references; the second is referenced only by `agents/handoffs/implementer-2026-09-27-0400.md`.
- `design_handoff/` (15 MB) — contains the same 5.4 MB manual PDF twice (`AULA_WIN60_HE_Series_Manual.pdf` and `-2af1f602.pdf`, byte-identical) plus scratch screenshots. Referenced only from two docs.
- `docs/HALLBYTE_REPLY_DRAFT.md`, `docs/ISSUE_REPLIES_DRAFT.md` — reply drafts; no code references.
- `docs/context/hed-aulacn-raw/deobf.py` and both `unpack_driver.py` copies — operate on vendor files that are no longer in the repo.

### Stale docs that contradict current behaviour

- `ui/layouts/README.md:52-65` "REGISTRY GAP": says the registry cannot tell the 2E3C:C365 boards apart. It can, since the product-string discriminator.
- `ui/layouts/README.md:45`: calls the WIN 68 HE Max layout a "standard ANSI 65% guess"; PR #31 replaced it with the vendor table. Line 39 still says the WIN 68 file is not corroborated.
- `_meta.note` in the SI2825HEARGB, SI2825KZHEARGB, SI2828KZHEARGB and KP-TE153 files repeats the same obsolete "registry keys on (vid,pid) alone" warning.
- `_meta.provenance` in all five hed files, and the README, cite `docs/context/hed-aulacn-raw/driver_src/...`, which is not in the repo.
- `HFD_SDK_DECODE.md:488` says "62 keys"; the table and the layout have 61.
- `device_state.py:25-27, 97` comments still say keys are aligned "by physical position".
- `protocol_mini60.py:60-63` says "the Max used big-endian"; see section 4.

### Tests that test nothing, or the wrong thing

- `tests/test_layouts.py:165-173` `test_hed_imports_match_vendor_configs_verbatim` — always skips: it looks in `research/vendor-reference/`, which is git-ignored and absent in CI. The vendor-fidelity guarantee is unenforced everywhere but the maintainer's machine.
- `tests/test_layouts.py:264-310` `test_design_code_alignment_is_total_only_at_exactly_61_keys` — the docstring describes the positional zip that PR #31 replaced; the assertions only pin key counts.
- `tests/test_protocol_sonix.py` — pins a mis-decoded record layout byte-for-byte.
- `tests/test_layouts.py:309-311` — an `if __name__ == "__main__"` block sits in the middle of the file with tests defined after it.

### Remote branches on origin

Fully merged (0 commits ahead, `git cherry` empty), safe to delete:

- `claude/dazzling-turing-fdbei6`
- `claude/eager-einstein-c745de` (PR #31)
- `claude/quirky-pascal-k6poog`
- `feat/auto-update-on-launch` (PR #11)
- `feat/macos` (PR #32)
- `feature/board-submission-form`
- `feature/multi-board-support`
- `fix/actuation-fnlayer-traveltest-and-flatpak`
- `fix/reconnect-and-actuation-keyboard`

Not merged: `feat/sayo-actuation-decode` (2 commits, 2026-07-06): a cmd-0x1C actuation decode and a `protocol_adapter.py` that predates the driver layer. The decode is worth porting; the adapter is superseded by `drivers/`.

## 4. Anything new

1. **The MINI60HE Max almost certainly speaks `protocol_mini60`.** `protocol_sonix` reads the payload from byte 9 as big-endian with a "truncated 7th record". Read from byte 8 as little-endian, the #4 frames are seven whole HFD records: flags 1, trip 1.70 mm, RT 2.00/2.00, and the "mode 0x43" record is trip 0.67 mm, RT 0.50/0.80. `protocol_mini60.build_light(mode, color_mode=flag)` reproduces all the #4 lighting golden frames byte-for-byte (I ran three of five). The vendor driver lists 80A1 as the same protocol. The "falsified on hardware" note describes the mis-parse failing on the Pro, not a different protocol. This still needs a test on a real Max before it is offered.
2. **The KP-TE153 shows the 60% drawing**, so ten of its keys cannot be configured.
3. **The Sayo board's lighting is advertised but has no driver.**
4. **The WIN 60 HE Max has usable evidence sitting in issue #25** (same 0xFFA0 interface as the WIN 68 HE Max, plus an in-app capture). The registry links only #5.
5. **The F75 layout has two Esc keys**, which silently breaks key mapping for both F75 entries.
6. **Layout fidelity is not enforced in CI** (the vendor comparison always skips).
7. Other open board requests with no registry entry: #21 HERO 84 HE, #23 HERO 68 HE, #22 F75 Pro, #24 DAREU EK60 HE, #28 Madlions Nano68 Pro. Issue #22 could not be read (connection reset).
