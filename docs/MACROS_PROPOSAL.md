# Aether HE — Macros Proposal (v0.4.0 candidate)

> Status: **Draft**. Open question — exact user request from r/keyboards
> `1tmoypx/comment/ovukxbz` couldn't be retrieved (Reddit blocking + no
> Wayback snapshot). This proposal covers the 80%-case shape of "macros" so a
> first PR is meaningful even before the comment comes in. Adjust scope when
> the source text lands.

## 0. Goal

Let a user bind a **sequence of timed key events** to any key (or combo) on
supported Aula HE keyboards, with the trigger happening **on the host**
through the existing `Api` HID bridge. Macros persist per-profile, play back
through the same key-event injection path the UI already uses for remap, and
survive app restart + per-board export.

Out of scope for v0.4 (called out so we don't scope-creep):
- Onboard/firmware-side macros (needs protocol decode per board — see §6).
- Mouse-button macros (no gamepad uinput signal yet on Windows; even on Linux
  it lives in `gamepad.py`, gated to Linux).
- Macro UI that contradicts the v0.2.0 widget-shell pattern.

## 1. Data shape — `macros.json`

A single new file in the same directory that already holds lighting profiles
(`profiles/<board-vid-pid>/macros.json`). Schema (one key per bound trigger):

```json
{
  "version": 1,
  "updated": "2026-07-07T15:30:00Z",
  "macros": [
    {
      "id": "uuid-v4",
      "name": "Discord mute toggle",
      "trigger": { "type": "tap", "key": "F1" },
      "steps": [
        { "op": "press",   "code": "ControlLeft" },
        { "op": "press",   "code": "KeyD" },
        { "op": "release", "code": "KeyD" },
        { "op": "release", "code": "ControlLeft" },
        { "op": "delay",   "ms": 50 }
      ]
    },
    {
      "id": "uuid-v4",
      "name": "Snippet: signature",
      "trigger": { "type": "combo", "keys": ["LShift", "KeyS"] },
      "steps": [
        { "op": "type", "text": "Best,\n— Me" }
      ]
    }
  ]
}
```

Step ops (small, deliberately):
- `press(code)` — synthetic press; respects active modifiers
- `release(code)`
- `delay(ms)` — block the macro queue for N ms (inter-key timing)
- `type(text)` — expansion in input chunks; each chunk broken on modifier-safe
  boundaries (no typing across an unheld modifier)

Codes use the same dictionary the rest of the app already uses
(`device_state.DESIGN_CODES` for named keys, `KeyA`/`Digit1`/etc for
browser-event codes — same set the remap UI uses).

## 2. Engine — `macros.py`

New file alongside `effects.py` / `gamepad.py`. Single class:

```python
class MacroEngine:
    def __init__(self, api, keymap, profile_path):
        self.api = api                  # bridge back into Python (device_state, keymap)
        self.km = keymap
        self.path = profile_path
        self.queue = queue.Queue()      # serialized macro steps
        self.worker = threading.Thread(target=self._run, daemon=True)
        self.recording = False
        self.active_macros = {}         # trigger -> macro_id

    def load(self, macros_json_path): ...
    def bind(self, trigger, steps): ...  # adds to active_macros + persists
    def unbind(self, trigger): ...
    def on_key_event(self, code, pressed): ...  # called by Api on every input
    def _run(self):                     # consumer: pop step, exec, sleep
        while True:
            step = self.queue.get()
            ...
```

Two key design choices:
- **Single worker thread, one queue.** Plays macros strictly sequentially within
  the app. Multi-macro triggers fire back-to-back in arrival order. Cheaper
  than a stack/coroutine model and matches the "predictable, debuggable"
  vibe of the rest of Aether.
- **Trigger firings** happen on host key events from the same `Api.on_key_event`
  the remap UI already consumes. No new polling. No new HID reads.

## 3. Trigger dictionary — what can fire a macro

- `tap` — single key (the simplest 80% case; covers the Reddit comment's likely shape).
- `combo` — modifier+key, all held within a 100 ms window.
- `hold` — key held for ≥ N ms before fire (avoids accidental triggers).
- `double-tap` — two taps within 250 ms.
- (later) `layer` — Fn + key on the layer-shift layer.

This mirrors what Via/QMK expose, so users coming from those tools won't get
culture-shocked.

## 4. UI — new `Macros` section widget

Matches the v0.2.0 desktop-shell widgets the other sections use. File:
`ui/runtime_src/src/sections/macros.jsx`. CRUD list on the left, step editor
on the right. Two affordances the UI must have:

1. **Active-key badge in the keyboard panel header** — same fix from the
   Reddit thread about "can't select individual keys". Clicking a key on the
   keyboard widget puts `selectedKey` in app-level state; Macros shows
   "Editing trigger key: F1"; Keymap / Lighting / Actuation all see the same
   selection. This also retroactively fixes that complaint.
2. **Recorder button** — `record_macro.py` analog on the JS side: arm, fire
   keys, disarm → emits the same step list §1 uses.

The compiler step (`ui/runtime_src/build_runtime.py`) already ingests new
jsx files in `sections/`, so no build wiring changes.

## 5. Persistence + per-board gating

- File lives in `profiles/<vid>-<pid>/macros.json` next to the existing
  per-board lighting profile. Format matched to `profiles/<...>/lighting.json`
  for consistency.
- `tools/validate_profile.py` gets a `validate_macros(path)` peer function
  (size cap, no `eval`, no `__import__`, op set whitelist, single-step time
  cap, total-step cap). Fail-closed on bad input — the same posture
  `validate_keymap.py` already takes.
- Per-board gating: a board is *macro-capable* only when its `boards.py`
  entry has `lighting=True` and the connected handle is open. Boards still in
  layout-only state (`#5` Win60 HE Max, `#7` WIN 68 HE Max) show the macros
  widget disabled with a pointer to the protocol-capture TODO.
- Import/export buttons next to the section header use the same pattern
  lighting already uses.

## 6. Per-board wire requirements

`boards.py` already maps VID/PID → `Board` capability flags. Add one flag:

```python
class Board:
    ...
    macros: bool = False   # default; only True where protocol is decoded
```

Set `macros=True` for the boards where lighting + actuation are already
working (currently just `#3` Aula WIN 60 HE Pro after `#3`'s actuation
decode landed). Flip the others to `True` the same day their lighting decode
lands — keeps the contract tight.

There is **no firmware-side macro trigger** for any current Aula board we're
aware of; we don't have evidence one exists, and `KBblindtestV3EN.pyw`
(contributed via #3) doesn't expose one. So v0.4 is host-side only. If a
firmware macro path turns up in a future capture, this is the only section
that grows.

## 7. Estimated scope (real numbers, not fantasy)

- `macros.py`: ~250 LOC (engine + recorder + validation + persistence)
- `macros.jsx` UI widget: ~400 LOC React
- Bridge additions in `app_web.py`: ~60 LOC (load on startup, expose CRUD
  Api methods, hook `on_key_event` → engine trigger eval)
- `validate_profile.macros`: ~80 LOC
- Tests: ~150 LOC (trigger eval, queue draining, validation catches)
- Docs update (CLAUDE.md, SUBMIT_A_BOARD.md): ~30 LOC

Two-day focused PR if no blockers; four-day if the Reddit comment reveals a
shape we didn't anticipate (string templates, conditional steps, etc.).

## 8. Open questions to resolve

1. **What's actually in the Reddit comment?** Until we can read it, scope
   is set to a "shape QMK users recognize" baseline.
2. **Per-key recording conflict with rebinding.** If a key is remapped AND
   has a macro attached, which wins? Default proposal: macro wins, with a
   yellow warning when both fire.
3. **Multi-board profiles.** One macros file per board (matches lighting),
   but the UI should let a user copy a macro across boards. v0.4 can ship
   without copy and add it in v0.5 if it bites anyone.
4. **Recording in OS key events vs only keyboard-internal events.** v0.4
   records from the live key stream only — won't pick up text typed in
   another app. v0.5 can wire a low-level OS hook if it matters.

## 9. What this PR will NOT do

- Won't add firmware-side macros (needs hardware evidence we don't have).
- Won't ship to un-decoded boards (gating contract above).
- Won't replace the existing keymap remap UI.
- Won't snake anything into `gamepad.py` — macros are keyboard-side only.
