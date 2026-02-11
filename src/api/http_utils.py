"""
Shared HTTP helpers for API clients.
"""

from __future__ import annotations

import ssl
import urllib.request
import os
from pathlib import Path


def _build_ssl_context() -> ssl.SSLContext:
    """
    Build an SSL context using certifi CA bundle when available.
    Falls back to the system default trust store.
    """
    if os.getenv("LCCN_SSL_NO_VERIFY", "0") == "1":
        return ssl._create_unverified_context()

    env_cafile = os.getenv("SSL_CERT_FILE") or os.getenv("REQUESTS_CA_BUNDLE")
    if env_cafile and Path(env_cafile).exists():
        return ssl.create_default_context(cafile=env_cafile)

    try:
        import certifi  # type: ignore

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def urlopen_with_ca(req: urllib.request.Request, timeout: int):
    """
    Open URL with a CA-aware SSL context.
    """
    ctx = _build_ssl_context()
    return urllib.request.urlopen(req, timeout=timeout, context=ctx)
