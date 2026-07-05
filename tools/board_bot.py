"""Board-draft bot: validate a submission, have MiniMax draft board support, open
a PR. NEVER merges; NEVER logs the API key. Pure helpers here are unit-tested;
main() shells out to `gh`."""
import ast
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # tools/ on path
from validate_keymap import validate_keymap  # noqa: E402

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
