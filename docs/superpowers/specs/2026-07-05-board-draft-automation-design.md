# MiniMax Board-Draft Automation — Design (sub-project B)

**Date:** 2026-07-05
**Status:** Approved (design), pending spec review → implementation plan
**Relationship:** Part 2 of 2. **A** = in-app "Submit your board" (shipped: builds a submission
JSON, opens a pre-filled add-a-board issue). **B** (this doc) = owner-side automation that turns
a submission into a review-ready PR. The **submission JSON (`aether-board-submission/1`) is the
contract** from A; `tools/board_submission.py` (from A) is reused to validate it.

## Goal

When a user opens an add-a-board GitHub issue with a submission file attached, automatically
draft board support (registry entry + layout + best-effort protocol adapter + decode notes) via
MiniMax and open a PR — **never merged**, always human-verified on hardware before a board is
promoted to `supported`.

## Locked decisions (from brainstorm)

1. **Runtime = GitHub Actions + encrypted secret.** A workflow triggers on new add-a-board
   issues; `MINIMAX_API_KEY` is a GitHub Actions secret. No local machine to keep running.
2. **Draft scope = everything.** Registry entry + layout JSON + a best-effort `protocol_<slug>.py`
   + `DECODE_NOTES.md` (MiniMax's analysis). PR opens marked `status: experimental`.
3. **Verify gate = PR never auto-merges.** The owner pulls the branch, tests the adapter on the
   real board, fixes as needed, flips `experimental→supported`, and merges. Experimental/
   unverified adapters never reach end users.

## Key-security constraint (non-negotiable)

- `MINIMAX_API_KEY` lives **only** as an encrypted GitHub Actions secret, passed to the bot as an
  environment variable. It is never echoed, logged, printed, committed, or written to any file or
  PR. The bot refuses to run (clear error) if the env var is absent.
- Nothing key-related exists in the app/client (that's sub-project A's guarantee, already verified).

## Trigger & data flow

```
add-a-board issue opened (template/label)
  -> .github/workflows/board-bot.yml runs on ubuntu-latest
     env: MINIMAX_API_KEY (secret), GITHUB_TOKEN (default), ISSUE_NUMBER (from event)
  -> python tools/board_bot.py --issue <n>
       1. Fetch issue body via `gh issue view <n> --json body,title,number,labels`.
       2. Locate the submission JSON: first a GitHub attachment link to a *.json in the body
          (github user-content URL), else a ```json fenced block. Download/parse it.
       3. Validate via board_submission.validate_submission(). If invalid ->
          `gh issue comment` with the errors, exit 0 (no PR).
       4. Build the MiniMax prompt(s) from device + meta + size_template + input_capture.reports
          + output_pcap presence (from tools/prompts/*).
       5. Call MiniMax (tools/minimax_client). Parse the response into 4 artifacts.
       6. Sanity-check the artifacts (see below). If any hard-fails -> comment + exit 0 (no PR).
       7. Create branch `board/<slug>`, write files, commit, `gh pr create` (draft/labeled
          experimental) linking the issue. NEVER merge.
       8. `gh issue comment` with the PR link.
```

## Components (each one job)

| File | Responsibility |
|---|---|
| `.github/workflows/board-bot.yml` (new) | Trigger on `issues: [opened]` (+ `workflow_dispatch` with an `issue` input for manual/dry runs); checkout; setup-python; run `tools/board_bot.py --issue ${{ github.event.issue.number }}` with `MINIMAX_API_KEY` from secrets and `GH_TOKEN` from the default token. `permissions: contents: write, pull-requests: write, issues: write`. |
| `tools/board_bot.py` (new) | Orchestrator + pure helpers: `extract_submission(issue_body)->dict|None`, `build_prompt(sub)->str`, `parse_model_output(text)->{registry,layout,adapter,notes}`, `sanity_check(artifacts)->list[str]`, plus the `main(--issue)` glue that calls `gh` and `minimax_client`. |
| `tools/minimax_client.py` (new) | `complete(prompt, *, model=env MINIMAX_MODEL or "MiniMax-M3", key=env MINIMAX_API_KEY) -> str`. Stdlib `urllib` only; OpenAI-compatible chat-completions POST to the MiniMax endpoint (`MINIMAX_BASE_URL` env, default the MiniMax chat API). Raises `RuntimeError("MINIMAX_API_KEY not set")` if key missing. Never logs the key. |
| `tools/prompts/board_draft.md` (new) | The drafting prompt template: given the submission, produce the 4 artifacts in a parseable delimited format (e.g. `=== FILE: data/board_registry.json entry ===` blocks). |
| `tests/test_board_bot.py` (new) | Unit tests for the pure helpers with mocked MiniMax + mocked `gh`. |

## Output artifacts (what lands in the PR)

- `data/board_registry.json` — the new board object appended to `boards[]`, `status: "experimental"`,
  with `slug/name/vid/pid/usage_page/formFactor/protocol/keymap/capabilities`. (`protocol` names the
  new adapter module; `keymap` points at the new layout file.)
- `ui/layouts/<slug>.json` — layout of shape `{_meta, type, keys[]}`, derived from `size_template`
  and refined by MiniMax.
- `protocol_<slug>.py` — best-effort adapter (clearly commented "AI-DRAFTED — UNVERIFIED, needs
  on-hardware validation").
- `DECODE_NOTES.md` — MiniMax's analysis of the captures: what it inferred, confidence, and what a
  human must verify (especially lighting/output, which is unavailable without a pcap).

## Sanity checks (bot-side, before opening a PR)

- Submission validates (`board_submission.validate_submission` == []).
- Registry entry is JSON, has the required keys, `status == "experimental"`, `slug` is filesystem-safe
  and unique (not already in `boards[]`).
- Layout JSON parses and passes `tools/validate_keymap.validate_keymap` (reuse the existing validator).
- `protocol_<slug>.py` passes `ast.parse` (syntactically valid Python). A parse failure does NOT block
  the PR but is flagged loudly in `DECODE_NOTES.md` and the PR body.
- If the *submission* is invalid or MiniMax returns unparseable output → comment on the issue, exit 0,
  no PR (never open a broken PR).

## Error handling

- Missing `MINIMAX_API_KEY` → bot exits non-zero with a clear message (fails the Action visibly; no
  partial work).
- No submission file found in the issue → comment asking the user to attach the file, exit 0.
- MiniMax HTTP/parse error → comment "automated draft failed, a maintainer will follow up", exit 0.
- The bot never merges, never force-pushes, never edits `main` directly (only its `board/<slug>` branch
  + issue/PR comments).

## Testing

- Unit tests (mocked): `extract_submission` (attachment URL, fenced block, none), `parse_model_output`
  (well-formed + malformed), `sanity_check` (valid entry, dup slug, bad layout, unparseable adapter),
  and `build_prompt` (includes device + reports). MiniMax + `gh` are mocked — no network, no key needed
  in CI tests.
- Live path: `workflow_dispatch` with an `issue` input against a real test issue, once, to confirm the
  end-to-end draft + PR (uses the real secret; run by the owner).

## Non-goals

- No auto-merge, ever. No promotion to `supported` by the bot.
- No writing to a physical device (B runs in CI; it only reads the submission and writes files).
- No lighting/output protocol synthesis when no pcap is attached — MiniMax says so in the notes rather
  than guessing output bytes.
- Not a general LLM framework — one narrow MiniMax call for board drafting.
