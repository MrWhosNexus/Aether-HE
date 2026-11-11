"""macOS in-place update: refusals, staged-bundle verification, the swap helper.

updater.py replaces the user's installed AetherHE.app. Everything that decides
whether it may, and the shell helper that actually does it, is exercised here
against REAL tools — codesign, ditto and /bin/sh — on throwaway fake bundles in
a temp dir. Nothing is mocked that the claim depends on: a "rejects a bad
signature" test that stubbed codesign would only prove the stub works.

What is faked: the network (urlopen serves a locally built zip), the release
metadata (check_for_update), the PID the helper waits on (a `sleep` we control)
and `open` (a script that records its arguments — a test must never launch an
app).

The tests that need those tools are macOS-only; the pure ones run anywhere.

Run: python -m pytest tests/test_macos_installer.py
"""
import hashlib
import io
import os
import plistlib
import shutil
import stat
import struct
import subprocess
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import updater
import version

BUNDLE_ID = updater.MACOS_BUNDLE_ID
IS_MAC = sys.platform == "darwin"
mac_only = pytest.mark.skipif(not IS_MAC, reason="needs macOS codesign/ditto")
not_root = pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0,
                              reason="root ignores directory permissions")


# ------------------------------------------------------------------ helpers --
def make_app(parent, ver, bundle_id=BUNDLE_ID, name="AetherHE.app", sign=True):
    """A minimal but REAL bundle: a genuine Mach-O executable (a copy of
    /usr/bin/true), an Info.plist and a resource, ad-hoc signed the way
    build_macos.sh signs the shipping app."""
    app = os.path.join(str(parent), name)
    os.makedirs(os.path.join(app, "Contents", "MacOS"))
    os.makedirs(os.path.join(app, "Contents", "Resources"))
    exe = os.path.join(app, "Contents", "MacOS", "AetherHE")
    shutil.copyfile("/usr/bin/true", exe)
    os.chmod(exe, 0o755)
    with open(os.path.join(app, "Contents", "Resources", "marker.txt"), "w") as f:
        f.write(ver)
    with open(os.path.join(app, "Contents", "Info.plist"), "wb") as f:
        plistlib.dump({"CFBundleIdentifier": bundle_id,
                       "CFBundleExecutable": "AetherHE",
                       "CFBundleShortVersionString": ver,
                       "CFBundleVersion": ver,
                       "CFBundlePackageType": "APPL"}, f)
    if sign:
        subprocess.run(["codesign", "--force", "--timestamp=none", "-s", "-",
                        "-i", bundle_id, app], check=True, capture_output=True)
    return app


def zip_app(app, dest):
    """Exactly how build_macos.sh --zip builds the release asset."""
    subprocess.run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent",
                    app, str(dest)], check=True, capture_output=True)
    return str(dest)


def app_version(app):
    with open(os.path.join(app, "Contents", "Info.plist"), "rb") as f:
        return plistlib.load(f)["CFBundleShortVersionString"]


def marker(app):
    with open(os.path.join(app, "Contents", "Resources", "marker.txt")) as f:
        return f.read()


def signature_ok(app):
    return subprocess.run(["codesign", "--verify", "--deep", "--strict", app],
                          capture_output=True).returncode == 0


def leftovers(parent):
    return [n for n in os.listdir(str(parent))
            if n.startswith(updater._MACOS_STAGE_PREFIX)]


def dead_pid():
    p = subprocess.Popen(["/usr/bin/true"])
    p.wait()
    return p.pid


@pytest.fixture
def sleeper():
    """A live process standing in for the running app. kill() + wait() so it is
    reaped — `kill -0` still succeeds on a zombie."""
    procs = []

    def start():
        p = subprocess.Popen(["/bin/sleep", "120"])
        procs.append(p)
        return p

    yield start
    for p in procs:
        if p.poll() is None:
            p.kill()
        p.wait()


@pytest.fixture
def opener(tmp_path):
    """Stand-in for /usr/bin/open: records what it was asked to open."""
    logf = tmp_path / "opened.log"
    script = tmp_path / "fake-open.sh"
    script.write_text(f'#!/bin/sh\necho "$@" >> "{logf}"\n')
    script.chmod(0o755)

    def opened():
        return logf.read_text().splitlines() if logf.exists() else []

    return str(script), opened


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch, tmp_path):
    """No test may reveal/launch for real or write under the real $HOME."""
    monkeypatch.setattr(updater, "_MACOS_OPENER", "")
    monkeypatch.setattr(updater, "_macos_swap_started", False)
    monkeypatch.setattr(updater, "_macos_last_helper", None)
    home = tmp_path / "home"
    (home / "Downloads").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    yield
    h = updater._macos_last_helper
    if h is not None and h.poll() is None:
        h.kill()
        h.wait()


# ----------------------------------------------------- locating the bundle --
def test_source_checkout_has_no_bundle():
    assert updater._macos_running_bundle(
        executable="/usr/local/bin/python3", frozen=False) is None


def test_frozen_executable_resolves_to_its_bundle(tmp_path):
    exe = tmp_path / "Apps" / "AetherHE.app" / "Contents" / "MacOS" / "AetherHE"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")
    got = updater._macos_running_bundle(executable=str(exe), frozen=True)
    assert got == os.path.realpath(str(tmp_path / "Apps" / "AetherHE.app"))


def test_frozen_but_not_in_a_bundle_is_not_a_bundle(tmp_path):
    """A onedir build run straight out of dist/AetherHE/ is frozen, but there
    is no .app to swap."""
    exe = tmp_path / "dist" / "AetherHE" / "AetherHE"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")
    assert updater._macos_running_bundle(executable=str(exe), frozen=True) is None


# ---------------------------------------------------------------- refusals --
def _plain_app(tmp_path, where="Applications"):
    app = tmp_path / where / "AetherHE.app"
    (app / "Contents" / "MacOS").mkdir(parents=True)
    return str(app)


def test_installable_app_has_no_blocker(tmp_path, monkeypatch):
    monkeypatch.setattr(updater, "_volume_read_only", lambda p: False)
    assert updater._macos_install_blocker(_plain_app(tmp_path)) is None


def test_refuses_source_checkout():
    assert "source" in updater._macos_install_blocker(None)


def test_refuses_translocated_app(tmp_path, monkeypatch):
    monkeypatch.setattr(updater, "_volume_read_only", lambda p: False)
    app = ("/private/var/folders/ab/xyz/T/AppTranslocation/"
           "0B9F0E1C-1111-2222-3333-444455556666/d/AetherHE.app")
    assert "Translocation" in updater._macos_install_blocker(app)


def test_refuses_read_only_volume(tmp_path, monkeypatch):
    """Launched straight from the mounted .dmg."""
    monkeypatch.setattr(updater, "_volume_read_only", lambda p: True)
    assert "read-only" in updater._macos_install_blocker(_plain_app(tmp_path))


@pytest.mark.skipif(not hasattr(os, "statvfs"), reason="no statvfs")
def test_volume_read_only_reads_the_mount_flag(tmp_path, monkeypatch):
    class _St:
        def __init__(self, flag):
            self.f_flag = flag

    monkeypatch.setattr(updater.os, "statvfs", lambda p: _St(os.ST_RDONLY))
    assert updater._volume_read_only(str(tmp_path)) is True
    monkeypatch.setattr(updater.os, "statvfs", lambda p: _St(0))
    assert updater._volume_read_only(str(tmp_path)) is False

    def boom(p):
        raise OSError("gone")
    monkeypatch.setattr(updater.os, "statvfs", boom)
    assert updater._volume_read_only(str(tmp_path)) is True, \
        "an unknown volume must count as read-only (refuse, don't guess)"


@pytest.mark.skipif(not hasattr(os, "statvfs"), reason="no statvfs")
def test_a_normal_temp_dir_is_not_read_only(tmp_path):
    assert updater._volume_read_only(str(tmp_path)) is False


@not_root
def test_refuses_when_parent_dir_is_not_writable(tmp_path, monkeypatch):
    """/Applications for a non-admin user."""
    monkeypatch.setattr(updater, "_volume_read_only", lambda p: False)
    app = _plain_app(tmp_path)
    parent = os.path.dirname(app)
    os.chmod(parent, 0o555)
    try:
        assert "permission" in updater._macos_install_blocker(app)
    finally:
        os.chmod(parent, 0o755)


@not_root
def test_refuses_when_the_bundle_itself_is_not_writable(tmp_path, monkeypatch):
    """Installed by another account: the folder is writable, the app is not."""
    monkeypatch.setattr(updater, "_volume_read_only", lambda p: False)
    app = _plain_app(tmp_path)
    os.chmod(app, 0o555)
    try:
        assert "permission" in updater._macos_install_blocker(app)
    finally:
        os.chmod(app, 0o755)


def test_refuses_a_symlinked_bundle(tmp_path, monkeypatch):
    monkeypatch.setattr(updater, "_volume_read_only", lambda p: False)
    real = _plain_app(tmp_path, "real")
    link = tmp_path / "AetherHE.app"
    os.symlink(real, str(link))
    assert updater._macos_install_blocker(str(link)) is not None


# ------------------------------------------------------------ Mach-O archs --
def _write(tmp_path, data, name="bin"):
    p = tmp_path / name
    p.write_bytes(data)
    return str(p)


def test_macho_thin_arm64(tmp_path):
    p = _write(tmp_path, struct.pack("<II", 0xFEEDFACF, 0x0100000C) + b"\0" * 24)
    assert updater._macho_archs(p) == {"arm64"}


def test_macho_thin_x86_64(tmp_path):
    p = _write(tmp_path, struct.pack("<II", 0xFEEDFACF, 0x01000007) + b"\0" * 24)
    assert updater._macho_archs(p) == {"x86_64"}


def test_macho_universal(tmp_path):
    fat = struct.pack(">II", 0xCAFEBABE, 2)
    fat += struct.pack(">IIIII", 0x01000007, 3, 0x4000, 0x100, 14)
    fat += struct.pack(">IIIII", 0x0100000C, 0x80000002, 0xC000, 0x100, 14)
    assert updater._macho_archs(_write(tmp_path, fat)) == {"arm64", "x86_64"}


def test_macho_rejects_non_macho(tmp_path):
    assert updater._macho_archs(_write(tmp_path, b"#!/bin/sh\necho hi\n")) == set()
    assert updater._macho_archs(_write(tmp_path, b"", "empty")) == set()
    assert updater._macho_archs(str(tmp_path / "missing")) == set()
    # 0xCAFEBABE is also the Java class-file magic; the "arch count" there is
    # a version number far above any real slice count.
    java = struct.pack(">IHH", 0xCAFEBABE, 0, 61) + b"\0" * 32
    assert updater._macho_archs(_write(tmp_path, java, "A.class")) == set()


@mac_only
def test_macho_reads_a_real_system_binary():
    assert updater._macos_arch() in updater._macho_archs("/usr/bin/true")


# --------------------------------------------------- staged-bundle checks --
@mac_only
def test_good_staged_bundle_is_accepted(tmp_path):
    app = make_app(tmp_path, "9.9.9")
    updater._macos_verify_staged(app, "9.9.9")        # must not raise
    updater._macos_verify_staged(app, "v9.9.9")       # tag spelling


@mac_only
def test_rejects_wrong_bundle_id(tmp_path):
    """Validly signed, right version — but it is some other app."""
    app = make_app(tmp_path, "9.9.9", bundle_id="com.example.NotAether")
    with pytest.raises(updater.UpdateRejected, match="different app"):
        updater._macos_verify_staged(app, "9.9.9")


@mac_only
def test_rejects_tampered_bundle(tmp_path):
    """A file changed after signing: the seal no longer matches."""
    app = make_app(tmp_path, "9.9.9")
    with open(os.path.join(app, "Contents", "Resources", "marker.txt"), "a") as f:
        f.write("tampered")
    with pytest.raises(updater.UpdateRejected, match="signature"):
        updater._macos_verify_staged(app, "9.9.9")


@mac_only
def test_rejects_added_file(tmp_path):
    app = make_app(tmp_path, "9.9.9")
    with open(os.path.join(app, "Contents", "Resources", "extra.dylib"), "w") as f:
        f.write("not part of the signed bundle")
    with pytest.raises(updater.UpdateRejected, match="signature"):
        updater._macos_verify_staged(app, "9.9.9")


@mac_only
def test_rejects_unsigned_bundle(tmp_path):
    app = make_app(tmp_path, "9.9.9", sign=False)
    # /usr/bin/true carries Apple's own signature; strip it so the bundle is
    # genuinely unsigned rather than signed-by-someone-else.
    subprocess.run(["codesign", "--remove-signature",
                    os.path.join(app, "Contents", "MacOS", "AetherHE")],
                   capture_output=True)
    with pytest.raises(updater.UpdateRejected, match="signature"):
        updater._macos_verify_staged(app, "9.9.9")


@mac_only
def test_rejects_version_mismatch(tmp_path):
    """The release says 9.9.9; the zip holds something else (a stale or
    mislabelled build, or a downgrade)."""
    app = make_app(tmp_path, "9.9.8")
    with pytest.raises(updater.UpdateRejected, match="version 9.9.8"):
        updater._macos_verify_staged(app, "9.9.9")


@mac_only
def test_rejects_when_release_version_is_unknown(tmp_path):
    app = make_app(tmp_path, "9.9.9")
    with pytest.raises(updater.UpdateRejected):
        updater._macos_verify_staged(app, "")
    with pytest.raises(updater.UpdateRejected):
        updater._macos_verify_staged(app, None)


@mac_only
def test_rejects_wrong_architecture(tmp_path, monkeypatch):
    app = make_app(tmp_path, "9.9.9")
    monkeypatch.setattr(updater, "_macos_arch", lambda: "arm64")
    monkeypatch.setattr(updater, "_macho_archs", lambda p: {"x86_64"})
    with pytest.raises(updater.UpdateRejected, match="x86_64"):
        updater._macos_verify_staged(app, "9.9.9")


@mac_only
def test_accepts_universal_build_on_either_arch(tmp_path, monkeypatch):
    app = make_app(tmp_path, "9.9.9")
    monkeypatch.setattr(updater, "_macho_archs", lambda p: {"arm64", "x86_64"})
    for arch in ("arm64", "x86_64"):
        monkeypatch.setattr(updater, "_macos_arch", lambda a=arch: a)
        updater._macos_verify_staged(app, "9.9.9")


@mac_only
def test_rejects_non_macho_executable(tmp_path, monkeypatch):
    app = make_app(tmp_path, "9.9.9")
    monkeypatch.setattr(updater, "_macho_archs", lambda p: set())
    with pytest.raises(updater.UpdateRejected, match="unknown architecture"):
        updater._macos_verify_staged(app, "9.9.9")


# ------------------------------------------------------------------ staging --
@mac_only
def test_stage_unpacks_next_to_the_app_with_signature_intact(tmp_path):
    apps = tmp_path / "Applications"
    apps.mkdir()
    installed = make_app(apps, "1.0.0")
    z = zip_app(make_app(tmp_path / "build", "9.9.9"), tmp_path / "u.zip")

    stage, staged = updater._macos_stage(z, installed)
    assert os.path.dirname(stage) == str(apps), "staging must be a sibling (same volume)"
    assert os.stat(stage).st_dev == os.stat(installed).st_dev
    assert stat.S_IMODE(os.stat(stage).st_mode) == 0o700
    assert app_version(staged) == "9.9.9"
    assert signature_ok(staged), "the signature did not survive ditto -c -k / -x -k"
    assert app_version(installed) == "1.0.0", "staging must not touch the installed app"


@mac_only
def test_stage_rejects_garbage_and_leaves_nothing_behind(tmp_path):
    apps = tmp_path / "Applications"
    apps.mkdir()
    installed = make_app(apps, "1.0.0")
    bad = tmp_path / "u.zip"
    bad.write_bytes(b"this is not a zip archive")
    with pytest.raises(updater.UpdateRejected):
        updater._macos_stage(str(bad), installed)
    assert leftovers(apps) == []


@mac_only
def test_stage_rejects_archive_without_exactly_one_app(tmp_path):
    apps = tmp_path / "Applications"
    apps.mkdir()
    installed = make_app(apps, "1.0.0")
    src = tmp_path / "two"
    make_app(src, "9.9.9", name="AetherHE.app")
    make_app(src, "9.9.9", name="Other.app")
    z = tmp_path / "two.zip"
    subprocess.run(["ditto", "-c", "-k", str(src), str(z)], check=True)
    with pytest.raises(updater.UpdateRejected, match="exactly one"):
        updater._macos_stage(str(z), installed)
    assert leftovers(apps) == []


@mac_only
def test_stage_clears_leftovers_from_an_earlier_attempt(tmp_path):
    apps = tmp_path / "Applications"
    apps.mkdir()
    installed = make_app(apps, "1.0.0")
    stale = apps / (updater._MACOS_STAGE_PREFIX + "stale")
    (stale / "payload").mkdir(parents=True)
    z = zip_app(make_app(tmp_path / "build", "9.9.9"), tmp_path / "u.zip")
    stage, _ = updater._macos_stage(z, installed)
    assert leftovers(apps) == [os.path.basename(stage)]


# ------------------------------------------------------- the swap helper ----
# Run for real: /bin/sh, the script text updater.py ships, real renames, real
# codesign. Layout mirrors what _macos_stage/_macos_launch_swap produce.
class Swap:
    def __init__(self, tmp_path, opener_path, new_ver="9.9.9"):
        self.parent = tmp_path / "Applications"
        self.parent.mkdir()
        self.app = make_app(self.parent, "1.0.0")
        self.stage = str(self.parent / (updater._MACOS_STAGE_PREFIX + "test"))
        os.makedirs(os.path.join(self.stage, "payload"))
        self.new = make_app(os.path.join(self.stage, "payload"), new_ver)
        self.backup = os.path.join(self.stage, "previous.app")
        self.log = str(tmp_path / "update.log")
        self.script = os.path.join(self.stage, "swap.sh")
        with open(self.script, "w") as f:
            f.write(updater._MACOS_SWAP_HELPER)
        self.opener = opener_path
        self.failmark = str(tmp_path / "failed-version")

    def argv(self, pid, timeout=20):
        return ["/bin/sh", self.script, str(pid), self.app, self.new, self.backup,
                str(timeout), self.log, self.opener, self.stage,
                self.failmark, "9.9.9"]

    def failed_version(self):
        if not os.path.exists(self.failmark):
            return None
        return open(self.failmark).read().strip()

    def run(self, pid, timeout=20):
        return subprocess.run(self.argv(pid, timeout), capture_output=True,
                              timeout=60).returncode

    def logtext(self):
        return open(self.log).read() if os.path.exists(self.log) else ""


@mac_only
def test_helper_swaps_relaunches_and_cleans_up(tmp_path, opener):
    path, opened = opener
    s = Swap(tmp_path, path)
    assert s.run(dead_pid()) == 0, s.logtext()
    assert app_version(s.app) == "9.9.9" and marker(s.app) == "9.9.9"
    assert signature_ok(s.app)
    assert opened() == [s.app], "must relaunch the app at its ORIGINAL path"
    assert not os.path.exists(s.stage), "backup + staging must be deleted on success"
    assert os.listdir(str(s.parent)) == ["AetherHE.app"]
    assert "update installed" in s.logtext()
    assert s.failed_version() is None


@mac_only
def test_helper_waits_for_the_app_to_exit(tmp_path, opener, sleeper):
    """Swapping a bundle out from under a live process is the bug this whole
    design exists to avoid."""
    path, opened = opener
    s = Swap(tmp_path, path)
    app_proc = sleeper()
    helper = subprocess.Popen(s.argv(app_proc.pid))
    try:
        time.sleep(1.2)
        assert helper.poll() is None, "helper finished while the app was still running"
        assert app_version(s.app) == "1.0.0", "bundle was swapped under a running app"
        assert opened() == []
        app_proc.kill()
        app_proc.wait()
        assert helper.wait(timeout=30) == 0, s.logtext()
    finally:
        if helper.poll() is None:
            helper.kill()
            helper.wait()
    assert app_version(s.app) == "9.9.9"
    assert opened() == [s.app]


@mac_only
def test_helper_gives_up_if_the_app_never_exits(tmp_path, opener, sleeper):
    path, opened = opener
    s = Swap(tmp_path, path)
    assert s.run(sleeper().pid, timeout=1) == 3
    assert app_version(s.app) == "1.0.0" and signature_ok(s.app)
    assert opened() == [], "the app is still running — must not open a second copy"
    assert not os.path.exists(s.stage)
    assert "nothing was changed" in s.logtext()


@mac_only
def test_helper_restores_old_bundle_when_the_new_one_fails_verification(tmp_path, opener):
    """The staged bundle is corrupted between verification and the swap."""
    path, opened = opener
    s = Swap(tmp_path, path)
    with open(os.path.join(s.new, "Contents", "Resources", "marker.txt"), "a") as f:
        f.write("corrupted after staging")
    assert s.run(dead_pid()) == 7, s.logtext()
    assert app_version(s.app) == "1.0.0" and marker(s.app) == "1.0.0"
    assert signature_ok(s.app), "the restored bundle must be the intact original"
    assert opened() == [s.app], "the restored app must be relaunched"
    assert os.listdir(str(s.parent)) == ["AetherHE.app"]
    assert "previous version restored" in s.logtext()
    assert s.failed_version() == "9.9.9", "a rollback must be recorded for next launch"


@mac_only
def test_helper_restores_old_bundle_when_the_new_one_will_not_open(tmp_path):
    s = Swap(tmp_path, "/usr/bin/false")
    assert s.run(dead_pid()) == 8, s.logtext()
    assert app_version(s.app) == "1.0.0" and signature_ok(s.app)
    assert os.listdir(str(s.parent)) == ["AetherHE.app"]


@mac_only
@not_root
def test_helper_restores_old_bundle_when_the_update_cannot_be_moved_in(tmp_path, opener):
    """Old bundle is already aside when the second rename fails."""
    path, opened = opener
    s = Swap(tmp_path, path)
    payload = os.path.dirname(s.new)
    os.chmod(payload, 0o555)             # rename OUT of payload/ now fails
    try:
        rc = s.run(dead_pid())
    finally:
        if os.path.exists(payload):
            os.chmod(payload, 0o755)
    assert rc == 6, s.logtext()
    assert app_version(s.app) == "1.0.0" and signature_ok(s.app)
    assert opened() == [s.app]
    assert "previous version restored" in s.logtext()


@mac_only
@not_root
def test_helper_changes_nothing_when_the_old_bundle_cannot_be_moved(tmp_path, opener):
    path, opened = opener
    s = Swap(tmp_path, path)
    os.chmod(str(s.parent), 0o555)
    try:
        rc = s.run(dead_pid())
        assert rc == 5, s.logtext()
        assert app_version(s.app) == "1.0.0" and signature_ok(s.app)
        assert opened() == [s.app]
    finally:
        os.chmod(str(s.parent), 0o755)


@mac_only
def test_helper_changes_nothing_when_the_staged_bundle_is_gone(tmp_path, opener):
    path, opened = opener
    s = Swap(tmp_path, path)
    shutil.rmtree(s.new)
    assert s.run(dead_pid()) == 4
    assert app_version(s.app) == "1.0.0" and signature_ok(s.app)
    assert opened() == [s.app]


@mac_only
def test_helper_handles_paths_with_spaces(tmp_path, opener):
    """~/Applications/My Apps/AETHER HE.app — every path is quoted."""
    path, opened = opener
    root = tmp_path / "My Apps"
    root.mkdir()
    s = Swap(root, path)
    renamed = os.path.join(str(s.parent), "AETHER HE.app")
    os.rename(s.app, renamed)
    s.app = renamed
    assert s.run(dead_pid()) == 0, s.logtext()
    assert app_version(renamed) == "9.9.9"
    assert opened() == [renamed]


# ------------------------------------------------- end to end: apply_update --
class _FakeResp:
    def __init__(self, data):
        self._buf = io.BytesIO(data)
        self.headers = {"Content-Length": str(len(data))}

    def read(self, n=-1):
        return self._buf.read(n)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Release:
    """A locally built fake release: v1.0.0 installed, vNEW published."""

    def __init__(self, tmp_path, monkeypatch, opener_path, sleeper,
                 zip_ver="9.9.9", tag="9.9.9"):
        self.parent = tmp_path / "Applications"
        self.parent.mkdir()
        self.app = make_app(self.parent, "1.0.0")
        self.zip = zip_app(make_app(tmp_path / "build", zip_ver),
                           tmp_path / "AetherHE-macos-arm64.zip")
        self.data = open(self.zip, "rb").read()
        self.url = ("https://github.com/%s/releases/download/v%s/"
                    "AetherHE-macos-arm64.zip" % (version.GITHUB_REPO, tag))
        self.chk = {"ok": True, "update": True, "newer": True,
                    "current": "1.0.0", "latest": tag, "kind": "macos",
                    "asset_url": self.url,
                    "asset_name": "AetherHE-macos-arm64.zip",
                    "asset_size": len(self.data),
                    "asset_sha256": hashlib.sha256(self.data).hexdigest()}
        self.requested = []
        self.app_proc = sleeper()                       # "the running app"

        def urlopen(req, timeout=None):
            self.requested.append(req.full_url)
            return _FakeResp(self.data)

        monkeypatch.setattr(updater, "platform_kind", lambda: "macos")
        monkeypatch.setattr(updater, "check_for_update", lambda *a, **k: dict(self.chk))
        monkeypatch.setattr(updater.urllib.request, "urlopen", urlopen)
        monkeypatch.setattr(updater, "_macos_own_pid", lambda: self.app_proc.pid)
        monkeypatch.setattr(updater, "_MACOS_OPENER", opener_path)
        # What a PyInstaller .app looks like from the inside.
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "executable",
                            os.path.join(self.app, "Contents", "MacOS", "AetherHE"))

    def quit_app(self):
        self.app_proc.kill()
        self.app_proc.wait()

    def cache(self):
        return os.path.expanduser("~/Library/Caches/AetherHE/updates")


@mac_only
def test_end_to_end_update_swaps_v1_for_v2(tmp_path, monkeypatch, opener, sleeper):
    path, opened = opener
    rel = Release(tmp_path, monkeypatch, path, sleeper)
    app = os.path.realpath(rel.app)

    res = updater.apply_update(rel.url)

    # Same action the Windows installer path returns: the bridge quits on it.
    assert res == {"ok": True, "action": "installer_launched", "quit": True}
    assert rel.requested == [rel.url]
    # Until the app exits, the installed bundle is untouched.
    time.sleep(0.8)
    assert app_version(app) == "1.0.0"
    assert opened() == []
    assert not os.path.exists(os.path.join(rel.cache(), "AetherHE-macos-arm64.zip")), \
        "the downloaded zip should be removed once staged"

    rel.quit_app()
    assert updater._macos_last_helper.wait(timeout=30) == 0

    assert app_version(app) == "9.9.9" and marker(app) == "9.9.9"
    assert signature_ok(app)
    assert opened() == [app]
    assert os.listdir(str(rel.parent)) == ["AetherHE.app"], "staging/backup left behind"
    with open(os.path.join(rel.cache(), "update.log")) as f:
        assert "update installed" in f.read()


@mac_only
def test_end_to_end_refuses_a_zip_whose_version_is_not_the_release(
        tmp_path, monkeypatch, opener, sleeper):
    path, opened = opener
    rel = Release(tmp_path, monkeypatch, path, sleeper, zip_ver="9.9.8", tag="9.9.9")
    res = updater.apply_update(rel.url)
    assert res["ok"] is False and "refused" in res["error"]
    assert "quit" not in res, "a refused update must not make the app quit"
    assert updater._macos_last_helper is None, "helper started for a rejected bundle"
    assert app_version(rel.app) == "1.0.0" and signature_ok(rel.app)
    assert os.listdir(str(rel.parent)) == ["AetherHE.app"]
    assert os.listdir(rel.cache()) == [], "a rejected download must not be kept"


@mac_only
def test_end_to_end_refuses_tampered_download(tmp_path, monkeypatch, opener, sleeper):
    """The SHA-256 gate still comes first on macOS: nothing is even unpacked."""
    path, opened = opener
    rel = Release(tmp_path, monkeypatch, path, sleeper)
    rel.chk["asset_sha256"] = "0" * 64
    res = updater.apply_update(rel.url)
    assert res["ok"] is False and "integrity" in res["error"]
    assert updater._macos_last_helper is None
    assert os.listdir(str(rel.parent)) == ["AetherHE.app"]
    assert app_version(rel.app) == "1.0.0"


@mac_only
def test_end_to_end_refuses_a_caller_supplied_url(tmp_path, monkeypatch, opener, sleeper):
    """The bridge cannot point the macOS installer at a zip of its choosing."""
    path, opened = opener
    rel = Release(tmp_path, monkeypatch, path, sleeper)
    res = updater.apply_update("https://github.com/evil/repo/releases/download/v9/x.zip")
    assert res["ok"] is False
    assert rel.requested == [], "nothing may be downloaded from a caller URL"
    assert updater._macos_last_helper is None


@mac_only
def test_end_to_end_refuses_untrusted_release_url(tmp_path, monkeypatch, opener, sleeper):
    path, opened = opener
    rel = Release(tmp_path, monkeypatch, path, sleeper)
    rel.chk["asset_url"] = "https://example.com/AetherHE-macos-arm64.zip"
    res = updater.apply_update()
    assert res["ok"] is False and "unexpected download location" in res["error"]
    assert rel.requested == []


@mac_only
def test_second_apply_while_a_swap_is_pending_is_refused(
        tmp_path, monkeypatch, opener, sleeper):
    path, opened = opener
    rel = Release(tmp_path, monkeypatch, path, sleeper)
    assert updater.apply_update(rel.url)["ok"] is True
    again = updater.apply_update(rel.url)
    assert again["ok"] is False and "already" in again["error"]
    rel.quit_app()
    assert updater._macos_last_helper.wait(timeout=30) == 0
    assert app_version(rel.app) == "9.9.9"


@mac_only
def test_a_rolled_back_version_is_not_retried_in_a_loop(
        tmp_path, monkeypatch, opener, sleeper):
    """Update-on-launch + a version that always rolls back must not become
    download -> quit -> fail -> relaunch -> download ... forever. After a
    rollback the next attempt hands the zip over instead; the one after that
    may try in place again."""
    path, opened = opener
    rel = Release(tmp_path, monkeypatch, path, sleeper)
    revealed = []
    monkeypatch.setattr(updater, "_macos_reveal", revealed.append)
    os.makedirs(rel.cache())
    with open(os.path.join(rel.cache(), "failed-version"), "w") as f:
        f.write("9.9.9\n")                      # what the helper leaves behind

    res = updater.apply_update(rel.url)
    assert res["ok"] is True and res["action"] == "downloaded" and "quit" not in res
    assert "did not complete" in res["reason"]
    assert updater._macos_last_helper is None
    assert len(revealed) == 1
    assert app_version(rel.app) == "1.0.0"

    res = updater.apply_update(rel.url)          # the marker was consumed
    assert res == {"ok": True, "action": "installer_launched", "quit": True}
    rel.quit_app()
    assert updater._macos_last_helper.wait(timeout=30) == 0
    assert app_version(rel.app) == "9.9.9"


@mac_only
def test_a_failure_of_an_older_version_does_not_block_a_newer_one(
        tmp_path, monkeypatch, opener, sleeper):
    path, opened = opener
    rel = Release(tmp_path, monkeypatch, path, sleeper)
    os.makedirs(rel.cache())
    with open(os.path.join(rel.cache(), "failed-version"), "w") as f:
        f.write("9.9.8\n")
    assert updater.apply_update(rel.url).get("quit") is True
    rel.quit_app()
    assert updater._macos_last_helper.wait(timeout=30) == 0
    assert app_version(rel.app) == "9.9.9"


# ----------------------------------- fallback: download and reveal instead --
def _fallback_release(tmp_path, monkeypatch):
    data = b"PK-not-really-a-zip" * 100
    url = ("https://github.com/%s/releases/download/v9.9.9/"
           "AetherHE-macos-arm64.zip" % version.GITHUB_REPO)
    chk = {"ok": True, "latest": "9.9.9", "asset_url": url,
           "asset_name": "AetherHE-macos-arm64.zip", "asset_size": len(data),
           "asset_sha256": hashlib.sha256(data).hexdigest()}
    monkeypatch.setattr(updater, "platform_kind", lambda: "macos")
    monkeypatch.setattr(updater, "check_for_update", lambda *a, **k: dict(chk))
    monkeypatch.setattr(updater.urllib.request, "urlopen",
                        lambda req, timeout=None: _FakeResp(data))
    revealed = []
    monkeypatch.setattr(updater, "_macos_reveal", revealed.append)

    def no_install(*a, **k):
        raise AssertionError("in-place install attempted despite a blocker")
    monkeypatch.setattr(updater, "_macos_install", no_install)
    return url, data, revealed


@pytest.mark.parametrize("blocker", [
    "macOS is running Aether from a temporary read-only copy (App Translocation)",
    "Aether is running from a read-only volume (the disk image)",
    "Aether does not have permission to replace itself in /Applications",
    "Aether is running from source, not from an installed AetherHE.app",
])
def test_blocked_install_falls_back_to_download_and_reveal(tmp_path, monkeypatch, blocker):
    url, data, revealed = _fallback_release(tmp_path, monkeypatch)
    monkeypatch.setattr(updater, "_macos_install_blocker", lambda app: blocker)

    res = updater.apply_update(url)

    want = os.path.join(os.path.expanduser("~/Downloads"), "AetherHE-macos-arm64.zip")
    assert res["ok"] is True and res["action"] == "downloaded"
    assert "quit" not in res, "the app must keep running when nothing was installed"
    assert res["path"] == want and open(want, "rb").read() == data
    assert res["reason"] == blocker
    assert "/Applications" in res["message"]
    assert revealed == [want]


def test_source_checkout_falls_back_without_stubbing_the_blocker(tmp_path, monkeypatch):
    """The real decision path: pytest is not a frozen .app, so the real
    _macos_running_bundle/_macos_install_blocker must send this to the fallback."""
    url, data, revealed = _fallback_release(tmp_path, monkeypatch)
    monkeypatch.delattr(sys, "frozen", raising=False)
    res = updater.apply_update(url)
    assert res["ok"] is True and res["action"] == "downloaded"
    assert "source" in res["reason"]
    assert len(revealed) == 1


def test_fallback_still_verifies_the_download(tmp_path, monkeypatch):
    url, data, revealed = _fallback_release(tmp_path, monkeypatch)
    chk = updater.check_for_update()
    chk["asset_sha256"] = "0" * 64
    monkeypatch.setattr(updater, "check_for_update", lambda *a, **k: dict(chk))
    monkeypatch.setattr(updater, "_macos_install_blocker", lambda app: "blocked")
    res = updater.apply_update(url)
    assert res["ok"] is False and "integrity" in res["error"]
    assert revealed == []
    assert os.listdir(os.path.expanduser("~/Downloads")) == []


def test_reveal_never_raises_and_is_skipped_without_an_opener(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(updater.subprocess, "Popen",
                        lambda *a, **k: calls.append(a[0]))
    monkeypatch.setattr(updater, "_MACOS_OPENER", "")
    updater._macos_reveal(str(tmp_path / "x.zip"))
    assert calls == []
    monkeypatch.setattr(updater, "_MACOS_OPENER", "/usr/bin/open")
    updater._macos_reveal(str(tmp_path / "x.zip"))
    assert calls == [["/usr/bin/open", "-R", str(tmp_path / "x.zip")]]

    def boom(*a, **k):
        raise OSError("no open here")
    monkeypatch.setattr(updater.subprocess, "Popen", boom)
    updater._macos_reveal(str(tmp_path / "x.zip"))        # must not raise


# ------------------------------------------------------ the helper's text ----
def test_helper_script_is_posix_sh_and_self_contained():
    s = updater._MACOS_SWAP_HELPER
    assert s.startswith("#!/bin/sh\n")
    # Nothing from the bundle being replaced, and no interpreter that may be
    # missing on a stock Mac.
    for forbidden in ("python", "bash", "osascript", "Contents/MacOS"):
        assert forbidden not in s, f"helper must not depend on {forbidden}"
    if os.path.exists("/bin/sh"):
        assert subprocess.run(["/bin/sh", "-n", "-c", s]).returncode == 0
