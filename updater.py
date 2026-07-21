"""Cross-platform in-app updater driven by GitHub Releases.

One source of truth: whatever the latest published release on
`version.GITHUB_REPO` is. The app embeds its own version (version.py);
check_for_update() asks GitHub what the newest release is and, if it's newer,
returns the per-OS download asset. apply_update() installs it in place using
each platform's native mechanism:

  - Windows : download `*Setup.exe`, run it (the Inno installer closes the
              running app, upgrades in place, and relaunches), then quit.
  - Linux   : if running inside Flatpak, download the `.flatpak` bundle and
    (Flatpak) install it on the host via `flatpak-spawn --host flatpak
              install`. The user restarts the app to pick it up.
  - other   : no in-place install (source checkout / unknown packaging) — we
              just hand back the release URL for a manual update.

Stdlib only (urllib/json/subprocess), so there's no extra dependency to ship.
Everything talks to GitHub over HTTPS; the repo is hard-pinned in version.py.
"""
import hashlib
import json
import logging
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

import version

log = logging.getLogger("aether.update")

_API = "https://api.github.com/repos/{repo}/releases/latest"
_UA = {"User-Agent": "AetherHE-Updater", "Accept": "application/vnd.github+json"}


# ---------------------------------------------------------------- platform ----
def in_flatpak():
    return bool(os.environ.get("FLATPAK_ID")) or os.path.exists("/.flatpak-info")


def platform_kind():
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "flatpak" if in_flatpak() else "linux"


# ---------------------------------------------------------------- versions ----
def _parse(v):
    """'v1.2.3' / '1.2.3-beta' -> (1,2,3). Missing parts are 0; suffixes drop."""
    v = (v or "").strip().lstrip("vV").split("-")[0].split("+")[0]
    out = []
    for part in v.split("."):
        digits = "".join(c for c in part if c.isdigit())
        out.append(int(digits) if digits else 0)
    while len(out) < 3:
        out.append(0)
    return tuple(out[:3])


def is_newer(latest, current):
    return _parse(latest) > _parse(current)


def _pick_asset(assets, kind):
    """Choose the right release asset for this OS by filename.

    Returns (url, name) for backwards compatibility; _pick_asset_full() gives
    the same choice plus the integrity metadata."""
    a = _pick_asset_full(assets, kind)
    return (a["url"], a["name"]) if a else (None, None)


def _pick_asset_full(assets, kind):
    """The chosen asset as {url, name, size, sha256} — None when this OS has no
    installable asset.

    `size` and `sha256` come from GitHub's own asset metadata (`digest` is
    "sha256:<hex>") and are what _download() checks the bytes against before
    anything is executed."""
    def find(*needles):
        for a in assets:
            name = (a.get("name") or "").lower()
            # Ignore assets GitHub hasn't finished storing — downloading one
            # yields a truncated or 404 body.
            if a.get("state") not in (None, "uploaded"):
                continue
            if all(n in name for n in needles):
                digest = (a.get("digest") or "")
                sha = digest.split("sha256:", 1)[1].strip() if "sha256:" in digest else None
                return {"url": a.get("browser_download_url"), "name": a.get("name"),
                        "size": a.get("size"), "sha256": sha}
        return None
    if kind == "windows":
        return find("setup", ".exe") or find(".exe")
    if kind in ("flatpak", "linux"):
        return find(".flatpak")
    return None


# ------------------------------------------------------------ preference ----
# The auto-update-on-launch flag lives in the app's settings.json as `autoUpdate`.
# These helpers are stdlib-only and take an explicit path so they can be unit
# tested without importing app_web (which pulls in the native `hid` module).
def get_auto_update(settings_path):
    """Return the auto-update-on-launch preference: True, False, or None when the
    key is absent or the file is missing/unreadable (i.e. first run)."""
    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            s = json.load(f)
    except Exception:
        return None
    val = s.get("autoUpdate") if isinstance(s, dict) else None
    return val if isinstance(val, bool) else None


def set_auto_update(settings_path, on):
    """Persist the preference, merging into settings.json so sibling keys survive.
    A missing or corrupt file is treated as an empty settings object."""
    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            s = json.load(f)
        if not isinstance(s, dict):
            s = {}
    except Exception:
        s = {}
    s["autoUpdate"] = bool(on)
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2)
    return bool(on)


# ------------------------------------------------------------------- check ----
def check_for_update(timeout=10):
    """Return {ok, update, current, latest, notes, url, asset_url, asset_name}.
    `update` is True only when a newer release exists AND there's an asset this
    OS can install. Network/parse failures come back as {ok: False, error}."""
    kind = platform_kind()
    rel = None
    last_err = None
    # One transient DNS/connection blip shouldn't read as "no update available"
    # — that failure mode is exactly what kept 0.3.1 users stranded. Two quick
    # retries, then report the real reason.
    for attempt in range(3):
        try:
            req = urllib.request.Request(_API.format(repo=version.GITHUB_REPO), headers=_UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                rel = json.load(r)
            break
        except urllib.error.HTTPError as e:
            if e.code == 404:    # no release published yet
                return {"ok": True, "update": False, "current": version.__version__,
                        "latest": None, "notes": "", "reason": "no releases yet"}
            if e.code in (403, 429):
                # Unauthenticated GitHub API is 60 req/hr/IP. Say so — this is
                # otherwise indistinguishable from being offline.
                remaining = e.headers.get("X-RateLimit-Remaining") if e.headers else None
                if remaining == "0" or e.code == 429:
                    return {"ok": False, "error": "GitHub rate limit reached — try again in an hour",
                            "current": version.__version__}
                return {"ok": False, "error": f"HTTP {e.code} (forbidden)",
                        "current": version.__version__}
            last_err = f"HTTP {e.code}"
        except Exception as e:
            last_err = str(e)
        if attempt < 2:
            time.sleep(1.5 * (attempt + 1))
    if rel is None:
        return {"ok": False, "error": last_err or "could not reach GitHub",
                "current": version.__version__}

    latest = rel.get("tag_name") or rel.get("name") or ""
    newer = is_newer(latest, version.__version__)
    asset = _pick_asset_full(rel.get("assets", []), kind)
    return {
        "ok": True,
        "update": bool(newer and asset),
        "newer": bool(newer),               # newer exists even if no asset for us
        "current": version.__version__,
        "latest": latest.lstrip("vV"),
        "notes": (rel.get("body") or "")[:4000],
        "url": rel.get("html_url", ""),
        "asset_url": asset["url"] if asset else None,
        "asset_name": asset["name"] if asset else None,
        "asset_size": asset["size"] if asset else None,
        "asset_sha256": asset["sha256"] if asset else None,
        "kind": kind,
    }


# ------------------------------------------------------------------ apply ----
class IntegrityError(Exception):
    """Downloaded bytes did not match the size/hash GitHub published."""


# Progress of the in-flight download, polled by the UI via Api.update_progress().
# One update runs at a time, so a module-level dict is enough.
_progress = {"phase": "idle", "done": 0, "total": 0, "pct": 0}


def get_progress():
    return dict(_progress)


def _set_progress(**kw):
    _progress.update(kw)
    if _progress.get("total"):
        _progress["pct"] = int(_progress["done"] * 100 / _progress["total"])


def _download(url, dest, expect_size=None, expect_sha256=None, on_progress=None):
    """Download to `dest`, verifying it before it is ever visible under that name.

    We hand this file to the OS to EXECUTE, so a truncated or tampered download
    must never reach the point of being run. Three things follow from that:

      - bytes land in `dest + '.part'` and are renamed only after verification,
        so a half-finished or failed download can't be mistaken for a good one
        (an interrupted download previously left a runnable partial .exe);
      - the SHA-256 is streamed while downloading and compared to the digest
        GitHub publishes for the asset, which is what makes a corrupted CDN
        response or a tampered mirror fail closed instead of executing;
      - a mismatch deletes the file and raises, rather than returning a path.

    GitHub has published `digest` per asset since 2025; when it is absent we
    fall back to the size check alone and say so in the log rather than
    pretending the download was verified.
    """
    part = dest + ".part"
    sha = hashlib.sha256()
    got = 0
    req = urllib.request.Request(url, headers=_UA)
    try:
        with urllib.request.urlopen(req, timeout=120) as r, open(part, "wb") as f:
            total = expect_size or int(r.headers.get("Content-Length") or 0)
            _set_progress(phase="downloading", done=0, total=total)
            while True:
                chunk = r.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                sha.update(chunk)
                got += len(chunk)
                _set_progress(done=got, total=total)
                if on_progress:
                    try:
                        on_progress(got, total)
                    except Exception:
                        pass

        if expect_size is not None and got != expect_size:
            raise IntegrityError(f"size mismatch: got {got} bytes, expected {expect_size}")
        if expect_sha256:
            actual = sha.hexdigest()
            if actual.lower() != expect_sha256.lower():
                raise IntegrityError(f"sha256 mismatch: got {actual}, expected {expect_sha256}")
            log.info("update: verified sha256 %s", actual)
        else:
            log.warning("update: no sha256 published for this asset — size checked only")

        _set_progress(phase="verified", done=got)
        os.replace(part, dest)   # atomic: dest only ever exists fully verified
        return dest
    except BaseException:
        try:
            if os.path.exists(part):
                os.remove(part)
        except OSError:
            pass
        _set_progress(phase="idle", done=0, total=0)
        raise


def _download_dir(kind):
    """A directory to download into. For Flatpak this must be a path the HOST
    can also see (so host `flatpak install` can read the bundle): $XDG_DATA_HOME
    maps to ~/.var/app/<id>/data on both sides. Elsewhere a temp dir is fine."""
    if kind == "flatpak":
        d = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
        os.makedirs(d, exist_ok=True)
        return d
    return tempfile.gettempdir()


def apply_update(asset_url, asset_name=None, asset_size=None, asset_sha256=None):
    """Download the asset and install it with the OS-native mechanism.
    Returns {ok, action, ...}. On Windows this spawns the installer and asks
    the caller to quit; on Flatpak it installs on the host and asks the user to
    relaunch.

    `asset_size`/`asset_sha256` are the values from check_for_update(); when the
    caller omits them (an older UI) they are re-fetched here rather than
    skipped, so the integrity check cannot be bypassed by calling this directly.
    """
    if not asset_url:
        return {"ok": False, "error": "no installable asset for this platform"}
    kind = platform_kind()
    name = asset_name or os.path.basename(asset_url.split("?")[0])

    if asset_sha256 is None:
        # Re-derive from the release rather than trusting an unverified download.
        try:
            chk = check_for_update()
            if chk.get("ok") and chk.get("asset_url") == asset_url:
                asset_size = asset_size if asset_size is not None else chk.get("asset_size")
                asset_sha256 = chk.get("asset_sha256")
        except Exception as e:
            log.warning("update: could not re-fetch asset digest: %s", e)

    ddir = _download_dir(kind)
    try:
        dest = os.path.join(ddir, name)
        _download(asset_url, dest, expect_size=asset_size, expect_sha256=asset_sha256)
    except IntegrityError as e:
        # Never fall through to executing a file that failed verification.
        log.error("update: integrity check FAILED: %s", e)
        _set_progress(phase="idle", done=0, total=0)
        return {"ok": False, "error": f"integrity check failed — update refused ({e})"}
    except Exception as e:
        _set_progress(phase="idle", done=0, total=0)
        return {"ok": False, "error": f"download failed: {e}"}
    _set_progress(phase="installing")

    try:
        if kind == "windows":
            # Inno Setup: /SILENT shows a progress bar but no wizard; it stops
            # the running app, upgrades, and (per installer.iss) relaunches.
            subprocess.Popen([dest, "/SILENT", "/NOCANCEL"],
                             close_fds=True)
            return {"ok": True, "action": "installer_launched", "quit": True}
        if kind == "flatpak":
            # The sandbox can't install flatpaks itself; run it on the host
            # (needs finish-arg --talk-name=org.freedesktop.Flatpak). The bundle
            # lives under $XDG_DATA_HOME, which the host sees at the same path.
            # --directory gives flatpak-spawn a host cwd that exists (it would
            # otherwise inherit the sandbox cwd /app/... and fail to chdir).
            cp = subprocess.run(
                ["flatpak-spawn", "--host", f"--directory={ddir}",
                 "flatpak", "install", "--user", "--reinstall",
                 "--noninteractive", "-y", dest],
                capture_output=True, text=True, timeout=300)
            if cp.returncode != 0:
                return {"ok": False, "error": (cp.stderr or cp.stdout or "install failed").strip()}
            return {"ok": True, "action": "installed", "restart": True}
        # Bare Linux / macOS / source checkout: nothing safe to auto-install.
        return {"ok": True, "action": "downloaded", "path": dest}
    except Exception as e:
        return {"ok": False, "error": str(e)}
