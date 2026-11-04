"""Phase 3: GameService glue (settings.json "games" block, mapping, custom
games, status, tooltip callback, thread gate). Fake scanner + fake clock +
in-memory settings: no processes, no network, no threads unless asked."""
import json

import pytest

import games
from test_games_index import NEON, STARFALL, _fixture_bytes


class Settings:
    """In-memory settings.json with Api.save_settings' top-level merge."""

    def __init__(self, data=None):
        self.data = dict(data or {})
        self.writes = 0

    def read(self):
        return json.loads(json.dumps(self.data))

    def write(self, partial):
        self.writes += 1
        self.data.update(json.loads(json.dumps(partial)))
        return {"ok": True}


class Scanner:
    def __init__(self):
        self.running, self.fg = set(), None

    def __call__(self, index):
        return set(self.running), self.fg


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def _svc(tmp_path, settings=None, platform="win32", with_list=True):
    store = games.DetectableStore(str(tmp_path / "games"),
                                  fetcher=lambda url, cap: _fixture_bytes())
    if with_list:
        store.refresh()
    s = settings or Settings({"activeProfile": "p1"})
    scan, clock = Scanner(), Clock()
    svc = games.GameService(str(tmp_path), s.read, s.write, platform=platform,
                            store=store, scanner=scan, clock=clock,
                            programs=lambda index: [{"exe": "x/x.exe", "name": "x.exe",
                                                     "gameId": None}])
    svc.sync({"activeProfile": "p1", "handledSeq": 0,
              "profiles": [{"id": "p1", "name": "Default"}, {"id": "pg", "name": "Games"}]})
    return svc, s, scan, clock


def _polls(svc, clock, n):
    out = None
    for _ in range(n):
        clock.t += games.POLL_S
        out = svc.tick() or out
    return out


def test_mapping_a_discord_game_stores_its_name_and_exes(tmp_path):
    svc, s, _, _ = _svc(tmp_path)
    assert svc.set_profile(STARFALL, "pg") == {"ok": True, "autoSwitch": True}
    entry = s.data["games"]["map"][STARFALL]
    assert entry == {"name": "Starfall Arena", "exes": ["starfall/starfall.exe"],
                     "profile": "pg", "custom": False}
    assert s.data["games"]["autoSwitch"] is None          # default: ON because a game is mapped


def test_mapped_games_are_detected_even_without_the_discord_list(tmp_path):
    s = Settings({"games": {"map": {STARFALL: {"name": "Starfall Arena",
                                               "exes": ["starfall/starfall.exe"],
                                               "profile": "pg"}}}})
    svc, _, _, _ = _svc(tmp_path, settings=s, with_list=False)
    assert svc.index.match(r"C:\Starfall\starfall.exe") == STARFALL


def test_unknown_game_and_unknown_profile_are_refused(tmp_path):
    svc, _, _, _ = _svc(tmp_path)
    with pytest.raises(ValueError):
        svc.set_profile("123", "pg")
    with pytest.raises(ValueError):
        svc.set_profile(STARFALL, "nope")
    with pytest.raises(ValueError):
        svc.set_profile(STARFALL, "../../evil")


def test_unmapping_removes_the_entry(tmp_path):
    svc, s, _, _ = _svc(tmp_path)
    svc.set_profile(STARFALL, "pg")
    svc.set_profile(STARFALL, None)
    assert s.data["games"]["map"] == {}
    assert svc.auto_switch is False


def test_custom_game_from_a_running_program(tmp_path):
    svc, s, _, _ = _svc(tmp_path)
    r = svc.add_custom(r"C:\Users\me\Games\Indie\Indie.exe", "  My Indie\x07 ")
    assert r == {"ok": True, "id": "custom:indie/indie.exe", "name": "My Indie"}
    assert svc.index.match(r"D:\Indie\INDIE.EXE") == "custom:indie/indie.exe"
    assert s.data["games"]["map"]["custom:indie/indie.exe"]["profile"] is None
    svc.set_profile("custom:indie/indie.exe", "pg")
    assert s.data["games"]["map"]["custom:indie/indie.exe"]["profile"] == "pg"
    with pytest.raises(ValueError):
        svc.add_custom("notes.txt")
    with pytest.raises(ValueError):
        svc.add_custom("")


def test_auto_switch_toggle_is_persisted_and_explicit_off_wins(tmp_path):
    svc, s, _, _ = _svc(tmp_path)
    svc.set_profile(STARFALL, "pg")
    assert svc.set_auto(False) == {"ok": True, "autoSwitch": False}
    assert s.data["games"]["autoSwitch"] is False
    assert svc.auto_switch is False


def test_malformed_settings_block_is_dropped_not_fatal(tmp_path):
    s = Settings({"games": {"autoSwitch": "yes", "map": {
        "abc": {"name": "Bad id", "exes": ["a.exe"]},
        STARFALL: {"name": "", "exes": ["a.exe"]},
        NEON: {"name": "Neon", "exes": ["neonquest.exe"], "profile": "../x"},
        "custom:": {"name": "Empty", "exes": ["a.exe"]}}}})
    svc, _, _, _ = _svc(tmp_path, settings=s)
    st = svc.status()
    assert [g["id"] for g in st["games"]] == [NEON]
    assert st["games"][0]["profileId"] is None
    assert svc._block["autoSwitch"] is None


def test_tick_switches_and_reports_the_tooltip_name(tmp_path):
    svc, _, scan, clock = _svc(tmp_path)
    svc.set_profile(STARFALL, "pg")
    shown = []
    svc.on_detected = shown.append
    scan.running, scan.fg = {STARFALL}, STARFALL
    sw = _polls(svc, clock, 3)
    assert sw["profileId"] == "pg" and sw["gameName"] == "Starfall Arena"
    assert shown == ["Starfall Arena"]                    # once, not every poll
    st = svc.status()
    assert st["active"] == {"id": STARFALL, "name": "Starfall Arena", "profileId": "pg"}
    assert st["detected"] == [{"id": STARFALL, "name": "Starfall Arena", "mapped": True,
                               "profileId": "pg"}]
    assert st["switch"]["seq"] == 1
    svc.sync({"activeProfile": "pg", "handledSeq": 1})
    scan.running, scan.fg = set(), None
    sw = _polls(svc, clock, 3)
    assert sw["profileId"] == "p1" and sw["reason"] == "revert"
    assert shown == ["Starfall Arena", None]


def test_a_profile_switch_logs_no_game_name(tmp_path, caplog):
    """aether.log is a rotating, timestamped file: a game name there is a play history."""
    import logging
    svc, _, scan, clock = _svc(tmp_path)
    svc.set_profile(STARFALL, "pg")
    scan.running, scan.fg = {STARFALL}, STARFALL
    with caplog.at_level(logging.INFO):
        sw = _polls(svc, clock, 3)
    assert sw["profileId"] == "pg"
    info = [r for r in caplog.records if r.levelno >= logging.INFO]
    assert any("pg" in r.getMessage() for r in info)          # the switch itself is still logged
    assert not any("Starfall" in r.getMessage() or STARFALL in r.getMessage() for r in info)


def test_detected_but_unmapped_games_show_but_never_switch(tmp_path):
    svc, _, scan, clock = _svc(tmp_path)
    shown = []
    svc.on_detected = shown.append
    scan.running = {NEON}
    assert _polls(svc, clock, 4) is None
    assert shown == ["Neon Quest"]
    assert svc.status()["detected"][0]["mapped"] is False


def test_previous_profile_falls_back_to_settings_json_before_the_first_sync(tmp_path):
    s = Settings({"activeProfile": "p7"})
    store = games.DetectableStore(str(tmp_path / "g"), fetcher=lambda u, c: _fixture_bytes())
    store.refresh()
    scan, clock = Scanner(), Clock()
    svc = games.GameService(str(tmp_path), s.read, s.write, platform="win32",
                            store=store, scanner=scan, clock=clock)
    svc._block["map"][STARFALL] = {"name": "S", "exes": ["starfall/starfall.exe"],
                                   "profile": "pg", "custom": False}
    scan.running = {STARFALL}
    _polls(svc, clock, 3)
    assert svc.switcher.prev_profile == "p7"


def test_sync_validates_its_input(tmp_path):
    svc, _, _, _ = _svc(tmp_path)
    with pytest.raises(ValueError):
        svc.sync("nope")
    svc.sync({"profiles": [{"id": "ok_1", "name": "\x01A"}, {"id": "bad id"}, "x"],
              "activeProfile": "bad id", "handledSeq": True})
    assert svc.profiles == [{"id": "ok_1", "name": "A"}]
    assert svc.active_profile == "p1"                     # invalid id ignored


def test_unavailable_platform_never_polls_or_starts(tmp_path):
    svc, _, scan, clock = _svc(tmp_path, platform="linux")
    scan.running = {STARFALL}
    assert svc.tick() is None and svc.start() is False and svc._thread is None
    assert svc.running() == []
    st = svc.status()
    assert st["ok"] is True and st["available"] is False


def test_start_and_stop_the_poll_thread(tmp_path, monkeypatch):
    svc, _, _, _ = _svc(tmp_path)
    monkeypatch.setattr(svc.store, "should_refresh", lambda: False)
    assert svc.start() is True and svc._thread.daemon
    assert svc.start() is True                            # idempotent
    svc.stop()
    assert svc._thread is None


def test_refresh_detectable_rebuilds_the_index(tmp_path):
    svc, _, _, _ = _svc(tmp_path, with_list=False)
    assert svc.index.match(r"C:\Starfall\starfall.exe") is None
    assert svc.refresh_detectable() == {"ok": True, "count": 5}
    assert svc.index.match(r"C:\Starfall\starfall.exe") == STARFALL


def test_nothing_about_other_processes_is_kept(tmp_path):
    svc, s, scan, clock = _svc(tmp_path)
    scan.running = {NEON}
    _polls(svc, clock, 2)
    blob = json.dumps(s.data) + json.dumps(svc.status())
    assert "chrome" not in blob and "explorer" not in blob
    assert not hasattr(svc, "processes")


def test_foreground_game_feeds_the_stats_hook_on_change_only(tmp_path):
    svc, _, scan, clock = _svc(tmp_path)
    fg = []
    svc.on_foreground = fg.append
    scan.running, scan.fg = {STARFALL}, STARFALL
    _polls(svc, clock, 3)
    assert fg == ["Starfall Arena"]
    scan.fg = None                                        # alt-tab out, still running
    _polls(svc, clock, 2)
    assert fg == ["Starfall Arena", None]
