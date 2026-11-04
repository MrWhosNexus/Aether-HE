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
