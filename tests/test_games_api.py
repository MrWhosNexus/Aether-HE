"""Phase 3 bridge: the games_* Api methods (never raise to JS), the settings
lock, and the service lifecycle hooks. Fakes only: no HID, no network, no
real processes."""
import json
import os
import re
import threading

import app_web
import games
from test_games_index import STARFALL, _fixture_bytes
from test_games_service import Clock, Scanner
from test_stats_api import _api

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _with_games(a, tmp_path, platform="win32"):
    store = games.DetectableStore(str(tmp_path / "games"),
                                  fetcher=lambda url, cap: _fixture_bytes())
    store.refresh()
    read = lambda: (a.load_settings() or {}).get("settings")      # noqa: E731
    a._games = games.GameService(str(tmp_path), read, a.save_settings,
                                 platform=platform, store=store, scanner=Scanner(),
                                 clock=Clock(),
                                 programs=lambda index: [{"exe": "indie/indie.exe",
                                                          "name": "indie.exe",
                                                          "gameId": None}])
    return a


def test_without_a_service_every_bridge_call_answers(tmp_path):
    a = _api(tmp_path)
    st = a.games_status()
    assert st["ok"] is True and st["available"] is False and st["games"] == []
    assert a.list_running_games()["ok"] is False
    assert a.set_game_profile(STARFALL, "p1")["ok"] is False
    assert a.add_custom_game("x/y.exe", "Y")["ok"] is False
    assert a.refresh_detectable()["ok"] is False
    assert a.set_games_auto_switch(True)["ok"] is False
    assert a.games_sync({"activeProfile": "p1"}) == {"ok": True}


def test_bridge_round_trip_persists_into_settings_json(tmp_path):
    a = _with_games(_api(tmp_path), tmp_path)
    a.save_settings({"profiles": [{"id": "p1"}], "activeProfile": "p1"})
    assert a.games_sync({"activeProfile": "p1", "handledSeq": 0,
                         "profiles": [{"id": "p1", "name": "Default"},
                                      {"id": "pg", "name": "Games"}]})["ok"]
    assert a.set_game_profile(STARFALL, "pg") == {"ok": True, "autoSwitch": True}
    r = a.add_custom_game(r"C:\Games\Indie\Indie.exe", "Indie")
    assert r == {"ok": True, "id": "custom:indie/indie.exe", "name": "Indie"}
    assert a.list_running_games()["programs"][0]["exe"] == "indie/indie.exe"
    with open(a._settings_path(), encoding="utf-8") as f:
        data = json.load(f)
    assert data["profiles"] == [{"id": "p1"}]                    # UI keys preserved
    assert set(data["games"]["map"]) == {STARFALL, "custom:indie/indie.exe"}
    st = a.games_status()
    assert [g["name"] for g in st["games"]] == ["Indie", "Starfall Arena"]
    assert a.set_games_auto_switch(False) == {"ok": True, "autoSwitch": False}


def test_bridge_turns_errors_into_ok_false(tmp_path):
    a = _with_games(_api(tmp_path), tmp_path)
    for r in (a.set_game_profile("999", "p1"), a.set_game_profile(None, "p1"),
              a.add_custom_game("notes.txt"), a.add_custom_game(None),
              a.games_sync("nope")):
        assert r["ok"] is False and r["error"]
    a._games.status = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    assert a.games_status() == {"ok": False, "error": "boom"}


def test_refresh_detectable_goes_through_the_injected_fetcher(tmp_path):
    a = _with_games(_api(tmp_path), tmp_path)
    assert a.refresh_detectable() == {"ok": True, "count": 5}
    a._games.store._fetch = lambda url, cap: (_ for _ in ()).throw(OSError("offline"))
    r = a.refresh_detectable()
    assert r["ok"] is False and "offline" in r["error"]


def test_make_games_reads_settings_and_starts_no_thread(tmp_path, monkeypatch):
    monkeypatch.setattr(app_web, "user_data_dir", lambda: str(tmp_path))
    a = _api(tmp_path)
    with open(a._settings_path(), "w", encoding="utf-8") as f:
        json.dump({"games": {"map": {STARFALL: {"name": "Starfall Arena",
                                                "exes": ["starfall/starfall.exe"],
                                                "profile": "p1"}}}}, f)
    svc = a._make_games()
    assert isinstance(svc, games.GameService) and svc._thread is None
    assert svc.status()["games"][0]["id"] == STARFALL
    assert svc.store.path == os.path.join(str(tmp_path), "games", "detectable.json")


def test_start_and_stop_hooks(tmp_path):
    a = _with_games(_api(tmp_path), tmp_path, platform="linux")
    seen = []
    assert a._start_games(seen.append) is False            # Linux: no thread
    assert a._games.on_detected == seen.append
    a._stop_games()
    a._games = None
    assert a._start_games(None) is False
    a._stop_games()


def test_concurrent_settings_saves_never_drop_a_key(tmp_path):
    a = _api(tmp_path)
    threads = [threading.Thread(target=a.save_settings, args=({f"k{i}": i},))
               for i in range(24)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    with open(a._settings_path(), encoding="utf-8") as f:
        data = json.load(f)
    assert all(data.get(f"k{i}") == i for i in range(24))


def test_the_service_is_never_a_public_api_attribute():
    src = open(os.path.join(ROOT, "app_web.py"), encoding="utf-8").read()
    assert re.search(r"self\.games\s*=", src) is None       # pywebview walks public attrs
    assert "self._games = self._make_games()" in src
