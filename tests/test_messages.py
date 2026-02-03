
import unittest
import sys
import os

# Add project root to sys.path to allow imports from src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.utils import messages

class TestMessages(unittest.TestCase):
    
    def test_system_messages(self):
        """Verify SystemMessages attributes are present."""
        self.assertTrue(messages.SystemMessages.app_start)
        self.assertTrue(messages.SystemMessages.app_close)
        self.assertTrue(messages.SystemMessages.config_loaded)
        # Test formatting
        self.assertIn("test", messages.SystemMessages.config_error.format(error="test"))

    def test_database_messages(self):
        """Verify DatabaseMessages attributes and formatting."""
        self.assertTrue(messages.DatabaseMessages.connecting)
        self.assertTrue(messages.DatabaseMessages.connect_success)
        
        # Dynamic checks
        self.assertIn("123", messages.DatabaseMessages.record_found.format(isbn="123"))
        msg = messages.DatabaseMessages.insert_success.format(isbn="123", lccn="abc")
        self.assertIn("123", msg)
        self.assertIn("abc", msg)
        self.assertIn("err", messages.DatabaseMessages.insert_fail.format(isbn="123", error="err"))

    def test_network_messages(self):
        """Verify NetworkMessages attributes and formatting."""
        self.assertIn("LOC", messages.NetworkMessages.connecting_to_target.format(target="LOC"))
        self.assertIn("123", messages.NetworkMessages.searching.format(isbn="123"))
        
        msg = messages.NetworkMessages.success_match.format(target="LOC", call_number="QA76")
        self.assertIn("LOC", msg)
        self.assertIn("QA76", msg)
        
        self.assertIn("LOC", messages.NetworkMessages.no_match.format(target="LOC"))
        self.assertIn("5", messages.NetworkMessages.connection_timeout.format(target="LOC", seconds=5))
        self.assertIn("err", messages.NetworkMessages.protocol_error.format(target="LOC", error="err"))

    def test_gui_messages(self):
        """Verify GuiMessages attributes."""
        self.assertTrue(messages.GuiMessages.ready)
        self.assertTrue(messages.GuiMessages.processing.format(current=1, total=10))
        self.assertTrue(messages.GuiMessages.completed.format(success=5))
        
        self.assertTrue(messages.GuiMessages.err_title_file)
        self.assertTrue(messages.GuiMessages.err_body_file)
        
        self.assertTrue(messages.GuiMessages.warn_title_invalid)
        self.assertTrue(messages.GuiMessages.warn_body_invalid.format(count=5))

    def test_config_messages(self):
        """Verify ConfigMessages attributes and formatting."""
        self.assertIn("LOC", messages.ConfigMessages.target_added.format(name="LOC"))
        self.assertIn("LOC", messages.ConfigMessages.target_modified.format(name="LOC"))
        self.assertIn("1", messages.ConfigMessages.target_deleted.format(target_id="1"))
        self.assertIn("1", messages.ConfigMessages.target_not_found.format(target_id="1"))
        self.assertIn("err", messages.ConfigMessages.load_error.format(error="err"))
        self.assertIn("err", messages.ConfigMessages.save_error.format(error="err"))

if __name__ == "__main__":
    unittest.main()
