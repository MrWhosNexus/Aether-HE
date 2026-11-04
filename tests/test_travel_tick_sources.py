"""Phase 2 Travel Test polish: each key draws its actuation point. The Key
component is JSX, so these pin the wiring in the sources and the built bundle."""
import os
import re

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, "ui", "runtime_src")


def _read(*parts):
    with open(os.path.join(SRC, *parts), encoding="utf-8") as fh:
        return fh.read()


def test_fill_and_tick_share_one_travel_scale():
    kb = _read("src", "keyboard.jsx")
    assert re.search(r"const TRAVEL_SCALE_MM = 4;", kb)
    assert "Math.min(1, depth / TRAVEL_SCALE_MM)" in kb
    assert "(mm / TRAVEL_SCALE_MM) * 100" in kb
    assert "depth / 4)" not in kb          # the old literal must not creep back


def test_tick_is_per_key_and_only_in_actuation_mode():
    kb = _read("src", "keyboard.jsx")
    m = re.search(r'\{mode === "actuation" && actuationPoint > 0 && \(\s*'
                  r"<span aria-hidden data-act-tick.*?bottom: tickPct\(actuationPoint\)", kb, re.S)
    assert m, "tick must be gated on actuation mode and use the key's own actuationPoint"
    # per-key value reaches Key from perKeyOverride (the firmware read-back)
    assert "actuationPoint={override.actuation ?? actuationPoint}" in kb


def test_actuation_header_explains_the_line():
    assert "line = actuation point" in _read("workspaces", "actuation.jsx")


def test_built_bundle_contains_the_tick():
    with open(os.path.join(SRC, "build", "keyboard.js"), encoding="utf-8") as fh:
        built = fh.read()
    assert "data-act-tick" in built and "TRAVEL_SCALE_MM" in built
