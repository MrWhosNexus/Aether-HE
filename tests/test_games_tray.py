"""Phase 3: the tray tooltip names the detected game, and main() runs the
game service for the app's lifetime. No pystray, no window."""
import os

import tray
from test_tray import StubApi, StubIcon

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_tooltip_shows_the_detected_game_and_clears():
    c = tray.TrayController(StubApi())
    c.icon = StubIcon()
    c.set_game("Neon Quest")
    assert c.icon.title == c.title == "Aether HE — Neon Quest"
    c.set_game(None)
    assert c.icon.title == "Aether HE"


def test_tooltip_is_plain_capped_text():
    c = tray.TrayController(StubApi())
    c.set_game("Bad\x07\nName" + "x" * 300)
    assert c.title.startswith("Aether HE — BadName") and len(c.title) <= 120
    assert "\n" not in c.title and "\x07" not in c.title


def test_tooltip_set_before_the_icon_exists_is_used_when_it_starts():
    c = tray.TrayController(StubApi())
    c.set_game("Starfall Arena")                  # icon not created yet: no error
    assert c.title == "Aether HE — Starfall Arena"
    src = open(os.path.join(ROOT, "tray.py"), encoding="utf-8").read()
    assert 'pystray.Icon("aether-he", image, self.title, menu)' in src


def test_icon_errors_never_escape():
    class Grumpy(StubIcon):
        def __setattr__(self, k, v):
            if k == "title":
                raise RuntimeError("shell said no")
            super().__setattr__(k, v)
    c = tray.TrayController(StubApi())
    c.icon = Grumpy()
    c.set_game("X")
    assert c.title == "Aether HE — X"


def test_main_runs_the_game_service_for_the_app_lifetime():
    src = open(os.path.join(ROOT, "app_web.py"), encoding="utf-8").read()
    main = src[src.index("def main():"):]
    assert "api._start_games(tray_ctl.set_game)" in main
    assert main.index("api._start_games(") > main.index("tray_ctl = tray.TrayController(")
    fin = main[main.index("finally:"):]
    assert "api._stop_games()" in fin
