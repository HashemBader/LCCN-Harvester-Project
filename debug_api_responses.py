#!/usr/bin/env python3
"""
Debug script to inspect raw API responses from LOC, Harvard, and OpenLibrary.
This will help diagnose why LOC and Harvard aren't finding ISBNs.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from api.loc_api import LocApiClient
from api.harvard_api import HarvardApiClient
from api.openlibrary_api import OpenLibraryApiClient
import json


def test_api_with_debug(api_client, isbn, api_name):
    """Test an API and show detailed response information."""
    print(f"\n{'='*80}")
    print(f"Testing {api_name} with ISBN: {isbn}")
    print(f"{'='*80}")

    try:
        # Show the URL being queried
        if hasattr(api_client, 'build_url'):
            url = api_client.build_url(isbn)
            print(f"\n1. Query URL:")
            print(f"   {url}")
        else:
            # OpenLibrary doesn't have build_url
            url = f"{api_client.base_url}/{isbn}.json"
            print(f"\n1. Query URL:")
            print(f"   {url}")

        # Fetch the raw response
        print(f"\n2. Fetching data...")
        payload = api_client.fetch(isbn)

        # Show raw response
        print(f"\n3. Raw Response:")
        if payload is None:
            print("   None (404 or no response)")
        else:
            print(json.dumps(payload, indent=2)[:2000])  # First 2000 chars
            if len(json.dumps(payload)) > 2000:
                print(f"\n   ... (truncated, total length: {len(json.dumps(payload))} chars)")

        # Try extraction
        print(f"\n4. Call Number Extraction:")
        result = api_client.extract_call_numbers(isbn, payload)
        print(f"   Status: {result.status}")
        print(f"   LCCN: {result.lccn}")
        print(f"   NLMCN: {result.nlmcn}")
        if hasattr(result, 'error_message') and result.error_message:
            print(f"   Error: {result.error_message}")

        return result

    except Exception as e:
        print(f"\n❌ Exception occurred:")
        print(f"   Type: {type(e).__name__}")
        print(f"   Message: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


def main():
    # Test ISBNs - using older books more likely to be in LOC catalog
    test_isbns = [
        "0060935464",     # To Kill a Mockingbird - classic literature
        "9780451524935",  # 1984 by George Orwell
        "0316769487",     # The Catcher in the Rye
        "9780134685991",  # Effective Java (modern, less likely in LOC)
    ]

    # Initialize API clients with longer timeout for debugging
    loc_client = LocApiClient(timeout_seconds=30)
    harvard_client = HarvardApiClient(timeout_seconds=30)
    openlibrary_client = OpenLibraryApiClient(timeout_seconds=30)

    for isbn in test_isbns:
        print(f"\n\n{'#'*80}")
        print(f"# Testing ISBN: {isbn}")
        print(f"{'#'*80}")

        # Test Library of Congress
        test_api_with_debug(loc_client, isbn, "Library of Congress")

        # Test Harvard LibraryCloud
        test_api_with_debug(harvard_client, isbn, "Harvard LibraryCloud")

        # Test OpenLibrary
        test_api_with_debug(openlibrary_client, isbn, "OpenLibrary")

        print("\n" + "="*80)
        input("Press Enter to continue to next ISBN...")


if __name__ == "__main__":
    main()
