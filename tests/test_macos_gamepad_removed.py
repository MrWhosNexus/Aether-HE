"""The Gamepad section must not exist in the macOS UI.

Two separate things can regress independently, so both are pinned:
  1. platform_info() — the backend answer the shell filters on. It must stay
     side-effect-free; gamepad_status() calls vigembus_present(), which builds
     a real VX360 pad on Windows, and nav chrome must never do that.
  2. The COMPILED runtime — ui/index_runtime.html is prebuilt and shipped. An
     edit to app.jsx that is never passed through build_runtime.py leaves the
     shipped UI stale, and no other test in this suite would notice.

Run: python -m pytest tests/test_macos_gamepad_removed.py
"""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import gamepad

APP_JSX = os.path.join(ROOT, "ui", "runtime_src", "src", "app.jsx")
RUNTIME = os.path.join(ROOT, "ui", "index_runtime.html")


@pytest.fixture
def api():
    import app_web
    return app_web.Api.__new__(app_web.Api)      # no __init__: no device, no threads


# ------------------------------------------------------------- backend
def test_platform_info_reports_macos_as_unsupported(api, monkeypatch):
    monkeypatch.setattr(gamepad, "_BACKEND", None)
    monkeypatch.setattr(gamepad.sys, "platform", "darwin")
    info = api.platform_info()
    assert info["ok"] is True
    assert info["gamepad_supported"] is False
    assert info["gamepad_installable"] is False
    assert "entitlement" in info["gamepad_reason"]


def test_platform_info_reports_supported_where_a_backend_exists(api, monkeypatch):
    """Contrast case — the filter must not hide the tab on Windows/Linux."""
    monkeypatch.setattr(gamepad, "_BACKEND", "evdev")
    assert api.platform_info()["gamepad_supported"] is True


def test_platform_info_never_probes_vigembus(api, monkeypatch):
    """Building a VX360 pad just to draw a nav bar is the phantom-pad defect.
    platform_info must answer from the backend table alone."""
    def _boom():
        raise AssertionError("platform_info called vigembus_present()")
    monkeypatch.setattr(gamepad, "vigembus_present", _boom)
    monkeypatch.setattr(gamepad, "_BACKEND", None)
    monkeypatch.setattr(gamepad.sys, "platform", "win32")
    assert api.platform_info()["ok"] is True      # would raise if it probed


# ----------------------------------------------------------------- UI
def test_app_jsx_filters_the_gamepad_section():
    src = open(APP_JSX, encoding="utf-8").read()
    assert "padSupported" in src, "app.jsx lost the platform capability state"
    # Upstream already filters the section list per board (sectionAllowed);
    # the platform gate rides the same filter.
    assert 'const padHidden = (id) => id === "gamepad" && padSupported === false;' in src, \
        "app.jsx no longer hides the gamepad section where the platform has no pad"
    assert "sectionAllowed(sdef.id, board) && !padHidden(sdef.id)" in src
    assert "sections={sectionDefs}" in src, "the top bar must render the filtered list"


def test_app_jsx_redirects_away_from_a_hidden_gamepad_section():
    """A profile persisted on Windows can carry section:'gamepad'. Without the
    redirect the user lands on a tab that is not in the nav and is stuck."""
    src = open(APP_JSX, encoding="utf-8").read()
    # Same fallback as a capability-gated tab: the (ungated) Dashboard.
    assert ('if (!sectionAllowed(section, board) || padHidden(section)) '
            'setSection("dashboard");') in src


def test_compiled_runtime_is_not_stale():
    """ui/index_runtime.html is the file that actually ships. If it predates the
    filter, macOS still shows a Gamepad tab no matter what app.jsx says."""
    assert os.path.exists(RUNTIME), "compiled runtime missing — run build_runtime.py"
    html = open(RUNTIME, encoding="utf-8", errors="replace").read()
    assert "padSupported" in html, (
        "compiled runtime does not contain the gamepad filter — "
        "run: python ui/runtime_src/build_runtime.py")
    assert "platform_info" in html, (
        "compiled runtime never calls platform_info — it cannot know the platform")


def test_unsupported_pad_still_refuses_loudly_if_constructed(monkeypatch):
    """Hiding the tab must not become the ONLY guard — the backend still has to
    refuse, since set_gamepad_capture is reachable over the bridge."""
    monkeypatch.setattr(gamepad, "_BACKEND", None)
    monkeypatch.setattr(gamepad.sys, "platform", "darwin")
    with pytest.raises(RuntimeError):
        gamepad.VirtualGamepad()


# ------------------------------------------- updater fallback message
def test_ui_shows_the_updaters_reason_for_a_download_only_update():
    """On macOS apply_update may only download (app not in /Applications,
    translocated, read-only volume) and says why in `message`. All three
    update surfaces must show it rather than a bare "Downloaded to <path>"."""
    src = os.path.join(ROOT, "ui", "runtime_src")
    sections = open(os.path.join(src, "src", "sections.jsx"), encoding="utf-8").read()
    assert "const updateDownloadedText = (r, fallback) =>" in sections
    assert "r.message" in sections
    for rel, call in (
            (("src", "sections.jsx"), 'updateDownloadedText(r, "Downloaded.")'),
            (("src", "app.jsx"), 'window.AetherSections.updateDownloadedText(r, "Downloaded.")'),
            (("workspaces", "settings.jsx"), 'S.updateDownloadedText(r, "Update complete")')):
        text = open(os.path.join(src, *rel), encoding="utf-8").read()
        assert call in text, f"{rel[-1]} does not show the updater's message"
        assert "`Downloaded to ${r.path}` :" not in text.replace(
            "const where = r && r.path ? `Downloaded to ${r.path}` : fallback;", "")
