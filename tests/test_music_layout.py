"""Phase 7: 14 bands -> keyboard columns (KeyMap x/y), and the dependency /
platform availability check. Pure: no numpy, no soundcard, no device."""
import device_state
import music


def _layout():
    km = device_state.KeyMap()
    pos = {i: (e["x"], e["y"]) for i, e in km.by_index.items()}
    return km, music.grid_layout(pos)


def _at(km, lay, code):
    return lay[km.index_of_code[code]]


def test_every_win60_key_is_mapped_onto_five_rows():
    km, lay = _layout()
    assert set(lay) == set(km.by_index)
    assert {m[2] for m in lay.values()} == {5}
    assert {m[1] for m in lay.values()} == {0, 1, 2, 3, 4}
    for bands, row, _ in lay.values():
        assert bands and all(0 <= b < 14 for b in bands)


def test_rows_count_from_the_bottom():
    km, lay = _layout()
    assert _at(km, lay, "Space")[1] == 0
    assert _at(km, lay, "Escape")[1] == 4
    assert _at(km, lay, "Q")[1] == 3


def test_number_and_qwerty_rows_cover_all_fourteen_columns_left_to_right():
    km, lay = _layout()
    for first, last in (("Escape", "Backspace"), ("Tab", "Bsl")):
        row = _at(km, lay, first)[1]
        keys = sorted((km.by_index[i]["x"], lay[i][0]) for i in lay if lay[i][1] == row)
        covered = set(b for _, bands in keys for b in bands)
        assert covered == set(range(14)), (first, covered)
        flat = [b for _, bands in keys for b in bands]
        assert flat == sorted(flat)
    assert _at(km, lay, "Escape")[0] == (0,)
    assert _at(km, lay, "Tab")[0] == (0,)
    assert 13 in _at(km, lay, "Backspace")[0]
    assert _at(km, lay, "Bsl")[0] == (13,)


def test_space_bar_averages_several_columns():
    km, lay = _layout()
    assert len(_at(km, lay, "Space")[0]) >= 4


def test_layout_is_generic_for_other_grids():
    pos = {i: (float(i % 8), float(i // 8)) for i in range(16)}   # 2 x 8 grid
    lay = music.grid_layout(pos)
    assert {m[2] for m in lay.values()} == {2}
    assert lay[0][1] == 1 and lay[8][1] == 0
    assert set(b for m in lay.values() if m[1] == 1 for b in m[0]) == set(range(14))
    assert music.grid_layout({}) == {}


def test_single_key_board_does_not_divide_by_zero():
    lay = music.grid_layout({5: (10.0, 3.0)})
    assert lay[5][1] == 0 and lay[5][2] == 1 and lay[5][0]


# ---------------------------------------------------------- availability ----
def _spec(present):
    return lambda name: object() if name in present else None


def test_available_on_windows_with_both_packages():
    assert music.availability("win32", _spec({"numpy", "soundcard"})) == (True, None)


def test_unavailable_off_windows_with_a_clear_reason():
    ok, why = music.availability("linux", _spec({"numpy", "soundcard"}))
    assert ok is False and "Windows" in why


def test_unavailable_names_the_missing_packages():
    assert music.availability("win32", _spec({"numpy"})) == (
        False, "Music visualizer needs the soundcard package (not installed).")
    assert music.availability("win32", _spec(set())) == (
        False, "Music visualizer needs the numpy and soundcard packages (not installed).")


def test_availability_never_imports_the_packages():
    import sys
    before = {m for m in ("numpy", "soundcard") if m in sys.modules}
    music.availability("win32")              # real importlib.util.find_spec
    after = {m for m in ("numpy", "soundcard") if m in sys.modules}
    assert after == before


def test_a_broken_find_spec_counts_as_missing():
    def boom(name):
        raise ValueError("bad spec")
    ok, why = music.availability("win32", boom)
    assert ok is False and "numpy and soundcard" in why
