# Fork review: `xpLayA/main` (9a70ec6, base 99bee57)

Reviewed read-only against `origin/main` @ f38e69a. No fork code was built or run. Upstream's own
`protocol_mini60.py` was run (isolated, `python -I`) to compare golden vectors.

## 1. Summary

- The fork proves, with raw hardware read-backs committed as fixtures, that the **AULA F75 HE
  (38A6:2729) speaks upstream's existing `protocol_mini60` unchanged**: interface 2, usage page
  0xFF68 / usage 0x61, no report ID, 64-byte frames. No new protocol code is needed upstream; the
  port is a registry entry, a real 80-key layout, fixtures and tests.
- Evidence is **not a vendor capture**. It is the fork author's own probe scripts plus the reply
  bytes they saved. Under upstream policy that is an owner claim (with artifacts), so it ports
  behind an experimental flag, not as "supported".
- `protocol_mini60.py` and `drivers/mini60.py` are byte-identical in base, fork and `origin/main`
  (same blob IDs), so the fork's 183 "golden" frames match upstream trivially. They are a snapshot
  of upstream's own builders, not independent evidence.
- One find is capture-backed by upstream's own data: battery level and work mode in the 0x10 reply
  over the 2.4 GHz dongle. Upstream does not parse it.
- No malicious code found. The fork deletes upstream's workflows and relabels the tree GPL; upstream
  has since adopted GPL-3.0-or-later itself, so the F75 additions are licence-compatible (credit xpLayA).

## 2. Item table

| # | Item | Fork file:line | Upstream status | Evidence | Value | Risk | Recommendation |
|---|---|---|---|---|---|---|---|
| 1 | F75 HE wired identity + transport: 38A6:2729, if 2, usage page 0xFF68/0x61, 64-byte frames, `protocol_mini60` | `legacy/python/data/board_registry.json:423-592`; `data/boards/aula-f75-he/board.json`; `docs/boards/aula-f75-he.md` | PARTIAL: identity-only, `protocol: null`, `usage_page: null` (`data/board_registry.json:424-438`) | owner-claim with fixtures (`fixtures/f75/backup.json`: 0x10 reply reports 38A6:2729, fw V1.55) | high | Writes to a board no maintainer owns | PORT-EXPERIMENTAL: `bringup`, not offered, flag-gated |
| 2 | F75 HE key layout, 80 keys, stride-16 firmware indices (Esc 0, F1-F12 1-12, rows at 16/32/48/64/80, Back 92, Enter 76, `\` 60, Del 106, PgUp 105, PgDn 108, End 107) | `legacy/python/ui/layouts/aula-f75he.json` (same index set as `data/boards/aula-f75-he/layout.json`) | MISSING: upstream draws the F75 HE with the Tri-Mode placeholder `ui/layouts/aula-f75.json` (81 keys, provisional indices) | source-only (vendor layout array `t`) **plus** fixture cross-check: 67 of 68 non-F-row keys have the matching HID usage at that slot in the board's 0x12 key table | high | Low; drawing only until item 1 is enabled | PORT: replaces a known placeholder |
| 3 | F75 hardware fixtures (0x10/0x13 replies, 0x17/0x12/0x14/0x11/0x18 tables, dongle 0x10 reply, BT report descriptor) | `fixtures/f75/*` | MISSING | owner-claim (raw data) | med | None (data) | PORT as `tests/fixtures/f75/` |
| 4 | Battery + work mode in 0x10 reply: payload[16] work mode (02 = wireless), [17] battery %, [18] charging (1 or 2) | `crates/aether-proto/src/lib.rs:294-301`; `fixtures/f75/dongle_info.json` | MISSING: `protocol_mini60.py:652-664` parses VID/PID only; offsets are listed SOURCE-ONLY in `HFD_SDK_DECODE.md` §3 | **captured**: upstream's own `webhid-capture-dongle-handshake.json` 0x10 reply carries `02 64 00` at payload 16-18; F75 fixture shows the same | med | Wired value is junk (0x10 at [17] in the wired capture); must be dongle-only | PORT (parser + dongle-only display) |
| 5 | F75 2.4 GHz receiver: 0C45:FEFE, product string "AULA F75 HE Dongle", if 3, 0xFF60, 32-byte frames; tables round-trip; 0x32 host stream acked but never shown | `data/boards/aula-f75-he/board.json` (`links`, `wireless_capabilities`); `docs/boards/aula-f75-he.md` | MISSING as an entry. Upstream has the same transport for the MINI (`aula-mini60he-pro-24g`, `data/board_registry.json:292-361`) and the same "no host streaming over RF" rule | owner-claim with one fixture | med | Shared PID: must be discriminated by `productString` | PORT-EXPERIMENTAL, same flag as item 1 |
| 6 | Bluetooth LE has no vendor collection (typing + GATT battery only) | `fixtures/f75/bt_report_descriptor.txt`; `docs/boards/aula-f75-he.md` | MISSING | owner-claim (descriptor dump) | low | None | PORT as a registry `_note` only |
| 7 | Behaviour notes: (a) 0x13 read-back colour is stale after a 0x23 write, restore from the saved block; (b) all-zero 0x17 table is the factory state; (c) F1-F12 base key records are empty; (d) 0x66 travel test acks but streams nothing | `docs/protocols/hfd.md`; `fixtures/f75/README.md`; `crates/aether-proto/src/lib.rs:318` | MISSING for the F75 | owner-claim | med | (d) means live travel must stay off for the F75 | PORT as registry `_note`s; no code |
| 8 | Golden frame snapshot for `protocol_mini60` (183 frames, 64-byte) + generator | `crates/aether-proto/tests/golden/mini60.json`; `legacy/python/tools/dump_golden_mini60.py` | HAVE (stronger): `tests/test_protocol_mini60.py` rebuilds vendor captures byte for byte | none (self-generated from upstream's code) | low | Tautological; adds churn | SKIP. Verified: all 183 frames equal upstream's current builders |
| 9 | New Win60 golden vectors | none in the fork | n/a | n/a | n/a | n/a | Nothing to port. The fork adds no Win60 test data |
| 10 | Updater kill switch `UPDATES_ENABLED = False` | `legacy/python/version.py:20`; `legacy/python/app_web.py:1790,1821` | MISSING (by design) | n/a | low | Would disable upstream's updater | SKIP: fork-specific |
| 11 | Test path fixes after the move (`parents[3]`, `../..`), `test_boards.py`/`test_drivers.py` promoting F75 to captured/offered | `legacy/python/tests/*` | n/a | n/a | low | Contradicts policy (see §4) | SKIP the path edits; rewrite the F75 assertions per §3 |
| 12 | udev rules for 38a6:2729 and 0c45:fefe | `packaging/70-aether.rules` | MISSING: `99-aula.rules` covers only 2e3c:c365 | n/a | med (Linux users cannot open the board without it) | Grants seat-user hidraw access, same as the existing rule | PORT with item 1 |
| 13 | Fn-shortcut table from the paper manual | `data/boards/aula-f75-he/shortcuts.json` | MISSING | owner transcription | low | No UI consumes it upstream | SKIP |
| 14 | Removal of `session_backup.md`, `session_part_1.md`, `session_part_2.md` | deleted in fork | Upstream still ships all three at repo root | n/a | low | See §5 | PORT (delete) |
| 15 | Rust workspace, Slint GUI, CLI, effects, `keys_in.rs` key reader, profiles/backups, `scripts/`, `ci.yml`, docs rewrite, deletion of workflows/installer/Flatpak | `crates/**`, `Cargo.*`, `.github/**`, `README.md`, `CLAUDE.md` | n/a | n/a | n/a | n/a | SKIP: out of scope, upstream stays Python |

Issue #8 is unaffected: it is the mechanical **F75 Tri-Mode (258A:010C)**, a different silicon family.
The fork contains nothing for it.

## 3. Port spec

### 3.1 Layout (item 2): PORT

- **Add** `ui/layouts/aula-f75he.json` from the fork's `legacy/python/ui/layouts/aula-f75he.json`
  (80 keys, `type: us`). Keep its `_meta.provenance`. Change `_meta.indicesStatus` to say:
  "SOURCE-ONLY from vendor layout `t`; cross-checked against a contributor's 0x12 key-table read
  (xpLayA fork fixture), not maintainer-verified". Keep `status: experimental`.
- **Registry**: point `aula-f75-he.keymap` at the new file. Leave `aula-f75-tri-mode` on
  `ui/layouts/aula-f75.json`. Update `ui/layouts/README.md` with a row.
- Known gap to record: slot 85 (Fn) holds usage 0xAF in the firmware table; the layout uses the
  Aether `0xfa` convention. The rotary knob is not modelled. The board's table also populates 30
  slots outside the layout (shared full-size defaults); do not draw them.
- **Guarded by**: `tests/test_layouts.py` (schema, duplicate indices,
  `test_design_code_alignment_is_total_only_at_exactly_61_keys` needs `"aula-f75he.json": 80` added
  to `oversized`).
- **New test**: load `tests/fixtures/f75/backup.json`, and for every layout key outside F1-F12 and
  Fn assert key-table record `index*4` is `[02, 00, hidCode, 00]`; assert records 1-12 are empty.

### 3.2 Fixtures (item 3): PORT

- Copy `fixtures/f75/{backup.json, dongle_info.json, light_before.json, act_before.json,
  keytable_before.json, custom_led_before.json, dks_before.json, bt_report_descriptor.txt,
  README.md}` to `tests/fixtures/f75/`. Add a header line to the README: contributor-supplied
  read-backs, 2026-10-21/23, firmware V1.55, not a vendor capture.
- Do not copy `docs/context/f75-bringup/*.py`. They import the fork's layout paths and write to the
  board. Reference them by fork commit in the README instead.

### 3.3 Battery parse (item 4): PORT

- **`protocol_mini60.py`**: add `parse_device_status(reply)` beside `parse_device_info` (line 652)
  returning `{"firmware": reply[16] | reply[17] << 8, "work_mode": reply[24], "battery": reply[25],
  "charging": reply[26] in (1, 2)}`. Offsets are frame offsets (payload + 8). Tolerate the optional
  leading report-id byte the same way existing parsers do.
- **`drivers/mini60.py`**: expose it only when the profile's `frameLen` is 32 (dongle). On the wired
  link return `None`: the wired capture shows 0x10 at payload[17], which is not a percentage.
- **Bridge/UI**: optional; a read-only field on the existing device-info call is enough. Mark the
  charging flag SOURCE-ONLY (both captures show 00; 1/2 comes from vendor JS).
- **Tests** (`tests/test_protocol_mini60.py`): parse the offset-0 0x10 IN frame from
  `webhid-capture-dongle-handshake.json` and assert firmware 0x0153, work mode 2, battery 100;
  parse `tests/fixtures/f75/dongle_info.json` and assert 38A6:2729, 0x0155, battery 100; assert the
  driver returns `None` for a 64-byte profile.

### 3.4 F75 HE drivable entry, wired + dongle (items 1, 5, 6, 7, 12): PORT-EXPERIMENTAL

- **Registry `aula-f75-he`** (`data/board_registry.json:424`): set `usage_page: "0xFF68"`,
  `protocol: "protocol_mini60"`, `frameLen: 64`, `status: "bringup"`, keep `offerInUi: false`.
  Capabilities: `lighting`, `actuation`, `rapidTrigger`, `perKeyRgb` true; `deadzone`, `socd`,
  `remap`, `advancedKeys`, `macros`, `calibration` `"wip"`; `gamepad` false. Copy the `lighting`
  block (modes 1-20, `customModeByte: 20`, `hostEngine: true`, `hostEngineMaxFps: 28`) and the
  `actuation` block (`travelRange [0.1, 3.4]`, `rtRange [0.01, 3.4]`, `deadzoneScope: global`,
  `switches: []`) from the fork entry. Rewrite every "HARDWARE-VERIFIED" in the fork's `_note`s to
  "contributor-reported (xpLayA fork, 2026-10-21), not maintainer-verified". Add the item 7 notes.
- **New registry entry `aula-f75-he-24g`**: `0x0C45:0xFEFE`, `productString: "AULA F75 HE Dongle"`,
  `usage_page: "0xFF60"`, `frameLen: 32`, `protocol: "protocol_mini60"`, `hostEngine: false`,
  `status: "bringup"`, `offerInUi: false`. `boards.py` already resolves shared VID:PID by product
  string (`by_ids`, line 421); confirm the registry loader's "one undiscriminated entry per pair"
  rule still passes.
- **Gate**: follow `_apply_experimental_flags` (`app_web.py:3414`). Add flag `f75`. With the flag
  off, `drivers/__init__.py` must hand both F75 slugs a `NullDriver` (every write raises). With it
  on, they get `Mini60Driver`. Do not add a new driver class. Live travel stays unsupported.
- **Linux**: add the two udev lines from `packaging/70-aether.rules` to `99-aula.rules` (and the
  Flatpak copy if one exists).
- **Docs**: `data/boards.json` keeps the F75 HE under "recognized" with reason "contributor
  round-trip, experimental (`AETHER_EXPERIMENTAL=f75`)"; regenerate the README table. Add a section
  to `docs/HARDWARE_TEST_CHECKLIST.md`.
- **Existing tests to update** (`tests/test_boards.py`): `test_only_captured_boards_are_drivable`
  (line 128) needs an explicit, documented exception for the two F75 slugs, as the fork did, but
  worded as contributor evidence; `test_frame_len_declared_in_raw_registry` (238) add both slugs;
  `test_hfd_sibling_identity_entries_present` (341) drop `aula-f75-he`;
  `test_unsupported_boards_are_never_offered` (733) must stay unchanged (F75 not offered).
- **New tests** (fakes only): flag off gives `NullDriver` for both slugs; flag on gives
  `Mini60Driver` at frame length 64 and 32; the dongle profile refuses host streaming; 0C45:FEFE
  with "MINI 60 HE PRO Dongle" still resolves to the MINI and with "AULA F75 HE Dongle" to the F75;
  a fake transport replaying `tests/fixtures/f75/backup.json` decodes lighting mode 11, brightness
  5, speed 3 and an all-zero actuation table.

### 3.5 Session transcripts (item 14): PORT

Delete `session_backup.md`, `session_part_1.md`, `session_part_2.md` from the repo root and check
that no doc or test references them.

## 4. Conflicts with upstream decisions

- **Promotion to "supported" and offered in the UI.** The fork sets `status: supported`,
  `offerInUi: true` and adds the F75 to the "captured" set on its own round-trips. Upstream policy
  does not record a fork author's result as evidence. Upstream is right on process; the fork's data
  is nevertheless internally consistent (identity reply, key table matching the vendor layout,
  dongle reply matching the MINI capture's shape). Resolution: `bringup` behind a flag.
- **Advanced keys / SOCD on the F75.** The Rust board file marks `advanced_keys: true` ("wire-verified,
  feel pending"); the fork's own Python registry keeps them `"wip"`. Take the Python side.
- **SOCD numbering.** The fork documents HFD SOCD modes as 3 last input, 1 key 1, 2 key 2, 4 neutral.
  That is the HFD family's own wire encoding and is separate from the Win60's zero-based wire
  values. It does not contradict the Win60 rule, but nothing here should be routed through the
  bridge's Model 1..4 without the MINI driver's existing conversion.
- **Workflows and packaging.** The fork deletes `board-bot.yml`, `release.yml`,
  `validate-submissions.yml`, the installer and Flatpak. Upstream has since hardened `board-bot.yml`
  (maintainer label trigger, body hash). Keep upstream's.
- **Licence.** The fork's `NOTICE.md` says upstream is unlicensed. That is out of date: upstream is
  now GPL-3.0-or-later, the same licence the fork put on its F75 additions.
- **Updater disabled** in the fork: fork-local choice, not a finding against upstream.

## 5. Security findings

No network client, no credential handling, no obfuscated or minified blobs, and no downloads were
found in the fork's additions.

- **Workflows.** `.github/workflows/ci.yml` (new): `push`/`pull_request` only, no secrets, no
  `pull_request_target`, no write permissions requested. Actions are pinned by tag, not SHA
  (`actions/checkout@v4`, `dtolnay/rust-toolchain@stable`, `Swatinem/rust-cache@v2`). Low. Not ported.
- **`board-bot.yml` and `.env.example`** are deletions of upstream files, not fork additions.
  `.env.example` holds an empty key placeholder only. The base `board-bot.yml` is the old
  any-issue-triggers version; `origin/main` already replaced it.
- **`crates/aether-gui/build.rs`**: four lines, compiles the Slint UI. No network, no process spawn.
- **Process spawns**: `crates/aether-gui/src/main.rs:134` (`notify-send`) and `:1748` (`xdg-open` on
  the app's own data dir). Fixed program names, no shell.
- **Writes outside the data dir**: `crates/aether-gui/src/main.rs:1385-1400` writes
  `~/.config/autostart/aether-he.desktop` when the user toggles autostart.
- **Local socket**: `crates/aether-gui/src/instance.rs:7-26`, Unix socket in `$XDG_RUNTIME_DIR`,
  single-instance signalling.
- **Keystroke reading**: `crates/aether-device/src/keys_in.rs` reads the board's own keyboard
  collections for reactive effects. No logging or transmission seen in the grep pass; not read line
  by line because it is not being ported.
- **D-Bus**: `zbus` dependency reads the BlueZ battery property. `Cargo.lock` is 6,200 lines of
  third-party crates; not audited (not ported).
- **Bring-up scripts** (`docs/context/f75-bringup/*.py`) open hidraw and **write to the keyboard**
  (0x22/0x23/0x24/0x27/0x28, and 0x66/0x67 travel-test on/off). No flash, reset or calibration
  command. Do not run them from upstream.
- **`scripts/build.sh`** only prints `sudo` commands; it does not execute them.
- **`session_backup.md` / `session_part_*.md`** (still in upstream `main`): scanned for API keys,
  tokens, private keys, e-mail addresses and IP addresses. **None found.** They do contain personal
  data of low sensitivity: the owner's local Linux username in dozens of home-directory paths, the
  local project path, the subscription tier shown in the CLI banner, and device-node listings.
  Recommend removing them from the tree (item 14); history rewriting is not warranted.

## Verification performed

- Blob IDs of `protocol_mini60.py` and `drivers/mini60.py` are equal at 99bee57, fork and origin/main.
- All 183 frames in the fork's `mini60.json` were rebuilt from `origin/main`'s builders: no differences.
- Fork layout vs fixture key table: 67 match, 12 empty (F1-F12), 1 differs (Fn).
- Battery offsets checked against upstream's `webhid-capture-dongle-handshake.json`.
- Issue #8 read with `gh` (needed the sandbox lifted for that one read-only call; the proxy failed TLS).
