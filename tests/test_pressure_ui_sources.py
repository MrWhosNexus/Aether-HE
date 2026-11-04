"""Phase 2 UI wiring guards. The lighting lists are hand-kept JS copies of the
engine's tables, so a new effect can be half-wired (engine knows it, UI never
offers it, or the other way round). These read the JSX sources as text."""
import os
import re

import effects
from test_pressure_effect import _engine

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, "ui", "runtime_src")


def _read(*parts):
    with open(os.path.join(SRC, *parts), encoding="utf-8") as fh:
        return fh.read()


def _set_ids(text, name):
    m = re.search(r"const %s = new Set\(\[(.*?)\]\)" % name, text, re.S)
    assert m, name
    return set(re.findall(r'"([a-z0-9_]+)"', m.group(1)))


def _list_ids(text, name):
    m = re.search(r"const %s = \[(.*?)\n\];" % name, text, re.S)
    assert m, name
    return set(re.findall(r'id: "([a-z0-9_]+)"', m.group(1)))


def test_host_fx_ids_equal_the_engine_generators():
    gens = set(_engine()._gens) - {"static", "calibrate"}
    assert _set_ids(_read("workspaces", "lighting.jsx"), "HOST_FX_IDS") == gens


def test_host_fx_fast_equals_the_press_reactive_set():
    assert _set_ids(_read("workspaces", "lighting.jsx"), "HOST_FX_FAST") \
        == set(effects.PRESS_REACTIVE)


def test_pressure_is_offered_in_every_effect_list():
    for rel in (("workspaces", "lighting.jsx"), ("src", "sections.jsx")):
        text = _read(*rel)
        assert "pressure" in _list_ids(text, "LIGHT_MODES"), rel
        assert "pressure" in _list_ids(text, "ZONE_MODES"), rel


def test_pressure_previews_like_the_other_press_reactive_effects():
    text = _read("workspaces", "lighting.jsx")
    assert re.search(r'pattern === "pressure"\) return "react"', text)
