"""Api.save_settings must PRESERVE top-level keys the UI does not own.

Regression guard for a real bug: save_settings wrote the UI's blob verbatim, so
`autoUpdate` — written by set_auto_update() when the user answers the first-run
update prompt — was erased by the next profile/theme save. The app then treated
the user as first-run again and re-prompted on every launch.

The fix merges instead of replacing, so this covers the whole class: any setting
written by a different code path survives a UI save.

Run: python -m pytest tests/test_settings_merge.py
"""
import json
import os
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import app_web


def _api(tmp):
    """A bare Api with only the settings path stubbed — no HID, no webview."""
    a = app_web.Api.__new__(app_web.Api)
    a._settings_path = types.MethodType(lambda self: os.path.join(tmp, "settings.json"), a)
    return a


def test_save_settings_preserves_unowned_keys():
    """The exact reported bug: a UI save must not drop autoUpdate."""
    with tempfile.TemporaryDirectory() as tmp:
        a = _api(tmp)
        path = a._settings_path()
        # written by set_auto_update(), NOT part of the UI's blob
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"autoUpdate": False, "updateSkipped": "1.2.3"}, f)

        r = a.save_settings({"profiles": [{"name": "Default"}], "theme": "dark"})
        assert r["ok"] is True

        with open(path, encoding="utf-8") as f:
            out = json.load(f)
        assert out["autoUpdate"] is False, "autoUpdate was dropped by a UI save"
        assert out["updateSkipped"] == "1.2.3", "sibling key was dropped"
        assert out["theme"] == "dark" and out["profiles"][0]["name"] == "Default"


def test_ui_keys_win_on_conflict():
    """Merging must not resurrect a stale value the UI is actively changing."""
    with tempfile.TemporaryDirectory() as tmp:
        a = _api(tmp)
        with open(a._settings_path(), "w", encoding="utf-8") as f:
            json.dump({"theme": "light", "autoUpdate": True}, f)
        a.save_settings({"theme": "dark"})
        with open(a._settings_path(), encoding="utf-8") as f:
            out = json.load(f)
        assert out["theme"] == "dark", "the UI's own value must win"
        assert out["autoUpdate"] is True


def test_missing_file_is_not_an_error():
    with tempfile.TemporaryDirectory() as tmp:
        a = _api(tmp)
        r = a.save_settings({"theme": "dark"})
        assert r["ok"] is True
        with open(a._settings_path(), encoding="utf-8") as f:
            assert json.load(f) == {"theme": "dark"}


def test_corrupt_file_does_not_block_the_save():
    """A damaged settings.json must not make the app unable to save — matches
    the updater's own tolerance rather than failing the write."""
    with tempfile.TemporaryDirectory() as tmp:
        a = _api(tmp)
        with open(a._settings_path(), "w", encoding="utf-8") as f:
            f.write("{ this is not json")
        r = a.save_settings({"theme": "dark"})
        assert r["ok"] is True
        with open(a._settings_path(), encoding="utf-8") as f:
            assert json.load(f) == {"theme": "dark"}


def test_non_dict_file_is_treated_as_empty():
    with tempfile.TemporaryDirectory() as tmp:
        a = _api(tmp)
        with open(a._settings_path(), "w", encoding="utf-8") as f:
            json.dump(["not", "a", "dict"], f)
        assert a.save_settings({"theme": "dark"})["ok"] is True
        with open(a._settings_path(), encoding="utf-8") as f:
            assert json.load(f) == {"theme": "dark"}
