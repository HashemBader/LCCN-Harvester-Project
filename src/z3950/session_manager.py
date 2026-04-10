"""
Module: session_manager.py
Part of the LCCN Harvester Project — Z39.50 subsystem.

Provides lightweight utilities for validating Z39.50 server reachability
before committing to a full protocol-level connection.

Z39.50 servers can be unreachable for many reasons (firewall rules, temporary
downtime, DNS failures, wrong port).  A cheap TCP-level probe at the start of
a harvest run surfaces those problems early with a clear message rather than
letting them surface as a cryptic timeout deep inside the PyZ3950 ZOOM stack.

Currently exposes a single public function, ``validate_connection``, which
performs a plain TCP handshake (no Z39.50 protocol exchange) and returns a
boolean result.  This is intentionally protocol-agnostic so it can also be
used to pre-check plain socket connectivity to any host/port pair.
"""

import socket
import logging


def validate_connection(host: str, port: int, timeout: int = 5, silent: bool = False) -> bool:
    """
    Check whether a TCP connection can be established to the given host and port.

    Opens a socket, attempts a TCP three-way handshake, and immediately closes
    the connection.  No Z39.50 protocol bytes are exchanged; this is a pure
    network-reachability check.

    The ``int(port)`` cast guards against callers who store port numbers as
    strings (e.g. values read from a configuration file or GUI text field).

    Args:
        host (str): The hostname or IP address of the Z39.50 server.
        port (int): The TCP port number (Z39.50 standard port is 210; many
            modern catalog servers use 7090 or custom ports).
        timeout (int): Maximum seconds to wait for the connection to be
            established before giving up (default: 5).
        silent (bool): When ``True``, suppress the warning log message on
            failure.  Useful for background connectivity pre-checks where
            failures are expected and handled silently by the caller.

    Returns:
        bool: ``True`` if the TCP handshake succeeded; ``False`` on any
            network error (timeout, refused connection, DNS failure, etc.).
    """
    try:
        # socket.create_connection handles DNS resolution and IPv4/IPv6
        # selection automatically.  The context manager closes the socket
        # immediately after the handshake — we only need to know it succeeded.
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except (socket.timeout, socket.error, ValueError) as e:
        # ValueError is caught to handle invalid port values (e.g. non-numeric
        # strings) that slip past the int() cast if port is already an int but
        # the host string is malformed in a way that triggers a socket error.
        if not silent:
            logging.warning(f"Connection validation failed for {host}:{port} - {e}")
        return False
