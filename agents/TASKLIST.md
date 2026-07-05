# Aether-Windows — Task List

> **Owner:** Central Boss AI. The Implementer proposes changes; Central Boss writes them here.
>
> **Format:** Each task has a unique ID, an assigned agent, a severity (inherited from the audit finding for FIX-* tasks), acceptance criteria, dependencies, and a status.
>
> **Status legend:** `pending` · `in-progress` · `in-review` · `changes-required` · `done` · `blocked`

---

## Active tasks

| ID | Owner | Severity | Description | Status | Dependencies | Files | Acceptance criteria |
|----|-------|----------|-------------|--------|--------------|-------|---------------------|
| AUDIT-SWEEP | Implementer | n/a | Read every file in inventory; populate `audit/findings.md` with severity-ranked findings + reproducers. | pending | Phase 0 complete | all source files in inventory | One entry per file (even if "no issues"); every entry has severity + reproducer + proposed fix. |
| FIX-001 | Implementer | HIGH | `aula_device.find_vendor_interface`: verify `0xFF1B` usage-page match works on Windows; document Linux fallback to highest interface_number; add tests for both branches. | pending | AUDIT-SWEEP | `aula_device.py`, `tests/test_aula_device.py` (new) | Test on Win opens vendor collection, not keyboard HID; test on Linux falls back to iface 2; full suite passes. Hardware test required. |
| FIX-002 | Implementer | HIGH | Add golden-frame tests for `protocol.py` (cmd 7 lighting, cmd 9 per-key, cmd 33 actuation). Assert exact bytes. | pending | AUDIT-SWEEP | `tests/test_protocol.py` (new), `protocol.py` | Exact-byte assertions for one known value per command; full suite passes. Hardware test required. |
| FIX-003 | Implementer | HIGH | `effects.py` per-frame spawner math: verify FPS independence at 60/120/240 fps; no per-frame list/dict allocations in hot loop. | pending | AUDIT-SWEEP | `effects.py`, `tests/test_effects.py` (new) | Density assertion holds across FPS values; allocator assertion holds. Hardware test required. |
| FIX-004 | Implementer | HIGH | `gamepad.py` vgamepad (Windows) port; self-disable when vgamepad or evdev is missing. | pending | AUDIT-SWEEP | `gamepad.py`, `tests/test_gamepad.py` (new) | Win+Linux branches both exist; missing-dep self-disable tested; app still launches with dep missing. |
| FIX-005 | Implementer | MED | `boards.py` registry: corrupt JSON → default board; missing file → default board; hot-reload does not break in-flight sessions. | pending | AUDIT-SWEEP | `boards.py`, `tests/test_boards.py` | All three failure modes tested; `python -m pytest tests/` passes. |
| POLISH-001 | Implementer | LOW | `.gitignore` completeness — add `venv-web/`, `dist/`, `graphify-out/cache/`, `build/`, `__pycache__/`, `*.pyc`, `*.spec`. | pending | Phase 4 entry | `.gitignore` | After commit, `git status` does not show files in those paths. |
| POLISH-002 | Implementer | LOW | Remove tracked files from gitignored paths (single commit with POLISH-001). | pending | POLISH-001 | repo index | `git ls-files` shows no files in gitignored paths. |

---

## Backlog (out of sprint — see PLAN.md BACKLOG section)

| ID | Source |
|----|--------|
| BL-001 | Tauri port of React/Tailwind UI |
| BL-002 | Multi-board JSON schema validator |
| BL-003 | Automated UI rebuild hook |
| BL-004 | `main.py` removal |

---

## Recently completed (move here from Active when DONE)

(empty — populate as tasks close)

---

## Handoff index

(See `agents/handoffs/` for files. Format: `[role]-[YYYY-MM-DD-HHMM].md`.)

(empty — populate as sessions end.)
