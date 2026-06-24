# Provisional board layouts (staging)

Scaffolded `keymap.json` files for boards submitted via GitHub issues but **not yet
brought up on hardware**. They exist so each board's layout can be drawn and reviewed
ahead of the multi-board registry refactor; the live app still loads `ui/keymap.json`.

Each file carries a `_meta` block (board, VID/PID, protocol family, source issues,
status). **`provisionalIndices: true` means the firmware `index` values are a starting
hypothesis** (carried over from the Aula Win60, stride 22) — they MUST be confirmed
from per-key travel reports during bring-up before lighting/actuation will address the
right keys.

| File | Board | VID:PID | Size | Source issue(s) |
|------|-------|---------|------|-----------------|
| `aula-mini60he-max.json` | Aula MINI60HE Max | 0C45:80A1 | 60% | #4 (+#1 dup) |
| `aula-win60he-max.json`  | Aula Win60 HE Max | 1CA2:1902 | 60% | #5 |
| `aula-mini60he-pro.json` | Aula Mini 60 HE Pro | 0C45:FEFE | 60% | #6 |
| `aula-win68he-max.json`  | Aula win68 HE Max | 1CA2:1901 | 65% | #7 |

All files pass `python tools/validate_keymap.py ui/layouts/*.json`.

The 60% boards clone the verified Aula Win60 ANSI geometry. The 65% `win68` extends it
with a Del/PgUp/PgDn right column + inverted-T arrow cluster as a **standard** ANSI 65%
arrangement — verify the exact key placement against the issue #7 photos at bring-up.
