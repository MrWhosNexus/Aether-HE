# HARDWARE_TEST_CHECKLIST.md

One entry per change that touches the board and was not verified on a physical
keyboard before merge. Tick an entry only after running it on the real board;
add the board, OS, app version and date next to the tick. Referenced by
`docs/DEFINITION_OF_DONE.md` and `agents/PLAN.md` (POLISH-004).

Legend: `[ ]` untested · `[x] Win60 HE / Windows / v0.5.0 / 2026-09-27` when done.

## v0.5.1 (launch fix)
- [ ] Install 0.5.1 over 0.5.0 via Setup; tick "Launch" on Finish → app opens NOT elevated (Task Manager → Details → Elevated column = No).
- [ ] With Aether running (window or tray), double-click the desktop shortcut → existing window comes up; no second process.
- [ ] Start Aether as administrator on purpose, then from the shortcut → a message box says it is running but unreachable (instead of nothing happening).
- [ ] `%LOCALAPPDATA%\AetherHE\aether.log` exists and starts with "Aether 0.5.1 starting".

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

## Roadmap 2026-11-04

Built overnight on branch claude/win60-roadmap-6c2753; nothing below has been run on hardware.

### Before you start
- [ ] Music is optional. To enable it, install the deps into the build venv before building: `venv-web\Scripts\pip install numpy soundcard`. The overnight installer was built WITHOUT them, so Music shows "unavailable".
- [ ] Run `pip-audit` (skipped overnight because there was no network).

### Do these first
- [ ] Phase 1 checks 1 and 5: with stats on, type normally for 10 minutes (no missed, doubled or laggy keys; AetherHE CPU low), and calibration completes with Travel Test still showing depth.
- [ ] Phase 2 checks 1 and 3: Pressure with no stuck keys, including after ten rapid taps on different keys.
- [ ] Phase 3 checks 4 and 6: a mapped game's profile applies on launch and reverts on quit; alt-tabbing adds no `trigger pkt` lines.
- [ ] Phase 4 check 7: Apply a suggestion; read-back succeeds, only those keys change, and the suggestion disappears.
- [ ] Phase 6 check 1 (untick): with overlays off, the lighting returns exactly to the static colour.
- [ ] Phase 7 check 4: with a click track, the pulse looks locked to the clicks (latency under 60 ms).

### Phase 1: telemetry (key statistics)
- [ ] Stats on (Windows default), connected: type normally for 10 minutes; no missed, doubled or laggy keystrokes; AetherHE CPU in Task Manager stays low (note the figure).
- [ ] After 1-2 minutes, `%LOCALAPPDATA%\AetherHE\stats\<today>.json` exists and holds only per-key counters and a 34-number histogram (no letters, no timestamps).
- [ ] Press W fully 10 times: Settings > Key statistics "Today" grows by about 10 (and about 10 bottom-outs if bottoming out).
- [ ] Press W gently, below 0.80 mm, 5 times: "shallow" grows by about 5 and presses do not.
- [ ] Calibration with stats on: keys turn green as calibrated and calibration completes; afterwards Travel Test still shows depth.
- [ ] Actuation Apply (read-back matches), remap, macros, dead band and switch selection all still work with stats on.
- [ ] Toggle "Collect key statistics" off (Actuation tab closed, no press-reactive effect): the travel stream stops and the day file stops changing. Toggle on: counting resumes.
- [ ] "Clear statistics" (two clicks): the stats folder's day files are gone and Today shows 0.
- [ ] Poll-rate change and an unplug/replug: counting continues after the reconnect.
- [ ] Tray > Exit right after some typing: the day file includes those presses on the next launch.
- [ ] Press-reactive effects and the Actuation tab's Travel Test behave as before; closing the Actuation tab no longer stops the stream (expected while stats are on).

### Phase 2: pressure lighting
- [ ] Lighting > Pressure with a two-colour palette and dark background: resting keys show only the background; pressing a key slowly brightens and shifts colour smoothly with depth (no steps, no flicker).
- [ ] With 0.80 mm actuation: a key pressed to its actuation point shows about the palette midpoint at half strength; bottoming out shows the last palette colour at full strength.
- [ ] Release a key quickly from bottom-out: dark within about a quarter second. No key stays lit after ten rapid taps on different keys, including keys released lightly (stopped mid-travel).
- [ ] Hold a key halfway: it stays at a constant glow (no pulsing or decay).
- [ ] Change a few keys' actuation (Apply, read-back matches) while Pressure runs: those keys' midpoint shifts within about a second.
- [ ] Switch Pressure <-> Ripple/Reactive <-> a non-reactive effect 10 times: the board follows the last choice; typing and Travel Test still work; nothing lingers.
- [ ] Typing feel and CPU: type normally for 5 minutes on Pressure (no missed or doubled keys; CPU similar to Ripple). Also run it in an Effect Zone (select keys, Pressure in Custom): only those keys react.
- [ ] Actuation tab, Travel Test ON: every key shows an accent line at its own actuation height; pressing a key, its fill rises through the line at the instant it types and the line turns white. Travel Test OFF: lines still show. Changing one key's actuation moves only that key's line after Apply/Re-read.
- [ ] Tray panel effect grid shows Pressure; selecting it switches the board's effect.

### Phase 3: game profiles
- [ ] Settings > Games is visible. Click "Update": the Discord game list count becomes several thousand and reads "updated just now". If it reports "larger than 5 MB", note the size (see the Waiting item on the cap).
- [ ] Start any game: within about 3-6 s "Now playing: <game>" appears, and hovering the tray icon shows "Aether HE - <game>". Quit it: both clear.
- [ ] "Add running program" while an unlisted game runs: it appears in the list (folder/name.exe). Map it to a second profile that differs in lighting, actuation (e.g. 0.50 mm vs your 0.80 mm) and one SOCD pair. Auto-switch ON.
- [ ] Launch that game: about 6 s later the profile menu shows the game profile, lighting changes, Actuation read-back shows 0.50 mm on every key, and the SOCD pair works in game.
- [ ] Quit the game: about 6 s later the previous profile and lighting return; read-back shows 0.80 mm on every key.
- [ ] Alt-tab between the game and the desktop every 1-2 s for 30 s: no profile flicker and no extra writes (no new `trigger pkt` lines in the log).
- [ ] Map a game to a profile whose actuation equals the board's current value (0.80 to 0.80): on switch the log shows NO `trigger pkt` line.
- [ ] While a mapped game runs, switch profile by hand: Aether keeps your choice; after quitting the game it does NOT revert.
- [ ] Unplug the keyboard, launch the mapped game, wait 10 s, plug it back in: after reconnect the read-back shows the game profile's actuation and the lighting follows.
- [ ] Two mapped games running (different profiles): the one in front wins after about 6 s; switching to a browser keeps the last game's profile.
- [ ] Start Aether minimised to the tray (sign-in autostart) and launch a mapped game: the switch still happens with the window hidden.
- [ ] Idle CPU with detection on stays negligible (AetherHE under 1 %). Anti-cheat titles (e.g. EAC/Vanguard) start and run normally. Offline first run (network off, no cache): the app works, list count 0, user-added games still switch.

### Phase 4: analytics and auto-tune
- [ ] With key statistics on, the **Analytics** tab appears right after Actuation. It is absent for boards without `keyStats` (e.g. pick the MINI 60 HE PRO in the board picker).
- [ ] Type a paragraph: within about 5 s the heatmap (Today) shows the keys you used, the busiest one red/amber, unused keys uncoloured; Overview totals match Settings > Key statistics "Today".
- [ ] Click a key on the heatmap: Overview shows it. Ctrl-click a second key: "2 keys" with summed numbers; "clear" returns to Whole board. Range chips (Today / 7 / 14 / 30 days) change the numbers; Presses per Day shows today's bar at the right.
- [ ] At 0.80 mm: press one key gently ten times so it moves but does not type (about 0.3-0.6 mm). Overview shows them under Shallow. Ten light presses that just type (stop right after the click point) show under Barely over.
- [ ] Auto-tune with little data shows notes like "Space: N of 200 presses recorded..." and no suggestion; disconnecting shows "Connect the keyboard..." instead of suggestions.
- [ ] After enough typing (200+ presses on a key or group), check whether a suggestion appears and whether its text matches your experience (missed keys -> "earlier"; accidental letters -> "later"). Report suggestions that feel wrong: the 5 % / 15 % thresholds are a first guess.
- [ ] Apply a suggestion: a read-back runs (no "Read-back differs" notice), the Actuation tab shows the new value on exactly those keys, other keys are unchanged, and the suggestion disappears.
- [ ] Undo: those keys return to the previous value (check in the Actuation tab).
- [ ] Set one key to rapid trigger (RT on, Apply), produce a suggestion for it or its group, and Apply it: the key stays in rapid trigger with the same press/release sensitivities after read-back.
- [ ] Typing feel and CPU with the Analytics tab open for 5 minutes (refreshes every 5 s): no missed or doubled keys; closing the tab stops the refreshes.

### Phase 5: dashboard
- [ ] Launch at the minimum window (1160 x 800): opens on **Dashboard**, nothing scrolls, top bar shows Pair / zoom / gear (inactive tabs icon-only with tooltips). Switch to Lighting, quit, relaunch: opens on Lighting (remembered). Maximise: tab labels return.
- [ ] WIN60 connected, stats on: Heatmap matches today's typing (busiest keys red/amber); Today's presses, bottom-out % and shallow match the Analytics tab on "Today".
- [ ] Click a key on the hero: caption shows its presses today, bottom-out % and actuation (e.g. 0.80 mm). The Actuation tab's selection is unchanged.
- [ ] Switch the hero to **Live depth** and press keys: fills track travel, a key glows past its actuation point, "deepest" follows. Switch to Heatmap, then another tab: typing feel and CPU return to normal. Turn Travel Test on in the Actuation tab, come back to Live depth, leave again: Travel Test still streams.
- [ ] **Actuation** mode shows the same per-key values as the Actuation tab; the rail reads e.g. "0.80 mm on all 61 keys" and counts rapid-trigger keys correctly.
- [ ] Apply a suggestion from the Auto-tune panel: read-back succeeds, the rail's summary updates, the suggestion disappears, and the Analytics tab offers Undo.
- [ ] Start a mapped game: the rail shows "playing · profile ..." within a few seconds and the profile chip switches; an unmapped game shows "not mapped to a profile"; closing it shows "No game running".
- [ ] Pick effects from the Lighting panel (chips and arrows): the keyboard changes like a Lighting-tab click, and the tray mini panel shows the same effect.
- [ ] Unplug the keyboard: rail says Offline with Pair, Live depth says to connect, Heatmap/Today still show today's counts. Select the MINI 60 HE PRO (if available): Heatmap is not offered, Today says typing statistics need a live travel stream, and there are no Analytics links.
- [ ] Leave the app on the Dashboard for 5 minutes: CPU similar to the Analytics tab (no live stream unless Live depth is shown).

### Phase 6: overlays (CPU / RAM / GPU / Pomodoro)
- [ ] Dashboard, WIN60 connected, lighting = **Static**: tick **CPU**. The number row 1-0 becomes a bar, the rest keeps the static colour at the same brightness. Run a CPU stress: the bar climbs within about 2 s, green -> amber -> red. Untick: the board returns to exactly the static colour.
- [ ] Same with **RAM** (Q..P) and **GPU** on an NVIDIA machine (home row). Without `nvidia-smi` the GPU chip is disabled with the reason, and a hand-edited "gpu: true" does nothing.
- [ ] Lighting = a busy effect (Wave / Rain / Fireworks): bars sit on top, opaque and readable; the rest keeps animating. Press-reactive effects still react on other rows. Typing feel and Dashboard CPU are unchanged with CPU+RAM+GPU on; no console window may ever appear (check Task Manager and `nvidia-smi.exe` flicker).
- [ ] **Pomodoro**: tick it; the shift row fills left to right over 25 min. To test faster, set `"overlays": {"pomodoro": {"workMin": 1, "breakMin": 1}}` in `%LOCALAPPDATA%\AetherHE\settings.json` while Aether is closed. Work -> break pulses the board green for about 0.7 s, then the row restarts in green; break -> work pulses orange-red. The chip reads `Focus 24:30` / `Break 0:45`. Untick and tick again: the cycle restarts.
- [ ] **Per profile**: with two profiles, tick CPU on one only; switching profiles shows or hides the bar, and the tile chips follow within 2 s. A game-profile auto-switch does the same. Restart Aether: choices are remembered.
- [ ] Lighting **off** (power toggle) with CPU on: the board is dark except the bar. Untick: still off.
- [ ] Lighting = **Custom** (per-key paint): tick CPU; the paint stays on the other keys. Untick: the paint is back exactly (re-check a few colours).
- [ ] Change lighting while an overlay is on (colour, brightness, effect -> static -> effect): each change applies immediately with no flicker to a stale colour; switching to a host effect and back keeps the bar.
- [ ] Unplug with overlays on, plug back in: the bar returns after reconnect. While unplugged, `nvidia-smi.exe` is not started (Process Explorer).
- [ ] Kill Aether (end task) with an overlay on: the keyboard keeps the last frame (same as any host effect today); relaunch restores normal lighting. Note whether the board kept the bar after a power cycle.
- [ ] `flash`: from a Python console attached to the running app (or a throwaway script calling `Api.flash([255,0,0], 800)`), the whole board flashes red and fades in about 0.8 s over a host effect and over a running overlay. With plain Static and no overlay it answers `ok: false`.
- [ ] Leave CPU+RAM on for 30 minutes: Aether's CPU stays near the Dashboard idle baseline; no memory growth; no stuck pulse after the machine sleeps and wakes mid-Pomodoro.

### Phase 7: music visualizer
- [ ] Availability: launch from source. Lighting > Mode Picker: the Music tile is enabled. (Before the deps are installed it is dimmed and its tooltip says "Music visualizer needs the numpy and soundcard packages (not installed).")
- [ ] Bars: connect, play music, select Music: 14 columns follow the spectrum (bass on the left), height across the 5 rows, palette bottom -> top; the note reads "Listening to <your output device>. ...".
- [ ] Beat pulse: with a track that has a clear kick, unlit keys flash toward the first palette colour on the beats and fade within about 0.3 s; a steady pad or sine produces no pulses.
- [ ] Latency (under 60 ms): play a click track (e.g. 120 BPM); the pulse should look locked to the clicks. Optional: film keyboard and speaker at 240 fps and count frames between click and flash (14 or fewer).
- [ ] CPU (under 5 % of one core): Task Manager > Details > AetherHE.exe, compare Wave vs Music. Task Manager shows % of ALL logical processors, so on 16 threads 5 % of one core is about 0.3 %.
- [ ] Silence: pause playback; bars fall to dark within about 1 s and nothing stays lit. Resume: bars return.
- [ ] Output switch: while Music runs, change the default output (headphones or another device). Bars resume from the new device within about 2 s and the note shows its name.
- [ ] No device: disable every output device while Music runs. The note says "No audio output device found." and the bottom row breathes. Re-enable one: bars return.
- [ ] Capture stops: switch to Wave, then to a firmware effect (e.g. Static); CPU drops back to the baseline (no capture thread left running). Disconnect while Music runs: same.
- [ ] Speed and palette edits: drag the speed slider and change colours while Music runs; no stall; higher speed makes bars fall faster.
- [ ] Overlays: turn on the CPU overlay (Phase 6) with Music running: the number row shows the CPU bar over the music bars; turning it off restores the bars.
- [ ] Tray and Dashboard: pick Music from the tray mini panel and from the Dashboard lighting tile; it starts the same way.
- [ ] Frozen build (Phase 8): after installing the deps, build with PyInstaller; Music works in the frozen app. If the note says "Audio capture failed: ...mediafoundation...", the soundcard data files were not bundled (`collect_data_files("soundcard")` in `AetherHE.spec`).
- [ ] Size: compare the `dist\AetherHE` folder and the Inno Setup installer before and after the deps (estimate: about +25-40 MB unpacked, mostly numpy's OpenBLAS; about +10-15 MB installer; not measured).
- [ ] If no capture: try `get_microphone(str(speaker.name), include_loopback=True)` in music.py (reviewer note).

### DKS capture (advanced keys, vendor web driver)
Full steps are in `docs/context/aula-win60-advanced-keys-capture-checklist.md`. Summary only: Aether stays closed, budget about 20 minutes, and the vendor UI rewrites the keymap, macros and all 40 advanced slots on every Apply.
- [ ] D1: create a DKS bound to J (1.5 mm down and up); feel test in Notepad types "a" on the way down and again on the way up.
- [ ] D2: DKS hold bar; confirm the slot 0 bytes match the expected frame (pins the meaning of step code 2).
- [ ] M1 / M2: Mod-Tap on Caps Lock (tap = Esc, hold = L-Ctrl; hold byte before tap byte; 500 ms duration unit).
- [ ] T1: Toggle on K latches L-Shift (press once to latch, press again to release).
- [ ] R1: read-back after a page reload returns the same payload bytes.
- [ ] X1: delete the test entries; the board returns to 40 empty slots and J, K and Caps Lock type normally.
- [ ] Send back the JSON (Method 1) or filtered `.pcapng` (Method 2) with the step marks, one feel-test line per step, and any mismatch against an Expect line.

## WIN 68 HE Max bring-up (1CA2:1901, issue #7)
For a WIN 68 HE Max owner (nieruuu19 offered in #7). Nobody working on Aether owns this board, so every line below is unverified until a tester ticks it. `protocol_magnet.py` rebuilds all 344 frames the vendor web driver sent byte for byte (`tests/test_protocol_magnet.py`), but no frame from Aether has reached a Max yet. The board is detected and driven when plugged in; it is not offered in the board picker until this list passes.

### Before you start
- [ ] Close the vendor web driver (magnet.aulastar.com). Two programs on one HID handle steal each other's replies.
- [ ] Use a build from Aether's CI or `python app_web.py` on this repo. Never use a build from a fork.
- [ ] Note the Max's current lighting in the vendor driver so you can restore it.

### Default mode (safe: captured frames only)
- [ ] Connect: the top bar says WIN 68 HE MAX, and the on-screen keyboard is the 68-key layout (Ins/Del/PgUp/PgDn column, arrows). `aether.log` shows it opened the 0xFFA0 interface. If it opened another interface, report the `usage_page` list from the log.
- [ ] Static colour: pick Static and a colour; every key turns that colour. Change brightness 0-4 and confirm each step is visible.
- [ ] Lights off: the power toggle turns the board dark; on brings the colour back.
- [ ] Per-key paint: paint W, A, S and D; only those four change.
- [ ] Host effects: run Wave, then Rain, and note how smooth they look. hostEngineMaxFps is a guessed 12 (each changed key costs one HID write); report whether motion stutters or keys lag so the value can be tuned.
- [ ] Firmware effects: pick Breath. Aether should say the effect is not supported on this board rather than show something else. Effects 1-20 still need names: for each one, report the vendor driver's name for mode N (the vendor log prints 灯光模式：N).
- [ ] Travel: in default mode the Travel Test cannot run (live travel is experimental-only) and Key Statistics are not offered for this board. That is expected.

### Experimental mode (unverified frames from the contributor fork)
Set `AETHER_EXPERIMENTAL=magnet` before starting Aether (PowerShell: `$env:AETHER_EXPERIMENTAL="magnet"; python app_web.py`). `aether.log` then warns that experimental writes are on. Run these one at a time. If anything misbehaves, restore the board's settings with the vendor driver.
- [ ] Travel Test: press W slowly; the on-screen depth follows within about 50 ms and returns to 0 on release. Press keys on every row, including the arrows and the right-hand column, and check the right key moves. Wrong keys mean the 21-per-row matrix index is off: report which key lit for which press.
- [ ] Actuation: set W to 0.50 mm; W now fires on a shallow press in Notepad. Set it back to 2.00 mm. Re-open the vendor driver and check it shows the same values.
- [ ] Rapid trigger: set W to RT with 0.10 / 0.10 mm; tap-and-hold with small lifts re-fires W. Turn RT off again.
- [ ] SOCD: one A/D pair on Model 1 (last pressed wins); hold A, press D, release D: A should come back. Then Model 2 (A always wins), Model 3 (D always wins) and Model 4 (neutral: with A held, D is not sent and A stops): each must behave differently. Delete the pair.
- [ ] Send back: the `aether.log` from the session, which lines passed, and the vendor driver's view of actuation and SOCD after each write.
