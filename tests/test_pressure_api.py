"""Phase 2: the Api keeps a per-key actuation map for the pressure effect, fed
by the firmware read-back (verify_actuation) and by successful writes, and
hands it to the engine as fx.get_actuation. Fakes only: no HID, no keyboard."""
import types

import pytest

import app_web
from test_stats_api import _api


def _with_engine(a):
    a.fx = types.SimpleNamespace(get_depths=None, get_actuation=None)
    return a


def _read_back(a, mm=0.80):
    w = a.km.index_of_code["W"]
    a.driver.detail = {a.km.by_index[w]["name"]: {"travel_mm": mm, "mode": 0}}
    assert a.verify_actuation([])["ok"]
    return w


def test_read_back_feeds_the_pressure_effect(tmp_path):
    a = _with_engine(_api(tmp_path))
    w = _read_back(a, 0.80)
    a._ensure_reactive(["pressure"])
    assert a.fx.get_depths is not None
    assert a.fx.get_actuation()[w] == 0.80


def test_non_reactive_effect_detaches_the_actuation_source(tmp_path):
    a = _with_engine(_api(tmp_path))
    a._ensure_reactive(["pressure"])
    assert a.fx.get_actuation is not None
    a._ensure_reactive(["wave"])
    assert a.fx.get_actuation is None and a.fx.get_depths is None


def test_actuation_source_survives_a_missing_reader(tmp_path):
    a = _with_engine(_api(tmp_path))
    a.driver.make_live_reader = lambda km, indices=None: (_ for _ in ()).throw(
        app_web.UnsupportedFeature("Test board", "travel_stream"))
    a._ensure_reactive(["pressure"])
    assert a.fx.get_depths is None             # effect stays dark, no exception


def test_snapshot_is_a_copy_the_engine_may_keep(tmp_path):
    a = _api(tmp_path)
    a._note_actuation({46: 0.8})
    snap = a._actuation_snapshot()
    a._note_actuation({47: 1.0})
    assert snap == {46: 0.8}


def test_garbage_values_never_enter_the_map(tmp_path):
    a = _api(tmp_path)
    a._note_actuation({1: "x", 2: -1.0, 3: float("nan"), 4: float("inf"),
                       5: 0.0, 6: 0.9})
    assert a._actuation_snapshot() == {6: 0.9}


def test_successful_write_updates_the_map_immediately(tmp_path):
    a = _with_engine(_api(tmp_path))
    w = _read_back(a, 0.80)
    assert a.set_trigger_codes(["W"], 1.2)["ok"]
    assert a._actuation_snapshot()[w] == pytest.approx(1.2)


def test_failed_write_leaves_the_map_alone(tmp_path):
    a = _with_engine(_api(tmp_path))
    w = _read_back(a, 0.80)

    def boom(*args, **kw):
        raise RuntimeError("link lost")
    a._flush_triggers = boom
    assert a.set_trigger_codes(["W"], 1.2)["ok"] is False
    assert a._actuation_snapshot()[w] == 0.80


def test_whole_board_write_updates_every_key(tmp_path):
    a = _api(tmp_path)
    assert a.set_trigger_all(1.0)["ok"]
    snap = a._actuation_snapshot()
    assert set(snap) == set(a.km.indices())
    assert set(snap.values()) == {1.0}


def test_selecting_another_board_forgets_the_map(tmp_path):
    a = _api(tmp_path)
    a._note_actuation({46: 0.8})
    a._registry = None
    a._remaps, a._deadband_state, a._fn_layer_raw = {}, {}, None
    assert a.select_board("aula-mini60he-pro")["ok"] is True
    assert a._actuation_snapshot() == {}
