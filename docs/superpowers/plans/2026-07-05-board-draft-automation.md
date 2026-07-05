# MiniMax Board-Draft Automation (sub-project B) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A GitHub Action that, when an add-a-board issue is opened, validates the attached submission, has MiniMax draft board support (registry entry + layout + best-effort adapter + notes), and opens a PR — never merged, human-verified on hardware before promotion.

**Architecture:** A stdlib MiniMax client (`tools/minimax_client.py`), a bot with pure testable helpers + a thin orchestrator (`tools/board_bot.py`) that shells out to `gh`, a prompt template (`tools/prompts/board_draft.md`), and the workflow (`.github/workflows/board-bot.yml`). Reuses A's `tools/board_submission.py` (validator) and `tools/validate_keymap.py` (layout check). No new runtime deps.

**Tech Stack:** Python 3.12 stdlib (`urllib`, `json`, `ast`, `re`, `subprocess`), GitHub Actions, `gh` CLI, pytest.

## Global Constraints

- **`MINIMAX_API_KEY` lives ONLY as an encrypted GitHub Actions secret**, read from the env by the bot. It is NEVER printed, logged, echoed, committed, or written to any file/PR/issue comment. The bot raises a clear error and exits non-zero if the key is absent. No key material in tests (tests mock the client).
- **The bot NEVER merges, force-pushes, or edits `main` directly.** It only creates a `board/<slug>` branch, opens a PR, and posts issue/PR comments.
- **Drafted boards are `status: "experimental"`.** Promotion to `supported` is a human action after on-hardware verification.
- **No new runtime dependencies** (stdlib only). Tests mock MiniMax + `gh` — no network, no key needed in CI.
- **Submission contract:** `aether-board-submission/1`, validated by `tools.board_submission.validate_submission` (reused from sub-project A).
- **Board artifacts:** registry entry keys `slug,name,vid,pid,usage_page,formFactor,protocol,keymap,capabilities,status`; layout shape `{_meta, type, keys[]}` (must pass `tools.validate_keymap.validate_keymap`).
- **Build B off `main`** (independent of the held `feature/in-app-board-submit` branch). Note: A's `tools/board_submission.py` is on that branch — Task 0 handles availability.

## File Structure

| File | Responsibility |
|---|---|
| `tools/minimax_client.py` (new) | `complete(prompt, *, model, key, base_url) -> str`. Stdlib urllib; key from env; never logs key. |
| `tools/board_bot.py` (new) | Pure helpers (`extract_json_block`, `extract_attachment_url`, `build_prompt`, `parse_model_output`, `sanity_check`) + `main(--issue)` orchestrator. |
| `tools/prompts/board_draft.md` (new) | The MiniMax drafting prompt (delimited-block output format). |
| `.github/workflows/board-bot.yml` (new) | Trigger on `issues:[opened]` + `workflow_dispatch`; runs the bot with the secret. |
| `tests/test_minimax_client.py` (new) | Client: key-missing raises; request built + response parsed (urlopen mocked). |
| `tests/test_board_bot.py` (new) | Pure helpers with mocks. |
| `README.md` (modify) | One line + a short "maintainers: set the MINIMAX_API_KEY secret" note. |

---

### Task 0: Branch + ensure the shared validator is present

**Files:** none (setup).

- [ ] **Step 1: Branch off main**

```bash
git checkout main
git checkout -b feature/board-draft-bot
```

- [ ] **Step 2: Ensure `tools/board_submission.py` exists on this branch**

`tools/board_submission.py` (the submission validator) was created in sub-project A on branch `feature/in-app-board-submit`. If it is not present on `main`:

Run: `test -f tools/board_submission.py && echo present || echo missing`
If `missing`: `git checkout feature/in-app-board-submit -- tools/board_submission.py tests/test_board_submission.py` then `git commit -m "chore: bring board_submission validator onto board-bot branch"`.
If `present`: nothing to do.

- [ ] **Step 3: Confirm the suite runs**

Run: `python -m pytest tests/ -q` (fallback `./venv-web/Scripts/python.exe -m pytest tests/ -q`)
Expected: all pass (existing tests, incl. board_submission if brought over).

---

### Task 1: MiniMax client

**Files:**
- Create: `tools/minimax_client.py`
- Test: `tests/test_minimax_client.py`

**Interfaces:**
- Produces: `complete(prompt: str, *, model=None, key=None, base_url=None, timeout=120) -> str`. Raises `RuntimeError("MINIMAX_API_KEY not set")` if no key. OpenAI-compatible chat-completions POST; returns `choices[0].message.content`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_minimax_client.py
import io, json, types
import tools.minimax_client as mc

def test_missing_key_raises(monkeypatch):
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    try:
        mc.complete("hi", key=None)
        assert False, "should have raised"
    except RuntimeError as e:
        assert "MINIMAX_API_KEY" in str(e)

def test_builds_request_and_parses(monkeypatch):
    captured = {}
    class FakeResp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False
    def fake_urlopen(req, timeout=0):
        captured["url"] = req.full_url
        captured["auth"] = req.headers.get("Authorization")
        captured["body"] = json.loads(req.data.decode())
        r = FakeResp(json.dumps({"choices": [{"message": {"content": "DRAFT"}}]}).encode())
        return r
    monkeypatch.setattr(mc.urllib.request, "urlopen", fake_urlopen)
    out = mc.complete("make a board", key="secret123", model="MiniMax-M3",
                      base_url="https://example.test/v1")
    assert out == "DRAFT"
    assert captured["url"] == "https://example.test/v1/chat/completions"
    assert captured["auth"] == "Bearer secret123"
    assert captured["body"]["model"] == "MiniMax-M3"
    assert captured["body"]["messages"][0]["content"] == "make a board"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_minimax_client.py -q`
Expected: FAIL — `ModuleNotFoundError: tools.minimax_client`.

- [ ] **Step 3: Implement**

```python
# tools/minimax_client.py
"""Thin MiniMax chat-completions client — stdlib only. Key from env; NEVER logged.

OpenAI-compatible request shape. Override endpoint/model via MINIMAX_BASE_URL /
MINIMAX_MODEL if MiniMax's API path differs from the default."""
import json
import os
import urllib.request

DEFAULT_MODEL = "MiniMax-M3"
DEFAULT_BASE = "https://api.minimax.chat/v1"


def complete(prompt, *, model=None, key=None, base_url=None, timeout=120):
    key = key or os.environ.get("MINIMAX_API_KEY")
    if not key:
        raise RuntimeError("MINIMAX_API_KEY not set")
    model = model or os.environ.get("MINIMAX_MODEL", DEFAULT_MODEL)
    base = (base_url or os.environ.get("MINIMAX_BASE_URL", DEFAULT_BASE)).rstrip("/")
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    req = urllib.request.Request(
        base + "/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_minimax_client.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add tools/minimax_client.py tests/test_minimax_client.py
git commit -m "feat(bot): stdlib MiniMax client (key from env, never logged)"
```

---

### Task 2: Bot input helpers (extract submission + build prompt)

**Files:**
- Create: `tools/board_bot.py` (input helpers only this task), `tools/prompts/board_draft.md`
- Test: `tests/test_board_bot.py`

**Interfaces:**
- Produces: `extract_json_block(body: str) -> dict | None` (parses a ```json fenced block to a dict); `extract_attachment_url(body: str) -> str | None` (first `https://…/*.json` link); `build_prompt(submission: dict, template: str) -> str` (template + the submission JSON).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_board_bot.py
import tools.board_bot as bot

def test_extract_json_block():
    body = 'intro\n```json\n{"schema": "aether-board-submission/1", "meta": {}}\n```\nend'
    d = bot.extract_json_block(body)
    assert d and d["schema"] == "aether-board-submission/1"

def test_extract_json_block_none():
    assert bot.extract_json_block("no code here") is None

def test_extract_attachment_url():
    body = "see file [board.json](https://github.com/x/files/1/board.json) attached"
    assert bot.extract_attachment_url(body) == "https://github.com/x/files/1/board.json"

def test_extract_attachment_url_none():
    assert bot.extract_attachment_url("no links") is None

def test_build_prompt_includes_submission():
    p = bot.build_prompt({"meta": {"brand": "Aula"}}, "TEMPLATE:\n{submission}")
    assert "TEMPLATE:" in p and "Aula" in p
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_board_bot.py -q`
Expected: FAIL — `ModuleNotFoundError: tools.board_bot`.

- [ ] **Step 3: Implement the helpers + prompt template**

`tools/board_bot.py`:
```python
"""Board-draft bot: validate a submission, have MiniMax draft board support, open
a PR. NEVER merges; NEVER logs the API key. Pure helpers here are unit-tested;
main() shells out to `gh`."""
import json
import re

_JSON_BLOCK = re.compile(r"```json\s*(\{.*?\})\s*```", re.S)
_JSON_URL = re.compile(r"https://[^\s)\"']+\.json")


def extract_json_block(body):
    """Return the dict from the first ```json fenced block, or None."""
    m = _JSON_BLOCK.search(body or "")
    if not m:
        return None
    try:
        d = json.loads(m.group(1))
        return d if isinstance(d, dict) else None
    except Exception:
        return None


def extract_attachment_url(body):
    """Return the first https URL ending in .json, or None."""
    m = _JSON_URL.search(body or "")
    return m.group(0) if m else None


def build_prompt(submission, template):
    """Fill the drafting template with the submission JSON."""
    return template.replace("{submission}", json.dumps(submission, indent=2))
```

`tools/prompts/board_draft.md`:
```markdown
You are drafting keyboard support for the AetherHE controller from a hardware
submission. Output ONLY the four delimited blocks below — no prose outside them.

Submission (schema aether-board-submission/1):
{submission}

Board model: infer a filesystem-safe kebab-case slug from meta.brand + meta.model.
The registry entry MUST have status "experimental". The layout must be shape
{"_meta":..., "type":..., "keys":[...]} sized from meta.size / size_template.
The protocol adapter is BEST-EFFORT from the input_capture reports (input side
only; you cannot know lighting/output commands unless a pcap was attached — say so
in the notes rather than guessing output bytes). Mark the adapter AI-DRAFTED/UNVERIFIED.

=== FILE: registry_entry.json ===
<the single board object to append to data/board_registry.json's "boards" array>
=== FILE: layout.json ===
<the ui/layouts/<slug>.json content>
=== FILE: protocol_adapter.py ===
<the protocol_<slug>.py content, commented AI-DRAFTED — UNVERIFIED>
=== FILE: DECODE_NOTES.md ===
<your analysis: what you inferred, confidence, and exactly what a human must verify on hardware>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_board_bot.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add tools/board_bot.py tools/prompts/board_draft.md tests/test_board_bot.py
git commit -m "feat(bot): submission extraction + prompt building + draft template"
```

---

### Task 3: Bot output helpers (parse model output + sanity check)

**Files:**
- Modify: `tools/board_bot.py`
- Test: `tests/test_board_bot.py`

**Interfaces:**
- Consumes: `tools.validate_keymap.validate_keymap`.
- Produces: `parse_model_output(text: str) -> dict` with keys `registry` (dict|None), `layout` (dict|None), `adapter` (str), `notes` (str); `sanity_check(artifacts: dict, existing_slugs: set) -> list[str]` (empty = ok).

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_board_bot.py
_MODEL_OUT = '''
=== FILE: registry_entry.json ===
{"slug": "acme-60", "name": "Acme 60", "vid": "0x1", "pid": "0x2",
 "usage_page": "0xFF1B", "formFactor": "60%", "protocol": "protocol_acme_60",
 "keymap": "ui/layouts/acme-60.json",
 "capabilities": {"actuation": true, "lighting": false, "perKeyRgb": false},
 "status": "experimental"}
=== FILE: layout.json ===
{"_meta": {"board": "acme-60"}, "type": "60", "keys": [{"index": 0, "code": "KeyA", "x": 0, "y": 0}]}
=== FILE: protocol_adapter.py ===
# AI-DRAFTED - UNVERIFIED
def build(): return b""
=== FILE: DECODE_NOTES.md ===
Inferred input reports only. Lighting unknown (no pcap).
'''

def test_parse_model_output():
    a = bot.parse_model_output(_MODEL_OUT)
    assert a["registry"]["slug"] == "acme-60"
    assert a["registry"]["status"] == "experimental"
    assert a["layout"]["type"] == "60"
    assert "def build" in a["adapter"]
    assert "Lighting unknown" in a["notes"]

def test_sanity_check_ok():
    a = bot.parse_model_output(_MODEL_OUT)
    assert bot.sanity_check(a, existing_slugs=set()) == []

def test_sanity_check_dup_slug():
    a = bot.parse_model_output(_MODEL_OUT)
    errs = bot.sanity_check(a, existing_slugs={"acme-60"})
    assert any("slug" in e for e in errs)

def test_sanity_check_bad_status():
    a = bot.parse_model_output(_MODEL_OUT)
    a["registry"]["status"] = "supported"
    assert any("experimental" in e for e in bot.sanity_check(a, set()))

def test_sanity_check_unparseable_adapter_not_fatal():
    a = bot.parse_model_output(_MODEL_OUT)
    a["adapter"] = "def (:::"   # invalid python
    errs = bot.sanity_check(a, set())
    assert any("adapter" in e.lower() for e in errs)  # reported, but caller treats as non-fatal
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_board_bot.py -q`
Expected: FAIL — `AttributeError: module 'tools.board_bot' has no attribute 'parse_model_output'`.

- [ ] **Step 3: Implement**

Add to `tools/board_bot.py` (top: `import ast`, `import os`, `import sys`; and import the sibling validators):
```python
import ast
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # tools/ on path
from validate_keymap import validate_keymap  # noqa: E402

_FILE_BLOCK = re.compile(r"=== FILE: (?P<name>[^\n=]+?) ===\n(?P<body>.*?)(?=\n=== FILE:|\Z)", re.S)
_REQUIRED_ENTRY_KEYS = {"slug", "name", "vid", "pid", "usage_page", "formFactor",
                        "protocol", "keymap", "capabilities", "status"}
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def parse_model_output(text):
    blocks = {m.group("name").strip(): m.group("body").strip()
              for m in _FILE_BLOCK.finditer(text or "")}
    def as_json(name):
        raw = blocks.get(name)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return None
    return {
        "registry": as_json("registry_entry.json"),
        "layout": as_json("layout.json"),
        "adapter": blocks.get("protocol_adapter.py", ""),
        "notes": blocks.get("DECODE_NOTES.md", ""),
    }


def sanity_check(artifacts, existing_slugs):
    e = []
    reg = artifacts.get("registry")
    if not isinstance(reg, dict):
        e.append("registry_entry.json missing or not an object")
    else:
        missing = _REQUIRED_ENTRY_KEYS - set(reg)
        if missing:
            e.append(f"registry entry missing keys: {sorted(missing)}")
        if reg.get("status") != "experimental":
            e.append('registry entry status must be "experimental"')
        slug = reg.get("slug", "")
        if not _SLUG_RE.match(str(slug)):
            e.append(f"slug not filesystem-safe kebab-case: {slug!r}")
        elif slug in existing_slugs:
            e.append(f"slug already exists: {slug}")
    layout = artifacts.get("layout")
    if not isinstance(layout, dict):
        e.append("layout.json missing or not an object")
    else:
        e += [f"layout: {m}" for m in validate_keymap(layout)]
    if artifacts.get("adapter"):
        try:
            ast.parse(artifacts["adapter"])
        except SyntaxError as ex:
            e.append(f"adapter has a python syntax error (non-fatal, flag in PR): {ex}")
    return e
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_board_bot.py -q`
Expected: PASS (all board_bot tests).

- [ ] **Step 5: Commit**

```bash
git add tools/board_bot.py tests/test_board_bot.py
git commit -m "feat(bot): parse model output + sanity-check drafted artifacts"
```

---

### Task 4: Bot orchestrator (main --issue)

**Files:**
- Modify: `tools/board_bot.py` (add `main`, `_gh`, `_run`)
- Test: `tests/test_board_bot.py`

**Interfaces:**
- Consumes: all helpers above, `tools.board_submission.validate_submission`, `tools.minimax_client.complete`.
- Produces: `run(issue_number, *, gh, complete, write_files, repo_root) -> dict` — the testable core with injected side-effects; `main()` = argparse wrapper wiring real `gh`/`complete`.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_board_bot.py
def test_run_happy_path(tmp_path, monkeypatch):
    # existing registry with no boards
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "board_registry.json").write_text('{"boards": []}')
    (tmp_path / "ui" / "layouts").mkdir(parents=True)
    calls = {"pr": None, "comment": None}
    def fake_gh(args):
        if args[:2] == ["issue", "view"]:
            return '{"number": 9, "title": "t", "body": "```json\\n' + \
                   '{\\"schema\\":\\"aether-board-submission/1\\",\\"device\\":{\\"vid\\":\\"0x1\\",\\"pid\\":\\"0x2\\"},' + \
                   '\\"meta\\":{\\"brand\\":\\"Acme\\",\\"model\\":\\"60\\",\\"size\\":\\"60\\"},\\"input_capture\\":{\\"reports\\":[]}}\\n```"}'
        if args[0] == "pr":
            calls["pr"] = args; return "https://github.com/x/pull/3"
        if args[:2] == ["issue", "comment"]:
            calls["comment"] = args; return ""
        return ""
    monkeypatch.setattr(bot, "_read_prompt", lambda: "T {submission}")
    res = bot.run(9, gh=fake_gh, complete=lambda p: _MODEL_OUT, repo_root=str(tmp_path))
    assert res["ok"] is True and res["pr_url"] == "https://github.com/x/pull/3"
    assert (tmp_path / "ui" / "layouts" / "acme-60.json").exists()
    assert (tmp_path / "protocol_acme_60.py").exists()
    assert calls["comment"] is not None   # commented the PR link on the issue

def test_run_invalid_submission_comments_no_pr(tmp_path, monkeypatch):
    def fake_gh(args):
        if args[:2] == ["issue", "view"]:
            return '{"number": 9, "title": "t", "body": "```json\\n{\\"schema\\":\\"wrong\\"}\\n```"}'
        return ""
    monkeypatch.setattr(bot, "_read_prompt", lambda: "T {submission}")
    res = bot.run(9, gh=fake_gh, complete=lambda p: "", repo_root=str(tmp_path))
    assert res["ok"] is False and res["pr_url"] is None
    assert "invalid" in res["reason"].lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_board_bot.py -k run -q`
Expected: FAIL — `AttributeError: ... 'run'`.

- [ ] **Step 3: Implement**

Add to `tools/board_bot.py` (top: `import argparse`, `import subprocess`; and the submission validator + minimax import guarded):
```python
import argparse
import subprocess

from board_submission import validate_submission  # noqa: E402 (tools/ already on path)


def _run(cmd):
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout


def _gh(args):
    return _run(["gh"] + args)


def _read_prompt():
    here = os.path.dirname(os.path.abspath(__file__))
    return open(os.path.join(here, "prompts", "board_draft.md"), encoding="utf-8").read()


def run(issue_number, *, gh, complete, repo_root):
    """Testable core. gh(args)->stdout, complete(prompt)->text are injected."""
    issue = json.loads(gh(["issue", "view", str(issue_number), "--json", "number,title,body"]))
    body = issue.get("body", "")
    sub = extract_json_block(body)
    if sub is None:
        url = extract_attachment_url(body)
        if url:
            import urllib.request
            sub = json.loads(urllib.request.urlopen(url, timeout=60).read().decode("utf-8"))
    if not isinstance(sub, dict):
        gh(["issue", "comment", str(issue_number), "--body",
            "Automated draft: no submission JSON found. Please attach the file the app generated."])
        return {"ok": False, "pr_url": None, "reason": "no submission found"}
    errs = validate_submission(sub)
    if errs:
        gh(["issue", "comment", str(issue_number), "--body",
            "Automated draft: submission is invalid:\n- " + "\n- ".join(errs)])
        return {"ok": False, "pr_url": None, "reason": "invalid submission"}

    artifacts = parse_model_output(complete(build_prompt(sub, _read_prompt())))
    reg_path = os.path.join(repo_root, "data", "board_registry.json")
    existing = set()
    try:
        existing = {b.get("slug") for b in json.load(open(reg_path)).get("boards", [])}
    except Exception:
        pass
    problems = sanity_check(artifacts, existing)
    hard = [p for p in problems if "syntax error" not in p]   # adapter syntax = non-fatal
    if hard:
        gh(["issue", "comment", str(issue_number), "--body",
            "Automated draft could not produce a clean board:\n- " + "\n- ".join(hard)])
        return {"ok": False, "pr_url": None, "reason": "sanity failed"}

    slug = artifacts["registry"]["slug"]
    # write files
    reg = json.load(open(reg_path))
    reg["boards"].append(artifacts["registry"])
    json.dump(reg, open(reg_path, "w"), indent=2)
    lay_path = os.path.join(repo_root, "ui", "layouts", f"{slug}.json")
    os.makedirs(os.path.dirname(lay_path), exist_ok=True)
    json.dump(artifacts["layout"], open(lay_path, "w"), indent=2)
    open(os.path.join(repo_root, f"protocol_{slug.replace('-', '_')}.py"), "w",
         encoding="utf-8").write(artifacts["adapter"])
    notes = artifacts["notes"] + ("\n\n> NOTE: adapter has a syntax error — needs a human fix."
                                  if any("syntax error" in p for p in problems) else "")
    open(os.path.join(repo_root, "DECODE_NOTES.md"), "w", encoding="utf-8").write(notes)

    branch = f"board/{slug}"
    _run(["git", "checkout", "-b", branch])
    _run(["git", "add", "-A"])
    _run(["git", "commit", "-m", f"draft(board): {slug} (AI-DRAFTED, experimental) — closes #{issue_number}"])
    _run(["git", "push", "-u", "origin", branch])
    pr_url = gh(["pr", "create", "--title", f"Draft board: {slug} (experimental)",
                 "--body", f"AI-drafted from #{issue_number}. UNVERIFIED — verify on hardware before promoting to supported. See DECODE_NOTES.md.",
                 "--label", "experimental", "--head", branch]).strip()
    gh(["issue", "comment", str(issue_number), "--body", f"Automated draft opened: {pr_url}"])
    return {"ok": True, "pr_url": pr_url, "reason": "ok"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--issue", type=int, required=True)
    args = ap.parse_args()
    from minimax_client import complete as mm_complete   # env key; raises if absent
    res = run(args.issue, gh=_gh, complete=mm_complete, repo_root=os.getcwd())
    print("result:", res["reason"])   # never prints the key


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_board_bot.py -q`
Expected: PASS (all board_bot tests, incl. the two `run` tests).

- [ ] **Step 5: Commit**

```bash
git add tools/board_bot.py tests/test_board_bot.py
git commit -m "feat(bot): orchestrator run(--issue) — validate, draft, open PR (never merge)"
```

---

### Task 5: Workflow + maintainer docs

**Files:**
- Create: `.github/workflows/board-bot.yml`
- Modify: `README.md`

- [ ] **Step 1: Create the workflow**

```yaml
# .github/workflows/board-bot.yml
name: Board draft bot

on:
  issues:
    types: [opened]
  workflow_dispatch:
    inputs:
      issue:
        description: "Issue number to draft"
        required: true

permissions:
  contents: write
  pull-requests: write
  issues: write

jobs:
  draft:
    # Only run for add-a-board submissions (label or template marker in the title).
    if: >
      github.event_name == 'workflow_dispatch' ||
      contains(github.event.issue.title, '[Board]') ||
      contains(toJSON(github.event.issue.labels.*.name), 'add-a-board')
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Draft board support
        env:
          MINIMAX_API_KEY: ${{ secrets.MINIMAX_API_KEY }}
          GH_TOKEN: ${{ github.token }}
          ISSUE: ${{ github.event.issue.number || github.event.inputs.issue }}
        run: |
          git config user.name "aether-board-bot"
          git config user.email "bot@users.noreply.github.com"
          python tools/board_bot.py --issue "$ISSUE"
```

- [ ] **Step 2: Add maintainer docs to README**

Add a short subsection under the board-submission area:
```markdown
### Automated board drafting (maintainers)
New **add-a-board** issues trigger `.github/workflows/board-bot.yml`, which validates the
attached submission and uses MiniMax to open a **draft PR** (`experimental`) with a registry
entry, layout, best-effort protocol adapter, and `DECODE_NOTES.md`. **It never merges** —
verify the adapter on real hardware, flip `experimental`→`supported`, then merge.
Setup: add a repo secret **`MINIMAX_API_KEY`** (Settings → Secrets → Actions). Optional:
`MINIMAX_MODEL` / `MINIMAX_BASE_URL` repo variables if your endpoint differs from the default.
```

- [ ] **Step 3: Validate the workflow YAML parses**

Run: `python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/board-bot.yml')); print('yaml ok')"`
(If pyyaml is unavailable, use: `python -c "import json,subprocess; print('skip - yaml lib absent')"` and instead confirm `gh workflow list` shows it after push.)
Expected: `yaml ok`.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/board-bot.yml README.md
git commit -m "feat(bot): board-draft workflow (issue-triggered) + maintainer docs"
```

---

### Task 6: Integration + key-security verify

**Files:** none (verification).

- [ ] **Step 1: Full suite**

Run: `python -m pytest tests/ -q`
Expected: all pass (existing + minimax_client + board_bot).

- [ ] **Step 2: Key never logged/committed**

Run: `grep -rniE "print\(.*key|log.*key|MINIMAX_API_KEY" tools/board_bot.py tools/minimax_client.py`
Expected: the ONLY `MINIMAX_API_KEY` references are `os.environ.get("MINIMAX_API_KEY")` (client) and the `RuntimeError` string — NO print/log of the key value. `main()` prints only `res["reason"]`. Confirm and report.

- [ ] **Step 3: No auto-merge anywhere**

Run: `grep -rniE "pr merge|gh pr merge|--merge|--auto|merge --" tools/board_bot.py .github/workflows/board-bot.yml`
Expected: NO matches (the bot never merges).

- [ ] **Step 4: Commit (if README/notes touched) and report**

```bash
git commit -am "chore(bot): integration verified — suite green, key never logged, no auto-merge" --allow-empty
```

- [ ] **Step 5: Live dry-run (owner, manual — not automated here)**

After adding the `MINIMAX_API_KEY` secret, trigger `workflow_dispatch` with a real test issue number and confirm: submission validated, a `board/<slug>` PR opened (`experimental`), issue commented, and NOTHING merged. Fix the MiniMax endpoint/model env if the API path differs.

---

## Self-Review Notes

- **Spec coverage:** trigger/flow (Tasks 4+5); components minimax_client (1) / board_bot helpers (2,3) / orchestrator (4) / workflow (5) / prompt (2); key-security (Global Constraints + Task 6 step 2); sanity checks (3); never-merge gate (4 + Task 6 step 3); error handling — invalid/no submission/malformed (4, tested); testing with mocks (1-4). All spec sections mapped.
- **Key security:** structurally enforced — key only via `os.environ` in the client, never printed; Task 6 step 2 greps to prove it; tests never use a real key (client mocked / `complete` injected).
- **Type consistency:** `run(issue, *, gh, complete, repo_root)`, `parse_model_output`→`{registry,layout,adapter,notes}`, `sanity_check(artifacts, existing_slugs)`, `complete(prompt,...)`, `validate_submission` — names consistent across tasks.
- **Note:** MiniMax endpoint/model are env-configurable (defaults `MiniMax-M3` / `api.minimax.chat/v1`); the owner confirms the real path in the Task 6 live dry-run — the code doesn't hard-fail on the default being wrong until a live call.
