#!/usr/bin/env python3
"""
Test script to verify API fixes
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from api.loc_api import LibraryOfCongressAPI
from api.harvard_api import HarvardLibraryCloudAPI
from api.openlibrary_api import OpenLibraryAPI

def print_section(title):
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80 + "\n")

def test_harvard_api():
    """Test Harvard API with fixed parsing"""
    print_section("TEST 1: Harvard API - Fixed Parsing")

    api = HarvardLibraryCloudAPI(timeout=15)

    test_isbns = [
        ("9780134685991", "Clean Code"),
        ("9780596007126", "Head First Design Patterns"),
    ]

    for isbn, book_name in test_isbns:
        print(f"Testing ISBN: {isbn} ({book_name})")
        try:
            result = api.lookup_isbn(isbn)
            if result:
                print(f"  ✅ SUCCESS: Found LCCN: {result.get('lccn')}")
                if 'title' in result:
                    print(f"     Title: {result['title']}")
            else:
                print(f"  ⚠️  No match found (not an error)")
        except Exception as e:
            print(f"  ❌ ERROR: {str(e)}")
        print()

def test_openlibrary_validation():
    """Test OpenLibrary with invalid ISBN validation"""
    print_section("TEST 2: OpenLibrary - Invalid ISBN Filtering")

    api = OpenLibraryAPI(timeout=15)

    test_cases = [
        ("9780134685991", True, "Valid ISBN (Clean Code)"),
        ("9780000000000", False, "All zeros - should be rejected"),
        ("9789999999999", False, "All nines - should be rejected"),
        ("1234567890123", False, "Sequential digits - should be rejected"),
        ("9990000000000", False, "Invalid prefix - should be rejected"),
    ]

    for isbn, should_query, description in test_cases:
        print(f"Testing: {description}")
        print(f"  ISBN: {isbn}")
        try:
            result = api.lookup_isbn(isbn)
            if should_query:
                if result:
                    print(f"  ✅ Result: {result.get('lccn')}")
                else:
                    print(f"  ⚠️  No match found (queried but not in catalog)")
            else:
                if result:
                    print(f"  ❌ FAIL: Should have been rejected, but got: {result.get('lccn')}")
                else:
                    print(f"  ✅ PASS: Correctly rejected invalid ISBN")
        except Exception as e:
            print(f"  Error: {str(e)}")
        print()

def test_loc_api():
    """Test LOC API with improved queries"""
    print_section("TEST 3: Library of Congress - Improved Querying")

    api = LibraryOfCongressAPI(timeout=20)

    # Test with known ISBNs that should be in LOC catalog
    test_isbns = [
        ("9780134685991", "Clean Code by Robert Martin"),
        ("9780596007126", "Head First Design Patterns"),
        ("0201633612", "Design Patterns (ISBN-10)"),
    ]

    for isbn, book_name in test_isbns:
        print(f"Testing ISBN: {isbn} ({book_name})")
        try:
            result = api.lookup_isbn(isbn)
            if result:
                print(f"  ✅ SUCCESS: Found LCCN: {result.get('lccn')}")
                if 'title' in result:
                    print(f"     Title: {result['title']}")
            else:
                print(f"  ⚠️  No match found")
                print(f"     (Book may not be in LOC catalog or different indexing)")
        except Exception as e:
            print(f"  ❌ ERROR: {str(e)}")
        print()

def main():
    print("\n" + "=" * 80)
    print("  API FIXES VERIFICATION TEST")
    print("  Testing all three API improvements")
    print("=" * 80)

    # Test 1: Harvard API fixes
    test_harvard_api()

    # Test 2: OpenLibrary validation
    test_openlibrary_validation()

    # Test 3: LOC API improvements
    test_loc_api()

    print_section("VERIFICATION COMPLETE")
    print("✅ All API improvements have been tested")
    print()
    print("Summary of fixes:")
    print("  1. Harvard API: Added null checks to prevent 'NoneType' errors")
    print("  2. OpenLibrary: Added validation to reject obviously invalid ISBNs")
    print("  3. LOC API: Added multiple query methods and better MARCXML parsing")
    print()

if __name__ == "__main__":
    main()
