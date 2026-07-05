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
