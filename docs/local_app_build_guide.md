# Local App Build Guide

This guide records the current local packaging situation relative to the `main` branch.

---

## Current State On `main`

The `main` branch baseline does not currently include committed platform build scripts such as `build_mac.sh` or `build_windows.bat`.

It also does not include a checked-in local packaging workflow that can be followed directly from the branch contents alone.

---

## What Is Reliably Supported Here

What is fully represented on `main` is:

- running the application from source
- maintaining the repository as the development source of truth

---

## Packaging Guidance

If packaging automation exists in another branch or in separate release engineering materials, document it there instead of claiming it exists on `main`.

For the `main` branch docs, the safe and accurate statement is:

- source execution is documented here
- local packaging automation is not currently committed on `main`

---

## Recommended Workflow

1. Treat `main` as the source-of-truth branch.
2. Verify behavior by running from source.
3. Keep packaging instructions only where the actual packaging assets exist.

---

## See Also

- [installation_guide.md](installation_guide.md)
- [contribution_guide.md](contribution_guide.md)
