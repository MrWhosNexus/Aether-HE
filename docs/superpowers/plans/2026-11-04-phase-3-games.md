# Phase 3: Game Detection + Per-Game Profiles (Discord-style) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect running games (Discord's public detectable list + programs the user adds), and while a game mapped to a profile runs, switch Aether to that profile and apply it to the keyboard (actuation/RT on all keys, SOCD, lighting); revert to the previous profile when it exits.

**Architecture:** New stdlib-only `games.py`: a list parser + trailing-path-segment matcher (`DetectableIndex`), a cached downloader (`DetectableStore` / `fetch_url`), a Windows ctypes process scanner (`scan`), a pure debounced state machine (`GameSwitcher`) and the glue service (`GameService`, owns settings.json `"games"` and the 3 s poll thread). `Api` exposes it as bridge methods and adds `apply_profile_to_board` (reuses `set_trigger_all` / `set_socd`, skips writes the board already holds, defers while offline). Python DECIDES which profile should be active; `app.jsx` polls `games_status()`, switches the profile through the same path as the profile menu (lighting follows), calls `apply_profile_to_board`, and reports back with `games_sync`. Settings gets a "Games" widget; the tray tooltip names the detected game.

**Tech Stack:** Python 3 stdlib (`ctypes`, `urllib.request`, `ssl`, `zlib`, `json`, `threading`), pytest, the existing React/Tailwind UI (precompiled by `ui/runtime_src/build_runtime.py`).

**Spec:** `docs/superpowers/specs/2026-11-04-win60-roadmap-design.md` (section "Phase 3" + "Global constraints"). Also read `docs/superpowers/roadmap-status.md` (Phase 1/2 decisions: `Api._act_mm` is the per-key actuation cache; build readers only via `Api._make_live_reader`).

**Prototype note:** every test and code block below was run against this tree before the plan was written (full suite `916 passed, 13 skipped`) and then reverted; the worktree holds only this plan.

## Global Constraints

- Windows is the shipping target; nothing may break Linux (guard Windows-only code by `sys.platform`; degrade to "unavailable" elsewhere). On Linux/macOS `games.processes_supported()` is False: no poll thread, `games_status()["available"] is False`, the Settings widget says detection is available on Windows.
- **NEVER write to the keyboard, open HID, or run the app against it. Fakes only** (patterns: `tests/test_stats_api.py::_api`, `tests/test_socd_clear.py`, `tests/test_tray.py` stubs). Hardware checks are listed at the end for the orchestrator.
- No push, merge into other branches, tag, release, or install.
- **NO NETWORK during development or tests** (never discord.com). Tests use the committed fixture `tests/fixtures/discord_detectable_sample.json` and injected fetchers / a fake `urlopen`. The shipped app may fetch at runtime.
- Python: `C:\Users\yygbu\Aether-HE\venv-web\Scripts\python.exe` (written `<py>` below). Full suite: `<py> -m pytest -q -p no:cacheprovider` (`808 passed, 12 skipped` at the start of this phase); green at every commit.
- JSX changes need `<py> ui\runtime_src\build_runtime.py`; commit `ui/index_runtime.html` + only the `ui/runtime_src/build/*.js` files with real diffs (`git diff --ignore-cr-at-eol --stat`; `git checkout -- <file>` for every build file that only shows in plain `git diff --stat`).
- UI: edit `ui/runtime_src/src/*.jsx` / `ui/runtime_src/workspaces/*.jsx`, never `vendor/`. No raw-HTML sinks (`dangerouslySetInnerHTML`, `innerHTML`); game/program names are rendered as text only. Match the existing look (Tailwind classes, CSS vars `--text`, `--accent`, `--line`, `--ink`). Every `/*` must close (`tests/test_ui_sources.py`).
- **No new Python dependencies** this phase (no `requirements.txt` change). **No new PyInstaller hidden imports**: `games` is a static import of `app_web`; `urllib.request`, `ssl`, `zlib`, `ctypes` are stdlib and found by analysis (`updater.py` already ships urllib/ssl). The Flatpak copy list DOES need `games.py` (`tests/test_packaging.py` checks the import closure) — Task 6.
- **Privacy anti-goal:** never store/transmit key sequences, text, or per-keystroke timestamps; **never persist the process list**. Only processes whose file name could be a known game are opened; only matched game ids/names are kept in memory; nothing about other processes is logged, stored or sent. The detectable list is downloaded; nothing is uploaded.
- Bridge methods return `{"ok": bool, ...}` and never raise to JS (`Api._fail`).
- Do NOT touch `service/server.py`, `updater.py`, `Api.open_submission_url`, `.github/workflows/board-bot.yml`, or the Pillow pin.
- `git add` only the files you changed (other agents may leave untracked files). Never `git stash`. Every commit message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- The user is asleep: "If it doesn't require my intervention write the code save items that require me for later." Do not stop to ask; queue user items in `docs/superpowers/roadmap-status.md` under `## Waiting on the user`.
- Context limit: if your context approaches ~400k tokens, stop: commit only what is green, append a status entry saying exactly where you stopped, and return.
- Sources in this worktree are LF. If the Edit tool cannot match a multi-line `old_string`, do the replacement with a short Python snippet (`str.replace` with an `assert s.count(old) == 1`).

## Design decisions (resolved; do not re-decide)

1. **Matcher index.** `DetectableIndex._by_suffix: dict[str, str]` maps every normalised pattern (lowercase, `/` separators, no drive, no leading `>`; e.g. `valorant/valorant.exe`, `neonquest.exe`) to a game id. A process path is normalised and looked up from its longest candidate suffix (`max_segments` = deepest pattern, capped at `MAX_SEGMENTS = 8`) down to its file name: the most specific pattern wins, at most 8 dict lookups per process. `basenames` (last segment of every pattern) is a prefilter: the scanner only opens processes whose file name is in it. Discord duplicates: first entry wins. Single-file-name Discord patterns in `GENERIC_EXES` (java/python/browsers/launchers/…) are ignored; the user's own games (`extra`) override Discord patterns and are always honoured. Discord's `>name.exe` ("file name only") is treated as a one-segment pattern. Only `os == "win32"` and `is_launcher != true` executables count.
2. **Game ids.** Discord entries: the snowflake string (`^[0-9]{1,24}$`; int ids are converted). User-added programs: `"custom:" + last two path segments` (e.g. `custom:indie/indie.exe`).
3. **Downloader.** `fetch_url(url, max_bytes, timeout=20, urlopen=None)`: https only (also after redirects), `ssl.create_default_context()` (certificate + hostname verification ON), `Accept-Encoding: gzip`; refuses a declared `Content-Length` over the cap before reading and enforces the cap while streaming 64 KiB chunks. `MAX_DETECTABLE_BYTES = 5 MiB` applies to the bytes received (the spec's cap); gzip is unpacked through `zlib.decompressobj` with its own `MAX_DECOMPRESSED_BYTES = 32 MiB` cap (zip-bomb guard) and truncation check. Shape validation in `parse_detectable` (array, ≤ 100 000 entries, valid id, cleaned name ≤ 64 chars without control chars, ≥ 1 win32 exe; else dropped; nothing left → ValueError).
4. **Cache.** `<user_data_dir>/games/detectable.json` = `{"version": 1, "fetched": <epoch s>, "source": url, "games": [{"id", "name", "exes"}]}` — compact, re-validated on load, written atomically (`.tmp` + `os.replace`). Weekly refresh (`REFRESH_AFTER_S = 7 d`); after a failed automatic attempt wait `RETRY_AFTER_S = 6 h`. Offline: no cache = no Discord games (custom and already-mapped games still work, because a mapping stores the game's exes). Automatic refreshes run on a one-shot daemon thread so detection never blocks; Settings "Update" calls `refresh_detectable()` synchronously.
5. **Process enumeration** (Windows, ctypes, explicit `argtypes`/`restype`): `CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS)` + `Process32FirstW/NextW` → `(pid, szExeFile)`; candidates only: `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION=0x1000)` + `QueryFullProcessImageNameW`; access denied → fall back to the file name. Foreground: `GetForegroundWindow` → `GetWindowThreadProcessId`. Off Windows all three return empty/None.
6. **Poll thread lifecycle.** Started by `main()` on app start (not on connect: a game must switch the selected profile even while the board is unplugged) via `Api._start_games(tray_ctl.set_game)`, stopped in `main()`'s `finally` via `Api._stop_games()`. Daemon thread `aether-games`, `POLL_S = 3.0`. `GameService.start()` returns False and creates nothing when unavailable. The service lives at the PRIVATE `Api._games` (pywebview walks public Api attributes recursively).
7. **State machine** (`GameSwitcher.step`, pure, injected clock). Inputs per poll: running known games, the foreground one, `{game id: profile id}` for mapped games, auto flag, the app's active profile. Wanted game = foreground mapped game; else the one already applied while it still runs (alt-tab to a browser does not switch back); else the most recently started. A changed `(game, profile)` target must hold ≥ `DEBOUNCE_S = 5.0` s (≈ 2 polls) before it commits. First game of a session records the active profile as the revert target; switching between games keeps it; when no mapped game runs any more the app reverts to it. Remapping the running game switches to the new profile; unmapping it reverts.
8. **Manual switch during a game.** `games_sync` carries `handledSeq`. Once the app has handled Python's newest switch (`handledSeq >= seq`), an active profile different from the one Python asked for is a manual choice: the revert is cancelled and that game is not re-applied until it exits or another mapped game takes over. Reports with an older `handledSeq` are ignored for this (out-of-order bridge threads).
9. **Auto-switch toggle.** settings.json `games.autoSwitch`: explicit bool wins; unset = ON iff any game has a profile (spec: "default ON once any game is mapped"). Toggling resets the session (no revert; a running game re-applies after the debounce when turned on). With it off the game is still detected/shown, never switched.
10. **Profile apply path + JS sync.** Profiles are owned by `app.jsx` (labels → design codes live there), so the JS executes the switch: it polls `games_status()` every 2 s (WebView2 timers keep full rate hidden: `--disable-background-timer-throttling` in `main()`), consistent with the existing `status`/`refreshBoards` polls; on `switch.seq > handled` it calls `switchProfile(id)` (same as the menu → `applyState` → the lighting effects re-send when connected), acks with `games_sync({activeProfile, handledSeq, profiles})`, then `apply_profile_to_board(profileBoardSpec(profile.state))`. A missing profile id is ignored (acked with the unchanged active profile → Python treats it as an override, no revert). `games_sync` is also pushed whenever `activeId` or the profile names change.
11. **`apply_profile_to_board(spec)`** — spec `{actuation, rtEnabled, rtPress, rtRelease, socd: [{model, key1, key2}]}`; `null` fields are left alone (a profile that never stored a value gets no default). Actuation → `set_trigger_all(travel, rtp, rtr, mode=13 if rtEnabled else 0)` on ALL keys (clamped to the board's `travelRange`/`rtRange`); SOCD → `set_socd(pairs)` (`[]` clears, same as the SOCD tab). Returns `{"ok", "deferred", "actuation": "written"|"unchanged"|"skipped", "socd": ...}`, or the failing call's result plus `"step"`.
12. **Flash wear.** (a) the 5 s debounce; (b) actuation is skipped when the cached per-key state says EVERY key already has that travel (±0.005 mm) and mode (and RT pair in mode 13): `_act_mm` (Phase 2) + new `_trig_mode` `{idx: (mode, rtp|None, rtr|None)}` fed by `verify_actuation`'s trigger detail and by successful `set_trigger_all`/`set_trigger_codes`; (c) SOCD is skipped when the pairs equal the last `set_socd` pairs this connection (`_socd_last`, order-sensitive); (d) `_trig_mode`/`_socd_last` are cleared on every `_connect` and `select_board` (board state unknown until the UI's on-connect read-back), so a stale cache can never suppress a needed write. Lighting is not flash and only re-sends when the profile actually changes.
13. **Disconnected.** The JS switches the selected profile anyway; `apply_profile_to_board` stores the newest spec in `Api._pending_board` and returns `{"ok": True, "deferred": True}`; `_connect` applies it after `_start_stats_reader()` (never raises), and the UI's on-connect read-back then shows it. Lighting follows the existing `connected` flip.
14. **Tray tooltip.** `TrayController.set_game(name|None)` → `"Aether HE — <name>"` / `"Aether HE"`, control chars stripped, ≤ 120 chars (Windows caps at 128); applied to the live icon or used when the icon is created. Fed by `GameService.on_detected`, called only when the shown game changes. Shown game = the foreground known game, else the previously shown one while it runs, else the alphabetically first running known game (mapped or not).
15. **Settings persistence.** `"games": {"autoSwitch": bool|null, "map": {id: {"name", "exes", "profile": id|null, "custom": bool}}}` via `Api.save_settings` (top-level merge; the UI never sends `"games"`). New module lock `_SETTINGS_LOCK` serialises `save_settings`' read-merge-write (UI saves and Python writers run on different threads). Profile ids validated `^[A-Za-z0-9_-]{1,64}$` and against the last `games_sync` profile list when known. ≤ 200 mapped games.
16. **Known limitation (queued for the user):** the revert target is not persisted; if Aether restarts during a game, the game's exit will not revert.

## Review Focus

- **Alt-tab / launcher / crash-restart churn** must not hammer the flash: nothing commits before 5 s; flipping back cancels. Tests: Task 4 `test_a_short_blip_never_switches`, `test_alt_tab_between_two_games_is_debounced`; Task 7 `test_a_repeated_apply_is_skipped`, `test_board_that_already_matches_is_not_written`.
- **A stale or partial read-back must never suppress a needed write** (most keys unknown, other app changed the board while unplugged). Tests: Task 7 `test_different_travel_or_partial_read_back_writes`, `test_reconnect_forgets_what_the_board_holds`.
- **Hostile/garbage Discord data or a hostile server** (huge body, gzip bomb, redirect to http, wrong JSON shape, HTML in names). Tests: Task 1 `test_parse_rejects_wrong_shapes`, `test_names_are_plain_text_from_the_list`; Task 2 `test_fetch_cap_is_enforced_while_streaming`, `test_fetch_unpacks_gzip_with_its_own_cap`, `test_fetch_refuses_plain_http_and_https_downgrade_redirects`; Task 9 `test_game_names_are_rendered_as_text_only`.
- **User switches profile by hand mid-game**: Aether must not fight them or revert on exit. Tests: Task 4 `test_manual_switch_during_a_game_cancels_revert_and_reapply`, `test_a_stale_report_before_the_ui_handled_the_switch_is_not_an_override`.
- **Keyboard unplugged when the game starts**: profile switches now, board write on reconnect, once. Test: Task 7 `test_offline_apply_is_deferred_and_the_newest_wins`.

## File Structure

- Create `games.py` (Tasks 1–5; each task appends one section).
- Create `tests/fixtures/discord_detectable_sample.json` (Task 1; fictional games shaped like Discord's list).
- Modify `app_web.py`: import + `_SETTINGS_LOCK` + `save_settings` lock + `_make_games/_start_games/_stop_games` + games bridge (Task 6); `_trig_mode`/`_socd_last`/`_pending_board` + notes in `set_trigger_all`/`set_trigger_codes`/`verify_actuation`/`set_socd` + resets in `_connect`/`select_board` + `apply_profile_to_board` (Task 7); `main()` wiring (Task 8).
- Modify `flatpak/io.github.mrwhosnexus.AetherHE.yml` (Task 6), `tray.py` (Task 8).
- Modify `ui/runtime_src/src/app.jsx`, `ui/runtime_src/workspaces/settings.jsx`; regenerated `ui/index_runtime.html`, `ui/runtime_src/build/app.js`, `ui/runtime_src/build/ws_settings.js` (Task 9).
- Modify `CLAUDE.md`, `docs/superpowers/roadmap-status.md` (Task 10).
- Tests (all new): `tests/test_games_index.py` (18), `test_games_store.py` (12), `test_games_procs.py` (8 collected: 7 run on Windows + 1 non-Windows skip), `test_games_switcher.py` (16), `test_games_service.py` (15), `test_games_api.py` (8), `test_games_apply.py` (21), `test_games_tray.py` (5), `test_games_ui_sources.py` (6). **108 new passing tests, 1 new skip on Windows → `916 passed, 13 skipped`.**

---

### Task 1: Discord list parsing and the trailing-segment matcher

**Files:**
- Create: `games.py`, `tests/fixtures/discord_detectable_sample.json`
- Test: `tests/test_games_index.py` (create)

**Interfaces:**
- Produces (module `games`): constants (all used by later tasks) `DETECTABLE_URL, MAX_DETECTABLE_BYTES, MAX_DECOMPRESSED_BYTES, FETCH_TIMEOUT_S, REFRESH_AFTER_S, RETRY_AFTER_S, POLL_S, DEBOUNCE_S, CACHE_VERSION, SETTINGS_KEY, CUSTOM_PREFIX, MAX_NAME, MAX_EXE, MAX_SEGMENTS, MAX_EXES_PER_GAME, MAX_GAMES, MAX_MAPPED, MAX_PROFILES, GENERIC_EXES`; `clean_name(s) -> str|None`; `norm_exe(s) -> str|None`; `exe_suffix(path, segments=2) -> str|None`; `parse_detectable(raw: bytes|str|list) -> list[{"id","name","exes"}]` (ValueError on bad shape); `parse_cache(obj) -> (games, fetched_float)`; `class DetectableIndex(games=(), extra=())` with `match(path) -> id|None`, `could_match(basename) -> bool`, `name_of(id)`, `exes_of(id) -> list`, `basenames: set`, `max_segments: int`, `__len__`.

- [ ] **Step 1: Create the fixture** `tests/fixtures/discord_detectable_sample.json` (fictional games; covers launcher/linux/darwin exes, `>` marker, a generic `javaw.exe`, a duplicate pattern, a control char in a name, an int id, backslashes, and junk entries):

```json
[
  {
    "aliases": [],
    "executables": [
      {"is_launcher": false, "name": "starfall/starfall.exe", "os": "win32"},
      {"is_launcher": true, "name": "starfall launcher.exe", "os": "win32"},
      {"is_launcher": false, "name": "starfall", "os": "linux"}
    ],
    "hook": true,
    "id": "100000000000000001",
    "name": "Starfall Arena",
    "overlay": false
  },
  {
    "aliases": ["NQ"],
    "executables": [
      {"is_launcher": false, "name": "win64/neonquest-win64-shipping.exe", "os": "win32"},
      {"is_launcher": false, "name": ">neonquest.exe", "os": "win32"},
      {"is_launcher": false, "name": "neonquest.app", "os": "darwin"}
    ],
    "hook": true,
    "id": "100000000000000002",
    "name": "Neon Quest\u0007",
    "overlay": true
  },
  {
    "executables": [
      {"is_launcher": false, "name": "javaw.exe", "os": "win32"}
    ],
    "id": "100000000000000003",
    "name": "Blocky Java Game"
  },
  {
    "executables": [
      {"is_launcher": false, "name": "neonquest.exe", "os": "win32"}
    ],
    "id": "100000000000000004",
    "name": "Neon Quest Duplicate"
  },
  {
    "executables": [],
    "id": "100000000000000005",
    "name": "No Executables"
  },
  {
    "executables": [{"name": "macgame", "os": "darwin"}],
    "id": "100000000000000006",
    "name": "Mac Only"
  },
  {"id": "not-a-snowflake", "name": "Bad Id", "executables": [{"name": "bad.exe", "os": "win32"}]},
  {"id": "100000000000000007", "executables": [{"name": "noname.exe", "os": "win32"}]},
  {"id": "100000000000000008", "name": "Weird Executables", "executables": "valorant.exe"},
  "junk",
  42,
  {
    "executables": [
      {"is_launcher": false, "name": "Tiny Tactics\\Bin\\TinyTactics.exe", "os": "win32"}
    ],
    "id": 100000000000000009,
    "name": "Tiny Tactics"
  }
]
```

- [ ] **Step 2: Write the failing tests** — `tests/test_games_index.py`:

```python
"""Phase 3 game detection: parsing Discord's detectable list and matching
process paths by trailing path segments. Pure: a committed fixture shaped
like the real list, no network, no processes."""
import json
import os

import pytest

import games

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "fixtures", "discord_detectable_sample.json")
STARFALL, NEON, JAVA, NEON_DUP, TINY = ("100000000000000001", "100000000000000002",
                                        "100000000000000003", "100000000000000004",
                                        "100000000000000009")


def _fixture_bytes():
    with open(FIXTURE, "rb") as f:
        return f.read()


def _index(extra=()):
    return games.DetectableIndex(games.parse_detectable(_fixture_bytes()), extra)


def test_norm_exe_lowercases_drops_drive_marker_and_dot_segments():
    n = games.norm_exe
    assert n("C:\\Games\\Foo\\FOO.exe") == "games/foo/foo.exe"
    assert n(">Foo.EXE") == "foo.exe"
    assert n("/a/./b/../c.exe") == "a/b/c.exe"
    assert n("") is None and n(None) is None and n(42) is None
    assert n("bad\x00.exe") is None
    assert n("x" * 300) is None
    assert games.exe_suffix("D:\\SteamLibrary\\common\\Tiny\\Tiny.exe") == "tiny/tiny.exe"
    assert games.exe_suffix("tiny.exe") == "tiny.exe"


def test_clean_name_strips_control_characters_and_caps_length():
    assert games.clean_name("  Neon\x07 Quest ") == "Neon Quest"
    assert games.clean_name("\x01\x02") is None
    assert games.clean_name(None) is None
    assert len(games.clean_name("a" * 500)) == games.MAX_NAME


def test_parse_keeps_only_valid_windows_games():
    parsed = games.parse_detectable(_fixture_bytes())
    by_id = {g["id"]: g for g in parsed}
    assert set(by_id) == {STARFALL, NEON, JAVA, NEON_DUP, TINY}
    assert by_id[STARFALL]["exes"] == ["starfall/starfall.exe"]          # launcher + linux dropped
    assert by_id[NEON]["name"] == "Neon Quest"                           # \x07 removed
    assert by_id[NEON]["exes"] == ["win64/neonquest-win64-shipping.exe", "neonquest.exe"]
    assert by_id[TINY]["exes"] == ["tiny tactics/bin/tinytactics.exe"]   # int id + backslashes


@pytest.mark.parametrize("raw", [b"{}", b'"x"', b"null", "[]", b"[1, 2]",
                                 b'[{"id": "1", "name": "x", "executables": []}]'])
def test_parse_rejects_wrong_shapes(raw):
    with pytest.raises(ValueError):
        games.parse_detectable(raw)


def test_parse_rejects_invalid_json():
    with pytest.raises(ValueError):
        games.parse_detectable(b"[{")


def test_parse_caps_entry_count(monkeypatch):
    monkeypatch.setattr(games, "MAX_GAMES", 3)
    with pytest.raises(ValueError):
        games.parse_detectable(_fixture_bytes())


def test_match_uses_trailing_segments_case_insensitively():
    idx = _index()
    assert idx.match(r"C:\Program Files\Starfall\STARFALL.exe") == STARFALL
    assert idx.match(r"C:\Program Files\Other\starfall.exe") is None     # needs the folder too
    assert idx.match(r"E:\NQ\Engine\Win64\NeonQuest-Win64-Shipping.exe") == NEON
    assert idx.match(r"D:\anything\neonquest.exe") == NEON               # '>' = file name only
    assert idx.match(r"D:\Steam\common\Tiny Tactics\bin\TinyTactics.exe") == TINY
    assert idx.match(r"C:\Windows\notepad.exe") is None
    assert idx.match("") is None and idx.match(None) is None


def test_generic_runtime_names_and_duplicates_are_not_indexed():
    idx = _index()
    assert idx.match(r"C:\Java\bin\javaw.exe") is None                   # generic: never a game
    assert idx.name_of(JAVA) is None
    assert idx.name_of(NEON_DUP) is None                                 # first entry wins
    assert len(idx) == 3


def test_basename_prefilter():
    idx = _index()
    assert idx.could_match("STARFALL.EXE") and idx.could_match("neonquest.exe")
    assert not idx.could_match("explorer.exe") and not idx.could_match(None)


def test_longest_matching_suffix_wins():
    g = [{"id": "1", "name": "Short", "exes": ["game.bin"]},
         {"id": "2", "name": "Long", "exes": ["deep/dir/game.bin"]}]
    idx = games.DetectableIndex(g)
    assert idx.max_segments == 3
    assert idx.match("C:/x/deep/dir/game.bin") == "2"
    assert idx.match("C:/x/other/game.bin") == "1"


def test_user_games_override_discord_patterns():
    extra = [{"id": "custom:starfall/starfall.exe", "name": "My Starfall",
              "exes": ["starfall/starfall.exe"]},
             {"id": "custom:tools/javaw.exe", "name": "My Java Thing", "exes": ["javaw.exe"]}]
    idx = _index(extra)
    assert idx.match(r"C:\Starfall\starfall.exe") == "custom:starfall/starfall.exe"
    assert idx.name_of("custom:starfall/starfall.exe") == "My Starfall"
    assert idx.match(r"C:\Java\javaw.exe") == "custom:tools/javaw.exe"   # user's choice honoured


def test_exes_of_returns_the_indexed_patterns():
    idx = _index()
    assert idx.exes_of(NEON) == ["win64/neonquest-win64-shipping.exe", "neonquest.exe"]
    assert idx.exes_of("nope") == []


def test_names_are_plain_text_from_the_list():
    raw = json.dumps([{"id": "7", "name": "<img src=x onerror=alert(1)>",
                       "executables": [{"name": "x.exe", "os": "win32"}]}])
    g = games.parse_detectable(raw)
    assert g[0]["name"] == "<img src=x onerror=alert(1)>"   # kept as TEXT; the UI never renders HTML
```

- [ ] **Step 3: Run them to verify they fail**

Run: `<py> -m pytest tests/test_games_index.py -q -p no:cacheprovider`
Expected: collection ERROR `ModuleNotFoundError: No module named 'games'`.

- [ ] **Step 4: Create `games.py`** with this content (module docstring, every import the later sections need, constants, parsing, the index):

```python
"""Game detection + per-game profiles (Discord-style).

Aether looks at which programs are running every few seconds and matches them
against (a) Discord's public "detectable applications" list and (b) programs
the user added. A game mapped to a profile switches the app to that profile
(and the app applies it to the keyboard) while it runs; when it exits the
previous profile comes back.

Privacy: process enumeration is transient. Only processes whose file name
could be a known game are opened, nothing about any other process is kept,
and nothing is logged, stored or sent except the matched game's id/name.
The detectable list is DOWNLOADED (nothing is uploaded) and cached on disk.

Windows only (Toolhelp32 + QueryFullProcessImageNameW through ctypes, no new
dependency); elsewhere `processes_supported()` is False and nothing polls.
"""
import ctypes
import json
import logging
import os
import re
import ssl
import sys
import threading
import time
import types
import urllib.request
import zlib

log = logging.getLogger("aether.games")

DETECTABLE_URL = "https://discord.com/api/v9/applications/detectable"
MAX_DETECTABLE_BYTES = 5 * 1024 * 1024      # cap on the bytes received
MAX_DECOMPRESSED_BYTES = 32 * 1024 * 1024   # cap after gunzip (zip-bomb guard)
FETCH_TIMEOUT_S = 20
REFRESH_AFTER_S = 7 * 24 * 3600             # weekly
RETRY_AFTER_S = 6 * 3600                    # after a failed automatic fetch
POLL_S = 3.0
DEBOUNCE_S = 5.0
CACHE_VERSION = 1
SETTINGS_KEY = "games"
CUSTOM_PREFIX = "custom:"
MAX_NAME = 64
MAX_EXE = 260
MAX_SEGMENTS = 8
MAX_EXES_PER_GAME = 32
MAX_GAMES = 100000
MAX_MAPPED = 200
MAX_PROFILES = 200

# Single-file-name patterns too generic to mean "a game is running" (runtimes,
# shells, browsers, launchers). Only applied to Discord's list; a program the
# user adds is always honoured.
GENERIC_EXES = frozenset({
    "java.exe", "javaw.exe", "python.exe", "pythonw.exe", "node.exe",
    "electron.exe", "cmd.exe", "powershell.exe", "pwsh.exe", "explorer.exe",
    "dotnet.exe", "rundll32.exe", "svchost.exe", "conhost.exe", "dllhost.exe",
    "msedge.exe", "chrome.exe", "firefox.exe", "steam.exe",
    "steamwebhelper.exe", "launcher.exe", "game.exe", "start.exe",
    "setup.exe", "unins000.exe", "aetherhe.exe",
})

_CTRL = re.compile(r"[\x00-\x1f\x7f]")
_ID_RE = re.compile(r"^[0-9]{1,24}$")
_PROFILE_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def clean_name(s):
    """Untrusted display name -> stripped text without control characters,
    at most MAX_NAME chars; None if nothing is left."""
    if not isinstance(s, str):
        return None
    s = _CTRL.sub("", s).strip()
    return s[:MAX_NAME] or None


def norm_exe(s):
    """Executable path or pattern -> lowercase '/'-joined segments without a
    drive, a leading '>' (Discord's "file name only" marker) or empty/./..
    segments. 'C:\\Games\\Foo\\FOO.exe' -> 'games/foo/foo.exe'. None if empty,
    too long, or containing control characters."""
    if not isinstance(s, str) or not s or len(s) > MAX_EXE or _CTRL.search(s):
        return None
    s = s.strip().lstrip(">").replace("\\", "/").lower()
    if len(s) >= 2 and s[1] == ":":
        s = s[2:]
    segs = [p for p in s.split("/") if p and p not in (".", "..")]
    return "/".join(segs) or None


def exe_suffix(path, segments=2):
    """The last `segments` path segments of `path`, normalised."""
    n = norm_exe(path)
    if not n:
        return None
    return "/".join(n.split("/")[-segments:])


def _game_exes(xs):
    """Discord `executables` -> normalised win32, non-launcher patterns."""
    out = []
    if not isinstance(xs, list):
        return out
    for x in xs:
        if not isinstance(x, dict) or x.get("os") != "win32" or x.get("is_launcher") is True:
            continue
        n = norm_exe(x.get("name"))
        if n and n.count("/") < MAX_SEGMENTS and n not in out:
            out.append(n)
        if len(out) >= MAX_EXES_PER_GAME:
            break
    return out


def parse_detectable(raw):
    """Validate Discord's detectable list (bytes/str/parsed list) and reduce
    it to [{"id", "name", "exes"}] for games with Windows executables.
    Raises ValueError when the shape is wrong or no game survives."""
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8")
    if isinstance(raw, str):
        raw = json.loads(raw)
    if not isinstance(raw, list):
        raise ValueError("detectable list must be a JSON array")
    if len(raw) > MAX_GAMES:
        raise ValueError("detectable list has too many entries")
    out, seen = [], set()
    for e in raw:
        if not isinstance(e, dict):
            continue
        gid = e.get("id")
        if isinstance(gid, int) and not isinstance(gid, bool):
            gid = str(gid)
        if not isinstance(gid, str) or not _ID_RE.match(gid) or gid in seen:
            continue
        name = clean_name(e.get("name"))
        exes = _game_exes(e.get("executables"))
        if not name or not exes:
            continue
        seen.add(gid)
        out.append({"id": gid, "name": name, "exes": exes})
    if not out:
        raise ValueError("detectable list has no Windows games")
    return out


def parse_cache(obj):
    """Our own cache file -> (games, fetched_epoch). Re-validates every
    entry (the file is on disk and could be edited). ValueError if unusable."""
    if not isinstance(obj, dict) or obj.get("version") != CACHE_VERSION:
        raise ValueError("unknown cache format")
    fetched = obj.get("fetched")
    if isinstance(fetched, bool) or not isinstance(fetched, (int, float)) \
            or fetched != fetched or fetched < 0:
        raise ValueError("cache has no valid fetch time")
    games = obj.get("games")
    if not isinstance(games, list) or len(games) > MAX_GAMES:
        raise ValueError("cache has no game list")
    out, seen = [], set()
    for g in games:
        if not isinstance(g, dict):
            continue
        gid, name = g.get("id"), clean_name(g.get("name"))
        if not isinstance(gid, str) or not _ID_RE.match(gid) or gid in seen or not name:
            continue
        exes = [n for n in (norm_exe(x) for x in (g.get("exes") or [])
                            if isinstance(x, str))
                if n and n.count("/") < MAX_SEGMENTS][:MAX_EXES_PER_GAME]
        if exes:
            seen.add(gid)
            out.append({"id": gid, "name": name, "exes": exes})
    return out, float(fetched)


class DetectableIndex:
    """Trailing-path-segment matcher over thousands of patterns.

    `_by_suffix` maps every normalised pattern ('foo/bin/foo.exe',
    'foo.exe') to a game id. A process path is looked up from its longest
    candidate suffix (`max_segments`, the deepest pattern) down to its file
    name, so the most specific pattern wins: at most MAX_SEGMENTS dict
    lookups per process. `basenames` (last segment of every pattern) lets
    the scanner skip opening any process whose file name cannot match.
    Discord duplicates: the first entry wins. `extra` (the user's mapped and
    added games) overrides Discord patterns."""

    def __init__(self, games=(), extra=()):
        self._by_suffix = {}
        self._names = {}
        self._exes = {}
        self.basenames = set()
        self.max_segments = 1
        for g in games:
            self._add(g, discord=True)
        for g in extra:
            self._add(g, discord=False)

    def _add(self, g, discord):
        gid, name = g["id"], g["name"]
        kept = []
        for exe in g["exes"]:
            if discord and "/" not in exe and exe in GENERIC_EXES:
                continue
            if discord and exe in self._by_suffix:
                continue
            self._by_suffix[exe] = gid
            self.basenames.add(exe.rsplit("/", 1)[-1])
            self.max_segments = max(self.max_segments, exe.count("/") + 1)
            kept.append(exe)
        if kept or not discord:
            if not discord or gid not in self._names:
                self._names[gid] = name
            self._exes.setdefault(gid, [])
            for exe in kept:
                if exe not in self._exes[gid]:
                    self._exes[gid].append(exe)

    def __len__(self):
        return len(self._names)

    def could_match(self, basename):
        return isinstance(basename, str) and basename.lower() in self.basenames

    def match(self, path):
        """Game id for a process path (or bare file name), else None."""
        n = norm_exe(path)
        if not n:
            return None
        segs = n.split("/")
        for k in range(min(self.max_segments, len(segs)), 0, -1):
            gid = self._by_suffix.get("/".join(segs[-k:]))
            if gid is not None:
                return gid
        return None

    def name_of(self, gid):
        return self._names.get(gid)

    def exes_of(self, gid):
        return list(self._exes.get(gid, ()))
```

- [ ] **Step 5: Run the tests**

Run: `<py> -m pytest tests/test_games_index.py -q -p no:cacheprovider`
Expected: `18 passed`.

- [ ] **Step 6: Commit**

```bash
git add games.py tests/fixtures/discord_detectable_sample.json tests/test_games_index.py
git commit -m "feat(games): parse Discord's detectable list and match trailing path segments" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Detectable-list cache and the capped HTTPS downloader

**Files:**
- Modify: `games.py` (append)
- Test: `tests/test_games_store.py` (create)

**Interfaces:**
- Consumes: Task 1 `parse_detectable`, `parse_cache`, constants; test helpers `STARFALL`, `_fixture_bytes` from `tests/test_games_index.py`.
- Produces: `fetch_url(url, max_bytes, timeout=FETCH_TIMEOUT_S, urlopen=None) -> bytes`; `class DetectableStore(cache_dir, fetcher=None, clock=time.time)` with `.path` (`<cache_dir>/detectable.json`), `.games`, `.fetched`, `.last_error`, `load() -> int`, `is_stale()`, `should_refresh()`, `refresh() -> {"ok", "count"} | {"ok": False, "error"}`, `info() -> {"count","fetched","stale","error"}`. `fetcher` signature: `fetcher(url, max_bytes) -> bytes`.

- [ ] **Step 1: Write the failing tests** — `tests/test_games_store.py`:

```python
"""Phase 3: the Discord list cache and its downloader. The network is never
touched: the store gets an injected fetcher, and fetch_url gets a fake
urlopen that serves the committed fixture."""
import gzip
import json
import os

import pytest

import games
from test_games_index import STARFALL, _fixture_bytes


class Clock:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


class FakeResponse:
    def __init__(self, body, headers=None, url=games.DETECTABLE_URL):
        self._body, self._pos = body, 0
        self.headers = dict(headers or {})
        self._url = url
        self.reads = 0

    def read(self, n=-1):
        self.reads += 1
        if n is None or n < 0:
            n = len(self._body) - self._pos
        chunk = self._body[self._pos:self._pos + n]
        self._pos += len(chunk)
        return chunk

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _opener(resp, seen=None):
    def urlopen(req, timeout=None, context=None):
        if seen is not None:
            seen.update(url=req.full_url, timeout=timeout, context=context,
                        headers=dict(req.header_items()))
        return resp
    return urlopen


# ---------------------------------------------------------------- fetch_url --
def test_fetch_uses_verified_tls_and_a_timeout():
    seen = {}
    body = games.fetch_url(games.DETECTABLE_URL, 1 << 20,
                           urlopen=_opener(FakeResponse(_fixture_bytes()), seen))
    assert body == _fixture_bytes()
    assert seen["timeout"] == games.FETCH_TIMEOUT_S
    ctx = seen["context"]
    assert ctx.check_hostname is True and ctx.verify_mode == games.ssl.CERT_REQUIRED
    assert seen["headers"].get("Accept-encoding") == "gzip"


def test_fetch_refuses_plain_http_and_https_downgrade_redirects():
    with pytest.raises(ValueError):
        games.fetch_url("http://discord.com/x", 100, urlopen=_opener(FakeResponse(b"[]")))
    resp = FakeResponse(b"[]", url="http://evil.example/x")
    with pytest.raises(ValueError):
        games.fetch_url(games.DETECTABLE_URL, 100, urlopen=_opener(resp))


def test_fetch_cap_is_enforced_while_streaming():
    resp = FakeResponse(b"x" * 300_000)                # no Content-Length header
    with pytest.raises(ValueError, match="larger than"):
        games.fetch_url(games.DETECTABLE_URL, 100_000, urlopen=_opener(resp))
    assert resp.reads <= 3                             # stopped early, not read to the end


def test_fetch_rejects_a_declared_oversize_body_before_reading():
    resp = FakeResponse(b"[]", headers={"Content-Length": str(6 * 1024 * 1024)})
    with pytest.raises(ValueError):
        games.fetch_url(games.DETECTABLE_URL, games.MAX_DETECTABLE_BYTES, urlopen=_opener(resp))
    assert resp.reads == 0


def test_fetch_unpacks_gzip_with_its_own_cap(monkeypatch):
    gz = gzip.compress(_fixture_bytes())
    resp = FakeResponse(gz, headers={"Content-Encoding": "gzip"})
    assert games.fetch_url(games.DETECTABLE_URL, 1 << 20, urlopen=_opener(resp)) == _fixture_bytes()
    monkeypatch.setattr(games, "MAX_DECOMPRESSED_BYTES", 100)
    resp = FakeResponse(gz, headers={"Content-Encoding": "gzip"})
    with pytest.raises(ValueError, match="decompressed"):
        games.fetch_url(games.DETECTABLE_URL, 1 << 20, urlopen=_opener(resp))


def test_fetch_rejects_truncated_gzip_and_unknown_encodings():
    gz = gzip.compress(_fixture_bytes())[:-20]
    with pytest.raises(ValueError):
        games.fetch_url(games.DETECTABLE_URL, 1 << 20,
                        urlopen=_opener(FakeResponse(gz, headers={"Content-Encoding": "gzip"})))
    with pytest.raises(ValueError):
        games.fetch_url(games.DETECTABLE_URL, 1 << 20,
                        urlopen=_opener(FakeResponse(b"[]", headers={"Content-Encoding": "br"})))


# ------------------------------------------------------------------- store --
def _store(tmp_path, fetcher=None, clock=None):
    return games.DetectableStore(str(tmp_path / "games"),
                                 fetcher=fetcher or (lambda url, cap: _fixture_bytes()),
                                 clock=clock or Clock())


def test_offline_with_no_cache_is_empty_and_stale(tmp_path):
    s = _store(tmp_path)
    assert s.load() == 0 and s.games == [] and s.is_stale()
    assert s.info() == {"count": 0, "fetched": None, "stale": True, "error": None}


def test_refresh_validates_and_writes_a_compact_cache_atomically(tmp_path):
    calls = []
    s = _store(tmp_path, fetcher=lambda url, cap: calls.append((url, cap)) or _fixture_bytes())
    assert s.refresh() == {"ok": True, "count": 5}
    assert calls == [(games.DETECTABLE_URL, games.MAX_DETECTABLE_BYTES)]
    with open(s.path, encoding="utf-8") as f:
        cached = json.load(f)
    assert cached["version"] == 1 and cached["source"] == games.DETECTABLE_URL
    assert {g["id"] for g in cached["games"]} >= {STARFALL}
    assert set(cached["games"][0]) == {"id", "name", "exes"}           # nothing else kept
    assert not os.path.exists(s.path + ".tmp")
    s2 = _store(tmp_path, fetcher=lambda *a: pytest.fail("must not fetch"))
    assert s2.load() == 5 and not s2.is_stale()


def test_failed_refresh_keeps_the_old_list(tmp_path):
    s = _store(tmp_path)
    s.refresh()

    def boom(url, cap):
        raise OSError("offline")
    s._fetch = boom
    r = s.refresh()
    assert r["ok"] is False and "offline" in r["error"]
    assert len(s.games) == 5 and s.info()["error"]
    s._fetch = lambda url, cap: b'{"not": "a list"}'
    assert s.refresh()["ok"] is False and len(s.games) == 5


def test_weekly_staleness_and_retry_backoff(tmp_path):
    clock = Clock()
    s = _store(tmp_path, clock=clock)
    assert s.should_refresh()
    s.refresh()
    assert not s.should_refresh()
    clock.t += games.REFRESH_AFTER_S
    assert s.is_stale() and s.should_refresh()
    s._fetch = lambda url, cap: (_ for _ in ()).throw(OSError("offline"))
    s.refresh()
    assert not s.should_refresh()                       # failed: wait before retrying
    clock.t += games.RETRY_AFTER_S
    assert s.should_refresh()


def test_corrupt_or_foreign_cache_is_ignored(tmp_path):
    s = _store(tmp_path)
    os.makedirs(os.path.dirname(s.path))
    for bad in ("{", "[]", json.dumps({"version": 99, "fetched": 1, "games": []}),
                json.dumps({"version": 1, "fetched": "yesterday", "games": []})):
        with open(s.path, "w", encoding="utf-8") as f:
            f.write(bad)
        s.games = []
        assert s.load() == 0 and s.games == []


def test_cache_entries_are_revalidated_on_load(tmp_path):
    s = _store(tmp_path)
    os.makedirs(os.path.dirname(s.path))
    with open(s.path, "w", encoding="utf-8") as f:
        json.dump({"version": 1, "fetched": 5, "games": [
            {"id": "1", "name": "Ok", "exes": ["A\\B.exe"]},
            {"id": "x", "name": "Bad id", "exes": ["c.exe"]},
            {"id": "2", "name": "\x01", "exes": ["d.exe"]},
            {"id": "3", "name": "No exes", "exes": []}]}, f)
    assert s.load() == 1 and s.games == [{"id": "1", "name": "Ok", "exes": ["a/b.exe"]}]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `<py> -m pytest tests/test_games_store.py -q -p no:cacheprovider`
Expected: 12 FAIL/ERROR with `AttributeError: module 'games' has no attribute 'fetch_url'` / `'DetectableStore'`.

- [ ] **Step 3: Append to `games.py`:**

```python
def _atomic_write_json(path, obj):
    """Write JSON next to `path` and swap it in, so a crash mid-write never
    leaves a truncated cache."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, separators=(",", ":"))
    os.replace(tmp, path)


def _gunzip_capped(data, limit):
    d = zlib.decompressobj(16 + zlib.MAX_WBITS)
    out = d.decompress(data, limit + 1)
    if len(out) > limit or d.unconsumed_tail:
        raise ValueError("detectable list is too large once decompressed")
    if not d.eof:
        raise ValueError("detectable list download was truncated")
    return out


def fetch_url(url, max_bytes, timeout=FETCH_TIMEOUT_S, urlopen=None):
    """GET `url` over verified HTTPS and return the body, refusing more than
    `max_bytes` on the wire (checked while streaming, before reading it all).
    gzip is accepted and unpacked with its own cap. Raises on any failure."""
    if not url.startswith("https://"):
        raise ValueError("only https URLs are fetched")
    req = urllib.request.Request(url, headers={
        "User-Agent": "AetherHE-Games", "Accept": "application/json",
        "Accept-Encoding": "gzip"})
    ctx = ssl.create_default_context()      # certificate + hostname checks on
    opener = urlopen or urllib.request.urlopen
    with opener(req, timeout=timeout, context=ctx) as r:
        final = r.geturl() or url
        if not final.startswith("https://"):
            raise ValueError("redirected away from https")
        length = (r.headers.get("Content-Length") or "").strip()
        if length.isdigit() and int(length) > max_bytes:
            raise ValueError(f"detectable list is larger than {max_bytes // 1048576} MB")
        buf = bytearray()
        while True:
            chunk = r.read(65536)
            if not chunk:
                break
            buf += chunk
            if len(buf) > max_bytes:
                raise ValueError(f"detectable list is larger than {max_bytes // 1048576} MB")
        enc = (r.headers.get("Content-Encoding") or "").strip().lower()
    if enc == "gzip":
        return _gunzip_capped(bytes(buf), MAX_DECOMPRESSED_BYTES)
    if enc not in ("", "identity"):
        raise ValueError(f"unsupported content encoding {enc!r}")
    return bytes(buf)


class DetectableStore:
    """Discord's list, cached at <dir>/detectable.json in a compact,
    re-validated form ({"version", "fetched", "source", "games"}).
    Works offline: a missing/corrupt cache just means no Discord games.
    `fetcher(url, max_bytes) -> bytes` is injectable; tests never touch the
    network."""

    def __init__(self, cache_dir, fetcher=None, clock=time.time):
        self.path = os.path.join(cache_dir, "detectable.json")
        self._fetch = fetcher or fetch_url
        self._clock = clock
        self.games = []
        self.fetched = None
        self.last_error = None
        self._last_attempt = None

    def load(self):
        """Read the cache; returns the number of games (0 when absent/bad)."""
        try:
            with open(self.path, encoding="utf-8") as f:
                obj = json.load(f)
            games, fetched = parse_cache(obj)
        except FileNotFoundError:
            return 0
        except (OSError, ValueError) as e:
            self.last_error = f"cached game list unusable: {e}"
            log.warning("%s", self.last_error)
            return 0
        self.games, self.fetched = games, fetched
        return len(games)

    def is_stale(self):
        return self.fetched is None or self._clock() - self.fetched >= REFRESH_AFTER_S

    def should_refresh(self):
        """Stale, and no automatic attempt in the last RETRY_AFTER_S."""
        if not self.is_stale():
            return False
        return (self._last_attempt is None
                or self._clock() - self._last_attempt >= RETRY_AFTER_S)

    def refresh(self):
        """Download, validate, cache. {"ok", "count"} or {"ok": False, "error"};
        a failure keeps whatever list was loaded before."""
        self._last_attempt = self._clock()
        try:
            games = parse_detectable(self._fetch(DETECTABLE_URL, MAX_DETECTABLE_BYTES))
        except Exception as e:
            self.last_error = f"game list not updated: {e}"
            log.warning("%s", self.last_error)
            return {"ok": False, "error": self.last_error}
        now = self._clock()
        try:
            _atomic_write_json(self.path, {"version": CACHE_VERSION, "fetched": now,
                                           "source": DETECTABLE_URL, "games": games})
        except OSError as e:
            log.warning("game list cache not written: %s", e)
        self.games, self.fetched, self.last_error = games, now, None
        return {"ok": True, "count": len(games)}

    def info(self):
        return {"count": len(self.games), "fetched": self.fetched,
                "stale": self.is_stale(), "error": self.last_error}
```

- [ ] **Step 4: Run the tests**

Run: `<py> -m pytest tests/test_games_store.py tests/test_games_index.py -q -p no:cacheprovider`
Expected: `30 passed`.

- [ ] **Step 5: Commit**

```bash
git add games.py tests/test_games_store.py
git commit -m "feat(games): cached Discord list with a 5 MB capped, TLS-verified downloader" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Windows process scan (ctypes Toolhelp32) and the running-programs picker

**Files:**
- Modify: `games.py` (append)
- Test: `tests/test_games_procs.py` (create)

**Interfaces:**
- Consumes: Task 1 `DetectableIndex`, `norm_exe`; test helpers `NEON`, `STARFALL`, `_index` from `tests/test_games_index.py`.
- Produces: `processes_supported(platform=None) -> bool`; `list_processes() -> [(pid, file_name)]`; `process_path(pid) -> str|None`; `foreground_pid() -> int|None`; `scan(index, procs=None, path_of=None, fg=None) -> (set[game_id], fg_game_id|None)`; `running_programs(index, procs=None, path_of=None, limit=200, own_pid=None) -> [{"exe": "folder/name.exe", "name", "gameId"}]` (Windows folder and own process skipped, one row per exe, known games first then by name).

- [ ] **Step 1: Write the failing tests** — `tests/test_games_procs.py` (the last test reads THIS machine's process list on Windows: a read-only OS call, no HID, no network):

```python
"""Phase 3: process scanning. The scanner is fed fake process lists, so the
matching, foreground arbitration and the privacy rule (only candidate
processes are opened) are tested anywhere. One smoke test reads this
machine's own process list on Windows (read-only OS call, no HID)."""
import os
import sys

import pytest

import games
from test_games_index import NEON, STARFALL, _index

PROCS = [(10, "System"), (20, "explorer.exe"), (30, "starfall.exe"),
         (40, "NeonQuest-Win64-Shipping.exe"), (50, "chrome.exe"), (60, "starfall.exe")]
PATHS = {20: r"C:\Windows\explorer.exe",
         30: r"C:\Games\Starfall\starfall.exe",
         40: r"E:\NQ\Win64\NeonQuest-Win64-Shipping.exe",
         50: r"C:\Program Files\Google\Chrome\chrome.exe",
         60: r"C:\Other\starfall.exe"}


def _scan(fg_pid=None):
    opened = []

    def path_of(pid):
        opened.append(pid)
        return PATHS.get(pid)
    running, fg = games.scan(_index(), procs=lambda: PROCS, path_of=path_of,
                             fg=lambda: fg_pid)
    return running, fg, opened


def test_scan_finds_running_games_and_the_foreground_one():
    running, fg, _ = _scan(fg_pid=40)
    assert running == {STARFALL, NEON}
    assert fg == NEON


def test_foreground_non_game_means_no_foreground_game():
    _, fg, _ = _scan(fg_pid=50)
    assert fg is None


def test_only_candidate_processes_are_opened():
    _, _, opened = _scan()
    assert sorted(opened) == [30, 40, 60]                 # never explorer/chrome/System


def test_access_denied_falls_back_to_the_file_name():
    running, _ = games.scan(_index(), procs=lambda: [(7, "neonquest.exe")],
                               path_of=lambda pid: None, fg=lambda: None)
    assert running == {NEON}                              # '>neonquest.exe' = file name only


def test_running_programs_lists_user_programs_once_known_games_first(monkeypatch):
    monkeypatch.setenv("SystemRoot", r"C:\Windows")
    rows = games.running_programs(_index(), procs=lambda: PROCS + [(99, "aether.exe")],
                                  path_of=lambda pid: PATHS.get(pid) or
                                  (r"C:\Aether\AetherHE.exe" if pid == 99 else None),
                                  own_pid=99)
    assert [r["exe"] for r in rows] == ["win64/neonquest-win64-shipping.exe",
                                        "starfall/starfall.exe", "chrome/chrome.exe",
                                        "other/starfall.exe"]
    assert rows[0] == {"exe": "win64/neonquest-win64-shipping.exe", "name": "Neon Quest",
                       "gameId": NEON}
    assert rows[2]["gameId"] is None and rows[2]["name"] == "chrome.exe"


def test_platform_gate():
    assert games.processes_supported("win32") is True
    assert games.processes_supported("linux") is False
    assert games.processes_supported("darwin") is False


@pytest.mark.skipif(sys.platform.startswith("win"), reason="non-Windows behaviour")
def test_enumeration_is_empty_off_windows():
    assert games.list_processes() == []
    assert games.process_path(os.getpid()) is None
    assert games.foreground_pid() is None


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows ctypes smoke test")
def test_windows_enumeration_sees_this_process():
    procs = games.list_processes()
    assert len(procs) > 5
    assert any(pid == os.getpid() for pid, _ in procs)
    path = games.process_path(os.getpid())
    # a venv python.exe is a launcher for the base interpreter: compare names
    assert path and os.path.basename(path).lower().startswith("python")
    fg = games.foreground_pid()
    assert fg is None or isinstance(fg, int)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `<py> -m pytest tests/test_games_procs.py -q -p no:cacheprovider`
Expected: FAIL with `AttributeError: module 'games' has no attribute 'scan'` (and the others).

- [ ] **Step 3: Append to `games.py`:**

```python
def processes_supported(platform=None):
    """Process enumeration exists on Windows only."""
    return (platform or sys.platform).startswith("win")


_W = None
_INVALID_HANDLE = ctypes.c_void_p(-1).value


def _win():
    """kernel32/user32 entry points with explicit argtypes (64-bit handles)."""
    global _W
    if _W is None:
        from ctypes import wintypes as wt
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        u32 = ctypes.WinDLL("user32", use_last_error=True)

        class PROCESSENTRY32W(ctypes.Structure):
            _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD),
                        ("th32ProcessID", wt.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                        ("th32ModuleID", wt.DWORD), ("cntThreads", wt.DWORD),
                        ("th32ParentProcessID", wt.DWORD), ("pcPriClassBase", ctypes.c_long),
                        ("dwFlags", wt.DWORD), ("szExeFile", ctypes.c_wchar * 260)]

        pe_p = ctypes.POINTER(PROCESSENTRY32W)
        k32.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]
        k32.CreateToolhelp32Snapshot.restype = wt.HANDLE
        k32.Process32FirstW.argtypes = [wt.HANDLE, pe_p]
        k32.Process32FirstW.restype = wt.BOOL
        k32.Process32NextW.argtypes = [wt.HANDLE, pe_p]
        k32.Process32NextW.restype = wt.BOOL
        k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
        k32.OpenProcess.restype = wt.HANDLE
        k32.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR,
                                                   ctypes.POINTER(wt.DWORD)]
        k32.QueryFullProcessImageNameW.restype = wt.BOOL
        k32.CloseHandle.argtypes = [wt.HANDLE]
        k32.CloseHandle.restype = wt.BOOL
        u32.GetForegroundWindow.argtypes = []
        u32.GetForegroundWindow.restype = wt.HWND
        u32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
        u32.GetWindowThreadProcessId.restype = wt.DWORD
        _W = types.SimpleNamespace(k32=k32, u32=u32, PE=PROCESSENTRY32W, wt=wt)
    return _W


def list_processes():
    """[(pid, file name)] of every process (Toolhelp32). [] off Windows or
    on any failure. Transient: callers must not keep it."""
    if not processes_supported():
        return []
    try:
        w = _win()
        snap = w.k32.CreateToolhelp32Snapshot(0x2, 0)       # TH32CS_SNAPPROCESS
        if not snap or snap == _INVALID_HANDLE:
            return []
        try:
            e = w.PE()
            e.dwSize = ctypes.sizeof(w.PE)
            out = []
            ok = w.k32.Process32FirstW(snap, ctypes.byref(e))
            while ok:
                out.append((int(e.th32ProcessID), e.szExeFile))
                ok = w.k32.Process32NextW(snap, ctypes.byref(e))
            return out
        finally:
            w.k32.CloseHandle(snap)
    except Exception as ex:
        log.debug("process list unavailable: %s", ex)
        return []


def process_path(pid):
    """Full image path of `pid` (QueryFullProcessImageNameW with
    PROCESS_QUERY_LIMITED_INFORMATION), or None (gone / access denied)."""
    if not processes_supported():
        return None
    try:
        w = _win()
        h = w.k32.OpenProcess(0x1000, False, int(pid))
        if not h:
            return None
        try:
            size = w.wt.DWORD(1024)
            buf = ctypes.create_unicode_buffer(1024)
            if w.k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                return buf.value
            return None
        finally:
            w.k32.CloseHandle(h)
    except Exception:
        return None


def foreground_pid():
    """PID owning the foreground window, or None."""
    if not processes_supported():
        return None
    try:
        w = _win()
        hwnd = w.u32.GetForegroundWindow()
        if not hwnd:
            return None
        pid = w.wt.DWORD(0)
        w.u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return int(pid.value) or None
    except Exception:
        return None


def scan(index, procs=None, path_of=None, fg=None):
    """One detection pass -> (set of running game ids, id of the game that
    owns the foreground window or None). Only processes whose file name ends
    some pattern are opened; nothing about any other process is kept."""
    procs = procs or list_processes
    path_of = path_of or process_path
    fg = fg or foreground_pid
    fg_pid = fg()
    running, fg_game = set(), None
    for pid, base in procs():
        if not index.could_match(base):
            continue
        gid = index.match(path_of(pid) or base)
        if gid is None:
            continue
        running.add(gid)
        if pid == fg_pid:
            fg_game = gid
    return running, fg_game


def running_programs(index, procs=None, path_of=None, limit=200, own_pid=None):
    """For the Settings "add a running program" picker, built on demand and
    never stored: [{"exe": "folder/name.exe", "name", "gameId"}] for user
    programs (the Windows folder and Aether itself skipped), one row per
    exe, known games first, then by name."""
    procs = procs or list_processes
    path_of = path_of or process_path
    own = os.getpid() if own_pid is None else own_pid
    windir = norm_exe(os.environ.get("SystemRoot") or "C:\\Windows") or "windows"
    rows, seen = [], set()
    for pid, _base in procs():
        if pid == own:
            continue
        n = norm_exe(path_of(pid) or "")
        if not n or not n.endswith(".exe") or n.startswith(windir + "/"):
            continue
        suffix = "/".join(n.split("/")[-2:])
        if suffix in seen:
            continue
        seen.add(suffix)
        gid = index.match(n)
        rows.append({"exe": suffix,
                     "name": (index.name_of(gid) if gid else None) or n.rsplit("/", 1)[-1],
                     "gameId": gid})
    rows.sort(key=lambda r: (r["gameId"] is None, r["name"].lower()))
    return rows[:limit]
```

- [ ] **Step 4: Run the tests**

Run: `<py> -m pytest tests/test_games_procs.py -q -p no:cacheprovider`
Expected on Windows: `7 passed, 1 skipped`.

- [ ] **Step 5: Commit**

```bash
git add games.py tests/test_games_procs.py
git commit -m "feat(games): Toolhelp32 process scan that only opens candidate processes" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: The debounced switch state machine

**Files:**
- Modify: `games.py` (append)
- Test: `tests/test_games_switcher.py` (create)

**Interfaces:**
- Produces: `class GameSwitcher(debounce_s=DEBOUNCE_S)` with `step(now, running, fg, mapping, auto, active_profile, names=None) -> dict|None` (switch dict `{"seq", "profileId", "reason": "game"|"revert", "gameId", "gameName"}`), `note_active(active_profile, handled_seq)`, `reset()`, `pick(running, fg)`, attributes `seq`, `last` (latest switch dict), `current`, `current_profile`, `session`, `prev_profile`, `overridden`.

- [ ] **Step 1: Write the failing tests** — `tests/test_games_switcher.py`:

```python
"""Phase 3: the debounced profile-switch state machine. Pure: the test owns
the clock and calls step() the way the 3 s poll does."""
import games

G, H = "100000000000000001", "100000000000000002"
MAP = {G: "pg", H: "ph"}
NAMES = {G: "Starfall Arena", H: "Neon Quest"}


class Run:
    """Drive a switcher on a fake clock, one poll per call."""

    def __init__(self, auto=True, active="p1"):
        self.sw = games.GameSwitcher()
        self.t = 0.0
        self.auto = auto
        self.active = active
        self.mapping = dict(MAP)

    def poll(self, running=(), fg=None, dt=games.POLL_S):
        self.t += dt
        out = self.sw.step(self.t, set(running), fg, self.mapping, self.auto,
                           self.active, NAMES)
        if out:
            self.active = out["profileId"]                     # the app obeys
            self.sw.note_active(self.active, out["seq"])
        return out

    def until_switch(self, running=(), fg=None, polls=5):
        for _ in range(polls):
            out = self.poll(running, fg)
            if out:
                return out
        return None


def test_game_start_switches_after_the_debounce():
    r = Run()
    assert r.poll({G}) is None                                  # t=3: seen
    assert r.poll({G}) is None                                  # t=6: held 3 s < 5 s
    out = r.until_switch({G})
    assert out == {"seq": 1, "profileId": "pg", "reason": "game",
                   "gameId": G, "gameName": "Starfall Arena"}
    assert r.t >= 3.0 + games.DEBOUNCE_S


def test_exit_reverts_to_the_profile_active_before_the_game():
    r = Run(active="p1")
    r.until_switch({G})
    assert r.poll({G}) is None                                  # steady while running
    out = r.until_switch(set())
    assert out["profileId"] == "p1" and out["reason"] == "revert" and out["gameId"] is None


def test_a_short_blip_never_switches():
    r = Run()
    r.poll({G})
    assert r.poll(set()) is None                                # gone again before 5 s
    for _ in range(4):
        assert r.poll(set()) is None
    assert r.sw.seq == 0


def test_alt_tab_between_two_games_is_debounced():
    r = Run()
    r.until_switch({G, H}, fg=G)
    assert r.active == "pg"
    assert r.poll({G, H}, fg=H) is None                         # tabbed to H for 3 s ...
    assert r.poll({G, H}, fg=G) is None                         # ... and back: nothing
    for _ in range(3):
        assert r.poll({G, H}, fg=G) is None
    out = r.until_switch({G, H}, fg=H)                          # H stays in front: switch
    assert out["profileId"] == "ph" and out["gameId"] == H


def test_foreground_non_game_keeps_the_current_game():
    r = Run()
    r.until_switch({G, H}, fg=H)
    for _ in range(5):
        assert r.poll({G, H}, fg=None) is None                  # browser in front: stay on H


def test_without_focus_the_most_recently_started_game_wins():
    r = Run()
    r.poll({G})
    r.poll({G, H})
    out = r.until_switch({G, H})
    assert out["gameId"] == H


def test_switching_between_games_keeps_the_original_revert_target():
    r = Run(active="p1")
    r.until_switch({G}, fg=G)
    r.until_switch({G, H}, fg=H)
    out = r.until_switch(set())
    assert out["profileId"] == "p1"


def test_manual_switch_during_a_game_cancels_revert_and_reapply():
    r = Run(active="p1")
    out = r.until_switch({G})
    r.active = "p9"
    r.sw.note_active("p9", out["seq"])                          # user picked p9 by hand
    for _ in range(4):
        assert r.poll({G}) is None                              # game NOT re-applied
    for _ in range(4):
        assert r.poll(set()) is None                            # and no revert on exit
    assert r.sw.session is False


def test_a_stale_report_before_the_ui_handled_the_switch_is_not_an_override():
    r = Run(active="p1")
    out = r.until_switch({G})
    r.sw.note_active("p1", out["seq"] - 1)                      # old sync landing late
    assert r.sw.overridden is False
    assert r.until_switch(set())["profileId"] == "p1"


def test_auto_switch_off_tracks_but_never_switches():
    r = Run(auto=False)
    for _ in range(5):
        assert r.poll({G}) is None
    assert r.sw.current == G and r.sw.session is False
    for _ in range(5):
        assert r.poll(set()) is None


def test_reset_lets_a_running_game_apply_when_auto_is_turned_on():
    r = Run(auto=False)
    for _ in range(4):
        r.poll({G})
    r.auto = True
    r.sw.reset()
    assert r.until_switch({G})["profileId"] == "pg"


def test_remapping_the_running_game_switches_to_the_new_profile():
    r = Run()
    r.until_switch({G})
    r.mapping[G] = "pz"
    out = r.until_switch({G})
    assert out["profileId"] == "pz" and out["reason"] == "game"


def test_unmapping_the_running_game_reverts():
    r = Run(active="p1")
    r.until_switch({G})
    del r.mapping[G]
    assert r.until_switch({G})["profileId"] == "p1"


def test_unmapped_games_are_ignored():
    r = Run()
    for _ in range(5):
        assert r.poll({"999"}) is None


def test_no_revert_when_the_previous_profile_is_unknown():
    r = Run(active=None)
    r.until_switch({G})
    assert r.until_switch(set()) is None


def test_seq_increases_and_last_is_a_copy():
    r = Run()
    a = r.until_switch({G})
    b = r.until_switch(set())
    assert (a["seq"], b["seq"]) == (1, 2)
    a["profileId"] = "tamper"
    assert r.sw.last["seq"] == 2 and r.sw.last["profileId"] == "p1"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `<py> -m pytest tests/test_games_switcher.py -q -p no:cacheprovider`
Expected: 16 FAIL with `AttributeError: module 'games' has no attribute 'GameSwitcher'`.

- [ ] **Step 3: Append to `games.py`:**

```python
class GameSwitcher:
    """Debounced "which profile should be active" decisions. Pure: the
    caller passes the clock, so tests drive it directly.

    step(now, running, fg, mapping, auto, active_profile) is called once per
    poll with the running KNOWN games, the foreground one, {game id: profile
    id} for mapped games, the auto-switch flag and the profile the app shows.
    It returns a switch dict {"seq", "profileId", "reason": "game"|"revert",
    "gameId", "gameName"} when the app should switch, else None.

    - Wanted game: the foreground one if it is a running mapped game; else
      the one already applied while it still runs (alt-tab to a browser does
      not switch back); else the most recently started.
    - A change must hold for `debounce_s` before it commits (alt-tab, game
      restarts and launchers never hammer the keyboard's flash).
    - The first game of a session remembers the active profile; when the
      last mapped game exits the app reverts to it.
    - A manual switch during a session (note_active) cancels that revert and
      the game is not re-applied until it exits or another game takes over.
    - Auto-switch off: nothing is emitted (status still tracks the game).
    """

    def __init__(self, debounce_s=DEBOUNCE_S):
        self.debounce_s = debounce_s
        self.seq = 0
        self.last = None
        self.reset()

    def reset(self):
        """Forget the session (auto-switch toggled): the next poll re-decides
        from scratch, through the debounce, without a revert."""
        self.current = None
        self.current_profile = None
        self.session = False
        self.prev_profile = None
        self.overridden = False
        self._cand = None
        self._cand_since = None
        self._first_seen = {}

    def pick(self, running, fg):
        if fg in running:
            return fg
        if self.current in running:
            return self.current
        if not running:
            return None
        return max(running, key=lambda g: (self._first_seen.get(g, 0.0), g))

    def step(self, now, running, fg, mapping, auto, active_profile, names=None):
        running = {g for g in running if mapping.get(g)}
        for g in list(self._first_seen):
            if g not in running:
                del self._first_seen[g]
        for g in running:
            self._first_seen.setdefault(g, now)
        want = self.pick(running, fg)
        target = (want, mapping.get(want) if want else None)
        if target == (self.current, self.current_profile):
            self._cand = None
            return None
        if self._cand != target:
            self._cand, self._cand_since = target, now
            return None
        if now - self._cand_since < self.debounce_s:
            return None
        self._cand = None
        game, profile = target
        self.current, self.current_profile = target
        if not auto:
            return None
        if game is not None:
            if not self.session:
                self.session = True
                self.prev_profile = active_profile
                self.overridden = False
            elif self.overridden:
                self.overridden = False          # a new game takes over
            return self._emit(profile, "game", game, (names or {}).get(game))
        was = self.session
        prev, overridden = self.prev_profile, self.overridden
        self.session, self.prev_profile, self.overridden = False, None, False
        if was and not overridden and prev:
            return self._emit(prev, "revert", None, None)
        return None

    def _emit(self, profile, reason, game, name):
        self.seq += 1
        self.last = {"seq": self.seq, "profileId": profile, "reason": reason,
                     "gameId": game, "gameName": name}
        return dict(self.last)

    def note_active(self, active_profile, handled_seq):
        """The app reports its active profile and the newest switch it has
        handled. Once it has handled our last switch, a different active
        profile means the user switched by hand: no revert, no re-apply."""
        if (self.session and self.last is not None and active_profile
                and isinstance(handled_seq, int) and handled_seq >= self.seq
                and active_profile != self.last["profileId"]):
            self.overridden = True
            self.prev_profile = None
```

- [ ] **Step 4: Run the tests**

Run: `<py> -m pytest tests/test_games_switcher.py -q -p no:cacheprovider`
Expected: `16 passed`.

- [ ] **Step 5: Commit**

```bash
git add games.py tests/test_games_switcher.py
git commit -m "feat(games): debounced game->profile switch state machine with manual override" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: GameService (settings block, mapping, custom games, status, poll thread)

**Files:**
- Modify: `games.py` (append)
- Test: `tests/test_games_service.py` (create)

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces: `norm_block(b) -> {"autoSwitch": bool|None, "map": {...}}`; `class GameService(data_dir, read_settings, write_settings, platform=None, store=None, scanner=None, programs=None, clock=time.monotonic)` with `available`, `index`, `store`, `switcher`, `profiles`, `active_profile`, `on_detected` (callback `name|None`), `auto_switch` (property), `set_profile(game_id, profile_id|None) -> {"ok", "autoSwitch"}`, `add_custom(exe_path, name=None) -> {"ok", "id", "name"}`, `set_auto(on) -> {"ok", "autoSwitch"}`, `sync(state) -> {"ok"}`, `tick() -> switch|None`, `running() -> list`, `refresh_detectable() -> dict`, `status() -> dict` (keys `ok, available, autoSwitch, detected[{id,name,mapped,profileId}], foreground, active{id,name,profileId}|None, games[{id,name,profileId,custom}], switch, detectable`), `start() -> bool`, `stop()`. Errors raise `ValueError` (the Api turns them into `{"ok": False}`). Test helpers later tasks import: `Clock`, `Scanner` from `tests/test_games_service.py`.

- [ ] **Step 1: Write the failing tests** — `tests/test_games_service.py`:

```python
"""Phase 3: GameService glue (settings.json "games" block, mapping, custom
games, status, tooltip callback, thread gate). Fake scanner + fake clock +
in-memory settings: no processes, no network, no threads unless asked."""
import json

import pytest

import games
from test_games_index import NEON, STARFALL, _fixture_bytes


class Settings:
    """In-memory settings.json with Api.save_settings' top-level merge."""

    def __init__(self, data=None):
        self.data = dict(data or {})
        self.writes = 0

    def read(self):
        return json.loads(json.dumps(self.data))

    def write(self, partial):
        self.writes += 1
        self.data.update(json.loads(json.dumps(partial)))
        return {"ok": True}


class Scanner:
    def __init__(self):
        self.running, self.fg = set(), None

    def __call__(self, index):
        return set(self.running), self.fg


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def _svc(tmp_path, settings=None, platform="win32", with_list=True):
    store = games.DetectableStore(str(tmp_path / "games"),
                                  fetcher=lambda url, cap: _fixture_bytes())
    if with_list:
        store.refresh()
    s = settings or Settings({"activeProfile": "p1"})
    scan, clock = Scanner(), Clock()
    svc = games.GameService(str(tmp_path), s.read, s.write, platform=platform,
                            store=store, scanner=scan, clock=clock,
                            programs=lambda index: [{"exe": "x/x.exe", "name": "x.exe",
                                                     "gameId": None}])
    svc.sync({"activeProfile": "p1", "handledSeq": 0,
              "profiles": [{"id": "p1", "name": "Default"}, {"id": "pg", "name": "Games"}]})
    return svc, s, scan, clock


def _polls(svc, clock, n):
    out = None
    for _ in range(n):
        clock.t += games.POLL_S
        out = svc.tick() or out
    return out


def test_mapping_a_discord_game_stores_its_name_and_exes(tmp_path):
    svc, s, _, _ = _svc(tmp_path)
    assert svc.set_profile(STARFALL, "pg") == {"ok": True, "autoSwitch": True}
    entry = s.data["games"]["map"][STARFALL]
    assert entry == {"name": "Starfall Arena", "exes": ["starfall/starfall.exe"],
                     "profile": "pg", "custom": False}
    assert s.data["games"]["autoSwitch"] is None          # default: ON because a game is mapped


def test_mapped_games_are_detected_even_without_the_discord_list(tmp_path):
    s = Settings({"games": {"map": {STARFALL: {"name": "Starfall Arena",
                                               "exes": ["starfall/starfall.exe"],
                                               "profile": "pg"}}}})
    svc, _, _, _ = _svc(tmp_path, settings=s, with_list=False)
    assert svc.index.match(r"C:\Starfall\starfall.exe") == STARFALL


def test_unknown_game_and_unknown_profile_are_refused(tmp_path):
    svc, _, _, _ = _svc(tmp_path)
    with pytest.raises(ValueError):
        svc.set_profile("123", "pg")
    with pytest.raises(ValueError):
        svc.set_profile(STARFALL, "nope")
    with pytest.raises(ValueError):
        svc.set_profile(STARFALL, "../../evil")


def test_unmapping_removes_the_entry(tmp_path):
    svc, s, _, _ = _svc(tmp_path)
    svc.set_profile(STARFALL, "pg")
    svc.set_profile(STARFALL, None)
    assert s.data["games"]["map"] == {}
    assert svc.auto_switch is False


def test_custom_game_from_a_running_program(tmp_path):
    svc, s, _, _ = _svc(tmp_path)
    r = svc.add_custom(r"C:\Users\me\Games\Indie\Indie.exe", "  My Indie\x07 ")
    assert r == {"ok": True, "id": "custom:indie/indie.exe", "name": "My Indie"}
    assert svc.index.match(r"D:\Indie\INDIE.EXE") == "custom:indie/indie.exe"
    assert s.data["games"]["map"]["custom:indie/indie.exe"]["profile"] is None
    svc.set_profile("custom:indie/indie.exe", "pg")
    assert s.data["games"]["map"]["custom:indie/indie.exe"]["profile"] == "pg"
    with pytest.raises(ValueError):
        svc.add_custom("notes.txt")
    with pytest.raises(ValueError):
        svc.add_custom("")


def test_auto_switch_toggle_is_persisted_and_explicit_off_wins(tmp_path):
    svc, s, _, _ = _svc(tmp_path)
    svc.set_profile(STARFALL, "pg")
    assert svc.set_auto(False) == {"ok": True, "autoSwitch": False}
    assert s.data["games"]["autoSwitch"] is False
    assert svc.auto_switch is False


def test_malformed_settings_block_is_dropped_not_fatal(tmp_path):
    s = Settings({"games": {"autoSwitch": "yes", "map": {
        "abc": {"name": "Bad id", "exes": ["a.exe"]},
        STARFALL: {"name": "", "exes": ["a.exe"]},
        NEON: {"name": "Neon", "exes": ["neonquest.exe"], "profile": "../x"},
        "custom:": {"name": "Empty", "exes": ["a.exe"]}}}})
    svc, _, _, _ = _svc(tmp_path, settings=s)
    st = svc.status()
    assert [g["id"] for g in st["games"]] == [NEON]
    assert st["games"][0]["profileId"] is None
    assert svc._block["autoSwitch"] is None


def test_tick_switches_and_reports_the_tooltip_name(tmp_path):
    svc, _, scan, clock = _svc(tmp_path)
    svc.set_profile(STARFALL, "pg")
    shown = []
    svc.on_detected = shown.append
    scan.running, scan.fg = {STARFALL}, STARFALL
    sw = _polls(svc, clock, 3)
    assert sw["profileId"] == "pg" and sw["gameName"] == "Starfall Arena"
    assert shown == ["Starfall Arena"]                    # once, not every poll
    st = svc.status()
    assert st["active"] == {"id": STARFALL, "name": "Starfall Arena", "profileId": "pg"}
    assert st["detected"] == [{"id": STARFALL, "name": "Starfall Arena", "mapped": True,
                               "profileId": "pg"}]
    assert st["switch"]["seq"] == 1
    svc.sync({"activeProfile": "pg", "handledSeq": 1})
    scan.running, scan.fg = set(), None
    sw = _polls(svc, clock, 3)
    assert sw["profileId"] == "p1" and sw["reason"] == "revert"
    assert shown == ["Starfall Arena", None]


def test_detected_but_unmapped_games_show_but_never_switch(tmp_path):
    svc, _, scan, clock = _svc(tmp_path)
    shown = []
    svc.on_detected = shown.append
    scan.running = {NEON}
    assert _polls(svc, clock, 4) is None
    assert shown == ["Neon Quest"]
    assert svc.status()["detected"][0]["mapped"] is False


def test_previous_profile_falls_back_to_settings_json_before_the_first_sync(tmp_path):
    s = Settings({"activeProfile": "p7"})
    store = games.DetectableStore(str(tmp_path / "g"), fetcher=lambda u, c: _fixture_bytes())
    store.refresh()
    scan, clock = Scanner(), Clock()
    svc = games.GameService(str(tmp_path), s.read, s.write, platform="win32",
                            store=store, scanner=scan, clock=clock)
    svc._block["map"][STARFALL] = {"name": "S", "exes": ["starfall/starfall.exe"],
                                   "profile": "pg", "custom": False}
    scan.running = {STARFALL}
    _polls(svc, clock, 3)
    assert svc.switcher.prev_profile == "p7"


def test_sync_validates_its_input(tmp_path):
    svc, _, _, _ = _svc(tmp_path)
    with pytest.raises(ValueError):
        svc.sync("nope")
    svc.sync({"profiles": [{"id": "ok_1", "name": "\x01A"}, {"id": "bad id"}, "x"],
              "activeProfile": "bad id", "handledSeq": True})
    assert svc.profiles == [{"id": "ok_1", "name": "A"}]
    assert svc.active_profile == "p1"                     # invalid id ignored


def test_unavailable_platform_never_polls_or_starts(tmp_path):
    svc, _, scan, clock = _svc(tmp_path, platform="linux")
    scan.running = {STARFALL}
    assert svc.tick() is None and svc.start() is False and svc._thread is None
    assert svc.running() == []
    st = svc.status()
    assert st["ok"] is True and st["available"] is False


def test_start_and_stop_the_poll_thread(tmp_path, monkeypatch):
    svc, _, _, _ = _svc(tmp_path)
    monkeypatch.setattr(svc.store, "should_refresh", lambda: False)
    assert svc.start() is True and svc._thread.daemon
    assert svc.start() is True                            # idempotent
    svc.stop()
    assert svc._thread is None


def test_refresh_detectable_rebuilds_the_index(tmp_path):
    svc, _, _, _ = _svc(tmp_path, with_list=False)
    assert svc.index.match(r"C:\Starfall\starfall.exe") is None
    assert svc.refresh_detectable() == {"ok": True, "count": 5}
    assert svc.index.match(r"C:\Starfall\starfall.exe") == STARFALL


def test_nothing_about_other_processes_is_kept(tmp_path):
    svc, s, scan, clock = _svc(tmp_path)
    scan.running = {NEON}
    _polls(svc, clock, 2)
    blob = json.dumps(s.data) + json.dumps(svc.status())
    assert "chrome" not in blob and "explorer" not in blob
    assert not hasattr(svc, "processes")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `<py> -m pytest tests/test_games_service.py -q -p no:cacheprovider`
Expected: 15 FAIL with `AttributeError: module 'games' has no attribute 'GameService'`.

- [ ] **Step 3: Append to `games.py`:**

```python
def _norm_entry(gid, e):
    if not isinstance(e, dict):
        return None
    custom = gid.startswith(CUSTOM_PREFIX)
    if not custom and not _ID_RE.match(gid):
        return None
    if custom and not norm_exe(gid[len(CUSTOM_PREFIX):]):
        return None
    name = clean_name(e.get("name"))
    exes = [n for n in (norm_exe(x) for x in (e.get("exes") or []) if isinstance(x, str))
            if n and n.count("/") < MAX_SEGMENTS][:MAX_EXES_PER_GAME]
    prof = e.get("profile")
    if not (isinstance(prof, str) and _PROFILE_RE.match(prof)):
        prof = None
    if not name or not exes:
        return None
    return {"name": name, "exes": exes, "profile": prof, "custom": custom}


def norm_block(b):
    """settings.json "games" block -> {"autoSwitch": bool|None, "map": {...}};
    anything malformed is dropped (the file is user-editable)."""
    b = b if isinstance(b, dict) else {}
    auto = b.get("autoSwitch")
    out = {"autoSwitch": auto if isinstance(auto, bool) else None, "map": {}}
    m = b.get("map")
    if isinstance(m, dict):
        for gid, e in list(m.items())[:MAX_MAPPED]:
            if isinstance(gid, str):
                ne = _norm_entry(gid, e)
                if ne:
                    out["map"][gid] = ne
    return out


class GameService:
    """Owns the user's game map (settings.json "games"), the matcher, the
    switcher and the poll thread. Every public method is called from a
    pywebview bridge thread or the poll thread; one lock guards the state.

    read_settings() -> settings dict or None; write_settings(partial) merges
    (Api.save_settings). scanner(index) -> (running, fg) and the clock are
    injectable for tests; start() is the only thing that creates a thread."""

    def __init__(self, data_dir, read_settings, write_settings, platform=None,
                 store=None, scanner=None, programs=None, clock=time.monotonic):
        self._lock = threading.RLock()
        self.available = processes_supported(platform)
        self.store = store or DetectableStore(os.path.join(data_dir, "games"))
        self._read, self._write = read_settings, write_settings
        self._scan = scanner or scan
        self._programs = programs or running_programs
        self._clock = clock
        self.switcher = GameSwitcher()
        self.on_detected = None            # callback(name or None): tray tooltip
        self.profiles = []                 # [{"id", "name"}] from games_sync
        self.active_profile = None
        self.detected = []
        self.foreground = None
        self.shown = None
        self._thread = None
        self._stop = threading.Event()
        self._refreshing = False
        try:
            self._block = norm_block((read_settings() or {}).get(SETTINGS_KEY))
        except Exception:
            self._block = norm_block(None)
        self.store.load()
        self._rebuild()

    # ---- map + persistence ----------------------------------------------
    def _rebuild(self):
        extra = [{"id": gid, "name": e["name"], "exes": e["exes"]}
                 for gid, e in self._block["map"].items()]
        self.index = DetectableIndex(self.store.games, extra)

    def _save(self):
        r = self._write({SETTINGS_KEY: {"autoSwitch": self._block["autoSwitch"],
                                        "map": self._block["map"]}})
        if isinstance(r, dict) and not r.get("ok", True):
            raise RuntimeError(r.get("error") or "settings not saved")

    @property
    def auto_switch(self):
        a = self._block["autoSwitch"]
        if isinstance(a, bool):
            return a
        return any(e["profile"] for e in self._block["map"].values())

    def _mapping(self):
        return {gid: e["profile"] for gid, e in self._block["map"].items() if e["profile"]}

    def _check_profile(self, profile_id):
        if not (isinstance(profile_id, str) and _PROFILE_RE.match(profile_id)):
            raise ValueError("invalid profile id")
        known = {p["id"] for p in self.profiles}
        if known and profile_id not in known:
            raise ValueError(f"unknown profile {profile_id!r}")

    def set_profile(self, game_id, profile_id):
        with self._lock:
            if not isinstance(game_id, str) or not game_id:
                raise ValueError("invalid game id")
            m = self._block["map"]
            if profile_id is None:
                m.pop(game_id, None)
            else:
                self._check_profile(profile_id)
                if game_id in m:
                    m[game_id]["profile"] = profile_id
                else:
                    if len(m) >= MAX_MAPPED:
                        raise ValueError("too many games")
                    exes = self.index.exes_of(game_id)
                    name = self.index.name_of(game_id)
                    if game_id.startswith(CUSTOM_PREFIX) or not exes or not name:
                        raise ValueError("unknown game")
                    m[game_id] = {"name": name, "exes": exes,
                                  "profile": profile_id, "custom": False}
            self._save()
            self._rebuild()
            return {"ok": True, "autoSwitch": self.auto_switch}

    def add_custom(self, exe_path, name=None):
        with self._lock:
            suffix = exe_suffix(exe_path, 2)
            if not suffix or not suffix.endswith(".exe"):
                raise ValueError("pick a program (.exe)")
            gid = CUSTOM_PREFIX + suffix
            label = clean_name(name) or suffix.rsplit("/", 1)[-1]
            m = self._block["map"]
            if gid in m:
                m[gid]["name"] = label
            else:
                if len(m) >= MAX_MAPPED:
                    raise ValueError("too many games")
                m[gid] = {"name": label, "exes": [suffix], "profile": None, "custom": True}
            self._save()
            self._rebuild()
            return {"ok": True, "id": gid, "name": label}

    def set_auto(self, on):
        with self._lock:
            self._block["autoSwitch"] = bool(on)
            self._save()
            self.switcher.reset()
            return {"ok": True, "autoSwitch": self.auto_switch}

    def sync(self, state):
        """games_sync from app.jsx: profile list, active profile, newest
        switch handled."""
        if not isinstance(state, dict):
            raise ValueError("state must be an object")
        profs = []
        for p in (state.get("profiles") or [])[:MAX_PROFILES]:
            if isinstance(p, dict) and isinstance(p.get("id"), str) and _PROFILE_RE.match(p["id"]):
                profs.append({"id": p["id"], "name": clean_name(p.get("name")) or p["id"]})
        active = state.get("activeProfile")
        active = active if isinstance(active, str) and _PROFILE_RE.match(active) else None
        seq = state.get("handledSeq")
        seq = seq if isinstance(seq, int) and not isinstance(seq, bool) else -1
        with self._lock:
            if profs:
                self.profiles = profs
            if active:
                self.active_profile = active
                self.switcher.note_active(active, seq)
        return {"ok": True}

    def _active_profile(self):
        if self.active_profile:
            return self.active_profile
        try:
            a = (self._read() or {}).get("activeProfile")
        except Exception:
            a = None
        return a if isinstance(a, str) and _PROFILE_RE.match(a) else None

    # ---- detection --------------------------------------------------------
    def tick(self):
        """One poll: scan, decide, notify. Returns the switch dict or None."""
        if not self.available:
            return None
        running, fg = self._scan(self.index)
        with self._lock:
            self.detected = sorted(running)
            self.foreground = fg if fg in running else None
            names = {g: self.index.name_of(g) for g in running}
            sw = self.switcher.step(self._clock(), set(running), self.foreground,
                                    self._mapping(), self.auto_switch,
                                    self._active_profile(), names)
            shown = self.foreground if self.foreground else (
                self.shown if self.shown in running else
                (min(running, key=lambda g: (names.get(g) or "", g)) if running else None))
            changed = shown != self.shown
            self.shown = shown
            label = self.index.name_of(shown) if shown else None
        if sw:
            log.info("game profile switch: %s -> %s (%s)",
                     sw["gameName"] or "-", sw["profileId"], sw["reason"])
        if changed and self.on_detected is not None:
            try:
                self.on_detected(label)
            except Exception:
                pass
        return sw

    def running(self):
        if not self.available:
            return []
        with self._lock:
            index = self.index
        return self._programs(index)

    def refresh_detectable(self):
        r = self.store.refresh()
        if r.get("ok"):
            with self._lock:
                self._rebuild()
        return r

    def _maybe_refresh(self):
        if self._refreshing or not self.store.should_refresh():
            return
        self._refreshing = True

        def run():
            try:
                self.refresh_detectable()
            finally:
                self._refreshing = False
        threading.Thread(target=run, name="aether-games-list", daemon=True).start()

    def status(self):
        with self._lock:
            m = self._block["map"]
            sw = self.switcher
            detected = [{"id": g, "name": self.index.name_of(g) or g,
                         "mapped": bool(m.get(g, {}).get("profile")),
                         "profileId": m.get(g, {}).get("profile")} for g in self.detected]
            games = sorted(({"id": gid, "name": e["name"], "profileId": e["profile"],
                             "custom": e["custom"]} for gid, e in m.items()),
                           key=lambda g: g["name"].lower())
            active = None
            if sw.session and sw.current:
                active = {"id": sw.current,
                          "name": self.index.name_of(sw.current) or sw.current,
                          "profileId": sw.current_profile}
            return {"ok": True, "available": self.available,
                    "autoSwitch": self.auto_switch,
                    "detected": detected, "foreground": self.foreground,
                    "active": active, "games": games,
                    "switch": dict(sw.last) if sw.last else None,
                    "detectable": self.store.info()}

    # ---- thread -----------------------------------------------------------
    def start(self):
        """Start polling (Windows only). Returns whether a thread runs."""
        if not self.available:
            return False
        if self._thread is not None and self._thread.is_alive():
            return True
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="aether-games", daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._stop.set()
        t = self._thread
        if t is not None and t is not threading.current_thread():
            t.join(timeout=2)
        self._thread = None

    def _loop(self):
        while not self._stop.is_set():
            try:
                self._maybe_refresh()
                self.tick()
            except Exception as e:
                log.warning("game detection pass failed: %s", e)
            self._stop.wait(POLL_S)
```

- [ ] **Step 4: Run all games tests**

Run: `<py> -m pytest tests/test_games_index.py tests/test_games_store.py tests/test_games_procs.py tests/test_games_switcher.py tests/test_games_service.py -q -p no:cacheprovider`
Expected: `68 passed, 1 skipped` (on Windows).

- [ ] **Step 5: Commit**

```bash
git add games.py tests/test_games_service.py
git commit -m "feat(games): GameService with settings-backed game map and 3 s poll thread" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Api bridge for games + settings lock + packaging

**Files:**
- Modify: `app_web.py`, `flatpak/io.github.mrwhosnexus.AetherHE.yml`
- Test: `tests/test_games_api.py` (create)

**Interfaces:**
- Consumes: Task 5 `games.GameService`; `tests/test_stats_api.py::_api(tmp_path)` (fake driver/dev/reader, real `KeyMap`, `_settings_path` in `tmp_path`); `Clock`, `Scanner` from Task 5's tests.
- Produces (Api): `self._games` (PRIVATE), `_make_games() -> GameService|None`, `_start_games(on_detected=None) -> bool`, `_stop_games()`; bridge `games_status()`, `list_running_games() -> {"ok", "programs"}`, `set_game_profile(game_id, profile_id=None)`, `add_custom_game(exe_path, name=None)`, `refresh_detectable()`, `set_games_auto_switch(on)`, `games_sync(state)`. Module `_SETTINGS_LOCK`.

- [ ] **Step 1: Write the failing tests** — `tests/test_games_api.py`:

```python
"""Phase 3 bridge: the games_* Api methods (never raise to JS), the settings
lock, and the service lifecycle hooks. Fakes only: no HID, no network, no
real processes."""
import json
import os
import re
import threading

import app_web
import games
from test_games_index import STARFALL, _fixture_bytes
from test_games_service import Clock, Scanner
from test_stats_api import _api

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _with_games(a, tmp_path, platform="win32"):
    store = games.DetectableStore(str(tmp_path / "games"),
                                  fetcher=lambda url, cap: _fixture_bytes())
    store.refresh()
    read = lambda: (a.load_settings() or {}).get("settings")      # noqa: E731
    a._games = games.GameService(str(tmp_path), read, a.save_settings,
                                 platform=platform, store=store, scanner=Scanner(),
                                 clock=Clock(),
                                 programs=lambda index: [{"exe": "indie/indie.exe",
                                                          "name": "indie.exe",
                                                          "gameId": None}])
    return a


def test_without_a_service_every_bridge_call_answers(tmp_path):
    a = _api(tmp_path)
    st = a.games_status()
    assert st["ok"] is True and st["available"] is False and st["games"] == []
    assert a.list_running_games()["ok"] is False
    assert a.set_game_profile(STARFALL, "p1")["ok"] is False
    assert a.add_custom_game("x/y.exe", "Y")["ok"] is False
    assert a.refresh_detectable()["ok"] is False
    assert a.set_games_auto_switch(True)["ok"] is False
    assert a.games_sync({"activeProfile": "p1"}) == {"ok": True}


def test_bridge_round_trip_persists_into_settings_json(tmp_path):
    a = _with_games(_api(tmp_path), tmp_path)
    a.save_settings({"profiles": [{"id": "p1"}], "activeProfile": "p1"})
    assert a.games_sync({"activeProfile": "p1", "handledSeq": 0,
                         "profiles": [{"id": "p1", "name": "Default"},
                                      {"id": "pg", "name": "Games"}]})["ok"]
    assert a.set_game_profile(STARFALL, "pg") == {"ok": True, "autoSwitch": True}
    r = a.add_custom_game(r"C:\Games\Indie\Indie.exe", "Indie")
    assert r == {"ok": True, "id": "custom:indie/indie.exe", "name": "Indie"}
    assert a.list_running_games()["programs"][0]["exe"] == "indie/indie.exe"
    with open(a._settings_path(), encoding="utf-8") as f:
        data = json.load(f)
    assert data["profiles"] == [{"id": "p1"}]                    # UI keys preserved
    assert set(data["games"]["map"]) == {STARFALL, "custom:indie/indie.exe"}
    st = a.games_status()
    assert [g["name"] for g in st["games"]] == ["Indie", "Starfall Arena"]
    assert a.set_games_auto_switch(False) == {"ok": True, "autoSwitch": False}


def test_bridge_turns_errors_into_ok_false(tmp_path):
    a = _with_games(_api(tmp_path), tmp_path)
    for r in (a.set_game_profile("999", "p1"), a.set_game_profile(None, "p1"),
              a.add_custom_game("notes.txt"), a.add_custom_game(None),
              a.games_sync("nope")):
        assert r["ok"] is False and r["error"]
    a._games.status = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    assert a.games_status() == {"ok": False, "error": "boom"}


def test_refresh_detectable_goes_through_the_injected_fetcher(tmp_path):
    a = _with_games(_api(tmp_path), tmp_path)
    assert a.refresh_detectable() == {"ok": True, "count": 5}
    a._games.store._fetch = lambda url, cap: (_ for _ in ()).throw(OSError("offline"))
    r = a.refresh_detectable()
    assert r["ok"] is False and "offline" in r["error"]


def test_make_games_reads_settings_and_starts_no_thread(tmp_path, monkeypatch):
    monkeypatch.setattr(app_web, "user_data_dir", lambda: str(tmp_path))
    a = _api(tmp_path)
    with open(a._settings_path(), "w", encoding="utf-8") as f:
        json.dump({"games": {"map": {STARFALL: {"name": "Starfall Arena",
                                                "exes": ["starfall/starfall.exe"],
                                                "profile": "p1"}}}}, f)
    svc = a._make_games()
    assert isinstance(svc, games.GameService) and svc._thread is None
    assert svc.status()["games"][0]["id"] == STARFALL
    assert svc.store.path == os.path.join(str(tmp_path), "games", "detectable.json")


def test_start_and_stop_hooks(tmp_path):
    a = _with_games(_api(tmp_path), tmp_path, platform="linux")
    seen = []
    assert a._start_games(seen.append) is False            # Linux: no thread
    assert a._games.on_detected == seen.append
    a._stop_games()
    a._games = None
    assert a._start_games(None) is False
    a._stop_games()


def test_concurrent_settings_saves_never_drop_a_key(tmp_path):
    a = _api(tmp_path)
    threads = [threading.Thread(target=a.save_settings, args=({f"k{i}": i},))
               for i in range(24)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    with open(a._settings_path(), encoding="utf-8") as f:
        data = json.load(f)
    assert all(data.get(f"k{i}") == i for i in range(24))


def test_the_service_is_never_a_public_api_attribute():
    src = open(os.path.join(ROOT, "app_web.py"), encoding="utf-8").read()
    assert re.search(r"self\.games\s*=", src) is None       # pywebview walks public attrs
    assert "self._games = self._make_games()" in src
```

- [ ] **Step 2: Run them to verify they fail**

Run: `<py> -m pytest tests/test_games_api.py -q -p no:cacheprovider`
Expected: FAIL (`AttributeError: 'Api' object has no attribute 'games_status'`, `_make_games`, the source assertion).

- [ ] **Step 3: Edit `app_web.py`** (exactly these changes):
- Imports: add `import games` right after `import gamepad`.
- Below `STATS_SETTING = "collectKeyStats"` add:

```python

# Serialises Api.save_settings' read-merge-write: the UI's profile saves and
# Python-side writers (games map, stats toggle) run on different pywebview /
# poll threads, and two interleaved merges would drop one writer's keys.
_SETTINGS_LOCK = threading.Lock()
```

- `Api.save_settings`: keep the docstring and the `try/except`; after `path = self._settings_path()` wrap the whole read → merge → `json.dump` sequence in `with _SETTINGS_LOCK:` (the `return {"ok": True, "path": path}` stays after the `with`).
- `Api.__init__`: append `self._games = self._make_games()` as the last line (after `self.telemetry = self._make_telemetry()`).
- Insert directly above `def _stats_supported(self):`:

```python
    def _make_games(self):
        """Game detection service (games.py). Reads the cached Discord list;
        no thread until _start_games. Never raises: None disables it."""
        try:
            return games.GameService(
                user_data_dir(),
                lambda: (self.load_settings() or {}).get("settings"),
                self.save_settings)
        except Exception as e:
            log.warning("game detection unavailable: %s", e)
            return None

    def _start_games(self, on_detected=None):
        """main(): start polling (Windows only). `on_detected(name|None)`
        feeds the tray tooltip."""
        g = getattr(self, "_games", None)
        if g is None:
            return False
        g.on_detected = on_detected
        return g.start()

    def _stop_games(self):
        g = getattr(self, "_games", None)
        if g is not None:
            g.stop()
```

- Insert directly above the comment line `    # ---- advanced keys + per-key remap (MINI 60 HE PRO family) ----`:

```python
    # ---- games: detection + per-game profiles (games.py) ----
    #
    # Python decides WHICH profile should be active (debounced); app.jsx polls
    # games_status(), switches the profile like the profile menu does (its
    # lighting effects then follow) and hands the profile's actuation / RT /
    # SOCD to apply_profile_to_board. games_sync reports the active profile
    # back, so a manual switch during a game cancels the revert.
    _GAMES_OFF = {"ok": False, "error": "game detection is unavailable"}

    def games_status(self):
        try:
            g = getattr(self, "_games", None)
            if g is None:
                return {"ok": True, "available": False, "autoSwitch": False,
                        "detected": [], "foreground": None, "active": None,
                        "games": [], "switch": None, "detectable": None}
            return g.status()
        except Exception as e:
            return self._fail(e)

    def list_running_games(self):
        """Running user programs for the "add a game" picker. Built on demand,
        never stored or logged."""
        try:
            g = getattr(self, "_games", None)
            if g is None:
                return dict(self._GAMES_OFF)
            return {"ok": True, "programs": g.running()}
        except Exception as e:
            return self._fail(e)

    def set_game_profile(self, game_id, profile_id=None):
        """Map a game to a profile id, or unmap it (None): unmapping a
        program you added removes it."""
        try:
            g = getattr(self, "_games", None)
            if g is None:
                return dict(self._GAMES_OFF)
            return g.set_profile(game_id, profile_id)
        except Exception as e:
            return self._fail(e)

    def add_custom_game(self, exe_path, name=None):
        try:
            g = getattr(self, "_games", None)
            if g is None:
                return dict(self._GAMES_OFF)
            return g.add_custom(exe_path, name)
        except Exception as e:
            return self._fail(e)

    def refresh_detectable(self):
        """Download Discord's game list now (HTTPS, 5 MB cap). Nothing is
        uploaded."""
        try:
            g = getattr(self, "_games", None)
            if g is None:
                return dict(self._GAMES_OFF)
            return g.refresh_detectable()
        except Exception as e:
            return self._fail(e)

    def set_games_auto_switch(self, on):
        try:
            g = getattr(self, "_games", None)
            if g is None:
                return dict(self._GAMES_OFF)
            return g.set_auto(bool(on))
        except Exception as e:
            return self._fail(e)

    def games_sync(self, state):
        """app.jsx -> Python: {activeProfile, profiles: [{id, name}], handledSeq}."""
        try:
            g = getattr(self, "_games", None)
            if g is None:
                return {"ok": True}
            return g.sync(state)
        except Exception as e:
            return self._fail(e)
```

In `flatpak/io.github.mrwhosnexus.AetherHE.yml`, in the `cp -r app_web.py ...` command change `telemetry.py tools data ui` to `telemetry.py games.py tools data ui` (`tests/test_packaging.py::test_flatpak_packages_entire_import_closure` fails without it).

- [ ] **Step 4: Run the tests**

Run: `<py> -m pytest tests/test_games_api.py tests/test_settings_merge.py tests/test_packaging.py tests/test_tray.py tests/test_stats_api.py -q -p no:cacheprovider`
Expected: all pass (`8` in `test_games_api.py`).

- [ ] **Step 5: Commit**

```bash
git add app_web.py flatpak/io.github.mrwhosnexus.AetherHE.yml tests/test_games_api.py
git commit -m "feat(api): game detection bridge and serialised settings writes" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: `apply_profile_to_board` — the board half of a game switch

**Files:**
- Modify: `app_web.py`
- Test: `tests/test_games_apply.py` (create)

**Interfaces:**
- Consumes: existing `Api.set_trigger_all(travel_mm, rt_press_mm, rt_release_mm, key_count=64, mode=0)`, `Api.set_socd(pairs)`, `Api.verify_actuation(codes)`, `Api._clamp_mm(range_key, mm)`, `Api._act_mm` (Phase 2).
- Produces (Api): bridge `apply_profile_to_board(spec) -> {"ok", "deferred", "actuation", "socd"}`; `_board_spec`, `_board_has_actuation`, `_apply_board_spec`, `_apply_pending_board`, `_note_trigger_modes(idxs, mode, rtp, rtr)`, `_note_read_back_modes(detail_by_idx)`, `_socd_key(pairs)` (staticmethod); state `_trig_mode`, `_socd_last`, `_pending_board`.

- [ ] **Step 1: Write the failing tests** — `tests/test_games_apply.py`:

```python
"""Phase 3: apply_profile_to_board, the board half of a game switch.
Actuation/RT to all keys + SOCD through the existing Api paths, skipped when
the read-back says the board already holds it, deferred while offline.
Fakes only: no HID, no keyboard."""
import pytest

from test_stats_api import FakeDriver, _api


class RecordingDriver(FakeDriver):
    def __init__(self):
        super().__init__()
        self.actuation, self.socd = [], []
        self.fail = False

    def set_actuation(self, idxs, mode, travel, rt1, rt2):
        if self.fail:
            raise RuntimeError("link lost")
        self.actuation.append((len(idxs), mode, round(travel, 2), rt1, rt2))

    def set_socd(self, plist):
        self.socd.append(list(plist))


SPEC = {"actuation": 0.8, "rtEnabled": False, "rtPress": 0.05, "rtRelease": 0.05,
        "socd": [{"model": 1, "key1": "A", "key2": "D"}]}


def _a(tmp_path):
    a = _api(tmp_path)
    a.driver = RecordingDriver()
    return a


def _all_keys(a):
    return sorted(set(a.km.index_of_code.values()))


def _read_back(a, mm=0.8, mode=0, rtp=0.05, rtr=0.05, only=None):
    names = [a.km.by_index[i]["name"] for i in (only or _all_keys(a))]
    a.driver.detail = {n: {"travel_mm": mm, "mode": mode, "rt_press_mm": rtp,
                           "rt_release_mm": rtr} for n in names}
    assert a.verify_actuation([])["ok"]


def test_first_apply_writes_all_keys_and_socd(tmp_path):
    a = _a(tmp_path)
    r = a.apply_profile_to_board(SPEC)
    assert r == {"ok": True, "deferred": False, "actuation": "written", "socd": "written"}
    assert a.driver.actuation == [(len(a.km.indices()), 0, 0.8, None, None)]
    assert len(a.driver.socd) == 1 and len(a.driver.socd[0]) == 1


def test_board_that_already_matches_is_not_written(tmp_path):
    a = _a(tmp_path)
    _read_back(a, 0.8)
    a._socd_last = a._socd_key(SPEC["socd"])
    r = a.apply_profile_to_board(SPEC)
    assert r["actuation"] == "unchanged" and r["socd"] == "unchanged"
    assert a.driver.actuation == [] and a.driver.socd == []


def test_a_repeated_apply_is_skipped(tmp_path):
    a = _a(tmp_path)
    a.apply_profile_to_board(SPEC)
    r = a.apply_profile_to_board(SPEC)
    assert r["actuation"] == "unchanged" and r["socd"] == "unchanged"
    assert len(a.driver.actuation) == 1 and len(a.driver.socd) == 1


def test_different_travel_or_partial_read_back_writes(tmp_path):
    a = _a(tmp_path)
    _read_back(a, 1.2)
    assert a.apply_profile_to_board(SPEC)["actuation"] == "written"
    b = _a(tmp_path)
    _read_back(b, 0.8, only=_all_keys(b)[:5])               # most keys unknown
    assert b.apply_profile_to_board(SPEC)["actuation"] == "written"


def test_rapid_trigger_compares_mode_and_pair(tmp_path):
    a = _a(tmp_path)
    _read_back(a, 0.8, mode=13, rtp=0.1, rtr=0.1)
    rt = dict(SPEC, rtEnabled=True, rtPress=0.1, rtRelease=0.1, socd=None)
    assert a.apply_profile_to_board(rt)["actuation"] == "unchanged"
    assert a.apply_profile_to_board(dict(rt, rtRelease=0.2))["actuation"] == "written"
    assert a.driver.actuation[-1] == (len(a.km.indices()), 13, 0.8, 0.1, 0.2)
    assert a.apply_profile_to_board(dict(rt, rtEnabled=False))["actuation"] == "written"
    assert a.driver.actuation[-1][1] == 0


def test_socd_order_or_content_change_is_written(tmp_path):
    a = _a(tmp_path)
    a.apply_profile_to_board(SPEC)
    two = [{"model": 1, "key1": "A", "key2": "D"}, {"model": 1, "key1": "W", "key2": "S"}]
    assert a.apply_profile_to_board(dict(SPEC, socd=two))["socd"] == "written"
    assert a.apply_profile_to_board(dict(SPEC, socd=two[::-1]))["socd"] == "written"
    assert a.apply_profile_to_board(dict(SPEC, socd=[]))["socd"] == "written"   # [] clears


def test_a_manual_socd_write_is_remembered(tmp_path):
    a = _a(tmp_path)
    assert a.set_socd(SPEC["socd"])["ok"]
    assert a.apply_profile_to_board(dict(SPEC, actuation=None))["socd"] == "unchanged"


def test_null_fields_are_left_alone(tmp_path):
    a = _a(tmp_path)
    r = a.apply_profile_to_board({})
    assert r == {"ok": True, "deferred": False, "actuation": "skipped", "socd": "skipped"}
    assert a.driver.actuation == [] and a.driver.socd == []


def test_actuation_is_clamped_to_the_board_range(tmp_path):
    a = _a(tmp_path)
    a.apply_profile_to_board(dict(SPEC, actuation=0.01, socd=None))
    lo = a.board.actuation["travelRange"][0]
    assert a.driver.actuation[-1][2] == pytest.approx(lo)


@pytest.mark.parametrize("bad", ["x", None, {"actuation": "abc"}, {"actuation": -1},
                                 {"actuation": float("nan")}, {"socd": "x"},
                                 {"socd": [{"key1": "A"}]}, {"socd": [{"key1": "A", "key2": "D",
                                                                       "model": 999}]}])
def test_invalid_specs_fail_cleanly(tmp_path, bad):
    a = _a(tmp_path)
    r = a.apply_profile_to_board(bad)
    assert r["ok"] is False and r["error"]
    assert a.driver.actuation == [] and a.driver.socd == []


def test_failed_write_names_the_step_and_is_not_remembered(tmp_path):
    a = _a(tmp_path)
    a.driver.fail = True
    r = a.apply_profile_to_board(SPEC)
    assert r["ok"] is False and r["step"] == "actuation" and "link lost" in r["error"]
    a.driver.fail = False
    assert a.apply_profile_to_board(SPEC)["actuation"] == "written"


def test_offline_apply_is_deferred_and_the_newest_wins(tmp_path):
    a = _a(tmp_path)
    a.dev.open = False
    assert a.apply_profile_to_board(dict(SPEC, actuation=1.0)) == {"ok": True, "deferred": True}
    assert a.apply_profile_to_board(SPEC) == {"ok": True, "deferred": True}
    assert a.driver.actuation == []
    a.dev.open = True
    assert a._connect(resume=False)["ok"] is True
    assert a.driver.actuation == [(len(a.km.indices()), 0, 0.8, None, None)]
    assert a._pending_board is None
    a._connect(resume=False)
    assert len(a.driver.actuation) == 1                     # applied once


def test_reconnect_forgets_what_the_board_holds(tmp_path):
    a = _a(tmp_path)
    a.apply_profile_to_board(SPEC)
    a._connect(resume=False)
    r = a.apply_profile_to_board(SPEC)
    assert r["actuation"] == "written" and r["socd"] == "written"


def test_selecting_another_board_drops_board_state(tmp_path):
    a = _a(tmp_path)
    a.apply_profile_to_board(SPEC)
    a.dev.open = False
    a.apply_profile_to_board(SPEC)
    a._registry = None
    a._remaps, a._deadband_state, a._fn_layer_raw = {}, {}, None
    assert a.select_board("aula-mini60he-pro")["ok"] is True
    assert a._trig_mode == {} and a._socd_last is None and a._pending_board is None
```

- [ ] **Step 2: Run them to verify they fail**

Run: `<py> -m pytest tests/test_games_apply.py -q -p no:cacheprovider`
Expected: FAIL with `AttributeError: 'Api' object has no attribute 'apply_profile_to_board'` (and `_socd_key`, `_trig_mode`).

- [ ] **Step 3: Edit `app_web.py`** (exactly these changes):
- `Api.__init__`: directly after `self._act_mm = {}` add:

```python
        # idx -> (trigger mode, rt press mm|None, rt release mm|None) from the
        # same read-back / successful writes; with _act_mm it tells
        # apply_profile_to_board whether the board already holds a profile's
        # actuation (skip the flash write). Cleared on every connect.
        self._trig_mode = {}
        self._socd_last = None      # last SOCD pairs written this connection
        self._pending_board = None  # game-profile board apply waiting for connect
```

- After `def _actuation_snapshot(self): ...` (3 lines) insert:

```python
    def _note_trigger_modes(self, idxs, mode, rt_press_mm, rt_release_mm):
        """A successful actuation write: remember each key's trigger mode
        (and RT pair in an RT mode; mode 0 keeps the stored pair, unknown)."""
        cur = getattr(self, "_trig_mode", None)
        if cur is None:
            cur = self._trig_mode = {}
        mode = int(mode)
        rt = ((None, None) if mode == 0
              else (round(float(rt_press_mm), 2), round(float(rt_release_mm), 2)))
        for i in idxs:
            cur[i] = (mode,) + rt

    def _note_read_back_modes(self, detail_by_idx):
        """verify_actuation's per-key trigger detail -> _trig_mode."""
        cur = getattr(self, "_trig_mode", None)
        if cur is None:
            cur = self._trig_mode = {}
        for idx, d in (detail_by_idx or {}).items():
            try:
                cur[idx] = (int(d["mode"]), round(float(d.get("rt_press_mm") or 0.0), 2),
                            round(float(d.get("rt_release_mm") or 0.0), 2))
            except (KeyError, TypeError, ValueError):
                cur.pop(idx, None)
```

- `_connect`: directly after `info = self.driver.connect()` insert

```python
            # Fresh handle: what the board holds is unknown until the UI's
            # read-back, so the next profile apply writes instead of skipping.
            self._trig_mode = {}
            self._socd_last = None
```

  and directly after `self._start_stats_reader()` (inside `_connect`, before `return {"ok": True, "iface": ...}`) add `self._apply_pending_board()`.
- `select_board`: in the per-board cache reset after `self._act_mm = {}` add `self._trig_mode = {}`, `self._socd_last = None`, `self._pending_board = None` (one per line).
- `set_trigger_all`: after `self._note_actuation({i: float(travel_mm) for i in idxs})` add `self._note_trigger_modes(idxs, mode, rt_press_mm, rt_release_mm)`.
- `set_trigger_codes`: after `self._note_actuation({i: travel_mm for i in idxs})` add `self._note_trigger_modes(idxs, mode, rt_press_mm, rt_release_mm)` (here `rt_press_mm`/`rt_release_mm` are already clamped).
- `verify_actuation`: change `all_by_code, trig_by_code, act_by_idx = {}, {}, {}` to `all_by_code, trig_by_code, act_by_idx, trig_by_idx = {}, {}, {}, {}`; inside `if detail is not None and name in detail:` add `trig_by_idx[idx] = detail[name]` after the `trig_by_code[...]` line; after `self._note_actuation(act_by_idx)` add `self._note_read_back_modes(trig_by_idx)`. The returned dict is unchanged.
- SOCD section: directly under `# ---- SOCD / PRCS ----` (above `def set_socd`) insert:

```python
    @staticmethod
    def _socd_key(pairs):
        """Comparable form of a set_socd pair list (order kept: it is the
        slot order on the board)."""
        return tuple((int(p["model"]), str(p["key1"]), str(p["key2"])) for p in pairs)

```

  and in `set_socd`, after `self.driver.set_socd(plist)` add `self._socd_last = self._socd_key(pairs)`.
- Insert directly above the comment line `    # ---- advanced keys + per-key remap (MINI 60 HE PRO family) ----` (i.e. after Task 6's `games_sync`):

```python
    def _board_spec(self, spec):
        """Validate apply_profile_to_board's argument. ValueError if bad."""
        if not isinstance(spec, dict):
            raise ValueError("profile spec must be an object")
        out = {"actuation": None, "mode": 0, "rtPress": None, "rtRelease": None,
               "socd": None}
        a = spec.get("actuation")
        if a is not None:
            a = float(a)
            if not (a == a) or not 0.0 < a <= 10.0:
                raise ValueError("invalid actuation")
            out["actuation"] = round(self._clamp_mm("travelRange", a), 2)
            if spec.get("rtEnabled"):
                out["mode"] = 13
                out["rtPress"] = round(self._clamp_mm("rtRange", float(spec.get("rtPress", 0.05))), 2)
                out["rtRelease"] = round(self._clamp_mm("rtRange", float(spec.get("rtRelease", 0.05))), 2)
        pairs = spec.get("socd")
        if pairs is not None:
            if not isinstance(pairs, list) or len(pairs) > 16:
                raise ValueError("invalid SOCD list")
            norm = []
            for p in pairs:
                if not isinstance(p, dict):
                    raise ValueError("invalid SOCD pair")
                k1, k2, model = p.get("key1"), p.get("key2"), int(p.get("model", 1))
                if not (isinstance(k1, str) and isinstance(k2, str) and 0 < len(k1) <= 32
                        and 0 < len(k2) <= 32 and 0 <= model <= 255):
                    raise ValueError("invalid SOCD pair")
                norm.append({"model": model, "key1": k1, "key2": k2})
            out["socd"] = norm
        return out

    def _board_has_actuation(self, spec):
        """True only when the last read-back/write says EVERY key already has
        this travel and trigger mode (and RT pair in RT mode)."""
        km = getattr(self, "km", None)
        if not km:
            return False
        idxs = set(km.index_of_code.values())
        act = getattr(self, "_act_mm", None) or {}
        trig = getattr(self, "_trig_mode", None) or {}
        if not idxs:
            return False
        for i in idxs:
            mm, t = act.get(i), trig.get(i)
            if mm is None or t is None or t[0] != spec["mode"]:
                return False
            if abs(mm - spec["actuation"]) > 0.005:
                return False
            if spec["mode"] != 0 and (t[1] is None or t[2] is None
                                      or abs(t[1] - spec["rtPress"]) > 0.005
                                      or abs(t[2] - spec["rtRelease"]) > 0.005):
                return False
        return True

    def _apply_board_spec(self, spec):
        """Write a validated spec through the normal paths, skipping what the
        board already holds (flash wear)."""
        out = {"ok": True, "deferred": False, "actuation": "skipped", "socd": "skipped"}
        if spec["actuation"] is not None:
            if self._board_has_actuation(spec):
                out["actuation"] = "unchanged"
            else:
                r = self.set_trigger_all(spec["actuation"], spec["rtPress"] or 0.0,
                                         spec["rtRelease"] or 0.0, mode=spec["mode"])
                if not r.get("ok"):
                    return {**r, "step": "actuation"}
                out["actuation"] = "written"
        if spec["socd"] is not None:
            if self._socd_key(spec["socd"]) == getattr(self, "_socd_last", None):
                out["socd"] = "unchanged"
            else:
                r = self.set_socd(spec["socd"])
                if not r.get("ok"):
                    return {**r, "step": "socd", "actuation": out["actuation"]}
                out["socd"] = "written"
        return out

    def apply_profile_to_board(self, spec):
        """A game switch's board half: {actuation, rtEnabled, rtPress,
        rtRelease, socd: [{model, key1, key2}]} from the profile app.jsx just
        switched to (null fields are left alone). Actuation/RT go to ALL keys
        via set_trigger_all, SOCD via set_socd; anything the board already
        holds is skipped. While disconnected the spec is kept and applied on
        the next connect (the newest one wins)."""
        try:
            norm = self._board_spec(spec)
            dev = getattr(self, "dev", None)
            if dev is None or not dev.is_open():
                self._pending_board = norm
                return {"ok": True, "deferred": True}
            self._pending_board = None
            return self._apply_board_spec(norm)
        except Exception as e:
            return self._fail(e)

    def _apply_pending_board(self):
        """connect(): apply a game profile that arrived while offline. Never
        raises (connect must still report the open handle)."""
        spec = getattr(self, "_pending_board", None)
        if spec is None:
            return
        self._pending_board = None
        try:
            r = self._apply_board_spec(spec)
            if not r.get("ok"):
                log.warning("game profile not applied after connect: %s", r.get("error"))
        except Exception as e:
            log.warning("game profile not applied after connect: %s", e)
```

- [ ] **Step 4: Run the tests and the suites that touch this code**

Run: `<py> -m pytest tests/test_games_apply.py tests/test_games_api.py tests/test_pressure_api.py tests/test_stats_api.py tests/test_actuation_readback.py tests/test_socd_clear.py tests/test_link_recovery.py tests/test_drivers.py tests/test_win60_settings_fixes.py -q -p no:cacheprovider`
Expected: all pass (`21` in `test_games_apply.py`).

- [ ] **Step 5: Commit**

```bash
git add app_web.py tests/test_games_apply.py
git commit -m "feat(api): apply a game profile to the board, skipping what it already holds" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Tray tooltip + lifetime wiring in `main()`

**Files:**
- Modify: `tray.py`, `app_web.py` (`main()` only)
- Test: `tests/test_games_tray.py` (create)

**Interfaces:**
- Consumes: Task 6 `Api._start_games(on_detected)`, `Api._stop_games()`; `StubApi`, `StubIcon` from `tests/test_tray.py`.
- Produces: `TrayController.title` (str, default `APP_NAME`), `TrayController.set_game(name|None)`.

- [ ] **Step 1: Write the failing tests** — `tests/test_games_tray.py`:

```python
"""Phase 3: the tray tooltip names the detected game, and main() runs the
game service for the app's lifetime. No pystray, no window."""
import os

import tray
from test_tray import StubApi, StubIcon

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_tooltip_shows_the_detected_game_and_clears():
    c = tray.TrayController(StubApi())
    c.icon = StubIcon()
    c.set_game("Neon Quest")
    assert c.icon.title == c.title == "Aether HE — Neon Quest"
    c.set_game(None)
    assert c.icon.title == "Aether HE"


def test_tooltip_is_plain_capped_text():
    c = tray.TrayController(StubApi())
    c.set_game("Bad\x07\nName" + "x" * 300)
    assert c.title.startswith("Aether HE — BadName") and len(c.title) <= 120
    assert "\n" not in c.title and "\x07" not in c.title


def test_tooltip_set_before_the_icon_exists_is_used_when_it_starts():
    c = tray.TrayController(StubApi())
    c.set_game("Starfall Arena")                  # icon not created yet: no error
    assert c.title == "Aether HE — Starfall Arena"
    src = open(os.path.join(ROOT, "tray.py"), encoding="utf-8").read()
    assert 'pystray.Icon("aether-he", image, self.title, menu)' in src


def test_icon_errors_never_escape():
    class Grumpy(StubIcon):
        def __setattr__(self, k, v):
            if k == "title":
                raise RuntimeError("shell said no")
            super().__setattr__(k, v)
    c = tray.TrayController(StubApi())
    c.icon = Grumpy()
    c.set_game("X")
    assert c.title == "Aether HE — X"


def test_main_runs_the_game_service_for_the_app_lifetime():
    src = open(os.path.join(ROOT, "app_web.py"), encoding="utf-8").read()
    main = src[src.index("def main():"):]
    assert "api._start_games(tray_ctl.set_game)" in main
    assert main.index("api._start_games(") > main.index("tray_ctl = tray.TrayController(")
    fin = main[main.index("finally:"):]
    assert "api._stop_games()" in fin
```

- [ ] **Step 2: Run them to verify they fail**

Run: `<py> -m pytest tests/test_games_tray.py -q -p no:cacheprovider`
Expected: 5 FAIL (`AttributeError: 'TrayController' object has no attribute 'set_game'`, source assertions).

- [ ] **Step 3: Edit `tray.py`:**
- `TrayController.__init__`: after `self._Image = None` add

```python
        # Tooltip text; set_game() puts the detected game in it.
        self.title = APP_NAME
```

- `start()`: `pystray.Icon("aether-he", image, APP_NAME, menu)` becomes `pystray.Icon("aether-he", image, self.title, menu)`.
- Insert directly above `    # ---- windows ---------------------------------------------------------`:

```python
    def set_game(self, name):
        """Tooltip: "Aether HE — <game>" while a game is detected, plain
        "Aether HE" otherwise (games.GameService.on_detected). The name is
        untrusted text from Discord's list; the shell shows it as text and
        Windows caps tooltips at 128 characters."""
        name = name if isinstance(name, str) else ""
        name = "".join(ch for ch in name if ch >= " ").strip()
        title = f"{APP_NAME} — {name}" if name else APP_NAME
        self.title = title[:120]
        icon = self.icon
        if icon is not None:
            try:
                icon.title = self.title
            except Exception as e:
                log.debug("tray tooltip not updated: %s", e)
```

**Edit `app_web.py` `main()`:** directly after `tray_ctl = tray.TrayController(api, webview)` add

```python
    # Game detection polls from here on (Windows only); the tray tooltip
    # names the detected game.
    api._start_games(tray_ctl.set_game)
```

and in the final `finally:` block, between the `tray_ctl.exit()` try/except and `inst.release()`, add `api._stop_games()`.

- [ ] **Step 4: Run the tests**

Run: `<py> -m pytest tests/test_games_tray.py tests/test_tray.py tests/test_single_instance.py tests/test_boot.py -q -p no:cacheprovider`
Expected: all pass (`5` new). `tests/test_tray.py::test_api_exposes_no_tray_or_window_objects_to_pywebview` must still pass (`api._start_games(...)` is a call, not a public attribute).

- [ ] **Step 5: Commit**

```bash
git add tray.py app_web.py tests/test_games_tray.py
git commit -m "feat(tray): tooltip names the detected game; game detection runs for the app lifetime" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: UI — apply game switches in `app.jsx`, Settings "Games" widget

**Files:**
- Modify: `ui/runtime_src/src/app.jsx`, `ui/runtime_src/workspaces/settings.jsx`
- Regenerated: `ui/index_runtime.html`, `ui/runtime_src/build/app.js`, `ui/runtime_src/build/ws_settings.js`
- Test: `tests/test_games_ui_sources.py` (create)

**Interfaces:**
- Consumes: Tasks 6–7 bridge methods; `games_status().switch = {"seq", "profileId", "reason", "gameId", "gameName"}`; `apply_profile_to_board` result `actuation: "written"|...`.
- Produces (app.jsx, module level): `socdPairsFrom(rows)`, `profileBoardSpec(state)`; (component) `gameSeqRef`, `actReadNonce`; (settings.jsx) `GamesWidget(ctx)` reading `ctx.profiles`, `ctx.activeId`; `SETTINGS_WIDGETS` entry `id: "games"`.

- [ ] **Step 1: Write the failing tests** — `tests/test_games_ui_sources.py`:

```python
"""Phase 3 UI wiring guards (JSX is not executed in tests): the app polls
the game decision and applies it through the bridge, the Settings "Games"
widget exists, and untrusted game names never reach a raw-HTML sink."""
import os
import re

import app_web

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, "ui", "runtime_src")


def _read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as fh:
        return fh.read()


def test_app_polls_games_status_and_applies_through_the_bridge():
    app = _read(SRC, "src", "app.jsx")
    assert 'apiCall("games_status")' in app
    assert 'apiCall("apply_profile_to_board", profileBoardSpec(p.state))' in app
    assert re.search(r'apiCall\("games_sync", \{\s*activeProfile: active, handledSeq: seq,', app)
    assert "sw.seq > gameSeqRef.current" in app
    assert "switchProfileRef.current(p.id)" in app          # same path as the profile menu
    assert "[connected, actReadNonce]" in app                # re-read after a write


def test_profile_board_spec_and_socd_pairs_are_shared():
    app = _read(SRC, "src", "app.jsx")
    assert "const socdPairsFrom = (rows) =>" in app
    assert "const pairs = socdPairsFrom(profiles);" in app   # SOCD tab uses the same mapping
    spec = app[app.index("const profileBoardSpec"):app.index("// Keymap target label")]
    for field in ("actuation:", "rtEnabled:", "rtPress:", "rtRelease:", "socd:"):
        assert field in spec, field


def test_every_bridge_method_the_ui_calls_exists():
    ui = _read(SRC, "src", "app.jsx") + _read(SRC, "workspaces", "settings.jsx")
    for name in ("games_status", "games_sync", "apply_profile_to_board", "list_running_games",
                 "set_game_profile", "add_custom_game", "refresh_detectable",
                 "set_games_auto_switch"):
        assert name in ui, name
        assert callable(getattr(app_web.Api, name)), name


def test_settings_has_a_games_widget():
    st = _read(SRC, "workspaces", "settings.jsx")
    assert "function GamesWidget(ctx)" in st
    assert re.search(r'\{ id: "games",\s+title: "Games",.*render: GamesWidget \}', st)
    assert "Auto-switch profiles for games" in st
    assert "data-games-now" in st and "data-games-picker" in st


def test_game_names_are_rendered_as_text_only():
    for rel in (("src", "app.jsx"), ("workspaces", "settings.jsx")):
        text = _read(SRC, *rel)
        assert "dangerouslySetInnerHTML" not in text and "innerHTML" not in text, rel


def test_built_bundle_carries_the_games_ui():
    built = _read(SRC, "build", "ws_settings.js")
    assert "GamesWidget" in built and "set_games_auto_switch" in built
    html = _read(HERE, "ui", "index_runtime.html")
    assert "apply_profile_to_board" in html and "games_status" in html
```

- [ ] **Step 2: Run them to verify they fail**

Run: `<py> -m pytest tests/test_games_ui_sources.py -q -p no:cacheprovider`
Expected: 5 FAIL (`test_game_names_are_rendered_as_text_only` already passes).

- [ ] **Step 3: Edit `ui/runtime_src/src/app.jsx`** — four exact replacements.

(a) Replace

```jsx
// Keymap target label → USB HID usage code (page 0x07). Used by Remap Key.
```

with

```jsx
// SOCD tab rows ({k1, k2, mode} with key LABELS) -> set_socd pairs (design
// codes). Rows missing a key are skipped; [] clears the board's pairs.
const socdPairsFrom = (rows) => (rows || [])
  .filter(p => p && p.k1 && p.k2)
  .map(p => ({ model: p.mode || 1, key1: LABEL_TO_CODE[p.k1] || p.k1, key2: LABEL_TO_CODE[p.k2] || p.k2 }));

// A saved profile's board-side settings for Api.apply_profile_to_board (game
// auto-switch). A field the profile never stored is null, so the board keeps
// what it has instead of receiving a default.
const profileBoardSpec = (st) => {
  const s = st || {};
  const num = (v) => (typeof v === "number" && isFinite(v)) ? v : null;
  return {
    actuation: num(s.actuation),
    rtEnabled: !!s.rtEnabled,
    rtPress: num(s.rtPress) ?? 0.05,
    rtRelease: num(s.rtRelease) ?? 0.05,
    socd: Array.isArray(s.socdProfiles) ? socdPairsFrom(s.socdProfiles) : null,
  };
};

// Keymap target label → USB HID usage code (page 0x07). Used by Remap Key.
```

(b) In `handleSocdApply`, replace

```jsx
  const handleSocdApply = (profiles) => {
    const pairs = (profiles || [])
      .filter(p => p.k1 && p.k2)
      .map(p => ({ model: p.mode || 1, key1: LABEL_TO_CODE[p.k1] || p.k1, key2: LABEL_TO_CODE[p.k2] || p.k2 }));
```

with

```jsx
  const handleSocdApply = (profiles) => {
    const pairs = socdPairsFrom(profiles);
```

(c) Replace the line `  /* ===== HID bridge: effects (push state to the board) ===== */` with (the game block goes after `handleSocdApply`, `switchProfile` and `pushNotice`, which it uses):

```jsx
  // ---- game auto-switch (games.py) ------------------------------------------
  // Python detects games and decides, debounced 5 s, which profile should be
  // active; games_status().switch carries that decision with a sequence
  // number. We poll it (WebView2 timers keep full rate while hidden: see
  // app_web.main), switch the profile exactly like the profile menu (the
  // lighting effects below then re-send), and hand the profile's actuation /
  // RT / SOCD to apply_profile_to_board, which skips anything the board
  // already holds and defers the write while the board is offline.
  // games_sync reports the active profile and the newest switch handled, so
  // Python can tell a manual switch (no revert) from its own.
  const gameSeqRef = useRef(0);
  const activeIdRef = useRef(activeId); activeIdRef.current = activeId;
  const profilesRef = useRef(profiles); profilesRef.current = profiles;
  const switchProfileRef = useRef(null); switchProfileRef.current = switchProfile;
  const [actReadNonce, setActReadNonce] = useState(0);   // bump = re-read actuation
  const profileListKey = JSON.stringify(profiles.map(p => [p.id, p.name || ""]));
  const gameSync = (active, seq) => apiCall("games_sync", {
    activeProfile: active, handledSeq: seq,
    profiles: profilesRef.current.map(p => ({ id: p.id, name: p.name || "" })),
  });
  useEffect(() => {
    if (hydrated) gameSync(activeId, gameSeqRef.current);
  }, [hydrated, activeId, profileListKey]);
  useEffect(() => {
    if (!hydrated) return;
    let alive = true, busy = false;
    const applyGameSwitch = async (sw) => {
      const p = profilesRef.current.find(x => x.id === sw.profileId);
      if (p && p.id !== activeIdRef.current && switchProfileRef.current)
        switchProfileRef.current(p.id);
      await gameSync(p ? p.id : activeIdRef.current, sw.seq);
      if (!p) return;
      const r = await apiCall("apply_profile_to_board", profileBoardSpec(p.state));
      if (r && r.ok && r.actuation === "written") setActReadNonce(n => n + 1);
      else if (r && r.ok === false && !r.unsupported)
        pushNotice(`Game profile not applied to the keyboard: ${r.error || "no reply"}`);
    };
    const tick = async () => {
      if (!alive || busy) return;
      busy = true;
      try {
        const s = await apiCall("games_status");
        const sw = s && s.ok ? s.switch : null;
        if (alive && sw && sw.seq > gameSeqRef.current) {
          gameSeqRef.current = sw.seq;
          await applyGameSwitch(sw);
        }
      } catch {}
      busy = false;
    };
    tick();
    const id = setInterval(tick, 2000);
    return () => { alive = false; clearInterval(id); };
  }, [hydrated]);

  /* ===== HID bridge: effects (push state to the board) ===== */
```

(d) Replace

```jsx
  useEffect(() => { if (connected) refreshPerKeyActuation(); }, [connected]);
```

with

```jsx
  // A game profile that rewrote actuation re-reads it too (actReadNonce).
  useEffect(() => { if (connected) refreshPerKeyActuation(); }, [connected, actReadNonce]);
```

- [ ] **Step 4: Edit `ui/runtime_src/workspaces/settings.jsx`** — insert this block directly above `/* ===== Backup/Import widget ===== */` (it uses the `Toggle` component defined above `SystemWidget`):

```jsx
/* ===== Games widget =====
   Discord-style game detection (games.py). Every 3 s Aether checks which
   programs run, matches them against Discord's public game list (downloaded,
   cached, refreshed weekly) and the programs you added, and switches to the
   mapped profile while a game runs (back again when it closes). Bridge:
   games_status / list_running_games / set_game_profile / add_custom_game /
   refresh_detectable / set_games_auto_switch. Game and program names come
   from outside Aether: they are rendered as plain text only. */
const agoText = (epochS) => {
  if (!epochS) return "never";
  const d = Math.max(0, Date.now() / 1000 - epochS);
  if (d < 3600) return "just now";
  if (d < 86400) return `${Math.round(d / 3600)} h ago`;
  return `${Math.round(d / 86400)} days ago`;
};

function GamesWidget(ctx) {
  const { profiles = [], activeId } = ctx;
  const [st, setSt] = useState(null);
  const [err, setErr] = useState("");
  const [picker, setPicker] = useState(null);     // null = closed, [] = programs
  const [busy, setBusy] = useState("");
  const alive = useRef(true);

  const refresh = () => {
    const api = window.pywebview?.api;
    if (!api || !api.games_status) return;
    api.games_status().then(r => {
      if (!alive.current) return;
      if (r && r.ok) setSt(r); else setErr((r && r.error) || "failed");
    }).catch(() => {});
  };
  useEffect(() => {
    alive.current = true;
    refresh();
    const id = setInterval(refresh, 3000);
    return () => { alive.current = false; clearInterval(id); };
  }, []);

  const call = async (fn, ...args) => {
    setErr("");
    const api = window.pywebview?.api;
    if (!api || !api[fn]) return null;
    try {
      const r = await api[fn](...args);
      if (!(r && r.ok)) setErr((r && r.error) || "failed");
      refresh();
      return r;
    } catch (e) { setErr(String(e)); return null; }
  };
  const openPicker = async () => {
    setBusy("scan");
    const r = await call("list_running_games");
    setBusy("");
    setPicker(r && r.ok ? (r.programs || []) : null);
  };
  const pick = async (prog) => {
    let id = prog.gameId;
    if (!id) {
      const r = await call("add_custom_game", prog.exe, prog.name);
      if (!(r && r.ok)) return;
      id = r.id;
    }
    await call("set_game_profile", id, activeId || (profiles[0] && profiles[0].id) || null);
    setPicker(null);
  };
  const refreshList = async () => {
    setBusy("list");
    await call("refresh_detectable");
    setBusy("");
  };
  const profName = (id) => (profiles.find(p => p.id === id) || {}).name || "missing profile";

  const head = (
    <div className="font-display text-[11px] uppercase tracking-[0.18em] text-[var(--text-dim)] mb-3">
      Games
    </div>
  );
  if (!st) return <div>{head}<div className="font-mono text-[10.5px] text-[var(--text-faint)]">Loading…</div></div>;
  if (!st.available) {
    return (
      <div>
        {head}
        <div className="font-mono text-[10.5px] text-[var(--text-faint)] leading-relaxed">
          Game detection (switch profiles when a game starts) is available on Windows.
        </div>
      </div>
    );
  }
  const detected = st.detected || [];
  const now = detected.find(d => d.id === st.foreground) || detected[0] || null;
  const games = st.games || [];
  const dl = st.detectable || {};
  const btn = "px-2.5 h-8 rounded-md border border-[var(--line)] bg-white/[0.02] text-[var(--text-dim)] font-display text-[10.5px] uppercase tracking-[0.16em] hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)] disabled:opacity-50";
  return (
    <div>
      {head}
      <Toggle on={!!st.autoSwitch} onClick={() => call("set_games_auto_switch", !st.autoSwitch)}
              label="Auto-switch profiles for games"
              desc="When a mapped game starts or comes to the front, switch to its profile and apply it to the keyboard (actuation and rapid trigger on all keys, SOCD, lighting). Switches back when the game closes." />

      <div className="mt-3 flex items-center gap-2 font-mono text-[10.5px] text-[var(--text-dim)]" data-games-now>
        <span className={`w-2 h-2 rounded-full shrink-0 ${now ? "bg-[var(--accent)] shadow-[0_0_8px_var(--accent-glow)]" : "bg-[var(--text-faint)]"}`}/>
        <span className="truncate">{now ? `Now playing: ${now.name}` : "No game detected"}</span>
        {st.active && <span className="text-[var(--accent)] truncate">{`→ ${profName(st.active.profileId)}`}</span>}
      </div>

      <div className="mt-3 flex flex-col gap-1.5">
        {games.length === 0 && (
          <div className="font-mono text-[10px] text-[var(--text-faint)] leading-relaxed">
            No games mapped yet. Start a game, then add it from the running programs.
          </div>
        )}
        {games.map(g => (
          <div key={g.id} className="flex items-center gap-2 rounded-lg border border-[var(--line)] bg-white/[0.02] px-2.5 py-1.5">
            <span className="flex-1 min-w-0 truncate font-display text-[12px] text-[var(--text)]" title={g.name}>{g.name}</span>
            <select value={g.profileId || ""} aria-label={`Profile for ${g.name}`}
                    onChange={e => e.target.value && call("set_game_profile", g.id, e.target.value)}
                    className="h-7 max-w-[140px] rounded-md border border-[var(--line)] bg-[rgba(5,11,14,0.5)] px-1.5 text-[11px] text-[var(--text)] font-display outline-none">
              {!g.profileId && <option value="">Choose profile</option>}
              {profiles.map(p => <option key={p.id} value={p.id}>{p.name || "Untitled"}</option>)}
            </select>
            <button onClick={() => call("set_game_profile", g.id, null)} title="Remove"
                    className="w-6 h-6 rounded-md border border-[var(--line)] bg-white/[0.02] text-[var(--text-dim)] hover:border-rose-400/40 hover:text-rose-300 flex items-center justify-center text-[10px]">
              ✕
            </button>
          </div>
        ))}
      </div>

      <div className="mt-3 flex gap-2">
        <button onClick={openPicker} disabled={busy === "scan"} className={btn}>
          {busy === "scan" ? "Scanning…" : "Add running program"}
        </button>
        {picker && <button onClick={() => setPicker(null)} className={btn}>Cancel</button>}
      </div>
      {picker && (
        <div className="mt-2 max-h-[180px] overflow-auto flex flex-col gap-1 rounded-lg border border-[var(--line)] p-1.5" data-games-picker>
          {picker.length === 0 && <div className="font-mono text-[10px] text-[var(--text-faint)] p-1">No programs found.</div>}
          {picker.slice(0, 60).map(p => (
            <button key={p.exe} onClick={() => pick(p)}
                    className="text-left rounded-md px-2 py-1 hover:bg-[var(--accent)]/10 border border-transparent hover:border-[var(--accent)]/30">
              <div className="font-display text-[11.5px] text-[var(--text)] truncate">
                {p.name}{p.gameId && <span className="ml-2 text-[9.5px] text-[var(--accent)] uppercase tracking-[0.14em]">game</span>}
              </div>
              <div className="font-mono text-[9.5px] text-[var(--text-faint)] truncate">{p.exe}</div>
            </button>
          ))}
        </div>
      )}

      <div className="mt-3 flex items-center justify-between gap-2 font-mono text-[10px] text-[var(--text-faint)]">
        <span className="truncate">{`Discord game list: ${(dl.count || 0).toLocaleString()} games · updated ${agoText(dl.fetched)}`}</span>
        <button onClick={refreshList} disabled={busy === "list"} className={btn}>
          {busy === "list" ? "Updating…" : "Update"}
        </button>
      </div>
      {dl.error && <div className="mt-1 font-mono text-[10px] text-rose-300/90">{dl.error}</div>}
      {err && <div className="mt-2 font-mono text-[10px] text-rose-300/90">{err}</div>}
      <div className="mt-3 font-mono text-[10px] text-[var(--text-faint)] leading-relaxed">
        Program names are checked on this PC only and never stored or sent. The game list is downloaded from Discord; nothing is uploaded.
      </div>
    </div>
  );
}
```

and add to `SETTINGS_WIDGETS`, directly after the `stats` entry:

```jsx
  { id: "games",    title: "Games",         default: { x: 800, y: 632, w: 360, h: 460 }, min: { w: 320, h: 300 }, render: GamesWidget },
```

- [ ] **Step 5: Build and keep only real diffs**

Run: `<py> ui\runtime_src\build_runtime.py`
Expected: ends with `Wrote ...index_runtime.html  (NNNN KB)`, no Babel error.
Run: `git diff --ignore-cr-at-eol --stat` — expected files: the two `.jsx`, `ui/index_runtime.html`, `ui/runtime_src/build/app.js`, `ui/runtime_src/build/ws_settings.js`. Run plain `git diff --stat`; every other `ui/runtime_src/build/*.js` listed there is a line-ending-only change: `git checkout -- <file>`.

- [ ] **Step 6: Run the tests**

Run: `<py> -m pytest tests/test_games_ui_sources.py tests/test_ui_sources.py tests/test_tray.py tests/test_pressure_ui_sources.py -q -p no:cacheprovider`
Expected: all pass (`6` new). `git grep -n "dangerouslySetInnerHTML\|innerHTML" -- ui/runtime_src/src/app.jsx ui/runtime_src/workspaces/settings.jsx` prints nothing.

- [ ] **Step 7: Commit**

```bash
git add ui/runtime_src/src/app.jsx ui/runtime_src/workspaces/settings.jsx ui/index_runtime.html ui/runtime_src/build/app.js ui/runtime_src/build/ws_settings.js tests/test_games_ui_sources.py
git commit -m "feat(ui): apply game profile switches and add the Settings Games widget" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: Docs, full suite, status

**Files:**
- Modify: `CLAUDE.md`, `docs/superpowers/roadmap-status.md`

- [ ] **Step 1: CLAUDE.md** — in "## Architecture" add a bullet after the `tray.py` bullet:

```markdown
- `games.py` — game detection (Windows; ctypes Toolhelp32, no dependency): Discord's public detectable list
  (HTTPS, 5 MB wire cap, cached `<user_data_dir>/games/detectable.json`, weekly) + user-added programs, matched by
  trailing path segments; `GameSwitcher` debounces 5 s and reverts on exit; `GameService` owns settings.json `games`
  and the 3 s poll thread (`main()` starts/stops it via `Api._start_games/_stop_games`; private `Api._games`). Python
  decides, `app.jsx` polls `games_status()` and switches the profile, then `Api.apply_profile_to_board` writes
  actuation/RT to all keys + SOCD (skipped when `_act_mm`/`_trig_mode`/`_socd_last` show the board already has it;
  deferred to the next connect while offline). Only candidate processes are opened; nothing about other processes
  is kept or sent. Tray tooltip names the detected game.
```

- [ ] **Step 2: Full suite**

Run: `<py> -m pytest -q -p no:cacheprovider`
Expected: `916 passed, 13 skipped` (808 + 18 + 12 + 7 + 16 + 15 + 8 + 21 + 5 + 6; the new skip is the non-Windows enumeration test), zero failures/errors.

- [ ] **Step 3: Commit docs**

```bash
git add CLAUDE.md
git commit -m "docs: record game detection in the architecture notes" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 4: Status entry** — append to `docs/superpowers/roadmap-status.md`, ABOVE `## Waiting on the user`, a dated implementer entry in the file's format (≤ 15 lines): commits landed; decisions later phases must respect (`Api._games` is private; `games_status()` shape incl. `active` for Phase 5's dashboard tile; `apply_profile_to_board` + `_trig_mode` is the reusable "apply a profile's board settings" path; `_SETTINGS_LOCK`); gotchas; the hardware checks below pointing at this plan. Add inside `## Waiting on the user`: `- [Phase 3] Run the 12 hardware checks at the end of docs/superpowers/plans/2026-11-04-phase-3-games.md (switch/revert, debounce, offline apply, tooltip, anti-cheat/CPU).` Commit it alone:

```bash
git add docs/superpowers/roadmap-status.md
git commit -m "docs(status): phase 3 game detection done" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Hardware checks (for the orchestrator → `docs/HARDWARE_TEST_CHECKLIST.md` under `## Roadmap 2026-11-04`)

1. Settings → Games is visible (scroll the Settings canvas if needed). Click "Update": the Discord game list count becomes several thousand and "updated just now". If it reports "larger than 5 MB", note the size (see the Waiting item on the cap).
2. Start any game: within about 3–6 s "Now playing: <game>" appears and hovering the tray icon shows "Aether HE — <game>". Quit it: both clear.
3. "Add running program" while an unlisted game runs: it appears in the list (folder/name.exe); pick it, map it to a second profile that differs in lighting, actuation (e.g. 0.50 mm vs your 0.80 mm) and one SOCD pair. Auto-switch ON.
4. Launch that game: about 6 s later the profile menu shows the game profile, the lighting changes, Actuation tab read-back shows 0.50 mm on every key, and the SOCD pair works in game.
5. Quit the game: about 6 s later the previous profile is back, lighting back, read-back 0.80 mm on every key.
6. Alt-tab between the game and the desktop every 1–2 s for 30 s: no profile flicker and no extra writes (the log shows no new `trigger pkt` lines during the alt-tabbing).
7. Map a game to a profile whose actuation equals what the board already has (0.80 → 0.80): on switch the log shows NO `trigger pkt` line (skip-if-unchanged).
8. While a mapped game runs, switch profile by hand: Aether keeps your choice; after quitting the game it does NOT revert.
9. Unplug the keyboard, launch the mapped game, wait 10 s (profile switches in the UI), plug it back in: after reconnect the read-back shows the game profile's actuation and the lighting follows.
10. Two mapped games running (different profiles): the one in front wins after about 6 s; switching to a browser keeps the last game's profile.
11. Start Aether minimised to the tray (sign-in autostart) and launch a mapped game: the switch still happens with the window hidden.
12. Idle CPU with detection on stays negligible (Task Manager, AetherHE < 1 %); games with anti-cheat (e.g. EAC/Vanguard titles) start and run normally while Aether runs (Aether only queries image names with limited rights). Offline first run (network off, no cache): the app works, list count 0, user-added games still switch.
