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
