"""Per-game key statistics: runs made while a game is in front are ALSO
counted under that game (same counters only), in pending and in the file."""
import json

import telemetry
from test_telemetry import _tel, _press, W, TODAY


def test_runs_count_under_the_foreground_game_too(tmp_path):
    tel = _tel(tmp_path)
    _press(tel, W, [1.0, 2.0])                       # no game
    tel.set_game("Valorant")
    _press(tel, W, [1.0, 3.4], t0=200.0)
    _press(tel, W, [0.8, 1.5], t0=300.0)
    tel.set_game(None)
    assert tel.load_day(TODAY)[W]["presses"] == 3
    g = tel.load_day_buckets(TODAY, "Valorant")
    assert sum(a["presses"] for a in g.values()) == 2
    assert tel.games_seen(1) == [{"name": "Valorant", "presses": 2}]


def test_games_survive_a_flush_and_merge_with_pending(tmp_path):
    tel = _tel(tmp_path)
    tel.set_game("Apex Legends")
    _press(tel, W, [1.0, 2.0])
    assert tel.flush()
    _press(tel, W, [1.0, 2.0], t0=200.0)
    doc = json.loads((tmp_path / "stats" / f"{TODAY}.json").read_text())
    assert set(doc["games"]) == {"Apex Legends"}
    assert set(doc["games"]["Apex Legends"]) == {tel.board}
    got = tel.load_day_buckets(TODAY, "Apex Legends")
    assert sum(a["presses"] for a in got.values()) == 2
    assert tel.load_day(TODAY)[W]["presses"] == 2      # main view not doubled


def test_game_file_holds_counters_only(tmp_path):
    tel = _tel(tmp_path)
    tel.set_game("Game")
    _press(tel, W, [1.0, 2.0])
    tel.flush()
    doc = json.loads((tmp_path / "stats" / f"{TODAY}.json").read_text())
    for rec in doc["games"]["Game"][tel.board].values():
        assert set(rec) == set(telemetry.FIELDS) | {"hist"}


def test_game_names_are_cleaned_and_capped(tmp_path):
    assert telemetry.clean_game("  Doom\x00\n ") == "Doom"
    assert telemetry.clean_game("") is None and telemetry.clean_game(5) is None
    assert len(telemetry.clean_game("x" * 500)) == telemetry.GAME_NAME_MAX
    tel = _tel(tmp_path)
    for i in range(telemetry.MAX_GAMES + 5):
        tel.set_game(f"g{i}")
        _press(tel, W, [1.0, 2.0], t0=100.0 + i)
    tel.flush()
    doc = json.loads((tmp_path / "stats" / f"{TODAY}.json").read_text())
    assert len(doc["games"]) == telemetry.MAX_GAMES
