# 🔧 Centralized GitHub Actions Workflows

A centralized repository of reusable GitHub Actions workflows and composite actions for multi-project development. Supports Android, Flutter, and Chrome Extension projects with consistent CI/CD patterns.

## 📋 Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Available Actions](#available-actions)
- [Configuration](#configuration)
- [Migration Guide](#migration-guide)
- [Contributing](#contributing)

## 🎯 Overview

This repository provides:
- ✅ **Reusable Workflows** - Complete CI/CD pipelines ready to use
- ✅ **Composite Actions** - Modular building blocks for custom workflows
- ✅ **Consistent Quality** - Same standards across all projects
- ✅ **Easy Maintenance** - Fix once, benefit everywhere
- ✅ **Flexible Configuration** - Customize for your needs

### Benefits

| Feature | Before | After | Improvement |
|---------|--------|-------|-------------|
| **YAML Lines** | ~350 | ~65 | **81% reduction** |
| **Code Duplication** | ~70% | ~5% | **93% less** |
| **Time to Add Project** | 2-4 hours | 15 min | **88% faster** |
| **Maintenance** | Per-project | Centralized | **Instant propagation** |

## 🚀 Quick Start

### 1. Use in Your Project

Add this to your workflow file (e.g., `.github/workflows/ci.yml`):

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  # For Android projects
  android-ci:
    uses: YOUR_ORG/.github-workflows-shared/.github/workflows/android-ci.yml@main
    with:
      java-version: '17'
      run-tests: true
```

### 2. Using Composite Actions

For more control, use composite actions directly:

```yaml
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Setup Android
        uses: YOUR_ORG/.github-workflows-shared/composite-actions/android/setup@main
        with:
          java-version: '17'
      
      - name: Run Tests
        uses: YOUR_ORG/.github-workflows-shared/composite-actions/android/test@main
```

## 📦 Available Actions

### Android

| Action | Description | Usage |
|--------|-------------|-------|
| `android/setup` | Setup JDK + Android SDK | [Docs](composite-actions/android/setup/action.yml) |
| `android/test` | Run unit tests | [Docs](composite-actions/android/test/action.yml) |
| `android/build-apk` | Build APK | [Docs](composite-actions/android/build-apk/action.yml) |
| `android/build-bundle` | Build AAB | [Docs](composite-actions/android/build-bundle/action.yml) |
| `android/deploy-play` | Deploy to Play Store | [Docs](composite-actions/android/deploy-play/action.yml) |

### Flutter

| Action | Description | Usage |
|--------|-------------|-------|
| `flutter/setup` | Setup Flutter SDK | [Docs](composite-actions/flutter/setup/action.yml) |
| `flutter/analyze` | Run analyzer + arch checks | [Docs](composite-actions/flutter/analyze/action.yml) |
| `flutter/test` | Run tests with coverage | [Docs](composite-actions/flutter/test/action.yml) |
| `flutter/build-android` | Build Android (APK/AAB) | [Docs](composite-actions/flutter/build-android/action.yml) |
| `flutter/build-ios` | Build iOS | [Docs](composite-actions/flutter/build-ios/action.yml) |

### Chrome Extension

| Action | Description | Usage |
|--------|-------------|-------|
| `chrome-extension/validate` | Validate manifest & files | [Docs](composite-actions/chrome-extension/validate/action.yml) |
| `chrome-extension/lint` | ESLint checks | [Docs](composite-actions/chrome-extension/lint/action.yml) |
| `chrome-extension/test-unit` | Run unit tests | [Docs](composite-actions/chrome-extension/test-unit/action.yml) |
| `chrome-extension/test-e2e` | Playwright E2E tests | [Docs](composite-actions/chrome-extension/test-e2e/action.yml) |
| `chrome-extension/package` | Create ZIP package | [Docs](composite-actions/chrome-extension/package/action.yml) |
| `chrome-extension/publish-cws` | Publish to Chrome Web Store | [Docs](composite-actions/chrome-extension/publish-cws/action.yml) |

### Common Utilities

| Action | Description | Usage |
|--------|-------------|-------|
| `common/changelog` | Generate changelog | [Docs](composite-actions/common/changelog/action.yml) |
| `common/version-bump` | Semantic versioning | [Docs](composite-actions/common/version-bump/action.yml) |
| `common/create-release` | Create GitHub release | [Docs](composite-actions/common/create-release/action.yml) |
| `validation/detect-changes` | Path-based change detection | [Docs](composite-actions/validation/detect-changes/action.yml) |

## ⚙️ Configuration

Configuration defaults are provided in `config/`:

- `android.json` - Android build settings
- `flutter.json` - Flutter project settings
- `extension.json` - Chrome Extension settings
- `runners.json` - Runner selection & caching

Override in your workflow:

```yaml
- uses: YOUR_ORG/.github-workflows-shared/composite-actions/android/setup@main
  with:
    java-version: '21'  # Override default (17)
    gradle-cache: 'false'
```

## 📚 Documentation

- [Migration Guide](docs/MIGRATION.md) - Move existing projects
- [Contributing Guide](docs/CONTRIBUTING.md) - Add new actions
- [Examples](docs/examples/) - Real-world usage examples

## 🎓 Examples

See `docs/examples/` for complete workflow examples:
- [Android App](docs/examples/android-example.yml)
- [Flutter App](docs/examples/flutter-example.yml)
- [Chrome Extension](docs/examples/extension-example.yml)

## 🔄 Version Pinning

Always pin to a specific version in production:

```yaml
# Recommended: Pin to tag
uses: YOUR_ORG/.github-workflows-shared/composite-actions/android/setup@v1.0.0

# Development: Use main branch
uses: YOUR_ORG/.github-workflows-shared/composite-actions/android/setup@main
```

## 🤝 Contributing

See [CONTRIBUTING.md](docs/CONTRIBUTING.md) for guidelines.

## 📝 License

MIT License - see LICENSE file for details.

## 🙋 Support

- **Issues**: [GitHub Issues](https://github.com/YOUR_ORG/.github-workflows-shared/issues)
- **Discussions**: [GitHub Discussions](https://github.com/YOUR_ORG/.github-workflows-shared/discussions)

---

Made with ❤️ for consistent CI/CD across projects

