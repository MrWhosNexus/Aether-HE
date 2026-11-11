"""The built runtime's module ORDER is load-bearing, not cosmetic.

ui/index_runtime.html concatenates every compiled module into one file, so a
module that reads a `window.*` export at MODULE SCOPE only sees it if the
publishing module was concatenated earlier. Getting it wrong fails SILENTLY at
runtime: no exception, no console error, just a component wired to an object
nobody provides.

It already happened once: desktop.jsx's TopBar resolved the board context at
module scope as

    (window.AetherBoard && window.AetherBoard.BoardContext)
        || React.createContext(null)

but is concatenated BEFORE components/board-context.jsx publishes
window.AetherBoard, so it bound a private context nothing provides and the
top-bar chip showed "WIN 60 HE" for every board. desktop.jsx now ALSO looks the
context up at render time, which is what makes its early position safe; this
pins that, and the order for the modules that do read exports at module scope.
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RUNTIME = os.path.join(ROOT, "ui", "index_runtime.html")
DESKTOP = os.path.join(ROOT, "ui", "runtime_src", "src", "desktop.jsx")

#: (publisher marker, consumer marker, what breaks if the order flips)
ORDERED_PAIRS = [
    ("window.AetherSocd = {",
     "migrateState: migrateSocdState",
     "app.jsx destructures window.AetherSocd at module scope; undefined there "
     "is a TypeError and the whole UI stays blank"),
    ("window.AetherBoard = {",
     "window.AetherBoard || {}",
     "app.jsx reads the board context helpers at module scope"),
]


def _html():
    assert os.path.exists(RUNTIME), f"built runtime missing: {RUNTIME}"
    with open(RUNTIME, encoding="utf-8") as f:
        return f.read()


def test_runtime_publishes_before_it_is_consumed():
    html = _html()
    for publisher, consumer, breakage in ORDERED_PAIRS:
        pub = html.find(publisher)
        con = html.find(consumer)
        assert pub != -1, f"publisher marker not found in built runtime: {publisher!r}"
        assert con != -1, f"consumer marker not found in built runtime: {consumer!r}"
        assert pub < con, (
            f"module order regression in ui/index_runtime.html: {publisher!r} "
            f"(offset {pub}) must be concatenated BEFORE {consumer!r} "
            f"(offset {con}). Rebuild with ui/runtime_src/build_runtime.py and "
            f"check the `jobs` list order. Otherwise: {breakage}")


def test_desktop_topbar_resolves_the_board_context_at_render_time():
    """desktop.jsx is concatenated before board-context.jsx, so a module-scope
    lookup alone would bind a dead private context (the bug above)."""
    with open(DESKTOP, encoding="utf-8") as f:
        src = f.read()
    assert ("React.useContext((window.AetherBoard && window.AetherBoard.BoardContext) "
            "|| BOARD_CTX)") in src, (
        "desktop.jsx TopBar must look window.AetherBoard.BoardContext up at "
        "RENDER time; a module-scope lookup runs before the context exists")
