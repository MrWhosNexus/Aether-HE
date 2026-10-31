"""An empty SOCD list must reach the keyboard: the board keeps its pairs in
flash, and the UI used to skip the call when no pair was complete, leaving
the old pairs active. set_socd([]) clears them (verified on hardware)."""
import threading

import app_web
import device_state
import protocol
from drivers import Win60Driver

from test_keyboard_review import ReadableDevice


def _api():
    a = app_web.Api.__new__(app_web.Api)
    a._lock = threading.RLock()
    a.km = device_state.KeyMap()
    a.dev = ReadableDevice()
    a.driver = Win60Driver(None, a.dev, a._lock)
    return a


def test_empty_socd_list_is_written_as_a_clear():
    a = _api()
    assert a.set_socd([]) == {"ok": True}
    assert a.dev.writes, "an empty list must still write the PRCS table"
    assert all(w[0] == protocol.REPORT_ID for w in a.dev.writes)
    cleared = list(a.dev.writes)
    a.dev.writes.clear()
    assert a.set_socd([{"model": 4, "key1": "A", "key2": "D"}])["ok"]
    assert a.dev.writes and a.dev.writes != cleared
