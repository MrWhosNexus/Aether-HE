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

def test_list_hid_devices_collapses_by_interface(monkeypatch):
    # Same physical board exposed as 4 usage collections across 2 interfaces:
    # iface 1 appears 3x (three usage pages), iface 2 once. Expect 2 rows.
    fake = [
        {"path": b"p1", "vendor_id": 0x2E3C, "product_id": 0xC365, "product_string": "Win60 HE",
         "usage_page": 0x0001, "interface_number": 1},
        {"path": b"p2", "vendor_id": 0x2E3C, "product_id": 0xC365, "product_string": "Win60 HE",
         "usage_page": 0x000C, "interface_number": 1},
        {"path": b"p3", "vendor_id": 0x2E3C, "product_id": 0xC365, "product_string": "Win60 HE",
         "usage_page": 0x0001, "interface_number": 1},
        {"path": b"p4", "vendor_id": 0x2E3C, "product_id": 0xC365, "product_string": "Win60 HE",
         "usage_page": 0xFF1B, "interface_number": 2},
    ]
    monkeypatch.setattr(app_web.hid, "enumerate", lambda *a, **k: fake)
    devs = _api().list_hid_devices()["devices"]
    assert len(devs) == 2                                  # collapsed, not 4
    i1 = next(d for d in devs if d["interface_number"] == 1)
    assert i1["path"] == "p1"                              # first path kept
    assert i1["usage_pages"] == ["0x0001", "0x000c"]       # de-duped, ordered
    i2 = next(d for d in devs if d["interface_number"] == 2)
    assert i2["usage_pages"] == ["0xff1b"]

def test_capture_dedupes_and_caps(monkeypatch):
    # Stream: A A B B (only 2 transitions) then keep emitting to test the cap.
    seq = [[1, 0], [1, 0], [2, 0], [2, 0]]
    box = {"i": 0}
    class FakeDev:
        def open_path(self, p): pass
        def set_nonblocking(self, v): pass
        def read(self, n, timeout_ms=0):
            i = box["i"]; box["i"] += 1
            return seq[i] if i < len(seq) else [box["i"] % 7 + 3, 0]  # always-changing tail
        def close(self): pass
    monkeypatch.setattr(app_web.hid, "device", lambda: FakeDev())
    monkeypatch.setattr(app_web.Api, "_CAP_MAX_REPORTS", 5)
    a = _api()
    a.open_capture("p")
    import time; time.sleep(0.1); a.stop_capture()
    reps = a.read_capture()["reports"]
    assert len(reps) <= 5                                  # hard cap honored
    hexes = [r["hex"] for r in reps]
    assert all(hexes[i] != hexes[i - 1] for i in range(1, len(hexes)))  # no consecutive dupes

def test_capture_arms_stream_only_for_recognized_board(monkeypatch):
    import threading, protocol
    writes = []
    class FakeRaw:
        def set_nonblocking(self, v): pass
        def read(self, n): return []
        def close(self): pass
    class FakeAula:  # stand-in for AulaDevice (the app's shared handle)
        def __init__(self): self._dev = FakeRaw(); self._lock = threading.Lock()
        def is_open(self): return True
        def write(self, b): writes.append(bytes(b)); return len(b)
    # Fresh read-only handle used only for the unknown-board path.
    freshes = []
    class FreshDev:
        def open_path(self, p): pass
        def set_nonblocking(self, v): pass
        def write(self, b): writes.append(bytes(b)); return len(b)   # must never be called
        def read(self, n, timeout_ms=0): return []
        def close(self): freshes.append("closed")
    monkeypatch.setattr(app_web.hid, "device", lambda: FreshDev())
    a = _api()
    a.board = types.SimpleNamespace(vid=0x2E3C, pid=0xC365)
    a.km = types.SimpleNamespace(indices=lambda: [0, 1, 2])
    a.dev = FakeAula()
    a.reader = None

    # Matching board -> shared handle, arms Travel-Test on open, disarms on stop,
    # and NEVER closes the app's device.
    a.open_capture("p", "0x2e3c", "0xc365")
    assert a._cap_shared is True
    assert writes and writes[0] == bytes(protocol.build_open_trigger_test([0, 1, 2]))
    a.stop_capture()
    assert writes[-1] == bytes(protocol.build_close_trigger_test())
    assert freshes == []                      # app handle never closed

    # Non-matching device -> fresh read-only handle, never written to.
    writes.clear()
    a.open_capture("p", "0x9999", "0x0001")
    assert a._cap_shared is False
    a.stop_capture()
    assert writes == []                       # zero writes on unknown hardware
    assert freshes == ["closed"]              # fresh handle opened and closed

def test_capture_bounds_held_key_flood(monkeypatch):
    import threading
    def travel_frame(row, col, depth):
        b = [0] * 64
        b[0] = 1; b[1] = 33; b[5] = 5; b[7] = row; b[8] = col
        b[9] = depth & 0xFF; b[10] = (depth >> 8) & 0xFF
        return b
    calls = {"i": 0}
    class FakeRaw:
        def set_nonblocking(self, v): pass
        def read(self, n):
            # Same key (2,2) held: depth jitters every sample, so full frames all
            # differ — a frame-level filter would never dedup these.
            i = calls["i"]; calls["i"] += 1
            return travel_frame(2, 2, 100 + (i % 5)) if i < 200 else []
        def close(self): pass
    class FakeAula:
        def __init__(self): self._dev = FakeRaw(); self._lock = threading.Lock()
        def is_open(self): return True
        def write(self, b): return len(b)
    a = _api()
    a.board = types.SimpleNamespace(vid=0x2E3C, pid=0xC365)
    a.km = types.SimpleNamespace(indices=lambda: [0, 1, 2])
    a.dev = FakeAula(); a.reader = None
    monkeypatch.setattr(app_web.Api, "_CAP_MAX_PER_KEY", 3)
    a.open_capture("p", "0x2e3c", "0xc365")
    import time; time.sleep(0.1); a.stop_capture()
    reps = a.read_capture()["reports"]
    assert len(reps) == 3          # one held key bounded to _CAP_MAX_PER_KEY, not 200
    assert all(r["hex"][14:18] == "0202" for r in reps)  # all the same key (row=2,col=2)

def test_save_submission_trims_whitespace(monkeypatch, tmp_path):
    a = _api()
    monkeypatch.setattr(a, "_submissions_dir", lambda: str(tmp_path))
    r = a.save_submission({"schema": "aether-board-submission/1",
                           "device": {"vid": "0x1", "pid": "0x2"},
                           "meta": {"brand": "Aula ", "model": " Win60 ", "size": "60"},
                           "input_capture": {"reports": []}})
    assert r["ok"] is True
    m = json.load(open(r["path"]))["meta"]
    assert m["brand"] == "Aula" and m["model"] == "Win60"

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
