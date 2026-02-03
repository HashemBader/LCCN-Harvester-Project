
import pytest
from unittest.mock import patch, MagicMock
from src.z3950.session_manager import validate_connection
import socket
# Add src to path so we can import modules from the project source
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

def test_validate_connection_success():
    """Test that valid connection returns True."""
    with patch("socket.create_connection") as mock_conn:
        # Mock successful context manager entry/exit
        mock_conn.return_value.__enter__.return_value = MagicMock()
        
        result = validate_connection("valid.host", 210)
        assert result is True
        mock_conn.assert_called_once_with(("valid.host", 210), timeout=5)

def test_validate_connection_timeout():
    """Test that timeout returns False."""
    with patch("socket.create_connection", side_effect=socket.timeout):
        result = validate_connection("timeout.host", 210)
        assert result is False

def test_validate_connection_error():
    """Test that socket error returns False."""
    with patch("socket.create_connection", side_effect=socket.error("Connection refused")):
        result = validate_connection("bad.host", 210)
        assert result is False

def test_validate_connection_invalid_port():
    """Test that ValueError (e.g. invalid port type conversion) is handled."""
    # Although type hint says int, python allows passing str, which int() converts.
    # If we pass something non-convertible, int() raises ValueError.
    # validate_connection catches ValueError.
    
    # We don't verify socket call here because it fails before calling socket if int() fails
    # But wait, int(port) is called inside the try block.
    
    result = validate_connection("localhost", "invalid-port")
    assert result is False
