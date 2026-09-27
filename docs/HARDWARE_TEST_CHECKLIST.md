# HARDWARE_TEST_CHECKLIST.md

One entry per change that touches the board and was not verified on a physical
keyboard before merge. Tick an entry only after running it on the real board;
add the board, OS, app version and date next to the tick. Referenced by
`docs/DEFINITION_OF_DONE.md` and `agents/PLAN.md` (POLISH-004).

Legend: `[ ]` untested · `[x] Win60 HE / Windows / v0.5.0 / 2026-09-27` when done.

## v0.5.0 (commits `09dc94a..eec898c`)

### Actuation
- [ ] **Actuation read-back** (`a588261`, `Win60Driver.read_actuation`): Actuation tab → select one key → Apply 1.70 mm → reconnect. The per-key badge must read **1.70** (before the fix it was blank or 4.26).
- [ ] **Fixed mode keeps RT intervals** (`a45af89`, `_set_fixed_preserving_intervals`): set RT 1.20/1.20 on all keys, then switch to fixed 1.70 mm. `verify_actuation` (or the vendor page) must still show sensitivities 1.20/1.20 — not 0/0 and not 1/1. If some keys show 1/1 the config read timed out for them (`TRIGGER_READ_MAX_MISSES`).
- [ ] **All-keys write covers slots 64–131** (`a588261`, `set_trigger_all`): Apply with no selection; every key including the bottom row must change.
- [ ] **RMW with a live reader on** (`eec898c`, `_reader_paused`): turn Travel Test ON, then apply fixed-mode actuation, a remap, and a switch change. All three must succeed (previously "keymap read failed" / silent 1/1 fallback) and Travel Test must still animate afterwards.

### Switch profile
- [ ] **Unselected keys keep their profile** (`a588261`, `set_switch` RMW): WASD → TC1, then Space → HH1, then read back (vendor page or `read_switch_table`). WASD must still be TC1.

### Keymap / remap
- [ ] **Vendor bindings survive a remap** (`a45af89`, `_rmw_base_layer`): bind a macro to M in the vendor page; in Aether remap Z → B; re-read in the vendor page — M's macro binding must still exist, Fn+key combos must still work.
- [ ] **Abort-before-write**: unplug during Apply. No base-layer pages may go out without the Fn write following (sniff cmd 24; or simply confirm the board is not stuck in Fn mode afterwards).

### Macros (`a45af89`)
- [ ] Macros tab → Read board → 10 slots listed.
- [ ] Record `abc` into M3, Save; Read board shows 6 events, Once.
- [ ] Bind M → press M types `abc`; existing remaps and Fn layer unaffected.
- [ ] Repeat ×3 → press M types `abcabcabc`.
- [ ] Bind N to M3 too; unbind M → M types `m`, N still fires; erase M3 → N restored. (The vendor duplicates the slot for a second key; direct multi-bind is unverified.)
- [ ] Toggle / Hold play modes (source-only; expect them to work, report if not).

### Lighting / effects
- [ ] **Reactive effects survive the Actuation tab** (`09dc94a`, `_ensure_reactive`): start Ripple, open Actuation, press keys — ripples must still appear.
- [ ] **Effect restart has no ghost stream** (`09dc94a`): switch effects rapidly 10×; the board must show only the last effect, no interleaved frames.
- [ ] **Brightness/speed clamp** (`a45af89`): console `set_light(0,255,255,255,brightness=9,speed=9)` → LEDs at full (bytes 6-7 = `04 04`), not off.
- [ ] **Stop → static ordering** (`ab5ef69`, `callSeq`): from a running host effect pick Static; the board must land on the static colour, not stale per-key pixels.

### Raw write guard (`a45af89`)
- [ ] `send_raw("01 14 00 00 00 01 01")` → `{"ok": false, "error": "refusing …"}`, board settings unchanged; `send_raw("01 21 00 00 00 18 03")` → ok.

### Windows: tray, launch, updater (`9bc6a28`, `06be1e8`, `107a823`, `eec898c`)
- [ ] Close window with X → tray icon appears, effect keeps animating.
- [ ] Left-click icon → mini panel opens near the cursor; change effect + drag speed → board follows within ~1 s (if it lags ≈1 s the `--disable-background-timer-throttling` flag is not reaching WebView2 — check for an elevated launch).
- [ ] Open Aether HE → window returns with Lighting tab matching the panel choice.
- [ ] Right-click → Hide window greys out while hidden; Exit ends the process (no `AetherHE.exe`/`python.exe` left in Task Manager, icon gone).
- [ ] Settings → System → Start minimized ON → Exit → relaunch: no window, icon present, effect running. Start on launch ON → sign out/in → same.
- [ ] Launch Aether twice → second launch brings the first window up, no `0x8007139F` error.
- [ ] Explorer restart (`taskkill /f /im explorer.exe && start explorer`) → icon re-appears (pystray TaskbarCreated).
- [ ] Settings → Updates → Check for updates on a 0.4.6 install → offers v0.5.0; install runs Setup and relaunches.
- [ ] `tools/list_hid.py` shows the Win60 with usage page `0xFF1B`; Pair opens the vendor collection (lighting works), not the keyboard HID.

### Gamepad (`ab5ef69`)
- [ ] Gamepad capture ON with no ViGEmBus → clear error + Install button; after install, capture works and CPU stays low when no mapped key moves.
