#!/usr/bin/env bash

# ==============================================================================
# 🚀 Chrome Extension Onboarding Script
# ==============================================================================
# Standardizes and automates the onboarding process for Chrome Extension projects.
# Generates boilerplate, metadata, privacy files, packages, and guides setup.
# ==============================================================================

set -euo pipefail

# --- Color Definitions ---
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# --- Help Menu ---
show_help() {
  echo -e "${BOLD}Usage:${NC} $0 [target_directory]"
  echo -e "  If target_directory is omitted, the current directory will be used."
  exit 0
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  show_help
fi

# --- Target Directory Configuration ---
TARGET_DIR="${1:-.}"
export TARGET_DIR
echo -e "${BLUE}${BOLD}====================================================${NC}"
echo -e "${BLUE}${BOLD}    Chrome Extension Onboarding & CI/CD Wizard      ${NC}"
echo -e "${BLUE}${BOLD}====================================================${NC}"
echo -e "Target directory: ${BOLD}$TARGET_DIR${NC}"

# Detect extension directory structure
if [ -f "$TARGET_DIR/manifest.json" ]; then
  EXT_DIR="."
  echo -e "  🔍 Detected manifest.json at root level. Using root as extension directory."
elif [ -f "$TARGET_DIR/extension/manifest.json" ]; then
  EXT_DIR="extension"
  echo -e "  🔍 Detected manifest.json inside 'extension' subdirectory."
elif [ -f "$TARGET_DIR/chrome-extension/manifest.json" ]; then
  EXT_DIR="chrome-extension"
  echo -e "  🔍 Detected manifest.json inside 'chrome-extension' subdirectory."
else
  EXT_DIR="extension"
  echo -e "  🔍 No existing manifest.json found. Defaulting to 'extension' subdirectory."
fi
export EXT_DIR

# Create directories if they don't exist
mkdir -p "$TARGET_DIR/.github/workflows"
mkdir -p "$TARGET_DIR/$EXT_DIR/icons"
mkdir -p "$TARGET_DIR/$EXT_DIR/popup"

# --- 1. Generate Boilerplate Files (if missing) ---
echo -e "\n${YELLOW}📦 Step 1: Checking and generating extension files...${NC}"

# Generate manifest.json if missing
MANIFEST_FILE="$TARGET_DIR/$EXT_DIR/manifest.json"
if [ ! -f "$MANIFEST_FILE" ]; then
  cat << 'EOF' > "$MANIFEST_FILE"
{
  "manifest_version": 3,
  "name": "My Chrome Extension",
  "version": "1.0.0",
  "description": "A beautiful extension created with onboard-extension.sh",
  "action": {
    "default_popup": "popup/popup.html",
    "default_icon": {
      "16": "icons/icon-16.png",
      "48": "icons/icon-48.png",
      "128": "icons/icon-128.png"
    }
  },
  "background": {
    "service_worker": "service-worker.js"
  },
  "icons": {
    "16": "icons/icon-16.png",
    "48": "icons/icon-48.png",
    "128": "icons/icon-128.png"
  },
  "permissions": [
    "storage"
  ]
}
EOF
  echo -e "  ✅ Generated default ${BOLD}manifest.json${NC}"
else
  echo -e "  ℹ️ Existing ${BOLD}manifest.json${NC} found."
fi

# Generate default base64 transparent PNG icons to prevent validation failure
echo -e "  🎨 Generating default icon files..."
# ⚡ Bolt Optimization: Replace slow Python script with fast native base64 decoding
# Eliminates interpreter startup overhead for faster execution
PNG_B64="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="

EXT_DIR_NAME="${EXT_DIR:-extension}"
if [ "$EXT_DIR_NAME" = "." ]; then
    TARGET_ICONS_DIR="${TARGET_DIR:-.}/icons"
else
    TARGET_ICONS_DIR="${TARGET_DIR:-.}/$EXT_DIR_NAME/icons"
fi
mkdir -p "$TARGET_ICONS_DIR"

for size in 16 48 128; do
    FILE_PATH="$TARGET_ICONS_DIR/icon-${size}.png"
    if [ ! -f "$FILE_PATH" ]; then
        if ! echo "$PNG_B64" | base64 --decode > "$FILE_PATH" 2>/dev/null; then
            echo "$PNG_B64" | base64 -D > "$FILE_PATH" 2>/dev/null
        fi
    fi
done
# Generate service worker if missing
SW_FILE="$TARGET_DIR/$EXT_DIR/service-worker.js"
if [ ! -f "$SW_FILE" ]; then
  cat << 'EOF' > "$SW_FILE"
// service-worker.js
// Modern, ephemeral extension service worker

// Always listen for events directly. Service workers can be terminated at any time.
chrome.runtime.onInstalled.addListener(() => {
  console.log("Extension installed successfully!");
});

// Use chrome.storage for persisting states (instead of global variables)
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "ping") {
    // Return true if using sendResponse asynchronously
    sendResponse({ status: "pong" });
  }
  return true; 
});
EOF
  echo -e "  ✅ Generated default ${BOLD}service-worker.js${NC}"
else
  echo -e "  ℹ️ Existing ${BOLD}service-worker.js${NC} found."
fi

# Generate popup UI if missing
POPUP_HTML="$TARGET_DIR/$EXT_DIR/popup/popup.html"
if [ ! -f "$POPUP_HTML" ]; then
  cat << 'EOF' > "$POPUP_HTML"
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>My Chrome Extension</title>
  <style>
    body {
      width: 250px;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      padding: 16px;
      margin: 0;
      background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
      color: #333;
    }
    h3 {
      margin-top: 0;
      color: #4a5568;
    }
    button {
      background-color: #4299e1;
      color: white;
      border: none;
      padding: 8px 12px;
      border-radius: 4px;
      cursor: pointer;
      width: 100%;
      font-weight: bold;
      transition: background-color 0.2s;
    }
    button:hover {
      background-color: #3182ce;
    }
  </style>
</head>
<body>
  <h3>Extension Popup</h3>
  <p>Hello! This is a clean boilerplate UI.</p>
  <button id="ping-btn">Ping Background</button>
  <p id="response-text" style="font-size: 12px; color: #718096;"></p>
  <script src="popup.js"></script>
</body>
</html>
EOF
  echo -e "  ✅ Generated default ${BOLD}popup/popup.html${NC}"
fi

# Generate popup JS if missing
POPUP_JS="$TARGET_DIR/$EXT_DIR/popup/popup.js"
if [ ! -f "$POPUP_JS" ]; then
  cat << 'EOF' > "$POPUP_JS"
// popup.js - Interactive controls
document.addEventListener("DOMContentLoaded", () => {
  const pingBtn = document.getElementById("ping-btn");
  const responseText = document.getElementById("response-text");

  pingBtn.addEventListener("click", async () => {
    try {
      const response = await chrome.runtime.sendMessage({ action: "ping" });
      responseText.textContent = `Response: ${response.status}`;
    } catch (error) {
      console.error(error);
      responseText.textContent = "Error communicating with service worker.";
    }
  });
});
EOF
  echo -e "  ✅ Generated default ${BOLD}popup/popup.js${NC}"
fi

# --- 2. Generate Store Listing & Privacy Files ---
echo -e "\n${YELLOW}📋 Step 2: Generating store metadata and privacy documentation...${NC}"

python3 - << 'EOF'
import json
import os
import datetime

target_dir = os.getenv("TARGET_DIR", ".")
ext_dir = os.getenv("EXT_DIR", "extension")
if ext_dir == ".":
    manifest_path = os.path.join(target_dir, "manifest.json")
else:
    manifest_path = os.path.join(target_dir, "extension", "manifest.json")

# Load manifest details
try:
    with open(manifest_path, "r") as f:
        manifest = json.load(f)
except Exception as e:
    print(f"Error loading manifest.json: {e}")
    manifest = {}

ext_name = manifest.get("name", "My Chrome Extension")
ext_desc = manifest.get("description", "A premium Chrome Extension.")
ext_version = manifest.get("version", "1.0.0")
permissions = manifest.get("permissions", [])
host_permissions = manifest.get("host_permissions", [])

# Map permissions to plain English review explanations
perm_justifications = {
    "storage": "Used to persist user settings and configuration preferences locally, ensuring they are preserved across service worker restarts.",
    "activeTab": "Grants temporary access to the active tab to execute scripting and perform operations on user request (e.g. clicking the extension action).",
    "tabs": "Allows reading the URL and title of the active tab to display page-specific analysis or summaries within the extension popup.",
    "scripting": "Enables injecting content scripts programmatically into web pages to interact with the DOM on behalf of the user.",
    "alarms": "Enables scheduling periodic background tasks and synchronization events without keeping the service worker persistently active, saving system resources.",
    "contextMenus": "Registers custom actions in the browser's right-click context menu, letting users perform extension actions directly on webpage selections.",
    "cookies": "Enables reading and writing specific domain cookies to manage authentication states and sync credentials.",
    "webRequest": "Used to intercept and analyze network requests in real-time to block trackers or modify headers.",
    "declarativeNetRequest": "Allows blocking or redirecting network requests efficiently using declarative rules, preserving browser performance and user privacy.",
    "unlimitedStorage": "Provides unlimited quota for local chrome.storage data, allowing user-generated content to be stored indefinitely without disk errors."
}

# Generate permissions table
table_rows = []
for p in permissions:
    just = perm_justifications.get(p, "[REQUIRED] Provide a specific user-facing reason why this permission is needed.")
    table_rows.append(f"| `{p}` | permissions | {just} |")
for hp in host_permissions:
    table_rows.append(f"| `{hp}` | host_permissions | Allows the extension to interact with user-requested pages on {hp} to perform core functionality. |")

if not table_rows:
    table_rows.append("| None | - | This extension requires no additional permissions. |")

permissions_table = "\n".join(table_rows)
today_str = datetime.date.today().isoformat()

## Graphics & Assets

icon_path = os.path.join(ext_dir if ext_dir != '.' else '', 'icons/icon-128.png')

# Create CHROMEWEBSTORE.md
cws_md_content = f"""# Chrome Web Store Listing — {ext_name}

> Last Updated: {today_str}

## Store Listing

**Extension Name** [REQUIRED]
{ext_name}

**Short Description** [REQUIRED]
{ext_desc[:130]}

**Detailed Description** [REQUIRED]
{ext_desc}
   
Structure recommendation:
1. One-sentence summary of what the extension does.
2. Key features (separated by line breaks, no bullets).
3. How to use it step-by-step.
4. Privacy/permissions notice (builds trust).

**Category** [REQUIRED]
Productivity

**Single Purpose** [REQUIRED]
{ext_desc[:70]}

**Primary Language** [REQUIRED]
English

## Graphics & Assets

| Asset | Dimensions | Status | Filename |
|---|---|---|---|
| Store Icon [REQUIRED] | 128×128 PNG | ✅ Ready | {icon_path} |
| Screenshot 1 [REQUIRED] | 1280×800 or 640×400 | ⬜ Not created | |
| Screenshot 2 [RECOMMENDED] | 1280×800 or 640×400 | ⬜ Not created | |
| Small Promo Tile [RECOMMENDED] | 440×280 | ⬜ Not created | |

## Permissions Justification

Every permission in manifest.json needs a justification. The review team reads these.

| Permission | Type | Justification |
|---|---|---|
{permissions_table}

## Privacy & Data Use

### Data Collection
**Does the extension collect user data?** No

All extension preferences and inputs are stored locally on the device and never sent off-device.

### Data Use Certification
- [x] Data is NOT sold to third parties
- [x] Data is NOT used for purposes unrelated to the extension's core functionality
- [x] Data is NOT used for creditworthiness or lending purposes

## Privacy Policy
Privacy Policy available in `PRIVACY.md` in the project root. Recommended to host via GitHub Pages.

## Version History

| Version | Date | Changes | Status |
|---|---|---|---|
| {ext_version} | {today_str} | Initial onboarding draft. | Draft |
"""

with open(os.path.join(target_dir, "CHROMEWEBSTORE.md"), "w") as f:
    f.write(cws_md_content.strip() + "\n")
print("  ✅ Generated CHROMEWEBSTORE.md (metadata source of truth)")

# Create PRIVACY.md
privacy_content = f"""# Privacy Policy for {ext_name}

Last updated: {today_str}

## Overview
We take your privacy seriously. This extension is designed to operate securely and keep your data safe.

## What Data We Collect
**{ext_name} does not collect, store, or transmit any personal data, telemetry, or browsing history.**
All preferences and user configurations are stored strictly on your local device.

## How Data Is Stored
All data is stored locally on the device using standard API methods:
- `chrome.storage.local`: Used to save configuration preferences.

No data is uploaded or synced to external servers.

## Third-Party Services
This extension does not use any third-party services, APIs, analytics platforms, or external tracking services.

## Contact
If you have any questions or feedback regarding this policy, please open a GitHub Issue in the project repository.
"""

with open(os.path.join(target_dir, "PRIVACY.md"), "w") as f:
    f.write(privacy_content.strip() + "\n")
print("  ✅ Generated PRIVACY.md (standard privacy policy)")

# Create app-metadata.json
metadata_content = {
    "appName": ext_name,
    "appType": "chrome-extension",
    "repoName": os.path.basename(os.path.abspath(target_dir)),
    "description": ext_desc,
    "modules": [
        {
            "name": "Chrome Extension",
            "type": "chrome-extension",
            "path": ext_dir,
            "status": "draft",
            "storeId": "your-extension-id-here",
            "storeUrl": "https://chromewebstore.google.com/detail/your-app/your-extension-id-here",
            "developerConsoleUrl": "https://chrome.google.com/webstore/devconsole/your-extension-id-here",
            "buildScript": "npm run build",
            "artifactPath": "initial-package.zip",
            "cwsListing": {
                "shortDescription": ext_desc[:130] if ext_desc else "Short description here.",
                "detailedDescription": ext_desc or "Detailed description here.",
                "category": "productivity",
                "singlePurpose": ext_desc[:70] if ext_desc else "Single purpose here.",
                "privacyPolicyUrl": f"https://ravitejakamalapuram.github.io/{os.path.basename(os.path.abspath(target_dir))}/privacy.html"
            }
        }
    ]
}

with open(os.path.join(target_dir, "app-metadata.json"), "w") as f:
    json.dump(metadata_content, f, indent=2)
print("  ✅ Generated app-metadata.json (central app registry standard)")
EOF

# --- 3. Generate Local GitHub Workflow File ---
echo -e "\n${YELLOW}⚙️ Step 3: Setting up GitHub Actions CI/CD workflows...${NC}"

WORKFLOW_FILE="$TARGET_DIR/.github/workflows/ci-cd.yml"
cat << 'EOF' > "$WORKFLOW_FILE"
name: CI/CD Pipeline

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]
  workflow_dispatch:

concurrency:
  group: ci-cd-${{ github.ref }}
  cancel-in-progress: true

jobs:
  ci:
    name: CI Pipeline
    uses: ravitejakamalapuram/.github-workflows-shared/.github/workflows/chrome-extension-ci.yml@main
    with:
      extension-dir: 'EXT_DIR_PLACEHOLDER'
      manifest-version: '3'
      strict-mode: 'false'
      run-lint: false # Enable after configuring ESLint
      run-unit-tests: false # Enable after adding tests

  cd:
    name: CD Pipeline
    needs: ci
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    uses: ravitejakamalapuram/.github-workflows-shared/.github/workflows/chrome-extension-cd.yml@main
    with:
      extension-dir: 'EXT_DIR_PLACEHOLDER'
      publish-target: 'default'
      auto-publish: 'true'
    secrets:
      chrome-extension-id: ${{ secrets.CHROME_EXTENSION_ID }}
      chrome-client-id: ${{ secrets.CHROME_CLIENT_ID }}
      chrome-client-secret: ${{ secrets.CHROME_CLIENT_SECRET }}
      chrome-refresh-token: ${{ secrets.CHROME_REFRESH_TOKEN }}
EOF
python3 -c "import sys, os; content=open('$WORKFLOW_FILE').read().replace('EXT_DIR_PLACEHOLDER', os.getenv('EXT_DIR', 'extension')); open('$WORKFLOW_FILE', 'w').write(content)"
echo -e "  ✅ Generated local workflow ${BOLD}.github/workflows/ci-cd.yml${NC} pointing to the central pipeline"

# --- 4. Package initial draft ZIP ---
echo -e "\n${YELLOW}📦 Step 4: Packaging extension for the initial manual upload...${NC}"
ZIP_PATH="$TARGET_DIR/initial-package.zip"
rm -f "$ZIP_PATH"
(cd "$TARGET_DIR/$EXT_DIR" && zip -r "../initial-package.zip" . > /dev/null)
echo -e "  ✅ Package created successfully: ${BOLD}initial-package.zip${NC}"

# --- 5. Output Interactive Step-by-Step Onboarding Checklist ---
echo -e "\n${GREEN}${BOLD}====================================================${NC}"
echo -e "${GREEN}${BOLD}🎉 SUCCESS: Project Onboarded onto Centralized CI/CD!${NC}"
echo -e "${GREEN}${BOLD}====================================================${NC}"
echo -e "\nWe have generated standard boilerplate, listing details, privacy disclosure, and packaged your ZIP."
echo -e "Follow these steps to complete the onboarding on Chrome Web Store and configure CI/CD:\n"

echo -e "${BOLD}Step 1: Obtain Google API OAuth Credentials${NC}"
echo -e "  1. Open the ${BLUE}Google Cloud Console${NC} (https://console.cloud.google.com)."
echo -e "  2. Enable the ${BOLD}Chrome Web Store API${NC} in your project."
echo -e "  3. Configure the ${BOLD}OAuth Consent Screen${NC} (External) and add scope: ${BLUE}https://www.googleapis.com/auth/chromewebstore${NC}"
echo -e "  4. Create credentials for an ${BOLD}OAuth client ID${NC} (Web application)."
echo -e "     - Add authorized redirect URI: ${BLUE}https://developers.google.com/oauthplayground${NC}"
echo -e "     - Note down your ${BOLD}Client ID${NC} and ${BOLD}Client Secret${NC}."
echo -e "  5. Go to the ${BLUE}OAuth 2.0 Playground${NC} (https://developers.google.com/oauthplayground)."
echo -e "     - Click the cog icon (top right), check 'Use your own OAuth credentials', and enter your Client ID and Client Secret."
echo -e "     - Input scope ${BLUE}https://www.googleapis.com/auth/chromewebstore${NC} and authorize."
echo -e "     - Click 'Exchange authorization code for tokens' and copy the ${BOLD}Refresh Token${NC}."

echo -e "\n${BOLD}Step 2: Create Store Listing & Perform Initial Upload${NC}"
echo -e "  1. Navigate to the ${BLUE}Chrome Web Store Developer Console${NC} (https://chrome.google.com/webstore/devconsole)."
echo -e "  2. Click ${BOLD}Add new item${NC}."
echo -e "  3. Upload the generated ${BOLD}initial-package.zip${NC} file."
echo -e "  4. Fill out Listing, Privacy, and Categories. Use descriptions and justifications from ${BOLD}CHROMEWEBSTORE.md${NC}."
echo -e "  5. Copy your new **Extension ID** from the Dashboard url or console."

echo -e "\n${BOLD}Step 3: Save Secrets to your GitHub Repository (Automated!)${NC}"
echo -e "  You can automatically retrieve tokens and set up your repository secrets using our Python script."
echo -e "  Make sure you have the ${BOLD}GitHub CLI (gh)${NC} installed and authenticated (${BLUE}gh auth login${NC})."
echo -e "  Then, run:"
echo -e "    ${BLUE}python3 \"\$(dirname \"\$0\")/setup-secrets.py\" \"\$TARGET_DIR\"${NC}"
echo -e ""
echo -e "  Alternatively, you can manually add these secrets under Settings -> Secrets and variables -> Actions -> New repository secret:"
echo -e "    - ${YELLOW}CHROME_EXTENSION_ID${NC}   : Your Extension ID from Step 2.5."
echo -e "    - ${YELLOW}CHROME_CLIENT_ID${NC}       : Your Google OAuth Client ID."
echo -e "    - ${YELLOW}CHROME_CLIENT_SECRET${NC}   : Your Google OAuth Client Secret."
echo -e "    - ${YELLOW}CHROME_REFRESH_TOKEN${NC}   : Your Google OAuth Refresh Token."

echo -e "\n${BOLD}Step 4: Push code to trigger centralized CI/CD${NC}"
echo -e "  Push your files to Git:"
echo -e "    ${BLUE}git add .${NC}"
echo -e "    ${BLUE}git commit -m \"Onboard extension to centralized workflows\"${NC}"
echo -e "    ${BLUE}git push origin main${NC}"
echo -e "\n${GREEN}Standardized CI/CD validation, packaging, and automatic store publishing are now fully active!${NC}\n"
