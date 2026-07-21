"""The Flatpak manifest must package every module the app can import.

This bug class has already shipped twice. v0.3.0 crashed on Linux at boot with
ModuleNotFoundError because boards.py/data/tools were never copied into the
image, and 0.4.0 was one commit away from repeating it with drivers/ and
protocol_mini60.py.

It is invisible to every other test: on a dev checkout the modules are simply
*there*, so imports resolve and the suite is green. Only the packaged build is
missing them. And the protocol modules are the worst case — they are resolved
dynamically by name from the board registry, so no static import analysis of
app_web.py will ever mention protocol_sonix or protocol_sayo.

So this asserts against the two things that actually determine what gets
imported at runtime: the static import closure, and the registry's protocol
field.
"""
import ast
import os
import re

import pytest

import boards

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "flatpak", "io.github.mrwhosnexus.AetherHE.yml")

pytestmark = pytest.mark.skipif(
    not os.path.exists(MANIFEST), reason="flatpak manifest not present"
)


def _local_modules():
    py = {f[:-3] for f in os.listdir(ROOT) if f.endswith(".py")}
    pkgs = {
        d
        for d in os.listdir(ROOT)
        if os.path.isdir(os.path.join(ROOT, d))
        and os.path.exists(os.path.join(ROOT, d, "__init__.py"))
    }
    return py, pkgs


def _files_for(mod, pkgs):
    """Every .py file belonging to a module — the whole tree for a package."""
    if mod in pkgs:
        out = []
        for dirpath, _, names in os.walk(os.path.join(ROOT, mod)):
            out += [os.path.join(dirpath, n) for n in names if n.endswith(".py")]
        return out
    p = os.path.join(ROOT, mod + ".py")
    return [p] if os.path.exists(p) else []


def _top_level_imports(path):
    try:
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
    except (OSError, SyntaxError):
        return set()
    found = set()
    for node in ast.walk(tree):  # walk() reaches imports nested in functions too
        if isinstance(node, ast.Import):
            found |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module.split(".")[0])
    return found


def _import_closure(entry="app_web"):
    py, pkgs = _local_modules()
    seen, stack = set(), [entry]
    while stack:
        mod = stack.pop()
        if mod in seen:
            continue
        seen.add(mod)
        for path in _files_for(mod, pkgs):
            for imp in _top_level_imports(path):
                if (imp in py or imp in pkgs) and imp not in seen:
                    stack.append(imp)
    return {m for m in seen if m in py or m in pkgs}


def _packaged_names():
    """Module names in the manifest's `cp -r ... /app/share/aether/` command."""
    with open(MANIFEST, encoding="utf-8") as f:
        manifest = f.read()
    m = re.search(r"- cp -r (.*?)/app/share/aether/", manifest, re.S)
    assert m, "could not find the app-source cp command in the Flatpak manifest"
    names = re.split(r"\s+", m.group(1).replace("\n", " ").strip())
    return {n[:-3] if n.endswith(".py") else n for n in names if n}


def test_flatpak_packages_entire_import_closure():
    missing = sorted(_import_closure() - _packaged_names())
    assert not missing, (
        "these modules are imported by app_web.py but are NOT copied into the "
        f"Flatpak image, so the Linux build crashes at boot: {missing}"
    )


def test_flatpak_packages_every_registry_protocol_module():
    """Protocol modules are looked up by NAME from the registry, so they never
    appear in a static import graph. Each one still has to be in the image."""
    registry = boards.load_registry()
    needed = {
        p.protocol
        for p in registry.profiles
        if getattr(p, "protocol", None) and p.drivable
    }
    missing = sorted(needed - _packaged_names())
    assert not missing, (
        "the registry marks these protocol modules drivable but they are not "
        f"packaged into the Flatpak image: {missing}"
    )
