import sys
import os
import unittest

# Add src to path so we can import modules from the project source
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from utils.targets_manager import TargetsManager, Target

class TestTargetsManager(unittest.TestCase):
    """
    Test suite for TargetsManager.
    
    This suite tests the CRUD (Create, Read, Update, Delete) operations
    on the actual 'targets.tsv' file.
    
    NOTE: These tests are stateful and persistent. They modify the actual data file.
    """
    def setUp(self):
        """Prepare common test data and objects before each test method."""
        self.cm = TargetsManager()
        self.test_target_name = "Test Library"
        self.modified_target_name = "Modified Library"

    def _find_target_by_name(self, name):
        """Helper method to find a target object by its name."""
        targets = self.cm.get_all_targets()
        for t in targets:
            if t.name == name:
                return t
        return None

    def test_1_add_target(self):
        """
        Test adding a new target to the configuration.
        This verifies that a target can be persisted to the TSV file.
        """
        print("\n--- Test: Add Target ---")
        
        # Check if already exists to avoid duplicates if test is re-run without cleanup
        existing = self._find_target_by_name(self.test_target_name)
        if existing:
            print(f"Target '{self.test_target_name}' already exists. ID: {existing.target_id}")
            return

        new_target = Target(
            target_id="", # Empty ID tells TargetsManager to auto-assign one
            name=self.test_target_name,
            target_type="Z3950",
            host="test.host",
            port=9999,
            database="testdb",
            record_syntax="USMARC",
            rank=99,
            selected=True
        )
        self.cm.add_target(new_target)
        
        # Verify it was added successfully
        added = self._find_target_by_name(self.test_target_name)
        self.assertIsNotNone(added, "Target should have been added")
        print(f"Successfully added target: {added.name} (ID: {added.target_id})")

    def test_2_modify_target(self):
        """
        Test modifying an existing target.
        Renames 'Test Library' to 'Modified Library'.
        """
        print("\n--- Test: Modify Target ---")
        
        # Look for the target to modify (either original or already modified)
        target = self._find_target_by_name(self.test_target_name)
        if not target:
            # Check if it was already modified from a previous run
            target = self._find_target_by_name(self.modified_target_name)
            if target:
                print(f"Target already modified to '{self.modified_target_name}'. Skipping modification.")
                return
            else:
                self.fail(f"Could not find target '{self.test_target_name}' to modify. Run test_1_add_target first.")

        # Perform modification
        target.name = self.modified_target_name
        self.cm.modify_target(target)
        
        # Verify the change was persisted
        modified = self._find_target_by_name(self.modified_target_name)
        self.assertIsNotNone(modified, "Target name should have been updated")
        print(f"Successfully modified target to: {modified.name}")

    def test_3_delete_target(self):
        """
        Test deleting the target.
        Removes 'Modified Library' (or 'Test Library') from the configuration.
        """
        print("\n--- Test: Delete Target ---")
        
        # Find the target to delete (could be under old or new name)
        target = self._find_target_by_name(self.modified_target_name)
        if not target:
            target = self._find_target_by_name(self.test_target_name)
        
        if not target:
            print("Target not found. Nothing to delete.")
            return

        target_id = target.target_id
        self.cm.delete_target(target_id)
        
        # Verify it is gone
        deleted = self._find_target_by_name(self.modified_target_name) or self._find_target_by_name(self.test_target_name)
        self.assertIsNone(deleted, "Target should have been deleted")
        print(f"Successfully deleted target ID: {target_id}")

if __name__ == "__main__":
    # Run tests. 'failfast=True' stops testing at the first failure.
    unittest.main(failfast=True, verbosity=2)
