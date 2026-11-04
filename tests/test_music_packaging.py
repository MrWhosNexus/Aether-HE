"""Phase 7: the two new dependencies are declared for Windows only and
bundled by the PyInstaller spec. Text checks only: nothing is installed."""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as fh:
        return fh.read()


def test_requirements_add_numpy_and_soundcard_for_windows_only():
    req = _read("requirements.txt")
    assert re.search(r'^numpy>=1\.26;\s+sys_platform == "win32"$', req, re.M)
    assert re.search(r'^soundcard>=0\.4\.3;\s+sys_platform == "win32"$', req, re.M)


def test_pillow_pin_is_untouched():
    assert re.search(r'^Pillow>=13;    sys_platform == "win32"$', _read("requirements.txt"), re.M)


def test_spec_bundles_soundcard_data_and_lazy_imports():
    spec = _read("AetherHE.spec")
    assert 'collect_data_files("soundcard")' in spec
    for mod in ("numpy", "soundcard", "soundcard.mediafoundation", "_cffi_backend"):
        assert '"%s"' % mod in spec, mod
    excludes = spec[spec.index("excludes=["):spec.index("],", spec.index("excludes=["))]
    assert "numpy" not in excludes and "soundcard" not in excludes


def test_music_module_imports_neither_dependency_at_top_level():
    import ast
    tree = ast.parse(_read("music.py"))
    top = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            top |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            top.add(node.module.split(".")[0])
    assert not top & {"numpy", "soundcard"}
