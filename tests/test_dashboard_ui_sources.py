"""Phase 5 Dashboard (source checks; the UI has no JS test runner, so the
pure helpers run in node when it is installed). The Dashboard is the landing
tab, reuses the shared stores and ctx actions (no second polling loop), holds
the live-depth stream only while shown, and talks to the bridge directly only
for Phase 6's get_overlays / set_overlay."""
import json
import os
import re
import shutil
import subprocess

import pytest

import app_web

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, "ui", "runtime_src")
NODE = shutil.which("node")


def _read(*parts):
    with open(os.path.join(SRC, *parts), encoding="utf-8") as fh:
        return fh.read()


def _code(text):
    """Source without block and whole-line // comments (they may name things)."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", text)


# ---- Task 1: shared pieces the dashboard reuses ---------------------------
KB = _read("src", "keyboard.jsx")
AN = _read("workspaces", "analytics.jsx")


def test_keyboard_panel_footer_is_optional():
    assert "  showFooter = true,\n}) => {" in KB
    assert "{showFooter && (" in KB


def test_suggestion_list_has_a_compact_variant():
    assert "const SuggestionList = ({ ctx, limit, compact }) =>" in AN
    assert "compact={!!compact}" in AN
    assert "title={s.detail}" in AN
    assert "{!compact && (" in AN


# ---- Task 2: app.jsx plumbing ----------------------------------------------
APP = _read("src", "app.jsx")


def test_live_view_holds_the_one_travel_test_stream():
    assert "const liveWanted = travelTest || liveView;" in APP
    assert "if (!connected || !liveWanted) {" in APP
    assert "}, [connected, liveWanted]);" in APP
    assert APP.count('apiCall("open_analog_codes"') == 1     # one loop, one owner
    assert APP.count('apiCall("read_live")') == 1
    assert "liveView, setLiveView," in APP


def test_games_view_comes_from_the_existing_poll():
    assert APP.count('apiCall("games_status")') == 1
    assert "setGamesInfo(prev => sameJson(prev, view) ? prev : view);" in APP
    assert "games: gamesInfo," in APP


# ---- Task 3: workspaces/dashboard.jsx --------------------------------------
DASH = _read("workspaces", "dashboard.jsx")


def test_dashboard_exports_the_page_and_helpers():
    assert "window.AetherWorkspaces.DASHBOARD_PAGE = DashboardPage;" in DASH
    m = re.search(r"window\.AetherDashboard = \{(.*?)\};", DASH, re.S)
    assert m, "window.AetherDashboard export missing"
    names = {n.strip() for n in m.group(1).replace("\n", " ").split(",") if n.strip()}
    assert names == {"HERO_MODES", "OVERLAY_POLL_MS", "heroModesFor", "pickHeroMode",
                     "perKeyOverrideOf", "actuationSummary", "todayFrom", "gameLine",
                     "overlayView"}


def test_dashboard_calls_only_the_phase6_bridges():
    code = _code(DASH)
    assert set(re.findall(r'apiCall\("([a-z_]+)"', code)) == {"get_overlays", "set_overlay"}
    assert "pywebview" not in code
    for name in ("set_trigger_codes", "verify_actuation", "start_multicolor", "set_light",
                 "open_analog", "close_analog", "read_live", "games_status",
                 "get_analytics", "get_tune_suggestions"):
        assert name not in code, name


def test_dashboard_reuses_the_shared_stores_and_ctx_actions():
    code = _code(DASH)
    for needle in ("window.AetherAnalytics.useAnalytics",
                   "<An.SuggestionList ctx={ctx} limit={3} compact/>",
                   "An.heatLedMap(keys)", "<An.DailyBars daily={a.daily} height={64}/>",
                   "An.setDays(1)", "ctx.setLiveView(true);",
                   "return () => ctx.setLiveView(false);", "ctx.setPattern(",
                   "L.modeGridFor(", "ctx.switchProfile(p.id)", "ctx.togglePair",
                   "showFooter={false}"):
        assert needle in code, needle


def test_overlay_tile_polls_only_while_supported_and_cleans_up():
    body = DASH[DASH.index("function OverlaysPanel"):DASH.index("/* ===== the page")]
    assert "if (alive && v) timer = setInterval(" in body
    assert "return () => { alive = false; if (timer) clearInterval(timer); };" in body
    assert "if (!list || !list.length) return null;" in body


def test_no_raw_html_sinks_and_honest_copy():
    assert "dangerouslySetInnerHTML" not in DASH and "innerHTML" not in DASH
    assert "Suggestions only: nothing is written until you click Apply." in DASH
    assert "key statistics on · counters only" in DASH


def test_layout_fits_the_fixed_design_canvas():
    # app.jsx zooms a 1480 x 900 canvas to the window: 900 px tall = no
    # scrolling at the 1160 x 800 minimum (verified in a browser).
    for cls in ('"px-6 pt-5 pb-5 h-[900px] flex flex-col gap-3"',
                "grid-cols-[minmax(0,1fr)_392px] gap-3.5 h-[420px]",
                "grid-cols-[340px_minmax(0,1fr)_392px] gap-3.5 flex-1 min-h-0"):
        assert cls in DASH, cls


def test_built_dashboard_is_current():
    with open(os.path.join(SRC, "build", "ws_dashboard.js"), encoding="utf-8") as fh:
        built = fh.read()
    assert "DASHBOARD_PAGE" in built and "AetherDashboard" in built
    with open(os.path.join(HERE, "ui", "index_runtime.html"), encoding="utf-8") as fh:
        assert "window.AetherDashboard" in fh.read()


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_built_dashboard_parses():
    subprocess.run([NODE, "--check", os.path.join(SRC, "build", "ws_dashboard.js")], check=True)


HARNESS = r"""
const fs = require("fs");
global.window = { AetherKeyboard: { KB_ROWS: [[["Q", 4, "Q"], ["W", 4, "W"]]], KeyboardPanel() {} } };
global.React = { useState() {}, useEffect() {}, useMemo() {}, createElement() {} };
global.localStorage = { getItem() { return null; }, setItem() {} };
// Runs OUR built ws_dashboard.js (a repo file) with stub globals.
require("vm").runInThisContext(fs.readFileSync(process.argv[2], "utf8"), { filename: process.argv[2] });
const D = window.AetherDashboard;
const profiles = [{ id: "p1", name: "Default" }, { id: "p2", name: "FPS" }];
console.log(JSON.stringify({
  modesAll: D.heroModesFor(() => true),
  modesNoStats: D.heroModesFor(n => n !== "keyStats"),
  modesNone: D.heroModesFor(() => false),
  pick: [D.pickHeroMode(["heatmap", "live"], "live"), D.pickHeroMode(["live"], "heatmap"),
         D.pickHeroMode([], "live")],
  sum: D.actuationSummary({ Q: 0.8, W: 0.8, E: 0.45, R: 0.6, T: 0.3 },
                          { Q: { mode: 13 }, W: { mode: 0 } }, 61),
  uniform: D.actuationSummary({ Q: 0.8, W: 0.8 }, {}, 61),
  sumNone: D.actuationSummary({}, {}, 61),
  override: D.perKeyOverrideOf({ Q: 0.8 }, { Q: { mode: 13, travel_mm: 0.8, rt_press_mm: 0.15, rt_release_mm: 0.2 },
                                           W: { mode: 0, travel_mm: 1.2, rt_press_mm: 0.1, rt_release_mm: 0.1 } }),
  today: D.todayFrom({ daily: [{ date: "2026-11-03", presses: 9, shallow: 0, bottom: 0 },
                               { date: "2026-11-04", presses: 90, shallow: 10, bottom: 25 }] }),
  todayNone: D.todayFrom({ daily: [] }),
  games: [
    D.gameLine(null, profiles),
    D.gameLine({ available: false }, profiles),
    D.gameLine({ available: true, autoSwitch: true, active: { id: "g", name: "VALORANT", profileId: "p2" }, detected: [] }, profiles),
    D.gameLine({ available: true, autoSwitch: true, active: null, foreground: "g",
                 detected: [{ id: "g", name: "VALORANT", mapped: false }] }, profiles),
    D.gameLine({ available: true, autoSwitch: false, active: null, detected: [] }, profiles),
  ],
  overlays: [D.overlayView({ ok: false, error: "no bridge" }),
             D.overlayView({ ok: true, supported: false, overlays: [{ id: "cpu" }] }),
             D.overlayView({ ok: true, overlays: [{ id: "cpu", on: true }, null, { label: "x" }] })],
}));
"""


@pytest.fixture(scope="module")
def helpers(tmp_path_factory):
    if NODE is None:
        pytest.skip("node not installed")
    h = tmp_path_factory.mktemp("dash") / "harness.cjs"
    h.write_text(HARNESS, encoding="utf-8")
    out = subprocess.run([NODE, str(h), os.path.join(SRC, "build", "ws_dashboard.js")],
                         check=True, capture_output=True, text=True, encoding="utf-8")
    return json.loads(out.stdout)


def test_hero_modes_follow_the_board_capabilities(helpers):
    assert helpers["modesAll"] == ["heatmap", "live", "actuation"]
    assert helpers["modesNoStats"] == ["live", "actuation"]
    assert helpers["modesNone"] == []
    assert helpers["pick"] == ["live", "live", None]


def test_actuation_summary_reads_the_firmware_values(helpers):
    s = helpers["sum"]
    assert (s["keys"], s["total"], s["min"], s["max"]) == (5, 61, 0.3, 0.8)
    assert s["uniform"] is False and s["distinct"] == 4 and s["rt"] == 1
    assert s["groups"][0] == {"mm": 0.8, "n": 2} and len(s["groups"]) == 3
    assert helpers["uniform"]["uniform"] is True and helpers["uniform"]["keys"] == 2
    assert helpers["sumNone"] is None
    o = helpers["override"]
    assert o["Q"] == {"actuation": 0.8, "rtPress": 0.15, "rtRelease": 0.2}
    assert o["W"] == {"actuation": 1.2, "rtPress": 0, "rtRelease": 0}


def test_today_is_the_last_daily_row(helpers):
    assert helpers["today"] == {"date": "2026-11-04", "presses": 90, "shallow": 10,
                                "bottom": 25, "bottom_pct": 25}
    assert helpers["todayNone"] is None


def test_game_line_states(helpers):
    texts = [(g["tone"], g["text"]) for g in helpers["games"]]
    assert texts == [("dim", "Checking for games…"), ("dim", "Game detection unavailable"),
                     ("accent", "VALORANT"), ("text", "VALORANT"), ("dim", "No game running")]
    assert helpers["games"][2]["sub"] == "playing · profile FPS"
    assert helpers["games"][3]["sub"] == "running · not mapped to a profile"
    assert helpers["games"][4]["sub"] == "auto-switch off"


def test_overlay_tile_needs_a_supported_bridge(helpers):
    none, unsupported, ok = helpers["overlays"]
    assert none is None and unsupported is None
    assert ok == [{"id": "cpu", "on": True}]
