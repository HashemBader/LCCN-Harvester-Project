"""
http_utils.py

Shared HTTP helper utilities used by all API clients in the LCCN Harvester.

Responsibilities
----------------
- Build an SSL context that trusts the correct CA bundle, with a priority order:
  1. Opt-out: honour LCCN_SSL_NO_VERIFY=1 for local/test environments.
  2. Explicit CA bundle via SSL_CERT_FILE or REQUESTS_CA_BUNDLE env vars.
  3. The ``certifi`` package (if installed), which ships an up-to-date Mozilla CA list.
  4. Python's built-in system trust store as a final fallback.
- Provide ``urlopen_with_ca``, a thin wrapper around ``urllib.request.urlopen``
  that always injects the CA-aware context so every API client gets consistent
  TLS behaviour without duplicating SSL setup code.
"""

from __future__ import annotations

import ssl
import urllib.request
import os
from pathlib import Path


def _build_ssl_context() -> ssl.SSLContext:
    """
    Build an SSL context using the best available CA bundle.

    Resolution order
    ----------------
    1. If ``LCCN_SSL_NO_VERIFY=1`` is set in the environment, return an
       *unverified* context (useful for development/proxy environments only).
    2. If ``SSL_CERT_FILE`` or ``REQUESTS_CA_BUNDLE`` points to an existing
       file, use that bundle (compatible with the ``requests`` library convention).
    3. Try to import ``certifi`` and use its bundled CA certificates.
    4. Fall back to Python's default system trust store.

    Returns
    -------
    ssl.SSLContext
        A configured SSL context ready to be passed to ``urllib.request.urlopen``.
    """
    # Allow callers to completely disable certificate verification via env var.
    # Should only be used in development or behind a corporate MITM proxy.
    if os.getenv("LCCN_SSL_NO_VERIFY", "0") == "1":
        return ssl._create_unverified_context()

    # Honour the standard environment variables used by the ``requests`` library
    # so that users who already set these for other tools benefit automatically.
    env_cafile = os.getenv("SSL_CERT_FILE") or os.getenv("REQUESTS_CA_BUNDLE")
    if env_cafile and Path(env_cafile).exists():
        return ssl.create_default_context(cafile=env_cafile)

    try:
        # certifi provides a regularly-updated Mozilla CA bundle as a Python
        # package; prefer it over the OS bundle which may be stale on some
        # platforms (e.g., older macOS versions before security updates).
        import certifi  # type: ignore

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        # certifi not installed or failed to locate its bundle — fall back to
        # the platform's built-in trust store.
        return ssl.create_default_context()


def urlopen_with_ca(req: urllib.request.Request, timeout: int):
    """
    Open a URL request using a CA-aware SSL context.

    This is the single entry point for all outbound HTTP(S) requests in the
    harvester. Centralising the call here ensures every API client uses
    consistent TLS settings without duplicating SSL setup code.

    Parameters
    ----------
    req : urllib.request.Request
        A prepared request object (URL + headers already set by the caller).
    timeout : int
        Socket timeout in seconds.  Passed directly to ``urlopen``.

    Returns
    -------
    http.client.HTTPResponse
        An open response object (use as a context manager to ensure it is
        closed after reading).

    Raises
    ------
    urllib.error.URLError
        On network-level errors (DNS failure, refused connection, timeout).
    urllib.error.HTTPError
        On non-2xx HTTP status codes.
    """
    ctx = _build_ssl_context()
    return urllib.request.urlopen(req, timeout=timeout, context=ctx)
