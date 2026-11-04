"""Phase 6 / Task 1: overlay layout, colours and bar painting (pure maths)."""
import pytest

import device_state
import overlays


def test_rows_resolve_on_the_win60_keymap():
    km = device_state.KeyMap()
    for oid, n in (("cpu", 10), ("ram", 10), ("gpu", 10), ("pomodoro", 12)):
        idx = km.indices_for_codes(overlays.ROW_CODES[oid])
        assert len(idx) == n == len(set(idx)), oid
        ys = {round(km.by_index[i]["y"] / 10) for i in idx}
        assert len(ys) == 1, f"{oid} must be one physical row"
    rows = [{round(km.by_index[i]["y"] / 10) for i in km.indices_for_codes(overlays.ROW_CODES[o])}.pop()
            for o in ("cpu", "ram", "gpu", "pomodoro")]
    assert rows == sorted(rows) and len(set(rows)) == 4      # number, QWERTY, home, shift


def test_ids_labels_and_row_names_line_up():
    assert overlays.IDS == ("cpu", "ram", "gpu", "pomodoro")
    assert overlays.LABELS["gpu"] == "GPU" and overlays.ROW_NAMES["pomodoro"] == "shift row"
    assert set(overlays.ROW_CODES) == set(overlays.LABELS) == set(overlays.ROW_NAMES)


def test_unit_rejects_garbage():
    assert overlays.unit(0.5) == 0.5
    assert overlays.unit(-3) == 0.0 and overlays.unit(7) == 1.0
    for bad in (None, "x", float("nan")):
        assert overlays.unit(bad) is None


def test_load_ramp_goes_green_amber_red():
    assert overlays.color_for("cpu", 0.0) == (0, 210, 80)
    assert overlays.color_for("cpu", 0.65) == (255, 170, 0)
    assert overlays.color_for("gpu", 0.9) == (255, 30, 30)
    assert overlays.color_for("cpu", 1.0) == (255, 30, 30)
    mid = overlays.color_for("cpu", 0.325)
    assert mid == (128, 190, 40)                              # halfway green -> amber


def test_ram_uses_its_own_ramp_and_is_not_red_at_ordinary_use():
    assert overlays.color_for("ram", 0.0) == (0, 170, 255)
    assert overlays.color_for("ram", 0.75) == (110, 80, 255)
    r, g, b = overlays.color_for("ram", 0.75)
    assert b > r and b > g                                    # still blue at 75 %
    assert overlays.color_for("ram", 1.0) == (255, 40, 120)


def test_bar_levels_give_ten_steps_with_a_soft_edge():
    assert overlays.bar_levels(0.0, 10) == [0.0] * 10
    assert overlays.bar_levels(1.0, 10) == [1.0] * 10
    half = overlays.bar_levels(0.5, 10)
    assert half[:5] == [1.0] * 5 and half[5:] == [0.0] * 5
    soft = overlays.bar_levels(0.35, 10)
    assert soft[:3] == [1.0] * 3 and soft[3] == pytest.approx(0.5) and soft[4:] == [0.0] * 6
    assert overlays.bar_levels(None, 4) == [0.0] * 4
    assert overlays.bar_levels(float("nan"), 4) == [0.0] * 4


def test_paint_bar_replaces_the_row_and_leaves_other_keys_alone():
    frame = {i: (9, 9, 9) for i in range(6)}
    overlays.paint_bar(frame, [1, 2, 3, 4], 0.5, (200, 100, 0))
    assert frame[1] == frame[2] == (200, 100, 0)              # lit keys: the fill colour
    assert frame[3] == frame[4] == overlays.TRACK             # unlit keys: opaque track, not the effect
    assert frame[0] == frame[5] == (9, 9, 9)


def test_paint_bar_with_no_reading_shows_only_the_track():
    frame = {}
    overlays.paint_bar(frame, [5, 6], None, (255, 0, 0))
    assert frame == {5: overlays.TRACK, 6: overlays.TRACK}


def test_bar_edge_key_is_a_blend_of_track_and_fill():
    frame = {}
    overlays.paint_bar(frame, [0, 1], 0.25, (214, 14, 22))
    assert frame[0] == overlays.mix(overlays.TRACK, (214, 14, 22), 0.5)
    assert frame[1] == overlays.TRACK
