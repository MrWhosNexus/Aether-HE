import io, json, types
import tools.minimax_client as mc

def test_missing_key_raises(monkeypatch):
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    try:
        mc.complete("hi", key=None)
        assert False, "should have raised"
    except RuntimeError as e:
        assert "MINIMAX_API_KEY" in str(e)

def test_builds_request_and_parses(monkeypatch):
    captured = {}
    class FakeResp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False
    def fake_urlopen(req, timeout=0):
        captured["url"] = req.full_url
        captured["auth"] = req.headers.get("Authorization")
        captured["body"] = json.loads(req.data.decode())
        r = FakeResp(json.dumps({"choices": [{"message": {"content": "DRAFT"}}]}).encode())
        return r
    monkeypatch.setattr(mc.urllib.request, "urlopen", fake_urlopen)
    out = mc.complete("make a board", key="secret123", model="MiniMax-M3",
                      base_url="https://example.test/v1")
    assert out == "DRAFT"
    assert captured["url"] == "https://example.test/v1/chat/completions"
    assert captured["auth"] == "Bearer secret123"
    assert captured["body"]["model"] == "MiniMax-M3"
    assert captured["body"]["messages"][0]["content"] == "make a board"
