# Fork port brief (2026-11-12): implementers

The owner asked to "port everything worth taking", **always adapting**. Fit each change to current `main` (v0.6.5, `f38e69a`): fix the defects the reviews found, keep the repo's evidence gating, add tests. Never paste fork code verbatim.

The three reviews in this folder are your specs. Each item's PORT / PORT-EXPERIMENTAL verdict and port spec is binding. SKIP items stay skipped.
- `fork-review-nieruuu19.md`
- `fork-review-xplaya.md`
- `fork-review-fatalist.md`

Fork refs are fetched in the shared object store, so `git show <ref>:<path>` works from your worktree:
- `nieruuu19/aether-he-0.5.4-custom`
- `xpLayA/main`
- `origin/feat/sayo-actuation-decode`

## Rules for both agents
- **Gating.** SOURCE-ONLY or owner-claim hardware WRITES stay behind the board's experimental flag:
  - the WIN 68 Max uses the existing `AETHER_EXPERIMENTAL=magnet`;
  - the F75 gets a new `f75` flag, using the same mechanism as `_apply_experimental_flags` in app_web.py.
  CAPTURED behaviour ships on. Effect NAMES that come from source only are labelled unverified in code and UI. Their bytes are captured and ship on.
- **No hardware.** Never launch the real app, and never talk to a keyboard.
- **Credit.** Each commit that adapts fork work ends with:
  - a line `Adapted from <fork>@<sha>`, then
  - `Co-authored-by: <author>`, using `Niel <(email in commit trailers)>` for nieruuu19 or `xpLayA <70793661+xpLayA@users.noreply.github.com>` for xpLayA, then
  - `Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>`.

  The Sayo decode is the owner's own branch: no co-author, but do write "Adapted from origin/feat/sayo-actuation-decode@cfdcb8d".
- **Commits.** Small, logical commits on your branch, in your worktree only. Never push.
- **Tests.** Full suite with `PYTHONDONTWRITEBYTECODE=1 ~/aether-macos/.venv-mac/bin/python -m pytest -q -p no:cacheprovider`. In the sandbox, `test_service_guard` (port bind) and the `/bin/ps` updater tests fail or skip; that is expected. Everything else must be green.
- **UI.** Regenerate it with `python ui/runtime_src/build_runtime.py` after `.jsx` edits. Only agent A edits `ui/runtime_src/**`.
- **README.** Update the Supported keyboards table and boards text for what you changed. Agent A owns the WIN 68 HE Max text; agent B owns the F75 and Sayo text plus the new udev lines. Edit only your own rows and paragraphs, so the merge is trivial.
- **Report.** Write a deviations list (`port-deviations-A.md` / `port-deviations-B.md` in this folder): every place your port differs from the fork's code, and why. It goes into the PR.
- **Budget.** At ~300k tokens: commit what is green, write `port-status-A.md` / `port-status-B.md` with what's done and left, then stop.

## Agent A: nieruuu19 → WIN 68 HE Max (worktree `ah-forkA`, branch `port/nieruuu19-win68max`)

**Items:** nieruuu19 review items 1, 2, 3, 4, 6, 7, 8, 9, 10, 11, 18, 19 (power-off half only), and 20 (picker + hex; the saved-colour library is optional).

**Owns:**
- `protocol_magnet.py`
- `drivers/magnet.py`
- `ui/runtime_src/**` and its regenerated build output
- `app_web.py`
- `ui/layouts/aula-win68he-max.json`
- magnet tests and lighting UI tests

**Must not touch:**
- `data/board_registry.json`
- `data/boards.json`
- `protocol_mini60.py`
- `drivers/mini60.py`
- `protocol_sayo.py`
- F75 layouts and fixtures
- udev files

If you need a registry change, describe it in your status file instead.

**SOCD contract.** Since PR #32, the bridge carries Model 1..4 and each driver converts. The magnet driver must map 1..4 to the fork's corrected zero-based index, in the corrected frame layout (`bind` at byte 7, mode at byte 8, delay u16), behind the flag. Update `test_socd_clear.py` and any magnet SOCD tests to match.

## Agent B: xpLayA F75 + Sayo decode + housekeeping (worktree `ah-forkB`, branch `port/f75-sayo`)

**Items:**
- xpLayA review sections 3.1 to 3.5:
  - layout;
  - fixtures as test data;
  - battery/work-mode parse;
  - F75 HE drivable entry, wired + dongle, PORT-EXPERIMENTAL behind `f75`, `bringup`, not offered in the picker;
  - deleting `session_backup.md`, `session_part_1.md` and `session_part_2.md` from the repo root.
- udev rules for the two F75 IDs.
- The Fatalist review's B1 + B2: the Sayo cmd-0x1C field decode, library-only, with a required per-key `base_payload`, and goldens using the real captured echo 0x13.

**Owns:**
- `data/board_registry.json`
- `data/boards.json`
- `ui/layouts/aula-f75*.json`
- `tests/fixtures/f75/**`
- `protocol_mini60.py`
- `drivers/mini60.py`
- `protocol_sayo.py`
- udev rules files
- the three `session_*.md`
- their tests

**Must not touch** `app_web.py` or `ui/runtime_src/**`. If the F75 needs an `app_web.py` change (for example the `f75` experimental flag, or exposing battery state), write the exact change in `port-status-B.md`. The orchestrator applies it after the merge.
