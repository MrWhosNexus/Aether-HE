## Problem

The Aula Win60 HE keyboard's travel-test stream (cmd 33) carries two report subtypes:

- **Subtype 5** (`r[5] == 5`) — travel in 0.01 mm units. Used by `LiveReader` for per-key analog depth tracking.
- **Subtype 3** (`r[5] == 3`) — raw Hall ADC value. **Previously unhandled** — the reader skipped these frames entirely.

Subtype 5 is **event-driven and never sends 0.0 mm on key release**. When a key is released, the firmware simply stops sending updates — the last known depth (typically 0.1–1.23 mm of electrical noise) stays cached in `LiveReader.depths` indefinitely. This caused three problems in the virtual gamepad:

1. **Stuck axes** — released keys kept their last depth, the gamepad axis never returned to zero
2. **30 Hz oscillation** — the EMA smooth-decay alternated between instant-rise and `×0.7` decay when fed a small constant from a stuck key, perceived as stick shudder
3. **Race conditions** — concurrent reader/gamepad threads could snapshot a partially-popped `depths` dict

Previous mitigations (1.5 mm depth gate, 3-second stuck-key timeout, EMA decay) were bandaids — the gate ate ~30 % of the travel range, and the timeout kept released keys alive for up to 3 seconds.

## Solution

### 1. Decode subtype 3 as a release signal (`device_state.py`, `aula_device.py`)

Subtype 3 frames **do send 0 on key release**, unlike subtype 5. LiveReader now accepts both subtypes:

- **Subtype 3 + `raw_adc == 0` → confirmed release.** The key is immediately popped from `depths` under `_depth_lock` and added to the `_released` set. No stale subtype-5 report can re-add it until a non-zero frame signals a fresh press.
- **Subtype 3 + `raw_adc > 0` → clears `_released`, resumes normal depth tracking.
- **Subtype 5 → processed as before**, but skipped entirely if the key is in `_released`.

This eliminates the stuck-key problem at the root: the firmware **does** send a release signal — just not on the subtype we were listening to.

`aula_device.py:parse_travel()` now returns `{"key": (row, col), "raw_adc": int}` for subtype 3 with a debug hex dump.

### 2. Instant-drop in gamepad smooth-decay (`gamepad.py`)

Both backends (evdev + vgamepad) now short-circuit `raw == 0 → return 0`, so an unambiguous release signal cuts the axis to zero in a single frame (~8 ms at 120 fps). The EMA decay is preserved for **non-zero sensor micro-jitter** on held keys. The vgamepad backend was refactored to use a shared `_ema()` helper.

### 3. Impact on heuristics

| Heuristic | Before | After |
|-----------|--------|-------|
| `AXIS_GATE_MM = 1.5` | Primary stuck-key filter, ate 30 % of travel | Safety net — rarely reached |
| `STUCK_SILENCE_S = 3.0` | Only way to eventually release | Safety net — subtype 3 fires in <200 ms |
| EMA decay (`DECAY = 0.7`) | Masked jitter with exponential tail | Only smooths micro-jitter; `raw == 0` drops instantly |

## Testing environment

- **Keyboard**: Aula Win60 HE (VID 0x2E3C, PID 0xC365)
- **OS**: Windows 11 Pro (build 26100) 64-bit
- **Python**: 3.11.9
- **pywebview**: 6.2.1
- **hidapi**: 0.15.0
- **Test cases**: rapid key tapping, sustained holds, multi-key chords, gamepad axis response — all verified on physical hardware

## Related

- Prior fix (commit c48d50b): eliminated 30 Hz oscillation in EMA smooth-decay, added 1 mm depth gate and stuck-key timeout — these are now superseded by the subtype-3 signal as the primary release detection mechanism.
