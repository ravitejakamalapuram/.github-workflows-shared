# 📦 Migration Guide

This guide helps you migrate existing projects to use the centralized GitHub Actions workflows.

## 🎯 Overview

Migration is **incremental and safe**:
- ✅ No breaking changes to your code
- ✅ Migrate one workflow at a time
- ✅ Test before committing
- ✅ Rollback anytime

## 📋 Pre-Migration Checklist

- [ ] Backup existing workflows (copy `.github/workflows/` to safe location)
- [ ] Review current workflow functionality
- [ ] Identify which composite actions you need
- [ ] Check for custom build steps
- [ ] Document any project-specific requirements

## 🔧 Migration Steps

### Step 1: Choose Your Approach

**Option A: Full Reusable Workflow** (Recommended)
- Replace entire workflow with reusable workflow
- Simplest approach, least maintenance
- Good for standard projects

**Option B: Composite Actions** (More Control)
- Use individual composite actions in your workflow
- More flexibility for custom requirements
- Good for complex projects with unique needs

### Step 2: Migrate Android Project

#### Before (TelePort example):
```yaml
# .github/workflows/ci.yml - 43 lines
name: CI
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test-and-validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up JDK 17
        uses: actions/setup-java@v4
        with:
          distribution: 'zulu'
          java-version: '17'
          cache: 'gradle'
      - name: Setup Android SDK
        uses: android-actions/setup-android@v3
      - name: Grant execute permission for gradlew
        run: chmod +x gradlew
      - name: Run Screenshots and Unit Tests
        run: ./gradlew test
      - name: Validate Chrome Extension Manifest
        run: |
          if ! jq empty 'chrome-extension/manifest.json' > /dev/null 2>&1; then
            echo "Error: manifest.json is invalid"
            exit 1
          fi
```

#### After (Option A - Reusable Workflow):
```yaml
# .github/workflows/ci.yml - 17 lines ✨
name: CI
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  workflow_dispatch:

jobs:
  android-ci:
    uses: ravitejakamalapuram/.github-workflows-shared/.github/workflows/android-ci.yml@main
    with:
      java-version: '17'
      run-tests: true
      validate-extension: true
      extension-dir: 'chrome-extension'
```

#### After (Option B - Composite Actions):
```yaml
# .github/workflows/ci.yml - 25 lines
name: CI
on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Setup Android
        uses: ravitejakamalapuram/.github-workflows-shared/composite-actions/android/setup@main
        with:
          java-version: '17'
      
      - name: Run Tests
        uses: ravitejakamalapuram/.github-workflows-shared/composite-actions/android/test@main
      
      - name: Validate Extension
        uses: ravitejakamalapuram/.github-workflows-shared/composite-actions/chrome-extension/validate@main
        with:
          extension-dir: 'chrome-extension'
```

**Reduction**: 43 lines → 17 lines (60% reduction with Option A)

### Step 3: Migrate Flutter Project

#### Before (InvTrack example - 87 lines):
```yaml
jobs:
  ci-checks:
    runs-on: self-hosted
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
      - name: Verify Flutter installation
        run: flutter --version
      - name: Flutter Setup
        id: flutter_setup
        run: |
          flutter clean
          flutter pub get
          flutter gen-l10n
      # ... 60+ more lines
```

#### After:
```yaml
jobs:
  flutter-ci:
    uses: ravitejakamalapuram/.github-workflows-shared/.github/workflows/flutter-ci.yml@main
    with:
      flutter-channel: 'stable'
      runner-type: 'self-hosted'
      run-analyzer: true
      run-tests: true
      architecture-checks: true
```

**Reduction**: 87 lines → 19 lines (78% reduction)

### Step 4: Migrate Chrome Extension Project

#### Before (echokit example - 181 lines):
```yaml
jobs:
  validate:
    runs-on: ubuntu-latest
    # ... 40 lines
  lint:
    runs-on: ubuntu-latest
    # ... 25 lines
  unit:
    runs-on: ubuntu-latest
    # ... 20 lines
  smoke:
    runs-on: ubuntu-latest
    # ... 35 lines
```

#### After:
```yaml
jobs:
  extension-ci:
    uses: ravitejakamalapuram/.github-workflows-shared/.github/workflows/chrome-extension-ci.yml@main
    with:
      node-version: '20'
      extension-dir: 'extension'
      run-lint: true
      run-unit-tests: true
      run-e2e-tests: false
```

**Reduction**: 181 lines → 15 lines (92% reduction)

#### 🚀 Automated Onboarding for New/Existing Extensions
Rather than manually creating all config and workflow files, you can automate Chrome Web Store onboarding and CI/CD linking using our central onboarding script:

```bash
# In the root of your extension repository, run:
/Users/rkamalapuram/git-personal/.github-workflows-shared/scripts/onboard-extension.sh
```

This script will:
1. Auto-generate Chrome Extension boilerplate files (if starting from scratch).
2. Generate `CHROMEWEBSTORE.md` (listing metadata) and `PRIVACY.md` (privacy policy) with pre-filled permissions justifications based on your `manifest.json`.
3. Create a `.github/workflows/ci-cd.yml` workflow pointing to the centralized reusable workflows.
4. Package your extension into `initial-package.zip` and display a step-by-step checklist to guide you through Google API credentials, your first manual Web Store upload, and setting up repository secrets.

## ⚠️ Common Migration Challenges

### 1. Custom Build Steps

**Problem**: You have custom build steps not covered by actions.

**Solution**: Add custom steps before/after composite actions:

```yaml
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Android
        uses: ravitejakamalapuram/.github-workflows-shared/composite-actions/android/setup@main

      # Custom step
      - name: Generate Build Config
        run: ./scripts/generate-config.sh

      - name: Build APK
        uses: ravitejakamalapuram/.github-workflows-shared/composite-actions/android/build-apk@main
```

### 2. Project-Specific Secrets

**Problem**: Your project uses different secret names.

**Solution**: Map secrets in workflow:

```yaml
jobs:
  deploy:
    uses: ravitejakamalapuram/.github-workflows-shared/.github/workflows/android-cd.yml@main
    secrets:
      PLAY_SERVICE_ACCOUNT_KEY: ${{ secrets.MY_CUSTOM_SECRET_NAME }}
```

### 3. Self-Hosted Runners

**Problem**: You need self-hosted runners (e.g., for Flutter).

**Solution**: Specify runner type in inputs:

```yaml
jobs:
  flutter-ci:
    uses: ravitejakamalapuram/.github-workflows-shared/.github/workflows/flutter-ci.yml@main
    with:
      runner-type: 'self-hosted'  # or 'ubuntu-latest'
```

## ✅ Testing Your Migration

1. **Create a test branch**:
   ```bash
   git checkout -b migrate-to-centralized-actions
   ```

2. **Update workflow file**:
   - Replace old workflow with new one
   - Commit changes

3. **Push and create PR**:
   ```bash
   git add .github/workflows/
   git commit -m "Migrate to centralized GitHub Actions"
   git push origin migrate-to-centralized-actions
   ```

4. **Verify in PR**:
   - Check all jobs run successfully
   - Compare timing with old workflow
   - Verify artifacts are created correctly

5. **Merge when ready**:
   - Only merge after successful test
   - Keep backup of old workflow for 1-2 weeks

## 🔄 Rollback Plan

If something goes wrong:

```bash
# Restore old workflow
git checkout main -- .github/workflows/ci.yml
git commit -m "Rollback: Restore old workflow"
git push
```

## 📊 Migration Tracking

Track your migration progress:

- [ ] Android CI workflow migrated
- [ ] Android CD workflow migrated
- [ ] Flutter CI workflow migrated
- [ ] Flutter CD workflow migrated
- [ ] Chrome Extension CI workflow migrated
- [ ] Chrome Extension CD workflow migrated
- [ ] Tested all workflows in PR
- [ ] Documented custom steps
- [ ] Updated team documentation
- [ ] Removed backup workflows (after 2 weeks)

## 🚀 Next Steps

After successful migration:

1. **Monitor for issues** (first week)
2. **Document lessons learned**
3. **Share with team**
4. **Consider migrating other projects**
5. **Contribute improvements** back to central repo

## 💡 Tips

- ✅ Migrate one project at a time
- ✅ Start with simplest project first
- ✅ Test thoroughly before merging
- ✅ Keep old workflows as backup initially
- ✅ Update team documentation
- ❌ Don't migrate all projects at once
- ❌ Don't skip testing phase
- ❌ Don't delete old workflows immediately

## 🆘 Need Help?

- Check [Examples](examples/)
- Review [Contributing Guide](CONTRIBUTING.md)
- Open a [GitHub Discussion](https://github.com/YOUR_ORG/.github-workflows-shared/discussions)
- Contact the team

