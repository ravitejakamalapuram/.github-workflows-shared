# Security Best Practices

## Input Handling in GitHub Actions

### ✅ Recommended: Environment Variables

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

### ⚠️ Not Recommended: Direct Interpolation

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

All composite actions and reusable workflows in this repository should use environment variables for inputs in shell steps. If an action still relies on direct `${{ inputs.* }}` interpolation inside `run:` blocks, it should be treated as a fix-it-later security concern and corrected when that action is next modified.

## Recommendations

### For New Actions

- Always use environment variables for inputs
- Never use `eval` with user inputs
- Prefer `jq` over `python3` for JSON parsing in CI scripts where practical
- Map all inputs to env vars in the `env:` block
- Avoid disabling SSL verification in production workflows unless the environment requires it

### For Existing Actions

Any remaining warnings should be resolved when those actions are modified for other reasons. In the meantime, prefer migrating them to environment-variable usage as part of normal maintenance rather than leaving raw interpolation in place.

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
