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
import json
import logging
import os
import subprocess
import sys
import tempfile
import threading
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
    """Choose the right release asset for this OS by filename."""
    def find(*needles):
        for a in assets:
            name = a.get("name", "").lower()
            if all(n in name for n in needles):
                return a.get("browser_download_url"), a.get("name")
        return None, None
    if kind == "windows":
        url, name = find("setup", ".exe")
        if not url:
            url, name = find(".exe")
        return url, name
    if kind in ("flatpak", "linux"):
        return find(".flatpak")
    return None, None


# ------------------------------------------------------------------- check ----
def check_for_update(timeout=10):
    """Return {ok, update, current, latest, notes, url, asset_url, asset_name}.
    `update` is True only when a newer release exists AND there's an asset this
    OS can install. Network/parse failures come back as {ok: False, error}."""
    kind = platform_kind()
    try:
        req = urllib.request.Request(_API.format(repo=version.GITHUB_REPO), headers=_UA)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            rel = json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 404:    # no release published yet
            return {"ok": True, "update": False, "current": version.__version__,
                    "latest": None, "notes": "", "reason": "no releases yet"}
        return {"ok": False, "error": f"HTTP {e.code}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

    latest = rel.get("tag_name") or rel.get("name") or ""
    newer = is_newer(latest, version.__version__)
    asset_url, asset_name = _pick_asset(rel.get("assets", []), kind)
    return {
        "ok": True,
        "update": bool(newer and asset_url),
        "newer": bool(newer),               # newer exists even if no asset for us
        "current": version.__version__,
        "latest": latest.lstrip("vV"),
        "notes": (rel.get("body") or "")[:4000],
        "url": rel.get("html_url", ""),
        "asset_url": asset_url,
        "asset_name": asset_name,
        "kind": kind,
    }


# ------------------------------------------------------------------ apply ----
def _download(url, dest):
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
        while True:
            chunk = r.read(65536)
            if not chunk:
                break
            f.write(chunk)
    return dest


def _download_dir(kind):
    """A directory to download into. For Flatpak this must be a path the HOST
    can also see (so host `flatpak install` can read the bundle): $XDG_DATA_HOME
    maps to ~/.var/app/<id>/data on both sides. Elsewhere a temp dir is fine."""
    if kind == "flatpak":
        d = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
        os.makedirs(d, exist_ok=True)
        return d
    return tempfile.gettempdir()


def apply_update(asset_url, asset_name=None):
    """Download the asset and install it with the OS-native mechanism.
    Returns {ok, action, ...}. On Windows this spawns the installer and asks
    the caller to quit; on Flatpak it installs on the host and asks the user to
    relaunch."""
    if not asset_url:
        return {"ok": False, "error": "no installable asset for this platform"}
    kind = platform_kind()
    name = asset_name or os.path.basename(asset_url.split("?")[0])
    ddir = _download_dir(kind)
    try:
        dest = os.path.join(ddir, name)
        _download(asset_url, dest)
    except Exception as e:
        return {"ok": False, "error": f"download failed: {e}"}

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
