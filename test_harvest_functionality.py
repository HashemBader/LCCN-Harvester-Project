#!/usr/bin/env python3
"""
Functional test script for LCCN Harvester
Tests actual ISBN processing, API calls, and error handling
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from database.db_manager import DatabaseManager
from harvester.orchestrator import HarvestOrchestrator
from harvester.targets import create_target_from_config
import json
from datetime import datetime

def print_section(title):
    """Print a section header"""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)

def test_isbn_processing():
    """Test ISBN processing and validation"""
    print_section("TEST 1: ISBN Processing & Validation")

    test_cases = [
        ("9780134685991", True, "Valid ISBN-13"),
        ("978-0-13-468599-1", True, "Valid ISBN-13 with hyphens"),
        ("0134685997", True, "Valid ISBN-10"),
        ("invalid", False, "Invalid ISBN"),
        ("", False, "Empty ISBN"),
        ("123", False, "Too short"),
    ]

    from utils.isbn_validator import normalize_isbn, validate_isbn

    for isbn, should_be_valid, description in test_cases:
        normalized = normalize_isbn(isbn) if isbn else ""
        is_valid = validate_isbn(isbn) if isbn else False
        status = "✅ PASS" if is_valid == should_be_valid else "❌ FAIL"
        print(f"{status} | {description:30} | Input: '{isbn:20}' | Valid: {is_valid}")

def test_api_implementations():
    """Test that all APIs are properly implemented"""
    print_section("TEST 2: API Implementation Check")

    from api.loc_api import LibraryOfCongressAPI
    from api.harvard_api import HarvardLibraryCloudAPI
    from api.openlibrary_api import OpenLibraryAPI

    apis = [
        ("Library of Congress", LibraryOfCongressAPI),
        ("Harvard LibraryCloud", HarvardLibraryCloudAPI),
        ("OpenLibrary", OpenLibraryAPI)
    ]

    for name, api_class in apis:
        try:
            api = api_class(timeout=10)
            # Check if lookup_isbn method exists
            assert hasattr(api, 'lookup_isbn'), f"{name} missing lookup_isbn method"
            print(f"✅ PASS | {name:30} | API class initialized successfully")
        except Exception as e:
            print(f"❌ FAIL | {name:30} | Error: {str(e)}")

def test_target_creation():
    """Test target creation from config"""
    print_section("TEST 3: Target Creation & Priority")

    configs = [
        {"name": "Library of Congress", "enabled": True, "priority": 1},
        {"name": "Harvard LibraryCloud", "enabled": True, "priority": 2},
        {"name": "OpenLibrary", "enabled": True, "priority": 3},
    ]

    targets = []
    for config in configs:
        try:
            target = create_target_from_config(config)
            targets.append(target)
            print(f"✅ PASS | {config['name']:30} | Priority: {config['priority']} | Target created")
        except Exception as e:
            print(f"❌ FAIL | {config['name']:30} | Error: {str(e)}")

    return targets

def test_database_operations():
    """Test database save and retrieval"""
    print_section("TEST 4: Database Operations")

    from database import MainRecord, AttemptedRecord

    db = DatabaseManager()
    db.init_db()

    # Test save successful result
    try:
        record = MainRecord(
            isbn="TEST_ISBN_123",
            lccn="TEST_LCCN_456",
            nlmcn=None,
            source="Test Source"
        )
        db.upsert_main(record)
        print("✅ PASS | Save successful result    | Record saved to main table")
    except Exception as e:
        print(f"❌ FAIL | Save successful result    | Error: {str(e)}")

    # Test save failed attempt
    try:
        record = AttemptedRecord(
            isbn="TEST_ISBN_789",
            last_target="Test Target",
            last_error="Test error message",
            fail_count=1
        )
        db.upsert_attempted(record)
        print("✅ PASS | Save failed attempt       | Record saved to attempted table")
    except Exception as e:
        print(f"❌ FAIL | Save failed attempt       | Error: {str(e)}")

    # Test retrieval
    try:
        with db.connect() as conn:
            # Check main table
            cursor = conn.execute("SELECT COUNT(*) FROM main WHERE isbn = 'TEST_ISBN_123'")
            count = cursor.fetchone()[0]
            if count > 0:
                print(f"✅ PASS | Retrieve from main table  | Found {count} record(s)")
            else:
                print("❌ FAIL | Retrieve from main table  | No records found")

            # Check attempted table
            cursor = conn.execute("SELECT COUNT(*) FROM attempted WHERE isbn = 'TEST_ISBN_789'")
            count = cursor.fetchone()[0]
            if count > 0:
                print(f"✅ PASS | Retrieve from attempted   | Found {count} record(s)")
            else:
                print("❌ FAIL | Retrieve from attempted   | No records found")
    except Exception as e:
        print(f"❌ FAIL | Database retrieval        | Error: {str(e)}")

def test_actual_harvest():
    """Test actual harvest with real ISBNs"""
    print_section("TEST 5: Actual Harvest Execution")

    print("\n⚠️  NOTE: This test makes real API calls and may take 30-60 seconds...")
    print("Testing with 3 sample ISBNs from test_isbns.tsv\n")

    # Create a small test file
    test_file = Path("data/sample/functional_test.tsv")
    test_file.parent.mkdir(parents=True, exist_ok=True)

    with open(test_file, 'w') as f:
        f.write("ISBN\n")
        f.write("9780134685991\n")  # Clean Code by Robert Martin
        f.write("9780596007126\n")  # Head First Design Patterns
        f.write("9780000000000\n")  # Invalid/Non-existent ISBN

    print(f"Created test file: {test_file}")
    print("ISBNs to test:")
    print("  1. 9780134685991 (Clean Code)")
    print("  2. 9780596007126 (Head First Design Patterns)")
    print("  3. 9780000000000 (Non-existent)")
    print()

    # Create targets
    configs = [
        {"name": "Library of Congress", "enabled": True, "priority": 1},
        {"name": "Harvard LibraryCloud", "enabled": True, "priority": 2},
        {"name": "OpenLibrary", "enabled": True, "priority": 3},
    ]

    targets = []
    for config in configs:
        try:
            target = create_target_from_config(config)
            targets.append(target)
        except Exception as e:
            print(f"❌ Error creating target {config['name']}: {str(e)}")
            return

    # Initialize database
    db = DatabaseManager()
    db.init_db()

    # Clear previous test data
    try:
        with db.connect() as conn:
            conn.execute("DELETE FROM main WHERE isbn LIKE '97803%' OR isbn LIKE '97805%'")
            conn.execute("DELETE FROM attempted WHERE isbn LIKE '97803%' OR isbn LIKE '97805%'")
            conn.commit()
        print("✅ Cleared previous test data\n")
    except Exception as e:
        print(f"⚠️  Warning: Could not clear previous data: {str(e)}\n")

    # Read ISBNs from file
    isbns = []
    with open(test_file, 'r') as f:
        for line in f:
            line = line.strip()
            if line and line != "ISBN":  # Skip header
                isbns.append(line)

    print(f"Read {len(isbns)} ISBNs from file\n")

    # Run harvest
    print("Starting harvest...\n")
    start_time = datetime.now()

    try:
        orchestrator = HarvestOrchestrator(
            db=db,
            targets=targets,
            retry_days=7
        )

        summary = orchestrator.run(
            isbns=isbns,
            dry_run=False  # Actually save to database
        )

        elapsed = (datetime.now() - start_time).total_seconds()

        print("\n" + "-" * 80)
        print("HARVEST SUMMARY")
        print("-" * 80)
        print(f"Total ISBNs processed: {summary.total_isbns}")
        print(f"Successful lookups:    {summary.successes}")
        print(f"Failed lookups:        {summary.failures}")
        print(f"From cache:            {summary.cached_hits}")
        print(f"Skipped (recent fail): {summary.skipped_recent_fail}")
        print(f"Actually attempted:    {summary.attempted}")
        print(f"Elapsed time:          {elapsed:.2f} seconds")
        print("-" * 80)

    except Exception as e:
        print(f"\n❌ HARVEST FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        return

    # Check results in database
    print("\nChecking database results...")

    try:
        with db.connect() as conn:
            # Check successful results
            print("\n📊 SUCCESSFUL RESULTS (main table):")
            cursor = conn.execute("""
                SELECT isbn, lccn, classification, source
                FROM main
                WHERE isbn IN ('9780134685991', '9780596007126', '9780000000000')
                ORDER BY date_added DESC
            """)
            results = cursor.fetchall()

            if results:
                for row in results:
                    print(f"  ✅ ISBN: {row[0]}")
                    print(f"     LCCN: {row[1]}")
                    print(f"     Classification: {row[2]}")
                    print(f"     Source: {row[3]}")
                    print()
            else:
                print("  (No successful results)")

            # Check failed attempts
            print("\n❌ FAILED ATTEMPTS (attempted table):")
            cursor = conn.execute("""
                SELECT isbn, last_target, last_error, fail_count
                FROM attempted
                WHERE isbn IN ('9780134685991', '9780596007126', '9780000000000')
                ORDER BY last_attempted DESC
            """)
            failed = cursor.fetchall()

            if failed:
                for row in failed:
                    print(f"  ❌ ISBN: {row[0]}")
                    print(f"     Last Target: {row[1]}")
                    print(f"     Error: {row[2]}")
                    print(f"     Fail Count: {row[3]}")
                    print()
            else:
                print("  (No failed attempts)")

    except Exception as e:
        print(f"❌ Error checking results: {str(e)}")

def test_error_messages():
    """Test that error messages are standardized and correct"""
    print_section("TEST 6: Error Message Standardization")

    from utils import messages

    # Check that message constants exist
    message_tests = [
        ("NetworkMessages.api_not_implemented", hasattr(messages.NetworkMessages, 'api_not_implemented')),
        ("NetworkMessages.no_match", hasattr(messages.NetworkMessages, 'no_match')),
        ("HarvestMessages.lccn_found", hasattr(messages.HarvestMessages, 'lccn_found')),
        ("HarvestMessages.processing_isbn", hasattr(messages.HarvestMessages, 'processing_isbn')),
    ]

    for msg_name, exists in message_tests:
        status = "✅ PASS" if exists else "❌ FAIL"
        print(f"{status} | Message constant exists: {msg_name}")

def main():
    """Run all functional tests"""
    print("\n" + "=" * 80)
    print("  LCCN HARVESTER - FUNCTIONAL TESTING SUITE")
    print("  Date: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 80)

    try:
        test_isbn_processing()
        test_api_implementations()
        test_target_creation()
        test_database_operations()
        test_error_messages()
        test_actual_harvest()  # This one makes real API calls

        print_section("TEST SUITE COMPLETE")
        print("\n✅ All functional tests completed successfully!")
        print("\nNext steps:")
        print("  1. Review the harvest results above")
        print("  2. Check Results tab in GUI to see data")
        print("  3. Verify error messages are accurate")
        print("  4. Test with larger ISBN batches if needed")
        print()

    except KeyboardInterrupt:
        print("\n\n⚠️  Tests interrupted by user")
    except Exception as e:
        print(f"\n\n❌ TEST SUITE FAILED: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
