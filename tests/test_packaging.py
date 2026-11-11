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
import subprocess

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


def _registry_protocol_modules():
    registry = boards.load_registry()
    return {
        p.protocol
        for p in registry.profiles
        if getattr(p, "protocol", None) and p.drivable
    }


def test_flatpak_packages_every_registry_protocol_module():
    """Protocol modules are looked up by NAME from the registry, so they never
    appear in a static import graph. Each one still has to be in the image."""
    missing = sorted(_registry_protocol_modules() - _packaged_names())
    assert not missing, (
        "the registry marks these protocol modules drivable but they are not "
        f"packaged into the Flatpak image: {missing}"
    )


# --------------------------------------------------------- PyInstaller specs
# Same bug, different packager. PyInstaller bundles what its static analysis can
# see, and the registry's protocol modules are reached by string — grep confirms
# NOTHING in the tree imports protocol_sonix or protocol_sayo, so neither would
# be frozen in unless the spec names it in `hiddenimports`. The Flatpak manifest
# has always copied them; the specs must match, or the .exe/.app silently loses
# a board the Linux build supports.
SPECS = {
    "windows": os.path.join(ROOT, "AetherHE.spec"),
    "macos": os.path.join(ROOT, "AetherHE-macos.spec"),
}


def _spec_hiddenimports(path):
    """String literals in the spec's `hidden = [...]` list."""
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign)
                and any(getattr(t, "id", None) == "hidden" for t in node.targets)
                and isinstance(node.value, ast.List)):
            return {e.value for e in node.value.elts
                    if isinstance(e, ast.Constant) and isinstance(e.value, str)}
    return set()


@pytest.mark.parametrize("platform_name", sorted(SPECS))
def test_pyinstaller_spec_declares_registry_protocol_modules(platform_name):
    spec = SPECS[platform_name]
    if not os.path.exists(spec):
        pytest.skip(f"{spec} not present")
    missing = sorted(_registry_protocol_modules() - _spec_hiddenimports(spec))
    assert not missing, (
        f"the registry marks these protocol modules drivable, but the "
        f"{platform_name} PyInstaller spec does not list them in hiddenimports, "
        f"so they will not be frozen into the build: {missing}"
    )


def test_macos_spec_excludes_windows_and_linux_gamepad_backends():
    """vgamepad/evdev cannot work on macOS. Bundling them would make the
    'no backend' path look like a bug report instead of a platform gate."""
    spec = SPECS["macos"]
    if not os.path.exists(spec):
        pytest.skip("macOS spec not present")
    with open(spec, encoding="utf-8") as f:
        src = f.read()
    tree = ast.parse(src)
    excludes = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg == "excludes":
            excludes |= {e.value for e in node.value.elts
                         if isinstance(e, ast.Constant) and isinstance(e.value, str)}
    assert {"vgamepad", "evdev"} <= excludes, (
        f"macOS spec must exclude vgamepad and evdev; excludes={sorted(excludes)}")

    # The ViGEmBus installer is a Windows kernel driver — 3 MB of nonsense in a
    # .app, and a misleading one. Check the `datas` LIST, not the file text: the
    # spec legitimately names ViGEmBus in a comment explaining its absence, and
    # a substring search over the source would fail on that comment.
    datas = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign)
                and any(getattr(t, "id", None) == "datas" for t in node.targets)
                and isinstance(node.value, ast.List)):
            for elt in node.value.elts:
                if isinstance(elt, ast.Tuple):
                    datas |= {e.value for e in elt.elts
                              if isinstance(e, ast.Constant) and isinstance(e.value, str)}
    assert not any("ViGEmBus" in d or "vendor" in d for d in datas), (
        f"macOS spec must not bundle the Windows ViGEmBus payload; datas={sorted(datas)}")


# ----------------------------------------------- executable bits
# Every script the docs tell a user to invoke as ./script must be committed
# executable. git tracks the mode, and `chmod +x` in a working tree does NOT
# record it — the macOS build scripts shipped as 100644 and `./build_macos.sh`
# failed with "permission denied" on a fresh clone.
EXECUTABLES = [
    "run.sh",
    "run.command",
    "capture.sh",
    "build_macos.sh",
    "tools/make_icns.sh",
    "tools/verify_macos_bundle.py",
]


@pytest.mark.parametrize("rel", EXECUTABLES)
def test_scripts_are_committed_executable(rel):
    path = os.path.join(ROOT, rel)
    if not os.path.exists(path):
        pytest.skip(f"{rel} not present")
    mode = subprocess.run(["git", "ls-files", "-s", rel],
                          cwd=ROOT, capture_output=True, text=True).stdout.split()
    if not mode:
        pytest.skip(f"{rel} not tracked by git")
    assert mode[0] == "100755", (
        f"{rel} is committed as {mode[0]}; a fresh clone cannot run it. "
        f"Fix with: git update-index --chmod=+x {rel}")


# ------------------------------------------------ release tag == version.py --
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "release.yml")
CHECK_TAG = os.path.join(ROOT, "tools", "check_release_tag.py")


def _run_check(tag=None, env_tag=None):
    import sys
    env = dict(os.environ)
    env.pop("RELEASE_TAG", None)
    if env_tag is not None:
        env["RELEASE_TAG"] = env_tag
    argv = [sys.executable, CHECK_TAG] + ([tag] if tag is not None else [])
    return subprocess.run(argv, capture_output=True, text=True, env=env)


def test_release_tag_check_passes_only_for_the_exact_version():
    import version
    v = version.__version__
    assert _run_check(f"v{v}").returncode == 0
    assert _run_check(env_tag=f"v{v}").returncode == 0, "CI passes it as $RELEASE_TAG"
    for bad in (v, f"v{v}.1", f"v{v}-rc1", "v0.0.0", f"V{v}", f" v{v}x"):
        r = _run_check(env_tag=bad)
        assert r.returncode == 1, f"{bad!r} was accepted for version {v}"
        assert "::error::" in r.stdout and v in r.stdout


def test_release_tag_check_lets_a_build_only_run_through():
    """Manual dispatch without a tag publishes nothing: nothing to compare."""
    assert _run_check(env_tag="").returncode == 0
    assert _run_check().returncode == 0


def test_release_workflow_gates_every_build_on_the_tag_check():
    """A tag that is not v<version.py> must fail BEFORE a build or a publish:
    the Mac updater refuses a zip whose bundle version is not the release tag,
    so such a release is one no Mac can ever install."""
    y = open(WORKFLOW, encoding="utf-8").read()
    expr = ("RELEASE_TAG: ${{ inputs.tag || (startsWith(github.ref, 'refs/tags/') "
            "&& github.ref_name) || '' }}")
    assert y.count(expr) == 2, "the gate job and the macOS job both take the tag"
    assert "${{" not in "".join(l for l in y.splitlines() if "check_release_tag" in l), \
        "the tag must reach the script through the environment, not interpolation"
    jobs = y.split("\njobs:\n", 1)[1]
    assert jobs.lstrip().splitlines()[0].startswith("#") and "\n  version:\n" in jobs
    for job in ("windows", "linux", "macos"):
        body = jobs.split(f"\n  {job}:\n", 1)[1]
        assert body.lstrip().startswith("needs: version"), f"{job} does not wait for the gate"
    mac = jobs.split("\n  macos:\n", 1)[1].split("\n  release:\n", 1)[0]
    assert mac.index("check_release_tag.py") < mac.index("Run tests") \
        < mac.index("build_macos.sh"), "the macOS job must check before it builds"
    rel = jobs.split("\n  release:\n", 1)[1]
    assert "needs: [version, windows, linux, macos]" in rel
    assert "needs.version.result == 'success'" in rel


def test_build_script_does_not_overclaim_tcc_persistence():
    """An ad-hoc signature's designated requirement is the cdhash, so a grant
    may reset per update; only the no-grant vendor interface was measured."""
    s = open(os.path.join(ROOT, "build_macos.sh"), encoding="utf-8").read()
    assert "so the grant sticks" not in s
    assert "cdhash" in s and "MAY be reset" in s
    assert "0xFF1B" in s and "WITHOUT any grant" in s
