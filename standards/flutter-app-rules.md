# Flutter App Release Standards

This document establishes the release-readiness checklist for all Flutter Apps.

## Checklist

### 1. Version Bump (Mandatory)
- The version string in `pubspec.yaml` (e.g. `version: 1.0.0+1`) must be incremented.

### 2. Localization (Mandatory)
- If localization is used, running `flutter gen-l10n` must succeed without errors.

### 3. Release Changelog (Mandatory)
- `CHANGELOG.md` must contain an entry corresponding to the `pubspec.yaml` current version.

### 4. Tests and Coverage (Recommended)
- All unit and widget tests must pass.
- Coverage reports should be generated and verified where configured.
