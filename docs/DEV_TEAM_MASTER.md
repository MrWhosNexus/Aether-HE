# Aether-Windows — Dev Team Master Reference

> **This is the single document every agent reads first.**
> It links out to deeper docs but gives the agent enough context to start work without asking questions.

---

## What We're Building

A desktop app to control the **Aula Win60 HE** Hall-effect keyboard (VID `0x2E3C`, PID `0xC365`) over raw HID, plus a multi-board registry for related Aula controllers. Built on **Linux/CachyOS**, **Windows port in progress**. UI is the React/Tailwind "Claude Design" prototype rendered natively via pywebview; a Python `Api` (exposed as `window.pywebview.api`) bridges JS to HID.

**Stack:** Python 3.10–3.12 · pywebview + hidapi · vgamepad/ViGEmBus (Windows) / evdev (Linux) · React/Tailwind precompiled UI · PyInstaller + Inno Setup installer · optional Flatpak (Linux)

**Fixed constraints (non-negotiable):**
- Single-user desktop app — no multi-tenant, no auth, no RBAC.
- Cross-platform: every code path that touches `sys.platform` must work on both Windows and Linux, or self-disable cleanly.
- Hardware safety: never send malformed HID packets that could leave the keyboard in a bad state (stuck LED, locked actuation, etc.).
- The app must always launch; missing deps degrade gracefully (gamepad, effects self-disable).

**Primary specs (already exist — read on demand):**
- `README.md` — architecture + run instructions.
- `CLAUDE.md` — HID protocol cheat-sheet, current port status.
- `docs/context/aula-win60-*.md` — six deep-dive engineering notes (HIDAPI quirk, lighting modes, protocol capture, webview UI, Windows port, multi-board).
- `docs/context/multi-board-support-and-board-families.md` — board registry design.

---

## How to Start a Session

Every agent must follow this sequence at the start of any session:

1. **Read this document** (`docs/DEV_TEAM_MASTER.md`) — full file.
2. **Check `/handoffs/`** — list `agents/handoffs/` for the most recent handoff from your role or from your predecessor in the chain. Read completely.
3. **Load Tier 1 context** (see `docs/CONTEXT_ENGINEERING.md`):
   - `docs/DEFINITION_OF_DONE.md`
   - `agents/PLAN.md` — current sprint section only
   - `agents/TASKLIST.md` — your tasks only
4. **Load Tier 2 context** based on your role:
   - Implementer: `CLAUDE.md` + relevant `docs/context/aula-win60-*.md` for the subsystem you're touching.
   - Spec Reviewer: the implementer's pre-review message + the relevant audit finding from `audit/findings.md` (if it exists).
   - Code Reviewer: the spec reviewer's verdict + the diff to review.
5. **Begin work.**

When your session ends, produce a handoff note via `agents/orchestration/05_HANDOFF_AGENT.md` and save it to `agents/handoffs/[role]-[timestamp].md`.

---

## The Full File Inventory

### Agents (5 total — lean version of hr-intake-app's 20-agent roster)

| # | File | Role | Model |
|---|------|------|-------|
| 01 | `agents/orchestration/01_CENTRAL_BOSS_AI.md` | Orchestrates all work, dispatches briefs, issues INTEGRATION APPROVED | User-driven (you, in OpenClaude) |
| 02 | `agents/audit/02_AUDIT_IMPLEMENTER.md` | Audits codebase, surfaces findings, writes fixes + tests | Sonnet |
| 03 | `agents/audit/03_AUDIT_SPEC_REVIEWER.md` | Stage 1: does the work match the audit finding? | Opus |
| 04 | `agents/audit/04_AUDIT_CODE_REVIEWER.md` | Stage 2: is the code correct + safe + tested? | Sonnet |
| 05 | `agents/orchestration/05_HANDOFF_AGENT.md` | Writes structured handoffs when sessions end | Sonnet |

### Standards & Policies (docs/)

| File | What it governs |
|------|----------------|
| `docs/DEV_TEAM_MASTER.md` | This document — read first |
| `docs/CONTEXT_ENGINEERING.md` | How every agent loads and writes back context |
| `docs/DEFINITION_OF_DONE.md` | Universal checklist every task must pass before INTEGRATION APPROVED |
| `docs/SUBMIT_A_BOARD.md` | Community process for adding new boards to `data/board_registry.json` (unchanged) |
| `docs/context/aula-win60-*.md` | Six deep-dive engineering notes (existing) |

### Living Directories (to be populated as the team runs)

| Directory | Owner | Purpose |
|-----------|-------|---------|
| `audit/` | Audit Implementer | `findings.md` (severity-ranked) + per-finding fix notes |
| `agents/PLAN.md` | Central Boss AI | Sprint goals, epics, milestones |
| `agents/TASKLIST.md` | Central Boss AI | Task ID, owner, status, dependencies |
| `agents/handoffs/` | All agents | Handoff notes at session end. Named `[role]-[timestamp].md` |

### Source Code Surface (what the audit covers)

**Python (top-level modules, flat layout — no `src/`):**

| File | Purpose | Audit focus |
|------|---------|-------------|
| `app_web.py` | pywebview shell + `Api` HID bridge | Win+Linux startup, JS↔Python contract, exception handling |
| `protocol.py` | HID packet builders for Aula Win60 HE | Byte-index math, defensive defaults, golden-frame parity |
| `protocol_sonix.py` | Protocol variant for Sonix-based boards | Coverage vs `tests/test_protocol_sonix.py` |
| `aula_device.py` | Thread-safe hidapi wrapper | Win iface selection (usage_page `0xFF1B`), lock contention, error paths |
| `device_state.py` | KeyMap, LiveReader, CalibrationReader | Thread safety, parser robustness |
| `effects.py` | Host-driven per-key RGB engine @ ~120fps | FPS-independent spawners, no per-frame allocations, board-off behavior |
| `gamepad.py` | Linux uinput → Windows vgamepad port | Self-disable when deps missing (Win without vgamepad, Linux without evdev) |
| `boards.py` | Multi-board registry loader | Validation, hot-reload, fallback to default board |
| `updater.py` | GitHub Releases self-updater | Signature verification, rollback, error UX |
| `main.py` | Legacy CustomTkinter UI | **Ignore unless asked** — explicitly out of audit scope |
| `keyboard_widget.py`, `theme.py`, `cycle_modes.py`, `play_effect.py`, `capture.sh`, `capture_analog.js` | Utilities | Audit only if they appear in a bug report |

**UI:**
- `ui/index_runtime.html` — prebuilt React/Tailwind runtime (do not edit).
- `ui/runtime_src/src/{app,sections,keyboard}.jsx` — React source; rebuild via `ui/runtime_src/build_runtime.py` after editing.
- `ui/keymap.json`, `ui/layouts/` — keymap and layout assets.

**Data / vendor / build:**
- `data/boards.json`, `data/board_registry.json` — board metadata.
- `vendor/ViGEmBus_Setup.exe` — Windows gamepad driver.
- `driver_src/dec_agreement/deobfuscated.js` — reference deobfuscated Aula driver (read-only).
- `design_handoff/` — upstream React prototype (reference only).
- `flatpak/`, `installer.iss`, `AetherHE.spec`, `build_installer.bat`, `run.bat`, `run.sh` — packaging.

**Tests:**
- `tests/test_boards.py` — registry assertions.
- `tests/test_protocol_sonix.py` — golden-frame tests vs USBPcap capture.
- Runner: `python -m pytest tests/` (no pytest.ini/pyproject.toml/conftest.py).
- **Audit gap:** no test for `protocol.py`, `aula_device.py`, `effects.py`, `boards.py` registry failure modes.

**Repo hygiene (commit hygiene is part of the audit):**
- Already committed but should NOT be: `venv-web/`, `build/`, `dist/`, `__pycache__/`, `graphify-out/cache/`.
- `.gitignore` exists but is incomplete. Audit task: fix `.gitignore` and verify.

---

## Sprint Roadmap (Summary)

This team runs a single ongoing sprint: **"Full Codebase Audit."** The audit produces `audit/findings.md` (severity-ranked). Each HIGH and MED finding becomes a fix task that flows through the implementer → spec reviewer → code reviewer chain. LOW findings are documented but not auto-fixed unless the user requests them.

| Phase | Goal | Exit criteria |
|-------|------|---------------|
| **0** — Setup | This file, the 5 agent prompts, PLAN/TASKLIST exist | User can paste any agent file into a fresh OpenClaude session and it works without questions |
| **1** — Audit sweep | `audit/findings.md` populated with severity-ranked issues across all source files | Every file in the inventory above has at least one entry (even if "no issues found") |
| **2** — Fix high-severity | All HIGH findings fixed + tested + reviewed | `audit/findings.md` HIGH section is empty; each fix has a corresponding TASKLIST entry marked DONE |
| **3** — Fix medium-severity | All MED findings fixed + tested + reviewed | `audit/findings.md` MED section is empty |
| **4** — Polish | LOW findings triaged (fix or backlog), commit hygiene fixed, `.gitignore` complete | Audit sprint closed; next sprint decided by user |

---

## Testing Strategy

### The Three Layers

1. **Unit tests (pytest)** — pure logic only: protocol byte builders, keymap math, board registry validation, effect spawner math. Fast, no I/O.
2. **Integration tests (pytest)** — hidapi mock or recorded USBPcap frames; cross-platform sys.platform branches; gamepad self-disable. Requires hardware or fixtures for the full integration, but should not block CI on a connected keyboard.
3. **Manual hardware tests** — the user runs on real Aula hardware. The audit implementer writes a `docs/HARDWARE_TEST_CHECKLIST.md` for each fix that touches `protocol.py` / `protocol_sonix.py` / `aula_device.py` / `effects.py`.

### TDD Mandate

Write tests first for anything involving:
- HID packet byte math (golden frames)
- Cross-platform `sys.platform` branches
- Thread-safe access to `aula_device.AulaDevice`
- Effect spawner density math (FPS independence)
- Board registry validation

The rule: if a finding's proposed fix touches logic or hardware state, the test file exists and fails before the fix exists.

---

## Review Process (Two-Stage, Mandatory)

Every audit-fix task goes through two reviews before Central Boss AI issues INTEGRATION APPROVED:

**Stage 1 — Spec Reviewer (`03_AUDIT_SPEC_REVIEWER.md`)**
- Does this fix address the exact finding described in `audit/findings.md`?
- Does it stay within the finding's scope (no scope creep)?
- Are acceptance criteria met (test exists + passes, reproducer is fixed)?
- Verdict: APPROVED or CHANGES REQUIRED.

**Stage 2 — Code Reviewer (`04_AUDIT_CODE_REVIEWER.md`)**
- Is the fix safe? (No malformed HID packets, no lock contention, no `sys.platform` branch without `else` self-disable.)
- Is the fix minimal? (Smallest change that resolves the finding; no drive-by refactors.)
- Are tests meaningful? (Asserts the right thing, not just that code runs.)
- Verdict: APPROVED or CHANGES REQUIRED.

For any task touching `protocol.py`, `protocol_sonix.py`, or `effects.py`: **the Code Reviewer's HID safety checklist is mandatory** (byte indices, no silent truncation, defensive defaults on unknown cmd bytes).

Use `superpowers:requesting-code-review` at the end of each task. Use `superpowers:verification-before-completion` before claiming done.

---

## The Definition of Done (Quick Checklist)

Full checklist: `docs/DEFINITION_OF_DONE.md`

A task is DONE only when ALL of the following are true:
- [ ] Implements exactly the audit finding — no more, no less
- [ ] No hardcoded secrets, no debug prints in production paths, no commented-out code
- [ ] At least one test covers the happy path (and failure path if applicable)
- [ ] All existing tests still pass (`python -m pytest tests/`)
- [ ] Stage 1 Spec Reviewer: APPROVED
- [ ] Stage 2 Code Reviewer: APPROVED
- [ ] No new files in `venv-web/`, `build/`, `dist/`, `__pycache__/`, `graphify-out/cache/`
- [ ] If hardware-touching: `docs/HARDWARE_TEST_CHECKLIST.md` entry written
- [ ] `agents/TASKLIST.md` updated to DONE
- [ ] Handoff note written if session is ending

---

## Cross-Cutting Rules (Apply Everywhere)

### HID Safety
- Never send malformed packets. Every `protocol.py` / `protocol_sonix.py` change must have a golden-frame test.
- Byte indices are 1-source-of-truth: use named constants, not magic numbers, when index has meaning (e.g. `BYTE_CMD = 0`, `BYTE_MODE = 5`).
- Unknown cmd bytes: defensive default is "no-op + log", never "act on it."
- Locked-actuation recovery: if `cmd 33` ever fails mid-update, the implementer must verify the keyboard returns to a sane default state before closing the HID handle.

### Cross-Platform
- `sys.platform == 'win32'` and `sys.platform == 'linux'` branches must both exist for any feature that differs across OSes.
- Missing deps (`vgamepad`, `evdev`) must self-disable cleanly: feature unavailable, app still launches.
- No `import vgamepad` at module top-level if Linux might run this code — guard inside function bodies.

### Commit Hygiene
- `venv-web/`, `build/`, `dist/`, `__pycache__/`, `graphify-out/cache/`, `*.pyc`, `*.spec`, capture artifacts are NOT to be committed.
- The existing checked-in `venv-web/`, `build/`, `dist/` directories are an open audit finding (LOW unless someone actively suffers from them).

### Self-Disable Pattern
- Gamepad: feature off when `vgamepad`/`evdev` import fails.
- LiveReader: feature off when device disconnects; app must not crash.
- Effects: feature off if device rejects cmd 9 mid-stream.

---

## Quick-Reference: Who Handles What

| Situation | Call This Agent |
|-----------|----------------|
| New audit finding or fix to plan | Central Boss AI (you) |
| Auditing a file or writing a fix | Audit Implementer |
| Verifying a fix matches its finding | Audit Spec Reviewer |
| Verifying a fix is safe + minimal + tested | Audit Code Reviewer |
| Session ending, work incomplete | Handoff Agent |

---

## Off-Code Action Items

**Audit must surface the following whether or not they're raised organically:**
1. `.gitignore` completeness — current `.gitignore` does not cover `venv-web/`, `dist/`, `graphify-out/cache/`.
2. Missing tests for `protocol.py` (only `protocol_sonix.py` is tested).
3. `main.py` legacy UI — confirm it remains untouched per `CLAUDE.md` and is not audited.
4. `docs/HARDWARE_TEST_CHECKLIST.md` does not exist — create the first version as part of the audit setup.