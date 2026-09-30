"""boot: startup failures in the windowed exe must leave a log and a
visible error instead of a process that silently disappears."""
import logging
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import boot  # noqa: E402


def test_report_fatal_logs_and_shows_error(monkeypatch, tmp_path, caplog):
    shown = []
    monkeypatch.setattr(boot, "show_error", lambda text, title="": shown.append(text))
    monkeypatch.setattr(boot, "_log_path", str(tmp_path / "aether.log"))
    try:
        raise ImportError("DLL load failed while importing hid")
    except ImportError:
        with caplog.at_level(logging.CRITICAL):
            boot.report_fatal(*sys.exc_info())
    assert "uncaught exception" in caplog.text
    assert len(shown) == 1
    assert "DLL load failed" in shown[0] and "aether.log" in shown[0]


def test_keyboard_interrupt_is_not_an_error_box(monkeypatch):
    shown = []
    monkeypatch.setattr(boot, "show_error", lambda *a, **k: shown.append(a))
    boot.report_fatal(KeyboardInterrupt, KeyboardInterrupt(), None)
    assert shown == []


def test_user_data_dir_honours_xdg(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    d = boot.user_data_dir()
    assert d == str(tmp_path / "AetherHE") and os.path.isdir(d)


def test_boot_is_stdlib_only():
    """boot is imported before hid/webview precisely so it can report their
    failure — it must not import anything third-party itself."""
    src = open(os.path.join(ROOT, "boot.py"), encoding="utf-8").read()
    for mod in ("hid", "webview", "pystray", "PIL", "vgamepad"):
        assert f"import {mod}" not in src
