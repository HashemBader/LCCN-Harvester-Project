"""
README_SIDEBAR_TESTS.md - Index and Guide for Sidebar Tab Testing Suite
"""

# LCCN Harvester - Sidebar Tabs Testing Suite

## Overview

Complete testing suite for all sidebar tabs and features in the LCCN Harvester GUI application.

This includes:
- **6 main tabs** (Dashboard, Targets, Settings, Harvest, Results, AI Agent)
- **3 utility buttons** (Shortcuts, Accessibility, Theme Toggle)
- **All features** (theme toggle, sidebar collapse, keyboard navigation)

---

## Files in This Suite

### 1. **test_sidebar_tabs.py** (650+ lines)
Automated unit tests using pytest framework.

**What it tests:**
- Tab creation and properties
- Tab switching functionality
- Theme toggle (dark ↔ light)
- Theme persistence
- Sidebar collapse/expand
- Accessibility attributes
- Status pill functionality

**How to run:**
```bash
cd tests
pytest test_sidebar_tabs.py -v
```

**Test count:** 30+ automated tests
**Execution time:** 45-60 seconds
**Pass rate target:** 100%

---

### 2. **test_sidebar_tabs_manual.py** (concise format)
Manual UI test cases with step-by-step instructions.

**What it covers:**
- TC_001-029: 29 comprehensive manual tests
- Each test has clear steps and expected results
- Covers all user workflows and edge cases

**How to use:**
1. Open the file in a text editor
2. Read the test case comments
3. Follow the steps manually in the GUI
4. Verify expected results
5. Document pass/fail

**Test count:** 29 manual tests
**Estimated time:** 2-3 hours
**Coverage:** All tabs, features, keyboard navigation, accessibility

---

### 3. **SIDEBAR_TESTS_DOCUMENTATION.md** (comprehensive guide)
Complete reference documentation for the testing suite.

**Includes:**
- Test organization and structure
- Detailed execution instructions
- Test coverage matrix
- Running tests in CI/CD
- Troubleshooting guide
- Test report template
- Maintenance guidelines

**Read this for:** Understanding the full testing strategy and best practices

---

### 4. **SIDEBAR_TESTS_SUMMARY.txt** (quick reference)
One-page summary of all tests and key information.

**Includes:**
- File descriptions
- Quick start instructions
- Test coverage overview
- Execution times
- Test results
- Next steps

**Read this for:** Quick overview and to find what you need

---

## Test Organization

### By Tab
- **Dashboard** (2 automated, 2 manual tests)
- **Targets** (1 automated, 3 manual tests)
- **Settings** (1 automated, 3 manual tests)
- **Harvest** (1 automated, 3 manual tests)
- **Results** (1 automated, 2 manual tests)
- **AI Agent** (1 automated, 2 manual tests)

### By Feature
- **Tab Navigation** - 8 tests
- **Theme Toggle** - 6 tests
- **Sidebar Collapse** - 4 tests
- **Accessibility** - 5 tests
- **Keyboard Shortcuts** - 3 tests
- **Error Handling** - 2 tests

### Total: 69+ test cases (40+ automated + 29 manual)

---

## Quick Start

### For Developers
```bash
# Run automated tests
pytest tests/test_sidebar_tabs.py -v

# Run specific test class
pytest tests/test_sidebar_tabs.py::TestThemeToggle -v

# Run with coverage
pytest tests/test_sidebar_tabs.py --cov=src.gui
```

### For QA / Testers
1. Read `SIDEBAR_TESTS_SUMMARY.txt` for overview
2. Open the GUI application
3. Follow manual test cases in `test_sidebar_tabs_manual.py`
4. Document results in test report (template in documentation)

### For CI/CD Integration
1. See `SIDEBAR_TESTS_DOCUMENTATION.md` for examples
2. Add pytest command to CI/CD pipeline
3. Set pass threshold to 100%
4. Report failures before merging

---

## Test Execution Times

| Type | Time | Count |
|------|------|-------|
| Automated | 45-60 sec | 30+ |
| Manual | 2-3 hours | 29 |
| **Combined** | **2.5-3.5 hours** | **69+** |

---

## Expected Results

### Automated Tests
- All 30+ tests should **PASS**
- No warnings or errors
- Execution completes in under 1 minute

### Manual Tests
- All 29 tests should **PASS**
- User should follow exact steps
- Document any deviations

### Coverage
- 100% of sidebar tabs covered
- All major features tested
- Accessibility verified
- Error cases handled

---

## Common Issues

### "Cannot find module" error
→ Ensure `src` is in Python path and dependencies installed
→ Run: `pip install -r requirements.txt`

### Tests hang or freeze
→ Check system resources
→ Ensure QApplication initialized properly
→ May need headless/xvfb on Linux

### Theme doesn't persist
→ Check `data/gui_settings.json` exists
→ Verify write permissions in data folder

### Tab switch is slow
→ Normal on low-resource systems
→ Check system performance
→ May require UI optimization

---

## Integration Checklist

- [ ] Run all automated tests
- [ ] Execute critical manual tests (TC_001-010, TC_016-020)
- [ ] Verify theme toggle works
- [ ] Test keyboard navigation
- [ ] Check accessibility compliance
- [ ] Document test results
- [ ] Review failures if any
- [ ] Sign off on release

---

## Maintenance Schedule

### Before Each Release
- Run full automated test suite
- Execute manual tests (minimum subset)
- Verify accessibility
- Update test documentation if needed

### After Bug Fixes
- Run tests related to the bug
- Run full test suite for regression
- Document fix in test report

### After Feature Additions
- Add new tests for new features
- Update test documentation
- Run full suite to check for regressions

---

## Files at a Glance

```
tests/
├── test_sidebar_tabs.py                 (Automated tests - 650+ lines)
├── test_sidebar_tabs_manual.py          (Manual test cases)
├── SIDEBAR_TESTS_DOCUMENTATION.md       (Comprehensive guide)
├── SIDEBAR_TESTS_SUMMARY.txt            (Quick reference - 1 page)
└── README_SIDEBAR_TESTS.md              (This file - overview)
```

---

## Questions?

1. **For test details** → Read `test_sidebar_tabs.py` docstrings
2. **For manual testing** → Follow `test_sidebar_tabs_manual.py`
3. **For comprehensive info** → Read `SIDEBAR_TESTS_DOCUMENTATION.md`
4. **For quick overview** → Read `SIDEBAR_TESTS_SUMMARY.txt`
5. **For best practices** → See documentation file

---

## Summary

This comprehensive testing suite ensures all sidebar tabs and features work correctly:

✅ **Automated tests** for quick regression testing  
✅ **Manual tests** for thorough UI validation  
✅ **Complete documentation** for reference and CI/CD  
✅ **69+ test cases** covering all functionality  
✅ **Accessibility testing** for WCAG compliance  
✅ **Keyboard navigation** testing  
✅ **Error handling** verification  

**Total estimated execution:** 2.5 - 3.5 hours (including manual)  
**Automated-only execution:** 45 - 60 seconds

---

**Created:** February 2026  
**For:** LCCN Harvester Project  
**Framework:** pytest + PyQt6  
**Status:** Ready for use

