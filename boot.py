"""Startup diagnostics — stdlib only, imported before anything that can fail.

The installed Windows build is a windowed exe (no console). Before this, a
startup failure — a missing DLL, a broken bundle, an exception in main() —
killed the process with nothing on screen and, when it happened during the
third-party imports, nothing in the log either: "it isn't booting at all".
Now the log is armed first and an uncaught exception pops a message box
naming the error and the log file.
"""
import logging
import os
import sys
import traceback

log = logging.getLogger("aether.boot")
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
_log_path = None


def user_data_dir():
    """%LOCALAPPDATA%\\AetherHE (Windows) / ~/Library/Application Support/AetherHE
    (macOS) / $XDG_CONFIG_HOME/AetherHE (Linux) — settings.json, the WebView2
    profile and the log file all live here."""
    if sys.platform.startswith("win"):
        root = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        root = os.path.expanduser("~/Library/Application Support")
    else:
        root = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    d = os.path.join(root, "AetherHE")
    os.makedirs(d, exist_ok=True)
    return d


def show_error(text, title="Aether HE"):
    """Error box on Windows (the only place without a console to read);
    stderr elsewhere. Never raises."""
    try:
        if sys.platform.startswith("win"):
            import ctypes
            MB_ICONERROR = 0x10
            ctypes.WinDLL("user32").MessageBoxW(None, text, title, MB_ICONERROR)
            return True
        sys.stderr.write(text + "\n")
    except Exception:
        pass
    return False


def report_fatal(exc_type, exc, tb):
    """Log an uncaught exception and tell the user where the details are."""
    log.critical("uncaught exception", exc_info=(exc_type, exc, tb))
    if issubclass(exc_type, KeyboardInterrupt):
        return
    last = "".join(traceback.format_exception_only(exc_type, exc)).strip()
    where = f"\n\nFull details: {_log_path}" if _log_path else ""
    show_error(f"Aether HE could not start.\n\n{last}{where}")


def install_file_logging():
    """Console + rotating aether.log + faulthandler → aether-crash.log, and
    uncaught exceptions → report_fatal. Best-effort: a read-only profile must
    never stop the app from launching."""
    global _log_path
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    sys.excepthook = report_fatal
    try:
        import faulthandler
        from logging.handlers import RotatingFileHandler
        d = user_data_dir()
        path = os.path.join(d, "aether.log")
        fh = RotatingFileHandler(path, maxBytes=512 * 1024, backupCount=2, encoding="utf-8")
        fh.setFormatter(logging.Formatter(LOG_FORMAT))
        logging.getLogger().addHandler(fh)
        _log_path = path
        # faulthandler needs a real fd; keep the file open for the process life.
        crash = open(os.path.join(d, "aether-crash.log"), "a", encoding="utf-8")
        faulthandler.enable(file=crash, all_threads=True)
        try:
            import version
            ver = version.__version__
        except Exception:
            ver = "?"
        log.info("Aether %s starting (frozen=%s, argv=%s, log=%s)",
                 ver, bool(getattr(sys, "frozen", False)), sys.argv[1:], path)
    except Exception as e:  # pragma: no cover - defensive
        log.warning("file logging unavailable: %s", e)
