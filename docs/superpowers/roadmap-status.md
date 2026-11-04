# Roadmap status — shared notes for the agent team

Spec: `docs/superpowers/specs/2026-11-04-win60-roadmap-design.md`. Read the spec and
this file before starting. Append one entry when you finish (newest at the bottom).

Entry format:
```
## <date> <phase/task> — <role> (<model>)
- Landed: <commit hashes + one line each>
- Decisions: <calls later phases must respect>
- For next phase: <interfaces, gotchas>
- For the user (morning): <hardware checks, open questions>
- Stopped early? <where, why>
```

## 2026-11-04 Phase 0 — planner (Opus, session that wrote the spec)
- The overnight branch is cut from `claude/missing-broken-audit-cda685` at the commit that adds this file (Travel Test release fix 839a076, build CRLF fix dcc46d2, security plan 3ef647c).
- Security fixes are NOT done on the overnight branch: a scheduled run implements them on `claude/missing-broken-audit-cda685` at 10:00 on 2026-11-04. Leave their targets alone (listed in the spec's Global constraints).
- Baseline: 683 tests passing.
