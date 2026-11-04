"""Game detection + per-game profiles (Discord-style).

Aether looks at which programs are running every few seconds and matches them
against (a) Discord's public "detectable applications" list and (b) programs
the user added. A game mapped to a profile switches the app to that profile
(and the app applies it to the keyboard) while it runs; when it exits the
previous profile comes back.

Privacy: process enumeration is transient. Only processes whose file name
could be a known game are opened, nothing about any other process is kept,
and nothing is logged, stored or sent except the matched game's id/name.
The detectable list is DOWNLOADED (nothing is uploaded) and cached on disk.

Windows only (Toolhelp32 + QueryFullProcessImageNameW through ctypes, no new
dependency); elsewhere `processes_supported()` is False and nothing polls.
"""
import ctypes
import json
import logging
import os
import re
import ssl
import sys
import threading
import time
import types
import urllib.request
import zlib

log = logging.getLogger("aether.games")

DETECTABLE_URL = "https://discord.com/api/v9/applications/detectable"
MAX_DETECTABLE_BYTES = 5 * 1024 * 1024      # cap on the bytes received
MAX_DECOMPRESSED_BYTES = 32 * 1024 * 1024   # cap after gunzip (zip-bomb guard)
FETCH_TIMEOUT_S = 20
REFRESH_AFTER_S = 7 * 24 * 3600             # weekly
RETRY_AFTER_S = 6 * 3600                    # after a failed automatic fetch
POLL_S = 3.0
DEBOUNCE_S = 5.0
CACHE_VERSION = 1
SETTINGS_KEY = "games"
CUSTOM_PREFIX = "custom:"
MAX_NAME = 64
MAX_EXE = 260
MAX_SEGMENTS = 8
MAX_EXES_PER_GAME = 32
MAX_GAMES = 100000
MAX_MAPPED = 200
MAX_PROFILES = 200

# Single-file-name patterns too generic to mean "a game is running" (runtimes,
# shells, browsers, launchers). Only applied to Discord's list; a program the
# user adds is always honoured.
GENERIC_EXES = frozenset({
    "java.exe", "javaw.exe", "python.exe", "pythonw.exe", "node.exe",
    "electron.exe", "cmd.exe", "powershell.exe", "pwsh.exe", "explorer.exe",
    "dotnet.exe", "rundll32.exe", "svchost.exe", "conhost.exe", "dllhost.exe",
    "msedge.exe", "chrome.exe", "firefox.exe", "steam.exe",
    "steamwebhelper.exe", "launcher.exe", "game.exe", "start.exe",
    "setup.exe", "unins000.exe", "aetherhe.exe",
})

_CTRL = re.compile(r"[\x00-\x1f\x7f]")
_ID_RE = re.compile(r"^[0-9]{1,24}$")
_PROFILE_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def clean_name(s):
    """Untrusted display name -> stripped text without control characters,
    at most MAX_NAME chars; None if nothing is left."""
    if not isinstance(s, str):
        return None
    s = _CTRL.sub("", s).strip()
    return s[:MAX_NAME] or None


def norm_exe(s):
    """Executable path or pattern -> lowercase '/'-joined segments without a
    drive, a leading '>' (Discord's "file name only" marker) or empty/./..
    segments. 'C:\\Games\\Foo\\FOO.exe' -> 'games/foo/foo.exe'. None if empty,
    too long, or containing control characters."""
    if not isinstance(s, str) or not s or len(s) > MAX_EXE or _CTRL.search(s):
        return None
    s = s.strip().lstrip(">").replace("\\", "/").lower()
    if len(s) >= 2 and s[1] == ":":
        s = s[2:]
    segs = [p for p in s.split("/") if p and p not in (".", "..")]
    return "/".join(segs) or None


def exe_suffix(path, segments=2):
    """The last `segments` path segments of `path`, normalised."""
    n = norm_exe(path)
    if not n:
        return None
    return "/".join(n.split("/")[-segments:])


def _game_exes(xs):
    """Discord `executables` -> normalised win32, non-launcher patterns."""
    out = []
    if not isinstance(xs, list):
        return out
    for x in xs:
        if not isinstance(x, dict) or x.get("os") != "win32" or x.get("is_launcher") is True:
            continue
        n = norm_exe(x.get("name"))
        if n and n.count("/") < MAX_SEGMENTS and n not in out:
            out.append(n)
        if len(out) >= MAX_EXES_PER_GAME:
            break
    return out


def parse_detectable(raw):
    """Validate Discord's detectable list (bytes/str/parsed list) and reduce
    it to [{"id", "name", "exes"}] for games with Windows executables.
    Raises ValueError when the shape is wrong or no game survives."""
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8")
    if isinstance(raw, str):
        raw = json.loads(raw)
    if not isinstance(raw, list):
        raise ValueError("detectable list must be a JSON array")
    if len(raw) > MAX_GAMES:
        raise ValueError("detectable list has too many entries")
    out, seen = [], set()
    for e in raw:
        if not isinstance(e, dict):
            continue
        gid = e.get("id")
        if isinstance(gid, int) and not isinstance(gid, bool):
            gid = str(gid)
        if not isinstance(gid, str) or not _ID_RE.match(gid) or gid in seen:
            continue
        name = clean_name(e.get("name"))
        exes = _game_exes(e.get("executables"))
        if not name or not exes:
            continue
        seen.add(gid)
        out.append({"id": gid, "name": name, "exes": exes})
    if not out:
        raise ValueError("detectable list has no Windows games")
    return out


def parse_cache(obj):
    """Our own cache file -> (games, fetched_epoch). Re-validates every
    entry (the file is on disk and could be edited). ValueError if unusable."""
    if not isinstance(obj, dict) or obj.get("version") != CACHE_VERSION:
        raise ValueError("unknown cache format")
    fetched = obj.get("fetched")
    if isinstance(fetched, bool) or not isinstance(fetched, (int, float)) \
            or fetched != fetched or fetched < 0:
        raise ValueError("cache has no valid fetch time")
    games = obj.get("games")
    if not isinstance(games, list) or len(games) > MAX_GAMES:
        raise ValueError("cache has no game list")
    out, seen = [], set()
    for g in games:
        if not isinstance(g, dict):
            continue
        gid, name = g.get("id"), clean_name(g.get("name"))
        if not isinstance(gid, str) or not _ID_RE.match(gid) or gid in seen or not name:
            continue
        exes = [n for n in (norm_exe(x) for x in (g.get("exes") or [])
                            if isinstance(x, str))
                if n and n.count("/") < MAX_SEGMENTS][:MAX_EXES_PER_GAME]
        if exes:
            seen.add(gid)
            out.append({"id": gid, "name": name, "exes": exes})
    return out, float(fetched)


class DetectableIndex:
    """Trailing-path-segment matcher over thousands of patterns.

    `_by_suffix` maps every normalised pattern ('foo/bin/foo.exe',
    'foo.exe') to a game id. A process path is looked up from its longest
    candidate suffix (`max_segments`, the deepest pattern) down to its file
    name, so the most specific pattern wins: at most MAX_SEGMENTS dict
    lookups per process. `basenames` (last segment of every pattern) lets
    the scanner skip opening any process whose file name cannot match.
    Discord duplicates: the first entry wins. `extra` (the user's mapped and
    added games) overrides Discord patterns."""

    def __init__(self, games=(), extra=()):
        self._by_suffix = {}
        self._names = {}
        self._exes = {}
        self.basenames = set()
        self.max_segments = 1
        for g in games:
            self._add(g, discord=True)
        for g in extra:
            self._add(g, discord=False)

    def _add(self, g, discord):
        gid, name = g["id"], g["name"]
        kept = []
        for exe in g["exes"]:
            if discord and "/" not in exe and exe in GENERIC_EXES:
                continue
            if discord and exe in self._by_suffix:
                continue
            self._by_suffix[exe] = gid
            self.basenames.add(exe.rsplit("/", 1)[-1])
            self.max_segments = max(self.max_segments, exe.count("/") + 1)
            kept.append(exe)
        if kept or not discord:
            if not discord or gid not in self._names:
                self._names[gid] = name
            self._exes.setdefault(gid, [])
            for exe in kept:
                if exe not in self._exes[gid]:
                    self._exes[gid].append(exe)

    def __len__(self):
        return len(self._names)

    def could_match(self, basename):
        return isinstance(basename, str) and basename.lower() in self.basenames

    def match(self, path):
        """Game id for a process path (or bare file name), else None."""
        n = norm_exe(path)
        if not n:
            return None
        segs = n.split("/")
        for k in range(min(self.max_segments, len(segs)), 0, -1):
            gid = self._by_suffix.get("/".join(segs[-k:]))
            if gid is not None:
                return gid
        return None

    def name_of(self, gid):
        return self._names.get(gid)

    def exes_of(self, gid):
        return list(self._exes.get(gid, ()))


def _atomic_write_json(path, obj):
    """Write JSON next to `path` and swap it in, so a crash mid-write never
    leaves a truncated cache."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, separators=(",", ":"))
    os.replace(tmp, path)


def _gunzip_capped(data, limit):
    d = zlib.decompressobj(16 + zlib.MAX_WBITS)
    out = d.decompress(data, limit + 1)
    if len(out) > limit or d.unconsumed_tail:
        raise ValueError("detectable list is too large once decompressed")
    if not d.eof:
        raise ValueError("detectable list download was truncated")
    return out


def fetch_url(url, max_bytes, timeout=FETCH_TIMEOUT_S, urlopen=None):
    """GET `url` over verified HTTPS and return the body, refusing more than
    `max_bytes` on the wire (checked while streaming, before reading it all).
    gzip is accepted and unpacked with its own cap. Raises on any failure."""
    if not url.startswith("https://"):
        raise ValueError("only https URLs are fetched")
    req = urllib.request.Request(url, headers={
        "User-Agent": "AetherHE-Games", "Accept": "application/json",
        "Accept-Encoding": "gzip"})
    ctx = ssl.create_default_context()      # certificate + hostname checks on
    opener = urlopen or urllib.request.urlopen
    with opener(req, timeout=timeout, context=ctx) as r:
        final = r.geturl() or url
        if not final.startswith("https://"):
            raise ValueError("redirected away from https")
        length = (r.headers.get("Content-Length") or "").strip()
        if length.isdigit() and int(length) > max_bytes:
            raise ValueError(f"detectable list is larger than {max_bytes // 1048576} MB")
        buf = bytearray()
        while True:
            chunk = r.read(65536)
            if not chunk:
                break
            buf += chunk
            if len(buf) > max_bytes:
                raise ValueError(f"detectable list is larger than {max_bytes // 1048576} MB")
        enc = (r.headers.get("Content-Encoding") or "").strip().lower()
    if enc == "gzip":
        return _gunzip_capped(bytes(buf), MAX_DECOMPRESSED_BYTES)
    if enc not in ("", "identity"):
        raise ValueError(f"unsupported content encoding {enc!r}")
    return bytes(buf)


class DetectableStore:
    """Discord's list, cached at <dir>/detectable.json in a compact,
    re-validated form ({"version", "fetched", "source", "games"}).
    Works offline: a missing/corrupt cache just means no Discord games.
    `fetcher(url, max_bytes) -> bytes` is injectable; tests never touch the
    network."""

    def __init__(self, cache_dir, fetcher=None, clock=time.time):
        self.path = os.path.join(cache_dir, "detectable.json")
        self._fetch = fetcher or fetch_url
        self._clock = clock
        self.games = []
        self.fetched = None
        self.last_error = None
        self._last_attempt = None

    def load(self):
        """Read the cache; returns the number of games (0 when absent/bad)."""
        try:
            with open(self.path, encoding="utf-8") as f:
                obj = json.load(f)
            games, fetched = parse_cache(obj)
        except FileNotFoundError:
            return 0
        except (OSError, ValueError) as e:
            self.last_error = f"cached game list unusable: {e}"
            log.warning("%s", self.last_error)
            return 0
        self.games, self.fetched = games, fetched
        return len(games)

    def is_stale(self):
        return self.fetched is None or self._clock() - self.fetched >= REFRESH_AFTER_S

    def should_refresh(self):
        """Stale, and no automatic attempt in the last RETRY_AFTER_S."""
        if not self.is_stale():
            return False
        return (self._last_attempt is None
                or self._clock() - self._last_attempt >= RETRY_AFTER_S)

    def refresh(self):
        """Download, validate, cache. {"ok", "count"} or {"ok": False, "error"};
        a failure keeps whatever list was loaded before."""
        self._last_attempt = self._clock()
        try:
            games = parse_detectable(self._fetch(DETECTABLE_URL, MAX_DETECTABLE_BYTES))
        except Exception as e:
            self.last_error = f"game list not updated: {e}"
            log.warning("%s", self.last_error)
            return {"ok": False, "error": self.last_error}
        now = self._clock()
        try:
            _atomic_write_json(self.path, {"version": CACHE_VERSION, "fetched": now,
                                           "source": DETECTABLE_URL, "games": games})
        except OSError as e:
            log.warning("game list cache not written: %s", e)
        self.games, self.fetched, self.last_error = games, now, None
        return {"ok": True, "count": len(games)}

    def info(self):
        return {"count": len(self.games), "fetched": self.fetched,
                "stale": self.is_stale(), "error": self.last_error}


def processes_supported(platform=None):
    """Process enumeration exists on Windows only."""
    return (platform or sys.platform).startswith("win")


_W = None
_INVALID_HANDLE = ctypes.c_void_p(-1).value


def _win():
    """kernel32/user32 entry points with explicit argtypes (64-bit handles)."""
    global _W
    if _W is None:
        from ctypes import wintypes as wt
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        u32 = ctypes.WinDLL("user32", use_last_error=True)

        class PROCESSENTRY32W(ctypes.Structure):
            _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD),
                        ("th32ProcessID", wt.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                        ("th32ModuleID", wt.DWORD), ("cntThreads", wt.DWORD),
                        ("th32ParentProcessID", wt.DWORD), ("pcPriClassBase", ctypes.c_long),
                        ("dwFlags", wt.DWORD), ("szExeFile", ctypes.c_wchar * 260)]

        pe_p = ctypes.POINTER(PROCESSENTRY32W)
        k32.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]
        k32.CreateToolhelp32Snapshot.restype = wt.HANDLE
        k32.Process32FirstW.argtypes = [wt.HANDLE, pe_p]
        k32.Process32FirstW.restype = wt.BOOL
        k32.Process32NextW.argtypes = [wt.HANDLE, pe_p]
        k32.Process32NextW.restype = wt.BOOL
        k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
        k32.OpenProcess.restype = wt.HANDLE
        k32.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR,
                                                   ctypes.POINTER(wt.DWORD)]
        k32.QueryFullProcessImageNameW.restype = wt.BOOL
        k32.CloseHandle.argtypes = [wt.HANDLE]
        k32.CloseHandle.restype = wt.BOOL
        u32.GetForegroundWindow.argtypes = []
        u32.GetForegroundWindow.restype = wt.HWND
        u32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
        u32.GetWindowThreadProcessId.restype = wt.DWORD
        _W = types.SimpleNamespace(k32=k32, u32=u32, PE=PROCESSENTRY32W, wt=wt)
    return _W


def list_processes():
    """[(pid, file name)] of every process (Toolhelp32). [] off Windows or
    on any failure. Transient: callers must not keep it."""
    if not processes_supported():
        return []
    try:
        w = _win()
        snap = w.k32.CreateToolhelp32Snapshot(0x2, 0)       # TH32CS_SNAPPROCESS
        if not snap or snap == _INVALID_HANDLE:
            return []
        try:
            e = w.PE()
            e.dwSize = ctypes.sizeof(w.PE)
            out = []
            ok = w.k32.Process32FirstW(snap, ctypes.byref(e))
            while ok:
                out.append((int(e.th32ProcessID), e.szExeFile))
                ok = w.k32.Process32NextW(snap, ctypes.byref(e))
            return out
        finally:
            w.k32.CloseHandle(snap)
    except Exception as ex:
        log.debug("process list unavailable: %s", ex)
        return []


def process_path(pid):
    """Full image path of `pid` (QueryFullProcessImageNameW with
    PROCESS_QUERY_LIMITED_INFORMATION), or None (gone / access denied)."""
    if not processes_supported():
        return None
    try:
        w = _win()
        h = w.k32.OpenProcess(0x1000, False, int(pid))
        if not h:
            return None
        try:
            size = w.wt.DWORD(1024)
            buf = ctypes.create_unicode_buffer(1024)
            if w.k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                return buf.value
            return None
        finally:
            w.k32.CloseHandle(h)
    except Exception:
        return None


def foreground_pid():
    """PID owning the foreground window, or None."""
    if not processes_supported():
        return None
    try:
        w = _win()
        hwnd = w.u32.GetForegroundWindow()
        if not hwnd:
            return None
        pid = w.wt.DWORD(0)
        w.u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return int(pid.value) or None
    except Exception:
        return None


def scan(index, procs=None, path_of=None, fg=None):
    """One detection pass -> (set of running game ids, id of the game that
    owns the foreground window or None). Only processes whose file name ends
    some pattern are opened; nothing about any other process is kept."""
    procs = procs or list_processes
    path_of = path_of or process_path
    fg = fg or foreground_pid
    fg_pid = fg()
    running, fg_game = set(), None
    for pid, base in procs():
        if not index.could_match(base):
            continue
        gid = index.match(path_of(pid) or base)
        if gid is None:
            continue
        running.add(gid)
        if pid == fg_pid:
            fg_game = gid
    return running, fg_game


def running_programs(index, procs=None, path_of=None, limit=200, own_pid=None):
    """For the Settings "add a running program" picker, built on demand and
    never stored: [{"exe": "folder/name.exe", "name", "gameId"}] for user
    programs (the Windows folder and Aether itself skipped), one row per
    exe, known games first, then by name."""
    procs = procs or list_processes
    path_of = path_of or process_path
    own = os.getpid() if own_pid is None else own_pid
    windir = norm_exe(os.environ.get("SystemRoot") or "C:\\Windows") or "windows"
    rows, seen = [], set()
    for pid, _base in procs():
        if pid == own:
            continue
        n = norm_exe(path_of(pid) or "")
        if not n or not n.endswith(".exe") or n.startswith(windir + "/"):
            continue
        suffix = "/".join(n.split("/")[-2:])
        if suffix in seen:
            continue
        seen.add(suffix)
        gid = index.match(n)
        rows.append({"exe": suffix,
                     "name": (index.name_of(gid) if gid else None) or n.rsplit("/", 1)[-1],
                     "gameId": gid})
    rows.sort(key=lambda r: (r["gameId"] is None, r["name"].lower()))
    return rows[:limit]
