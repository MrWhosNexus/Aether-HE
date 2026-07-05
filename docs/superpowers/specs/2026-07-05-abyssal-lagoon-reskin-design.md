# Design: Convert AetherHE web UI to the "Abyssal Lagoon" look

**Date:** 2026-07-05
**Status:** Approved (design), pending spec review → implementation plan
**Target app version:** next update

## Goal

Re-skin the AetherHE shipping UI (the React/Tailwind web UI rendered natively in
WebView2 / GTK-WebKit) to match the "Abyssal Lagoon" liquid-glass design language
from the Nexus app, so AetherHE reads as a Nexus sibling. This is a full aesthetic
re-skin, not a color swap.

### Decisions (locked with user)

1. **Depth:** Full re-skin — green-black base, mint/ember default accent, the three
   Nexus fonts, liquid-glass panels, drifting aurora backdrop, grain + vignette.
2. **Accent model:** Mint becomes the single accent default; the app's existing
   `--accent`-driven recolor engine means a user's chosen color still propagates
   through the whole UI. Only defaults + presets change.
3. **Fonts:** Bundle all three (Instrument Serif, Schibsted Grotesk, Fragment Mono)
   as offline data-URI `@font-face` — no Google Fonts links (app must stay offline).
4. **Presets:** Replace theme-customizer palette + background presets with an Abyssal
   set (mint/ember palettes + the four Nexus auroras); keep the custom color picker.

## Non-goals (YAGNI / scope guardrails)

- Legacy Tkinter UI (`theme.py`, `main.py`, `keyboard_widget.py`) — already excluded
  from the PyInstaller bundle (`AetherHE.spec` entry is `app_web.py`). Do not touch.
- Device/HID/effects/protocol logic, board layouts, the `applyTheme()` gradient engine.
- Keyboard diagram key rendering: keys keep showing **actual device RGB**; only the
  surrounding chrome/labels get restyled so lighting stays truthful.
- No unrelated refactoring beyond what the re-skin requires.

## Source-of-truth reference (Nexus tokens)

From `C:\Users\yygbu\nexus\renderer\src\theme\styles.css` `:root`:

```
--accent: #6fe8c0;   /* lumen mint */
--accent-2: #f4b268; /* ember */
--ink: #06110f; --ink-2: #0a1a17;
--text: #eaf4f0; --text-dim: #8fa9a2; --text-faint: #557069;
--line: rgba(234,244,240,0.09);
--good: #7be3b0; --warn: #f4b268; --bad: #f08a78;
--radius: 18px; --glass-blur: 22px; --glass-tint: 0.42;
--ease-out: cubic-bezier(0.22, 1, 0.36, 1);
--font-display: 'Instrument Serif', georgia, serif;
--font-ui: 'Schibsted Grotesk', system-ui, sans-serif;
--font-mono: 'Fragment Mono', ui-monospace, monospace;
```

## Current state (what we're replacing)

`ui/runtime_src/head_inner.html` `:root`:

```
--bg-0: #07080d; --bg-1: #0b0d15; --bg-2: #0f1220; --bg-3: #161a29;
--line: rgba(148,163,184,0.08);
--accent: #9d4edd; --accent-2: #9d4edd; --accent-fg: #1a0833;
--accent-glow: rgba(157,78,221,0.45);
```

- Fonts: Inter (UI), Rajdhani (`.font-display`), JetBrains Mono (`.font-mono`),
  embedded as data URIs from the original bundle manifest.
- Backdrop: static `body::before` radial accent glows + `#__bg-image-layer`.
- Components: heavily Tailwind-utility-driven — raw `text-slate-*`, `bg-white/[n]`,
  `border-white/*`, `rounded-*` scattered across ~175KB of JSX
  (`app.jsx` 54KB, `sections.jsx` 105KB, `keyboard.jsx` 15KB). Thin semantic layer
  (`.surface`, `.surface-flat`, `.pill-active`) in `head_inner.html`.

## Architecture — three layers

The faithful path is not a global find/replace on colors. It's: introduce a
Nexus-style semantic layer, then migrate the JSX onto it.

### Layer 1 — Token layer (`head_inner.html` `:root`)

Replace the cool-blue tokens with the Abyssal Lagoon set (see reference above):
`--ink/--ink-2`, `--text/--text-dim/--text-faint`, `--line`, `--accent` (mint),
`--accent-2` (ember), `--good/--warn/--bad`, `--radius: 18px`, `--glass-blur: 22px`,
`--glass-tint: 0.42`, `--ease-out`, and the three `--font-*`. Keep `--accent-fg`,
`--accent-glow`, `--accent-gradient`, `--accent-2/3/4` names the `applyTheme()`
engine already writes to, so recolor keeps working.

### Layer 2 — Primitives layer (new CSS ported from Nexus `styles.css`)

Add semantic classes so the glass identity lives in one place:
`.glass`, `.panel`, `.rail` / `.rail-tab` (nav), `.btn` / `.btn.accent` / `.btn.danger`,
`.chip` (+ `.running/.done/.failed`), `.switch`, `.input`, and the background engine
`.bg-layer` / `.aurora-blob` (+ `.b2/.b3`) / `.grain` / `.vignette`, plus the
`prefers-reduced-motion` block. Port faithfully from
`nexus/renderer/src/theme/styles.css` (glass primitive lines ~99–129; aurora ~46–95;
buttons/inputs ~350–405; reduced motion ~1073–1078).

### Layer 3 — JSX migration (the sweep)

Replace hardcoded Tailwind utilities with semantic classes or var-bound arbitrary
values:
- `text-slate-100/300/400/500` → `text-[var(--text)] / var(--text-dim) / var(--text-faint)`
- `bg-white/[0.04]` etc. → glass/surface classes or `bg-[color-mix(...)]`
- `border-white/*` → `border-[var(--line)]`
- card containers → `.glass`
- `rounded-xl/lg` retained but panels use `--radius`

Do it in dependency order, section by section, each independently verifiable:
1. Global shell + top nav / profile dropdown (`app.jsx` chrome)
2. Left nav / rail
3. Each panel in `app.jsx`
4. The five setting screens in `sections.jsx` (Keymap, Lighting, Actuation, SOCD, Other)
5. `keyboard.jsx` last (chrome only; keys keep device RGB)

## Background & type

- Replace static `body::before` radial glows with the Nexus drifting aurora: a base
  gradient + three blurred `mix-blend: screen` blobs (36–58s drift), an SVG fractal
  grain overlay, and a vignette. **Keep `#__bg-image-layer`** so user image backdrops
  still work (theme customizer feature).
- Extend `ui/runtime_src/build_runtime.py` with a one-time WOFF2 fetch→embed step for
  the three fonts (mirroring the existing manifest data-URI embed), producing offline
  `@font-face` rules in `head_inner.html`. Map `.font-display`→Instrument Serif,
  body/default→Schibsted Grotesk, `.font-mono`→Fragment Mono. Remove Rajdhani, Inter,
  and JetBrains Mono faces.

## Theme customizer presets (`vendor/theme.jsx`)

- `PALETTE_PRESETS` → Abyssal set: e.g. Lagoon `[#6fe8c0]`, Ember `[#f4b268]`,
  Tide `[#6fe8c0,#8ae0ff]`, Moss `[#7be3b0,#c9e07a]`, Aurora `[#6fe8c0,#f4b268]`,
  plus a mono/slate option. Default = Lagoon mint.
- `IMAGE_PRESETS` → the four Nexus auroras (ember, tide, moss, violet-hour) as
  gradient data-URIs, matching `nexus/renderer/src/components/Background.tsx` bases.
- Keep the custom color picker and the 1–4 color gradient logic (`applyTheme`) intact.
- Update `DEFAULT_THEME.palette` to `["#6fe8c0"]`.

## Testing / verification

1. Run `venv-web/bin/python ui/runtime_src/build_runtime.py` — build succeeds, fonts
   embed, no Google Fonts link remains, output `index_runtime.html` is self-contained.
2. Launch `app_web.py` in the WebView shell.
3. Walk all five sections + profile dropdown + theme customizer; do a user recolor and
   confirm it propagates.
4. Confirm glass blur, drifting aurora, grain, vignette, and the three fonts render;
   confirm no leftover slate-gray / violet remnants.
5. Confirm keyboard diagram still shows real per-key device colors.
6. Confirm `prefers-reduced-motion` disables aurora/animation.
7. Before/after screenshots.

## Risks

- **JSX sweep breadth (~175KB):** the main risk. Mitigated by doing it section-by-
  section with verification between, and by centralizing style in Layers 1–2 so the
  sweep is mechanical, not creative.
- **Font sourcing offline:** build step must fetch WOFF2 once; if network is
  unavailable at build time, cache the WOFF2 files in-repo (e.g. `ui/runtime_src/fonts/`)
  so subsequent offline builds succeed.
- **Backdrop-filter cost in WebView:** aurora + blur is GPU-heavier than the old static
  glow; verify performance in the actual WebView2/GTK-WebKit shell, not just a browser.
