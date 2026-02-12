#!/usr/bin/env python3
"""
Quick test to verify Harvard API is properly connected.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from harvester.targets import create_target_from_config

def test_harvard_connection():
    """Test that Harvard API can be created from config."""

    print("=" * 60)
    print("  HARVARD API CONNECTION TEST")
    print("=" * 60)
    print()

    # Test with "Harvard" name (as used in targets.json)
    config1 = {
        "name": "Harvard",
        "type": "api",
        "selected": True,
        "rank": 2
    }

    print("Test 1: Creating target with name 'Harvard'")
    try:
        target = create_target_from_config(config1)
        print(f"  ✅ SUCCESS: Created target: {target.name}")
        print(f"     Type: {type(target).__name__}")
    except Exception as e:
        print(f"  ❌ FAILED: {str(e)}")

    print()

    # Test with "Harvard LibraryCloud" name (full name)
    config2 = {
        "name": "Harvard LibraryCloud",
        "type": "api",
        "selected": True,
        "rank": 2
    }

    print("Test 2: Creating target with name 'Harvard LibraryCloud'")
    try:
        target = create_target_from_config(config2)
        print(f"  ✅ SUCCESS: Created target: {target.name}")
        print(f"     Type: {type(target).__name__}")
    except Exception as e:
        print(f"  ❌ FAILED: {str(e)}")

    print()

    # Test actual lookup (optional - will make a real API call)
    print("Test 3: Testing actual Harvard API lookup")
    try:
        target = create_target_from_config(config1)
        result = target.lookup("9780134685991")

        if result.success:
            print(f"  ✅ API RESPONDED: Found LCCN: {result.lccn}")
        else:
            print(f"  ⚠️  API RESPONDED: No match found")
            print(f"     Error: {result.error}")
            print(f"     (This is OK - book may not be in Harvard catalog)")
    except Exception as e:
        print(f"  ❌ API CALL FAILED: {str(e)}")

    print()
    print("=" * 60)
    print("  TEST COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    test_harvard_connection()
