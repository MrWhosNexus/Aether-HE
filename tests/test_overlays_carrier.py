"""Phase 6 / Task 6: overlays over firmware lighting. While an overlay is on
and the UI's lighting is a firmware mode (static / Full-RGB / per-key paint /
off), the host engine runs as a "carrier"; turning the last overlay off stops it
and re-sends the firmware lighting once. Fakes only: no HID, no keyboard."""
import time

import overlays
import pytest

# _fake_sensors is autouse: importing it registers it here (no real sensors / nvidia-smi).
from test_overlays_api import _api, _fake_sensors, _teardown, _wait  # noqa: F401


# ---- carrier_plan (pure) ---------------------------------------------------
IDX = [3, 4, 5]


def _light(**kw):
    p = {"mode": 0, "fg": (200, 100, 0), "bg": (0, 0, 20), "brightness": 4, "speed": 4,
         "direction": 0, "full_color": 0, "power_on": True}
    p.update(kw)
    return ("light", p)


def test_no_known_lighting_carries_black():
    assert overlays.carrier_plan(None, IDX) == {"zones": [], "bg": (0, 0, 0), "base": {}}


def test_static_firmware_colour_is_reproduced_per_key():
    plan = overlays.carrier_plan(_light(), IDX, bright_max=4)
    assert plan["zones"] == [] and plan["base"] == {i: (200, 100, 0) for i in IDX}
    assert plan["bg"] == (0, 0, 20)


def test_firmware_brightness_steps_scale_the_colour():
    plan = overlays.carrier_plan(_light(brightness=2), IDX, bright_max=4)
    assert plan["base"][3] == (100, 50, 0)
    plan = overlays.carrier_plan(_light(brightness=5), IDX, bright_max=5)      # MINI-style scale
    assert plan["base"][3] == (200, 100, 0)
    assert overlays.carrier_plan(_light(brightness=99), IDX, 4)["base"][3] == (200, 100, 0)


def test_lights_off_carries_black_so_the_bars_still_show():
    assert overlays.carrier_plan(_light(power_on=False), IDX) == {
        "zones": [], "bg": (0, 0, 0), "base": {}}


def test_full_rgb_firmware_mode_becomes_a_rainbow_wave():
    plan = overlays.carrier_plan(_light(full_color=1, brightness=4), IDX, 4)
    z = plan["zones"][0]
    assert z["mode"] == "wave" and z["indices"] == IDX and z["palette"] == overlays.RAINBOW
    assert z["bright"] == 1.0 and plan["base"] == {}


def test_per_key_paint_is_reproduced_and_other_keys_are_dark():
    src = ("custom", {3: (255, 0, 0), 4: (0, 255, 0)}, 4, 4)
    plan = overlays.carrier_plan(src, IDX, 4)
    assert plan["base"] == {3: (255, 0, 0), 4: (0, 255, 0)} and plan["zones"] == []
    half = overlays.carrier_plan(("custom", {3: (255, 0, 0)}, 2, 4), IDX, 4)
    assert half["base"] == {3: (128, 0, 0)}


# ---- the Api carrier ---------------------------------------------------------
LIGHT = (0, 200, 100, 0, 4, 4, 0, 0, 20, 0, True, 0)       # set_light positional args


def test_without_overlays_set_light_goes_straight_to_the_firmware(tmp_path):
    a = _api(tmp_path)
    assert a.set_light(*LIGHT) == {"ok": True}
    assert a.driver.named("light") == [("light", 0, (200, 100, 0), (0, 0, 20), 4, 4, 0, 0, True)]
    assert a.driver.named("begin") == [] and not a.fx.is_running() and a._carrier_on is False
    _teardown(a)


def test_turning_an_overlay_on_over_static_starts_the_carrier(tmp_path):
    a = _api(tmp_path)
    a.set_light(*LIGHT)
    a.driver.calls.clear()
    assert a.set_overlay("cpu", True)["ok"]
    assert a.fx.is_running() and a._carrier_on is True
    assert a.driver.named("begin") == [("begin",)]
    assert a.driver.named("light") == []                           # firmware not touched
    assert _wait(lambda: a.frames)
    f = a.frames[-1]
    row = a.km.indices_for_codes(overlays.ROW_CODES["cpu"])
    other = a.km.index_of_code["Space"]
    assert f[other] == (200, 100, 0)                                # static colour carried
    assert all(f[i] == overlays.TRACK for i in row)                 # bar track (no reading yet)
    _teardown(a)


def test_last_overlay_off_stops_the_carrier_and_restores_the_firmware_once(tmp_path):
    a = _api(tmp_path)
    a.set_light(*LIGHT)
    a.set_overlay("cpu", True)
    a.set_overlay("ram", True)
    a.driver.calls.clear()
    a.set_overlay("cpu", False)
    assert a.fx.is_running()                                        # ram still on
    assert a.driver.named("light") == []
    a.set_overlay("ram", False)
    assert not a.fx.is_running() and a._carrier_on is False
    assert a.driver.named("light") == [("light", 0, (200, 100, 0), (0, 0, 20), 4, 4, 0, 0, True)]
    assert a.driver.named("end") == [("end",)]
    _teardown(a)


def test_ui_lighting_changes_while_overlays_are_on_are_carried_not_written(tmp_path):
    a = _api(tmp_path)
    a.set_light(*LIGHT)
    a.set_overlay("gpu", True)
    a.driver.calls.clear()
    a.stop_multicolor()                                             # the UI's usual first step
    assert a._carrier_on is False and not a.fx.is_running()
    a.set_light(0, 0, 0, 255, 4, 4, 0, 0, 0, 0, True, 0)           # then the new colour
    assert a._carrier_on is True and a.fx.is_running()
    assert a.driver.named("light") == []
    assert _wait(lambda: a.frames and a.frames[-1][a.km.index_of_code["Space"]] == (0, 0, 255))
    a.set_overlay("gpu", False)
    assert a.driver.named("light") == [("light", 0, (0, 0, 255), (0, 0, 0), 4, 4, 0, 0, True)]
    _teardown(a)


def test_a_host_effect_started_by_the_ui_is_never_touched_by_the_toggles(tmp_path):
    a = _api(tmp_path)
    assert a.start_multicolor("wave", [[255, 0, 0]], [0, 0, 0], 80, 60, 0, "v")["ok"]
    assert a._carrier_on is False
    a.driver.calls.clear()
    a.set_overlay("cpu", True)
    assert a.fx.is_running() and a._carrier_on is False
    assert a.driver.named("begin") == []                            # no restart, no extra write
    a.set_overlay("cpu", False)
    assert a.fx.is_running() and a.driver.named("light") == []      # the wave keeps going
    _teardown(a)


def test_overlays_draw_over_a_host_effect(tmp_path):
    a = _api(tmp_path)
    a.start_multicolor("wave", [[255, 0, 0]], [0, 0, 0], 80, 60, 0, "v")
    a.set_overlay("cpu", True)
    row = a.km.indices_for_codes(overlays.ROW_CODES["cpu"])
    assert _wait(lambda: a.frames and all(a.frames[-1][i] == overlays.color_for("cpu", 1.0) for i in row))
    _teardown(a)


def test_per_key_paint_is_carried_and_restored(tmp_path):
    a = _api(tmp_path)
    q = a.km.index_of_code["Q"]
    assert a.set_custom_colors({"Q": [255, 0, 0]}, 4, 4)["ok"]
    assert a.driver.named("paint") == [("paint", {q: (255, 0, 0)}, 4, 4)]
    a.driver.calls.clear()
    a.set_overlay("pomodoro", True)
    assert a._carrier_on and a.driver.named("paint") == []
    a.set_overlay("pomodoro", False)
    assert a.driver.named("paint") == [("paint", {q: (255, 0, 0)}, 4, 4)]
    _teardown(a)


def test_lights_off_still_shows_the_bars(tmp_path):
    a = _api(tmp_path)
    a.set_light(0, 255, 255, 255, 4, 4, 0, 0, 0, 0, False, 0)      # power off
    a.set_overlay("cpu", True)
    assert _wait(lambda: a.frames)
    other = a.km.index_of_code["Space"]
    assert a.frames[-1][other] == (0, 0, 0)
    a.set_overlay("cpu", False)
    assert a.driver.named("light")[-1][-1] is False                 # off is restored as off
    _teardown(a)


def test_no_known_lighting_restores_nothing(tmp_path):
    a = _api(tmp_path)
    a.set_overlay("cpu", True)
    assert a._carrier_on
    a.driver.calls.clear()
    a.set_overlay("cpu", False)
    assert a.driver.named("light") == [] and a.driver.named("paint") == []
    _teardown(a)


def test_offline_board_defers_the_carrier(tmp_path):
    a = _api(tmp_path)
    a.dev.open = False
    assert a.set_overlay("cpu", True)["ok"]
    assert not a.fx.is_running() and a._carrier_on is False
    a.dev.open = True
    a.set_light(*LIGHT)                                             # the UI re-sends on connect
    assert a.fx.is_running() and a._carrier_on is True
    _teardown(a)


def test_switching_profiles_to_one_without_overlays_hands_the_firmware_back(tmp_path):
    a = _api(tmp_path)
    a.games_sync({"activeProfile": "fps"})
    a.set_light(*LIGHT)
    a.set_overlay("cpu", True)
    assert a._carrier_on
    a.driver.calls.clear()
    a.games_sync({"activeProfile": "desk"})                         # desk has no overlays
    assert not a.fx.is_running()
    assert len(a.driver.named("light")) == 1
    _teardown(a)


def test_disconnect_style_stop_leaves_no_carrier_flag(tmp_path):
    a = _api(tmp_path)
    a.set_light(*LIGHT)
    a.set_overlay("cpu", True)
    a.stop_multicolor()
    assert a._carrier_on is False and not a.fx.is_running()
    _teardown(a)


def test_carrier_frame_rate_is_the_engines_normal_cap(tmp_path):
    a = _api(tmp_path)
    a.set_light(*LIGHT)
    a.set_overlay("cpu", True)
    t0 = time.time()
    n0 = len(a.frames)
    time.sleep(0.5)
    rate = (len(a.frames) - n0) / (time.time() - t0)
    assert rate <= a.fx.fps + 5                                     # never above the existing cap
    _teardown(a)


def test_carrier_start_and_stop_never_overlap_across_threads(tmp_path):
    import threading
    a = _api(tmp_path)
    a.set_light(*LIGHT)
    a.set_overlay("cpu", True)
    state = {"in": 0, "max": 0}
    guard = threading.Lock()

    def slow(real):
        def wrapped(*args, **kw):
            with guard:
                state["in"] += 1
                state["max"] = max(state["max"], state["in"])
            time.sleep(0.02)
            try:
                return real(*args, **kw)
            finally:
                with guard:
                    state["in"] -= 1
        return wrapped
    a.driver.begin_host_stream = slow(a.driver.begin_host_stream)
    a.driver.end_host_stream = slow(a.driver.end_host_stream)
    gate = threading.Barrier(6)

    def go(fn):
        gate.wait()
        try:
            fn()
        except Exception:
            pass
    fns = [a._carrier_start, a._carrier_stop, a._carrier_start, a._carrier_stop,
           a._carrier_start, a._carrier_stop]
    ts = [threading.Thread(target=go, args=(f,)) for f in fns]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert state["max"] == 1                                    # serialised: one at a time
    _teardown(a)
