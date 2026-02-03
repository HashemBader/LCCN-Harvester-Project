import os
import sys
import pytest
from unittest.mock import patch, MagicMock, mock_open
from src.utils.isbn_validator import validate_isbn, log_invalid_isbn, INVALID_ISBN_LOG

# Add src to path so we can import modules from the project source
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

# Valid ISBNs
VALID_ISBN10_CLEAN = "0131103628"
VALID_ISBN10_HYPHENS = "0-13-110362-8"
VALID_ISBN13_CLEAN = "9780131103627"
VALID_ISBN13_HYPHENS = "978-0-13-110362-7"

# Invalid ISBNs
INVALID_LENGTH_SHORT = "123"
INVALID_LENGTH_LONG = "12345678901234567890"
INVALID_CHARS = "0-13-110abc-8"
INVALID_CHECKSUM_10 = "0131103629" # Last digit changed
INVALID_CHECKSUM_13 = "9780131103628" # Last digit changed

@pytest.mark.parametrize("isbn_input", [
    VALID_ISBN10_CLEAN,
    VALID_ISBN10_HYPHENS,
    VALID_ISBN13_CLEAN,
    VALID_ISBN13_HYPHENS,
    "0-321-57351-X", # Valid ISBN-10 with X check digit
])
def test_validate_isbn_valid(isbn_input):
    """Test that valid ISBNs return True."""
    # We patch log_invalid_isbn to ensure it's NOT called for valid ISBNs
    with patch("src.utils.isbn_validator.log_invalid_isbn") as mock_log:
        assert validate_isbn(isbn_input) is True
        mock_log.assert_not_called()

@pytest.mark.parametrize("isbn_input", [
    INVALID_LENGTH_SHORT,
    INVALID_LENGTH_LONG,
    INVALID_CHARS,
    INVALID_CHECKSUM_10,
    INVALID_CHECKSUM_13,
    "",
    "   ",
])
def test_validate_isbn_invalid(isbn_input):
    """Test that invalid ISBNs return False and are logged."""
    with patch("src.utils.isbn_validator.log_invalid_isbn") as mock_log:
        assert validate_isbn(isbn_input) is False
        # Verify logging was triggered
        mock_log.assert_called_once()
        # Ensure called with the input string
        assert mock_log.call_args[0][0] == isbn_input

def test_log_invalid_isbn_file_write():
    """Test that log_invalid_isbn actually attempts to write to the file."""
    test_isbn = "bad-isbn"
    test_reason = "Test Reason"
    
    m_open = mock_open()
    
    with patch("pathlib.Path.open", m_open):
        log_invalid_isbn(test_isbn, test_reason)
        
    m_open.assert_called_once()
    handle = m_open()
    handle.write.assert_called_once()
    
    # Verify content format
    written_content = handle.write.call_args[0][0]
    # Expect: timestamp\tbad-isbn\n
    assert f"\t{test_isbn}\n" in written_content
