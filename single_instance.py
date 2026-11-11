"""One Aether at a time (Windows and macOS).

Why: WebView2 refuses to open a user-data folder that another WebView2
process already holds with different environment options — HRESULT
0x8007139F "The group or resource is not in the correct state". With the app
resident in the tray, a second launch (Start menu, autostart, `run.bat`) hit
exactly that and died with a blank window. Now the second launch pokes the
running instance, which shows its window, and exits.

Mechanics: a named mutex says "someone is running"; a named auto-reset event
is the poke. Both live in the per-session ``Local`` namespace, so nothing
leaks across users.

macOS: an exclusive `flock` on `<user data dir>/aether.lock`, held for the life
of the process (the kernel drops it when the process dies, so a crash never
leaves a stale lock). Without it the LaunchAgent autostart (RunAtLoad +
`launchctl bootstrap` starts the agent at once) put a second Aether next to the
running one: its `open_path` failed with a misleading permission error, and the
updater's swap helper - which waits for ONE pid - could replace the bundle
under the other. A second launch activates the running app and exits.

Linux: everything is a no-op and `acquire()` always says we are the first
instance.
"""
import logging
import os
import sys
import threading

log = logging.getLogger("aether.instance")

MUTEX_NAME = "Local\\AetherHE.Instance"
EVENT_NAME = "Local\\AetherHE.Show"
# Set by the running instance once its window is actually up again. Lets a
# second launch tell "poked and shown" from "poked a hung process": SetEvent
# succeeds either way, so without it a stuck background instance made every
# later launch exit silently ("it isn't booting at all").
ACK_NAME = "Local\\AetherHE.Shown"
ACK_TIMEOUT_MS = 4000

# poke_existing() results
SHOWN = "shown"               # running instance raised its window
UNRESPONSIVE = "unresponsive"  # poke delivered, window never came up (hung)
UNREACHABLE = "unreachable"    # couldn't open its event (elevated / booting)
ERROR_ALREADY_EXISTS = 183
WAIT_OBJECT_0 = 0
WAIT_FAILED = 0xFFFFFFFF
INFINITE = 0xFFFFFFFF


def _declare(k):
    """Pin the Win32 signatures we use. ctypes defaults every argument and
    return value to a 32-bit C int; a HANDLE is pointer-sized, so on 64-bit
    Windows an undeclared CreateMutexW/CreateEventW result is truncated and
    the value handed back to CloseHandle/WaitForSingleObject/SetEvent is a
    sign-extended int, not the handle — WaitForSingleObject then returns
    WAIT_FAILED immediately and the listener loop spins. Declaring
    restype/argtypes makes the round trip exact."""
    from ctypes import wintypes
    k.CreateMutexW.restype = wintypes.HANDLE
    k.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
    k.CreateEventW.restype = wintypes.HANDLE
    k.CreateEventW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL,
                               wintypes.LPCWSTR)
    k.OpenEventW.restype = wintypes.HANDLE
    k.OpenEventW.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR)
    k.SetEvent.restype = wintypes.BOOL
    k.SetEvent.argtypes = (wintypes.HANDLE,)
    k.WaitForSingleObject.restype = wintypes.DWORD
    k.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    k.CloseHandle.restype = wintypes.BOOL
    k.CloseHandle.argtypes = (wintypes.HANDLE,)
    return k


def _k32():
    import ctypes
    return _declare(ctypes.WinDLL("kernel32", use_last_error=True))


LOCK_NAME = "aether.lock"


def _is_mac():
    return sys.platform == "darwin"


def _default_lock_path():
    import boot
    return os.path.join(boot.user_data_dir(), LOCK_NAME)


class SingleInstance:
    def __init__(self, lock_path=None):
        self._lock_path = lock_path     # macOS only; None = user data dir
        self._lock_fd = None
        self._mutex = None
        self._event = None
        self._ack = None
        self._stop = threading.Event()
        self._thread = None

    def acquire(self):
        """True if this process is the first instance (and now owns the
        mutex); False if another Aether is already running."""
        if _is_mac():
            return self._acquire_flock()
        if not sys.platform.startswith("win"):
            return True
        try:
            import ctypes
            k = _k32()
            self._mutex = k.CreateMutexW(None, False, MUTEX_NAME)
            if not self._mutex:
                return True                 # can't tell → don't block launch
            if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
                k.CloseHandle(self._mutex)
                self._mutex = None
                return False
            return True
        except Exception as e:
            log.warning("single-instance check failed, continuing: %s", e)
            return True

    def _acquire_flock(self):
        """macOS: take the exclusive lock, or learn that someone holds it.
        Any failure other than "held by another process" lets the launch go
        ahead - a broken lock file must never keep the app from starting."""
        if self._lock_fd is not None:
            return True
        fd = None
        try:
            import fcntl
            path = self._lock_path or _default_lock_path()
            # Python opens fds close-on-exec, so no child (the update helper,
            # `open`, launchctl) inherits the lock and outlives us holding it.
            fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                os.close(fd)
                return False
            self._lock_fd = fd
            try:                        # the pid is for poke_existing()
                os.ftruncate(fd, 0)
                os.write(fd, str(os.getpid()).encode())
            except OSError:
                pass
            return True
        except Exception as e:
            log.warning("single-instance check failed, continuing: %s", e)
            if fd is not None and self._lock_fd is None:
                try:
                    os.close(fd)
                except OSError:
                    pass
            return True

    def holder_pid(self):
        """macOS: pid the lock file names (the running instance), or None."""
        try:
            with open(self._lock_path or _default_lock_path(), "r") as f:
                pid = int(f.read().strip() or 0)
            return pid if pid > 0 else None
        except (OSError, ValueError):
            return None

    def _poke_mac(self):
        """Bring the running instance's window to the front. Best effort:
        AppKit comes with pywebview on macOS; without it the second launch
        still exits, just without raising the first."""
        pid = self.holder_pid()
        if not pid or pid == os.getpid():
            return UNREACHABLE
        try:
            from AppKit import NSRunningApplication
            app = NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
            if app is None:
                return UNREACHABLE
            NSApplicationActivateIgnoringOtherApps = 1 << 1
            ok = app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
            return SHOWN if ok else UNREACHABLE
        except Exception as e:
            log.info("poke: could not activate pid %s (%s)", pid, e)
            return UNREACHABLE

    def poke_existing(self, ack_timeout_ms=ACK_TIMEOUT_MS):
        """Ask the running instance to show its window and wait for it to say
        it did. Returns SHOWN, UNRESPONSIVE or UNREACHABLE (False on Linux;
        macOS activates the running app and never reports UNRESPONSIVE)."""
        if _is_mac():
            return self._poke_mac()
        if not sys.platform.startswith("win"):
            return False
        try:
            import ctypes
            k = _k32()
            EVENT_MODIFY_STATE, SYNCHRONIZE = 0x0002, 0x00100000
            h = k.OpenEventW(EVENT_MODIFY_STATE, False, EVENT_NAME)
            if not h:
                # ERROR_ACCESS_DENIED (5): the other instance runs at a
                # different integrity level (typically elevated — e.g. launched
                # by the installer). ERROR_FILE_NOT_FOUND (2): it exists but
                # has not armed its listener yet (still booting).
                log.warning("poke: OpenEventW failed, error %s", ctypes.get_last_error())
                return UNREACHABLE
            ack = k.OpenEventW(SYNCHRONIZE, False, ACK_NAME)
            ok = bool(k.SetEvent(h))
            k.CloseHandle(h)
            if not ok:
                if ack:
                    k.CloseHandle(ack)
                return UNREACHABLE
            if not ack:
                # Older build without the ack event: trust the poke.
                return SHOWN
            rc = k.WaitForSingleObject(ack, ack_timeout_ms)
            k.CloseHandle(ack)
            if rc == WAIT_OBJECT_0:
                return SHOWN
            log.warning("poke: running instance did not show its window "
                        "within %d ms (rc=%s)", ack_timeout_ms, rc)
            return UNRESPONSIVE
        except Exception as e:
            log.warning("poke failed: %s", e)
            return UNREACHABLE

    @staticmethod
    def notify_unresponsive(app_name="Aether HE"):
        """The running instance took the poke but never showed its window:
        it is hung (or its window/WebView2 died and left the process
        behind). Say so — otherwise the new launch just vanishes."""
        return _message_box(
            app_name,
            f"{app_name} is already running in the background but is not "
            "responding, so its window could not be opened.\n\n"
            "Open Task Manager, end every AetherHE.exe process, then start "
            f"{app_name} again.")

    @staticmethod
    def notify_unreachable(app_name="Aether HE"):
        """Second launch found a running instance it cannot reach: say so
        instead of exiting silently (the symptom was 'the app does not
        start'). Windows-only message box; returns True if shown."""
        return _message_box(
            app_name,
            f"{app_name} is already running but could not be reached.\n\n"
            "It is probably running as administrator (for example, launched "
            "by the installer). Exit it from the tray icon, or end "
            "AetherHE.exe in Task Manager, then start it again.")

    def listen(self, on_show):
        """Start a daemon thread that calls `on_show()` each time another
        launch pokes us. Only the owning instance calls this."""
        if not sys.platform.startswith("win"):
            return
        try:
            k = _k32()
            # auto-reset (bManualReset=False): one SetEvent → one wake.
            self._event = k.CreateEventW(None, False, False, EVENT_NAME)
            if not self._event:
                return
            # auto-reset too: one successful show → one waiting launcher.
            self._ack = k.CreateEventW(None, False, False, ACK_NAME)
        except Exception as e:
            log.warning("show-event unavailable: %s", e)
            return

        def loop():
            k = _k32()
            while not self._stop.is_set():
                # 500 ms slices so stop() is honoured without a poke.
                rc = k.WaitForSingleObject(self._event, 500)
                if rc == WAIT_OBJECT_0:
                    if self._stop.is_set():
                        break
                    try:
                        shown = on_show() is not False
                    except Exception as e:
                        log.warning("on_show failed: %s", e)
                        shown = False
                    if shown and self._ack:
                        k.SetEvent(self._ack)
                elif rc == WAIT_FAILED:
                    # Bad/closed handle: WaitForSingleObject returns at once,
                    # so looping would burn a core. Give up on pokes.
                    log.warning("show-event wait failed; second launches will "
                                "not raise the window")
                    break

        self._thread = threading.Thread(target=loop, name="aether-instance-listen", daemon=True)
        self._thread.start()

    def release(self):
        self._stop.set()
        if self._lock_fd is not None:
            try:
                os.close(self._lock_fd)     # closing the fd drops the flock
            except OSError:
                pass
            self._lock_fd = None
        if not sys.platform.startswith("win"):
            return
        try:
            k = _k32()
            for h in (self._event, self._ack, self._mutex):
                if h:
                    k.CloseHandle(h)
        except Exception:
            pass
        self._event = self._ack = self._mutex = None


def _message_box(title, text):
    """Windows-only warning box; True if shown."""
    if not sys.platform.startswith("win"):
        return False
    try:
        import ctypes
        MB_ICONWARNING, MB_OK = 0x30, 0x0
        ctypes.WinDLL("user32", use_last_error=True).MessageBoxW(
            None, text, title, MB_ICONWARNING | MB_OK)
        return True
    except Exception as e:
        log.warning("notify failed: %s", e)
        return False
