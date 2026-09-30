"""One Aether at a time (Windows).

Why: WebView2 refuses to open a user-data folder that another WebView2
process already holds with different environment options — HRESULT
0x8007139F "The group or resource is not in the correct state". With the app
resident in the tray, a second launch (Start menu, autostart, `run.bat`) hit
exactly that and died with a blank window. Now the second launch pokes the
running instance, which shows its window, and exits.

Mechanics: a named mutex says "someone is running"; a named auto-reset event
is the poke. Both live in the per-session ``Local`` namespace, so nothing
leaks across users. Non-Windows: everything is a no-op and `acquire()`
always says we are the first instance.
"""
import logging
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


class SingleInstance:
    def __init__(self):
        self._mutex = None
        self._event = None
        self._ack = None
        self._stop = threading.Event()
        self._thread = None

    def acquire(self):
        """True if this process is the first instance (and now owns the
        mutex); False if another Aether is already running."""
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

    def poke_existing(self, ack_timeout_ms=ACK_TIMEOUT_MS):
        """Ask the running instance to show its window and wait for it to say
        it did. Returns SHOWN, UNRESPONSIVE or UNREACHABLE (False off
        Windows)."""
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
