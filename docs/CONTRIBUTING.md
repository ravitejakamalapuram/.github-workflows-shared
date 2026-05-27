# 🤝 Contributing Guide

Thank you for contributing to our centralized GitHub Actions repository!

## 📋 Table of Contents

- [Getting Started](#getting-started)
- [Adding New Actions](#adding-new-actions)
- [Testing](#testing)
- [Pull Request Process](#pull-request-process)
- [Style Guide](#style-guide)

## 🚀 Getting Started

1. **Fork the repository**
2. **Clone your fork**:
   ```bash
   git clone https://github.com/YOUR_USERNAME/.github-workflows-shared.git
   cd .github-workflows-shared
   ```
3. **Create a feature branch**:
   ```bash
   git checkout -b feature/add-new-action
   ```

## ➕ Adding New Actions

### Composite Action Structure

All composite actions must follow this structure:

```
composite-actions/
└── category/
    └── action-name/
        └── action.yml
```

### Minimum Requirements

Every composite action MUST have:

1. **Clear name and description**
2. **Input parameters** with descriptions and defaults
3. **Output parameters** (if applicable)
4. **Shell specified** for all `run` steps
5. **Branding** (icon and color)
6. **Error handling** (fail gracefully)

### Template

Use this template for new composite actions:

```yaml
name: 'Action Name'
description: 'Clear description of what this action does'
author: 'Your Organization'

inputs:
  input-name:
    description: 'Description of this input'
    required: false
    default: 'default-value'

outputs:
  output-name:
    description: 'Description of this output'
    value: ${{ steps.step-id.outputs.value }}

runs:
  using: 'composite'
  steps:
    - name: Descriptive Step Name
      id: step-id
      run: |
        echo "Your script here"
      shell: bash

branding:
  icon: 'package'  # From https://feathericons.com/
  color: 'blue'    # blue, green, yellow, orange, red, purple
```

### Best Practices

#### ✅ DO

- Use clear, descriptive names
- Provide sensible defaults
- Add extensive input validation
- Include error messages with context
- Use `::group::` for organized output
- Add to `$GITHUB_STEP_SUMMARY` for visibility
- Handle edge cases gracefully
- Document all inputs/outputs

#### ❌ DON'T

- Hardcode values (use inputs)
- Assume tools are installed
- Use deprecated actions
- Skip error handling
- Leave secrets in outputs
- Use absolute paths
- Assume specific directory structure

### Example: Good Action

```yaml
name: 'Setup Environment'
description: 'Sets up build environment with validation'

inputs:
  tool-version:
    description: 'Version of the tool to install'
    required: false
    default: 'latest'

outputs:
  installed-version:
    description: 'Actually installed version'
    value: ${{ steps.install.outputs.version }}

runs:
  using: 'composite'
  steps:
    - name: Validate Input
      run: |
        if [ -z "${{ inputs.tool-version }}" ]; then
          echo "::error::tool-version cannot be empty"
          exit 1
        fi
      shell: bash
    
    - name: Install Tool
      id: install
      run: |
        echo "::group::Installing tool v${{ inputs.tool-version }}"
        
        # Installation logic here
        ACTUAL_VERSION=$(get_installed_version)
        
        echo "version=$ACTUAL_VERSION" >> $GITHUB_OUTPUT
        echo "✅ Installed: $ACTUAL_VERSION"
        echo "::endgroup::"
        
        echo "📦 Tool Version: $ACTUAL_VERSION" >> $GITHUB_STEP_SUMMARY
      shell: bash

branding:
  icon: 'download'
  color: 'green'
```

## 🧪 Testing

### Test Your Action Locally

Create a test workflow in a separate repository:

```yaml
name: Test New Action
on: workflow_dispatch

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Test Action
        uses: YOUR_ORG/.github-workflows-shared/composite-actions/category/action@feature-branch
        with:
          input-param: 'test-value'
```

### Testing Checklist

- [ ] Action runs without errors
- [ ] All inputs work as expected
- [ ] Outputs are correctly set
- [ ] Error cases are handled
- [ ] Step summary is useful
- [ ] Branding displays correctly
- [ ] Works on all target platforms (ubuntu/macos/windows)

## 📝 Pull Request Process

1. **Update Documentation**:
   - Add action to README.md
   - Update relevant config files
   - Add usage examples

2. **Create PR with**:
   - Clear title: `feat: add XYZ action` or `fix: improve ABC action`
   - Description of what changed
   - Link to test workflow run
   - Breaking changes (if any)

3. **PR Template**:
   ```markdown
   ## Description
   Brief description of changes

   ## Type of Change
   - [ ] New composite action
   - [ ] Bug fix
   - [ ] Documentation update
   - [ ] Breaking change

   ## Testing
   - [ ] Tested locally
   - [ ] Test workflow passed: [link]
   - [ ] Updated documentation

   ## Checklist
   - [ ] Code follows style guide
   - [ ] Self-review completed
   - [ ] Documentation updated
   - [ ] No breaking changes (or documented)
   ```

4. **Review Process**:
   - Wait for automated checks
   - Address review comments
   - Get approval from maintainer
   - Squash and merge

## 🎨 Style Guide

### YAML Formatting

- Use 2-space indentation
- Quote strings that might be interpreted as booleans/numbers
- Use `|` for multi-line strings
- Add comments for complex logic

```yaml
# Good
inputs:
  version:
    description: 'Version to install'
    required: false
    default: '1.0.0'

# Bad
inputs:
  version:
    description: Version to install
    required: false
    default: 1.0.0  # Unquoted number
```

### Shell Scripts

- Always specify `shell: bash`
- Use `set -e` for fail-fast behavior
- Quote variables: `"${{ inputs.var }}"`
- Use `echo "::error::"` for errors
- Use `echo "::warning::"` for warnings

```bash
# Good
run: |
  set -e
  VERSION="${{ inputs.version }}"
  if [ -z "$VERSION" ]; then
    echo "::error::Version is required"
    exit 1
  fi
shell: bash

# Bad
run: |
  VERSION=${{ inputs.version }}  # Unquoted
  if [ -z $VERSION ]; then       # Unquoted
    echo "Error"                  # No ::error::
    exit 1
  fi
```

### Commit Messages

Follow Conventional Commits:

- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation only
- `style:` - Code style (formatting)
- `refactor:` - Code refactoring
- `test:` - Adding tests
- `chore:` - Maintenance tasks

Examples:
```
feat: add Flutter iOS build action
fix: correct version detection in Android setup
docs: update migration guide with Flutter examples
```

## 🏷️ Versioning

We use semantic versioning:

- **Major** (v1.0.0 → v2.0.0): Breaking changes
- **Minor** (v1.0.0 → v1.1.0): New features, backward compatible
- **Patch** (v1.0.0 → v1.0.1): Bug fixes

### When to Bump

- **Major**: Change input/output names, remove features
- **Minor**: Add new inputs (with defaults), new actions
- **Patch**: Fix bugs, improve error messages

## 📚 Documentation Standards

### Action Documentation

Every action must document:

1. **Purpose**: What does it do?
2. **Inputs**: All parameters with types and defaults
3. **Outputs**: What data does it provide?
4. **Example**: Real-world usage
5. **Requirements**: Dependencies, permissions

### README Updates

When adding an action:

1. Add to main README.md table
2. Add usage example
3. Update configuration if needed

## 🔒 Security

- Never commit secrets or credentials
- Validate all user inputs
- Use `secrets` context for sensitive data
- Don't log sensitive information
- Review dependencies regularly

## 💬 Getting Help

- **Questions**: Open a GitHub Discussion
- **Bug Reports**: Create an Issue
- **Feature Requests**: Create an Issue with `enhancement` label

## 📜 License

By contributing, you agree that your contributions will be licensed under the same license as this project (MIT).

---

Thank you for making our CI/CD better! 🎉

