"""Phase 3 game detection: parsing Discord's detectable list and matching
process paths by trailing path segments. Pure: a committed fixture shaped
like the real list, no network, no processes."""
import json
import os

import pytest

import games

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "fixtures", "discord_detectable_sample.json")
STARFALL, NEON, JAVA, NEON_DUP, TINY = ("100000000000000001", "100000000000000002",
                                        "100000000000000003", "100000000000000004",
                                        "100000000000000009")


def _fixture_bytes():
    with open(FIXTURE, "rb") as f:
        return f.read()


def _index(extra=()):
    return games.DetectableIndex(games.parse_detectable(_fixture_bytes()), extra)


def test_norm_exe_lowercases_drops_drive_marker_and_dot_segments():
    n = games.norm_exe
    assert n("C:\\Games\\Foo\\FOO.exe") == "games/foo/foo.exe"
    assert n(">Foo.EXE") == "foo.exe"
    assert n("/a/./b/../c.exe") == "a/b/c.exe"
    assert n("") is None and n(None) is None and n(42) is None
    assert n("bad\x00.exe") is None
    assert n("x" * 300) is None
    assert games.exe_suffix("D:\\SteamLibrary\\common\\Tiny\\Tiny.exe") == "tiny/tiny.exe"
    assert games.exe_suffix("tiny.exe") == "tiny.exe"


def test_clean_name_strips_control_characters_and_caps_length():
    assert games.clean_name("  Neon\x07 Quest ") == "Neon Quest"
    assert games.clean_name("\x01\x02") is None
    assert games.clean_name(None) is None
    assert len(games.clean_name("a" * 500)) == games.MAX_NAME


def test_parse_keeps_only_valid_windows_games():
    parsed = games.parse_detectable(_fixture_bytes())
    by_id = {g["id"]: g for g in parsed}
    assert set(by_id) == {STARFALL, NEON, JAVA, NEON_DUP, TINY}
    assert by_id[STARFALL]["exes"] == ["starfall/starfall.exe"]          # launcher + linux dropped
    assert by_id[NEON]["name"] == "Neon Quest"                           # \x07 removed
    assert by_id[NEON]["exes"] == ["win64/neonquest-win64-shipping.exe", "neonquest.exe"]
    assert by_id[TINY]["exes"] == ["tiny tactics/bin/tinytactics.exe"]   # int id + backslashes


@pytest.mark.parametrize("raw", [b"{}", b'"x"', b"null", "[]", b"[1, 2]",
                                 b'[{"id": "1", "name": "x", "executables": []}]'])
def test_parse_rejects_wrong_shapes(raw):
    with pytest.raises(ValueError):
        games.parse_detectable(raw)


def test_parse_rejects_invalid_json():
    with pytest.raises(ValueError):
        games.parse_detectable(b"[{")


def test_parse_caps_entry_count(monkeypatch):
    monkeypatch.setattr(games, "MAX_GAMES", 3)
    with pytest.raises(ValueError):
        games.parse_detectable(_fixture_bytes())


def test_match_uses_trailing_segments_case_insensitively():
    idx = _index()
    assert idx.match(r"C:\Program Files\Starfall\STARFALL.exe") == STARFALL
    assert idx.match(r"C:\Program Files\Other\starfall.exe") is None     # needs the folder too
    assert idx.match(r"E:\NQ\Engine\Win64\NeonQuest-Win64-Shipping.exe") == NEON
    assert idx.match(r"D:\anything\neonquest.exe") == NEON               # '>' = file name only
    assert idx.match(r"D:\Steam\common\Tiny Tactics\bin\TinyTactics.exe") == TINY
    assert idx.match(r"C:\Windows\notepad.exe") is None
    assert idx.match("") is None and idx.match(None) is None


def test_generic_runtime_names_and_duplicates_are_not_indexed():
    idx = _index()
    assert idx.match(r"C:\Java\bin\javaw.exe") is None                   # generic: never a game
    assert idx.name_of(JAVA) is None
    assert idx.name_of(NEON_DUP) is None                                 # first entry wins
    assert len(idx) == 3


def test_basename_prefilter():
    idx = _index()
    assert idx.could_match("STARFALL.EXE") and idx.could_match("neonquest.exe")
    assert not idx.could_match("explorer.exe") and not idx.could_match(None)


def test_longest_matching_suffix_wins():
    g = [{"id": "1", "name": "Short", "exes": ["game.bin"]},
         {"id": "2", "name": "Long", "exes": ["deep/dir/game.bin"]}]
    idx = games.DetectableIndex(g)
    assert idx.max_segments == 3
    assert idx.match("C:/x/deep/dir/game.bin") == "2"
    assert idx.match("C:/x/other/game.bin") == "1"


def test_user_games_override_discord_patterns():
    extra = [{"id": "custom:starfall/starfall.exe", "name": "My Starfall",
              "exes": ["starfall/starfall.exe"]},
             {"id": "custom:tools/javaw.exe", "name": "My Java Thing", "exes": ["javaw.exe"]}]
    idx = _index(extra)
    assert idx.match(r"C:\Starfall\starfall.exe") == "custom:starfall/starfall.exe"
    assert idx.name_of("custom:starfall/starfall.exe") == "My Starfall"
    assert idx.match(r"C:\Java\javaw.exe") == "custom:tools/javaw.exe"   # user's choice honoured


def test_exes_of_returns_the_indexed_patterns():
    idx = _index()
    assert idx.exes_of(NEON) == ["win64/neonquest-win64-shipping.exe", "neonquest.exe"]
    assert idx.exes_of("nope") == []


def test_names_are_plain_text_from_the_list():
    raw = json.dumps([{"id": "7", "name": "<img src=x onerror=alert(1)>",
                       "executables": [{"name": "x.exe", "os": "win32"}]}])
    g = games.parse_detectable(raw)
    assert g[0]["name"] == "<img src=x onerror=alert(1)>"   # kept as TEXT; the UI never renders HTML
