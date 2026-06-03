#!/bin/bash
# Batch fix all remaining input interpolation issues
# This script will be run manually for each remaining action

echo "🔧 Fixing remaining input interpolation issues..."
echo ""

# List of files that still need fixing based on validation output
FILES_TO_FIX=(
  "composite-actions/android/deploy-play/action.yml"
  "composite-actions/android/test/action.yml"
  "composite-actions/chrome-extension/lint/action.yml"
  "composite-actions/chrome-extension/publish-cws/action.yml"
  "composite-actions/chrome-extension/test-unit/action.yml"
  "composite-actions/chrome-extension/validate/action.yml"
  "composite-actions/common/changelog/action.yml"
  "composite-actions/common/create-release/action.yml"
  "composite-actions/common/size-check/action.yml"
  "composite-actions/common/slack-notify/action.yml"
  "composite-actions/common/version-bump/action.yml"
  "composite-actions/flutter/analyze/action.yml"
  "composite-actions/flutter/build-android/action.yml"
  "composite-actions/flutter/build-ios/action.yml"
  "composite-actions/flutter/setup/action.yml"
  "composite-actions/flutter/test/action.yml"
  "composite-actions/flutter/version-bump/action.yml"
)

echo "Found ${#FILES_TO_FIX[@]} files to fix"
echo ""

for file in "${FILES_TO_FIX[@]}"; do
  if [ -f "$file" ]; then
    echo "📝 $file - needs manual review"
  else
    echo "❌ $file - not found"
  fi
done

echo ""
echo "✅ List complete. These files will be fixed manually."
