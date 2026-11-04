"""Phase 3: the Discord list cache and its downloader. The network is never
touched: the store gets an injected fetcher, and fetch_url gets a fake
urlopen that serves the committed fixture."""
import gzip
import json
import os

import pytest

import games
from test_games_index import STARFALL, _fixture_bytes


class Clock:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


class FakeResponse:
    def __init__(self, body, headers=None, url=games.DETECTABLE_URL):
        self._body, self._pos = body, 0
        self.headers = dict(headers or {})
        self._url = url
        self.reads = 0

    def read(self, n=-1):
        self.reads += 1
        if n is None or n < 0:
            n = len(self._body) - self._pos
        chunk = self._body[self._pos:self._pos + n]
        self._pos += len(chunk)
        return chunk

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _opener(resp, seen=None):
    def urlopen(req, timeout=None, context=None):
        if seen is not None:
            seen.update(url=req.full_url, timeout=timeout, context=context,
                        headers=dict(req.header_items()))
        return resp
    return urlopen


# ---------------------------------------------------------------- fetch_url --
def test_fetch_uses_verified_tls_and_a_timeout():
    seen = {}
    body = games.fetch_url(games.DETECTABLE_URL, 1 << 20,
                           urlopen=_opener(FakeResponse(_fixture_bytes()), seen))
    assert body == _fixture_bytes()
    assert seen["timeout"] == games.FETCH_TIMEOUT_S
    ctx = seen["context"]
    assert ctx.check_hostname is True and ctx.verify_mode == games.ssl.CERT_REQUIRED
    assert seen["headers"].get("Accept-encoding") == "gzip"


def test_fetch_refuses_plain_http_and_https_downgrade_redirects():
    with pytest.raises(ValueError):
        games.fetch_url("http://discord.com/x", 100, urlopen=_opener(FakeResponse(b"[]")))
    resp = FakeResponse(b"[]", url="http://evil.example/x")
    with pytest.raises(ValueError):
        games.fetch_url(games.DETECTABLE_URL, 100, urlopen=_opener(resp))


def test_fetch_cap_is_enforced_while_streaming():
    resp = FakeResponse(b"x" * 300_000)                # no Content-Length header
    with pytest.raises(ValueError, match="larger than"):
        games.fetch_url(games.DETECTABLE_URL, 100_000, urlopen=_opener(resp))
    assert resp.reads <= 3                             # stopped early, not read to the end


def test_fetch_rejects_a_declared_oversize_body_before_reading():
    resp = FakeResponse(b"[]", headers={"Content-Length": str(6 * 1024 * 1024)})
    with pytest.raises(ValueError):
        games.fetch_url(games.DETECTABLE_URL, games.MAX_DETECTABLE_BYTES, urlopen=_opener(resp))
    assert resp.reads == 0


def test_fetch_unpacks_gzip_with_its_own_cap(monkeypatch):
    gz = gzip.compress(_fixture_bytes())
    resp = FakeResponse(gz, headers={"Content-Encoding": "gzip"})
    assert games.fetch_url(games.DETECTABLE_URL, 1 << 20, urlopen=_opener(resp)) == _fixture_bytes()
    monkeypatch.setattr(games, "MAX_DECOMPRESSED_BYTES", 100)
    resp = FakeResponse(gz, headers={"Content-Encoding": "gzip"})
    with pytest.raises(ValueError, match="decompressed"):
        games.fetch_url(games.DETECTABLE_URL, 1 << 20, urlopen=_opener(resp))


def test_fetch_rejects_truncated_gzip_and_unknown_encodings():
    gz = gzip.compress(_fixture_bytes())[:-20]
    with pytest.raises(ValueError):
        games.fetch_url(games.DETECTABLE_URL, 1 << 20,
                        urlopen=_opener(FakeResponse(gz, headers={"Content-Encoding": "gzip"})))
    with pytest.raises(ValueError):
        games.fetch_url(games.DETECTABLE_URL, 1 << 20,
                        urlopen=_opener(FakeResponse(b"[]", headers={"Content-Encoding": "br"})))


# ------------------------------------------------------------------- store --
def _store(tmp_path, fetcher=None, clock=None):
    return games.DetectableStore(str(tmp_path / "games"),
                                 fetcher=fetcher or (lambda url, cap: _fixture_bytes()),
                                 clock=clock or Clock())


def test_offline_with_no_cache_is_empty_and_stale(tmp_path):
    s = _store(tmp_path)
    assert s.load() == 0 and s.games == [] and s.is_stale()
    assert s.info() == {"count": 0, "fetched": None, "stale": True, "error": None}


def test_refresh_validates_and_writes_a_compact_cache_atomically(tmp_path):
    calls = []
    s = _store(tmp_path, fetcher=lambda url, cap: calls.append((url, cap)) or _fixture_bytes())
    assert s.refresh() == {"ok": True, "count": 5}
    assert calls == [(games.DETECTABLE_URL, games.MAX_DETECTABLE_BYTES)]
    with open(s.path, encoding="utf-8") as f:
        cached = json.load(f)
    assert cached["version"] == 1 and cached["source"] == games.DETECTABLE_URL
    assert {g["id"] for g in cached["games"]} >= {STARFALL}
    assert set(cached["games"][0]) == {"id", "name", "exes"}           # nothing else kept
    assert not os.path.exists(s.path + ".tmp")
    s2 = _store(tmp_path, fetcher=lambda *a: pytest.fail("must not fetch"))
    assert s2.load() == 5 and not s2.is_stale()


def test_failed_refresh_keeps_the_old_list(tmp_path):
    s = _store(tmp_path)
    s.refresh()

    def boom(url, cap):
        raise OSError("offline")
    s._fetch = boom
    r = s.refresh()
    assert r["ok"] is False and "offline" in r["error"]
    assert len(s.games) == 5 and s.info()["error"]
    s._fetch = lambda url, cap: b'{"not": "a list"}'
    assert s.refresh()["ok"] is False and len(s.games) == 5


def test_weekly_staleness_and_retry_backoff(tmp_path):
    clock = Clock()
    s = _store(tmp_path, clock=clock)
    assert s.should_refresh()
    s.refresh()
    assert not s.should_refresh()
    clock.t += games.REFRESH_AFTER_S
    assert s.is_stale() and s.should_refresh()
    s._fetch = lambda url, cap: (_ for _ in ()).throw(OSError("offline"))
    s.refresh()
    assert not s.should_refresh()                       # failed: wait before retrying
    clock.t += games.RETRY_AFTER_S
    assert s.should_refresh()


def test_corrupt_or_foreign_cache_is_ignored(tmp_path):
    s = _store(tmp_path)
    os.makedirs(os.path.dirname(s.path))
    for bad in ("{", "[]", json.dumps({"version": 99, "fetched": 1, "games": []}),
                json.dumps({"version": 1, "fetched": "yesterday", "games": []})):
        with open(s.path, "w", encoding="utf-8") as f:
            f.write(bad)
        s.games = []
        assert s.load() == 0 and s.games == []


def test_cache_entries_are_revalidated_on_load(tmp_path):
    s = _store(tmp_path)
    os.makedirs(os.path.dirname(s.path))
    with open(s.path, "w", encoding="utf-8") as f:
        json.dump({"version": 1, "fetched": 5, "games": [
            {"id": "1", "name": "Ok", "exes": ["A\\B.exe"]},
            {"id": "x", "name": "Bad id", "exes": ["c.exe"]},
            {"id": "2", "name": "\x01", "exes": ["d.exe"]},
            {"id": "3", "name": "No exes", "exes": []}]}, f)
    assert s.load() == 1 and s.games == [{"id": "1", "name": "Ok", "exes": ["a/b.exe"]}]
