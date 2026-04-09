"""
Module: client.py
Part of the LCCN Harvester Project — Z39.50 subsystem.

Provides Z3950Client, a thin wrapper around PyZ3950's ZOOM binding that:
  - Opens a Z39.50 connection to a remote catalog server
  - Sends PQF (Prefix Query Format) attribute-based searches
  - Parses raw MARC binary responses into pymarc Record objects

Z39.50 is an ANSI/NISO standard information retrieval protocol (ISO 23950)
used by libraries worldwide for catalog queries.  Port 210 is the well-known
default, though many modern catalogs use custom ports.

Typical usage::

    with Z3950Client("z3950.loc.gov", 7090, "Voyager") as client:
        records = client.search_by_isbn("9780596517748")
"""

import logging
from typing import List, Optional, Generator, TYPE_CHECKING, Any

from src.z3950.pyz3950_compat import ensure_pyz3950_importable

# TYPE_CHECKING guard: these imports exist only for static analysis tools
# (mypy, Pyright).  At runtime both PyZ3950 and pymarc are imported lazily
# inside each method so the module remains loadable even when those packages
# are not installed.
if TYPE_CHECKING:
    from PyZ3950 import zoom  # type: ignore
    from pymarc import Record, MARCReader

class Z3950Client:
    """
    A client for Z39.50 servers using the PyZ3950 (zoom) library.

    Wraps the ZOOM Connection/Query/ResultSet API and converts raw MARC
    bytes returned by the server into pymarc Record objects that the rest
    of the harvester pipeline can consume.

    Supports use as a context manager (``with`` statement) which automatically
    calls ``connect()`` on entry and ``close()`` on exit.

    Attributes:
        host (str): Hostname or IP address of the Z39.50 server.
        port (int): TCP port the server listens on (commonly 210 or 7090).
        database (str): Name of the database/index to search on the server.
        syntax (str): MARC record syntax requested from the server (e.g. 'USMARC').
        encoding (str): Character encoding hint passed to the ZOOM connection.
        timeout (int): Socket-level timeout in seconds for the connection attempt.
        conn: Active PyZ3950 ZOOM Connection object, or None if not connected.
    """

    def __init__(self, host: str, port: int, database: str, syntax: str = 'USMARC', encoding: str = 'utf-8', timeout: int = 5):
        """
        Initialize the Z39.50 client.

        Does not open a network connection; call :meth:`connect` (or use the
        context manager) to establish the connection before searching.

        Args:
            host (str): The hostname or IP of the Z39.50 server.
            port (int): The port number.
            database (str): The database name to query.
            syntax (str): The record syntax to request (default: USMARC).
            encoding (str): The encoding to use for records (default: utf-8).
            timeout (int): Socket timeout in seconds for the connection (default: 5).
        """
        self.host = host
        self.port = port
        self.database = database
        self.syntax = syntax
        self.encoding = encoding
        self.timeout = timeout
        self.conn = None
        self.logger = logging.getLogger(__name__)

    def connect(self):
        """
        Establish a TCP connection to the Z39.50 server.

        Performs a pre-flight check via :func:`ensure_pyz3950_importable` before
        attempting the connection so that a missing PyZ3950 package produces a
        clear error instead of a cryptic ImportError later.

        The global socket default timeout is temporarily overridden for the
        duration of the connection handshake, then restored in a ``finally``
        block so other parts of the application are not affected.

        Raises:
            RuntimeError: If PyZ3950 cannot be imported.
            ConnectionError: If the TCP connection or ZOOM handshake fails for
                any other reason (wraps the original exception message).
        """
        try:
            ok, reason = ensure_pyz3950_importable()
            if not ok:
                raise RuntimeError(f"PyZ3950 import failed: {reason}")
            # Lazy import to avoid import errors when PyZ3950 is missing/broken
            from PyZ3950 import zoom  # type: ignore

            self.logger.info(f"Connecting to {self.host}:{self.port}/{self.database}")

            import socket
            # Snapshot the current global timeout so it can be restored after
            # the connection attempt, even if an exception is raised.
            old_timeout = socket.getdefaulttimeout()
            socket.setdefaulttimeout(self.timeout)
            try:
                self.conn = zoom.Connection(
                    self.host,
                    self.port,
                    databaseName=self.database,
                    preferredRecordSyntax=self.syntax,
                    charset=self.encoding
                )
            finally:
                # Always restore the previous global timeout to avoid
                # accidentally leaving a short timeout for the rest of the app.
                socket.setdefaulttimeout(old_timeout)
        except Exception as e:
            self.logger.error(f"Failed to connect to {self.host}:{self.port} - {e}")
            raise ConnectionError(f"Could not connect to Z39.50 server: {e}")

    def search_by_isbn(self, isbn: str) -> List[Any]:
        """
        Search for records by ISBN using a Z39.50 PQF attribute query.

        Builds a PQF (Prefix Query Format) query using Bib-1 Use Attribute 7
        (which maps to the ISBN index on Z39.50 servers that implement the
        Bib-1 attribute set).  The ISBN is normalised (hyphens stripped) before
        the query is sent.

        Args:
            isbn (str): The ISBN to search for (hyphens are stripped automatically).

        Returns:
            List[Any]: A list of pymarc Record objects parsed from the raw MARC
                response.  An empty list is returned if the server returns no hits
                or all records fail to parse.

        Raises:
            ConnectionError: If the client is not connected or if PyZ3950 is
                unavailable.
            Exception: Re-raises any exception thrown by the ZOOM search call so
                the caller can decide how to handle server-level errors.
        """
        if not self.conn:
            raise ConnectionError("Not connected to server. Call connect() first.")

        # Lazy import — guard is repeated here so search_by_isbn can be called
        # independently of connect() in unit tests that mock self.conn.
        ok, reason = ensure_pyz3950_importable()
        if not ok:
            raise ConnectionError(f"PyZ3950 import failed: {reason}")
        from PyZ3950 import zoom  # type: ignore

        # Normalise ISBN: strip hyphens and surrounding whitespace so the server
        # receives a plain digit string (e.g. "9780596517748").
        clean_isbn = isbn.replace("-", "").strip()

        # PQF syntax: @attr 1=7 selects the Bib-1 "ISBN" use attribute (BIB-1
        # attribute set, use attribute 7 = ISBN).  PQF is the most portable query
        # format across Z39.50 implementations.
        query = zoom.Query('PQF', f'@attr 1=7 {clean_isbn}')

        try:
            self.logger.info(f"Searching for ISBN: {clean_isbn}")
            res = self.conn.search(query)
            return self._process_results(res)
        except Exception as e:
            self.logger.error(f"Search failed for ISBN {isbn} - {e}")
            raise

    def close(self):
        """
        Close the Z39.50 connection and release the underlying socket.

        Safe to call even if the client was never connected (no-op in that case).
        Errors during the close call are logged as warnings rather than raised so
        that cleanup code (e.g. in ``__exit__``) never masks the original exception.
        ``self.conn`` is always set to ``None`` in the ``finally`` block so the
        object can be inspected or garbage-collected cleanly.
        """
        if self.conn:
            try:
                self.conn.close()
            except Exception as e:
                self.logger.warning(f"Error closing connection: {e}")
            finally:
                self.conn = None

    def _process_results(self, result_set) -> list:
        """
        Iterate a ZOOM ResultSet and convert each entry to a pymarc Record.

        This is an internal helper called by :meth:`search_by_isbn` after the
        server returns results.  It handles several edge cases that arise from
        real-world Z39.50 server behaviour:

        * **Raw bytes vs. decoded string**: Some PyZ3950 builds auto-decode the
          MARC payload to a Python ``str``.  The bytes are recovered by re-encoding
          as UTF-8 (the best-effort assumption; MARC-8 data naively decoded as
          latin-1 may be corrupted, but this avoids a hard crash).
        * **MARC leader byte 9 (character coding scheme)**: pymarc's
          ``force_utf8`` flag does not fully suppress MARC-8 decoding when the
          leader byte at offset 9 is ``' '`` (MARC-8 indicator).  Patching this
          byte to ``'a'`` (UTF-8 indicator) ensures ``force_utf8=True`` takes
          effect uniformly and avoids ``UnicodeDecodeError`` exceptions.
        * **Broken upstream records**: Individual parse failures are caught and
          logged at DEBUG level so a single malformed server record does not
          abort the entire result set.

        Args:
            result_set: A PyZ3950 ZOOM ResultSet as returned by
                ``zoom.Connection.search()``.

        Returns:
            list: Zero or more pymarc Record objects parsed from the result set.
        """
        # Lazy import — pymarc is optional; suppress its verbose output while parsing.
        from pymarc import Record  # type: ignore
        # pymarc emits noisy warnings for records it cannot fully decode.
        # Silence those at the library logger level to keep the console clean.
        logging.getLogger('pymarc').setLevel(logging.CRITICAL)

        records = []
        try:
            for res in result_set:
                # PyZ3950 exposes the raw MARC payload via the .data attribute.
                raw_data = res.data
                if raw_data:
                    # Some PyZ3950 (Python 3 port) builds decode the payload to
                    # a str.  Re-encode it so pymarc always receives bytes.
                    if isinstance(raw_data, str):
                        raw_data = raw_data.encode('utf-8')  # Best guess; MARC-8 data decoded as latin-1 may be mangled but avoids a crash

                    try:
                        # MARC leader offset 9 signals the character coding scheme:
                        #   ' ' (space / 0x20) = MARC-8 encoding
                        #   'a'        (0x61)  = UTF-8 encoding
                        # When this byte is not 'a', pymarc's internal MARC-8
                        # decoder is still invoked even with force_utf8=True.
                        # Patching it to 'a' forces the UTF-8 path consistently.
                        if len(raw_data) >= 24 and raw_data[9:10] != b'a':
                            raw_data = raw_data[:9] + b'a' + raw_data[10:]

                        record = Record(data=raw_data, force_utf8=True, utf8_handling='replace')
                        records.append(record)
                    except Exception as parse_error:
                        # Only log at debug level so we don't spam the console for naturally broken upstream records
                        self.logger.debug(f"Failed to parse MARC record: {parse_error}")
        except Exception as e:
            self.logger.error(f"Error iterating result set: {e}")

        return records

    def __enter__(self):
        """Open the connection and return self when used as a context manager."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Close the connection on context manager exit, regardless of exceptions."""
        self.close()
