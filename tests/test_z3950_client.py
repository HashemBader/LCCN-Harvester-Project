import pytest
from unittest.mock import MagicMock, patch

# Skip if dependency missing
pytest.importorskip("PyZ3950")

from src.z3950.client import Z3950Client
from PyZ3950 import zoom
from pymarc import Record

@pytest.fixture
def mock_zoom_connection():
    with patch('PyZ3950.zoom.Connection') as mock_conn_cls:
        mock_conn_instance = MagicMock()
        mock_conn_cls.return_value = mock_conn_instance
        yield mock_conn_cls, mock_conn_instance

@pytest.fixture
def mock_record():
    with patch('pymarc.Record') as mock_rec_cls:
        yield mock_rec_cls

def test_initialization():
    client = Z3950Client("test.host", 210, "test_db")
    assert client.host == "test.host"
    assert client.port == 210
    assert client.database == "test_db"
    assert client.syntax == "USMARC" # Default

def test_connect_success(mock_zoom_connection):
    mock_conn_cls, mock_conn_instance = mock_zoom_connection
    
    client = Z3950Client("test.host", 210, "test_db")
    client.connect()
    
    mock_conn_cls.assert_called_once_with(
        "test.host", 
        210, 
        databaseName="test_db", 
        preferredRecordSyntax="USMARC", 
        charset="utf-8"
    )
    assert client.conn == mock_conn_instance

def test_connect_failure(mock_zoom_connection):
    mock_conn_cls, _ = mock_zoom_connection
    mock_conn_cls.side_effect = Exception("Connection refused")
    
    client = Z3950Client("test.host", 210, "test_db")
    
    with pytest.raises(ConnectionError) as excinfo:
        client.connect()
    
    assert "Could not connect to Z39.50 server" in str(excinfo.value)

def test_search_by_isbn_success(mock_zoom_connection, mock_record):
    _, mock_conn_instance = mock_zoom_connection
    
    # Mock result set
    mock_result_set = MagicMock()
    mock_conn_instance.search.return_value = mock_result_set
    
    # Mock a record in the result set
    mock_record_obj = MagicMock()
    # Mock raw MARC data (simple leader + directory + etc) or just something Record() accepts if we mocked Record
    mock_record_obj.data = b'some_bytes'
    mock_result_set.__iter__.return_value = [mock_record_obj]
    
    client = Z3950Client("test.host", 210, "test_db")
    client.connect()
    
    results = client.search_by_isbn("978-0-123-45678-9")
    
    # Check query construction
    args, _ = mock_conn_instance.search.call_args
    # We assume it's the right object type
    
    assert len(results) == 1
    # Verify Record was called
    mock_record.assert_called_with(data=b'some_bytes')
    # Verify result is the mock instance return by mock_record class
    assert results[0] == mock_record.return_value

def test_search_handles_string_data(mock_zoom_connection, mock_record):
    """Test the fix where PyZ3950 returns str instead of bytes"""
    _, mock_conn_instance = mock_zoom_connection
    
    mock_result_set = MagicMock()
    mock_conn_instance.search.return_value = mock_result_set
    
    mock_record_obj = MagicMock()
    # Simulate string return (e.g. naive decoding)
    mock_record_obj.data = 'some_string'
    mock_result_set.__iter__.return_value = [mock_record_obj]
    
    client = Z3950Client("test.host", 210, "test_db")
    client.connect()
    
    results = client.search_by_isbn("12345")
    
    assert len(results) == 1
    # Should have been encoded to bytes passed to Record
    mock_record.assert_called_with(data=b'some_string')
    
def test_close(mock_zoom_connection):
    _, mock_conn_instance = mock_zoom_connection
    
    client = Z3950Client("test.host", 210, "test_db")
    client.connect()
    client.close()
    
    mock_conn_instance.close.assert_called_once()
    assert client.conn is None

