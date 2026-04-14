# WCAG Accessibility Notes

This document summarizes the repository's current accessibility work. It is a self-assessment, not a formal certification.

---

## Current Accessibility-Oriented Features

- Keyboard-accessible primary navigation and harvest actions
- Visible focus styling in the Qt stylesheet
- Accessible names and descriptions on core controls
- Shortcut discoverability through the help UI
- Platform-aware shortcut labels
- Readable status and helper text across the main workflow

---

## What This Is Not

This repository does not ship with a formal conformance statement, VPAT, or third-party accessibility audit report.

Formal WCAG conformance requires manual assistive-technology testing and independent review.

---

## Recommended Manual Verification

For release readiness, manually test:

- Keyboard-only navigation
- Shortcut discoverability
- Focus visibility
- Readability in both light and dark themes
- Screen-reader labeling on core controls

---

## Scope Note

These notes apply to the current desktop application in this repository. They should be reviewed again whenever major UI changes are made.
