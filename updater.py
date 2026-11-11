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
  - macOS   : download `AetherHE-macos-<arch>.zip`, unpack it next to the
              installed AetherHE.app, verify it (signature, bundle id, version,
              arch), then hand over to a detached /bin/sh helper that waits for
              this process to exit, swaps the bundle with two same-volume
              renames (restoring the old one if anything fails) and relaunches.
              When the app cannot be replaced where it is (translocated, on a
              read-only disk image, no write access, source checkout) the zip
              is downloaded to ~/Downloads and revealed instead.
  - other   : no in-place install (source checkout / unknown packaging) — we
              just hand back the release URL for a manual update.

Stdlib only (urllib/json/subprocess), so there's no extra dependency to ship.
Everything talks to GitHub over HTTPS; the repo is hard-pinned in version.py.
"""
import hashlib
import json
import logging
import os
import plistlib
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
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
    def find(*needles, exclude=()):
        for a in assets:
            name = (a.get("name") or "").lower()
            # Ignore assets GitHub hasn't finished storing — downloading one
            # yields a truncated or 404 body.
            if a.get("state") not in (None, "uploaded"):
                continue
            if any(x in name for x in exclude):
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
    if kind == "macos":
        # The updater payload is the .zip (the .dmg beside it is for a first
        # install). Match the arch first so an Intel build never lands on Apple
        # Silicon or vice versa — build_macos.sh names the slice in the asset.
        arch = _macos_arch()                         # "arm64" | "x86_64"
        hit = find("macos", arch, ".zip")
        if hit:
            return hit
        # Fall back to an UNTAGGED (generic) or universal2 zip only. An asset
        # tagged for a different architecture is not a fallback: running an
        # x86_64 build on Apple Silicon needs Rosetta 2, which is not installed
        # by default, so offering it produces a download that may simply refuse
        # to launch. Reporting "no asset for this platform" is the honest answer.
        foreign = _MACOS_ARCH_TAGS - _MACOS_ARCH_ALIASES.get(arch, {arch}) - {"universal2"}
        return find("macos", ".zip", exclude=foreign)
    return None


_MACOS_ARCH_TAGS = {"arm64", "aarch64", "x86_64", "amd64", "intel", "universal2"}
_MACOS_ARCH_ALIASES = {"arm64": {"arm64", "aarch64"},
                       "x86_64": {"x86_64", "amd64", "intel"}}


def _macos_arch():
    """This process's architecture, as build_macos.sh spells it in asset names."""
    import platform
    return (platform.machine() or "").lower()


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
    if kind == "macos":
        # Only reached when the app can NOT be replaced in place (see
        # _macos_install_blocker): the zip is then handed to the user, and a
        # temp dir would be a file they can't find (and that the OS may reap).
        # ~/Downloads is where they'd look. The in-place path downloads to
        # _macos_cache_dir() instead.
        d = os.path.expanduser("~/Downloads")
        if os.path.isdir(d):
            return d
    return tempfile.gettempdir()


_RELEASE_DOWNLOAD = "https://github.com/{repo}/releases/download/"


def _trusted_asset_url(url):
    """True only for an https download of THIS repo's GitHub release assets
    (GitHub then redirects to its own asset CDN; the bytes are hash-checked)."""
    if not isinstance(url, str):
        return False
    prefix = _RELEASE_DOWNLOAD.format(repo=version.GITHUB_REPO)
    rest = url[len(prefix):] if url.startswith(prefix) else None
    return bool(rest) and ".." not in rest and "\\" not in rest and "?" not in rest \
        and "#" not in rest and "@" not in url


def apply_update(asset_url=None, asset_name=None, asset_size=None, asset_sha256=None):
    """Download the asset and install it with the OS-native mechanism.
    Returns {ok, action, ...}. On Windows this spawns the installer and asks
    the caller to quit; on macOS it stages the new bundle, starts the swap
    helper and asks the caller to quit (same action as Windows); on Flatpak it
    installs on the host and asks the user to relaunch.

    NOTHING the caller passes is trusted: the arguments arrive over the JS
    bridge, and if they were believed any script in the UI could make the app
    download and run a file of its choosing. The asset (URL, name, size,
    SHA-256) is re-resolved here from GitHub's latest release for
    version.GITHUB_REPO; the URL must be one of that repo's release downloads;
    a caller URL that differs from it (a release cut since the check, or a
    forged one) is refused. The caller's size/sha256 are ignored.
    """
    del asset_name, asset_size, asset_sha256      # bridge input: never trusted
    kind = platform_kind()
    try:
        chk = check_for_update()
    except Exception as e:
        chk = {"ok": False, "error": str(e)}
    if not chk.get("ok"):
        _set_progress(phase="idle", done=0, total=0)
        return {"ok": False, "error": "could not verify the update "
                f"({chk.get('error') or 'no reply from GitHub'}) - refusing to install"}
    url = chk.get("asset_url")
    if not url:
        return {"ok": False, "error": "no installable asset for this platform"}
    if asset_url and asset_url != url:
        log.warning("update: refused a caller URL that is not the latest release asset")
        return {"ok": False, "error": "the update changed since it was checked - "
                                      "check for updates again"}
    if not _trusted_asset_url(url):
        log.error("update: release asset URL is not a %s release download",
                  version.GITHUB_REPO)
        return {"ok": False, "error": "update refused: unexpected download location"}
    asset_url = url
    asset_size = chk.get("asset_size")
    asset_sha256 = chk.get("asset_sha256")
    # basename(): never let a name with a path separator escape the download dir.
    name = os.path.basename(chk.get("asset_name") or "") \
        or os.path.basename(url.split("?")[0])
    if not name:
        return {"ok": False, "error": "asset has no usable filename"}

    if asset_sha256 is None and asset_size is None:
        # Neither a checksum nor a size to verify the bytes against — refuse
        # rather than execute an unverified installer. This closes the fall-open
        # where the caller omits metadata AND the re-fetch fails to repopulate it
        # (API host rate-limited/offline, or a release cut between check and
        # apply), honouring the docstring's "cannot be bypassed" invariant.
        # (A size-only check remains available when GitHub published no digest.)
        _set_progress(phase="idle", done=0, total=0)
        return {"ok": False,
                "error": "could not verify the update (no checksum or size "
                         "available) — refusing to install an unverified download"}

    # macOS: decide BEFORE downloading whether the running bundle can be
    # replaced where it is — it picks the download location (a cache the user
    # never sees vs. ~/Downloads, where they will have to find the file).
    mac_app = mac_blocker = None
    mac_hint = ("Move AetherHE.app into /Applications and open it from there "
                "to update automatically.")
    ddir = None
    if kind == "macos":
        if _macos_swap_started:
            return {"ok": False, "error": "an update is already being installed"}
        mac_app = _macos_running_bundle()
        mac_blocker = _macos_install_blocker(mac_app)
        if not mac_blocker:
            try:
                ddir = _macos_cache_dir()
            except OSError as e:
                mac_blocker = f"the update cache could not be created ({e})"
        if not mac_blocker:
            # The helper rolled this exact version back last time. Trying again
            # unattended would loop (update on launch -> quit -> fail ->
            # relaunch -> update ...), so this once the download is handed over.
            failed = _macos_take_failed_version()
            if failed and failed == str(chk.get("latest") or ""):
                mac_blocker = (f"The last automatic install of {failed} did not "
                               "complete (details in ~/Library/Caches/AetherHE/"
                               "updates/update.log)")
                mac_hint = ("Quit Aether, unzip the download and replace "
                            "AetherHE.app to update by hand.")
    if ddir is None:
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
            # The bundle (tens of MB) has been copied into the flatpak repo;
            # don't leave one behind in $XDG_DATA_HOME per update.
            try:
                os.remove(dest)
            except OSError:
                pass
            return {"ok": True, "action": "installed", "restart": True}
        if kind == "macos":
            if mac_blocker:
                # Cannot replace the bundle where it is. Hand the verified zip
                # to the user and say why, rather than failing the update.
                log.info("update: not installing in place: %s", mac_blocker)
                _macos_reveal(dest)
                _set_progress(phase="idle", done=0, total=0)
                return {"ok": True, "action": "downloaded", "path": dest,
                        "manual": True, "reason": mac_blocker,
                        "message": f"{mac_blocker}. {mac_hint} This update "
                                   f"was downloaded to {dest}."}
            return _macos_install(dest, mac_app, chk.get("latest"))
        # Bare Linux / source checkout: nothing safe to auto-install.
        return {"ok": True, "action": "downloaded", "path": dest}
    except Exception as e:
        return {"ok": False, "error": str(e)}



# ------------------------------------------------------- macOS in-place ----
# A running .app cannot replace itself: the bundle on disk is the process's own
# code. So the work is split in two. THIS process does everything that can fail
# safely — download, hash check, unpack, verify — while the installed app is
# still untouched. Then a detached /bin/sh helper, which outlives us, does the
# one thing that cannot be done while we run: swap the bundle and relaunch.
#
# The swap is two rename(2) calls on one volume, so there is no moment where a
# half-copied app sits in /Applications, and the old bundle is kept until the
# new one has been verified in place and opened. Any failure puts it back.
MACOS_BUNDLE_ID = "io.github.mrwhosnexus.AetherHE"

# How long the helper waits for this process to exit before giving up (and
# leaving the installed app exactly as it was).
_MACOS_EXIT_TIMEOUT = 60
# `open` relaunches the app and reveals a manual download. Tests replace it:
# they must never start a real app.
_MACOS_OPENER = "/usr/bin/open"
_MACOS_STAGE_PREFIX = ".AetherHE-update-"

# Set once the helper has been started; a second apply_update() in the moment
# before the app quits must not unpack over the bundle the helper is about to
# move. `_macos_last_helper` is the helper's Popen, kept for the tests.
_macos_swap_started = False
_macos_last_helper = None


class UpdateRejected(Exception):
    """The unpacked update is not something we are willing to install."""


def _macos_cache_dir():
    d = os.path.expanduser("~/Library/Caches/AetherHE/updates")
    os.makedirs(d, exist_ok=True)
    return d


def _macos_running_bundle(executable=None, frozen=None):
    """Path of the AetherHE.app this process is running from, or None when it is
    not running from a bundle at all (a source checkout: `python app_web.py`).

    A PyInstaller app's sys.executable is <bundle>/Contents/MacOS/<name>."""
    if frozen is None:
        frozen = bool(getattr(sys, "frozen", False))
    if not frozen:
        return None
    exe = os.path.realpath(executable or sys.executable or "")
    macos_dir = os.path.dirname(exe)
    contents = os.path.dirname(macos_dir)
    app = os.path.dirname(contents)
    if (os.path.basename(macos_dir) != "MacOS"
            or os.path.basename(contents) != "Contents"
            or not app.endswith(".app")):
        return None
    return app


def _volume_read_only(path):
    """True when `path` is on a read-only filesystem (a mounted .dmg). Unknown
    counts as read-only: refusing an in-place install only costs a manual one."""
    try:
        return bool(os.statvfs(path).f_flag & os.ST_RDONLY)
    except (OSError, AttributeError):
        return True


def _macos_install_blocker(app):
    """Why the running bundle can NOT be replaced in place — None when it can.

    Each of these is a situation where swapping the bundle is impossible or
    would not do what the user expects, so the update falls back to handing
    over the download instead."""
    if not app:
        return "Aether is running from source, not from an installed AetherHE.app"
    if "/AppTranslocation/" in app + "/":
        # Gatekeeper runs a quarantined app that was never moved out of the
        # folder it was unpacked into from a randomised read-only mount. The
        # path we see is not where the user's copy lives, so there is nothing
        # here to replace.
        return ("macOS is running Aether from a temporary read-only copy "
                "(App Translocation)")
    if os.path.islink(app) or not os.path.isdir(app):
        return "the running AetherHE.app could not be located on disk"
    if _volume_read_only(app):
        return "Aether is running from a read-only volume (the disk image)"
    parent = os.path.dirname(app)
    # Both renames happen in the parent, and the old bundle is moved into (and
    # later deleted from) a staging folder there, which needs write access to
    # the bundle itself as well.
    if not os.access(parent, os.W_OK | os.X_OK) or not os.access(app, os.W_OK):
        return f"Aether does not have permission to replace itself in {parent}"
    return None


def _macos_reveal(path):
    """Show a manually-installable download in Finder. Best effort."""
    if not _MACOS_OPENER:
        return
    try:
        subprocess.Popen([_MACOS_OPENER, "-R", path], close_fds=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    except Exception as e:
        log.info("update: could not reveal %s (%s)", path, e)


_MACHO_CPU = {0x01000007: "x86_64", 0x0100000C: "arm64", 0x00000007: "i386",
              0x0000000C: "arm"}


def _macho_archs(path):
    """Architectures a Mach-O executable contains, e.g. {"arm64"} or
    {"arm64", "x86_64"} for a universal binary; empty when it is not Mach-O.

    Parsed from the header rather than asked of `lipo`/`file`: on a Mac without
    the Xcode command line tools `lipo` is a stub that pops up an installer
    prompt, which is no way to check an update."""
    try:
        with open(path, "rb") as f:
            head = f.read(4096)
    except OSError:
        return set()
    if len(head) < 8:
        return set()
    magic = head[:4]
    if magic in (b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe"):       # thin, little-endian
        return {_MACHO_CPU.get(struct.unpack("<I", head[4:8])[0], "unknown")}
    if magic in (b"\xfe\xed\xfa\xcf", b"\xfe\xed\xfa\xce"):       # thin, big-endian
        return {_MACHO_CPU.get(struct.unpack(">I", head[4:8])[0], "unknown")}
    if magic in (b"\xca\xfe\xba\xbe", b"\xca\xfe\xba\xbf"):       # universal (fat)
        entry = 20 if magic == b"\xca\xfe\xba\xbe" else 32
        n = struct.unpack(">I", head[4:8])[0]
        if not 0 < n <= 16:                # 0xCAFEBABE is also a Java class file
            return set()
        out = set()
        for i in range(n):
            off = 8 + i * entry
            if off + 4 > len(head):
                break
            out.add(_MACHO_CPU.get(struct.unpack(">I", head[off:off + 4])[0], "unknown"))
        return out
    return set()


def _macos_stage(zip_path, app):
    """Unpack the update into a fresh staging folder NEXT TO the installed app
    and return (stage_dir, staged_app).

    Next to it, not in a temp dir, because the swap is a rename and a rename is
    only atomic within one volume; a sibling folder is on the same volume by
    construction. `ditto -x -k` is the inverse of the `ditto -c -k` the release
    is built with and restores the symlinks and extended attributes the
    signature covers."""
    parent = os.path.dirname(app)
    # Leftovers from an earlier attempt that never finished. Safe to drop: the
    # app we are running from is in place, so nothing in them is the only copy.
    try:
        for n in os.listdir(parent):
            if n.startswith(_MACOS_STAGE_PREFIX):
                shutil.rmtree(os.path.join(parent, n), ignore_errors=True)
    except OSError:
        pass
    stage = tempfile.mkdtemp(prefix=_MACOS_STAGE_PREFIX, dir=parent)
    try:
        payload = os.path.join(stage, "payload")
        cp = subprocess.run(["/usr/bin/ditto", "-x", "-k", zip_path, payload],
                            capture_output=True, text=True, timeout=300)
        if cp.returncode != 0:
            raise UpdateRejected("could not unpack the update: "
                                 + (cp.stderr or cp.stdout or "ditto failed").strip())
        apps = [n for n in os.listdir(payload) if n.endswith(".app")]
        if len(apps) != 1:
            raise UpdateRejected("the update archive does not contain exactly one app")
        staged = os.path.join(payload, apps[0])
        if os.path.islink(staged) or not os.path.isdir(staged):
            raise UpdateRejected("the update archive's app is not a real bundle")
        return stage, staged
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def _macos_verify_staged(staged, expect_version):
    """Raise UpdateRejected unless the unpacked bundle is the app we expect.

    The zip's bytes already matched GitHub's SHA-256. These checks are about
    what is IN it — that it is intact, is this app, is the release we were
    told about and can run on this machine — before it replaces a working
    install."""
    # 1. Intact: every file matches the bundle's own seal. (Ad-hoc signed, so
    #    this proves integrity, not who built it; that is what the hash from
    #    GitHub is for.)
    try:
        cp = subprocess.run(["/usr/bin/codesign", "--verify", "--deep", "--strict", staged],
                            capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.SubprocessError) as e:
        raise UpdateRejected(f"could not check the update's signature ({e})")
    if cp.returncode != 0:
        raise UpdateRejected("the update's code signature is not valid: "
                             + (cp.stderr or cp.stdout or "codesign failed").strip())
    # 2. The right app.
    try:
        with open(os.path.join(staged, "Contents", "Info.plist"), "rb") as f:
            info = plistlib.load(f)
    except Exception as e:
        raise UpdateRejected(f"the update has no readable Info.plist ({e})")
    ident = info.get("CFBundleIdentifier")
    if ident != MACOS_BUNDLE_ID:
        raise UpdateRejected(f"the update is a different app (bundle id {ident!r})")
    # 3. The release we were told about — not an older or mislabelled build.
    got = str(info.get("CFBundleShortVersionString") or "")
    want = str(expect_version or "").strip().lstrip("vV")
    if not want or got != want:
        raise UpdateRejected(f"the update is version {got or '?'}, but the release "
                             f"is {want or '?'}")
    # 4. Runs here.
    exe_name = info.get("CFBundleExecutable") or ""
    exe = os.path.join(staged, "Contents", "MacOS", exe_name)
    if (not exe_name or os.path.basename(exe_name) != exe_name
            or os.path.islink(exe) or not os.path.isfile(exe)
            or not os.access(exe, os.X_OK)):
        raise UpdateRejected("the update has no runnable executable")
    arch = _macos_arch()
    archs = _macho_archs(exe)
    if not archs & _MACOS_ARCH_ALIASES.get(arch, {arch}):
        raise UpdateRejected(f"the update is built for {', '.join(sorted(archs)) or 'an unknown architecture'}, "
                             f"not {arch}")


# usage: swap.sh PID APP NEW BACKUP TIMEOUT LOG OPENER STAGE FAILMARK VERSION
#
# POSIX sh on purpose: /bin/sh is always there, and nothing in the app bundle
# (which is being replaced) may be needed to finish the job.
_MACOS_SWAP_HELPER = r'''#!/bin/sh
# AETHER HE update helper - written and started by updater.py, deletes itself.
PID="$1"; APP="$2"; NEW="$3"; BACKUP="$4"; TIMEOUT="$5"; LOG="$6"; OPENER="$7"; STAGE="$8"
FAILMARK="$9"; VERSION="${10}"
exec >>"$LOG" 2>&1
say() { echo "$(date '+%Y-%m-%d %H:%M:%S') swap[$$]: $*"; }
relaunch() {
  [ -n "$OPENER" ] || return 0
  "$OPENER" "$APP"
}
finish() {
  rm -rf "$STAGE"
  # Tell the next launch this version did not install, so an app set to update
  # on launch does not download, quit, fail and relaunch in a loop.
  if [ "$1" -ne 0 ] && [ -n "$FAILMARK" ]; then echo "$VERSION" > "$FAILMARK"; fi
  say "exit $1"
  exit "$1"
}
restore() {
  # Put the previous bundle back. The backup is only ever deleted (by finish)
  # once it is back in place - if it cannot be restored it is left where it is.
  if [ -e "$APP" ]; then
    mv "$APP" "$STAGE/rejected.app" || rm -rf "$APP"
  fi
  if mv "$BACKUP" "$APP"; then
    say "previous version restored"
    relaunch
    finish "$1"
  fi
  say "ROLLBACK FAILED - the previous version is at $BACKUP"
  [ -n "$FAILMARK" ] && echo "$VERSION" > "$FAILMARK"
  exit 9
}

say "updating $APP (waiting for pid $PID)"
ticks=$((TIMEOUT * 5)); i=0
while kill -0 "$PID" 2>/dev/null; do
  if [ "$i" -ge "$ticks" ]; then
    say "the app is still running after ${TIMEOUT}s - update abandoned, nothing was changed"
    finish 3
  fi
  i=$((i + 1)); sleep 0.2
done

if [ ! -d "$NEW" ] || [ ! -d "$APP" ]; then
  say "the staged update or the installed app is missing - nothing was changed"
  relaunch
  finish 4
fi
rm -rf "$BACKUP"
if ! mv "$APP" "$BACKUP"; then
  say "could not move the installed app aside - nothing was changed"
  relaunch
  finish 5
fi
if ! mv "$NEW" "$APP"; then
  say "could not move the update into place"
  restore 6
fi
if ! /usr/bin/codesign --verify --deep --strict "$APP"; then
  say "the installed update failed verification"
  restore 7
fi
if ! relaunch; then
  say "the updated app could not be opened"
  restore 8
fi
say "update installed"
finish 0
'''


def _macos_own_pid():
    return os.getpid()


def _macos_failmark():
    return os.path.join(_macos_cache_dir(), "failed-version")


def _macos_take_failed_version():
    """The version the swap helper last failed to install, or None. Reading it
    clears it, so one failure costs one manual fallback and the attempt after
    that tries in place again."""
    try:
        p = _macos_failmark()
        with open(p, "r", encoding="utf-8") as f:
            v = f.read().strip()
        os.remove(p)
        return v or None
    except OSError:
        return None


def _macos_launch_swap(app, staged, stage, new_version=""):
    """Write the swap helper into the staging folder and start it detached.

    start_new_session puts it in its own session and process group, so it is
    not taken down with us when the app quits a moment later."""
    global _macos_swap_started, _macos_last_helper
    script = os.path.join(stage, "swap.sh")
    with open(script, "w", encoding="utf-8") as f:
        f.write(_MACOS_SWAP_HELPER)
    os.chmod(script, 0o700)
    backup = os.path.join(stage, "previous.app")
    logf = os.path.join(_macos_cache_dir(), "update.log")
    _macos_last_helper = subprocess.Popen(
        ["/bin/sh", script, str(_macos_own_pid()), app, staged, backup,
         str(_MACOS_EXIT_TIMEOUT), logf, _MACOS_OPENER or "", stage,
         _macos_failmark(), str(new_version or "")],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, close_fds=True, cwd="/",
        start_new_session=True)
    _macos_swap_started = True
    log.info("update: swap helper started (pid %s) for %s", _macos_last_helper.pid, app)


def _macos_install(zip_path, app, expect_version):
    """Stage, verify, and hand over to the swap helper. Returns the same
    quit-now action as the Windows installer path, so the caller exits and the
    helper can replace the bundle."""
    stage = None
    try:
        try:
            stage, staged = _macos_stage(zip_path, app)
            _macos_verify_staged(staged, expect_version)
            _macos_launch_swap(app, staged, stage, expect_version)
        finally:
            # The staged copy is what gets installed; the zip (tens of MB) has
            # done its job either way, and a rejected one must not be reused.
            try:
                os.remove(zip_path)
            except OSError:
                pass
    except UpdateRejected as e:
        log.error("update: staged bundle REJECTED: %s", e)
        if stage:
            shutil.rmtree(stage, ignore_errors=True)
        _set_progress(phase="idle", done=0, total=0)
        return {"ok": False, "error": f"update refused: {e}"}
    except Exception as e:
        if stage:
            shutil.rmtree(stage, ignore_errors=True)
        _set_progress(phase="idle", done=0, total=0)
        return {"ok": False, "error": f"could not install the update: {e}"}
    return {"ok": True, "action": "installer_launched", "quit": True}
