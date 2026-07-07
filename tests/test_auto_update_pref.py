"""Tests for the auto-update-on-launch preference helpers in updater.py.

These are stdlib-only and take an explicit settings path, so they run without
importing app_web (which pulls in the native `hid` module). They cover the
first-run (None) state, round-tripping True/False, and the merge guarantee that
setting the flag never clobbers sibling keys in settings.json.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import updater


def test_missing_file_is_first_run_none(tmp_path):
    p = tmp_path / "settings.json"
    assert updater.get_auto_update(str(p)) is None


def test_absent_key_is_none(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"theme": "dark"}), encoding="utf-8")
    assert updater.get_auto_update(str(p)) is None


def test_set_true_then_get_true(tmp_path):
    p = tmp_path / "settings.json"
    assert updater.set_auto_update(str(p), True) is True
    assert updater.get_auto_update(str(p)) is True


def test_set_false_then_get_false(tmp_path):
    p = tmp_path / "settings.json"
    updater.set_auto_update(str(p), True)
    assert updater.set_auto_update(str(p), False) is False
    assert updater.get_auto_update(str(p)) is False


def test_set_preserves_sibling_keys(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"theme": "dark", "poll": 1000}), encoding="utf-8")
    updater.set_auto_update(str(p), True)
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["autoUpdate"] is True
    assert data["theme"] == "dark"      # sibling keys untouched
    assert data["poll"] == 1000


def test_set_coerces_truthy_to_bool(tmp_path):
    p = tmp_path / "settings.json"
    updater.set_auto_update(str(p), 1)   # non-bool truthy
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["autoUpdate"] is True    # stored as a real bool


def test_corrupt_file_reads_as_none(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text("{not valid json", encoding="utf-8")
    assert updater.get_auto_update(str(p)) is None


def test_set_on_corrupt_file_starts_clean(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text("{not valid json", encoding="utf-8")
    assert updater.set_auto_update(str(p), True) is True
    assert json.loads(p.read_text(encoding="utf-8"))["autoUpdate"] is True


def test_non_dict_json_is_none(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    assert updater.get_auto_update(str(p)) is None
