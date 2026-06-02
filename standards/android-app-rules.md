# Android App Release Standards

This document establishes the release-readiness checklist for all Android Apps.

## Checklist

### 1. Version Bump (Mandatory)
- The Gradle version code (`versionCode`) and version name (`versionName`) must be incremented for any release.

### 2. Signing Credentials (Mandatory)
- Keystore credentials (alias, password, key password) must be configured in environment variables or GitHub secrets for production builds.

### 3. Release Changelog (Mandatory)
- `CHANGELOG.md` must be present and contain an entry for the version code/name release.

### 4. Build Size Check (Recommended)
- The resulting Android App Bundle (`.aab`) should be size-verified to avoid exceeding Google Play's 150MB compressed download size limit.
