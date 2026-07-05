"""Board-draft bot: validate a submission, have MiniMax draft board support, open
a PR. NEVER merges; NEVER logs the API key. Pure helpers here are unit-tested;
main() shells out to `gh`."""
import argparse
import ast
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # tools/ on path
from validate_keymap import validate_keymap  # noqa: E402
from board_submission import validate_submission  # noqa: E402

_JSON_BLOCK = re.compile(r"```json\s*(\{.*?\})\s*```", re.S)
_JSON_URL = re.compile(r"https://[^\s)\"']+\.json")
_FILE_BLOCK = re.compile(r"=== FILE: (?P<name>[^\n=]+?) ===\n(?P<body>.*?)(?=\n=== FILE:|\Z)", re.S)
_REQUIRED_ENTRY_KEYS = {"slug", "name", "vid", "pid", "usage_page", "formFactor",
                        "protocol", "keymap", "capabilities", "status"}
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


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


def parse_model_output(text):
    """Parse MiniMax's === FILE: name === delimited output into artifacts."""
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
    """Validate drafted artifacts. Returns a list of human-readable errors (empty = ok)."""
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


def _run(cmd, cwd=None):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, cwd=cwd).stdout


def _gh(args):
    return _run(["gh"] + args)


def _read_prompt():
    here = os.path.dirname(os.path.abspath(__file__))
    return open(os.path.join(here, "prompts", "board_draft.md"), encoding="utf-8").read()


def run(issue_number, *, gh, complete, repo_root):
    """Testable core. gh(args)->stdout, complete(prompt)->text are injected.
    NEVER merges, force-pushes, or touches main directly — only creates
    branch board/<slug> and opens a PR via `gh pr create`."""
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
    # Only do real git ops when repo_root is an actual git checkout (production).
    # In tests repo_root is a bare tmp_path with no .git, so this is skipped —
    # keeps tests hermetic and never risks running git against the real repo cwd.
    if os.path.isdir(os.path.join(repo_root, ".git")):
        _run(["git", "checkout", "-b", branch], cwd=repo_root)
        _run(["git", "add", "-A"], cwd=repo_root)
        _run(["git", "commit", "-m",
              f"draft(board): {slug} (AI-DRAFTED, experimental) — closes #{issue_number}"], cwd=repo_root)
        _run(["git", "push", "-u", "origin", branch], cwd=repo_root)
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
