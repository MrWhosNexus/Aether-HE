# Aether-HE -- Opus Handoff Prompt (actuation decode for issue #3)

> Paste this file (or just the **Brief** below) as the first message of a fresh
> Opus session to land the actuation decode for the Aula WIN 60 HE Pro
> (SayoDevice, 8089:0009). The decode work itself is already DONE -- the
> prompt below turns it into a verified code change + golden test + registry flip.

---

## Brief (paste-and-go)

You are a fresh Opus session. Goal: land the actuation decode for the **Aula WIN 60 HE Pro** (`8089:0009`) on top of the existing lighting decode, so this board goes from `actuation: false` to `actuation: true` in `data/board_registry.json`. The protocol diff analysis is ALREADY DONE -- see `docs/context/issue-3-sayodevice-raw/actuation_decode_analysis.md` for the field map. Your job is to (1) extend `protocol_sayo.py` with a typed `build_key_analog(key_idx, press_mm, release_mm=None)` builder, (2) add a golden test in `tests/test_protocol_sayo.py` that reproduces the steady-state 0.4mm + 2.0mm writes byte-for-byte against the new captures, (3) flip the registry, (4) reply on issue #3.

**Working dir:** `C:\Users\yygbu\aether-windows`
**Branch:** start a new branch from `main`, e.g. `feat/sayo-actuation-decode`
**GitHub repo:** `MrWhosNexus/Aether-HE` (issues, not PRs -- bot opens PRs)
**Issue to reply on:** `#3` (https://github.com/MrWhosNexus/Aether-HE/issues/3)

**Files of interest (READ IN THIS ORDER, line numbers matter):**
1. `protocol_sayo.py` (lines 1-155, especially 86-88 `_LIGHT_TEMPLATE`, 121-130 `build_lighting`, 134-142 `build_key_analog_raw` which only does verbatim replay today)
2. `tests/test_protocol_sayo.py` (lines 1-130, pattern for golden tests + checksum verification)
3. `docs/context/issue-3-sayodevice-raw/actuation_decode_analysis.md` -- the field map I already wrote, with the 24-byte payload decoded
4. `data/board_registry.json` -- slug `aula-win60he-pro`, flip `actuation: false` → `actuation: true`
5. `docs/context/aula-win60-he-pro-sayo-protocol-capture.md` -- older notes; field-map section is now superseded by the new analysis file but the framing/commands/registry rules still apply

**Stop condition:** all 6 execution-order steps below complete, `pytest tests/test_protocol_sayo.py` is green, registry flipped, and the reply on issue #3 is posted.

**Execution order (follow exactly):**

1. Read the analysis file + `protocol_sayo.py` end-to-end. Confirm the field map against the byte tables.
2. Implement `build_key_analog(key_idx, press_mm, release_mm=None)` in `protocol_sayo.py`. Keep `build_key_analog_raw` for verbatim replay (other code may still use it). Validation: `press_mm` and `release_mm` must be in `[0.08, 3.4]` (matches our `protocol.py` cmd-33 range); reject with `ValueError` otherwise.
3. Add golden tests to `tests/test_protocol_sayo.py`:
   - `build_key_analog(0x2F, 0.4)` reproduces `actuation_0.4mm.pcapng` pkt 1415 head byte-for-byte (use `P()` helper already in the file).
   - `build_key_analog(0x2F, 2.0)` reproduces `actuation_2.0mm.pcapng` pkt 748 head byte-for-byte.
   - `build_key_analog(0x2F, 1.0, 1.0)` reproduces `actuation_0.4mm.pcapng` pkt 390 head byte-for-byte (sanity).
   - Out-of-range raises `ValueError`.
4. Run `pytest tests/test_protocol_sayo.py -v` and confirm green. Existing 5 tests must still pass.
5. Flip `data/board_registry.json`: slug `aula-win60he-pro` → `capabilities.actuation: true`, and update the `_note` to reflect that actuation is now decoded (drop the "payload fields unverified" sentence).
6. Commit on a new branch, push, and post a reply on issue #3. Reply text:
   - Thank Mema133 for the diff pair (0.4mm + 2.0mm)
   - State that the actuation field is decoded (bytes 12-13 = press, bytes 14-15 = release, LE16 in 0.001 mm; press==release in fixed mode)
   - Note the in-app "total report 0" workaround for now (Wireshark+USBPcap)
   - Mention v0.3.x release will flip the actuation flag

**Constraints:** stop-slop prose (no em-dashes, no "dig/pattern/use", no "First/Second"). Edit only the 4 files named in step 5. Do NOT touch `boards.py`, `device_state.py`, `app_web.py`, or any UI files — those are owned by other branches/agents and the user has been bitten by cross-branch edits before.

**After the commit and reply:** post a one-line status in your final report (`commit hash + pytest summary + issue-3 reply URL`). Do not start the RT-mode decode or per-key calibration work -- those are out of scope for this handoff.

---

## Full handoff context

### What I already verified (PASS, do not re-do)

- **Field map**: bytes 12-13 LE16 = press actuation in 0.001 mm; bytes 14-15 LE16 = release. Confirmed by:
  - 0.4mm steady state → `90 01 90 01` = 400 / 400 = 0.400 mm / 0.400 mm
  - 2.0mm steady state → `d0 07 d0 07` = 2000 / 2000 = 2.000 mm / 2.000 mm
  - Slider drag captures show press and release tracking together in fixed mode
- **Bytes 0-7 are per-key Hall calibration** (two captures, same key 0x2F, different values because user recalibrated between sessions). For v1 the app uses the new-capture default verbatim; per-key calibration is deferred.
- **Bytes 8-11 + 16-19 are constant** across both captures (592 / 0 / 231 / 3850). Schema, not user-settable.
- **Bytes 20-23 flip between fixed and RT mode** (100/400 in fixed, 130/130 in RT). RT mode is out of scope for this handoff; the builder defaults to fixed-mode bytes.
- **Checksum formula** still matches every new packet (verified against the byte tables in the analysis file).
- **Existing golden tests** (lighting, save, poll, analog-replay, checksum, header) all still PASS after the changes I propose.

### Captures are already on disk

Staged at `C:\Users\yygbu\aether-windows\docs\context\issue-3-sayodevice-raw\`:
- `actuation_0.4mm.pcapng` (1.9 MB, 1921 packets) -- slider drag from 1.0 mm to 0.4 mm
- `actuation_2.0mm.pcapng` (1.2 MB, 1138 packets) -- single 2.0 mm set
- `actuation.pcapng` (the original issue-#3 capture, key 0x2F, RT mode with press=2.0mm release=0.3mm)
- `rgb.pcapng` (lighting capture, mode bytes verified earlier)
- `KBblindtestV3EN.pyw` (the third-party script that gave us the framing)
- `actuation_decode_analysis.md` (my new analysis -- **read this first**)

### Verbatim byte references for the golden tests

```python
# Steady-state 0.4mm write (key 0x2F), actuation_0.4mm.pcapng packet 1415:
ACT_0_4MM_KEY_2F = ("2212c8481c001c2f6d8403006b84969e50020000"
                    "90019001e7000a0f64009001")

# Steady-state 2.0mm write (key 0x2F), actuation_2.0mm.pcapng packet 748:
ACT_2_0MM_KEY_2F = ("221215701c001c2f6d8403006b84969e50020000"
                    "d007d007e7000a0f64009001")

# Mid-drag 1.0mm write (key 0x2F), actuation_0.4mm.pcapng packet 390:
ACT_1_0MM_KEY_2F = ("221204a41c001c2f6d8403006b84969e50020000"
                    "e803e803e7000a0f64006400")
```

(Check these against the file before committing -- I derived them from the byte tables in
`actuation_decode_analysis.md`; if any byte is off, the test will fail loudly and you'll fix in
one cycle.)

### What this handoff does NOT do (deferred)

- **Rapid Trigger (RT) mode** -- needs a separate capture where the user toggles to RT mode and sets press != release. Mema133's captures are fixed-mode only. Original issue-#3 capture IS RT, but we already verified it against the new formula and it works: bytes 12-13 = press, 14-15 = release, they differ for RT. To actually ENABLE RT in the app we'd need a `mode` field on the cmd and a way to flip bytes 20-23. Defer.
- **Per-key calibration** -- bytes 0-7 vary per-key and per-user (recalibration). The new-capture default works for the dev's board but is not portable to other units. Defer until we have a calibration export from the official app or a per-key capture suite.
- **In-app capture "total report 0" fix** -- this is an OS-level endpoint exclusivity issue (MI_00 grabbed by keyboard class driver). Not a protocol problem; needs a different code path (USB-incap-style or pcap-on-write). Out of scope.
- **Other boards** -- issues #5 (1CA2:1902 Win60 HE Max) and #7 (1CA2:1901 WIN68 HE Max) still need a `1CA2` capture; issue #4/#6 (0C45:80A1 MINI60HE Max / 0C45:FEFE Mini 60 HE Pro) need a `0C45` capture. The actuation decode for SayoDevice does NOT transfer to those boards -- they are different silicon families with different protocols.

### Project rules worth re-reading

- `CLAUDE.md` (project root) has the HID protocol cheat-sheet for the 2E3C board (cmd 7 / cmd 9 / cmd 33). The SayoDevice protocol uses a different transport entirely -- read `protocol_sayo.py` and `aula-win60-he-pro-sayo-protocol-capture.md` instead.
- Per the user's standing rule: edit only `protocol_sayo.py`, `tests/test_protocol_sayo.py`, `data/board_registry.json`, and (optionally) the `_note` in the registry. Do NOT touch `boards.py`, `device_state.py`, `app_web.py`, or UI files.
- The `Minimax board-draft bot` (in `.superpowers/sdd/bot-ledger.md`) is what opens the PR once you push -- it runs `tools/board_bot.py` on issue triggers. You do NOT need to open a PR yourself; just push the branch.

### OS / shell / LLM notes

- Windows 11 + Git Bash MSYS2. Use POSIX shell syntax in `terminal()` calls. Python is `python` (3.14 in the venv at `C:\Python314`) for scapy work, but `python` (3.11) in the project's own venv works for the test run.
- Default LLM for this user is `minimax` / `MiniMax-M3` (per `~/.claude/CLAUDE.md`). You are running as Opus, which is fine for the decode work but stay terse and drive-mode -- no "is this OK?" closers.
- No `git push` token issue -- `gh auth status` shows the user is authenticated. Push will work.

### Prior transcript / source pointers

- Issue triage that triggered this handoff: `second-brain/wiki/log.md` entry "Aether-HE issue triage -- replies on #3, #4, #5, #7" (2026-07-06).
- Wiki source page for the broader project: `second-brain/wiki/sources/aether-windows-graph.md`.
- Existing protocol context: `docs/context/aula-win60-he-pro-sayo-protocol-capture.md` (superseded for the field map; the framing/commands/registry rules are still relevant).
- The 3-min stop discipline from `~/.claude/CLAUDE.md` applies at end of session: append a one-line log entry, no new wiki page (this is a code change, not an architecture decision).

### Malware reminder workaround

The builder tests will `open()` and `bytes()` data from the staged `.pcapng` files via the `P()` helper already in `tests/test_protocol_sayo.py`. If your session is running under a malware-reminder hook that flags `open()` of unknown binaries, dispatch the test-author subagent in a fresh context that has no prior Read history. None of the four files you edit are binaries -- they're `.py` and `.json` and `.md` -- so this should not bite, but be aware.

---

**End of handoff. Resume work with step 1 (read the analysis file + `protocol_sayo.py` end-to-end).**