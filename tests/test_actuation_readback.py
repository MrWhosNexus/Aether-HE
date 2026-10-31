"""verify_actuation reports what the firmware STORES per key — travel, and
now also the trigger mode and the RT press/release sensitivities — so the
UI can draw the board from the read-back instead of from what it asked for
(an "ok" used to be trusted even when the write went nowhere)."""
import threading

import app_web
import device_state
import protocol
from drivers import Win60Driver

from test_keyboard_review import ReadableDevice, _trigger_reply

KM = device_state.KeyMap()          # ui/keymap.json = the WIN 60 HE layout


class Board:
    """Answers cmd-33 sub-5 per-key trigger reads from a stored table."""

    def __init__(self):
        self.cfg = {i: (0, 170, 1, 1) for i in KM.indices()}

    def reply(self, payload):
        b = payload[1:]
        if b[0] == 33 and b[5] == 5:
            idx = b[6] * 22 + b[7]
            if idx in self.cfg:
                mode, travel, i1, i2 = self.cfg[idx]
                return [_trigger_reply(b[6], b[7], travel, mode, i1, i2)]
        return []


def _api(board):
    a = app_web.Api.__new__(app_web.Api)
    a._lock = threading.RLock()
    a.km = KM
    a.reader = None
    a._reader_users = set()
    a.dev = ReadableDevice(board.reply)
    a.driver = Win60Driver(None, a.dev, a._lock)
    return a


def test_verify_actuation_reports_mode_and_rt_per_key():
    board = Board()
    j, k = KM.index_of_code["J"], KM.index_of_code["K"]
    board.cfg[j] = (13, 120, 30, 40)          # RT, press 0.30 / release 0.40
    board.cfg[k] = (0, 200, 1, 1)             # fixed 2.00 mm (stored pair 1/1)
    r = _api(board).verify_actuation(["J", "K"])
    assert r["ok"]
    assert r["actuation_mm"] == {"J": 1.2, "K": 2.0}
    assert r["trigger"]["J"] == {"mode": 13, "travel_mm": 1.2,
                                 "rt_press_mm": 0.3, "rt_release_mm": 0.4}
    assert r["trigger"]["K"] == {"mode": 0, "travel_mm": 2.0,
                                 "rt_press_mm": 0.01, "rt_release_mm": 0.01}


def test_verify_actuation_all_keys_when_no_codes():
    r = _api(Board()).verify_actuation([])
    assert r["ok"] and len(r["actuation_mm"]) == len(KM.index_of_code)
    assert set(r["trigger"]) == set(r["actuation_mm"])


def test_verify_actuation_falls_back_without_trigger_detail():
    """A driver that only has read_actuation (MINI 60) keeps the old shape."""
    class D:
        def read_actuation(self, km):
            return {KM.by_index[KM.index_of_code["J"]]["name"]: 1.5}

    a = _api(Board())
    a.driver = D()
    r = a.verify_actuation(["J"])
    assert r["ok"] and r["actuation_mm"] == {"J": 1.5}
    assert "trigger" not in r
