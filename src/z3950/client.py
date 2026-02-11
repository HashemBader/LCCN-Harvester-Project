
import logging
from typing import List, Optional, Generator, TYPE_CHECKING, Any

# Lazy imports to allow graceful degradation when dependencies are missing or incompatible
if TYPE_CHECKING:
    from PyZ3950 import zoom  # type: ignore
    from pymarc import Record, MARCReader

class Z3950Client:
    """
    A client for Z39.50 servers using the PyZ3950 (zoom) library.
    """

    def __init__(self, host: str, port: int, database: str, syntax: str = 'USMARC', encoding: str = 'utf-8'):
        """
        Initialize the Z39.50 client.

        Args:
            host (str): The hostname or IP of the Z39.50 server.
            port (int): The port number.
            database (str): The database name to query.
            syntax (str): The record syntax to request (default: USMARC).
            encoding (str): The encoding to use for records (default: utf-8).
        """
        self.host = host
        self.port = port
        self.database = database
        self.syntax = syntax
        self.encoding = encoding
        self.conn = None
        self.logger = logging.getLogger(__name__)

    def connect(self):
        """
        Establish a connection to the Z39.50 server.
        """
        try:
            # Lazy import to avoid import errors when PyZ3950 is missing/broken
            from PyZ3950 import zoom  # type: ignore
            
            self.logger.info(f"Connecting to {self.host}:{self.port}/{self.database}")
            self.conn = zoom.Connection(
                self.host,
                self.port,
                databaseName=self.database,
                preferredRecordSyntax=self.syntax,
                charset=self.encoding
            )
        except Exception as e:
            self.logger.error(f"Failed to connect to {self.host}:{self.port} - {e}")
            raise ConnectionError(f"Could not connect to Z39.50 server: {e}")

    def search_by_isbn(self, isbn: str) -> List[Any]:
        """
        Search for records by ISBN.

        Args:
            isbn (str): The ISBN to search for.

        Returns:
            List[Record]: A list of pymarc Record objects.
        """
        if not self.conn:
            raise ConnectionError("Not connected to server. Call connect() first.")

        # Lazy import
        from PyZ3950 import zoom  # type: ignore
        
        # Remove hyphens from ISBN just in case
        clean_isbn = isbn.replace("-", "").strip()
        
        # Z39.50 Use Attribute 7 is ISBN
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
        Close the connection.
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
        Process the result set from a Z39.50 search and convert to pymarc Records.
        """
        # Lazy import
        from pymarc import Record  # type: ignore
        
        records = []
        try:
           for res in result_set:
               # PyZ3950 returns raw MARC bytes in the 'data' attribute usually, or we can use .data
               raw_data = res.data
               if raw_data:
                   # PyZ3950 (Python 3 version) might return str if it auto-decoded
                   if isinstance(raw_data, str):
                       raw_data = raw_data.encode('utf-8') # Best guess, or latin-1 if MARC-8 was naively decoded
                   
                   # Use pymarc to parse the raw data
                   # MARCReader expects a stream, but we can just parse the bytes directly if it's one record
                   # Or use Record(data=raw_data)
                   try:
                       record = Record(data=raw_data)
                       records.append(record)
                   except Exception as parse_error:
                       self.logger.warning(f"Failed to parse MARC record: {parse_error}")
        except Exception as e:
            self.logger.error(f"Error iterating result set: {e}")
            
        return records

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
