import types, app_web
import json, os

def _api():
    # Construct Api without opening hardware: bypass __init__ side effects.
    a = app_web.Api.__new__(app_web.Api)
    return a

def test_list_hid_devices_shape(monkeypatch):
    fake = [{"path": b"\\?\\hid#1", "vendor_id": 0x2E3C, "product_id": 0xC365,
             "manufacturer_string": "Aula", "product_string": "Win60 HE",
             "usage_page": 0xFF1B, "interface_number": 2}]
    monkeypatch.setattr(app_web.hid, "enumerate", lambda *a, **k: fake)
    out = _api().list_hid_devices()
    assert out["ok"] is True
    d = out["devices"][0]
    assert d["vid"] == "0x2e3c" and d["pid"] == "0xc365"
    assert d["usage_page"] == "0xff1b" and d["interface_number"] == 2
    assert isinstance(d["path"], str)

def test_capture_is_read_only(monkeypatch):
    reads = {"n": 0}
    class FakeDev:
        def open_path(self, p): pass
        def set_nonblocking(self, v): pass
        def read(self, n, timeout_ms=0):
            reads["n"] += 1
            return [1, 0xab] if reads["n"] == 1 else []
        def close(self): pass
        # NOTE: intentionally no write / send_feature_report — a write would AttributeError
    monkeypatch.setattr(app_web.hid, "device", lambda: FakeDev())
    a = _api()
    assert a.open_capture("\\?\\hid#1")["ok"] is True
    import time; time.sleep(0.05)
    out = a.read_capture()
    assert out["ok"] is True
    assert any(r["hex"] for r in out["reports"])   # got the 01ab report
    assert a.stop_capture()["ok"] is True

def test_save_submission_validates_and_writes(monkeypatch, tmp_path):
    a = _api()
    monkeypatch.setattr(a, "_submissions_dir", lambda: str(tmp_path))
    good = {"schema": "aether-board-submission/1",
            "device": {"vid": "0x1", "pid": "0x2"},
            "meta": {"brand": "X", "model": "Y", "size": "60"},
            "input_capture": {"reports": []}}
    r = a.save_submission(good)
    assert r["ok"] is True and os.path.exists(r["path"])
    assert json.load(open(r["path"]))["meta"]["brand"] == "X"

def test_save_submission_rejects_invalid(monkeypatch, tmp_path):
    a = _api()
    monkeypatch.setattr(a, "_submissions_dir", lambda: str(tmp_path))
    r = a.save_submission({"schema": "wrong"})
    assert r["ok"] is False and r["errors"]
