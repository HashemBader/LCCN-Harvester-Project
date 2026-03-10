# WCAG Accessibility Notes (Self-Assessed)

This app includes accessibility improvements aimed at WCAG 2.1 AA style usability for desktop users, especially keyboard-first users.

## What Is Already WCAG-Friendly

- Keyboard operation:
  - Main navigation and actions are available from keyboard shortcuts.
  - Standard editing shortcuts are preserved in text fields:
    - `Cmd/Ctrl+A` select all
    - `Cmd/Ctrl+C` copy
    - `Cmd/Ctrl+V` paste
- Focus visibility:
  - Buttons and key form controls have clear focus styling in the V2 stylesheet.
- Programmatic labels:
  - Major controls use accessible names/descriptions so screen readers can announce intent.
- Discoverability:
  - A shortcuts dialog is available and searchable.
  - The dialog auto-detects macOS vs Windows/Linux and shows the right modifier key labels.
- Readability:
  - Key status and helper labels were updated for stronger contrast and simpler wording.

## Important Limit

This is **not** a formal legal certification.

A real conformance claim usually requires a structured accessibility audit (manual + assistive tech testing), and typically produces a VPAT/ACR or equivalent report.

## If You Want Formal Certification

Use this workflow per release:

1. Run the internal self-check script:
   - `python3 wcag_self_check.py --write docs/release/WCAG_SELF_CHECK_REPORT.md`
2. Perform manual tests with actual users and assistive technology:
   - Keyboard-only testing
   - VoiceOver/NVDA screen-reader pass
   - Zoom/reflow checks
   - Contrast checks in real screens
3. Engage a third-party accessibility auditor for a formal report.
4. Publish that report as your official conformance artifact.

## Suggested Manual Test Matrix

- Keyboard only: Can complete input, settings, and harvest workflow without mouse.
- Screen reader: Primary controls are announced with meaningful names.
- Text editing: Copy/paste/select-all works naturally in all input widgets.
- Visual contrast: Primary text, disabled states, and focus outlines remain readable.

