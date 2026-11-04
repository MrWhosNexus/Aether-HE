# Community submissions: intake plan and security gate (2026-11-04)

After v0.6.1, WIN 68-class owners sent forks, a PR and issues. This plan says
what to do with each and how outside code gets in without becoming a way to
attack users. Everything below was reviewed by reading the code; no fork or PR
code was run.

## 1. What came in

| Source | What it is | Security read | Verdict |
|---|---|---|---|
| nieruuu19 fork (2 commits, 115 behind) | WIN 68 HE **Max** (1CA2:1901) via a new `protocol_sparkplay.py` (1,420 lines) + layout, Basic/Continuous RT; rewrites `app_web.py`/`aula_device.py`; ships ~22k lines of prebuilt JS and a rebuilt `index_runtime.html`; commits a personal `user_deadband_memory.json` | No network, no `eval`/`exec`, no extra `subprocess`, no obfuscation in its Python. JS bundles: no `fetch`/XHR/WebSocket/`eval`/raw-HTML sinks (they are Tailwind + the Aether build). | **Port, don't merge.** Take `protocol_sparkplay.py` + the layout as a new driver; never take its built files or its core-file rewrites (they are based on a 115-commit-old tree). |
| #20, #12, #27 (WIN 68 HE Standard) | Same VID:PID (2E3C:C365) and protocol as the Win60; #12 confirms everything works except the extra keys are missing; #20 attached an in-app capture; BARDIA156 (#27) offers to test | Data only | **Add the 68 layout**, keep `bringup`, promote after BARDIA156 runs the hardware checklist. |
| xpLayA fork | A Rust rewrite for the F75 HE; deletes the release/submission workflows; adds a GPL-3.0 `LICENSE` | Not proposed as a PR | **Reference only** for the F75 protocol. It relicenses code that upstream never licensed: needs the license decision (section 4). |
| PR #15 (Fatalist0001, July) | Subtype-3 raw_adc frames for instant release; 129 behind | No risky calls; `.spec` change only strips comments | Ask for a rebase or close with thanks: v0.6.1's travel fixes overlap it. |

## 2. Rules every outside contribution must pass

1. **No built output.** `ui/index_runtime.html`, `ui/runtime_src/build/**`, bundles, and the installer/spec are produced by our CI, never accepted from a PR.
2. **Protocol code is boring code.** `protocol_*.py` and `drivers/**` may not import `subprocess`, `socket`, `urllib`, `requests`, `ctypes`, `pickle`/`marshal`, or call `eval`/`exec`/`compile`/`__import__`, or read/write files. Enforced by a CI scan (allowlist of imports).
3. **The guards stay.** `send_raw`'s `dangerous_command_reason` check, the fixed driver dispatch table in `drivers/__init__.py` (a registry entry can never name a module to import), the no-raw-HTML UI rule.
4. **Fakes-only tests** for every new driver, like `tests/test_travel_release.py`.
5. **Dependency changes** (`requirements.txt`, `.spec`, `installer.iss`) need a maintainer review and a `pip-audit` run.
6. **Owner-only paths** (CODEOWNERS + branch protection on `main`, one approving review): `.github/**`, `updater.py`, `service/**`, `AetherHE.spec`, `installer.iss`, `requirements.txt`, `version.py`, `drivers/__init__.py`.
7. Hardware testers get builds from our CI artifacts, never from a contributor's fork.

## 3. Pipeline holes to close

| # | Hole | Risk | Fix |
|---|---|---|---|
| A | **Board bot** (`board-bot.yml` → `tools/board_bot.py`) runs on ANY issue titled `[Board]`, sends the issue text to MiniMax, and commits the model's Python `adapter` to a repo branch + PR with a write token. | Prompt injection: an attacker writes an issue that makes the model emit a malicious adapter; it lands as a bot-authored "experimental" PR that looks trustworthy. Anyone can also burn the MiniMax key. | Trigger only when a maintainer adds a `bot-draft` label. Commit **data only** (registry entry + layout); post the drafted adapter as a fenced text block in the PR body, never as a `.py` file. Add the rule-2 scan to its PRs. |
| B | **Updater** `Api.apply_update(asset_url, …, asset_sha256)` trusts the URL and checksum handed in from the UI. | Any UI script injection becomes "download and run this exe". | `apply_update` ignores caller values: re-runs `check_for_update()`, requires an https URL under `github.com/MrWhosNexus/Aether-HE/releases/download/` (or its asset CDN redirect), and verifies the release's own digest. |
| C | **`open_submission_url(url)`** opens any URL/scheme the UI passes. | `file:`/custom-scheme launch from an injected script. | Allow only `https://github.com/MrWhosNexus/Aether-HE/issues/new?…`. |
| D | `validate-submissions.yml` does not run for `data/board_registry.json`, `ui/layouts/**`, `protocol_*.py`, `drivers/**`. | Board PRs skip the checks. | Add those paths and the rule-2 scan job. |
| E | No CODEOWNERS / branch protection. | A push to `main` or a tag ships to every user via the updater. | Section 2 rule 6; require review before release tags. |

B, C and the bot were "do not touch" during the roadmap run; changing them needs the owner's OK.

## 4. Decisions only the owner can make

1. **License** (#30, #27): none exists, so nobody may legally reuse or contribute code, and the xpLayA fork's GPL label has no basis. Pick one (MIT, GPL-3.0, or source-available) and add a contributor sign-off (DCO) before merging outside code.
2. Approve fixes A-C (they touch frozen files).
3. Order: suggested **3A-C → 2 (CI gate) → WIN 68 HE Standard layout → WIN 68 HE Max port → F75**.

## 5. Order of work

1. Close the holes: bot (A), updater (B), submission URL (C), CI paths + scan (D), CODEOWNERS (E). One PR, tests with fakes.
2. WIN 68 HE Standard: layout from #20's capture; BARDIA156 runs `docs/HARDWARE_TEST_CHECKLIST.md`; promote to supported.
3. WIN 68 HE Max: port `protocol_sparkplay.py` into a `drivers/` driver against current `main`, credit nieruuu19, review it line by line against rule 2, `bringup` until hardware-checked.
4. Reply on #7, #12, #20, #27, #30 and PR #15 with what happens next.
