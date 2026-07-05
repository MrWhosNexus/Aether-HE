# Abyssal Lagoon Re-skin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-skin the AetherHE web UI (React/Tailwind, rendered in WebView2/GTK-WebKit) to the Nexus "Abyssal Lagoon" liquid-glass look — green-black base, mint/ember accent, three bundled offline fonts, aurora backdrop, glass panels.

**Architecture:** Three layers. (1) Token layer — swap the `:root` CSS custom properties in `head_inner.html`. (2) Primitives layer — add `.glass`/aurora/`.btn`/`.input`/`.chip`/`.switch` classes ported from Nexus `styles.css`. (3) JSX sweep — migrate hardcoded Tailwind utilities (`text-slate-*`, `bg-white/[n]`, `border-white/*`, panel `rounded-*`) onto the tokens/primitives, section by section. Fonts and theme-customizer presets are self-contained side tasks.

**Tech Stack:** Vendored React + Tailwind (browser, no bundler) compiled via `@babel/standalone` in `ui/runtime_src/build_runtime.py` → self-contained `ui/index_runtime.html`; served by `app_web.py` in a native WebView. Python build script. No npm install step.

**This is a re-skin, not feature work.** There are no unit tests. The test cycle for every task is: **rebuild → launch → observe**. Specifically:
- Build: `venv-web/bin/python ui/runtime_src/build_runtime.py` (from repo root `C:\Users\yygbu\aether-windows`). On Windows PowerShell use `.\venv-web\Scripts\python.exe ui\runtime_src\build_runtime.py` if the POSIX path is absent; plain `python ui/runtime_src/build_runtime.py` also works.
- Launch: `python app_web.py` and interact with the WebView window.
- Each task ends by rebuilding (must succeed) and visually confirming the described change, then committing.

## Global Constraints

- **Offline-only:** the final `ui/index_runtime.html` must contain zero network references — no `fonts.googleapis.com`, `fonts.gstatic.com`, or any `http://`/`https://`. Enforced by a build assertion (Task 4).
- **Preserve accent engine:** `applyTheme()` in `vendor/theme.jsx` writes `--accent`, `--accent-2`, `--accent-3`, `--accent-4`, `--accent-glow`, `--accent-fg`, `--accent-gradient`. These custom-property NAMES must not be renamed — only default values and presets change. User recolor must keep working.
- **Keyboard truth:** the keyboard diagram keys must keep rendering real per-key device RGB. Never route `ledColor`/`depth`/`actuationPoint`-driven inline `style={{}}` values through tokens/classes.
- **Do not touch:** legacy Tkinter UI (`theme.py`, `main.py`, `keyboard_widget.py` — excluded from the bundle), device/HID/effects/protocol logic, board layouts.
- **Target palette (verbatim):** `--accent #6fe8c0` mint · `--accent-2 #f4b268` ember · `--ink #06110f` · `--ink-2 #0a1a17` · `--text #eaf4f0` · `--text-dim #8fa9a2` · `--text-faint #557069` · `--line rgba(234,244,240,0.09)` · `--good #7be3b0` · `--warn #f4b268` · `--bad #f08a78` · `--radius 18px` · `--glass-blur 22px` · `--glass-tint 0.42` · `--ease-out cubic-bezier(0.22,1,0.36,1)`.
- **Fonts:** `--font-display` Instrument Serif (400) · `--font-ui` Schibsted Grotesk (400/500/600) · `--font-mono` Fragment Mono (400/400i).
- **Work branch:** `feature/abyssal-lagoon-reskin` (already created).

## File Structure

| File | Responsibility | Tasks |
|---|---|---|
| `ui/runtime_src/head_inner.html` | `:root` tokens, `@font-face`, primitive CSS classes, aurora/reduced-motion CSS, shim retarget | 1, 2, 3, 4 |
| `ui/runtime_src/build_runtime.py` | embed local fonts + offline assertion | 4 |
| `ui/runtime_src/fonts/*.woff2` | 6 committed offline font files (new dir) | 4 |
| `ui/runtime_src/vendor/theme.jsx` | palette + image presets, default-theme + fallback literals | 5 |
| `ui/runtime_src/src/app.jsx` | shell, top nav, rail, panels — utility sweep + aurora markup | 3, 6, 7 |
| `ui/runtime_src/src/sections.jsx` | five setting screens — utility sweep | 8a–8e |
| `ui/runtime_src/src/keyboard.jsx` | keyboard diagram chrome — utility sweep (device colors untouched) | 9 |

---

### Task 1: Token layer + shim retarget

Swap `:root` to the Abyssal Lagoon tokens and retarget the existing `.surface`/`.surface-flat`/`.pill-active`/`.menu-pop` classes in the SAME commit — otherwise `.pill-active` (which consumes `--accent-glow`) renders mismatched the moment the accent flips to mint.

**Files:**
- Modify: `ui/runtime_src/head_inner.html:506-518` (`:root`), `:520` (`html, body`), `:602-631` (shim classes)

**Interfaces:**
- Produces: CSS custom properties `--ink --ink-2 --text --text-dim --text-faint --line --good --warn --bad --radius --glass-blur --glass-tint --ease-out`, and re-defaulted `--accent #6fe8c0 --accent-2 #f4b268 --accent-gradient #6fe8c0 --accent-fg #06110f --accent-glow rgba(111,232,192,0.45)`. Consumed by every later task.

- [ ] **Step 1: Replace the `:root` block** (`head_inner.html:506-518`)

```css
:root {
  --ink: #06110f;
  --ink-2: #0a1a17;
  --text: #eaf4f0;
  --text-dim: #8fa9a2;
  --text-faint: #557069;
  --line: rgba(234, 244, 240, 0.09);
  --good: #7be3b0;
  --warn: #f4b268;
  --bad: #f08a78;
  --radius: 18px;
  --glass-blur: 22px;
  --glass-tint: 0.42;
  --ease-out: cubic-bezier(0.22, 1, 0.36, 1);

  /* applyTheme() writes these at runtime — names preserved, defaults changed */
  --accent: #6fe8c0;
  --accent-2: #f4b268;
  --accent-gradient: #6fe8c0;
  --accent-fg: #06110f;
  --accent-glow: rgba(111, 232, 192, 0.45);
}
```

The old `--bg-0/1/2/3` are removed. (Step 3 audits for stray usages.)

- [ ] **Step 2: Update `html, body`** (`head_inner.html:520`)

```css
html, body { background: var(--ink); color: var(--text); font-family: var(--font-ui, 'Schibsted Grotesk', system-ui, sans-serif); }
```

`--font-ui` is defined in Task 4; the `system-ui` fallback keeps rendering correct until then.

- [ ] **Step 3: Audit for orphaned `--bg-*` usages**

Run (Grep tool or): `grep -rn "var(--bg-" ui/runtime_src/head_inner.html ui/runtime_src/src`
Expected: only matches (if any) are the `.surface`/scrollbar rules edited in Step 4. If a `--bg-1/2/3` appears in JSX, note it and map it to `var(--ink-2)` (surfaces) or `var(--ink)` (base) — fix inline here.

- [ ] **Step 4: Retarget shim classes** (`head_inner.html:602-631`)

Replace hardcoded `rgba(255,255,255,*)` (white tints) with `--text`-based mixes and `rgba(20,24,38,*)` (old slate glass) with `--ink-2`-based values, keeping the class structure. Concretely, in `.surface`, `.surface-flat`, `.pill-active`, `.menu-pop`: change every `rgba(255,255,255,0.0X)` → `rgba(234,244,240,0.0X)` and every `rgba(20,24,38,0.YY)` / dark-slate background → `color-mix(in srgb, var(--ink-2) YY%, transparent)` (or `rgba(8,18,23,0.YY)`). `.pill-active`'s `--accent-glow` reference stays as-is (now mint). Read the exact current values at 602-631 before editing and preserve every non-color property.

- [ ] **Step 5: Rebuild**

Run: `python ui/runtime_src/build_runtime.py`
Expected: completes, writes `ui/index_runtime.html`, no error.

- [ ] **Step 6: Launch and verify**

Run: `python app_web.py`
Expected: app background is deep green-black (`#06110f`), text is off-white green-tinted, any active pill/segment glows mint (not violet). Nothing white-on-white or invisible.

- [ ] **Step 7: Commit**

```bash
git add ui/runtime_src/head_inner.html ui/index_runtime.html
git commit -m "feat(theme): Abyssal Lagoon token layer + shim retarget"
```

---

### Task 2: Glass + control primitives CSS

Add the reusable classes the JSX sweep will target. CSS only — no visual change yet until markup uses them (except `.pill-active` already retargeted).

**Files:**
- Modify: `ui/runtime_src/head_inner.html` (insert after the `:root` block, before `input[type="range"].aether`)

**Interfaces:**
- Produces: classes `.glass`, `.btn` (+`.accent`/`.danger`/`.on`), `.input`, `.chip` (+`.running`/`.done`/`.failed`), `.switch` (+`.on`), and a `prefers-reduced-motion` block. Consumed by Tasks 6–9.

- [ ] **Step 1: Add the glass primitive**

```css
.glass {
  position: relative;
  border-radius: var(--radius);
  background:
    linear-gradient(160deg, rgba(234, 244, 240, 0.055), rgba(234, 244, 240, 0.012) 38%),
    rgba(8, 18, 23, var(--glass-tint));
  backdrop-filter: blur(var(--glass-blur)) saturate(1.5);
  -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(1.5);
  box-shadow:
    0 24px 60px -18px rgba(0, 0, 0, 0.6),
    inset 0 1px 0 rgba(234, 244, 240, 0.14);
}
.glass::before {
  content: '';
  position: absolute; inset: 0;
  border-radius: inherit;
  padding: 1px;
  background: linear-gradient(165deg,
    rgba(234, 244, 240, 0.35),
    rgba(234, 244, 240, 0.06) 30%,
    rgba(234, 244, 240, 0.02) 60%,
    color-mix(in srgb, var(--accent) 22%, transparent) 100%);
  -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  -webkit-mask-composite: xor;
          mask-composite: exclude;
  pointer-events: none;
}
@supports not ((backdrop-filter: blur(1px)) or (-webkit-backdrop-filter: blur(1px))) {
  .glass { background: rgba(8, 18, 23, 0.9); }
}
```

The `@supports` fallback covers GTK-WebKit builds lacking `backdrop-filter` (a solid darker tint instead of blur).

- [ ] **Step 2: Add buttons + inputs**

```css
.btn {
  font-family: var(--font-ui); font-size: 12.5px; color: var(--text);
  background: rgba(234, 244, 240, 0.06); border: 1px solid var(--line);
  border-radius: 10px; padding: 7px 13px; cursor: pointer;
  transition: background 0.18s, border-color 0.18s, color 0.18s, transform 0.12s;
}
.btn:hover { background: rgba(234, 244, 240, 0.11); }
.btn:active { transform: scale(0.96); }
.btn:disabled { opacity: 0.45; cursor: default; }
.btn.accent {
  background: color-mix(in srgb, var(--accent) 20%, transparent);
  border-color: color-mix(in srgb, var(--accent) 45%, transparent);
  color: color-mix(in srgb, var(--accent) 80%, #fff);
}
.btn.accent:hover { background: color-mix(in srgb, var(--accent) 30%, transparent); }
.btn.danger { border-color: color-mix(in srgb, var(--bad) 50%, transparent); color: var(--bad); }
.btn.on {
  background: color-mix(in srgb, var(--accent) 24%, transparent);
  border-color: color-mix(in srgb, var(--accent) 50%, transparent);
}
.input, textarea.input {
  font-family: var(--font-ui); font-size: 13px; color: var(--text);
  background: rgba(5, 11, 14, 0.5); border: 1px solid var(--line);
  border-radius: 10px; padding: 8px 12px; outline: none; width: 100%;
  transition: border-color 0.18s, box-shadow 0.18s;
}
.input:focus {
  border-color: color-mix(in srgb, var(--accent) 55%, transparent);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 12%, transparent);
}
```

- [ ] **Step 3: Add chip + switch**

```css
.chip {
  font-family: var(--font-mono, monospace); font-size: 9px;
  text-transform: uppercase; letter-spacing: 0.08em;
  padding: 3px 8px; border-radius: 999px; border: 1px solid var(--line);
  color: var(--text-dim); flex: 0 0 auto;
  transition: color 0.2s, border-color 0.2s;
}
.chip.running { color: var(--warn); border-color: color-mix(in srgb, var(--warn) 40%, transparent); }
.chip.done { color: var(--good); border-color: color-mix(in srgb, var(--good) 40%, transparent); }
.chip.failed { color: var(--bad); border-color: color-mix(in srgb, var(--bad) 40%, transparent); }
.switch {
  width: 38px; height: 21px; border-radius: 999px;
  border: 1px solid var(--line); background: rgba(234, 244, 240, 0.06);
  position: relative; cursor: pointer;
  transition: background 0.18s, border-color 0.18s; flex: 0 0 auto;
}
.switch::after {
  content: ''; position: absolute; top: 2px; left: 2px;
  width: 15px; height: 15px; border-radius: 50%;
  background: var(--text-dim);
  transition: transform 0.18s var(--ease-out), background 0.18s;
}
.switch.on {
  background: color-mix(in srgb, var(--accent) 35%, transparent);
  border-color: color-mix(in srgb, var(--accent) 55%, transparent);
}
.switch.on::after { transform: translateX(17px); background: #fff; }
```

- [ ] **Step 4: Add reduced-motion guard**

```css
@media (prefers-reduced-motion: reduce) {
  .aurora-blob { animation: none; }
  .glass, .btn, .switch { transition: none; }
  .pulse-ring::after, .section-anim { animation: none; }
  * { transition-duration: 0.01ms !important; }
}
```

(`.aurora-blob` is defined in Task 3; declaring it here first is harmless.)

- [ ] **Step 5: Rebuild + commit**

Run: `python ui/runtime_src/build_runtime.py` → success.

```bash
git add ui/runtime_src/head_inner.html ui/index_runtime.html
git commit -m "feat(theme): glass + control primitive classes"
```

---

### Task 3: Aurora backdrop (CSS + DOM markup)

Replace the static `body::before` glow with markup-based drifting aurora blobs, grain, and vignette. Keep `#__bg-image-layer` working, layered above the aurora.

**Files:**
- Modify: `ui/runtime_src/head_inner.html:524-537` (delete `body::before`, add aurora CSS, bump `#__bg-image-layer` z-index)
- Modify: `ui/runtime_src/src/app.jsx` (insert `.bg-layer` markup at the root shell, near where `#__bg-image-layer` is rendered)

**Interfaces:**
- Consumes: `--accent`, `--accent-2`, `--good`, `--radius` tokens (Task 1).
- Produces: `.bg-layer`, `.aurora-blob` (+`.b2`/`.b3`), `.grain`, `.vignette` classes and the DOM node emitting them.

- [ ] **Step 1: Delete the `body::before` rule** (`head_inner.html:524-531`)

Remove the entire `/* Soft atmospheric backdrop ... */` + `body::before { ... }` block.

- [ ] **Step 2: Add aurora engine CSS** (where `body::before` was)

```css
.bg-layer { position: fixed; inset: 0; overflow: hidden; z-index: 0; pointer-events: none; }
.aurora-blob {
  position: absolute; width: 62vw; height: 62vw; border-radius: 50%;
  filter: blur(90px); opacity: 0.85; mix-blend-mode: screen;
  animation: drift 36s ease-in-out infinite alternate;
}
.aurora-blob.b2 { animation-duration: 47s; animation-delay: -12s; }
.aurora-blob.b3 { animation-duration: 58s; animation-delay: -29s; opacity: 0.6; }
@keyframes drift {
  0%   { transform: translate(-8%, -6%) scale(1) rotate(0deg); }
  50%  { transform: translate(10%, 8%) scale(1.18) rotate(24deg); }
  100% { transform: translate(-4%, 12%) scale(0.94) rotate(-18deg); }
}
.grain { position: absolute; inset: 0; pointer-events: none; opacity: 0.07; mix-blend-mode: overlay; }
.vignette {
  position: absolute; inset: 0; pointer-events: none;
  background: radial-gradient(120% 90% at 50% 20%, transparent 60%, rgba(3, 7, 9, 0.55) 100%);
}
```

- [ ] **Step 3: Bump `#__bg-image-layer` above the aurora** (`head_inner.html`, its rule ~533-537)

Add `z-index: 1;` to `#__bg-image-layer` (currently `z-index: 0`) so user background images render above `.bg-layer`.

- [ ] **Step 4: Add the aurora DOM markup in `app.jsx`**

Find the root shell render (near the `#__bg-image-layer` element / top-level app wrapper). Immediately before `#__bg-image-layer`, insert:

```jsx
<div className="bg-layer" aria-hidden="true">
  <div className="aurora-blob" style={{ background: "radial-gradient(circle, var(--accent), transparent 70%)", top: "-10%", left: "-5%" }} />
  <div className="aurora-blob b2" style={{ background: "radial-gradient(circle, var(--accent-2), transparent 70%)", top: "20%", right: "-10%" }} />
  <div className="aurora-blob b3" style={{ background: "radial-gradient(circle, var(--good), transparent 70%)", bottom: "-15%", left: "20%" }} />
  <div className="grain" />
  <div className="vignette" />
</div>
```

(If `#__bg-image-layer` is a raw DOM node in `index.html`/`head_inner.html` rather than JSX, place the `.bg-layer` node adjacent to it there instead — locate it first with `grep -rn "__bg-image-layer" ui/`.)

- [ ] **Step 5: Rebuild + launch + verify**

Run: `python ui/runtime_src/build_runtime.py` → success. `python app_web.py`.
Expected: three slow-drifting blurred mint/ember/green glows over the green-black base, subtle grain, darkened corners (vignette). Set a custom background image in theme settings → image still shows above the aurora.

- [ ] **Step 6: Commit**

```bash
git add ui/runtime_src/head_inner.html ui/runtime_src/src/app.jsx ui/index_runtime.html
git commit -m "feat(theme): drifting aurora backdrop replacing static glow"
```

---

### Task 4: Bundle the three fonts offline

Commit 6 WOFF2 files, embed them via a new `build_runtime.py` step, replace the old `@font-face` blocks, and add the offline assertion.

**Files:**
- Create: `ui/runtime_src/fonts/instrument-serif-400.woff2`, `schibsted-grotesk-400.woff2`, `schibsted-grotesk-500.woff2`, `schibsted-grotesk-600.woff2`, `fragment-mono-400.woff2`, `fragment-mono-400i.woff2`
- Modify: `ui/runtime_src/build_runtime.py` (new `embed_local_fonts()`, call in `main()`, offline assertion)
- Modify: `ui/runtime_src/head_inner.html:5-6` (drop preconnect), `:7-501` (replace `@font-face` blocks), `:520-522` (family mappings, add `--font-*` vars)

**Interfaces:**
- Produces: `@font-face` families `Instrument Serif`, `Schibsted Grotesk`, `Fragment Mono`; CSS vars `--font-display --font-ui --font-mono` (add to `:root`). Consumed by `.font-display`/`.font-mono`/body and the primitive classes.

- [ ] **Step 1: Download and commit the 6 WOFF2 files**

Fetch static (non-variable) weights from Google Fonts, Latin subset, into `ui/runtime_src/fonts/`:
- Instrument Serif: 400 normal
- Schibsted Grotesk: 400, 500, 600 normal
- Fragment Mono: 400 normal, 400 italic

If the build machine has network, a one-time helper is acceptable, but the files must be committed to the repo (offline builds must not refetch). Verify each file is a real WOFF2: `python -c "print(open('ui/runtime_src/fonts/instrument-serif-400.woff2','rb').read(4))"` → expect `b'wOF2'`.

- [ ] **Step 2: Add `embed_local_fonts()` to `build_runtime.py`** (after `resolve_fonts`, ~line 57)

```python
FONT_FILES = {
    "instrument-serif-400": "fonts/instrument-serif-400.woff2",
    "schibsted-grotesk-400": "fonts/schibsted-grotesk-400.woff2",
    "schibsted-grotesk-500": "fonts/schibsted-grotesk-500.woff2",
    "schibsted-grotesk-600": "fonts/schibsted-grotesk-600.woff2",
    "fragment-mono-400": "fonts/fragment-mono-400.woff2",
    "fragment-mono-400i": "fonts/fragment-mono-400i.woff2",
}

def embed_local_fonts(head):
    """Replace url("<local-font-key>") placeholders with data: URIs read
    directly from ui/runtime_src/fonts/ — no manifest/UUID, no network."""
    def repl(m):
        key = m.group(1)
        path = FONT_FILES.get(key)
        if not path:
            return m.group(0)
        raw = open(os.path.join(HERE, path), "rb").read()
        b64 = base64.b64encode(raw).decode("ascii")
        return f'url("data:font/woff2;base64,{b64}")'
    return re.sub(
        r'url\(["\']?(instrument-serif-[\w-]+|schibsted-grotesk-[\w-]+|fragment-mono-[\w-]+)["\']?\)',
        repl, head)
```

- [ ] **Step 3: Call it in `main()`** (after the `resolve_fonts` call, ~line 82)

```python
head = embed_local_fonts(head)
```

- [ ] **Step 4: Replace `@font-face` blocks + preconnect in `head_inner.html`**

Delete lines 5-6 (Google `<link rel="preconnect">` pair) and lines 7-501 (all Inter/JetBrains Mono/Rajdhani `@font-face` blocks). Insert these 6 blocks:

```css
@font-face { font-family: 'Instrument Serif'; font-style: normal; font-weight: 400; font-display: swap; src: url("instrument-serif-400") format('woff2'); }
@font-face { font-family: 'Schibsted Grotesk'; font-style: normal; font-weight: 400; font-display: swap; src: url("schibsted-grotesk-400") format('woff2'); }
@font-face { font-family: 'Schibsted Grotesk'; font-style: normal; font-weight: 500; font-display: swap; src: url("schibsted-grotesk-500") format('woff2'); }
@font-face { font-family: 'Schibsted Grotesk'; font-style: normal; font-weight: 600; font-display: swap; src: url("schibsted-grotesk-600") format('woff2'); }
@font-face { font-family: 'Fragment Mono'; font-style: normal; font-weight: 400; font-display: swap; src: url("fragment-mono-400") format('woff2'); }
@font-face { font-family: 'Fragment Mono'; font-style: italic; font-weight: 400; font-display: swap; src: url("fragment-mono-400i") format('woff2'); }
```

- [ ] **Step 5: Add `--font-*` vars + update family mappings**

In `:root` (Task 1 block), add:
```css
  --font-display: 'Instrument Serif', georgia, serif;
  --font-ui: 'Schibsted Grotesk', system-ui, sans-serif;
  --font-mono: 'Fragment Mono', ui-monospace, monospace;
```
Update the three mapping lines (formerly 520-522):
```css
html, body { background: var(--ink); color: var(--text); font-family: var(--font-ui); }
.font-display { font-family: var(--font-display); letter-spacing: 0.02em; }
.font-mono { font-family: var(--font-mono); }
```

- [ ] **Step 6: Add offline assertion in `main()`** (after writing `OUT`)

```python
banned = re.findall(r'(fonts\.googleapis\.com|fonts\.gstatic\.com|https?://)', html)
if banned:
    raise SystemExit(f"Offline check failed: network references present: {set(banned)}")
```

- [ ] **Step 7: Rebuild + verify offline + visual**

Run: `python ui/runtime_src/build_runtime.py`
Expected: no `SystemExit`; build succeeds. Redundant check: `grep -c "googleapis\|gstatic\|http://\|https://" ui/index_runtime.html` → `0`.
Launch `python app_web.py`: headings render in Instrument Serif (serif), body in Schibsted Grotesk, monospace/data in Fragment Mono.

- [ ] **Step 8: Commit**

```bash
git add ui/runtime_src/fonts/ ui/runtime_src/build_runtime.py ui/runtime_src/head_inner.html ui/index_runtime.html
git commit -m "feat(theme): bundle Instrument Serif / Schibsted Grotesk / Fragment Mono offline"
```

---

### Task 5: Abyssal theme-customizer presets

Replace palette + image presets and every violet fallback literal in `vendor/theme.jsx`. Keep the custom picker and gradient engine untouched.

**Files:**
- Modify: `ui/runtime_src/vendor/theme.jsx:7-20` (PALETTE_PRESETS), `:22-29` (IMAGE_PRESETS), `:47` (DEFAULT_THEME), `:56`, `:93`, `:172` (fallback literals); optionally `:181`, `:415` (slot seeds)

**Interfaces:**
- Consumes: `applyTheme()` internals (unchanged). Produces: new default theme so a fresh/legacy user lands on mint.

- [ ] **Step 1: Replace `PALETTE_PRESETS`** (lines 7-20)

```js
const PALETTE_PRESETS = [
  { name: "Lagoon",      colors: ["#6fe8c0"] },
  { name: "Ember",       colors: ["#f4b268"] },
  { name: "Tide",        colors: ["#6fe8c0", "#8ae0ff"] },
  { name: "Moss",        colors: ["#7be3b0", "#c9e07a"] },
  { name: "Aurora",      colors: ["#6fe8c0", "#f4b268"] },
  { name: "Mono Slate",  colors: ["#94a3b8"] },
];
```

- [ ] **Step 2: Replace `IMAGE_PRESETS`** (lines 22-29)

Four Nexus auroras as static SVG data-URIs (base gradient + two blob stops). Colors from `nexus/renderer/src/components/Background.tsx`:

```js
const IMAGE_PRESETS = [
  { name: "Ember",       url: "data:image/svg+xml;utf8," + encodeURIComponent(`<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 800 500'><defs><radialGradient id='g' cx='70%' cy='110%' r='120%'><stop offset='0' stop-color='%230c1a17'/><stop offset='0.55' stop-color='%23050b0e'/><stop offset='1' stop-color='%23000000'/></radialGradient><radialGradient id='b1' cx='40%' cy='40%' r='65%'><stop offset='0' stop-color='%23f5a952' stop-opacity='0.35'/><stop offset='1' stop-color='%23f5a952' stop-opacity='0'/></radialGradient><radialGradient id='b2' cx='60%' cy='60%' r='65%'><stop offset='0' stop-color='%231d5c52' stop-opacity='0.35'/><stop offset='1' stop-color='%231d5c52' stop-opacity='0'/></radialGradient></defs><rect width='800' height='500' fill='url(%23g)'/><rect width='800' height='500' fill='url(%23b1)'/><rect width='800' height='500' fill='url(%23b2)'/></svg>`) },
  { name: "Tide",        url: "data:image/svg+xml;utf8," + encodeURIComponent(`<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 800 500'><defs><radialGradient id='g' cx='30%' cy='110%' r='120%'><stop offset='0' stop-color='%2308131f'/><stop offset='0.55' stop-color='%2304080e'/><stop offset='1' stop-color='%23000000'/></radialGradient><radialGradient id='b1' cx='40%' cy='40%' r='65%'><stop offset='0' stop-color='%233aa6c9' stop-opacity='0.3'/><stop offset='1' stop-color='%233aa6c9' stop-opacity='0'/></radialGradient><radialGradient id='b2' cx='60%' cy='60%' r='65%'><stop offset='0' stop-color='%2314456e' stop-opacity='0.35'/><stop offset='1' stop-color='%2314456e' stop-opacity='0'/></radialGradient></defs><rect width='800' height='500' fill='url(%23g)'/><rect width='800' height='500' fill='url(%23b1)'/><rect width='800' height='500' fill='url(%23b2)'/></svg>`) },
  { name: "Moss",        url: "data:image/svg+xml;utf8," + encodeURIComponent(`<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 800 500'><defs><radialGradient id='g' cx='50%' cy='120%' r='120%'><stop offset='0' stop-color='%230b1510'/><stop offset='0.55' stop-color='%2305090a'/><stop offset='1' stop-color='%23000000'/></radialGradient><radialGradient id='b1' cx='40%' cy='40%' r='65%'><stop offset='0' stop-color='%236f9a3e' stop-opacity='0.3'/><stop offset='1' stop-color='%236f9a3e' stop-opacity='0'/></radialGradient><radialGradient id='b2' cx='60%' cy='60%' r='65%'><stop offset='0' stop-color='%231e4d36' stop-opacity='0.35'/><stop offset='1' stop-color='%231e4d36' stop-opacity='0'/></radialGradient></defs><rect width='800' height='500' fill='url(%23g)'/><rect width='800' height='500' fill='url(%23b1)'/><rect width='800' height='500' fill='url(%23b2)'/></svg>`) },
  { name: "Violet Hour", url: "data:image/svg+xml;utf8," + encodeURIComponent(`<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 800 500'><defs><radialGradient id='g' cx='80%' cy='120%' r='120%'><stop offset='0' stop-color='%23150f1d'/><stop offset='0.55' stop-color='%23070510'/><stop offset='1' stop-color='%23000000'/></radialGradient><radialGradient id='b1' cx='40%' cy='40%' r='65%'><stop offset='0' stop-color='%238a5cf6' stop-opacity='0.3'/><stop offset='1' stop-color='%238a5cf6' stop-opacity='0'/></radialGradient><radialGradient id='b2' cx='60%' cy='60%' r='65%'><stop offset='0' stop-color='%23d4638a' stop-opacity='0.3'/><stop offset='1' stop-color='%23d4638a' stop-opacity='0'/></radialGradient></defs><rect width='800' height='500' fill='url(%23g)'/><rect width='800' height='500' fill='url(%23b1)'/><rect width='800' height='500' fill='url(%23b2)'/></svg>`) },
];
```

- [ ] **Step 2b: Update comment/marker references to removed presets**

Grep the file for any lingering references to old preset names (`Obsidian`, `Crimson`, `Cosmic`, etc.) used elsewhere: `grep -n "Obsidian\|Crimson\|Cosmic\|Nebula" ui/runtime_src/vendor/theme.jsx`. Expected: none outside the arrays just replaced. If any, fix inline.

- [ ] **Step 3: Fix default + fallback literals**

- Line 47: `palette: ["#9d4edd"]` → `palette: ["#6fe8c0"]`
- Line 56 (`applyTheme` empty fallback): `["#9d4edd"]` → `["#6fe8c0"]`
- Line 93 (`migrate` push): `"#9d4edd"` → `"#6fe8c0"`
- Line 172 (draft fallback): `["#9d4edd"]` → `["#6fe8c0"]`

Verify none remain: `grep -n "9d4edd\|00f5ff" ui/runtime_src/vendor/theme.jsx`. Any remaining hit outside the seed arrays in Step 4 is a miss — fix it.

- [ ] **Step 4 (optional polish): Retint slot seeds** (lines 181, 415)

Swap old `["#00f5ff","#ff3d6e","#39ff8a"]` / `["#9d4edd","#00f5ff","#ff3d6e","#ffaa1f"]` seed arrays to Abyssal seeds, e.g. `["#f4b268","#8ae0ff","#c9e07a"]`. Cosmetic only (colors used when a user clicks "+"). Skip if time-constrained.

- [ ] **Step 5: Rebuild + verify**

Run: `python ui/runtime_src/build_runtime.py` → success. Launch: open theme customizer. Expected: palette presets read Lagoon/Ember/Tide/Moss/Aurora/Mono Slate; background presets show four Abyssal aurora thumbnails; default (fresh profile) is mint; custom color picker still works and recolors the whole UI.

- [ ] **Step 6: Commit**

```bash
git add ui/runtime_src/vendor/theme.jsx ui/index_runtime.html
git commit -m "feat(theme): Abyssal Lagoon palette + aurora presets, mint default"
```

---

### Task 6: JSX sweep — app.jsx shell + top nav + rail

First sweep pass. Establishes the utility→token mapping the remaining sweep tasks reuse.

**Files:**
- Modify: `ui/runtime_src/src/app.jsx` (chrome region — top nav, profile dropdown, connection pill, rail tab-group; roughly lines 1-330)

**Mapping table (reused by Tasks 7, 8a-8e, 9):**

| Old utility | New value |
|---|---|
| `text-slate-100` / `-200` | `text-[var(--text)]` |
| `text-slate-300` / `-400` | `text-[var(--text-dim)]` |
| `text-slate-500` / `-600` | `text-[var(--text-faint)]` |
| card triple `rounded-{xl,2xl} border border-white/[0.0X] bg-white/[0.0X]` | `className="glass"` (+ keep padding `p-4`/`p-5`) |
| segment/pill `border border-white/[0.0X] bg-white/[0.0X]` on `rounded-md` control | keep `rounded-md`, `border-[var(--line)]`, drop the white bg or use `bg-[color-mix(in_srgb,var(--text)_4%,transparent)]` |
| `border-white/[0.05\|0.06\|0.07]` | `border-[var(--line)]` |
| `border-white/10\|15\|20` (hover/active) | `border-[var(--line)]` default; emphasis → `hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)]` |
| `bg-black/30\|40` (inputs) | `.input` class background (or `bg-[rgba(5,11,14,0.5)]`) |
| panel `rounded-xl\|2xl` | drop — `.glass` carries `--radius` |
| `rounded-md\|lg\|sm\|full` on buttons/chips/dots | keep as-is |
| `.font-display`, `.font-mono` | no change (Task 4 redefined what they resolve to) |
| `bg-emerald-*`, `text-rose-*`, `hsl(...)`, status colors | leave — semantic, out of scope |

- [ ] **Step 1: Sweep the chrome region**

Apply the mapping table to `app.jsx` lines ~1-330 (nav bar, profile dropdown `menu-pop`, connection status pill, the rail tab-group at ~253-330). Convert card-triples to `.glass`, top-bar pills to `.chip`/segment treatment. Preserve every layout/transition/`hover:` non-color utility and all `style={{}}` blocks. Do NOT touch lines below the chrome (Task 7).

- [ ] **Step 2: Rebuild + verify**

Run: `python ui/runtime_src/build_runtime.py` → success. Launch. Open the profile dropdown; switch between the five nav tabs. Expected: nav chrome + dropdown read Abyssal (mint active states, green-tinted text, glass surfaces); no leftover slate-gray or white-tinted borders in the top bar; active tab uses mint.

- [ ] **Step 3: Commit**

```bash
git add ui/runtime_src/src/app.jsx ui/index_runtime.html
git commit -m "style(ui): sweep app shell + nav to Abyssal tokens"
```

---

### Task 7: JSX sweep — app.jsx panels

**Files:**
- Modify: `ui/runtime_src/src/app.jsx` (below the chrome, ~lines 330-end)

- [ ] **Step 1: Sweep remaining app.jsx**

Apply the Task 6 mapping table to the rest of `app.jsx` (panel containers, whatever wraps `sections.jsx`). Convert card-triples to `.glass`, inputs to `.input`, buttons to `.btn`. Preserve `style={{}}` and status colors.

- [ ] **Step 2: Rebuild + verify**

Build → success. Launch, exercise each panel `app.jsx` renders. Expected: panel surfaces are glass, no slate remnants; layout unchanged.

- [ ] **Step 3: Commit**

```bash
git add ui/runtime_src/src/app.jsx ui/index_runtime.html
git commit -m "style(ui): sweep app.jsx panels to Abyssal tokens"
```

---

### Tasks 8a-8e: JSX sweep — sections.jsx (five screens)

`sections.jsx` (~105KB, 171 `text-slate` + 76 `bg-white/` + 41 `border-white/` + 123 `rounded-*`) is swept one screen per task so each diff stays reviewable and independently testable. Use the Task 6 mapping table throughout. For each: locate the screen's component by name, sweep it, preserve `style={{}}` and semantic status colors, then rebuild + smoke-test that screen.

**Files (all):** Modify `ui/runtime_src/src/sections.jsx` (one screen's component per task).

- [ ] **Task 8a — Keymap screen.** Sweep. Verify: open Keymap, remap a key, confirm dropdown/panel/glass styling. Commit `style(ui): sweep Keymap screen`.
- [ ] **Task 8b — Lighting screen.** Sweep effect-selector cards → `.glass`. Verify: open Lighting, confirm cards + panels; confirm color pickers / swatches unaffected (device-color surfaces). Commit `style(ui): sweep Lighting screen`.
- [ ] **Task 8c — Actuation screen** (travel test / calibration, ~414-460). Sweep chrome only. Verify: run travel test live — slider/readout chrome restyled, live depth numbers still update. Commit `style(ui): sweep Actuation screen`.
- [ ] **Task 8d — SOCD screen.** Sweep toggles → `.switch`, chips → `.chip`. Verify: configure an SOCD pair. Commit `style(ui): sweep SOCD screen`.
- [ ] **Task 8e — Other/profile/backup screen** (profile list ~1244-1400, backup/import ~1550-1800, drop-zones ~800/1066). Sweep; restyle dashed drop-zone with `border-[var(--line)]` dashed. Verify: add/switch profile, import/export. Commit `style(ui): sweep Other screen`.

Each task's cycle: sweep → `python ui/runtime_src/build_runtime.py` (success) → `python app_web.py` smoke-test that screen → `git add ui/runtime_src/src/sections.jsx ui/index_runtime.html && git commit`.

---

### Task 9: JSX sweep — keyboard.jsx chrome only

**Highest-risk-per-line.** Read the whole file first. Sweep only className chrome; never touch device-telemetry inline styles.

**Files:**
- Modify: `ui/runtime_src/src/keyboard.jsx` (label text classes, key-border ternary literals, DevicePill)

**Do-NOT-touch lines (device telemetry — read and confirm before every edit):**
- `65-77`: `bg` computed from `ledColor` prop (per-key RGB gradient).
- `98`: `style={{ background: calibrated ? "..." : bg }}` — consumes dynamic `bg`.
- `153-160`: `hsl(${180 - actuationPoint*45} 80% 55%)` actuation-mode bar (data-driven).
- `167-168`: `text-rose-*`/`text-emerald-*` RT press/release readouts (status, not chrome).

**In-scope chrome:**
- `104-116`: key-border className ternary — swap literal utilities inside each branch (`border-white/[0.07]`→`border-[var(--line)]`, `border-white/15`→emphasis token) but **preserve the ternary structure exactly**.
- `136-142`, `162-169` (label classes only): `text-slate-200`→`text-[var(--text)]`, `text-slate-400`→`text-[var(--text-dim)]`.
- `200-208` DevicePill: already `var(--accent)`-based — no edit, just confirm it inherits mint.

- [ ] **Step 1: Read `keyboard.jsx` fully** (lines 1-208) and mark the do-not-touch lines above.

- [ ] **Step 2: Sweep chrome only** per the in-scope list. After editing, diff the file and confirm no `style={{}}` block or `ledColor`/`depth`/`actuationPoint`/`hsl(`/`rose`/`emerald` reference was altered.

- [ ] **Step 3: Rebuild + verify device truth**

Build → success. Launch, connect a device (or use the mock/preview), run a lighting mode + travel test side-by-side. Expected: per-key LED colors render exactly as before; only key borders and labels shifted to Abyssal tokens.

- [ ] **Step 4: Commit**

```bash
git add ui/runtime_src/src/keyboard.jsx ui/index_runtime.html
git commit -m "style(ui): sweep keyboard.jsx chrome (device colors untouched)"
```

---

### Task 10: Full verification pass

**Files:** none (verification + screenshots).

- [ ] **Step 1: Clean rebuild + offline assert**

Run: `python ui/runtime_src/build_runtime.py` → success, no `SystemExit`.
Run: `grep -c "googleapis\|gstatic\|http://\|https://" ui/index_runtime.html` → `0`.

- [ ] **Step 2: Walk every surface**

Launch `python app_web.py`. Visit all five sections (Keymap, Lighting, Actuation, SOCD, Other), the profile dropdown, and the theme customizer. Confirm: glass blur, drifting aurora, grain, vignette, and all three fonts render; no leftover slate-gray or violet anywhere in chrome.

- [ ] **Step 3: Exercise dynamic behavior**

Do a user recolor via the custom picker → whole UI accent follows. Connect device / run travel test → keyboard shows real per-key RGB. Toggle OS "reduce motion" → aurora/animation stops.

- [ ] **Step 4: WebView reality check (both engines if available)**

Confirm `backdrop-filter` glass + `color-mix()` render correctly in the actual WebView2 (Windows) build; if a Linux GTK-WebKit build is available, confirm the `@supports` fallback (solid tint) engages gracefully where blur is unsupported.

- [ ] **Step 5: Before/after screenshots + final commit**

Capture before/after screenshots into `docs/media/`. Commit any screenshot assets.

```bash
git add docs/media/
git commit -m "docs: Abyssal Lagoon re-skin before/after screenshots"
```

---

## Self-Review Notes

- **Spec coverage:** §Architecture (Tasks 1-2-3), §Color/accent (1,5), §Background (3), §Type (4), §Presets (5), §JSX sweep (6,7,8a-e,9), §Verification (10). All spec sections mapped.
- **Sequencing:** Tokens (1) → primitives (2) → aurora (3) → fonts (4) → presets (5) → sweep (6-9) → verify (10). Task 1 bundles the shim retarget so no intermediate commit looks broken. Fonts (4) land before the bulk sweep so `.font-*` resolve correctly during it.
- **Non-goals honored:** legacy Tk UI, device/HID/effects, layouts untouched; keyboard device colors fenced off in Task 9.
- **Risks tracked:** offline fonts (Task 4 assertion), backdrop-filter on GTK-WebKit (Task 2 `@supports`, Task 10 check), sweep breadth (split into 9 scoped, individually-testable passes).
