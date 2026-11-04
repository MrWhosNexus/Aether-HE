"""Phase 7 UI wiring guards for the "music" effect (JSX read as text). The
Phase 2 guards in test_pressure_ui_sources.py already pin HOST_FX_IDS to the
engine table and HOST_FX_FAST to PRESS_REACTIVE."""
import re

import effects
from test_pressure_effect import _engine
from test_pressure_ui_sources import _list_ids, _read, _set_ids


def _lighting():
    return _read("workspaces", "lighting.jsx")


def test_music_is_offered_in_every_effect_list():
    for rel in (("workspaces", "lighting.jsx"), ("src", "sections.jsx")):
        text = _read(*rel)
        assert "music" in _list_ids(text, "LIGHT_MODES"), rel
        assert "music" in _list_ids(text, "ZONE_MODES"), rel


def test_music_is_a_host_effect_but_not_press_reactive():
    assert "music" in _engine()._gens
    assert "music" in _set_ids(_lighting(), "HOST_FX_IDS")
    assert "music" not in effects.PRESS_REACTIVE
    assert "music" not in _set_ids(_lighting(), "HOST_FX_FAST")


def test_music_previews_as_a_wave():
    assert re.search(r'pattern === "music"\) return "wave"', _lighting())


def test_mode_picker_shows_music_availability_without_hiding_it():
    text = _lighting()
    assert 'apiCall("music_status")' in text
    assert "useMusicStatus(ctx.apiCall, pattern === \"music\")" in text
    assert "disabled={musicOff}" in text
    assert "title={musicOff ? musicSt.reason" in text
    assert "data-music-note" in text


def test_music_status_poll_is_cleaned_up():
    text = _lighting()
    body = text[text.index("function useMusicStatus"):text.index("const musicNoteOf")]
    assert "setInterval(load, MUSIC_POLL_MS)" in body and "clearInterval(id)" in body
    assert "alive = false" in body
