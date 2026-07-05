import types, app_web

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
