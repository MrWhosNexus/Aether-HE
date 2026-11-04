"""Phase 3 UI wiring guards (JSX is not executed in tests): the app polls
the game decision and applies it through the bridge, the Settings "Games"
widget exists, and untrusted game names never reach a raw-HTML sink."""
import os
import re

import app_web

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, "ui", "runtime_src")


def _read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as fh:
        return fh.read()


def test_app_polls_games_status_and_applies_through_the_bridge():
    app = _read(SRC, "src", "app.jsx")
    assert 'apiCall("games_status")' in app
    assert 'apiCall("apply_profile_to_board", profileBoardSpec(p.state))' in app
    assert re.search(r'apiCall\("games_sync", \{\s*activeProfile: active, handledSeq: seq,', app)
    assert "sw.seq > gameSeqRef.current" in app
    assert "switchProfileRef.current(p.id)" in app          # same path as the profile menu
    assert "[connected, actReadNonce]" in app                # re-read after a write


def test_profile_board_spec_and_socd_pairs_are_shared():
    app = _read(SRC, "src", "app.jsx")
    assert "const socdPairsFrom = (rows) =>" in app
    assert "const pairs = socdPairsFrom(profiles);" in app   # SOCD tab uses the same mapping
    spec = app[app.index("const profileBoardSpec"):app.index("// Keymap target label")]
    for field in ("actuation:", "rtEnabled:", "rtPress:", "rtRelease:", "socd:"):
        assert field in spec, field


def test_every_bridge_method_the_ui_calls_exists():
    ui = _read(SRC, "src", "app.jsx") + _read(SRC, "workspaces", "settings.jsx")
    for name in ("games_status", "games_sync", "apply_profile_to_board", "list_running_games",
                 "set_game_profile", "add_custom_game", "refresh_detectable",
                 "set_games_auto_switch"):
        assert name in ui, name
        assert callable(getattr(app_web.Api, name)), name


def test_settings_has_a_games_widget():
    st = _read(SRC, "workspaces", "settings.jsx")
    assert "function GamesWidget(ctx)" in st
    assert re.search(r'\{ id: "games",\s+title: "Games",.*render: GamesWidget \}', st)
    assert "Auto-switch profiles for games" in st
    assert "data-games-now" in st and "data-games-picker" in st


def test_game_names_are_rendered_as_text_only():
    for rel in (("src", "app.jsx"), ("workspaces", "settings.jsx")):
        text = _read(SRC, *rel)
        assert "dangerouslySetInnerHTML" not in text and "innerHTML" not in text, rel


def test_built_bundle_carries_the_games_ui():
    built = _read(SRC, "build", "ws_settings.js")
    assert "GamesWidget" in built and "set_games_auto_switch" in built
    html = _read(HERE, "ui", "index_runtime.html")
    assert "apply_profile_to_board" in html and "games_status" in html
