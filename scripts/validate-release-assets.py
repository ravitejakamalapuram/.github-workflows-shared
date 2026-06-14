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

def scan_repository_modules(repo_path):
    chrome_paths = []
    if os.path.exists(os.path.join(repo_path, "manifest.json")):
        chrome_paths.append(".")
    try:
        for item in os.listdir(repo_path):
            item_path = os.path.join(repo_path, item)
            if os.path.isdir(item_path) and not item.startswith('.') and item not in ["node_modules", "build", "gradle", "ios", "android"]:
                if os.path.exists(os.path.join(item_path, "manifest.json")):
                    chrome_paths.append(item)
    except Exception:
        pass
        
    flutter_paths = []
    if os.path.exists(os.path.join(repo_path, "pubspec.yaml")):
        flutter_paths.append(".")
    try:
        for item in os.listdir(repo_path):
            item_path = os.path.join(repo_path, item)
            if os.path.isdir(item_path) and not item.startswith('.') and item not in ["node_modules", "build", "gradle", "ios", "android"]:
                if os.path.exists(os.path.join(item_path, "pubspec.yaml")):
                    flutter_paths.append(item)
    except Exception:
        pass
        
    android_paths = []
    def is_android_dir(d):
        has_gradle = os.path.exists(os.path.join(d, "build.gradle")) or os.path.exists(os.path.join(d, "build.gradle.kts"))
        has_manifest = os.path.exists(os.path.join(d, "src", "main", "AndroidManifest.xml"))
        return has_gradle and has_manifest
        
    if is_android_dir(repo_path):
        android_paths.append(".")
    try:
        for item in os.listdir(repo_path):
            item_path = os.path.join(repo_path, item)
            if os.path.isdir(item_path) and not item.startswith('.') and item not in ["node_modules", "build", "gradle", "ios"]:
                if is_android_dir(item_path):
                    android_paths.append(item)
    except Exception:
        pass
        
    return chrome_paths, flutter_paths, android_paths

def generate_metadata_template(repo_path, expected_type, ext_dir="."):
    appName = os.path.basename(repo_path)
    repo_basename = os.path.basename(repo_path)
    description = "A premium application."
    
    chrome_paths, flutter_paths, android_paths = scan_repository_modules(repo_path)
    total_modules = len(chrome_paths) + len(flutter_paths) + len(android_paths)
    
    modules = []
    
    # 1. Chrome Extension Modules
    for cp in chrome_paths:
        manifest_path = os.path.join(repo_path, cp, "manifest.json")
        mod_appName = appName
        mod_description = "Chrome Extension."
        if os.path.exists(manifest_path):
            try:
                with open(manifest_path, "r") as f:
                    manifest = json.load(f)
                mod_appName = manifest.get("name", mod_appName)
                mod_description = manifest.get("description", mod_description)
            except Exception:
                pass
        modules.append({
            "name": f"{mod_appName} (Chrome Extension)" if cp != "." else mod_appName,
            "type": "chrome-extension",
            "path": cp,
            "status": "draft",
            "storeId": "your-extension-id-here",
            "storeUrl": "https://chromewebstore.google.com/detail/your-app/your-extension-id-here",
            "developerConsoleUrl": "https://chrome.google.com/webstore/devconsole/your-extension-id-here",
            "buildScript": "npm run build" if cp == "." else f"zip -r initial-package.zip {cp}",
            "artifactPath": "initial-package.zip",
            "cwsListing": {
                "shortDescription": mod_description[:130] if mod_description else "Short description here.",
                "detailedDescription": mod_description or "Detailed description here.",
                "category": "productivity",
                "singlePurpose": mod_description[:70] if mod_description else "Single purpose here.",
                "privacyPolicyUrl": f"https://ravitejakamalapuram.github.io/{repo_basename}/privacy.html"
            }
        })
        
    # 2. Flutter Modules
    for fp in flutter_paths:
        pubspec_path = os.path.join(repo_path, fp, "pubspec.yaml")
        mod_appName = appName
        mod_description = "Flutter app."
        if os.path.exists(pubspec_path):
            try:
                with open(pubspec_path, "r") as f:
                    for line in f:
                        if line.startswith("name:"):
                            mod_appName = line.split(":")[1].strip()
                        elif line.startswith("description:"):
                            mod_description = line.split(":")[1].strip()
            except Exception:
                pass
        modules.append({
            "name": f"{mod_appName} (Flutter App)" if fp != "." else mod_appName,
            "type": "flutter-app",
            "path": fp,
            "status": "draft",
            "storeId": f"com.ravitejakamalapuram.{mod_appName.lower()}",
            "storeUrl": f"https://play.google.com/store/apps/details?id=com.ravitejakamalapuram.{mod_appName.lower()}",
            "developerConsoleUrl": "https://play.google.com/console/u/0/developers",
            "buildScript": "flutter build appbundle" if fp == "." else f"cd {fp} && flutter build appbundle",
            "artifactPath": os.path.normpath(os.path.join(fp, "build/app/outputs/bundle/release/app-release.aab")),
            "playStoreListing": {
                "title": mod_appName,
                "shortDescription": mod_description[:80] if mod_description else "Short description here.",
                "fullDescription": mod_description or "Full description here.",
                "category": "utilities",
                "privacyPolicyUrl": f"https://ravitejakamalapuram.github.io/{repo_basename}/privacy.html"
            }
        })
        
    # 3. Android Modules
    for ap in android_paths:
        mod_appName = appName
        modules.append({
            "name": f"{mod_appName} (Android App)" if ap != "." else mod_appName,
            "type": "android-app",
            "path": ap,
            "status": "draft",
            "storeId": f"com.ravitejakamalapuram.{mod_appName.lower()}",
            "storeUrl": f"https://play.google.com/store/apps/details?id=com.ravitejakamalapuram.{mod_appName.lower()}",
            "developerConsoleUrl": "https://play.google.com/console/u/0/developers",
            "buildScript": "./gradlew assembleRelease" if ap == "." else f"./gradlew :{ap}:assembleRelease",
            "artifactPath": os.path.normpath(os.path.join(ap, "build/outputs/apk/release/app-release.apk" if ap != "." else "app/build/outputs/apk/release/app-release.apk")),
            "playStoreListing": {
                "title": mod_appName,
                "shortDescription": "Short description here.",
                "fullDescription": "Full description here.",
                "category": "utilities",
                "privacyPolicyUrl": f"https://ravitejakamalapuram.github.io/{repo_basename}/privacy.html"
            }
        })
        
    # Fallback if no modules detected
    if not modules:
        if expected_type == "chrome-extension":
            modules.append({
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
                    "shortDescription": "Short description here.",
                    "detailedDescription": "Detailed description here.",
                    "category": "productivity",
                    "singlePurpose": "Single purpose here.",
                    "privacyPolicyUrl": f"https://ravitejakamalapuram.github.io/{repo_basename}/privacy.html"
                }
            })
        elif expected_type == "flutter-app":
            modules.append({
                "name": "Flutter Android App",
                "type": "flutter-app",
                "path": ".",
                "status": "draft",
                "storeId": f"com.ravitejakamalapuram.{appName.lower()}",
                "storeUrl": f"https://play.google.com/store/apps/details?id=com.ravitejakamalapuram.{appName.lower()}",
                "developerConsoleUrl": "https://play.google.com/console/u/0/developers",
                "buildScript": "flutter build appbundle",
                "artifactPath": "build/app/outputs/bundle/release/app-release.aab",
                "playStoreListing": {
                    "title": appName,
                    "shortDescription": "Short description here.",
                    "fullDescription": "Full description here.",
                    "category": "utilities",
                    "privacyPolicyUrl": f"https://ravitejakamalapuram.github.io/{repo_basename}/privacy.html"
                }
            })
        else:
            modules.append({
                "name": "Android Application",
                "type": "android-app",
                "path": ".",
                "status": "draft",
                "storeId": f"com.ravitejakamalapuram.{appName.lower()}",
                "storeUrl": f"https://play.google.com/store/apps/details?id=com.ravitejakamalapuram.{appName.lower()}",
                "developerConsoleUrl": "https://play.google.com/console/u/0/developers",
                "buildScript": "./gradlew assembleRelease",
                "artifactPath": "app/build/outputs/apk/release/app-release.apk",
                "playStoreListing": {
                    "title": appName,
                    "shortDescription": "Short description here.",
                    "fullDescription": "Full description here.",
                    "category": "utilities",
                    "privacyPolicyUrl": f"https://ravitejakamalapuram.github.io/{repo_basename}/privacy.html"
                }
            })

    # Resolve appType
    appType = "multi-module" if total_modules > 1 else (modules[0]["type"] if modules else expected_type)

    return {
        "appName": appName,
        "appType": appType,
        "repoName": repo_basename,
        "description": description,
        "modules": modules
    }

def validate_app_metadata(repo_path, expected_type, ext_dir="."):
    metadata_name = "app-metadata.json"
    metadata_path = os.path.join(repo_path, metadata_name)
    if not os.path.exists(metadata_path):
        metadata_name = ".app-metadata.json"
        metadata_path = os.path.join(repo_path, metadata_name)
        
    if not os.path.exists(metadata_path):
        log_error("app-metadata.json is missing in the root directory. This file is required as the single source of truth for app details.")
        print("\n" + "="*80)
        print("💡 SELF-DOCUMENTING CI/CD FAILURE: MISSING METADATA")
        print("="*80)
        print("To fix this build error, create a file named 'app-metadata.json' at the root of your repository.")
        print(f"Here is a custom-tailored checklist template pre-populated for this '{expected_type}' project:")
        print("-"*80)
        
        template = generate_metadata_template(repo_path, expected_type, ext_dir)
        print(json.dumps(template, indent=2))
        print("-"*80)
        print("Copy the JSON template block above, populate any missing fields, and commit it to resolve compliance.")
        print("="*80 + "\n")
        return False

    try:
        with open(metadata_path, "r") as f:
            meta = json.load(f)
    except Exception as e:
        log_error(f"app-metadata.json is not valid JSON: {e}")
        return False
        
    success = True
    required_root_keys = ["appName", "appType", "modules"]
    for key in required_root_keys:
        if key not in meta:
            log_error(f"app-metadata.json is missing root key: '{key}'")
            success = False
            
    if not success:
        return False
        
    appName = meta.get("appName")
    appType = meta.get("appType")
    modules = meta.get("modules", [])
    
    valid_root_types = ["chrome-extension", "android-app", "flutter-app", "multi-module"]
    if appType not in valid_root_types:
        log_error(f"Root 'appType' value '{appType}' is invalid. Must be one of: {valid_root_types}")
        success = False
        
    if not isinstance(modules, list) or len(modules) == 0:
        log_error("Metadata 'modules' key must be a non-empty array.")
        return False
        
    for idx, mod in enumerate(modules):
        m_prefix = f"Module[{idx}]"
        required_mod_keys = ["name", "type", "path", "status"]
        for key in required_mod_keys:
            if key not in mod:
                log_error(f"{m_prefix} is missing key: '{key}'")
                success = False
        
        if not success:
            continue
            
        m_name = mod.get("name")
        m_type = mod.get("type")
        m_path = mod.get("path")
        m_status = mod.get("status")
        
        valid_types = ["chrome-extension", "android-app", "flutter-app"]
        if m_type not in valid_types:
            log_error(f"{m_prefix} ({m_name}) has invalid type '{m_type}'. Must be one of: {valid_types}")
            success = False
            
        full_mod_path = os.path.normpath(os.path.join(repo_path, m_path))
        if not os.path.exists(full_mod_path):
            log_error(f"{m_prefix} ({m_name}) has path '{m_path}' which does not exist on disk.")
            success = False
            
        valid_statuses = ["draft", "beta", "published", "unpublished"]
        if m_status not in valid_statuses:
            log_error(f"{m_prefix} ({m_name}) has invalid status '{m_status}'. Must be one of: {valid_statuses}")
            success = False
            
        if m_status in ["published", "beta"]:
            if not mod.get("storeId"):
                log_error(f"{m_prefix} ({m_name}) is status '{m_status}' but is missing 'storeId'")
                success = False
            if not mod.get("storeUrl"):
                log_error(f"{m_prefix} ({m_name}) is status '{m_status}' but is missing 'storeUrl'")
                success = False
                
        if m_type == "chrome-extension":
            cws = mod.get("cwsListing")
            if not cws or not isinstance(cws, dict):
                log_error(f"{m_prefix} ({m_name}) is a chrome-extension but is missing 'cwsListing' object.")
                success = False
            else:
                required_cws_keys = ["shortDescription", "detailedDescription", "category", "singlePurpose", "privacyPolicyUrl"]
                for key in required_cws_keys:
                    if not cws.get(key):
                        log_error(f"{m_prefix} ({m_name}) 'cwsListing' is missing or has empty key: '{key}'")
                        success = False
                        
        elif m_type in ["android-app", "flutter-app"]:
            play = mod.get("playStoreListing")
            if not play or not isinstance(play, dict):
                log_error(f"{m_prefix} ({m_name}) is an android/flutter app but is missing 'playStoreListing' object.")
                success = False
            else:
                required_play_keys = ["title", "shortDescription", "fullDescription", "category", "privacyPolicyUrl"]
                for key in required_play_keys:
                    if not play.get(key):
                        log_error(f"{m_prefix} ({m_name}) 'playStoreListing' is missing or has empty key: '{key}'")
                        success = False

    if success:
        log_success(f"app-metadata.json is valid and compliant for app: {appName} ({appType})")
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
    
    # Resolve layout dynamically if set to default '.' for extensions
    ext_dir = args.ext_dir
    if args.type == "chrome-extension" and ext_dir == ".":
        if os.path.exists(os.path.join(repo_path, "extension", "manifest.json")):
            ext_dir = "extension"
        elif os.path.exists(os.path.join(repo_path, "chrome-extension", "manifest.json")):
            ext_dir = "chrome-extension"
            
    # Step 0: Validate app-metadata.json
    print("\n🔍 Validating app-metadata.json compliance...")
    meta_success = validate_app_metadata(repo_path, args.type, ext_dir)
    if not meta_success:
        print("====================================================")
        print("❌ FAILED: Metadata check did not pass compliance. Review the errors above.")
        sys.exit(1)
    
    # Continue with regular checks
    if args.type == "chrome-extension":
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
