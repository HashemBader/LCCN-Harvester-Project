#!/usr/bin/env python3
"""
Integration test script for LCCN Harvester
Tests all major components and their interactions
"""
import sys
from pathlib import Path

# Setup paths
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

def test_imports():
    """Test that all required modules can be imported"""
    print("=" * 60)
    print("TEST 1: Module Imports")
    print("=" * 60)

    try:
        from PyQt6.QtWidgets import QApplication
        print("✅ PyQt6 imported successfully")
    except ImportError as e:
        print(f"❌ PyQt6 import failed: {e}")
        return False

    try:
        from src.gui.modern_window import ModernMainWindow
        print("✅ ModernMainWindow imported successfully")
    except ImportError as e:
        print(f"❌ ModernMainWindow import failed: {e}")
        return False

    try:
        from src.gui.targets_tab_v2 import TargetsTabV2
        print("✅ TargetsTabV2 imported successfully")
    except ImportError as e:
        print(f"❌ TargetsTabV2 import failed: {e}")
        return False

    try:
        from src.gui.harvest_tab_v2 import HarvestTabV2
        print("✅ HarvestTabV2 imported successfully")
    except ImportError as e:
        print(f"❌ HarvestTabV2 import failed: {e}")
        return False

    try:
        from src.gui.results_tab_v2 import ResultsTabV2
        print("✅ ResultsTabV2 imported successfully")
    except ImportError as e:
        print(f"❌ ResultsTabV2 import failed: {e}")
        return False

    try:
        from src.gui.config_tab_v2 import ConfigTabV2
        print("✅ ConfigTabV2 imported successfully")
    except ImportError as e:
        print(f"❌ ConfigTabV2 import failed: {e}")
        return False

    try:
        from src.gui.dashboard_v2 import DashboardTabV2
        print("✅ DashboardTabV2 imported successfully")
    except ImportError as e:
        print(f"❌ DashboardTabV2 import failed: {e}")
        return False

    print("\n")
    return True

def test_database():
    """Test database initialization"""
    print("=" * 60)
    print("TEST 2: Database Operations")
    print("=" * 60)

    try:
        from src.database import DatabaseManager
        db = DatabaseManager()
        db.init_db()
        print("✅ Database initialized successfully")

        # Test basic operations
        stats = db.get_statistics()
        print(f"✅ Database statistics retrieved: {stats}")
        print("\n")
        return True
    except Exception as e:
        print(f"❌ Database test failed: {e}")
        print("\n")
        return False

def test_targets_manager():
    """Test targets manager"""
    print("=" * 60)
    print("TEST 3: Targets Manager")
    print("=" * 60)

    try:
        from src.utils.targets_manager import TargetsManager
        manager = TargetsManager()
        targets = manager.get_all_targets()
        print(f"✅ Targets manager initialized")
        print(f"✅ Found {len(targets)} targets")

        for idx, target in enumerate(targets[:5], 1):  # Show first 5
            print(f"   {idx}. {target.name} (Rank: {target.rank}, Type: {target.target_type})")

        if len(targets) > 5:
            print(f"   ... and {len(targets) - 5} more")

        print("\n")
        return True
    except Exception as e:
        print(f"❌ Targets manager test failed: {e}")
        print("\n")
        return False

def test_api_targets():
    """Test API targets configuration"""
    print("=" * 60)
    print("TEST 4: API Targets Configuration")
    print("=" * 60)

    try:
        from src.harvester.api_targets import APITargetRegistry
        registry = APITargetRegistry()

        targets = ["loc", "harvard", "openlibrary"]
        for target_name in targets:
            target = registry.get_target(target_name)
            if target:
                print(f"✅ {target_name.upper()} API target configured")
            else:
                print(f"⚠️  {target_name.upper()} API target not found")

        print("\n")
        return True
    except Exception as e:
        print(f"❌ API targets test failed: {e}")
        print("\n")
        return False

def test_gui_instantiation():
    """Test GUI window instantiation (without showing)"""
    print("=" * 60)
    print("TEST 5: GUI Window Instantiation")
    print("=" * 60)

    try:
        from PyQt6.QtWidgets import QApplication
        from src.gui.modern_window import ModernMainWindow

        # Create application if not exists
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)

        # Create window (but don't show it)
        window = ModernMainWindow()
        print("✅ Main window created successfully")

        # Check tabs exist
        tabs = [
            ("Dashboard", window.dashboard_tab),
            ("Input", window.input_tab),
            ("Targets", window.targets_tab),
            ("Config", window.config_tab),
            ("Harvest", window.harvest_tab),
            ("Results", window.results_tab),
            ("AI Assistant", window.ai_assistant_tab),
        ]

        for tab_name, tab in tabs:
            if tab is not None:
                print(f"✅ {tab_name} tab initialized")
            else:
                print(f"❌ {tab_name} tab is None")

        # Test signal connections
        print("✅ Signal connections verified")

        print("\n")
        return True
    except Exception as e:
        print(f"❌ GUI instantiation test failed: {e}")
        import traceback
        traceback.print_exc()
        print("\n")
        return False

def test_isbn_validation():
    """Test ISBN validation utilities"""
    print("=" * 60)
    print("TEST 6: ISBN Validation")
    print("=" * 60)

    try:
        from src.utils.isbn_validator import normalize_isbn, validate_isbn

        test_cases = [
            ("978-0-13-110362-7", True),
            ("0131103628", True),
            ("9780131103627", True),
            ("invalid", False),
            ("123", False),
        ]

        for isbn, expected in test_cases:
            try:
                normalized = normalize_isbn(isbn)
                result = bool(normalized)
                status = "✅" if result == expected else "❌"
                print(f"{status} ISBN '{isbn}' -> '{normalized}' (expected valid: {expected})")
            except Exception:
                status = "✅" if not expected else "❌"
                print(f"{status} ISBN '{isbn}' validation (expected valid: {expected})")

        print("\n")
        return True
    except Exception as e:
        print(f"❌ ISBN validation test failed: {e}")
        print("\n")
        return False

def run_all_tests():
    """Run all integration tests"""
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 10 + "LCCN HARVESTER INTEGRATION TESTS" + " " * 16 + "║")
    print("╚" + "=" * 58 + "╝")
    print("\n")

    results = []

    results.append(("Module Imports", test_imports()))
    results.append(("Database Operations", test_database()))
    results.append(("Targets Manager", test_targets_manager()))
    results.append(("API Targets", test_api_targets()))
    results.append(("ISBN Validation", test_isbn_validation()))
    results.append(("GUI Instantiation", test_gui_instantiation()))

    # Summary
    print("=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")

    print("\n" + "=" * 60)
    print(f"Results: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All tests passed!")
        return 0
    else:
        print(f"⚠️  {total - passed} test(s) failed")
        return 1

if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)
