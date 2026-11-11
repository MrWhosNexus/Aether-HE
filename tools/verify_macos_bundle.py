#!/usr/bin/env python3
"""Verify a built AetherHE.app actually contains what it needs to boot.

Usage: python tools/verify_macos_bundle.py dist/AetherHE.app [--skip-selftest]

Structural checks are done here; the import-closure check is delegated to the
bundle itself (AETHER_SELFTEST=1), because only the frozen binary knows what its
own PYZ archive resolved. Asking the source tree would answer the wrong question
— that is precisely how the 0.3.0 Flatpak boot-crash passed a green suite.
"""
import os
import plistlib
import subprocess
import sys


def fail(msg):
    print(f"FAIL: {msg}", file=sys.stderr)
    return 1


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    skip_selftest = "--skip-selftest" in argv[1:]
    app = args[0] if args else "dist/AetherHE.app"
    errs = 0

    if not os.path.isdir(app):
        return fail(f"{app} does not exist")

    exe = os.path.join(app, "Contents", "MacOS", "AetherHE")
    if not os.path.isfile(exe) or not os.access(exe, os.X_OK):
        errs += fail(f"missing or non-executable {exe}")

    # --- Info.plist ---------------------------------------------------------
    plist_path = os.path.join(app, "Contents", "Info.plist")
    if not os.path.isfile(plist_path):
        errs += fail("missing Contents/Info.plist")
    else:
        with open(plist_path, "rb") as f:
            pl = plistlib.load(f)
        want = {
            "CFBundleIdentifier": "io.github.mrwhosnexus.AetherHE",
            "NSHighResolutionCapable": True,
        }
        for k, v in want.items():
            if pl.get(k) != v:
                errs += fail(f"Info.plist {k} == {pl.get(k)!r}, expected {v!r}")
        if not pl.get("CFBundleShortVersionString"):
            errs += fail("Info.plist has no CFBundleShortVersionString")
        # Keep the packaged version honest against version.py.
        try:
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            from version import __version__
            if pl.get("CFBundleShortVersionString") != __version__:
                errs += fail(f"Info.plist version {pl.get('CFBundleShortVersionString')!r} "
                             f"!= version.py {__version__!r}")
        except Exception as e:
            print(f"warn: could not compare against version.py ({e})")

    # --- data payload -------------------------------------------------------
    res = os.path.join(app, "Contents", "Resources")
    fw = os.path.join(app, "Contents", "Frameworks")
    for rel in ("ui/index_runtime.html", "data/board_registry.json"):
        if not any(os.path.exists(os.path.join(base, rel)) for base in (res, fw)):
            errs += fail(f"bundle is missing {rel} (looked in Resources/ and Frameworks/)")

    # --- signature ----------------------------------------------------------
    # --deep --strict is what updater.py runs on a staged update before it swaps
    # it in: a bundle that fails here could never be installed by the updater.
    r = subprocess.run(["codesign", "--verify", "--deep", "--strict", app],
                       capture_output=True)
    if r.returncode != 0:
        errs += fail("codesign --verify failed: "
                     + (r.stderr or b"").decode(errors="replace").strip())

    # --- the real one: make the frozen app prove its own import closure -----
    # The selftest hook lives in app_web.py. Without it the binary ignores
    # AETHER_SELFTEST and simply opens the GUI, which would hang this script
    # until the timeout — so check the source for the hook before running.
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        with open(os.path.join(root, "app_web.py"), encoding="utf-8") as f:
            has_hook = "AETHER_SELFTEST" in f.read()
    except OSError:
        has_hook = True          # verifying a bundle away from the source tree
    if skip_selftest:
        print("warn: --skip-selftest: the bundle's import closure was NOT checked")
    elif not has_hook:
        errs += fail("app_web.py has no AETHER_SELFTEST hook, so the bundle cannot "
                     "prove its import closure (not launching the GUI to find out)")
    elif os.path.isfile(exe):
        env = dict(os.environ, AETHER_SELFTEST="1")
        r = subprocess.run([exe], capture_output=True, env=env, timeout=120)
        out = ((r.stdout or b"") + (r.stderr or b"")).decode(errors="replace").strip()
        if r.returncode != 0 or "SELFTEST OK" not in out:
            errs += fail(f"bundle selftest failed (exit {r.returncode}):\n{out}")
        else:
            print(out)

    if errs:
        print(f"\n{errs} problem(s) found in {app}", file=sys.stderr)
        return 1
    print(f"OK: {app} verified")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
