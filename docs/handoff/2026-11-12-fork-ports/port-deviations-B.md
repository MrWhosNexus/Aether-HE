# Port deviations, Agent B (branch `port/f75-sayo`)

Every place the port differs from the fork's code, and why. Sources: `xpLayA/main@9a70ec6`.
The Sayo decode (`origin/feat/sayo-actuation-decode@cfdcb8d`) was **not started**; see
`port-status-B.md`.

## Owner override applied (2026-11-12)

The review specs said PORT-EXPERIMENTAL: `bringup`, not offered, everything behind an `f75` flag.
The owner then asked for the boards to be drivable. So:

- Both F75 entries are `offerInUi: true`. Features the contributor round-tripped on the board ship on.
- The `f75` flag survives only for writes nobody ran on an F75: the 0x21 dead-zone write and the
  0x15/0x25 macro table.
- `aula-win68he-max` is `offerInUi: true` with a "COMMUNITY-TESTED (nieruuu19)" note. Its
  capabilities, vid/pid and protocol are unchanged.

## F75 HE registry entries

| Fork | Port | Why |
|---|---|---|
| `status: "supported"` | `status: "bringup"`, offered | No maintainer owns the board. `aula-win68-he` is the precedent for offered + bringup. |
| Notes say "HARDWARE-VERIFIED" | "contributor-reported (xpLayA fork, 2026-10-21), not maintainer-verified"; entry opens with "COMMUNITY-TESTED (xpLayA read-backs)" | Upstream does not record a fork author's result as its own verification. A test forbids the string in these entries. |
| Python registry: `socd`, `remap`, `advancedKeys` = `"wip"`; Rust board file: `advanced_keys: true` | `true` | Owner override. The 0x22/0x28 round trips are documented in the fixture README. The note says the stored record is proven and the feel is not. |
| `deadzone`, `macros` = `"wip"` with no enforcement | `"wip"` and refused by the driver without `AETHER_EXPERIMENTAL=f75` | Never sent to an F75. |
| No Python entry for the 2.4 GHz receiver (Rust `links` only) | New entry `aula-f75-he-24g`: `0C45:FEFE`, productString `AULA F75 HE Dongle`, `0xFF60`, `frameLen: 32`, `hostEngine: false` | Upstream models each transport as its own entry, as for the MINI. |
| Name `AULA F75 HE` | `AULA F75 HE (wired)` / `AULA F75 HE (2.4GHz dongle)` | Matches the MINI pair. |
| Lighting mode table copied inline | Generated from the MINI's table (identical content) | Same firmware family; mode names other than Static and Drifting are labelled UNVERIFIED in the `_note`. |
| Behaviour notes spread over three docs | Folded into the entry `_note`: stale 0x13 colour after a 0x23 write, all-zero 0x17 table = factory, empty F1-F12 records, 0x66 acks but streams nothing, BLE has no vendor collection | Review item 7 and 6: notes only, no code. |

## Driver

- **No new driver class and no `drivers/__init__.py` dispatch change.** Both slugs map to
  `Mini60Driver` through `protocol: "protocol_mini60"`. The spec's "flag off gives NullDriver" was
  dropped with the owner override.
- **Per-slug gating is new, not from the fork:** `Mini60Driver.UNVERIFIED_FEATURES_BY_SLUG`,
  `experimental_f75`, `supports()` override and `_require_verified()`. The MINI has no entry, so its
  behaviour is unchanged (tested).
- **Battery.** The fork parses battery in Rust for any link. The port adds
  `protocol_mini60.parse_device_status()` and `Mini60Driver.device_status()`, which returns `None`
  on a 64-byte (wired) profile without sending a frame: upstream's wired capture has `0x10` at the
  battery offset. Added beyond the spec: a `version` string, `battery: None` for a byte above 100,
  and `ValueError` for a short, non-reply or non-offset-0 frame.
- I edited `drivers/__init__.py` (docstring only). It is on neither agent's ownership list.

## Layout

- `ui/layouts/aula-f75he.json` is the fork's file with `_meta.indicesStatus` reworded and a
  known-gaps sentence added to `_meta.note`. **No key was changed:** the key-by-key check against
  the fixture key table found 67 matches, 12 empty F-row records and the Fn convention difference,
  exactly as the review said.
- The fork changed nothing in `ui/layouts/aula-f75.json`; neither did I.

## Fixtures

- Copied to `tests/fixtures/f75/` (fork path: `fixtures/f75/`), byte-identical, plus a provenance
  header in the README.
- Not copied: `docs/context/f75-bringup/*.py` (they write to a keyboard), `shortcuts.json`, the
  golden snapshot, the Rust workspace, the fork's udev file name.

## Tests

- The fork promoted the F75 into the "captured" set. The port adds it as a **documented contributor
  exception** in `test_only_captured_boards_are_drivable`.
- `test_unsupported_boards_are_never_offered` and the picker test in `test_drivers.py` now expect
  seven offered boards. The spec said to leave the first unchanged; the owner override changed it.
- New `tests/test_f75.py` (fakes only) and four status tests in `tests/test_protocol_mini60.py`.

## Removals

- `session_backup.md`, `session_part_1.md`, `session_part_2.md` (repo root). Nothing referenced them.
- **Not removed: `ui/layouts/aula-f75.json`.** The F75 HE layout does not supersede it. It is the
  Tri-Mode's own scaffold (`_meta` 258A:010C) and `aula-f75-tri-mode` still references it. A test
  pins that.
- The identity-only F75 HE entry text and its `recognized` row in `data/boards.json` are replaced,
  not kept alongside.
- Nothing else became dead.

## Not done

- udev lines for `38a6:2729` and `0c45:fefe`.
- README boards prose beyond the generated table, and `docs/HARDWARE_TEST_CHECKLIST.md`.
- Sayo B1 + B2.
