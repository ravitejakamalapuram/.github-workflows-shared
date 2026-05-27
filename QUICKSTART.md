# 🚀 Quick Start Guide

Get started with centralized GitHub Actions in 5 minutes!

## For Android Projects

```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: YOUR_ORG/.github-workflows-shared/composite-actions/android/setup@main
        with:
          java-version: '17'
      - uses: YOUR_ORG/.github-workflows-shared/composite-actions/android/test@main
```

## For Flutter Projects

```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]

jobs:
  build:
    runs-on: self-hosted  # or ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: YOUR_ORG/.github-workflows-shared/composite-actions/flutter/setup@main
      - uses: YOUR_ORG/.github-workflows-shared/composite-actions/flutter/analyze@main
      - uses: YOUR_ORG/.github-workflows-shared/composite-actions/flutter/test@main
```

## For Chrome Extensions

```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - run: npm ci
      - uses: YOUR_ORG/.github-workflows-shared/composite-actions/chrome-extension/validate@main
      - uses: YOUR_ORG/.github-workflows-shared/composite-actions/chrome-extension/lint@main
```

## Common Tasks

### Create Release
```yaml
- uses: YOUR_ORG/.github-workflows-shared/composite-actions/common/version-bump@main
  id: version
- uses: YOUR_ORG/.github-workflows-shared/composite-actions/common/create-release@main
  with:
    tag-name: ${{ steps.version.outputs.new-tag }}
```

### Generate Changelog
```yaml
- uses: YOUR_ORG/.github-workflows-shared/composite-actions/common/changelog@main
  with:
    output-file: 'CHANGELOG.md'
```

### Detect Changes
```yaml
- uses: YOUR_ORG/.github-workflows-shared/composite-actions/validation/detect-changes@main
  id: changes
- name: Build Android
  if: steps.changes.outputs.android-changed == 'true'
  run: ./gradlew build
```

## Next Steps

1. 📖 Read the [Full Documentation](README.md)
2. 🔄 Follow the [Migration Guide](docs/MIGRATION.md)
3. 💡 Check [Complete Examples](docs/examples/)
4. 🤝 Learn to [Contribute](docs/CONTRIBUTING.md)

## Need Help?

- [GitHub Issues](https://github.com/YOUR_ORG/.github-workflows-shared/issues)
- [Discussions](https://github.com/YOUR_ORG/.github-workflows-shared/discussions)

---

**Remember**: Replace `YOUR_ORG` with your actual GitHub organization name!
