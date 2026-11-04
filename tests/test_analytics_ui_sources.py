"""Phase 4 UI wiring (source checks; the UI has no JS test runner): the
Analytics workspace is registered and gated on keyStats, talks to the bridge
through ctx.apiCall only, applies suggestions through app.jsx's
writeActuation (set_trigger_codes + verify_actuation), and exports the
pieces the Phase 5 dashboard reuses."""
import os
import re
import shutil
import subprocess

import pytest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, "ui", "runtime_src")


def _read(*parts):
    with open(os.path.join(SRC, *parts), encoding="utf-8") as fh:
        return fh.read()


WS = _read("workspaces", "analytics.jsx")


def test_workspace_exports_widgets_and_reusable_pieces():
    assert "window.AetherWorkspaces.ANALYTICS_WIDGETS = ANALYTICS_WIDGETS" in WS
    for wid in ('id: "heatmap"', 'id: "overview"', 'id: "daily"', 'id: "tune"'):
        assert wid in WS
    m = re.search(r"window\.AetherAnalytics = \{(.*?)\};", WS, re.S)
    assert m, "window.AetherAnalytics export missing"
    names = {n.strip() for n in m.group(1).replace("\n", " ").split(",") if n.strip()}
    assert {"store", "useAnalytics", "refreshAnalytics", "refreshTune",
            "heatColor", "heatLedMap", "topSuggestions", "HeatmapBoard",
            "DailyBars", "SuggestionCard", "SuggestionList",
            "applySuggestion"} <= names


def test_workspace_uses_only_the_two_read_bridges():
    code = re.sub(r"/\*.*?\*/", "", WS, flags=re.S)    # comments may name them
    calls = set(re.findall(r'call\("([a-z_]+)"', code))
    assert calls == {"get_analytics", "get_tune_suggestions"}
    assert "pywebview" not in code                  # ctx.apiCall only
    assert "set_trigger_codes" not in code          # writes go through ctx


def test_no_raw_html_sinks_and_suggestions_only_copy():
    assert "dangerouslySetInnerHTML" not in WS and "innerHTML" not in WS
    assert "nothing is written until you click Apply" in WS


def test_built_workspace_is_current():
    built = os.path.join(SRC, "build", "ws_analytics.js")
    with open(built, encoding="utf-8") as fh:
        code = fh.read()
    assert "ANALYTICS_WIDGETS" in code and "AetherAnalytics" in code
    with open(os.path.join(HERE, "ui", "index_runtime.html"), encoding="utf-8") as fh:
        html = fh.read()
    assert "window.AetherAnalytics" in html


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_built_workspace_parses():
    built = os.path.join(SRC, "build", "ws_analytics.js")
    subprocess.run(["node", "--check", built], check=True)


# ---- Task 6: app.jsx / desktop.jsx wiring --------------------------------
APP = _read("src", "app.jsx")
DESK = _read("src", "desktop.jsx")


def test_apply_goes_through_the_normal_actuation_path():
    assert "ctx.applyTuneSuggestion(" in WS
    body = APP[APP.index("const writeActuation"):APP.index("const applyDeadband")]
    assert 'apiCall("set_trigger_codes", codes, travel' in body
    assert 'apiCall("verify_actuation", codes)' in body
    assert "const applyActuation = () =>\n    writeActuation(" in body
    assert "writeActuation(s.codes, s.suggested_mm, s.mode || 0" in body
    assert "writeActuation, applyTuneSuggestion," in APP


def test_tab_is_registered_and_gated_on_key_stats():
    assert 'analytics: wsArr("ANALYTICS_WIDGETS", "Analytics")' in APP
    assert 'const SECTION_CAPS = { macros: "macros", analytics: "keyStats" };' in APP
    assert '{ id: "analytics", label: "Analytics", icon: IActivity }' in DESK
    assert "IActivity = I.IActivity" in DESK


def test_built_page_carries_the_gated_tab():
    with open(os.path.join(HERE, "ui", "index_runtime.html"), encoding="utf-8") as fh:
        html = fh.read()
    assert 'analytics: "keyStats"' in html
    assert "applyTuneSuggestion" in html
