"""Phase 3: process scanning. The scanner is fed fake process lists, so the
matching, foreground arbitration and the privacy rule (only candidate
processes are opened) are tested anywhere. One smoke test reads this
machine's own process list on Windows (read-only OS call, no HID)."""
import os
import sys

import pytest

import games
from test_games_index import NEON, STARFALL, _index

PROCS = [(10, "System"), (20, "explorer.exe"), (30, "starfall.exe"),
         (40, "NeonQuest-Win64-Shipping.exe"), (50, "chrome.exe"), (60, "starfall.exe")]
PATHS = {20: r"C:\Windows\explorer.exe",
         30: r"C:\Games\Starfall\starfall.exe",
         40: r"E:\NQ\Win64\NeonQuest-Win64-Shipping.exe",
         50: r"C:\Program Files\Google\Chrome\chrome.exe",
         60: r"C:\Other\starfall.exe"}


def _scan(fg_pid=None):
    opened = []

    def path_of(pid):
        opened.append(pid)
        return PATHS.get(pid)
    running, fg = games.scan(_index(), procs=lambda: PROCS, path_of=path_of,
                             fg=lambda: fg_pid)
    return running, fg, opened


def test_scan_finds_running_games_and_the_foreground_one():
    running, fg, _ = _scan(fg_pid=40)
    assert running == {STARFALL, NEON}
    assert fg == NEON


def test_foreground_non_game_means_no_foreground_game():
    _, fg, _ = _scan(fg_pid=50)
    assert fg is None


def test_only_candidate_processes_are_opened():
    _, _, opened = _scan()
    assert sorted(opened) == [30, 40, 60]                 # never explorer/chrome/System


def test_access_denied_falls_back_to_the_file_name():
    running, _ = games.scan(_index(), procs=lambda: [(7, "neonquest.exe")],
                               path_of=lambda pid: None, fg=lambda: None)
    assert running == {NEON}                              # '>neonquest.exe' = file name only


def test_running_programs_lists_user_programs_once_known_games_first(monkeypatch):
    monkeypatch.setenv("SystemRoot", r"C:\Windows")
    rows = games.running_programs(_index(), procs=lambda: PROCS + [(99, "aether.exe")],
                                  path_of=lambda pid: PATHS.get(pid) or
                                  (r"C:\Aether\AetherHE.exe" if pid == 99 else None),
                                  own_pid=99)
    assert [r["exe"] for r in rows] == ["win64/neonquest-win64-shipping.exe",
                                        "starfall/starfall.exe", "chrome/chrome.exe",
                                        "other/starfall.exe"]
    assert rows[0] == {"exe": "win64/neonquest-win64-shipping.exe", "name": "Neon Quest",
                       "gameId": NEON}
    assert rows[2]["gameId"] is None and rows[2]["name"] == "chrome.exe"


def test_platform_gate():
    assert games.processes_supported("win32") is True
    assert games.processes_supported("linux") is False
    assert games.processes_supported("darwin") is False


@pytest.mark.skipif(sys.platform.startswith("win"), reason="non-Windows behaviour")
def test_enumeration_is_empty_off_windows():
    assert games.list_processes() == []
    assert games.process_path(os.getpid()) is None
    assert games.foreground_pid() is None


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows ctypes smoke test")
def test_windows_enumeration_sees_this_process():
    procs = games.list_processes()
    assert len(procs) > 5
    assert any(pid == os.getpid() for pid, _ in procs)
    path = games.process_path(os.getpid())
    # a venv python.exe is a launcher for the base interpreter: compare names
    assert path and os.path.basename(path).lower().startswith("python")
    fg = games.foreground_pid()
    assert fg is None or isinstance(fg, int)
