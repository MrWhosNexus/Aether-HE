# Auto-update on launch (first-run opt-out)

Date: 2026-07-06
Status: approved

## Problem

Update checking exists (`updater.py` + `Api.check_update` / `Api.apply_update`) but
is only reachable inside the Settings panel, which silently auto-checks once when
that panel mounts. A user who never opens Settings never learns an update exists.
We want the app to keep itself current by default, while letting a user opt out.

## Decision

On launch the app auto-installs updates by default. The only prompt is a one-time,
first-run opt-out. A preference persists the choice; a Settings toggle changes it
later. (Chosen over "prompt every launch" and "update-now/later only".)

Windows behavior: auto-update means the app briefly opens, then the existing silent
installer closes and relaunches it. No per-launch confirmation. Default flag = on.

## Preference storage

Single flag `autoUpdate` in the existing `settings.json`
(`<config-root>/AetherHE/settings.json`). The pure read/merge logic lives as
stdlib-only helpers in `updater.py` (so it is unit-testable without importing
`app_web`, which pulls in `hid`); the `Api` methods are thin wrappers passing
`self._settings_path()`:

- `updater.get_auto_update(path)` -> `True | False | None`
  (`None` = key absent / unreadable = first run / never answered)
- `updater.set_auto_update(path, on)` -> loads the current blob, sets only
  `autoUpdate`, writes it back; never clobbers sibling keys.
- `Api.get_auto_update()` -> `{ok, autoUpdate}`; `Api.set_auto_update(on)` ->
  `{ok, autoUpdate}`.

The install mechanics in `updater.py` are unchanged; only the two pref helpers
are added.

## Startup flow (React root, app.jsx, on mount)

Driven from React to match how Settings already calls the bridge and to keep modal
styling consistent. Guards on `window.pywebview.api` being present (same pattern as
the existing update code).

1. `get_auto_update()`.
2. `null` (first run) -> blocking modal: "Keep Aether up to date? [Yes, auto-update]
   / [No, I'll check manually]". Save the choice via `set_auto_update`. On **Yes**,
   fall through to step 3 this launch; on **No**, dismiss.
3. `true` -> silently `check_update()`. If `r.update`, show a small "Updating Aether
   to vX..." overlay and call `apply_update(r.asset_url, r.asset_name)`. Windows:
   installer takes over, app quits/relaunches. Flatpak: host install, overlay says
   "restart to apply". Other: download only, overlay reports the path. If offline /
   no update / check error -> do nothing, no overlay (never nag at launch).
4. `false` -> nothing at startup. Manual check remains in Settings.

## Settings panel (sections.jsx)

Add an "Auto-update on launch" toggle next to the existing update UI, wired to
`get_auto_update` (initial state) and `set_auto_update` (on change).

## Error handling

- Startup `check_update` failure: swallowed silently.
- `apply_update` failure: surfaced in the overlay with a dismiss button.

## Out of scope (YAGNI)

Background/scheduled polling, per-release "skip this version", changes to
`updater.py`, and any non-launch trigger.

## Testing

- `tests/test_auto_update_pref.py`: unit tests against a temp settings path.
  - fresh (no file) -> `get_auto_update` returns `null`
  - `set_auto_update(True)` then `get` returns `true`; `False` -> `false`
  - setting the flag preserves an existing unrelated key in `settings.json`
- React startup orchestration + modals: manual-verified, consistent with the
  existing untested update state machine.

## Files

- `app_web.py` — `get_auto_update`, `set_auto_update`
- `ui/runtime_src/src/app.jsx` — startup effect + first-run modal + updating overlay
- `ui/runtime_src/src/sections.jsx` — auto-update toggle
- rebuild `ui/index_runtime.html` via `ui/runtime_src/build_runtime.py`
- `tests/test_auto_update_pref.py` — new
