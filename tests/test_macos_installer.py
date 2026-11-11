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


def _ps_usable():
    """The helper identifies a process by asking /bin/ps for its executable.
    A Seatbelt sandbox refuses to run ps at all (it is setuid), and then the
    helper - correctly - signals nothing, so the tests that expect a process
    to be stopped can only run where ps does."""
    try:
        cp = subprocess.run(["/bin/ps", "-p", str(os.getpid()), "-o", "comm="],
                            capture_output=True, timeout=10)
        return cp.returncode == 0 and bool(cp.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        return False


needs_ps = pytest.mark.skipif(not (IS_MAC and _ps_usable()),
                              reason="/bin/ps is not runnable here (sandbox)")


# ------------------------------------------------------------------ helpers --
def make_app(parent, ver, bundle_id=BUNDLE_ID, name="AetherHE.app", sign=True,
             exe_src="/usr/bin/true"):
    """A minimal but REAL bundle: a genuine Mach-O executable (a copy of
    /usr/bin/true - or of /bin/sleep for an app that must keep running), an
    Info.plist and a resource, ad-hoc signed the way build_macos.sh signs the
    shipping app."""
    app = os.path.join(str(parent), name)
    os.makedirs(os.path.join(app, "Contents", "MacOS"))
    os.makedirs(os.path.join(app, "Contents", "Resources"))
    exe = os.path.join(app, "Contents", "MacOS", "AetherHE")
    shutil.copyfile(exe_src, exe)
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


def expect_health(opener_path, marker_path):
    """Make the `opener` fixture's fake app report healthy at `marker_path`."""
    if opener_path and os.path.basename(opener_path) == "fake-open.sh":
        with open(opener_path + ".health", "a") as f:
            f.write(marker_path + "\n")


def silent_opener(tmp_path, body=""):
    """An `open` that succeeds but whose app never reports healthy. `body` is
    extra shell run on each call ($1 is the app path)."""
    logf = tmp_path / "silent-opened.log"
    script = tmp_path / "silent-open.sh"
    script.write_text(f'#!/bin/sh\necho "$@" >> "{logf}"\n{body}\n')
    script.chmod(0o755)
    return str(script), (lambda: logf.read_text().splitlines() if logf.exists() else [])


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
    """Stand-in for /usr/bin/open: records what it was asked to open and then
    plays a HEALTHY app - it writes every health marker listed in
    `<script>.health` (Swap/Release add theirs), which is what the real app
    does once its window is up."""
    logf = tmp_path / "opened.log"
    script = tmp_path / "fake-open.sh"
    script.write_text(
        '#!/bin/sh\n'
        f'echo "$@" >> "{logf}"\n'
        f'if [ -f "{script}.health" ]; then\n'
        f'  while IFS= read -r p; do echo $$ > "$p"; done < "{script}.health"\n'
        'fi\n')
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
    monkeypatch.setattr(updater, "_installer_proc", None)
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
    def __init__(self, tmp_path, opener_path, new_ver="9.9.9", new_exe="/usr/bin/true"):
        self.parent = tmp_path / "Applications"
        self.parent.mkdir()
        self.app = make_app(self.parent, "1.0.0")
        self.stage = str(self.parent / (updater._MACOS_STAGE_PREFIX + "test"))
        os.makedirs(os.path.join(self.stage, "payload"))
        self.new = make_app(os.path.join(self.stage, "payload"), new_ver,
                            exe_src=new_exe)
        self.backup = os.path.join(self.stage, "previous.app")
        self.log = str(tmp_path / "update.log")
        self.script = os.path.join(self.stage, "swap.sh")
        with open(self.script, "w") as f:
            f.write(updater._MACOS_SWAP_HELPER)
        self.opener = opener_path
        self.failmark = str(tmp_path / "failed-version")
        self.health = str(tmp_path / "healthy-9.9.9")
        self.pidfile = str(tmp_path / "launching-9.9.9")
        self.health_wait = 2
        expect_health(opener_path, self.health)

    def argv(self, pid, timeout=20):
        return ["/bin/sh", self.script, str(pid), self.app, self.new, self.backup,
                str(timeout), self.log, self.opener, self.stage,
                self.failmark, "9.9.9", self.health, str(self.health_wait),
                self.pidfile]

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
    assert s.failed_version() is None, \
        "nothing was attempted: this version did not FAIL to install"


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
        assert s.failed_version() == "9.9.9", \
            "a refused move is likely to be refused again: it must be on record"
        assert "nothing was changed" in s.logtext()
    finally:
        os.chmod(str(s.parent), 0o755)


@mac_only
@not_root
def test_a_refused_move_is_on_record_before_the_app_is_reopened(tmp_path):
    """Exit 5 reopens the existing app, which checks for updates as it
    starts: the record must already be there, or update-on-launch loops."""
    path, opened, seen = _recording_opener(tmp_path, tmp_path / "failed-version")
    s = Swap(tmp_path, path)
    os.chmod(str(s.parent), 0o555)
    try:
        assert s.run(dead_pid()) == 5, s.logtext()
    finally:
        os.chmod(str(s.parent), 0o755)
    assert opened() == [s.app]
    assert seen() == ["9.9.9"]
    assert app_version(s.app) == "1.0.0" and signature_ok(s.app)


@mac_only
def test_a_missing_staged_bundle_leaves_no_record(tmp_path, opener):
    """Exit 4 stays record-free: that version was never tried."""
    path, opened = opener
    s = Swap(tmp_path, path)
    shutil.rmtree(s.new)
    assert s.run(dead_pid()) == 4, s.logtext()
    assert s.failed_version() is None


@mac_only
def test_helper_changes_nothing_when_the_staged_bundle_is_gone(tmp_path, opener):
    path, opened = opener
    s = Swap(tmp_path, path)
    shutil.rmtree(s.new)
    assert s.run(dead_pid()) == 4
    assert app_version(s.app) == "1.0.0" and signature_ok(s.app)
    assert opened() == [s.app]
    assert s.failed_version() is None, "nothing was changed: no failure record"


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
        monkeypatch.setattr(updater, "_MACOS_HEALTH_TIMEOUT", 2)
        expect_health(opener_path, os.path.join(
            os.path.expanduser("~/Library/Caches/AetherHE/updates"), "healthy-" + tag))
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


def _record_failure(rel, ver):
    os.makedirs(rel.cache(), exist_ok=True)
    with open(os.path.join(rel.cache(), "failed-version"), "w") as f:
        f.write(ver + "\n")                     # what the helper leaves behind


def _failure_record(rel):
    p = os.path.join(rel.cache(), "failed-version")
    return open(p).read().strip() if os.path.exists(p) else None


@mac_only
def test_a_rolled_back_version_is_never_retried_automatically(
        tmp_path, monkeypatch, opener, sleeper):
    """Update-on-launch + a version that always rolls back must not become
    download -> quit -> fail -> relaunch -> download ... The record used to be
    consumed by the first read, so every OTHER launch tried in place again."""
    path, opened = opener
    rel = Release(tmp_path, monkeypatch, path, sleeper)
    _record_failure(rel, "9.9.9")

    for launch in range(3):                      # three launches, same answer
        res = updater.apply_update(rel.url)
        assert res["ok"] is True and res["action"] == "skipped", (launch, res)
        assert "quit" not in res and "did not complete" in res["reason"]
        assert "Settings" in res["message"]
        assert updater._macos_last_helper is None
        assert rel.requested == [], "an install that will not happen must not download"
        assert _failure_record(rel) == "9.9.9", "the record was consumed"
    assert app_version(rel.app) == "1.0.0"
    assert updater.get_progress()["phase"] == "idle"


@mac_only
def test_a_click_may_retry_a_rolled_back_version_and_success_clears_the_record(
        tmp_path, monkeypatch, opener, sleeper):
    path, opened = opener
    rel = Release(tmp_path, monkeypatch, path, sleeper)
    _record_failure(rel, "9.9.9")
    res = updater.apply_update(rel.url, manual=True)
    assert res == {"ok": True, "action": "installer_launched", "quit": True}
    assert _failure_record(rel) == "9.9.9", "cleared before the install succeeded"
    rel.quit_app()
    assert updater._macos_last_helper.wait(timeout=30) == 0
    assert app_version(rel.app) == "9.9.9"
    assert _failure_record(rel) is None, "a successful install must clear the record"


@mac_only
def test_a_failed_download_does_not_consume_the_record(
        tmp_path, monkeypatch, opener, sleeper):
    path, opened = opener
    rel = Release(tmp_path, monkeypatch, path, sleeper)
    _record_failure(rel, "9.9.8")                # older: 9.9.9 supersedes it ...
    rel.chk["asset_sha256"] = "0" * 64           # ... but its download is bad
    res = updater.apply_update(rel.url)
    assert res["ok"] is False and "integrity" in res["error"]
    assert _failure_record(rel) == "9.9.8"
    _record_failure(rel, "9.9.9")                # same story for a manual retry
    res = updater.apply_update(rel.url, manual=True)
    assert res["ok"] is False
    assert _failure_record(rel) == "9.9.9"


@mac_only
def test_a_failure_of_an_older_version_does_not_block_a_newer_one(
        tmp_path, monkeypatch, opener, sleeper):
    path, opened = opener
    rel = Release(tmp_path, monkeypatch, path, sleeper)
    _record_failure(rel, "9.9.8")
    assert updater.apply_update(rel.url).get("quit") is True
    assert _failure_record(rel) is None, "a newer target supersedes the old record"
    rel.quit_app()
    assert updater._macos_last_helper.wait(timeout=30) == 0
    assert app_version(rel.app) == "9.9.9"


@mac_only
def test_a_rollback_is_recorded_until_something_installs(tmp_path, opener):
    """The helper's side of the record: written on failure, kept by a later
    failure, removed by a success."""
    path, opened = opener
    s = Swap(tmp_path, path)
    with open(os.path.join(s.new, "Contents", "Resources", "marker.txt"), "a") as f:
        f.write("corrupt")
    assert s.run(dead_pid()) == 7
    assert s.failed_version() == "9.9.9"
    # A second, good attempt against the same record.
    os.makedirs(os.path.join(s.stage, "payload"))
    s.new = make_app(os.path.join(s.stage, "payload"), "9.9.9")
    with open(s.script, "w") as f:
        f.write(updater._MACOS_SWAP_HELPER)
    assert s.run(dead_pid()) == 0, s.logtext()
    assert s.failed_version() is None


# ------------------------------------------- health: the new app must start --
@mac_only
def test_helper_keeps_the_backup_until_the_new_app_reports_healthy(tmp_path):
    """`open` exiting 0 is not proof of anything: the backup must still exist
    while the helper waits, and go only after the marker appears."""
    path, opened = silent_opener(tmp_path)
    s = Swap(tmp_path, path)
    s.health_wait = 20
    with open(s.health, "w") as f:
        f.write("stale marker from an earlier run\n")
    helper = subprocess.Popen(s.argv(dead_pid()))
    try:
        deadline = time.time() + 15
        while not opened() and time.time() < deadline:
            time.sleep(0.1)
        assert opened() == [s.app]
        time.sleep(1.0)
        assert helper.poll() is None, "helper finished without a health report"
        assert not os.path.exists(s.health), "a stale marker must not count"
        assert app_version(s.backup) == "1.0.0", "backup deleted before the app proved itself"
        assert app_version(s.app) == "9.9.9"
        with open(s.health, "w") as f:           # the new app comes up
            f.write("123\n")
        assert helper.wait(timeout=30) == 0, s.logtext()
    finally:
        if helper.poll() is None:
            helper.kill()
            helper.wait()
    assert app_version(s.app) == "9.9.9"
    assert not os.path.exists(s.stage)
    assert s.failed_version() is None


@mac_only
def test_helper_rolls_back_when_the_new_app_never_reports_healthy(tmp_path):
    path, opened = silent_opener(tmp_path)
    s = Swap(tmp_path, path)
    s.health_wait = 1
    assert s.run(dead_pid()) == 10, s.logtext()
    assert app_version(s.app) == "1.0.0" and marker(s.app) == "1.0.0"
    assert signature_ok(s.app)
    assert opened() == [s.app, s.app], "open the update, then the restored app"
    assert os.listdir(str(s.parent)) == ["AetherHE.app"]
    assert s.failed_version() == "9.9.9"
    log = s.logtext()
    assert "did not report" in log and "previous version restored" in log
    assert "nothing to stop" in log


def _alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _wait_dead(pid, seconds=5):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if not _alive(pid):
            return True
        time.sleep(0.1)
    return False


def _hung_app_opener(tmp_path, write_pid=True, ignore_term=False):
    """An `open` whose FIRST call (the update) starts the bundle's own
    executable - a copy of /bin/sleep, so it runs from INSIDE the bundle, as
    the real app does - and never reports healthy. Later calls (the restored
    app) only record: whether the hung process is still alive at that moment,
    and what the failure record says."""
    pidfile = tmp_path / "launching-9.9.9"
    realpid = tmp_path / "hung.pid"
    run = '"$1/Contents/MacOS/AetherHE" 120 >/dev/null 2>&1'
    if ignore_term:
        run = "(trap '' TERM; exec " + run + ")"       # ignored across exec
    body = (
        f'if [ ! -e "{tmp_path}/started" ]; then : > "{tmp_path}/started"\n'
        f'  {run} &\n'
        f'  echo $! > "{realpid}"\n'
        + (f'  echo $! > "{pidfile}"\n' if write_pid else '')
        + 'else\n'
        f'  if kill -0 "$(cat "{realpid}")" 2>/dev/null; then echo alive; else echo gone; fi '
        f'>> "{tmp_path}/at-reopen"\n'
        'fi')
    path, opened = silent_opener(tmp_path, body)
    return path, opened, pidfile, realpid


def _kill_file_pid(f):
    try:
        os.kill(int(f.read_text()), 9)
    except (OSError, ValueError):
        pass


@mac_only
@needs_ps
def test_helper_stops_the_unhealthy_new_app_when_it_knows_its_pid(tmp_path):
    """The new app got far enough to write its pid, then hung. It is stopped
    before its bundle is moved away, and is GONE before the previous version
    is reopened."""
    path, opened, pidfile, realpid = _hung_app_opener(tmp_path)
    s = Swap(tmp_path, path, new_exe="/bin/sleep")
    s.health_wait = 1
    assert s.pidfile == str(pidfile)
    pidfile.write_text("1\n")                    # stale: must be cleared, never used
    try:
        assert s.run(dead_pid()) == 10, s.logtext()
        hung = int(realpid.read_text())
        assert hung > 1 and int(pidfile.read_text()) == hung
        assert _wait_dead(hung), "the hung new app was left running"
    finally:
        _kill_file_pid(realpid)
    assert f"stopped the updated app (pid {hung})" in s.logtext()
    assert (tmp_path / "at-reopen").read_text().split() == ["gone"], \
        "the previous version was reopened while the update was still running"
    assert app_version(s.app) == "1.0.0" and signature_ok(s.app)


@mac_only
def test_helper_never_signals_a_pid_that_is_not_this_app(tmp_path, sleeper):
    """The pid file names a live process - but one that is NOT running from
    the bundle (a recycled pid, a stale file). It must not be touched."""
    bystander = sleeper()                        # /bin/sleep: not inside $APP
    pidfile = tmp_path / "launching-9.9.9"
    path, opened = silent_opener(tmp_path, f'echo {bystander.pid} > "{pidfile}"')
    s = Swap(tmp_path, path)
    s.health_wait = 1
    assert s.run(dead_pid()) == 10, s.logtext()
    time.sleep(0.5)
    assert bystander.poll() is None, "the helper killed a process that is not ours"
    log = s.logtext()
    assert f"pid {bystander.pid} from the launch file is not a running copy" in log
    assert "stopped the updated app" not in log and "killed the updated app" not in log
    assert app_version(s.app) == "1.0.0" and signature_ok(s.app)


@mac_only
@needs_ps
def test_identity_is_the_executable_path_not_the_name(tmp_path):
    """A process with the right executable NAME but from another bundle (a
    second copy of the app elsewhere) is not ours either."""
    other = make_app(tmp_path / "elsewhere", "1.0.0", exe_src="/bin/sleep")
    stranger = subprocess.Popen([os.path.join(other, "Contents", "MacOS", "AetherHE"), "120"])
    pidfile = tmp_path / "launching-9.9.9"
    path, opened = silent_opener(tmp_path, f'echo {stranger.pid} > "{pidfile}"')
    try:
        s = Swap(tmp_path, path)
        s.health_wait = 1
        assert s.run(dead_pid()) == 10, s.logtext()
        time.sleep(0.5)
        assert stranger.poll() is None, "another copy of the app was killed"
        assert "is not a running copy" in s.logtext()
    finally:
        stranger.kill()
        stranger.wait()


@mac_only
@needs_ps
def test_helper_finds_an_app_that_hung_before_writing_its_pid(tmp_path):
    """No pid file at all: the app hung during import. It still holds the
    single-instance lock, so the restored app would exit on it - the helper
    finds the process by its executable path instead."""
    path, opened, pidfile, realpid = _hung_app_opener(tmp_path, write_pid=False)
    s = Swap(tmp_path, path, new_exe="/bin/sleep")
    s.health_wait = 1
    try:
        assert s.run(dead_pid()) == 10, s.logtext()
        assert not pidfile.exists()
        hung = int(realpid.read_text())
        assert _wait_dead(hung), "the hung new app was left running"
    finally:
        _kill_file_pid(realpid)
    assert f"stopped the updated app (pid {hung})" in s.logtext()
    assert (tmp_path / "at-reopen").read_text().split() == ["gone"]
    assert app_version(s.app) == "1.0.0" and signature_ok(s.app)
    assert opened() == [s.app, s.app]


@mac_only
@needs_ps
def test_helper_waits_for_a_kill_9_to_take_effect_before_reopening(tmp_path):
    """The hung app ignores SIGTERM. kill -9 is asynchronous: the helper must
    see the process gone before it moves bundles and calls `open`, or
    LaunchServices just activates the dying app."""
    path, opened, pidfile, realpid = _hung_app_opener(tmp_path, ignore_term=True)
    s = Swap(tmp_path, path, new_exe="/bin/sleep")
    s.health_wait = 1
    try:
        assert s.run(dead_pid()) == 10, s.logtext()
        hung = int(realpid.read_text())
        assert _wait_dead(hung), "the hung new app survived"
    finally:
        _kill_file_pid(realpid)
    log = s.logtext()
    assert f"killed the updated app (pid {hung})" in log
    assert log.index("killed the updated app") < log.index("the updated app has exited") \
        < log.index("previous version restored"), "restored without seeing it gone"
    assert (tmp_path / "at-reopen").read_text().split() == ["gone"]
    assert app_version(s.app) == "1.0.0" and signature_ok(s.app)


def _fake_ps(tmp_path, app, realpid):
    """Stands in for /bin/ps (which a sandbox may refuse to run). Listing
    every process works and reports the hung app at its real bundle path;
    asking about ONE pid fails - ps has stopped answering."""
    script = tmp_path / "fake-ps.sh"
    script.write_text(
        '#!/bin/sh\n'
        'case "$1" in\n'
        f'  -axo) echo "$(cat "{realpid}") {app}/Contents/MacOS/AetherHE" ;;\n'
        '  *) exit 1 ;;\n'
        'esac\n')
    script.chmod(0o755)
    return str(script)


@mac_only
def test_helper_moves_nothing_when_the_updated_app_cannot_be_stopped(tmp_path):
    """The update never reports healthy, ignores SIGTERM, and by the time
    kill -9 is due the helper can no longer confirm the pid is ours - so it
    is still running. Moving its bundle away and reopening the previous
    version would leave two copies fighting; the helper must stop instead,
    with the previous version untouched in the staging folder."""
    path, opened, pidfile, realpid = _hung_app_opener(
        tmp_path, write_pid=False, ignore_term=True)
    s = Swap(tmp_path, path, new_exe="/bin/sleep")
    s.health_wait = 1
    helper = updater._MACOS_SWAP_HELPER
    assert helper.count("/bin/ps") == 2
    with open(s.script, "w") as f:
        f.write(helper.replace("/bin/ps", _fake_ps(tmp_path, s.app, realpid)))
    try:
        rc = s.run(dead_pid())
        hung = int(realpid.read_text())
        assert rc == 12, s.logtext()
        assert _alive(hung), "precondition: the updated app is still running"
    finally:
        _kill_file_pid(realpid)
    log = s.logtext()
    assert f"is still running after kill -9 (pids: {hung})" in log
    assert "ROLLBACK NOT ATTEMPTED" in log and "exit 12" in log
    assert "previous version restored" not in log
    assert app_version(s.app) == "9.9.9" and signature_ok(s.app), \
        "the running update's bundle must not be moved"
    assert app_version(s.backup) == "1.0.0" and signature_ok(s.backup), \
        "the previous version must be left intact in the staging folder"
    assert not os.path.exists(os.path.join(s.stage, "rejected.app"))
    assert s.failed_version() == "9.9.9"
    assert opened() == [s.app], "nothing may be reopened"


@mac_only
def test_helper_ignores_a_pid_file_that_is_not_a_pid(tmp_path):
    pidfile = tmp_path / "launching-9.9.9"
    path, opened = silent_opener(tmp_path, f'echo "-1; rm -rf /" > "{pidfile}"')
    s = Swap(tmp_path, path)
    s.health_wait = 1
    assert s.run(dead_pid()) == 10, s.logtext()
    assert "nothing to stop" in s.logtext()
    assert app_version(s.app) == "1.0.0"


# --------------------------------- the record is written before the reopen --
def _recording_opener(tmp_path, failmark):
    """An `open` that never reports healthy and notes, on every call, what the
    failure record says at that moment."""
    seen = tmp_path / "record-at-open"
    path, opened = silent_opener(
        tmp_path,
        f'if [ -f "{failmark}" ]; then cat "{failmark}"; else echo none; fi >> "{seen}"')
    return path, opened, (lambda: seen.read_text().split() if seen.exists() else [])


@mac_only
def test_failure_is_on_record_before_the_restored_app_is_reopened(tmp_path):
    """The restored app checks for updates as it starts. If the record were
    written after `open`, it could find none and retry the same update."""
    path, opened, seen = _recording_opener(tmp_path, tmp_path / "failed-version")
    s = Swap(tmp_path, path)
    s.health_wait = 1
    assert s.run(dead_pid()) == 10, s.logtext()
    assert opened() == [s.app, s.app]
    assert seen() == ["none", "9.9.9"], \
        "open #1 is the update (no record yet); open #2 must already see the record"


@mac_only
def test_failure_is_on_record_before_reopening_after_a_failed_verification(tmp_path):
    path, opened, seen = _recording_opener(tmp_path, tmp_path / "failed-version")
    s = Swap(tmp_path, path)
    with open(os.path.join(s.new, "Contents", "Resources", "marker.txt"), "a") as f:
        f.write("corrupt")
    assert s.run(dead_pid()) == 7, s.logtext()
    assert opened() == [s.app] and seen() == ["9.9.9"]


# --------------------------------------------- "nothing was changed" exits --
@mac_only
def test_nothing_changed_exits_keep_an_existing_record_untouched(tmp_path, opener, sleeper):
    """They neither write a record nor clear one that an earlier, real
    rollback left."""
    path, opened = opener
    s = Swap(tmp_path, path)
    with open(s.failmark, "w") as f:
        f.write("9.9.8\n")
    assert s.run(sleeper().pid, timeout=1) == 3
    assert s.failed_version() == "9.9.8"


@mac_only
def test_a_slow_quit_does_not_block_or_poison_the_next_attempt(
        tmp_path, monkeypatch, opener, sleeper):
    """Exit 3: the app did not quit in time, the helper gave up and nothing
    was changed. The app is STILL RUNNING with its in-progress flag set, and
    the helper cannot reach into it - a later click must still work, and no
    failure may be on record (auto-update may try again too)."""
    path, opened = opener
    rel = Release(tmp_path, monkeypatch, path, sleeper)
    monkeypatch.setattr(updater, "_MACOS_EXIT_TIMEOUT", 1)
    assert updater.apply_update(rel.url).get("quit") is True
    first = updater._macos_last_helper
    # While the helper is still waiting, a second call is refused ...
    assert updater.apply_update(rel.url, manual=True) == \
        {"ok": False, "error": "update already in progress"}
    assert first.wait(timeout=30) == 3            # ... the app never quit
    assert updater._macos_swap_started is True, "precondition: the flag is stale"
    assert _failure_record(rel) is None, "nothing was changed: not a failed install"
    assert app_version(rel.app) == "1.0.0" and leftovers(rel.parent) == []

    monkeypatch.setattr(updater, "_MACOS_EXIT_TIMEOUT", 60)
    res = updater.apply_update(rel.url, manual=True)
    assert res == {"ok": True, "action": "installer_launched", "quit": True}, res
    assert updater._macos_last_helper is not first
    rel.quit_app()
    assert updater._macos_last_helper.wait(timeout=30) == 0
    assert app_version(rel.app) == "9.9.9"


@mac_only
def test_a_slow_quit_lets_the_next_launch_auto_update_again(
        tmp_path, monkeypatch, opener, sleeper):
    path, opened = opener
    rel = Release(tmp_path, monkeypatch, path, sleeper)
    monkeypatch.setattr(updater, "_MACOS_EXIT_TIMEOUT", 1)
    assert updater.apply_update(rel.url).get("quit") is True
    assert updater._macos_last_helper.wait(timeout=30) == 3
    monkeypatch.setattr(updater, "_MACOS_EXIT_TIMEOUT", 60)
    res = updater.apply_update(rel.url)                    # NOT manual
    assert res.get("quit") is True and res.get("action") != "skipped", res
    rel.quit_app()
    assert updater._macos_last_helper.wait(timeout=30) == 0


def test_swap_pending_is_true_only_while_something_is_in_hand(monkeypatch):
    class Helper:
        def __init__(self, rc):
            self.returncode = rc

        def poll(self):
            return self.returncode

    assert updater._macos_swap_pending() is False
    # Staging: flag set, no helper yet.
    monkeypatch.setattr(updater, "_macos_swap_started", True)
    assert updater._macos_swap_pending() is True
    # Helper running.
    monkeypatch.setattr(updater, "_macos_last_helper", Helper(None))
    assert updater._macos_swap_pending() is True
    # Helper gone, we are still here: stale.
    monkeypatch.setattr(updater, "_macos_last_helper", Helper(3))
    assert updater._macos_swap_pending() is False
    assert updater._macos_swap_started is False


@mac_only
def test_the_skipped_launch_result_offers_a_manual_retry_that_works(
        tmp_path, monkeypatch, opener, sleeper):
    """What the launch gate does: the automatic call is skipped and says a
    manual retry is possible; the SAME session then retries with manual=True
    and the install goes ahead."""
    path, opened = opener
    rel = Release(tmp_path, monkeypatch, path, sleeper)
    _record_failure(rel, "9.9.9")
    auto = updater.apply_update(rel.url, None, None, None, False)
    assert auto["ok"] is True and auto["action"] == "skipped" and auto["manual"] is True
    assert "quit" not in auto and "restart" not in auto and auto["message"]
    retry = updater.apply_update(rel.url, None, None, None, True)
    assert retry == {"ok": True, "action": "installer_launched", "quit": True}
    rel.quit_app()
    assert updater._macos_last_helper.wait(timeout=30) == 0
    assert app_version(rel.app) == "9.9.9" and _failure_record(rel) is None


def test_the_launch_gate_wires_a_try_again_button_to_a_manual_apply():
    src = os.path.join(ROOT, "ui", "runtime_src")
    app = open(os.path.join(src, "src", "app.jsx"), encoding="utf-8").read()
    # The skipped result turns the retry on ...
    assert 'retry: r.action === "skipped" && !!r.manual' in app
    # ... the gate shows a button for it ...
    assert "{gate.retry && onRetry && (" in app and ">Try again</button>" in app
    assert "onRetry={retryUpdate}" in app
    # ... and the button runs the flow with manual=true, which reaches the API.
    assert "runUpdateFlow(api, true, true)" in app
    assert "chk.asset_size, chk.asset_sha256, !!manual);" in app
    # The shipped (compiled) UI carries it too.
    built = open(os.path.join(src, "build", "app.js"), encoding="utf-8").read()
    assert "Try again" in built and "retryUpdate" in built and "!!manual" in built
    shipped = open(os.path.join(ROOT, "ui", "index_runtime.html"), encoding="utf-8").read()
    assert "retryUpdate" in shipped and "!!manual" in shipped


# ------------------------------------------------------------ health wait --
def test_health_wait_is_ninety_seconds(tmp_path, monkeypatch):
    """A healthy start measured 4 s; 45 s left too little room for a slow but
    working one. Both the value passed to the helper and the helper's own
    default are 90."""
    assert updater._MACOS_HEALTH_TIMEOUT == 90
    assert 'HEALTHWAIT="${12:-90}"' in updater._MACOS_SWAP_HELPER
    seen = {}

    class P:
        pid = 4242

        def __init__(self, argv, **kw):
            seen["argv"] = argv

        def poll(self):
            return 0

    monkeypatch.setattr(updater.subprocess, "Popen", P)
    stage = tmp_path / "stage"
    stage.mkdir()
    updater._macos_launch_swap("/Applications/AetherHE.app", str(stage / "new.app"),
                               str(stage), "9.9.9")
    argv = seen["argv"]
    assert argv[:2] == ["/bin/sh", str(stage / "swap.sh")]
    assert argv[2 + 11] == "90", "argument 12 is the health wait"
    assert argv[2 + 10].endswith("healthy-9.9.9") and argv[2 + 12].endswith("launching-9.9.9")


@mac_only
def test_helper_defaults_to_a_long_health_wait_when_none_is_given(tmp_path):
    """Run for real with the argument empty: after 3 s (well past the old
    test value) the helper must still be waiting, not rolling back."""
    path, opened = silent_opener(tmp_path)
    s = Swap(tmp_path, path)
    s.health_wait = ""
    helper = subprocess.Popen(s.argv(dead_pid()))
    try:
        deadline = time.time() + 15
        while not opened() and time.time() < deadline:
            time.sleep(0.1)
        time.sleep(3)
        assert helper.poll() is None and app_version(s.app) == "9.9.9"
        with open(s.health, "w") as f:
            f.write("1\n")
        assert helper.wait(timeout=30) == 0, s.logtext()
    finally:
        if helper.poll() is None:
            helper.kill()
            helper.wait()


@mac_only
def test_end_to_end_rolls_back_an_update_that_never_comes_up(
        tmp_path, monkeypatch, sleeper):
    path, opened = silent_opener(tmp_path)
    rel = Release(tmp_path, monkeypatch, path, sleeper)
    assert updater.apply_update(rel.url).get("quit") is True
    rel.quit_app()
    assert updater._macos_last_helper.wait(timeout=40) == 10
    assert app_version(rel.app) == "1.0.0" and signature_ok(rel.app)
    assert os.listdir(str(rel.parent)) == ["AetherHE.app"]
    assert _failure_record(rel) == "9.9.9"
    # ... and the next launch's auto-update leaves it alone.
    monkeypatch.setattr(updater, "_macos_swap_started", False)
    assert updater.apply_update(rel.url)["action"] == "skipped"


def _frozen_mac(monkeypatch, selftest=False):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    if selftest:
        monkeypatch.setenv("AETHER_SELFTEST", "1")
    else:
        monkeypatch.delenv("AETHER_SELFTEST", raising=False)


def test_app_writes_its_pid_then_the_health_marker(monkeypatch):
    _frozen_mac(monkeypatch)
    cache = os.path.expanduser("~/Library/Caches/AetherHE/updates")
    assert updater.macos_note_launch() is True
    pidfile = updater._macos_launch_pidfile(version.__version__)
    assert os.path.dirname(pidfile) == cache
    assert open(pidfile).read().strip() == str(os.getpid())
    stale = os.path.join(cache, "healthy-0.0.1")
    open(stale, "w").close()
    assert updater.macos_note_healthy() is True
    want = os.path.join(cache, "healthy-" + version.__version__)
    assert updater._macos_health_marker("v" + version.__version__) == want
    assert sorted(os.listdir(cache)) == [os.path.basename(want)], \
        "other versions' markers and the pid file are dropped once healthy"


@pytest.mark.parametrize("case", ["source", "selftest", "not-mac"])
def test_no_health_marker_outside_an_installed_mac_build(monkeypatch, case):
    if case == "source":
        monkeypatch.setattr(sys, "platform", "darwin")
        monkeypatch.delattr(sys, "frozen", raising=False)
    elif case == "selftest":
        _frozen_mac(monkeypatch, selftest=True)
    else:
        _frozen_mac(monkeypatch)
        monkeypatch.setattr(sys, "platform", "linux")
    assert updater.macos_health_wanted() is False
    assert updater.macos_note_launch() is False
    assert updater.macos_note_healthy() is False
    assert not os.path.exists(os.path.expanduser("~/Library/Caches/AetherHE"))


def test_health_marker_path_cannot_escape_the_cache():
    p = updater._macos_health_marker("../../etc/x y")
    assert os.path.dirname(p) == os.path.expanduser("~/Library/Caches/AetherHE/updates")
    assert "/" not in os.path.basename(p) and " " not in os.path.basename(p)


# ------------------------------------------------ restore must never nest ----
@mac_only
@not_root
def test_restore_never_moves_the_backup_inside_a_bundle_it_could_not_remove(tmp_path):
    """The update is in place, will not open, and cannot be moved away or
    removed (the folder turned read-only). `mv backup app` would then put the
    old app INSIDE the bad one. The helper must stop and leave the backup."""
    parent = tmp_path / "Applications"
    path, opened = silent_opener(tmp_path, f'chmod 555 "{parent}"; exit 1')
    s = Swap(tmp_path, path)
    try:
        rc = s.run(dead_pid())
    finally:
        os.chmod(str(parent), 0o755)
    assert rc == 11, s.logtext()
    assert os.path.isdir(s.app), "precondition: something is still at the app path"
    assert not os.path.exists(os.path.join(s.app, "previous.app")), "NESTED"
    assert not os.path.exists(os.path.join(s.app, "Contents", "Info.plist")) \
        or app_version(s.app) == "9.9.9"
    assert app_version(s.backup) == "1.0.0" and signature_ok(s.backup), \
        "the previous version must be left intact where it is"
    assert "ROLLBACK BLOCKED" in s.logtext()
    assert s.failed_version() == "9.9.9"
    assert len(opened()) == 1, "nothing may be relaunched from a half-restored state"


# ------------------------------------------------------- strictly newer ----
@pytest.mark.parametrize("latest", ["1.0.0", "0.9.0", "v1.0.0", "", None])
@pytest.mark.parametrize("kind", ["windows", "macos", "flatpak", "linux"])
def test_apply_refuses_anything_that_is_not_newer(monkeypatch, kind, latest):
    """Same version = reinstall, older = downgrade. Neither is an update, on
    any platform, whatever URL the caller holds."""
    url = ("https://github.com/%s/releases/download/v1.0.0/AetherHE-Setup.exe"
           % version.GITHUB_REPO)
    chk = {"ok": True, "update": True, "newer": True,      # flags lie; versions do not
           "latest": latest, "asset_url": url, "asset_name": "AetherHE-Setup.exe",
           "asset_size": 3, "asset_sha256": hashlib.sha256(b"abc").hexdigest()}
    monkeypatch.setattr(version, "__version__", "1.0.0")
    monkeypatch.setattr(updater, "platform_kind", lambda: kind)
    monkeypatch.setattr(updater, "check_for_update", lambda *a, **k: dict(chk))

    def no_network(*a, **k):
        raise AssertionError("downloaded something that is not an update")
    monkeypatch.setattr(updater.urllib.request, "urlopen", no_network)
    monkeypatch.setattr(updater.subprocess, "Popen", no_network)
    monkeypatch.setattr(updater.subprocess, "run", no_network)

    res = updater.apply_update(url, manual=True)
    assert res["ok"] is False and "no newer version" in res["error"]
    assert "quit" not in res
    assert updater.get_progress()["phase"] == "idle"


def test_apply_accepts_a_strictly_newer_release(tmp_path, monkeypatch):
    url, data, revealed = _fallback_release(tmp_path, monkeypatch)
    monkeypatch.setattr(version, "__version__", "9.9.8")
    assert updater.apply_update(url)["ok"] is True


# ------------------------------------------------------------ one at a time --
def test_concurrent_apply_is_refused_while_one_is_running(tmp_path, monkeypatch):
    import threading
    url, data, revealed = _fallback_release(tmp_path, monkeypatch)
    entered, go = threading.Event(), threading.Event()

    def slow(req, timeout=None):
        entered.set()
        assert go.wait(10)
        return _FakeResp(data)
    monkeypatch.setattr(updater.urllib.request, "urlopen", slow)

    out = {}
    t = threading.Thread(target=lambda: out.update(first=updater.apply_update(url)))
    t.start()
    try:
        assert entered.wait(10)
        second = updater.apply_update(url)
        assert second == {"ok": False, "error": "update already in progress"}
    finally:
        go.set()
        t.join(10)
    assert out["first"]["ok"] is True and out["first"]["action"] == "downloaded"
    assert len(revealed) == 1, "the refused call must not have downloaded too"
    # ... and the lock is released for the next attempt.
    monkeypatch.setattr(updater.urllib.request, "urlopen",
                        lambda req, timeout=None: _FakeResp(data))
    assert updater.apply_update(url)["ok"] is True


def _windows_release(tmp_path, monkeypatch):
    """A Windows release whose Setup.exe is 'spawned' into a recording fake."""
    data = b"MZ-not-really-an-installer" * 50
    url = ("https://github.com/%s/releases/download/v9.9.9/AetherHE-Setup.exe"
           % version.GITHUB_REPO)
    chk = {"ok": True, "latest": "9.9.9", "asset_url": url,
           "asset_name": "AetherHE-Setup.exe", "asset_size": len(data),
           "asset_sha256": hashlib.sha256(data).hexdigest()}
    downloads, spawned = [], []

    def urlopen(req, timeout=None):
        downloads.append(req.full_url)
        return _FakeResp(data)

    class Installer:
        def __init__(self, argv, **kw):
            self.argv, self.returncode = argv, None
            spawned.append(self)

        def poll(self):
            return self.returncode

    monkeypatch.setattr(updater, "platform_kind", lambda: "windows")
    monkeypatch.setattr(updater, "check_for_update", lambda *a, **k: dict(chk))
    monkeypatch.setattr(updater.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(updater.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(updater.subprocess, "Popen", Installer)
    return url, downloads, spawned


def test_windows_second_apply_before_quit_does_not_start_a_second_installer(
        tmp_path, monkeypatch):
    """apply_update returns - and releases its lock - once Setup.exe is
    spawned, about half a second before the app quits. A second call in that
    gap used to download again and run a second installer over the first."""
    url, downloads, spawned = _windows_release(tmp_path, monkeypatch)
    first = updater.apply_update(url)
    assert first == {"ok": True, "action": "installer_launched", "quit": True}
    assert len(spawned) == 1 and spawned[0].argv[1:] == ["/SILENT", "/NOCANCEL"]

    for manual in (False, True):
        again = updater.apply_update(url, manual=manual)
        assert again == {"ok": False, "error": "update already in progress"}
    assert len(spawned) == 1, "a second installer was started"
    assert len(downloads) == 1, "the refused call must not download either"


def test_windows_installer_that_exited_without_replacing_us_allows_a_retry(
        tmp_path, monkeypatch):
    """Same staleness rule as the macOS helper: an installer that has exited
    while this process is still alive did not update anything."""
    url, downloads, spawned = _windows_release(tmp_path, monkeypatch)
    assert updater.apply_update(url)["quit"] is True
    spawned[0].returncode = 1
    assert updater.apply_update(url)["quit"] is True
    assert len(spawned) == 2


def test_lock_is_released_when_apply_fails_or_raises(tmp_path, monkeypatch):
    url, data, revealed = _fallback_release(tmp_path, monkeypatch)

    def boom(*a, **k):
        raise RuntimeError("network down")
    monkeypatch.setattr(updater.urllib.request, "urlopen", boom)
    assert "download failed" in updater.apply_update(url)["error"]
    monkeypatch.setattr(updater, "platform_kind", boom)
    with pytest.raises(RuntimeError):
        updater.apply_update(url)
    assert updater._apply_lock.acquire(blocking=False), "lock leaked"
    updater._apply_lock.release()


@mac_only
def test_in_progress_flag_is_cleared_when_staging_or_verification_fails(
        tmp_path, monkeypatch, opener, sleeper):
    """Set before staging; a rejected bundle must not leave every later
    attempt answering 'already in progress' until the app restarts."""
    path, opened = opener
    rel = Release(tmp_path, monkeypatch, path, sleeper, zip_ver="9.9.8", tag="9.9.9")
    seen = []
    real_stage = updater._macos_stage

    def stage(*a, **k):
        seen.append(updater._macos_swap_started)
        return real_stage(*a, **k)
    monkeypatch.setattr(updater, "_macos_stage", stage)
    assert updater.apply_update(rel.url)["ok"] is False          # version mismatch
    assert seen == [True], "the flag must be up BEFORE staging starts"
    assert updater._macos_swap_started is False

    def broken(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(updater, "_macos_stage", broken)
    res = updater.apply_update(rel.url)
    assert res["ok"] is False and "disk full" in res["error"]
    assert updater._macos_swap_started is False


# ----------------------------------- fallback: download and reveal instead --
def _fallback_release(tmp_path, monkeypatch):
    data = b"PK-not-really-a-zip" * 100
    url = ("https://github.com/%s/releases/download/v9.9.9/"
           "AetherHE-macos-arm64.zip" % version.GITHUB_REPO)
    chk = {"ok": True, "latest": "9.9.9", "url": "https://example.invalid/rel",
           "asset_url": url,
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


def test_only_the_click_surfaces_ask_for_a_manual_retry():
    """`manual` is what lets a failed in-place install be retried. The two
    Update buttons pass it; the launch-time flow must not."""
    src = os.path.join(ROOT, "ui", "runtime_src")
    read = lambda *rel: open(os.path.join(src, *rel), encoding="utf-8").read()
    assert "upd.info.asset_name, null, null, true)" in read("src", "sections.jsx")
    assert "info.asset_size, info.asset_sha256, true)" in read("workspaces", "settings.jsx")
    app = read("src", "app.jsx")
    # One call site; whether it is a click is decided by its caller ...
    assert "chk.asset_size, chk.asset_sha256, !!manual);" in app
    assert app.count("api.apply_update(") == 1
    # ... and only the gate's Try again button says it is. The two launch-time
    # entries (saved preference, first-run "yes") never do.
    assert "runUpdateFlow(api, false);" in app
    assert "if (yes) await runUpdateFlow(api, true);" in app
    assert app.count("runUpdateFlow(") == 3          # exactly three callers
    assert app.count("runUpdateFlow(api, true, true)") == 1
    api = open(os.path.join(ROOT, "app_web.py"), encoding="utf-8").read()
    assert "manual=bool(manual))" in api


# ------------------------------------------------------ the helper's text ----
def test_helper_script_is_posix_sh_and_self_contained():
    s = updater._MACOS_SWAP_HELPER
    assert s.startswith("#!/bin/sh\n")
    # Nothing from the bundle being replaced, and no interpreter that may be
    # missing on a stock Mac.
    for forbidden in ("python", "bash", "osascript"):
        assert forbidden not in s, f"helper must not depend on {forbidden}"
    # The bundle's executable folder is named exactly once - to COMPARE a
    # process's executable path against. It is never run.
    assert s.count("Contents/MacOS") == 1
    assert 'EXEDIR="$APP/Contents/MacOS/"' in s
    for line in s.splitlines():
        if "EXEDIR" in line and "EXEDIR=" not in line and not line.lstrip().startswith("#"):
            assert line.strip() == '"$EXEDIR"*) return 0 ;;' \
                or line.strip() == '"$EXEDIR"*) echo "$p" ;;', line
    # Every signal is preceded by the identity check: the only pids ever put
    # in $TARGETS come from our_pids or passed is_ours.
    assert "is_ours \"$NEWPID\"" in s and "kill \"$NEWPID\"" not in s
    if os.path.exists("/bin/sh"):
        assert subprocess.run(["/bin/sh", "-n", "-c", s]).returncode == 0
