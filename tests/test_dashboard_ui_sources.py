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
