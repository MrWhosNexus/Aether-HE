---
name: aula-win60-v0.5.0-tray-macros-review
description: v0.5.0 engineering record — codebase review fixes, Win60 macros, tray/mini mode, Windows launch fixes, and what still needs a real board
metadata:
  node_type: memory
  type: reference
  release: v0.5.0
  commits: 09dc94a..eec898c (10 commits on main, tagged v0.5.0)
---

# v0.5.0 — what changed and why (2026-09-24 → 2026-09-27)

Ten commits, `2179fd7..eec898c`, 46 files, test suite 502 → 640 passing. Every
claim below was verified by tests, by reading the vendor driver
(`driver_src/dec_agreement/deobfuscated.js`) and the USB captures under
[[aula-win60-protocol-capture]], or by the Playwright+Xvfb sandbox harness that
runs the real `Api` + `TrayController` against the built UI. **Nothing in this
release ran on a physical board before tagging** — see the hardware section.

## Commit map (each is green on its own from `a588261` onward)

| Commit | Scope | Self-contained tests |
|---|---|---|
| `09dc94a` | effects.py / device_state.py perf + restart race | 2 fail (needs `a588261`'s app_web half) |
| `ab5ef69` | UI call ordering, gamepad idle-skip, HID pick, updater | 2 fail (same) |
| `a588261` | actuation read-back, switch RMW, clamping, reader glue | green |
| `a45af89` | Win60 macros; remap RMW; fixed-mode intervals; send_raw guard | green |
| `9bc6a28` `9bd51b4` `06be1e8` | tray residency, mini panel, Hide/Start-minimized | green |
| `107a823` `be83adb` | single instance + own WebView2 profile | green |
| `eec898c` | pre-release review fixes, version 0.5.0 | green |

The first two commits fail two tests each only because their `app_web.py`
half was committed in `a588261` (three agents edited concurrently and the
shared file was committed once). History was NOT rewritten: `main` and the
`v0.5.0` tag point at `eec898c`, which is consistent.

## Protocol facts established (Win60 HE)

- **Per-key trigger config read (cmd 33 sub 5 reply)**: `mode=body[6]`,
  `travel=body[11]<<8|body[7]`, `i1=body[13]<<8|body[9]`, `i2=body[14]<<8|body[10]`
  (vendor L966-969; capture frame 173 `21 00 00 00 0c 05 00 aa aa 01 01 …` = 1.70 mm).
  The old `parse_trigger_read` decoded the *live-stream* layout and filtered on
  `r[5]==5`, the payload LENGTH byte — it read 1.70 mm back as 4.26 mm.
  → `protocol.build_read_trigger_config` / `parse_trigger_config`,
  `Win60Driver.read_trigger_config` (matches replies by echoed row/col).
- **Fixed mode (0) keeps RT intervals.** Vendor `setAnyTriggerValue` always
  copies stored `interval1/2` (L1532-1538); capture 1842/1849 show mode 0 with
  the previous RT pair `78 78`. Factory pair is 1/1. Aether now RMWs per key
  and falls back to 1/1 when a key doesn't answer (`TRIGGER_READ_MAX_MISSES=3`).
- **Switch profile table (cmd 37/0x25)**: the vendor writes each key's own
  stored value (frames 1578-1581: 2 on the 61 keys, 0 on empty slots). Aether's
  old `build_switch_table` filled HM1 everywhere → selecting WASD=TC1 reset the
  rest. Now read (`25 02`, 58+58+16) → modify → write.
- **Base-layer keymap (cmd 24)** is RMW (`protocol.compose_base_keymap`: zero
  read-back = firmware default, non-zero kept verbatim). The Fn layer must be
  written after base pages or the board is left in Fn mode; if the Fn table
  can't be read/snapshotted the write ABORTS before any byte goes out.
- **Macros (cmd 25)**: see the cheat-sheet line in `CLAUDE.md`. Key finding:
  header byte 1 is the vendor `macroType` (play mode), NOT the slot number —
  the captures only looked that way because slot 0 was "once" and slot 1
  "repeat". Events carry the delay AFTER the event; Aether tuples are
  `(delay_before, hid, is_down)` and `protocol.py` shifts at the wire.
- **Dangerous raw commands** (`protocol.dangerous_command_reason`): cmd 20
  `[1]=0,[5]=1` factory reset (L1477), cmd 33 sub 6 trigger reset, cmd 33 sub
  8/15 with `[6]=0` calibration arm. No firmware-flash HID command exists in the
  web driver.

## Reader parking (lifecycle fix B.2, finally implemented)

`LiveReader._run` drains up to 256 reports and discards every non-travel frame.
Any RMW that needs a read-back (remap, switch table, mode-0 actuation,
verify_actuation, deadband, macros) therefore lost its reply whenever Travel
Test / a press-reactive effect / gamepad capture was on. `Api._reader_paused()`
(context manager, outer RLock) stops the reader, runs the op, and
`_restore_shared_reader()` brings it back for the registered owners. Lock order
stays outer→inner. See [[lifecycle-locking-design]].

## Effects engine

- `time.monotonic` for pacing/animation; per-run stop Events (a wedged old
  thread can never be revived by `start()`); `_g_reactive` is dt-based; static
  frame cached; `_MAX_PARTICLES=96` hard cap on every particle list;
  `LiveReader.snapshot_by_index()` removes the per-frame code→index remap.
  Measured: reactive ~300→~40 µs/frame, static ~388→~18 µs/frame.
- `_ensure_reactive` resolves the reader lazily — it used to capture
  `self.reader` at effect start, so opening the Actuation tab (which replaces
  the reader) made ripple/cross/fireworks go deaf.
- FPS stays 60 (`effects.FPS`); the 120 experiment noted in older notes was
  reverted long ago.

## Tray / mini mode (Windows)

`tray.py` + `ui/tray_panel.html`, documented in `CLAUDE.md` and README. Design
rule: the panel never drives the board; it sets `pattern`/`speed` in the React
app via `window.__aetherTraySet` and reads `Api.tray_sync` state. Hidden
WebView2 pages throttle timers to 1 Hz, so `main()` appends
`--disable-background-timer-throttling` via `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS`
(appended by the WebView2 runtime; ignored for elevated hosts). pystray's
detached thread is non-daemon → `tray_ctl.exit()` runs in `main()`'s `finally`.
Sandbox-verified: close→hide, panel effect/speed → React → `start_multicolor`,
settings persisted, Open/Hide/Exit, 90 s idle at 59.3 fps with flat RSS.

## Windows launch

- `0x8007139F` on WebView2 init = user-data folder held by another WebView2
  process with different options. pywebview's default is the shared
  `%LOCALAPPDATA%\pywebview`; Aether now passes
  `storage_path=%LOCALAPPDATA%\AetherHE\webview`. localStorage-only flags
  (setup-done, zoom, auto-connect) reset once.
- `single_instance.py`: `Local\AetherHE.Instance` mutex + `Local\AetherHE.Show`
  auto-reset event; second launch pokes the first and exits. HANDLE types are
  pinned pointer-sized; the listener exits on `WAIT_FAILED`.
- The autostart Run entry no longer bakes in `--minimized`; the Settings toggle
  (`settings.json.startMinimized`) decides, so flipping it needs no registry write.

## Still unverified on hardware (run `docs/HARDWARE_TEST_CHECKLIST.md`)

Actuation read-back, switch-table preservation, remap preserving vendor
bindings, fixed-mode interval preservation, macros (record/bind/repeat;
Toggle/Hold play modes are source-only), WebView2 hidden-window behaviour, tray
docking, single-instance poke, panel placement.

## Known gaps / not done

- macOS: nothing; tray is Windows-only (`tray.backend_supported`).
- MINI 60 HE PRO advanced-keys editor still never writes (`WRITE_PATH_EXISTS`
  but the widget collects table indices, the Api wants design codes).
- `write_keymap` re-reads the Fn layer even when a connect snapshot exists
  (≤1.5 s extra on a silent board).
- Mode-0 fallback writes 1/1 for keys that don't answer the config read.
