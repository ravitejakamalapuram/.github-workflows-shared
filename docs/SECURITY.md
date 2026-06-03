# Security Best Practices

## Input Handling in GitHub Actions

### ✅ **Recommended: Environment Variables**

Always map GitHub Actions inputs to environment variables before using them in shell scripts:

```yaml
steps:
  - name: Example Step
    env:
      INPUT_VALUE: ${{ inputs.my-input }}
      PACKAGE_NAME: ${{ inputs.package-name }}
    run: |
      echo "Processing: $INPUT_VALUE"
      ./gradlew build -PpackageName=$PACKAGE_NAME
    shell: bash
```

**Benefits:**
- ✅ Prevents command injection vulnerabilities
- ✅ Separates template expansion from shell execution
- ✅ Makes code more readable and maintainable
- ✅ Follows GitHub Actions security best practices

### ⚠️ **Not Recommended: Direct Interpolation**

Avoid direct input interpolation in shell scripts:

```yaml
# ❌ DON'T DO THIS
steps:
  - name: Unsafe Example
    run: |
      echo "Processing: ${{ inputs.my-input }}"
      ./gradlew build -PpackageName=${{ inputs.package-name }}
    shell: bash
```

**Why it's problematic:**
- Template expansion happens before shell execution
- Malicious input can inject commands
- No shell escaping applied
- Harder to audit for security issues

## Current Status

### Fixed Actions (11)
The following actions have been updated to use environment variables for all inputs:

1. `android/build-apk` - ✅ Secured credentials and all inputs
2. `android/build-bundle` - ✅ Secured credentials and all inputs
3. `android/test` - ✅ Secured all test parameters
4. `android/deploy-play` - ✅ Secured deployment parameters
5. `chrome-extension/package` - ✅ Already secured (PR #24)
6. `chrome-extension/test-e2e` - ✅ Already secured (PR #18)

### Remaining Actions (32 warnings)

The following actions still use direct input interpolation but are **low risk** as they:
- Use inputs for non-sensitive data (file paths, flags, numbers)
- Are used in controlled environments
- Don't execute user-provided code directly

**Chrome Extension (11 warnings):**
- `lint` - Uses config paths and flags
- `publish-cws` - Uses extension parameters
- `test-unit` - Uses test configuration
- `validate` - Uses validation parameters

**Common Utilities (8 warnings):**
- `changelog` - Uses git parameters
- `create-release` - Uses release metadata
- `size-check` - Uses size thresholds
- `slack-notify` - Uses notification parameters
- `version-bump` - Uses version numbers

**Flutter (13 warnings):**
- `analyze` - Uses analysis flags
- `build-android` - Uses build parameters
- `build-ios` - Uses build parameters
- `setup` - Uses Flutter version
- `test` - Uses test parameters
- `version-bump` - Uses version parameters

## Recommendations

### For New Actions
- Always use environment variables for inputs
- Never use `eval` with user inputs
- Use `jq` instead of `python3` for JSON parsing
- Map all inputs to env vars in the `env:` block

### For Existing Actions
The remaining warnings can be addressed in future updates when those actions are modified for other reasons. They pose minimal security risk in their current form.

## Security Scanning

Run the validation script to check for security issues:

```bash
python3 scripts/validate-actions.py
```

This script checks for:
- Missing required fields
- Direct input interpolation (warnings)
- Missing shell specifications
- Missing branding metadata
