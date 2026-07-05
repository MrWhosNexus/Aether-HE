# Aether-Windows — Sprint Plan

> **Owner:** Central Boss AI. The Implementer proposes changes; Central Boss writes them here.
>
> **Status legend:** `pending` · `in-progress` · `blocked` · `done` · `backlog`

---

## Sprint: Full Codebase Audit

**Goal:** Audit every file in the aether-windows inventory, surface severity-ranked findings, and fix all HIGH and MED findings with tests. LOW findings are triaged (fixed or moved to BACKLOG).

**Sprint window:** open-ended (continuous until user closes).

**Exit criteria:**
- `audit/findings.md` populated with every file in the inventory covered.
- HIGH section empty (every HIGH finding has a DONE FIX task).
- MED section empty.
- LOW section triaged (each entry either fixed or moved to BACKLOG).
- `agents/TASKLIST.md` shows all `AUDIT-*` and `FIX-*` tasks DONE.
- `.gitignore` complete.
- `docs/HARDWARE_TEST_CHECKLIST.md` exists and has at least one entry per hardware-touching fix.

---

## Phase 0 — Setup (DONE)

| Task | Status | Notes |
|------|--------|-------|
| Write `docs/DEV_TEAM_MASTER.md` | done | Master reference doc. |
| Write `docs/DEFINITION_OF_DONE.md` | done | Universal DoD + per-subsystem + HID safety. |
| Write `docs/CONTEXT_ENGINEERING.md` | done | Tier-1 + Tier-2 + handoff format. |
| Write 5 agent prompts | done | Boss, Implementer, Spec Reviewer, Code Reviewer, Handoff. |
| Write `agents/PLAN.md` + `agents/TASKLIST.md` | in-progress | This file. |
| Add `agents/handoffs/.gitkeep` | pending | Done as part of Phase 0 wrap-up. |

---

## Phase 1 — Audit Sweep

**Goal:** Implementer reads every file in the inventory top-to-bottom and writes at least one `audit/findings.md` entry per file (even if "no issues found"). Findings are severity-ranked HIGH/MED/LOW with reproducer + proposed fix scope.

**Exit criteria:**
- `audit/findings.md` exists with a section per file.
- Each finding: title · file:line · reproducer · proposed fix · severity.
- Implementer hands off to Central Boss for acceptance.
- Central Boss creates one fix task per HIGH and MED finding.

**Task shape (single sweeping task):**

| ID | Owner | Description |
|----|-------|-------------|
| AUDIT-SWEEP | Implementer | Read every file in `DEV_TEAM_MASTER.md` inventory; populate `audit/findings.md`. |

---

## Phase 2 — Fix HIGH findings

**Goal:** Each HIGH finding is a standalone fix task: implementer writes failing test + minimal fix, Spec Reviewer approves scope, Code Reviewer approves safety + quality, Central Boss issues INTEGRATION APPROVED.

**Initial candidate findings (refined after AUDIT-SWEEP runs; placeholders below):**

| ID | Subsystem | Placeholder finding | Hardware test? |
|----|-----------|---------------------|----------------|
| FIX-001 | `aula_device.py` | HID interface selection (`find_vendor_interface`) — verify `0xFF1B` usage-page match works on Windows; Linux fallback to highest interface_number documented and tested. | yes |
| FIX-002 | `protocol.py` | Missing golden-frame tests for cmd 7 (lighting), cmd 9 (per-key), cmd 33 (actuation). Add `tests/test_protocol.py` with exact-byte assertions. | yes |
| FIX-003 | `effects.py` | Verify per-frame spawner math is FPS-independent (assert density at 60/120/240 fps). | yes |
| FIX-004 | `gamepad.py` | Add vgamepad (Windows) port; ensure self-disable when vgamepad is absent (Win) and evdev is absent (Linux). | no |
| FIX-005 | `boards.py` | Registry validation: corrupt JSON → fallback to default board; missing file → fallback; hot-reload does not break in-flight sessions. | no |

(These are placeholders. The actual severity and ordering come from `audit/findings.md` after Phase 1.)

---

## Phase 3 — Fix MED findings

Same flow as Phase 2. Order by severity then by user-visible impact.

---

## Phase 4 — Polish

**Goal:** LOW findings triaged; commit hygiene enforced; `.gitignore` complete.

| Task | Description |
|------|-------------|
| POLISH-001 | `.gitignore` completeness — add `venv-web/`, `dist/`, `graphify-out/cache/`, `build/`, `__pycache__/`, `*.pyc`, `*.spec`. |
| POLISH-002 | Remove tracked files from gitignored paths (in the same commit as the `.gitignore` fix). |
| POLISH-003 | Triage every LOW finding: fix or move to BACKLOG. |
| POLISH-004 | Confirm `docs/HARDWARE_TEST_CHECKLIST.md` has an entry per hardware-touching fix. |

---

## BACKLOG (parking lot for out-of-sprint ideas)

| Idea | Source | Notes |
|------|--------|-------|
| Tauri port of the React/Tailwind UI | User mention, pre-sprint | Not in scope for audit sprint. |
| Multi-board JSON schema validator | Future feature | Add when boards.py grows beyond Win60 HE. |
| Automated UI rebuild hook | UX polish | Currently manual `build_runtime.py`. |
| `main.py` removal | Long-term cleanup | Explicitly out of audit scope per `CLAUDE.md`. |

---

## Decision Log

- **D1:** Sprint scope is the full codebase, not just the Windows port. Rationale: Windows-port bugs surface in cross-platform code; auditing only one OS gives an incomplete picture.
- **D2:** One Implementer agent, not per-subsystem. Rationale: the codebase is small enough that context-splitting would cost more than it saves. The Implementer reads Tier-2 context for whichever subsystem they are fixing.
- **D3:** Spec = the audit finding. The Spec Reviewer checks fidelity to the finding, not to a separate product spec (there isn't one). Rationale: this is an audit sprint, not a feature-build sprint.
- **D4:** Handoff files are the session-bridge. No in-process state is assumed between sessions. Rationale: user runs each agent in a fresh OpenClaude session.
