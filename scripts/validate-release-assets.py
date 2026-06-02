#!/usr/bin/env python3

import os
import sys
import json
import re
import argparse

def log_error(msg):
    print(f"::error::{msg}")

def log_warning(msg):
    print(f"::warning::{msg}")

def log_success(msg):
    print(f"✅ {msg}")

def validate_chrome_extension(repo_path, ext_dir):
    success = True
    manifest_path = os.path.join(repo_path, ext_dir, "manifest.json")
    
    if not os.path.exists(manifest_path):
        log_error(f"manifest.json not found at: {manifest_path}")
        return False
        
    try:
        with open(manifest_path, "r") as f:
            manifest = json.load(f)
    except Exception as e:
        log_error(f"manifest.json is not valid JSON: {e}")
        return False
        
    version = manifest.get("version", "")
    name = manifest.get("name", "Unknown Extension")
    
    if not version:
        log_error("manifest.json is missing 'version' property.")
        success = False
        
    log_success(f"Scanning Chrome Extension: {name} v{version}")
    
    # 1. Validate CHANGELOG.md
    changelog_path = os.path.join(repo_path, "CHANGELOG.md")
    if not os.path.exists(changelog_path):
        log_error("CHANGELOG.md is missing. A changelog is required for release compliance.")
        success = False
    else:
        with open(changelog_path, "r") as f:
            content = f.read()
        # Search for version in changelog (e.g. "v1.0.0", "1.0.0", "[1.0.0]")
        version_pattern = re.compile(r'(\b|\[)' + re.escape(version) + r'(\b|\])')
        if not version_pattern.search(content):
            log_error(f"CHANGELOG.md does not contain an entry for the manifest version v{version}.")
            success = False
        else:
            log_success("CHANGELOG.md contains matching release version entry.")
            
    # 2. Validate PRIVACY.md
    privacy_path = os.path.join(repo_path, "PRIVACY.md")
    if not os.path.exists(privacy_path):
        log_error("PRIVACY.md is missing. A privacy policy is required for store listings.")
        success = False
    else:
        with open(privacy_path, "r") as f:
            content = f.read()
        if "My Chrome Extension" in content or "TODO" in content:
            log_error("PRIVACY.md contains placeholder text. Please fill in details.")
            success = False
        else:
            log_success("PRIVACY.md is present and configured.")
            
    # 3. Validate CHROMEWEBSTORE.md
    cws_path = os.path.join(repo_path, "CHROMEWEBSTORE.md")
    if not os.path.exists(cws_path):
        log_error("CHROMEWEBSTORE.md is missing. Store listing metadata is required.")
        success = False
    else:
        with open(cws_path, "r") as f:
            content = f.read()
            
        if "[REQUIRED]" in content or "[RECOMMENDED]" in content:
            log_error("CHROMEWEBSTORE.md contains unpopulated template placeholders (e.g. [REQUIRED]).")
            success = False
        else:
            log_success("CHROMEWEBSTORE.md has all required template sections populated.")
            
        # Parse and check graphic assets listed in CHROMEWEBSTORE.md
        # Grabs filenames like: icons/icon-128.png or newtab_promo_tile.png
        assets = re.findall(r'\b([\w\-/_]+\.(?:png|jpg|jpeg))\b', content)
        for asset in set(assets):
            asset_path = os.path.join(repo_path, asset)
            if not os.path.exists(asset_path):
                log_warning(f"Listing asset '{asset}' referenced in CHROMEWEBSTORE.md was not found on disk.")
            else:
                log_success(f"Referenced listing asset '{asset}' is present on disk.")
                
    # 4. Check mandatory icons in manifest
    icons = manifest.get("icons", {})
    if not icons:
        log_error("No icons defined in manifest.json.")
        success = False
    else:
        for size, icon_rel_path in icons.items():
            icon_path = os.path.join(repo_path, ext_dir, icon_rel_path)
            if not os.path.exists(icon_path):
                log_error(f"Declared icon size {size} at '{icon_rel_path}' is missing from disk.")
                success = False
            else:
                log_success(f"Declared icon {size} is present.")
                
    return success

def validate_flutter_app(repo_path):
    success = True
    pubspec_path = os.path.join(repo_path, "pubspec.yaml")
    
    if not os.path.exists(pubspec_path):
        log_error(f"pubspec.yaml not found at: {pubspec_path}")
        return False
        
    # Read pubspec and extract version
    version = ""
    with open(pubspec_path, "r") as f:
        for line in f:
            if line.startswith("version:"):
                version = line.split(":")[1].strip()
                break
                
    if not version:
        log_error("pubspec.yaml is missing version tag.")
        return False
        
    # Parse version (e.g., 1.0.0+1 -> extract 1.0.0)
    base_version = version.split("+")[0]
    log_success(f"Scanning Flutter App: Version v{version} (Base: {base_version})")
    
    # 1. Validate CHANGELOG.md
    changelog_path = os.path.join(repo_path, "CHANGELOG.md")
    if not os.path.exists(changelog_path):
        log_error("CHANGELOG.md is missing. A changelog is required for release compliance.")
        success = False
    else:
        with open(changelog_path, "r") as f:
            content = f.read()
        version_pattern = re.compile(r'(\b|\[)' + re.escape(base_version) + r'(\b|\])')
        if not version_pattern.search(content):
            log_error(f"CHANGELOG.md does not contain an entry for the version v{base_version}.")
            success = False
        else:
            log_success("CHANGELOG.md contains matching release version entry.")
            
    return success

def validate_android_app(repo_path):
    success = True
    # Verify build.gradle is present
    gradle_path = os.path.join(repo_path, "app", "build.gradle")
    if not os.path.exists(gradle_path):
        # Fallback to gradle.properties or settings.gradle
        gradle_path = os.path.join(repo_path, "build.gradle.kts")
        if not os.path.exists(gradle_path):
            log_error("Could not locate build.gradle or build.gradle.kts file.")
            return False
            
    log_success("Scanning Android project configurations...")
    
    # Validate CHANGELOG.md
    changelog_path = os.path.join(repo_path, "CHANGELOG.md")
    if not os.path.exists(changelog_path):
        log_error("CHANGELOG.md is missing. A changelog is required for release compliance.")
        success = False
    else:
        log_success("CHANGELOG.md is present.")
        
    return success

def main():
    parser = argparse.ArgumentParser(description="PR Compliance and Assets Release Standards Validator")
    parser.add_argument("--path", default=".", help="Root path of the repository to validate")
    parser.add_argument("--type", required=True, choices=["chrome-extension", "flutter-app", "android-app"], help="Type of project being validated")
    parser.add_argument("--ext-dir", default=".", help="Chrome Extension directory layout (defaults to root '.')")
    
    args = parser.parse_args()
    repo_path = os.path.abspath(args.path)
    
    print("====================================================")
    print("📋 Centralized Assets and Release Standards Validator")
    print("====================================================")
    print(f"Target Repository : {repo_path}")
    print(f"Project Type      : {args.type}")
    
    if args.type == "chrome-extension":
        # Resolve layout dynamically if set to default '.'
        ext_dir = args.ext_dir
        if ext_dir == ".":
            if os.path.exists(os.path.join(repo_path, "extension", "manifest.json")):
                ext_dir = "extension"
            elif os.path.exists(os.path.join(repo_path, "chrome-extension", "manifest.json")):
                ext_dir = "chrome-extension"
        
        print(f"Extension Dir     : {ext_dir}")
        success = validate_chrome_extension(repo_path, ext_dir)
        
    elif args.type == "flutter-app":
        success = validate_flutter_app(repo_path)
        
    elif args.type == "android-app":
        success = validate_android_app(repo_path)
        
    else:
        log_error(f"Unsupported project type: {args.type}")
        success = False
        
    print("====================================================")
    if success:
        print("🎉 SUCCESS: Project meets all release compliance standards!")
        sys.exit(0)
    else:
        print("❌ FAILED: Project did not pass release compliance validations. Review the errors above.")
        sys.exit(1)

if __name__ == "__main__":
    main()
