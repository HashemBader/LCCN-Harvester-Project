"""
Package: src.z3950
Part of the LCCN Harvester Project.

Provides the Z39.50 client subsystem used to query library catalog servers
using the ISO 23950 (Z39.50) information retrieval protocol.

Sub-modules
-----------
client
    ``Z3950Client`` — opens connections, fires PQF ISBN queries, and converts
    raw MARC binary responses into ``pymarc.Record`` objects.
marc_decoder
    Converts ``pymarc.Record`` objects into the MARC-JSON dictionary format
    consumed by ``src.utils.marc_parser`` for call-number extraction.
pyz3950_compat
    One-shot import probe for the optional ``PyZ3950`` package; returns a
    ``(bool, reason)`` tuple so callers can degrade gracefully when the
    package is unavailable.
session_manager
    Lightweight TCP connectivity pre-check for Z39.50 servers.

All Z39.50 functionality is optional — if ``PyZ3950`` is not installed the
rest of the harvester continues to operate via its HTTP-based API paths.
"""
