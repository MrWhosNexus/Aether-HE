# DEFINITION_OF_DONE.md

## Purpose

Every agent and every task must meet these criteria before Central Boss AI issues INTEGRATION APPROVED. This is the universal finish line for the aether-windows audit team.

---

## Universal Criteria (Every Task, No Exceptions)

### Code
- [ ] Task implements exactly what the audit finding described — no more, no less
- [ ] No hardcoded secrets, credentials, or environment-specific values in code
- [ ] No commented-out dead code committed
- [ ] No `print()`, `console.log`, or debug statements left in production paths
- [ ] No new files committed in `venv-web/`, `build/`, `dist/`, `__pycache__/`, `graphify-out/cache/`, `*.pyc`

### Tests
- [ ] At least one test covers the happy path of the new behavior
- [ ] At least one test covers a failure or error path (where applicable)
- [ ] All existing tests still pass (`python -m pytest tests/`)
- [ ] Test results included in pre-review message

### Review
- [ ] Stage 1 (Spec Reviewer) returned APPROVED
- [ ] Stage 2 (Code Reviewer) returned APPROVED
- [ ] Central Boss AI issued INTEGRATION APPROVED

### Documentation
- [ ] If a new finding was discovered during the fix: added to `audit/findings.md`
- [ ] If a HID-protocol behavior changed: `docs/context/aula-win60-*.md` updated to match
- [ ] `agents/TASKLIST.md` updated to DONE
- [ ] Handoff note written if session is ending (see `agents/orchestration/05_HANDOFF_AGENT.md`)

### Handoff
- [ ] If session is ending, handoff note written to `agents/handoffs/[role]-[timestamp].md`

---

## Additional Criteria by Subsystem

### HID Protocol tasks (`protocol.py`, `protocol_sonix.py`)
- [ ] Golden-frame test added (asserts exact bytes sent for a known command)
- [ ] Byte indices either named constants or commented with their meaning
- [ ] Unknown cmd / mode bytes default to "no-op + log" — never act on unknown values
- [ ] `aula_device.AulaDevice` lock acquired and released correctly (no `with` statement left open)
- [ ] If the change affects lighting/actuation/effects, `docs/HARDWARE_TEST_CHECKLIST.md` entry added

### Device I/O tasks (`aula_device.py`, `device_state.py`)
- [ ] Thread-safety preserved (no shared mutable state without a lock)
- [ ] Device disconnect mid-operation does not crash the app
- [ ] HID interface selection (`find_vendor_interface`) works on both Windows and Linux
- [ ] Error returns are typed; callers can distinguish "device gone" from "packet rejected"

### Effects tasks (`effects.py`)
- [ ] Per-frame spawner math is FPS-independent (scaled by `_SPAWN_NORM` or equivalent)
- [ ] No per-frame list/dict allocations in the hot loop
- [ ] If device rejects cmd 9 mid-stream, effects self-disable and app continues
- [ ] No regressions in existing lighting modes (static, breath, wave, neon, reactive, ripple, custom, fireworks, speedres, autorip, striation, aurora)

### Cross-platform tasks (anything touching `sys.platform`)
- [ ] Both `win32` and `linux` branches exist; feature self-disables when dep missing
- [ ] No `import vgamepad` / `import evdev` at module top-level — guard inside function
- [ ] Verified on the target OS the task lists in ACCEPTANCE CRITERIA
- [ ] No Linux-only assumptions leak into Windows paths (and vice versa)

### Gamepad tasks (`gamepad.py`)
- [ ] Self-disables cleanly when `vgamepad` (Win) or `evdev` (Linux) is absent
- [ ] vgameport/ViGEmBus path matches the documented Win behavior in `CLAUDE.md`
- [ ] No analog events lost under load (queue capacity is bounded and tested)

### Board registry tasks (`boards.py`, `data/board_registry.json`)
- [ ] New boards pass `tests/test_boards.py` validation
- [ ] Hot-reload (if implemented) does not break currently-running sessions
- [ ] Fallback to default board works when registry is corrupt or missing

### Commit-hygiene tasks (`.gitignore`, repo cleanup)
- [ ] `.gitignore` updated to cover the offending paths
- [ ] Tracked files in those paths are removed from the index in the same commit
- [ ] CI / local `git status` is clean after the commit

---

## HID Safety Checklist (Code Reviewer Mandatory)

For any task touching `protocol.py`, `protocol_sonix.py`, `effects.py`, or `aula_device.py`:

- [ ] Byte-index math is correct (no off-by-one in the 64-byte report)
- [ ] No silent byte truncation (e.g. `r[9] | r[10]<<8` does not overflow when values are near 255)
- [ ] Named constants used where index has meaning (`BYTE_CMD = 0`, `BYTE_MODE = 5`, etc.)
- [ ] `r[1]==33` style brittle indexing is commented or refactored
- [ ] Defensive defaults exist for unknown cmd / mode bytes (no-op + log)
- [ ] Lock acquired/released correctly around HID writes
- [ ] If `cmd 33` (actuation) fails mid-update, recovery path is documented
- [ ] New lighting/actuation/effect changes have a `docs/HARDWARE_TEST_CHECKLIST.md` entry

---

## What Happens If Criteria Are Not Met

- **Implementer:** revise and resubmit. Do not self-merge.
- **Reviewer who approved incomplete work:** flagged by Central Boss; must re-review.
- **Central Boss AI:** may not issue INTEGRATION APPROVED until all boxes are checked.

---

## Anti-Patterns (Auto-Reject)

- "Drive-by refactor" — fixing something the audit finding did not mention. Open a new finding instead.
- "While I'm here" — bundling unrelated cleanup into the same commit.
- "Test for coverage" — a test that asserts the code runs without asserting the right behavior.
- "Defensive overkill" — wrapping every line in try/except. The standard is "fail loudly for programmer errors, fail gracefully for runtime errors."
- "Magic number" — `r[5]`, `length=22`, `0xC365` without a constant or comment.