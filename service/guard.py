"""Request guard for the AETHER loopback service.

The service binds 127.0.0.1, but loopback alone does not stop a web page in
the user's browser from reaching it: a cross-site POST is a "simple request"
and the server parses the body as JSON whatever its Content-Type, and DNS
rebinding lets a page read GET routes. `check_request` closes both:

  1. The Host header must be a loopback name on our own port (rebinding).
  2. A request carrying an Origin header (every browser cross-site request
     does; the nexus backend's server-side fetch sends none) must name an
     origin listed in AETHER_SERVICE_ORIGINS.
  3. If AETHER_SERVICE_TOKEN is set, X-Aether-Token must match it.
"""
import hmac
import os


def check_request(headers, port, *, allowed_origins=frozenset(), token=None):
    """Return a short rejection reason, or None if the request may proceed."""
    host = headers.get("Host")
    if not host:
        return "missing Host header"
    host = host.strip().lower()
    if host not in (f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"):
        return "Host not allowed"

    origin = headers.get("Origin")
    if origin is not None and origin not in allowed_origins:
        return "Origin not allowed"

    if token:
        supplied = headers.get("X-Aether-Token") or ""
        if not hmac.compare_digest(supplied.encode("utf-8"), token.encode("utf-8")):
            return "bad or missing token"
    return None


def config_from_env():
    """Return (allowed_origins, token) from AETHER_SERVICE_ORIGINS / _TOKEN."""
    raw = os.environ.get("AETHER_SERVICE_ORIGINS", "")
    origins = frozenset(o.strip() for o in raw.split(",") if o.strip())
    token = os.environ.get("AETHER_SERVICE_TOKEN", "") or None
    return origins, token
