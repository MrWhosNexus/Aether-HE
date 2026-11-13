# Handoff: fork ports + board audit (Mac → Windows, 2026-11-12)

Branch **`wip/fork-ports`** (draft PR). It is based on `main` @ `f38e69a` (v0.6.5) and merges two port branches:
- `port/nieruuu19-win68max`: WIN 68 HE Max, adapted from nieruuu19's fork;
- `port/f75-sayo`: AULA F75 HE, adapted from xpLayA's fork, plus cleanup.

It ends with `f710c34`, which wires the F75 experimental flag.

**Status:**
- **Tests:** full suite green on macOS. 1,699 passed / 26 skipped with `test_service_guard` deselected (the sandbox blocks port binds), then 94 more on the touched files after `f710c34`.
- **Not ready to merge:** the items in "What's left" are unfinished.
- **Hardware:** nothing has been run against a keyboard.

## Pick it up on Windows

```bat
cd %USERPROFILE%\Aether-HE
git fetch origin
git switch wip/fork-ports
venv-web\Scripts\python -m pip install -r requirements.txt
venv-web\Scripts\python -m pytest -q
```

`test_service_guard` passes on Windows. The macOS-only updater tests (`/bin/ps`, `ditto`, `codesign`) skip there. Rebuild the UI after any `.jsx` edit with `venv-web\Scripts\python ui\runtime_src\build_runtime.py`. CRLF is normalised by `compile.cjs`.

## What the owner asked for

1. "Full fable review of the three forks and implement anything I don't already have."
2. "Make improvements to their code if necessary; always adapt." This is a standing rule: never paste fork code verbatim.
3. "Make sure all these boards are drivable, each board has its correct key layout, remove what is redundant, get back to me if you find anything new."

Every unfinished item below serves one of those three.

## What's done on this branch

**WIN 68 HE Max** (`protocol_magnet.py`, `drivers/magnet.py`; credit nieruuu19):
- **Read-back on connect:** version, travel limits, lighting state, per-key config.
- **State-preserving lighting:** it reads first and keeps the board's palette and sleep settings, instead of overwriting them.
- **The 20 firmware effects:** the bytes were captured; the effect names come from the vendor's source code, so they are marked unverified.
- **Actuation that keeps the advanced-key bits.** Upstream used to wipe SOCD/macro bindings.
- **Standard vs Continuous Rapid Trigger and dead band.**
- **SOCD rebuilt on the fork author's corrected frame:** bind at byte 7, zero-based mode at byte 8, clear-before-apply. Upstream's frame only worked for Model 1, by accident.
- **Evidence labels:** paths the fork author ran on their own board are labelled COMMUNITY-TESTED (nieruuu19) and ship ON.
- **Still experimental:** only live travel (0x12) stays behind `AETHER_EXPERIMENTAL=magnet`.
- **No blind writes:** if the board's replies don't match the expected layout, writes refuse with an error.
- **Tests:** magnet tests went from 27 to 92.

**AULA F75 HE** (`38A6:2729` plus the dongle; credit xpLayA):
- It speaks the existing `protocol_mini60`, so no new protocol code was needed.
- The real 80-key layout, checked key by key against the contributor's read-back fixtures and pinned by a test.
- The fixtures are committed as test data.
- Offered in the picker, labelled community-tested.
- Dead zone and macros stay behind `AETHER_EXPERIMENTAL=f75`, because they were never run on an F75.

**Battery, work mode and firmware parse** from the mini60 0x10 reply. It's in the protocol and driver only; the UI doesn't show it yet.

**Removed:** `session_backup.md`, `session_part_1.md` and `session_part_2.md`. They held a local username and paths.

**Closed upstream:** PR #15 (Fatalist0001), with an explanation. Nothing from it was ported; see `fork-review-fatalist.md`.

## What's left (in order)

**WIN 68 HE Max**, from `port-status-A.md`:
1. **Registry entry `aula-win68he-max`.** The exact values are in `port-status-A.md` under "Registry change needed":
   - `offerInUi` is already true via `2ebce23`;
   - capabilities: actuation, rapidTrigger, socd, deadzone;
   - an `actuation` ranges block;
   - the 20 `fw-*` modes with `nameUnverified: true`.

   **Until this lands, the UI does not offer the new features.**
2. **Layout `_meta`:** correct it in `ui/layouts/aula-win68he-max.json` (the indices ARE verified against the capture), and add the 68-key pin test.
3. **UI** (spec F in `fork-review-nieruuu19.md`; exact edits in `port-status-A.md` step 2):
   - Custom-mode phantom keys;
   - preview dark when lights are off;
   - Per-key Paint free colour picker + hex;
   - the "unverified name" marker on effects.
4. **Docs:** README rows; `docs/HARDWARE_TEST_CHECKLIST.md:203` SOCD line; the `tests/test_socd_model.py:81` docstring.
5. **Owner decision:** live travel stays behind the flag. Without it, Travel Test and Dashboard live depth don't work on this board.

**F75 / Sayo**, from `port-status-B.md`:

6. **udev:** add the two F75 IDs to `99-aula.rules`.
7. **Sayo cmd-0x1C decode, library only.** Follow `fork-review-fatalist.md` §3:
   - make `base_payload` a required argument; the fork wrongly replays key 0x2F's bytes into every key;
   - use echo 0x13 in the goldens;
   - credit "Adapted from origin/feat/sayo-actuation-decode@cfdcb8d".

   The board stays NOT drivable: nobody owns one, and the per-key bytes 0-11 are unknown.
8. **Docs:** checklist F75 section; README F75 / Sayo prose.

**Board audit fixes**, from `layout-redundancy-audit.md`. Not started. One Fable agent can do all of these:

9. **KP-TE153.** Add a 69-key ISO drawing (`KB_ROWS_69_ISO`). Better: give every registry entry an explicit `uiLayout` field instead of inferring the layout from key codes. Today `_ui_layout()` sees Home instead of Ins and draws the 60% board, so ten keys are unreachable.
10. **MINI60HE Max (`0C45:80A1`) + dongle:**
    - point them at `aula-mini60he-pro.json`; the current file has Win60 stride-22 indices on a stride-16 HFD board;
    - delete `aula-mini60he-max.json`.

    **New finding:** `protocol_sonix` is a mis-parse. `protocol_mini60.build_light` reproduces the #4 lighting frames byte for byte, so this board is probably drivable with the existing mini60 driver. Repoint it, then retire `protocol_sonix` and its tests. Offer it as community / experimental until an owner (the #4 reporter volunteered) confirms on hardware.
11. **MINI 68 HE / Pro / Max.** They borrow the magnet family's layout. Generate `aula-mini68he.json` from the vendor HFD layout array `r` the same way the MINI 60 Pro file was built. The source lives only in the owner's local `issue-6-mini60-pro-raw/driver_src/`, not in the repo.
12. **F75 Tri-Mode `aula-f75.json`.** Index 22 is a duplicate Esc and should be Backquote / 0x35. That duplicate forces the positional key-map fallback (F1 reads as "1").
13. **WIN 60 HE Max (`1CA2:1902`).** Issue #25 has an in-app capture on the same 0xFFA0 interface as the WIN 68 Max. Check it against `protocol_magnet` travel parsing, infer the stride, set the usage page, and link #19 / #25 in the registry.
14. **Sayo** advertises `lighting: true` but runs `NullDriver`. Set it false, or write a lighting-only driver from the captured frames. `Logs.zip` on #3 has never been looked at.
15. **Redundant files to remove:**
    - the duplicate layouts `aula-win60he-si2825heargb.json`, `aula-win60he-si2825kzheargb.json` and `aula-win68he-si2828kzheargb.json`;
    - the legacy Tk UI: `main.py`, `keyboard_widget.py`, `theme.py`;
    - the one-off prompt files at the repo root;
    - the 5.4 MB manual PDF stored twice in `design_handoff/`;
    - the stale notes listed in the audit §3.
16. **Tests:**
    - `test_hed_imports_match_vendor_configs_verbatim` always skips in CI, because the vendor tables are git-ignored. Commit the needed vendor key tables as fixtures so it runs.
    - Fix the mid-file `if __name__` block in `tests/test_layouts.py`.

**Remote branches.** Nine branches on origin are fully merged, listed in the audit §3. **Ask the owner before deleting them.** `feat/sayo-actuation-decode` is superseded once item 7 lands.

## Issue attachments (owner approved downloading; not yet fetched)

Download into a fresh, empty folder. Treat them as untrusted data and never run anything from them.

| Issue | Attachment |
|---|---|
| #3 | https://github.com/user-attachments/files/29333643/Desktop.zip |
| #3 | https://github.com/user-attachments/files/29365432/KBblindtestV3EN.zip |
| #3 | https://github.com/user-attachments/files/29717025/Desktop.zip |
| #3 | https://github.com/user-attachments/files/30417059/Logs.zip (never analysed) |
| #4 | https://github.com/user-attachments/files/29090894/aula_capture.zip |
| #20 | https://github.com/user-attachments/files/31014493/board-win68he-20260812-232853.json (already pinned in the tests) |
| #25 | https://github.com/user-attachments/files/31835928/board-win60hemax-20260904-154601.json |

## Hardware checks for the PC (Win60 HE on hand)

- **SOCD numbering (v0.6.5, already released):** set an A/D pair to Model 2 ("Key 1 wins"), hold A, then press D. A should stay active. The vendor capture backs this (`WIN60_CAPTURE_NOTES.md` §7).
- **Reconnect:** Pair while already connected, then a calibration run.
- **Other boards:** the WIN 68 HE Max and the F75 need their owners. Ask on #7 (nieruuu19) and #8 / xpLayA's fork. For the WIN 68 HE Standard, answer #27: BARDIA156 offered to test in September and never got a reply.

## How the work was run (repeat this)

- **Implementers:** Fable agents, each with disjoint file ownership and a brief like `fork-port-brief.md`. Stop each one near 300k tokens.
- **Gate:** the orchestrator runs the full suite, the build, and a runtime probe for any behavioural claim.
- **Review:** adversarial reviewers try to REFUTE the change: Fable at low effort plus Sonnet. MiniMax via Hermes was out of credits (HTTP 402) on 2026-11-11.
- **Release:** dry-run `release.yml` (build-only dispatch, empty tag) before pushing a tag. On 2026-11-11 that caught the retired `macos-14` runner and a slow-runner test.

## Files in this folder

| File | Contents |
|---|---|
| `fork-review-*.md` | Per-fork review: item tables, port specs, conflicts, security |
| `layout-redundancy-audit.md` | Every board's layout and drivability verdict; redundancy list; new findings |
| `fork-port-brief.md`, `fork-review-brief.md` | The briefs the agents worked from |
| `port-status-{A,B}.md` | Where each implementer stopped and the exact next steps |
| `port-deviations-{A,B}.md` | Every place the port differs from the fork, and why. Goes into the PR description |
