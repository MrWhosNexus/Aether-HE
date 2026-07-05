#!/usr/bin/env python3
"""Build ui/index_runtime.html — the native-shell UI with the HID bridge baked
into the React source (no DOM/CSS scraping).

Pipeline:
  1. Resolve @font-face url("<uuid>") in head_inner.html to self-contained
     data: URIs (pulled from the original bundle's manifest) and drop the
     Google Fonts <link>s so the page is fully offline.
  2. Babel-compile the JSX modules with the bundle's own @babel/standalone.
  3. Concatenate React + ReactDOM + Tailwind (verbatim) and the compiled
     modules into one standalone HTML, in dependency order.

Run:  venv-web/bin/python ui/runtime_src/build_runtime.py    (plain python3 is fine too)
"""
import base64
import gzip
import json
import os
import re
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
UI = os.path.dirname(HERE)
BUNDLE = os.path.join(UI, "index.html")
OUT = os.path.join(UI, "index_runtime.html")
BUILD = os.path.join(HERE, "build")
os.makedirs(BUILD, exist_ok=True)


def load_manifest():
    html = open(BUNDLE, encoding="utf-8", errors="replace").read()
    m = re.search(r'<script type="__bundler/manifest">(.*?)</script>', html, re.S)
    return json.loads(m.group(1).strip())


def asset_bytes(entry):
    raw = base64.b64decode(entry["data"])
    if entry.get("compressed"):
        raw = gzip.decompress(raw)
    return raw


def resolve_fonts(head, manifest):
    """Replace url("<uuid>") with data: URIs; strip Google Fonts links."""
    def repl(m):
        uuid = m.group(1)
        e = manifest.get(uuid)
        if not e:
            return m.group(0)
        mime = e.get("mime", "font/woff2")
        b64 = base64.b64encode(asset_bytes(e)).decode("ascii")
        return f'url("data:{mime};base64,{b64}")'

    head = re.sub(r'url\(["\']?([0-9a-f-]{36})["\']?\)', repl, head)
    # Drop network font links (preconnect / googleapis / gstatic).
    head = re.sub(r'<link\b[^>]*(fonts\.googleapis|fonts\.gstatic)[^>]*>', "", head)
    return head


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


def compile_jsx(manifest):
    babel = os.path.join(HERE, "vendor", "babel.js")
    jobs = [
        ("vendor/icons.jsx", "icons.js"),
        ("src/keyboard.jsx", "keyboard.js"),
        ("src/sections.jsx", "sections.js"),
        ("vendor/theme.jsx", "theme.js"),
        ("src/app.jsx", "app.js"),
    ]
    pairs = [[os.path.join(HERE, i), os.path.join(BUILD, o)] for i, o in jobs]
    print("Compiling JSX with bundled Babel…")
    subprocess.run(
        ["node", os.path.join(HERE, "compile.cjs"), babel, json.dumps(pairs)],
        check=True,
    )
    return [o for _, o in jobs]


def main():
    manifest = load_manifest()

    head = open(os.path.join(HERE, "head_inner.html"), encoding="utf-8").read()
    head = resolve_fonts(head, manifest)
    head = embed_local_fonts(head)

    compiled = compile_jsx(manifest)

    def vendor(name):
        return open(os.path.join(HERE, "vendor", name), encoding="utf-8", errors="replace").read()

    def built(name):
        return open(os.path.join(BUILD, name), encoding="utf-8").read()

    # Dependency order: React, ReactDOM, Tailwind, then design modules, then App.
    scripts = [
        ("react", vendor("react.js")),
        ("react-dom", vendor("react-dom.js")),
        ("tailwind", vendor("tailwind.js")),
        ("icons", built("icons.js")),
        ("keyboard", built("keyboard.js")),
        ("sections", built("sections.js")),
        ("theme", built("theme.js")),
        ("app", built("app.js")),
    ]
    # Capture any runtime JS error before the modules run, so app_web.py's
    # render-state probe can report it (window.__aetherErrors).
    err_collector = (
        '<script>window.__aetherErrors=[];'
        "window.addEventListener('error',e=>window.__aetherErrors.push(String((e&&e.message)||(e&&e.error)||e)));"
        "window.addEventListener('unhandledrejection',e=>window.__aetherErrors.push('promise: '+String(e&&e.reason)));"
        "</script>"
    )
    script_html = err_collector + "\n" + "\n".join(
        f'<script data-mod="{name}">\n{code}\n</script>' for name, code in scripts
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
{head}
</head>
<body class="min-h-screen overflow-x-auto" style="min-width: 1200px;">
<div class="bg-layer" aria-hidden="true">
  <div class="aurora-blob" style="background: radial-gradient(circle, var(--accent), transparent 70%); top: -10%; left: -5%;"></div>
  <div class="aurora-blob b2" style="background: radial-gradient(circle, var(--accent-2), transparent 70%); top: 20%; right: -10%;"></div>
  <div class="aurora-blob b3" style="background: radial-gradient(circle, var(--good), transparent 70%); bottom: -15%; left: 20%;"></div>
  <div class="grain"></div>
  <div class="vignette"></div>
</div>
<div id="__bg-image-layer"></div>
<div id="root" class="relative z-10"></div>
{script_html}
</body>
</html>
"""
    open(OUT, "w", encoding="utf-8").write(html)
    kb = len(html) / 1024
    print(f"\nWrote {OUT}  ({kb:.0f} KB)")

    # Offline assertion: no live network references for fonts/assets. Scoped to
    # actual resource-loading contexts (href=/src=/url(...) and the Google Fonts
    # domains) rather than any bare "http(s)://" substring — react.js/react-dom.js/
    # tailwind.js vendor bundles legitimately contain https://reactjs.org,
    # https://github.com, etc. inside warning-message strings and comments; those
    # are static text, never fetched, and predate this task.
    banned = set(re.findall(r'(fonts\.googleapis\.com|fonts\.gstatic\.com)', html))
    banned |= set(re.findall(r'(?:href|src)=["\']https?://[^"\']*', html))
    banned |= set(re.findall(r'url\(\s*["\']?https?://[^)"\']*', html))
    if banned:
        raise SystemExit(f"Offline check failed: network references present: {banned}")


if __name__ == "__main__":
    main()
