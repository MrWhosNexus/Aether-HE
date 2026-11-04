"""Phase 6 / Task 4: per-profile toggles in settings.json and the OverlayManager
(availability, sampler lifecycle, the get_overlays rows). Fakes only."""
import json
import threading

import pytest

import overlays

ROWS = {"cpu": list(range(0, 10)), "ram": list(range(10, 20)), "gpu": list(range(20, 30)),
        "pomodoro": list(range(30, 42))}
ALL = list(range(42))


@pytest.fixture(autouse=True)
def _never_spawn_nvidia_smi(monkeypatch):
    def boom(exe):
        raise AssertionError("a test tried to run the real nvidia-smi")
    monkeypatch.setattr(overlays, "_run_nvidia_smi", boom)


class FakeGpu:
    def __init__(self, available=True, value=0.3):
        self.available, self.value = available, value
        self.reason = None if available else "nvidia-smi not found (NVIDIA GPU only)"

    def read(self):
        return self.value


def _mgr(tmp_path, rows=ROWS, cpu=lambda: (0, 1), mem=lambda: 0.5, gpu=None, **kw):
    path = str(tmp_path / "settings.json")
    m = overlays.OverlayManager(rows, ALL, path, threading.Lock(), cpu=cpu, mem=mem,
                                gpu=gpu or FakeGpu(), interval=0.01, **kw)
    return m, path


def _read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---- preferences ---------------------------------------------------------------
def test_missing_or_corrupt_settings_mean_everything_off(tmp_path):
    p = tmp_path / "settings.json"
    assert overlays.load_prefs(str(p)) == {"profiles": {}, "pomodoro": {}}
    p.write_text("{not json", encoding="utf-8")
    assert overlays.load_prefs(str(p)) == {"profiles": {}, "pomodoro": {}}
    assert overlays.toggles_for({"profiles": {}}, "p1") == {k: False for k in overlays.IDS}


def test_save_toggle_keeps_every_other_setting(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"profiles": [{"id": "p1"}], "activeProfile": "p1", "autoUpdate": True}),
                 encoding="utf-8")
    overlays.save_toggle(str(p), threading.Lock(), "p1", "cpu", True)
    overlays.save_toggle(str(p), threading.Lock(), "p2", "gpu", True)
    data = _read(str(p))
    assert data["autoUpdate"] is True and data["activeProfile"] == "p1"
    assert data["overlays"]["profiles"] == {"p1": {"cpu": True}, "p2": {"gpu": True}}
    prefs = overlays.load_prefs(str(p))
    assert overlays.toggles_for(prefs, "p1") == {"cpu": True, "ram": False, "gpu": False, "pomodoro": False}


def test_malformed_prefs_are_dropped_not_trusted(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"overlays": {"profiles": {"p1": "yes", "x" * 65: {"cpu": True},
                                                       "": {"cpu": True}, "ok": {"cpu": 1, "evil": True}},
                                          "pomodoro": {"workMin": "lots", "breakMin": True}}}),
                 encoding="utf-8")
    prefs = overlays.load_prefs(str(p))
    assert list(prefs["profiles"]) == ["ok"] and prefs["profiles"]["ok"] == {
        "cpu": True, "ram": False, "gpu": False, "pomodoro": False}
    assert prefs["pomodoro"] == {}


def test_pomodoro_length_comes_from_settings_with_sane_limits():
    assert overlays.pomodoro_seconds({}) == (1500.0, 300.0)
    assert overlays.pomodoro_seconds({"pomodoro": {"workMin": 50, "breakMin": 10}}) == (3000.0, 600.0)
    assert overlays.pomodoro_seconds({"pomodoro": {"workMin": 0, "breakMin": 999}}) == (60.0, 3600.0)


# ---- manager -------------------------------------------------------------------
def test_a_new_profile_starts_with_everything_off_and_no_sampler(tmp_path):
    m, _ = _mgr(tmp_path)
    m.follow_profile("p1")
    assert not m.any_on() and not m.sampler.running
    st = m.status()
    assert [o["id"] for o in st["overlays"]] == ["cpu", "ram", "gpu", "pomodoro"]
    assert all(o["on"] is False and o["available"] for o in st["overlays"])
    assert st["pomodoro"] == {"phase": None, "remaining_s": None}


def test_set_persists_per_profile_and_follows_the_profile(tmp_path):
    m, path = _mgr(tmp_path)
    m.follow_profile("p1")
    assert m.set("cpu", True) == {"ok": True, "id": "cpu", "on": True}
    assert m.sampler.running                                   # sampler runs while a sensor is on
    m.follow_profile("p2")                                     # another profile: all off, sampler stops
    assert not m.any_on() and not m.sampler.running
    m.set("pomodoro", True)
    m.follow_profile("p1")
    assert m.layer.enabled("cpu") and not m.layer.enabled("pomodoro")
    assert _read(path)["overlays"]["profiles"] == {"p1": {"cpu": True}, "p2": {"pomodoro": True}}
    m.close()
    fresh, _ = _mgr(tmp_path)                                  # a restart reads the same file
    fresh.follow_profile("p1")
    assert fresh.layer.enabled("cpu")
    fresh.close()


def test_pomodoro_alone_needs_no_sampler(tmp_path):
    m, _ = _mgr(tmp_path)
    m.follow_profile("p1")
    m.set("pomodoro", True)
    assert m.any_on() and not m.sampler.running
    st = m.status()
    pomo = [o for o in st["overlays"] if o["id"] == "pomodoro"][0]
    assert pomo["on"] and pomo["phase"] == "work" and pomo["remaining_s"] == 1500
    assert st["pomodoro"]["phase"] == "work"
    m.set("pomodoro", False)
    assert not m.any_on()


def test_pomodoro_length_is_read_from_settings(tmp_path):
    (tmp_path / "settings.json").write_text(
        json.dumps({"overlays": {"pomodoro": {"workMin": 50, "breakMin": 10}}}), encoding="utf-8")
    m, _ = _mgr(tmp_path)
    assert (m.layer.pomodoro.work_s, m.layer.pomodoro.break_s) == (3000.0, 600.0)


def test_gpu_without_nvidia_smi_is_unavailable_with_a_reason(tmp_path):
    m, _ = _mgr(tmp_path, gpu=FakeGpu(available=False))
    m.follow_profile("p1")
    gpu = [o for o in m.status()["overlays"] if o["id"] == "gpu"][0]
    assert gpu["available"] is False and "nvidia-smi" in gpu["reason"] and gpu["on"] is False
    res = m.set("gpu", True)
    assert res["ok"] is False and "nvidia-smi" in res["error"]
    assert not m.any_on()
    assert not (tmp_path / "settings.json").exists()           # a refused toggle is never saved


def test_a_stored_gpu_choice_is_not_drawn_while_unavailable(tmp_path):
    m, _ = _mgr(tmp_path, gpu=FakeGpu(available=False))
    (tmp_path / "settings.json").write_text(
        json.dumps({"overlays": {"profiles": {"p1": {"gpu": True, "cpu": True}}}}), encoding="utf-8")
    m.follow_profile("p1")
    assert m.layer.enabled("cpu") and not m.layer.enabled("gpu")
    m.close()


def test_a_probe_that_gives_up_turns_the_overlay_off_in_the_next_status(tmp_path):
    gpu = FakeGpu()
    m, _ = _mgr(tmp_path, gpu=gpu)
    m.follow_profile("p1")
    m.set("gpu", True)
    assert m.layer.enabled("gpu")
    gpu.available, gpu.reason = False, "nvidia-smi is not answering"
    st = m.status()
    row = [o for o in st["overlays"] if o["id"] == "gpu"][0]
    assert row["on"] is False and row["available"] is False and not m.layer.enabled("gpu")
    m.close()


def test_cpu_and_ram_are_unavailable_when_the_platform_cannot_read_them(tmp_path):
    m, _ = _mgr(tmp_path, cpu=lambda: None, mem=lambda: None)
    m.follow_profile("p1")
    rows = {o["id"]: o for o in m.status()["overlays"]}
    assert rows["cpu"]["available"] is False and "CPU" in rows["cpu"]["reason"]
    assert rows["ram"]["available"] is False and "RAM" in rows["ram"]["reason"]
    assert rows["pomodoro"]["available"] is True
    assert m.set("cpu", True)["ok"] is False


def test_a_layout_without_the_row_is_unavailable(tmp_path):
    rows = dict(ROWS, pomodoro=ROWS["pomodoro"][:5])
    m, _ = _mgr(tmp_path, rows=rows)
    row = [o for o in m.status()["overlays"] if o["id"] == "pomodoro"][0]
    assert row["available"] is False and "shift row" in row["reason"]


def test_unknown_overlay_id_is_refused_without_raising(tmp_path):
    m, _ = _mgr(tmp_path)
    assert m.set("fan", True)["ok"] is False


def test_status_rows_carry_the_dashboard_contract_fields(tmp_path):
    m, _ = _mgr(tmp_path)
    m.follow_profile("p1")
    m.set("cpu", True)
    m.layer.set_value("cpu", 0.42)
    row = m.status()["overlays"][0]
    assert set(row) == {"id", "label", "row", "on", "available", "reason", "value"}
    assert row["label"] == "CPU" and row["row"] == "number row" and row["value"] == 0.42
    m.close()
