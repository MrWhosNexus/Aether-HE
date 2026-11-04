"""Board-draft bot: validate a submission, have MiniMax draft board support, open
a PR. NEVER merges; NEVER logs the API key. Pure helpers here are unit-tested;
main() shells out to `gh`."""
import argparse
import ast
import ipaddress
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # tools/ on path
from validate_keymap import validate_keymap  # noqa: E402
from board_submission import validate_submission  # noqa: E402

_JSON_BLOCK = re.compile(r"```json\s*(\{.*?\})\s*```", re.S)
_JSON_URL = re.compile(r"https://[^\s)\"']+\.json")
_FILE_BLOCK = re.compile(r"=== FILE: (?P<name>[^\n=]+?) ===\n(?P<body>.*?)(?=\n=== FILE:|\Z)", re.S)
_REQUIRED_ENTRY_KEYS = {"slug", "name", "vid", "pid", "usage_page", "formFactor",
                        "protocol", "keymap", "capabilities", "status"}
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
# The registry entry is model output driven by an UNTRUSTED issue: it is
# REBUILT from validated identity fields only, and everything that changes app
# behaviour is pinned (no driver, no capabilities, not offered, the layout path
# is the file the bot itself wrote).
_PR_BODY_MAX = 60000
_HEX16_RE = re.compile(r"^0[xX][0-9A-Fa-f]{1,4}$")
_FORM_FACTORS = {"40%", "60%", "65%", "68%", "75%", "80%", "TKL", "96%", "100%", "other"}


def _hex16(v):
    """'0x1a' -> '0x001A' (the registry's form); None unless 1-4 hex digits."""
    return "0x%04X" % int(v, 16) if isinstance(v, str) and _HEX16_RE.match(v) else None


def safe_registry_entry(reg, slug):
    """(entry, problems). The entry holds only validated identity fields; the
    problems are reasons to refuse the draft (bad VID/PID)."""
    problems = []
    vid, pid = _hex16(reg.get("vid")), _hex16(reg.get("pid"))
    if vid is None or pid is None:
        problems.append("vid/pid must be 0x-prefixed hex (up to 4 digits)")
    up = reg.get("usage_page")
    up = _hex16(up) if up is not None else None
    name = reg.get("name") if isinstance(reg.get("name"), str) else slug
    name = "".join(ch for ch in name if ch.isprintable())[:80] or slug
    ff = reg.get("formFactor") if reg.get("formFactor") in _FORM_FACTORS else "other"
    entry = {"slug": slug, "name": name, "vid": vid, "pid": pid, "usage_page": up,
             "formFactor": ff, "protocol": None, "keymap": f"ui/layouts/{slug}.json",
             "capabilities": {}, "status": "experimental", "offerInUi": False,
             "_note": "AI-DRAFTED from a public issue; identity unverified."}
    return entry, problems


def shared_vid_pid(entry, boards):
    """Slugs of registered boards with the same VID:PID (several real boards
    share one, so this is flagged for the reviewer, not refused)."""
    key = (str(entry.get("vid")).upper(), str(entry.get("pid")).upper())
    return [b.get("slug") for b in boards
            if (str(b.get("vid")).upper(), str(b.get("pid")).upper()) == key]


def _fence(text):
    """A markdown code fence longer than any backtick run inside `text`."""
    run = max((len(m) for m in re.findall(r"`+", text)), default=0)
    return "`" * max(3, run + 1)


def pr_body(issue_number, adapter, syntax_error, shares=()):
    """PR description. The drafted adapter is shown as TEXT for a human to
    review and port; it is never committed as a .py file (a prompt-injected
    issue could otherwise land runnable code in a bot-authored PR)."""
    head = (f"AI-drafted from #{issue_number}. UNVERIFIED and UNTRUSTED: the draft "
            "was generated from a public issue. Verify on hardware before promoting. "
            "See DECODE_NOTES.md.\n\nThis PR commits data only (registry entry with "
            "`protocol: null`, layout). The drafted protocol adapter is below as text: "
            "review it line by line and port it by hand - never copy it in unread.\n")
    if shares:
        head += ("\n> **VID:PID already registered** for: " + ", ".join(map(str, shares))
                 + ". Same-ID siblings need a `productString` discriminator; check "
                 "this does not hijack detection of an existing board.\n")
    if not adapter:
        return head
    if syntax_error:
        head += "\n> The drafted adapter does not even parse.\n"
    fence = _fence(adapter)
    room = _PR_BODY_MAX - len(head) - 2 * len(fence) - 200   # wrapper + marker
    shown = adapter if len(adapter) <= room else adapter[:max(0, room)] + "\n# ... truncated"
    return f"{head}\n<details><summary>Drafted adapter (text only)</summary>\n\n{fence}python\n{shown}\n{fence}\n</details>\n"

_ALLOWED_HOSTS = {"github.com", "objects.githubusercontent.com",
                   "user-images.githubusercontent.com", "raw.githubusercontent.com"}


def _validate_url_host(url):
    """Raise ValueError unless url is https, allowlisted host, and resolves only
    to public (non-private/loopback/link-local/reserved/multicast) IPs."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("attachment fetch rejected: scheme must be https")
    host = parsed.hostname
    if not host or host not in _ALLOWED_HOSTS:
        raise ValueError("attachment fetch rejected: host not allowlisted")
    try:
        addrs = socket.getaddrinfo(host, 443)
    except Exception:
        raise ValueError("attachment fetch rejected: DNS resolution failed")
    for family, _, _, _, sockaddr in addrs:
        ip = sockaddr[0]
        addr = ipaddress.ip_address(ip)
        if (addr.is_private or addr.is_loopback or addr.is_link_local
                or addr.is_reserved or addr.is_multicast):
            raise ValueError("attachment fetch rejected: host resolves to a non-public address")
    return parsed


def _safe_fetch_json(url, *, max_bytes=1000000, max_redirects=2):
    """Fetch a JSON document over https from an allowlisted host, rejecting any
    hostname that resolves to a private/loopback/link-local/reserved/multicast
    IP, and never auto-following redirects (each hop is re-validated)."""
    class _NoRedirect(urllib.request.HTTPErrorProcessor):
        def http_response(self, request, response):
            return response
        https_response = http_response

    opener = urllib.request.build_opener(_NoRedirect)
    current = url
    for _ in range(max_redirects + 1):
        _validate_url_host(current)
        try:
            resp = opener.open(current, timeout=60)
        except urllib.error.HTTPError as ex:
            if ex.code in (301, 302, 303, 307, 308):
                location = ex.headers.get("Location")
                if not location:
                    raise ValueError("attachment fetch rejected: redirect with no Location")
                current = urllib.parse.urljoin(current, location)
                continue
            raise ValueError(f"attachment fetch rejected: HTTP error {ex.code}")
        except Exception:
            raise ValueError("attachment fetch rejected: request failed")
        code = getattr(resp, "status", 200) or 200
        if code in (301, 302, 303, 307, 308):
            location = resp.headers.get("Location")
            if not location:
                raise ValueError("attachment fetch rejected: redirect with no Location")
            current = urllib.parse.urljoin(current, location)
            continue
        try:
            data = resp.read(max_bytes)
            return json.loads(data.decode("utf-8"))
        except Exception:
            raise ValueError("attachment fetch rejected: invalid response body")
    raise ValueError("attachment fetch rejected: too many redirects")


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
    """Parse MiniMax's === FILE: name === delimited output into artifacts.

    Reasoning models (e.g. MiniMax-M3) prefix a <think>...</think> block; strip
    it so its contents can't be mistaken for output blocks."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    blocks = {m.group("name").strip(): m.group("body").strip()
              for m in _FILE_BLOCK.finditer(text)}

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


def body_sha256(body):
    return hashlib.sha256((body or "").encode("utf-8")).hexdigest()


def run(issue_number, *, gh, complete, repo_root, expect_body_sha256=None):
    """Testable core. gh(args)->stdout, complete(prompt)->text are injected.
    NEVER merges, force-pushes, or touches main directly — only creates
    branch board/<slug> and opens a PR via `gh pr create`."""
    issue = json.loads(gh(["issue", "view", str(issue_number), "--json", "number,title,body"]))
    body = issue.get("body", "")
    if expect_body_sha256 and body_sha256(body) != expect_body_sha256:
        # Edited after the maintainer added the label: draft nothing.
        gh(["issue", "comment", str(issue_number), "--body",
            "Automated draft skipped: the issue changed after it was approved for "
            "drafting. A maintainer must re-apply the `bot-draft` label."])
        return {"ok": False, "pr_url": None, "reason": "issue changed after approval"}
    sub = extract_json_block(body)
    if sub is None:
        url = extract_attachment_url(body)
        if url:
            try:
                sub = _safe_fetch_json(url)
            except Exception:
                sub = None
    if not isinstance(sub, dict):
        gh(["issue", "comment", str(issue_number), "--body",
            "Automated draft: no submission JSON found. Please attach the file the app generated."])
        return {"ok": False, "pr_url": None, "reason": "no submission found"}
    errs = validate_submission(sub)
    if errs:
        gh(["issue", "comment", str(issue_number), "--body",
            "Automated draft: submission is invalid:\n- " + "\n- ".join(errs)])
        return {"ok": False, "pr_url": None, "reason": "invalid submission"}

    try:
        artifacts = parse_model_output(complete(build_prompt(sub, _read_prompt())))
    except Exception:
        gh(["issue", "comment", str(issue_number), "--body",
            "Automated draft failed — a maintainer will follow up."])
        return {"ok": False, "pr_url": None, "reason": "minimax error"}
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
    syntax_error = any("syntax error" in p for p in problems)
    entry, bad = safe_registry_entry(artifacts["registry"], slug)
    if bad:
        gh(["issue", "comment", str(issue_number), "--body",
            "Automated draft could not produce a clean board:\n- " + "\n- ".join(bad)])
        return {"ok": False, "pr_url": None, "reason": "sanity failed"}
    # write files: DATA ONLY (no Python is ever committed from model output)
    reg = json.load(open(reg_path))
    shares = shared_vid_pid(entry, reg.get("boards", []))
    reg["boards"].append(entry)
    json.dump(reg, open(reg_path, "w"), indent=2)
    lay_path = os.path.join(repo_root, "ui", "layouts", f"{slug}.json")
    os.makedirs(os.path.dirname(lay_path), exist_ok=True)
    json.dump(artifacts["layout"], open(lay_path, "w"), indent=2)
    notes = artifacts["notes"] + ("\n\n> NOTE: the drafted adapter has a syntax error."
                                  if syntax_error else "")
    open(os.path.join(repo_root, "DECODE_NOTES.md"), "w", encoding="utf-8").write(notes)

    branch = f"board/{slug}"
    # Stage only the files this bot wrote — never `git add -A`, which would sweep
    # in any stray untracked file that happens to be in the working tree.
    written = [reg_path, lay_path, os.path.join(repo_root, "DECODE_NOTES.md")]
    # Only do real git ops when repo_root is an actual git checkout (production).
    # In tests repo_root is a bare tmp_path with no .git, so this is skipped —
    # keeps tests hermetic and never risks running git against the real repo cwd.
    if os.path.isdir(os.path.join(repo_root, ".git")):
        _run(["git", "checkout", "-b", branch], cwd=repo_root)
        _run(["git", "add"] + written, cwd=repo_root)
        _run(["git", "commit", "-m",
              f"draft(board): {slug} (AI-DRAFTED, experimental) — closes #{issue_number}"], cwd=repo_root)
        _run(["git", "push", "-u", "origin", branch], cwd=repo_root)
    # Ensure the `experimental` label exists before referencing it — a fresh repo
    # has no such label and `gh pr create --label` hard-fails without it.
    try:
        gh(["label", "create", "experimental", "--color", "BFD4F2",
            "--description", "AI-drafted board support, unverified on hardware"])
    except Exception:
        pass  # already exists (or no perms) — non-fatal
    pr_url = gh(["pr", "create", "--title", f"Draft board: {slug} (experimental)",
                 "--body", pr_body(issue_number, artifacts.get("adapter") or "", syntax_error, shares),
                 "--label", "experimental", "--head", branch]).strip()
    gh(["issue", "comment", str(issue_number), "--body", f"Automated draft opened: {pr_url}"])
    return {"ok": True, "pr_url": pr_url, "reason": "ok"}


def _load_dotenv(repo_root):
    """Load KEY=VALUE lines from a local .env into os.environ (stdlib only, no dep).
    Never overrides a variable already set in the environment (CI's real secret
    always wins over a stale local file), and never prints any value."""
    path = os.path.join(repo_root, ".env")
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
    except FileNotFoundError:
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--issue", type=int, required=True)
    ap.add_argument("--expect-body-sha256", default=None,
                    help="refuse unless the issue body still hashes to this "
                         "(the body as it was when the bot-draft label was added)")
    args = ap.parse_args()
    repo_root = os.getcwd()
    _load_dotenv(repo_root)                              # local runs: pick up .env
    from minimax_client import complete as mm_complete   # env key; raises if absent
    res = run(args.issue, gh=_gh, complete=mm_complete, repo_root=repo_root,
              expect_body_sha256=args.expect_body_sha256)
    print("result:", res["reason"])   # never prints the key


if __name__ == "__main__":
    main()
