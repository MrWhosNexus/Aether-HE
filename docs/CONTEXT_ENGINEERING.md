# CONTEXT_ENGINEERING.md

## Purpose

aether-windows agents run in **fresh OpenClaude sessions, one per agent**. They have no in-process memory of previous sessions. The handoff files in `agents/handoffs/` are the only state that persists between sessions. This document defines exactly what each agent must read on startup, and what it must write back at session end.

The protocol is small on purpose: aether-windows is a single-user desktop app, not a multi-tenant SaaS. There is no Supabase, no RLS, no RBAC, no cross-team coordination. The complexity is in the hardware, not in the org chart.

---

## Tier 1 — Universal (Every Agent, Every Session)

Read these before doing anything else:

1. `docs/DEV_TEAM_MASTER.md` — full file. This is the project map.
2. `docs/DEFINITION_OF_DONE.md` — full file. This is the finish line.
3. `agents/PLAN.md` — current sprint section only.
4. `agents/TASKLIST.md` — your tasks only (filter by your role).
5. `agents/handoffs/` — list the directory. Read the most recent handoff from your role, plus the most recent handoff from your predecessor in the chain (if any).

If any of these files is missing, that is itself an audit finding — open one and stop work until Central Boss resolves it.

---

## Tier 2 — Role-Specific

### Audit Implementer (`02_AUDIT_IMPLEMENTER.md`)
- `CLAUDE.md` — HID cheat-sheet, current port status.
- `audit/findings.md` — read existing findings before writing new ones (no duplicates).
- The specific subsystem you're touching, in this order:
  1. `docs/context/aula-win60-*.md` for the relevant subsystem (lighting, protocol, webview, etc.).
  2. The source file itself, end-to-end.
  3. Any existing tests for the file (`tests/`).
  4. Any usage in `app_web.py` or other callers.
- `docs/SUBMIT_A_BOARD.md` — only if the task touches `boards.py` or `data/board_registry.json`.

### Audit Spec Reviewer (`03_AUDIT_SPEC_REVIEWER.md`)
- The implementer's pre-review message (from `agents/handoffs/implementer-to-spec-reviewer-[task].md`).
- The audit finding being addressed (from `audit/findings.md`).
- The current `agents/TASKLIST.md` entry for the task.
- `docs/DEFINITION_OF_DONE.md` — re-read the relevant subsystem section.

### Audit Code Reviewer (`04_AUDIT_CODE_REVIEWER.md`)
- The spec reviewer's verdict (from `agents/handoffs/spec-reviewer-to-code-reviewer-[task].md`).
- The diff being reviewed (`git diff <base>..HEAD` or staged diff).
- The audit finding being addressed (from `audit/findings.md`).
- `docs/DEFINITION_OF_DONE.md` — re-read the HID Safety Checklist if protocol code is touched.

### Handoff Agent (`05_HANDOFF_AGENT.md`)
- The current session transcript (provided by the user pasting it in).
- The relevant agent's prompt file (so the handoff can speak in that role's voice).
- Existing `agents/handoffs/*.md` — read at least one to match format.

---

## Context Write-Back (Session End)

Every agent session ends with one of:

1. **Handoff note written to `agents/handoffs/[role]-[timestamp].md`** (use `05_HANDOFF_AGENT.md` or follow its template).
2. **Or** the session completed work that does not require follow-up — in which case the agent confirms in its final message that no handoff is needed.

### When a Handoff Is Required

A handoff is required when:
- The session ends mid-task (not done, not reviewed, not merged).
- The session discovered a new finding during work on an existing one.
- The session changed `audit/findings.md`, `agents/PLAN.md`, or `agents/TASKLIST.md`.
- The session made a design decision that future sessions need to know about.

A handoff is NOT required when:
- The task is fully DONE and Central Boss has issued INTEGRATION APPROVED.
- The session only made trivial edits (typo fix, comment cleanup) that are self-explanatory.

---

## Handoff File Format

```
# Handoff — [Role] — [Timestamp YYYY-MM-DD-HHMM]

## What I Was Doing
[1-2 sentences: which task, which finding]

## Where I Left Off
[Specific state: which files modified, which tests pass/fail, what's staged]

## Open Issues
- [issue 1]
- [issue 2]

## Decisions Made
- [decision 1: rationale]
- [decision 2: rationale]

## Context for the Next Agent
[Anything the next agent needs to know that's not in the code or in other docs.
 Typical contents: which subsystem was confusing, which doc is stale, which test
 fixture is broken, which OS the user is currently on.]

## Risks
- [risk 1: severity + mitigation]
```

The handoff file IS the context for the next session. If the next agent reads it and has questions, the handoff was incomplete.

---

## Why This Exists

hr-intake-app has a 20-agent team and runs in-process — chained agents share context automatically. aether-windows has 5 agents and runs one-per-session in OpenClaude — chained sessions share context only via handoff files.

The cost of running one-per-session is that every agent re-loads context from disk. The benefit is that each agent can be paused, resumed, retried, or replaced independently. The handoff files are how we get the in-process benefit (no repeated context-loading) without the in-process cost (one stuck agent blocks the whole chain).

---

## Anti-Patterns

- **Reading the entire codebase on startup.** Tier 2 says read the specific subsystem. Don't waste tokens on files you won't touch.
- **Skipping Tier 1.** Every agent skips Tier 1 at their peril — it's how context drift happens.
- **Writing a handoff with "see code for details."** The handoff IS the details. If you can't write it concisely, the work is too tangled to hand off cleanly — break it down first.
- **Modifying `audit/findings.md`, `PLAN.md`, or `TASKLIST.md` from a non-orchestrator session.** Only Central Boss owns those files. The Implementer proposes changes; Central Boss writes them.