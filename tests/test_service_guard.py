"""Request guard for the loopback service (service/guard.py)."""
import http.client
import json
import sys
import threading
import types

from service import guard

H = {"Host": "127.0.0.1:8672"}


def test_allows_loopback_backend_request():
    assert guard.check_request(H, 8672) is None


def test_rejects_browser_origin():
    assert guard.check_request({**H, "Origin": "https://evil.example"}, 8672)


def test_allows_listed_origin():
    assert guard.check_request({**H, "Origin": "app://nexus"}, 8672,
                               allowed_origins=frozenset({"app://nexus"})) is None


def test_rejects_rebound_host():
    assert guard.check_request({"Host": "evil.example:8672"}, 8672)


def test_rejects_missing_host():
    assert guard.check_request({}, 8672)


def test_host_variants():
    assert guard.check_request({"Host": "LOCALHOST:8672"}, 8672) is None
    assert guard.check_request({"Host": "[::1]:8672"}, 8672) is None
    assert guard.check_request({"Host": "127.0.0.1:80"}, 8672)


def test_token_required_when_configured():
    assert guard.check_request(H, 8672, token="s3cret")
    assert guard.check_request({**H, "X-Aether-Token": "nope"}, 8672, token="s3cret")
    assert guard.check_request({**H, "X-Aether-Token": "s3cret"}, 8672, token="s3cret") is None


def test_config_from_env(monkeypatch):
    monkeypatch.setenv("AETHER_SERVICE_ORIGINS", "app://nexus, ,http://localhost:5173")
    monkeypatch.setenv("AETHER_SERVICE_TOKEN", "")
    assert guard.config_from_env() == (frozenset({"app://nexus", "http://localhost:5173"}), None)


def test_server_refuses_cross_origin_post_without_calling_api(monkeypatch):
    calls = []

    class StubApi:
        def __getattr__(self, name):
            def rec(*a, **k):
                calls.append(name)
                return {"ok": True}
            return rec

    monkeypatch.setitem(sys.modules, "app_web", types.SimpleNamespace(Api=StubApi))
    monkeypatch.delitem(sys.modules, "service.server", raising=False)
    from http.server import ThreadingHTTPServer
    from service import server

    srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    body = json.dumps({"codes": [1], "travel_mm": 2.0})
    try:
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        c.request("POST", "/aether/trigger", body,
                  {"Origin": "https://evil.example", "Content-Type": "text/plain"})
        r = c.getresponse()
        data = json.loads(r.read())
        assert r.status == 403
        assert data["ok"] is False
        assert "set_trigger_codes" not in calls
        c.close()

        c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        c.request("POST", "/aether/trigger", body)
        r = c.getresponse()
        r.read()
        assert r.status == 200
        assert "set_trigger_codes" in calls
        c.close()
    finally:
        srv.shutdown()
        srv.server_close()
        sys.modules.pop("service.server", None)


def test_refused_request_cannot_smuggle_a_second_request_in_its_body(monkeypatch):
    """Security review 2026-11-04: the 403 path did not read the POST body and
    left the HTTP/1.1 connection open, so the body was parsed as a NEXT request
    with no Origin and a loopback Host, which passed the guard. A page could
    send that with fetch(..., {mode: "no-cors", body: inner})."""
    import socket
    calls = []

    class StubApi:
        def __getattr__(self, name):
            def rec(*a, **k):
                calls.append(name)
                return {"ok": True}
            return rec

    monkeypatch.setitem(sys.modules, "app_web", types.SimpleNamespace(Api=StubApi))
    monkeypatch.delitem(sys.modules, "service.server", raising=False)
    from http.server import ThreadingHTTPServer
    from service import server

    srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    inner_body = b'{"codes": ["KeyA"], "travel_mm": 0.1}'
    inner = (b"POST /aether/trigger HTTP/1.1\r\nHost: 127.0.0.1:%d\r\n"
             b"Content-Length: %d\r\n\r\n" % (port, len(inner_body))) + inner_body
    outer = (b"POST /aether/light/stop HTTP/1.1\r\nHost: 127.0.0.1:%d\r\n"
             b"Origin: https://evil.example\r\nContent-Type: text/plain;charset=UTF-8\r\n"
             b"Content-Length: %d\r\n\r\n" % (port, len(inner))) + inner
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=5)
        s.sendall(outer)
        got = b""
        s.settimeout(1.5)
        try:
            while True:
                chunk = s.recv(65536)
                if not chunk:
                    break
                got += chunk
        except socket.timeout:
            pass
        s.close()
        assert b" 403 " in got.split(b"\r\n", 1)[0]
        assert b" 200 " not in got, "a smuggled request was answered"
        assert "set_trigger_codes" not in calls
        assert "stop_multicolor" not in calls
    finally:
        srv.shutdown()
        srv.server_close()
        sys.modules.pop("service.server", None)
