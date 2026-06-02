# Chrome Extension Release Standards

This document establishes the release-readiness checklist for all Chrome Extensions. These checks are programmatically validated during CI/CD execution and must pass for a PR to be merged.

## Checklist

### 1. Manifest Configuration (Mandatory)
- `manifest.json` must exist in the root or designated subdirectory (e.g. `extension/` or `chrome-extension/`).
- Must use **Manifest Version 3** (`"manifest_version": 3`).
- The version string (e.g. `1.0.0`) must be bumped if introducing a release change.

### 2. Release Changelog (Mandatory)
- `CHANGELOG.md` must contain an entry corresponding to the manifest's current version (e.g., `## [1.0.0] - 2026-06-01` or similar).

### 3. Store Listing Copy (Mandatory)
- `CHROMEWEBSTORE.md` must contain the complete details for the dashboard listing.
- Must **not** contain template placeholders such as `[REQUIRED]` or `[RECOMMENDED]`.
- Must document justifications for every permission requested in the manifest.

### 4. Graphic Assets & Screenshots (Recommended)
- All declared icons in manifest (e.g. `16x16`, `48x48`, `128x128`) must exist on disk and be valid PNG files.
- All store listing screenshots or promo images referenced in `CHROMEWEBSTORE.md` must be checked into the repository and be of correct size/dimensions.

### 5. Privacy Policy (Mandatory)
- `PRIVACY.md` must exist in the repository root and be fully populated (no placeholders).
