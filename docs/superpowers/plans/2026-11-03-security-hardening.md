# Security Hardening (review of 2026-11-03) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the five findings of the 2026-11-03 security review without changing anything a normal user sees.

**Architecture:** Each finding is fixed at the boundary where untrusted input enters: the loopback service checks every request before routing; the updater refuses any URL outside this repo's release downloads and takes size/SHA-256 only from GitHub; the submission-URL opener accepts only this repo's new-issue page; Pillow moves past its CVEs; the board bot runs only when a maintainer applies a label and its PRs are drafts marked as untrusted code.

**Tech Stack:** Python 3.12 stdlib (`http.server`, `urllib.parse`, `hmac`), pytest, GitHub Actions YAML, PyInstaller + Inno Setup for the rebuild.

**Spec:** inline — the "Findings" section below (from the security review in the session of 2026-11-03; user approved all five).

## Findings (the spec)

1. **Medium — `service/server.py`** has no authentication and no Origin/Host check. While it runs, any web page can POST commands (simple requests are enough: the body is parsed as JSON whatever its Content-Type), and DNS rebinding can read GET routes.
2. **Medium — `updater.apply_update`** never checks that `asset_url` belongs to `https://github.com/MrWhosNexus/Aether-HE/releases/download/`, and trusts the caller-supplied `asset_size`/`asset_sha256`, so a caller can verify its own file against its own hash.
3. **Low–Med — `Api.open_submission_url`** passes any string to `webbrowser.open` (on Windows that reaches `os.startfile`, which launches local programs).
4. **Low — Pillow 12.3.0** in the build venv has 39 advisories, all fixed in 13.0.0. Only the bundled tray icon is ever opened, so none is reachable, but it ships in the exe.
5. **Low — `.github/workflows/board-bot.yml`** runs for any stranger's `[Board]` issue with `contents: write` and the `MINIMAX_API_KEY` secret: it spends API credit on demand and pushes AI-written Python (`protocol_<slug>.py`) from attacker-influenced text into a PR.

## Global Constraints

- Repo identity comes from `version.GITHUB_REPO` (`"MrWhosNexus/Aether-HE"`); never hard-code it a second time.
- No new runtime dependencies (stdlib only in `service/` and `updater.py`).
- Nothing in the desktop app's normal flows may change: the in-app update, the "Submit your board" button and the tray icon must keep working.
- Never push, merge, tag or release. Work on branch `claude/missing-broken-audit-cda685` (or a branch cut from it); commit per task.
- Run the full suite after every task: `C:\Users\yygbu\Aether-HE\venv-web\Scripts\python.exe -m pytest -q -p no:cacheprovider` — expected: all pass (683 before this plan, plus the new tests).
- Do NOT run the installer: building `dist\AetherHE-Setup.exe` is the last step; the user installs it (Windows UAC needs them).

## Review Focus

- Host header in other spellings (`LOCALHOST:8672`, `[::1]:8672`) must be allowed; `127.0.0.1:80` (rebinding to another port) must be refused — Task 1 `test_host_variants`.
- Look-alike update URLs (`https://github.com.evil.example/...`, `http://github.com/...`, `.../releases/download/../../x`) must be refused before any network call — Task 2 `test_apply_update_rejects_lookalike_urls`.
- Userinfo / look-alike submission URLs (`https://github.com@evil.example/...`, `https://github.com/MrWhosNexus/Aether-HE/issues/new.evil`) must be refused — Task 3 `test_rejects_lookalike_issue_urls`.
- The UI's real pre-filled URL (`buildIssueUrl` in `ui/runtime_src/src/board-submit.jsx`: `?template=add-a-board.yml&title=...&brand-model=...`) must still open — Task 3 `test_allows_prefilled_issue_url`.
- The tray icon must still load under Pillow 13 — Task 4 Step 3.

---

### Task 1: Guard the loopback service

**Files:**
- Create: `service/guard.py`
- Modify: `service/server.py` (`Handler._dispatch`, `Handler._sse`, `main`)
- Test: `tests/test_service_guard.py`

**Interfaces:**
- Produces: `guard.check_request(headers, port: int, *, allowed_origins: frozenset = frozenset(), token: str | None = None) -> str | None` — returns a short rejection reason, or `None` when the request may proceed. `headers` is any mapping with case-insensitive `.get` (an `http.client.HTTPMessage` in the server; a plain dict in tests, so look headers up as given: `"Host"`, `"Origin"`, `"X-Aether-Token"`).
- Produces: `guard.config_from_env() -> tuple[frozenset, str | None]` reading `AETHER_SERVICE_ORIGINS` (comma-separated, blanks dropped) and `AETHER_SERVICE_TOKEN` (empty = None).

Rules `check_request` enforces, in order:
1. `Host` missing → reject. `Host`, lower-cased, must equal one of `127.0.0.1:{port}`, `localhost:{port}`, `[::1]:{port}` → else reject (DNS rebinding).
2. `Origin` present and not in `allowed_origins` → reject (every browser cross-site POST carries Origin; the nexus backend's server-side fetch sends none).
3. `token` set → `X-Aether-Token` must match via `hmac.compare_digest` → else reject.

- [ ] **Step 1: Write the failing tests** in `tests/test_service_guard.py` (import `service.guard` after `sys.path.insert(0, <repo>/service)` or as `from service import guard` if `service/` is importable — add an empty `service/__init__.py` only if needed):

```python
H = {"Host": "127.0.0.1:8672"}
def test_allows_loopback_backend_request():
    assert guard.check_request(H, 8672) is None
def test_rejects_browser_origin():
    assert guard.check_request({**H, "Origin": "https://evil.example"}, 8672)
def test_allows_listed_origin():
    assert guard.check_request({**H, "Origin": "app://nexus"}, 8672,
                               allowed_origins=frozenset({"app://nexus"})) is None
def test_rejects_rebound_host():
    assert guard.check_request({"Host": "evil.example:8672"}, 8672)
def test_rejects_missing_host():
    assert guard.check_request({}, 8672)
def test_host_variants():
    assert guard.check_request({"Host": "LOCALHOST:8672"}, 8672) is None
    assert guard.check_request({"Host": "[::1]:8672"}, 8672) is None
    assert guard.check_request({"Host": "127.0.0.1:80"}, 8672)
def test_token_required_when_configured():
    assert guard.check_request(H, 8672, token="s3cret")
    assert guard.check_request({**H, "X-Aether-Token": "nope"}, 8672, token="s3cret")
    assert guard.check_request({**H, "X-Aether-Token": "s3cret"}, 8672, token="s3cret") is None
def test_config_from_env(monkeypatch):
    monkeypatch.setenv("AETHER_SERVICE_ORIGINS", "app://nexus, ,http://localhost:5173")
    monkeypatch.setenv("AETHER_SERVICE_TOKEN", "")
    assert guard.config_from_env() == (frozenset({"app://nexus", "http://localhost:5173"}), None)
```

Plus one end-to-end test, `test_server_refuses_cross_origin_post_without_calling_api`: before importing `service.server`, put a stub `app_web` module in `sys.modules` whose `Api` records every method call (`__getattr__` returning a recorder); start `ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)` on a thread; POST `/aether/trigger` with `Origin: https://evil.example` via `http.client`; assert status 403, JSON `{"ok": false, ...}`, and the stub recorded no `set_trigger_codes` call. Same request without Origin → 200 and the call recorded. Shut the server down in `finally`.

- [ ] **Step 2: Run** `...\python.exe -m pytest -q -p no:cacheprovider tests/test_service_guard.py` — Expected: FAIL (`guard` does not exist).

- [ ] **Step 3: Implement** `service/guard.py` (the two functions above). In `server.py`: module-level `_ALLOWED_ORIGINS, _TOKEN = guard.config_from_env()`; the server stores its bound port on the server object (`self.server.server_address[1]`); first line of `_dispatch` (before the `/aether/stream` branch so SSE is covered too) calls `check_request` and on a reason returns `self._json(403, {"ok": False, "error": f"forbidden: {reason}"})` and logs it at WARNING. Update the module docstring's "Binds 127.0.0.1 only" bullet to describe the checks and the two env vars.

- [ ] **Step 4: Run** the new tests, then the full suite — Expected: PASS.

- [ ] **Step 5: Commit** `git add service/guard.py service/server.py tests/test_service_guard.py` (+ `service/__init__.py` if added) — `fix(service): refuse cross-origin and rebound requests on the loopback API`.

---

### Task 2: Pin the updater to this repo's releases

**Files:**
- Modify: `updater.py` (`apply_update`, new constant), `app_web.py` (`Api.apply_update` docstring only)
- Test: `tests/test_updater_integrity.py`

**Interfaces:**
- Produces: `updater.RELEASE_DOWNLOAD_PREFIX = f"https://github.com/{version.GITHUB_REPO}/releases/download/"`.
- `apply_update(asset_url, asset_name=None, asset_size=None, asset_sha256=None)` keeps its signature (the UI still sends four values) but **ignores** `asset_size`/`asset_sha256`: it always calls `check_for_update()` and uses that result's `asset_size`/`asset_sha256`, and only when `chk["ok"]` and `chk["asset_url"] == asset_url`. Otherwise it refuses with the existing "could not verify the update … refusing to install an unverified download" error.
- New first check, before any network call: refuse unless `asset_url.startswith(RELEASE_DOWNLOAD_PREFIX)` and the URL contains none of `..`, `?`, `#`, `\`. Error text: `"refusing update from outside " + RELEASE_DOWNLOAD_PREFIX`.

- [ ] **Step 1: Update the three existing `apply_update` tests** to the new contract: use `URL = updater.RELEASE_DOWNLOAD_PREFIX + "v9.9.9/AetherHE-Setup.exe"`, and monkeypatch `updater.check_for_update` to return `{"ok": True, "asset_url": URL, "asset_size": <n>, "asset_sha256": <sha>}` where the old test passed those as arguments. `test_apply_update_refuses_when_no_checksum_or_size` keeps its "different asset_url" stub but calls with `URL`.

- [ ] **Step 2: Add the failing tests:**
  - `test_apply_update_rejects_url_outside_repo_releases` — `apply_update("https://example.com/AetherHE-Setup.exe", asset_size=1, asset_sha256="ab")` → `ok False`, `"outside"` in error; `check_for_update`, `_download` and `Popen` are never called (stub each to record).
  - `test_apply_update_rejects_lookalike_urls` — each of `"https://github.com.evil.example/MrWhosNexus/Aether-HE/releases/download/v1/a.exe"`, `"http://github.com/MrWhosNexus/Aether-HE/releases/download/v1/a.exe"`, `URL.replace("v9.9.9/", "v9.9.9/../../x/")`, `URL + "?x=1"` → refused, nothing downloaded.
  - `test_apply_update_ignores_caller_supplied_hash` — urlopen serves `b"EVIL"*100`; caller passes `asset_sha256=sha256(b"EVIL"*100)` and its size; `check_for_update` stub returns the real installer's different sha/size for `URL` → `ok False`, `"integrity"` in error, `Popen` not called.

- [ ] **Step 3: Run** `...\python.exe -m pytest -q -p no:cacheprovider tests/test_updater_integrity.py` — Expected: the new tests FAIL, the rest pass.

- [ ] **Step 4: Implement** the constant and the two checks in `updater.apply_update`; update its docstring (caller metadata is ignored, why) and `Api.apply_update`'s docstring line that says the values "come from check_update()".

- [ ] **Step 5: Run** the file, then the full suite — Expected: PASS.

- [ ] **Step 6: Commit** — `fix(update): only install this repo's release assets, verified against GitHub's own digest`.

---

### Task 3: Allow only the repo's new-issue page in `open_submission_url`

**Files:**
- Modify: `app_web.py` (`Api.open_submission_url`)
- Test: `tests/test_api_submission.py` (append; reuse its `_api()` helper)

**Interfaces:**
- Produces: `Api.open_submission_url(url) -> {"ok": True}` only when `urllib.parse.urlsplit(str(url))` has `scheme == "https"`, `netloc == "github.com"` (exact — rejects userinfo and ports), `path == f"/{version.GITHUB_REPO}/issues/new"`, and empty `fragment`. Otherwise `{"ok": False, "error": "refusing to open a URL that is not this repo's new-issue page"}` and `webbrowser.open` is not called.

- [ ] **Step 1: Write the failing tests** (monkeypatch `webbrowser.open` to record calls):
  - `test_allows_prefilled_issue_url` — `"https://github.com/MrWhosNexus/Aether-HE/issues/new?template=add-a-board.yml&title=%5BBoard%5D+Acme+60&vid-pid=0x1%3A0x2"` → ok, opened once with that exact string.
  - `test_rejects_local_program_path` — `r"C:\Windows\System32\calc.exe"` → ok False, nothing opened.
  - `test_rejects_lookalike_issue_urls` — `"https://github.com@evil.example/MrWhosNexus/Aether-HE/issues/new"`, `"https://github.com/MrWhosNexus/Aether-HE/issues/new.evil"`, `"http://github.com/MrWhosNexus/Aether-HE/issues/new"`, `"https://github.com/someone-else/repo/issues/new"`, `"file:///C:/x.exe"` → each refused, nothing opened.

- [ ] **Step 2: Run** `...\python.exe -m pytest -q -p no:cacheprovider tests/test_api_submission.py` — Expected: new tests FAIL.

- [ ] **Step 3: Implement** the check in `Api.open_submission_url` (import `version` the way `app_version` does).

- [ ] **Step 4: Run** the file, then the full suite — Expected: PASS.

- [ ] **Step 5: Commit** — `fix(submit): open only this repo's new-issue page from the bridge`.

---

### Task 4: Move Pillow past its advisories

**Files:**
- Modify: `requirements.txt` (`Pillow>=10;` → `Pillow>=13;`, same platform marker)

- [ ] **Step 1: Edit** `requirements.txt` as above.
- [ ] **Step 2: Upgrade the build venv:** `C:\Users\yygbu\Aether-HE\venv-web\Scripts\python.exe -m pip install -U "Pillow>=13"` — Expected: `Successfully installed pillow-13.x`.
- [ ] **Step 3: Check the tray icon still loads:** `...\python.exe -c "from PIL import Image; import pystray; im = Image.open(r'ui\assets\logo.png'); im.load(); print(im.size)"` — Expected: a size tuple, no exception. Then `...\python.exe -m pytest -q -p no:cacheprovider tests/test_tray.py` — Expected: PASS.
- [ ] **Step 4: Re-audit:** `pip freeze` the venv to a scratch file and run `pip-audit -r <file> --no-deps` from a throwaway venv (never install pip-audit into `venv-web`) — Expected: `No known vulnerabilities found`. If another package now reports advisories, list them in the hand-off; do not chase them in this task.
- [ ] **Step 5: Full suite**, then **commit** `requirements.txt` — `chore(deps): require Pillow 13 (39 advisories fixed upstream)`.

---

### Task 5: Board bot runs only on a maintainer's label; drafts are untrusted

**Files:**
- Modify: `.github/workflows/board-bot.yml`, `tools/board_bot.py` (`run`, PR creation)
- Test: `tests/test_board_bot.py` (`test_run_happy_path`)

**Interfaces:**
- Workflow trigger becomes `issues: types: [labeled]` (+ the existing `workflow_dispatch`), and the job `if:` becomes `github.event_name == 'workflow_dispatch' || github.event.label.name == 'bot-draft'`. Only users with triage access can apply labels, and the issue template (`.github/ISSUE_TEMPLATE/add-a-board.yml`) applies only `new-board`/`needs-triage`, so a stranger cannot start the bot. Add `concurrency: { group: board-bot-${{ github.event.issue.number || github.event.inputs.issue }}, cancel-in-progress: false }`. Nothing from the issue is interpolated into `run:` (keep it that way).
- `gh pr create` gains `"--draft"` and a second label `"untrusted-ai-code"` (created with the same try/except pattern as `experimental`). PR body becomes: `AI-drafted from #{n}. UNVERIFIED and UNTRUSTED: protocol_{slug}.py was written by a model from public issue text. Read every line before running or merging. See DECODE_NOTES.md.`

- [ ] **Step 1: Extend `test_run_happy_path`:** assert `"--draft" in calls["pr"]`, that `"untrusted-ai-code"` follows a `"--label"` in `calls["pr"]`, and that the `--body` value contains `"UNTRUSTED"`.
- [ ] **Step 2: Run** `...\python.exe -m pytest -q -p no:cacheprovider tests/test_board_bot.py` — Expected: FAIL on the new asserts.
- [ ] **Step 3: Implement** the `board_bot.py` changes and the workflow edits above.
- [ ] **Step 4: Check the YAML parses:** `...\python.exe -c "import yaml,sys; yaml.safe_load(open('.github/workflows/board-bot.yml'))"` if PyYAML is available; otherwise read it back and confirm indentation by eye. Then run the file's tests and the full suite — Expected: PASS.
- [ ] **Step 5: Commit** — `fix(ci): board bot runs only on a maintainer's bot-draft label; drafts marked untrusted`. In the hand-off, tell the user to create the `bot-draft` label on GitHub and that drafting a submission now means applying it.

---

### Task 6: Rebuild the installer (user installs)

- [ ] **Step 1: Build** from this worktree, in order: `...\python.exe ui\runtime_src\build_runtime.py`; `C:\Users\yygbu\Aether-HE\venv-web\Scripts\pyinstaller.exe --clean --noconfirm AetherHE.spec`; `"C:\Users\yygbu\AppData\Local\Programs\Inno Setup 6\ISCC.exe" installer.iss` — Expected: `dist\AetherHE-Setup.exe` with a fresh timestamp. (`vendor\ViGEmBus_Setup.exe` is already present; if missing, re-run the download line from `build_installer.bat` and check its Authenticode signer is Nefarius Software Solutions e.U.)
- [ ] **Step 2: Confirm the fixes are in the bundle:** read `device_state` and `updater` from the PYZ inside `dist\AetherHE\AetherHE.exe` with `PyInstaller.archive.readers.CArchiveReader` and check the code objects contain `RELEASE_SILENCE_S` and `RELEASE_DOWNLOAD_PREFIX`.
- [ ] **Step 3: Do not install.** Hand off: the installer path, the commits made, and that the tester fix from 2026-11-03 rides along. Leave `git status` clean apart from the line-ending-only noise in `ui/runtime_src/build/*.js`.
