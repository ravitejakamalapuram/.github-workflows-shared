#!/usr/bin/env python3

import sys
import os
import urllib.parse
import urllib.request
import json
import webbrowser
import subprocess
import re
import threading
import uuid
import glob
import shlex
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

# Global configurations
CREDENTIALS_PATH = os.path.expanduser("~/.chrome-api-credentials.json")
SERVER_PORT = 3000

# Server State
SERVER_CLIENT_ID = None
SERVER_CLIENT_SECRET = None
OAUTH_STATE = {"status": "idle", "refresh_token": None, "error": None}
ACTIVE_BUILDS = {}

class WebConsoleHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress server logs to keep console clean
        return

    def send_json_response(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        global OAUTH_STATE, SERVER_CLIENT_ID, SERVER_CLIENT_SECRET
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        # Serve Frontend UI
        if path == "/" or path == "/index.html":
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(INDEX_HTML.encode('utf-8'))
            return

        # Serve Favicon (Blank)
        if path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return

        # OAuth Callback Listener
        if path == "/oauth-callback":
            params = urllib.parse.parse_qs(parsed_url.query)
            if 'code' in params:
                code = params['code'][0]
                if not SERVER_CLIENT_ID or not SERVER_CLIENT_SECRET:
                    OAUTH_STATE = {
                        "status": "error",
                        "refresh_token": None,
                        "error": "Missing client credentials in session. Please start authorization from the web console again."
                    }
                    self.serve_oauth_feedback(False, OAUTH_STATE["error"])
                else:
                    refresh_token = self.exchange_code(SERVER_CLIENT_ID, SERVER_CLIENT_SECRET, code)
                    if refresh_token:
                        OAUTH_STATE = {
                            "status": "success",
                            "refresh_token": refresh_token,
                            "error": None
                        }
                        self.serve_oauth_feedback(True, "Access Token and Refresh Token captured successfully!")
                    else:
                        OAUTH_STATE = {
                            "status": "error",
                            "refresh_token": None,
                            "error": "Failed to exchange authorization code for tokens. Verify your Client ID/Secret."
                        }
                        self.serve_oauth_feedback(False, OAUTH_STATE["error"])
            else:
                OAUTH_STATE = {
                    "status": "error",
                    "refresh_token": None,
                    "error": "No authorization code found in Google callback query parameters."
                }
                self.serve_oauth_feedback(False, OAUTH_STATE["error"])
            return

        # API: Get Local Repos & Environment Configuration
        if path == "/api/repos":
            repos = self.get_local_repos()
            gh_status = self.check_gh_status()
            cached_client_id, cached_client_secret = self.load_cached_credentials()
            
            self.send_json_response({
                "repos": repos,
                "gh_status": gh_status,
                "cached_credentials": {
                    "client_id": cached_client_id,
                    "client_secret": cached_client_secret
                }
            })
            return

        # API: Poll OAuth State
        if path == "/api/oauth-status":
            self.send_json_response(OAUTH_STATE)
            return

        # API: Get CI/CD runs
        if path == "/api/cicd-status":
            params = urllib.parse.parse_qs(parsed_url.query)
            repo_path = params.get('path', [None])[0]
            if not repo_path or not os.path.exists(repo_path):
                self.send_json_response({"success": False, "error": "Invalid repository path."}, status=400)
                return
            runs = self.get_cicd_status_internal(repo_path)
            self.send_json_response({"success": True, "runs": runs})
            return

        # API: Get Build Status
        if path == "/api/build-status":
            params = urllib.parse.parse_qs(parsed_url.query)
            build_id = params.get('build_id', [None])[0]
            if not build_id or build_id not in ACTIVE_BUILDS:
                self.send_json_response({"success": False, "error": "Build not found."}, status=404)
                return
            build_info = ACTIVE_BUILDS[build_id]
            log_content = ""
            if os.path.exists(build_info["log_file"]):
                try:
                    with open(build_info["log_file"], "r") as f:
                        log_content = f.read()
                except Exception:
                    pass
            self.send_json_response({
                "success": True,
                "status": build_info["status"],
                "log": log_content
            })
            return

        # API: Get Local Assets
        if path == "/api/assets":
            params = urllib.parse.parse_qs(parsed_url.query)
            repo_path = params.get('path', [None])[0]
            if not repo_path or not os.path.exists(repo_path):
                self.send_json_response({"success": False, "error": "Invalid repository path."}, status=400)
                return
            assets = self.find_built_assets_internal(repo_path)
            self.send_json_response({"success": True, "assets": assets})
            return

        # API: Download Asset File
        if path == "/api/download":
            params = urllib.parse.parse_qs(parsed_url.query)
            file_path = params.get('path', [None])[0]
            if not file_path or not os.path.exists(file_path):
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"File not found")
                return
            
            # Simple security check to make sure it's inside git-personal folder
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            abs_file_path = os.path.abspath(file_path)
            if not abs_file_path.startswith(base_dir):
                self.send_response(403)
                self.end_headers()
                self.wfile.write(b"Forbidden access")
                return
                
            self.send_response(200)
            self.send_header('Content-Type', 'application/octet-stream')
            self.send_header('Content-Disposition', f'attachment; filename="{os.path.basename(abs_file_path)}"')
            self.end_headers()
            with open(abs_file_path, 'rb') as f:
                self.wfile.write(f.read())
            return

        # 404 Not Found
        self.send_response(404)
        self.end_headers()
        self.wfile.write(b"404 Not Found")

    def do_POST(self):
        global SERVER_CLIENT_ID, SERVER_CLIENT_SECRET, OAUTH_STATE
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length).decode('utf-8')
        
        try:
            req_data = json.loads(post_data) if post_data else {}
        except Exception:
            req_data = {}

        # API: Cache and Start Google OAuth
        if path == "/api/start-oauth":
            SERVER_CLIENT_ID = req_data.get("client_id", "").strip()
            SERVER_CLIENT_SECRET = req_data.get("client_secret", "").strip()
            save_credentials = req_data.get("save_credentials", False)

            if not SERVER_CLIENT_ID or not SERVER_CLIENT_SECRET:
                self.send_json_response({"success": False, "error": "Client ID and Client Secret are required."}, status=400)
                return

            if save_credentials:
                self.save_cached_credentials(SERVER_CLIENT_ID, SERVER_CLIENT_SECRET)

            # Reset OAuth State
            OAUTH_STATE = {"status": "authenticating", "refresh_token": None, "error": None}

            # Build Google Auth URL
            auth_url = (
                "https://accounts.google.com/o/oauth2/v2/auth?"
                f"client_id={SERVER_CLIENT_ID}&"
                "redirect_uri=http://localhost:3000/oauth-callback&"
                "response_type=code&"
                "scope=https://www.googleapis.com/auth/chromewebstore&"
                "access_type=offline&"
                "prompt=consent"
            )
            
            webbrowser.open(auth_url)
            self.send_json_response({"success": True, "auth_url": auth_url})
            return

        # API: Onboard Project
        if path == "/api/onboard":
            repo_path = req_data.get("path")
            if not repo_path or not os.path.exists(repo_path):
                self.send_json_response({"success": False, "error": "Invalid repository path."}, status=400)
                return

            try:
                res = subprocess.run(
                    ["bash", "./scripts/onboard-extension.sh", repo_path],
                    capture_output=True,
                    text=True,
                    check=True
                )
                
                # Relocate package ZIP if created in parent relative to repo_path
                zip_source = os.path.join(repo_path, "..", "initial-package.zip")
                zip_dest = os.path.join(repo_path, "initial-package.zip")
                if os.path.exists(zip_source):
                    if os.path.exists(zip_dest):
                        os.remove(zip_dest)
                    os.rename(zip_source, zip_dest)

                self.send_json_response({
                    "success": True,
                    "output": res.stdout,
                    "zip_path": zip_dest
                })
            except subprocess.CalledProcessError as e:
                self.send_json_response({
                    "success": False,
                    "error": e.stderr or e.stdout
                }, status=500)
            return

        # API: Provision GitHub Secrets
        if path == "/api/secrets":
            repo_path = req_data.get("path")
            client_id = req_data.get("client_id")
            client_secret = req_data.get("client_secret")
            extension_id = req_data.get("extension_id")
            refresh_token = req_data.get("refresh_token")

            if not all([repo_path, client_id, client_secret, extension_id, refresh_token]):
                self.send_json_response({"success": False, "error": "All parameters are required."}, status=400)
                return

            try:
                subprocess.run(["gh", "secret", "set", "CHROME_CLIENT_ID", "--body", client_id], cwd=repo_path, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                subprocess.run(["gh", "secret", "set", "CHROME_CLIENT_SECRET", "--body", client_secret], cwd=repo_path, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                subprocess.run(["gh", "secret", "set", "CHROME_EXTENSION_ID", "--body", extension_id], cwd=repo_path, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                subprocess.run(["gh", "secret", "set", "CHROME_REFRESH_TOKEN", "--body", refresh_token], cwd=repo_path, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                
                self.send_json_response({"success": True})
            except subprocess.CalledProcessError as e:
                self.send_json_response({
                    "success": False,
                    "error": e.stderr.decode('utf-8').strip() if e.stderr else str(e)
                }, status=500)
            return

        # API: Initialize Metadata JSON
        if path == "/api/init-metadata":
            repo_path = req_data.get("path")
            app_type = req_data.get("type")
            ext_dir = req_data.get("ext_dir", ".")
            
            if not repo_path or not os.path.exists(repo_path):
                self.send_json_response({"success": False, "error": "Invalid repository path."}, status=400)
                return
                
            try:
                template = self.generate_metadata_template_internal(repo_path, app_type, ext_dir)
                meta_file = os.path.join(repo_path, "app-metadata.json")
                with open(meta_file, "w") as f:
                    json.dump(template, f, indent=2)
                    
                self.send_json_response({"success": True, "metadata": template})
            except Exception as e:
                self.send_json_response({"success": False, "error": str(e)}, status=500)
            return

        # API: Save Metadata JSON
        if path == "/api/save-metadata":
            repo_path = req_data.get("path")
            metadata = req_data.get("metadata")
            
            if not repo_path or not os.path.exists(repo_path) or not metadata:
                self.send_json_response({"success": False, "error": "Invalid parameters."}, status=400)
                return
                
            try:
                meta_file = os.path.join(repo_path, "app-metadata.json")
                with open(meta_file, "w") as f:
                    json.dump(metadata, f, indent=2)
                self.send_json_response({"success": True})
            except Exception as e:
                self.send_json_response({"success": False, "error": str(e)}, status=500)
            return

        # API: Trigger Local Build Command
        if path == "/api/build":
            repo_path = req_data.get("path")
            build_script = req_data.get("build_script")
            
            if not repo_path or not os.path.exists(repo_path) or not build_script:
                self.send_json_response({"success": False, "error": "Invalid parameters."}, status=400)
                return
                
            build_id = str(uuid.uuid4())[:8]
            self.run_build_async_internal(repo_path, build_script, build_id)
            self.send_json_response({"success": True, "build_id": build_id})
            return

        # 404 Not Found
        self.send_response(404)
        self.end_headers()

    # --- Backend Helper Functions ---
    
    def exchange_code(self, client_id, client_secret, code):
        url = "https://oauth2.googleapis.com/token"
        data = urllib.parse.urlencode({
            'code': code,
            'client_id': client_id,
            'client_secret': client_secret,
            'redirect_uri': 'http://localhost:3000/oauth-callback',
            'grant_type': 'authorization_code'
        }).encode('utf-8')
        
        req = urllib.request.Request(url, data=data)
        try:
            with urllib.request.urlopen(req) as response:
                res_data = json.loads(response.read().decode('utf-8'))
                return res_data.get('refresh_token')
        except Exception:
            return None

    def get_local_repos(self):
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        repos = []
        
        if not os.path.exists(base_dir):
            return repos
            
        for name in os.listdir(base_dir):
            path = os.path.join(base_dir, name)
            if not os.path.isdir(path) or name.startswith('.'):
                continue
                
            is_git = os.path.exists(os.path.join(path, ".git"))
            if not is_git:
                continue
                
            # Detect existing workflows
            wf_exists = os.path.exists(os.path.join(path, ".github", "workflows", "ci-cd.yml"))
            
            # Detect metadata
            meta_path = os.path.join(path, "app-metadata.json")
            if not os.path.exists(meta_path):
                meta_path = os.path.join(path, ".app-metadata.json")
                
            metadata = None
            metadata_exists = False
            if os.path.exists(meta_path):
                try:
                    with open(meta_path, "r") as f:
                        metadata = json.load(f)
                    metadata_exists = True
                    pass
                except Exception:
                    pass
            
            # Fallback type inference
            chrome_paths = []
            if os.path.exists(os.path.join(path, "manifest.json")):
                chrome_paths.append(".")
            try:
                for item in os.listdir(path):
                    item_path = os.path.join(path, item)
                    if os.path.isdir(item_path) and not item.startswith('.') and item not in ["node_modules", "build", "gradle", "ios", "android"]:
                        if os.path.exists(os.path.join(item_path, "manifest.json")):
                            chrome_paths.append(item)
            except Exception:
                pass
                
            flutter_paths = []
            if os.path.exists(os.path.join(path, "pubspec.yaml")):
                flutter_paths.append(".")
            try:
                for item in os.listdir(path):
                    item_path = os.path.join(path, item)
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
                
            if is_android_dir(path):
                android_paths.append(".")
            try:
                for item in os.listdir(path):
                    item_path = os.path.join(path, item)
                    if os.path.isdir(item_path) and not item.startswith('.') and item not in ["node_modules", "build", "gradle", "ios"]:
                        if is_android_dir(item_path):
                            android_paths.append(item)
            except Exception:
                pass
                
            total_modules = len(chrome_paths) + len(flutter_paths) + len(android_paths)
            
            inferred_type = "unknown"
            ext_dir = "."
            if total_modules > 1:
                inferred_type = "multi-module"
                if chrome_paths:
                    ext_dir = chrome_paths[0]
                elif flutter_paths:
                    ext_dir = flutter_paths[0]
                elif android_paths:
                    ext_dir = android_paths[0]
            elif total_modules == 1:
                if chrome_paths:
                    inferred_type = "chrome-extension"
                    ext_dir = chrome_paths[0]
                elif flutter_paths:
                    inferred_type = "flutter-app"
                    ext_dir = flutter_paths[0]
                elif android_paths:
                    inferred_type = "android-app"
                    ext_dir = android_paths[0]
                
            app_type = metadata.get("appType", inferred_type) if metadata else inferred_type
            app_name = metadata.get("appName", name) if metadata else name
            
            repos.append({
                "name": name,
                "appName": app_name,
                "path": path,
                "appType": app_type,
                "inferredType": inferred_type,
                "ext_dir": ext_dir or ".",
                "is_git": is_git,
                "workflow_exists": wf_exists,
                "metadata_exists": metadata_exists,
                "metadata": metadata
            })
        return repos

    def check_gh_status(self):
        try:
            res = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True)
            if res.returncode == 0:
                match = re.search(r'Logged in to github.com account (\S+)', res.stderr)
                username = match.group(1) if match else "Authenticated"
                return {"authenticated": True, "user": username}
            else:
                return {"authenticated": False, "error": res.stderr.strip() or "Not logged in"}
        except Exception as e:
            return {"authenticated": False, "error": f"gh CLI error: {str(e)}"}

    def load_cached_credentials(self):
        if os.path.exists(CREDENTIALS_PATH):
            try:
                with open(CREDENTIALS_PATH, "r") as f:
                    data = json.load(f)
                    return data.get("client_id", ""), data.get("client_secret", "")
            except Exception:
                pass
        return "", ""

    def save_cached_credentials(self, client_id, client_secret):
        try:
            os.makedirs(os.path.dirname(CREDENTIALS_PATH), exist_ok=True)
            with open(CREDENTIALS_PATH, "w") as f:
                json.dump({"client_id": client_id, "client_secret": client_secret}, f, indent=2)
        except Exception:
            pass

    def get_cicd_status_internal(self, repo_path):
        try:
            res = subprocess.run(
                ["gh", "run", "list", "--limit", "5", "--json", "name,status,conclusion,url,createdAt"],
                cwd=repo_path,
                capture_output=True,
                text=True
            )
            if res.returncode == 0:
                return json.loads(res.stdout)
            else:
                return []
        except Exception:
            return []

    def run_build_async_internal(self, repo_path, build_script, build_id):
        global ACTIVE_BUILDS
        log_file_path = os.path.join(repo_path, f".build-{build_id}.log")
        ACTIVE_BUILDS[build_id] = {
            "status": "running",
            "log_file": log_file_path,
            "script": build_script,
            "repo_path": repo_path,
            "timestamp": datetime.now().isoformat()
        }
        
        def thread_target():
            try:
                with open(log_file_path, "w") as log_f:
                    log_f.write(f"--- Build started at {datetime.now()} ---\n")
                    log_f.write(f"Directory: {repo_path}\n")
                    log_f.write(f"Command: {build_script}\n\n")
                    log_f.flush()
                    
                    proc = subprocess.Popen(
                        shlex.split(build_script),
                        shell=False,
                        cwd=repo_path,
                        stdout=log_f,
                        stderr=subprocess.STDOUT,
                        text=True
                    )
                    ACTIVE_BUILDS[build_id]["process"] = proc
                    proc.wait()
                    
                    if proc.returncode == 0:
                        ACTIVE_BUILDS[build_id]["status"] = "success"
                    else:
                        ACTIVE_BUILDS[build_id]["status"] = "failed"
            except Exception as e:
                ACTIVE_BUILDS[build_id]["status"] = "failed"
                try:
                    with open(log_file_path, "a") as log_f:
                        log_f.write(f"\n❌ Exception occurred while running build: {str(e)}\n")
                except Exception:
                    pass

        t = threading.Thread(target=thread_target)
        t.daemon = True
        t.start()

    def find_built_assets_internal(self, repo_path):
        assets = []
        patterns = [
            "*.zip",
            "initial-package.zip",
            "**/*.zip",
            "**/*.apk",
            "**/*.aab"
        ]
        found_files = []
        for p in patterns:
            matches = glob.glob(os.path.join(repo_path, p), recursive=True)
            for m in matches:
                if any(x in m for x in ["node_modules", ".git", ".gradle", ".idea", "build/kotlin", "build/tmp"]):
                    continue
                if m not in found_files and os.path.isfile(m):
                    found_files.append(m)
                    
        for f in found_files:
            rel_path = os.path.relpath(f, repo_path)
            size = os.path.getsize(f)
            assets.append({
                "name": os.path.basename(f),
                "rel_path": rel_path,
                "abs_path": f,
                "size_mb": round(size / (1024 * 1024), 2)
            })
        return assets



    def generate_metadata_template_internal(self, repo_path, expected_type, ext_dir="."):
        appName = os.path.basename(repo_path)
        repo_basename = os.path.basename(repo_path)
        description = "A premium application."
        
        # Scan modules dynamically
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
                "storeId": "",
                "storeUrl": "",
                "developerConsoleUrl": "https://chrome.google.com/webstore/devconsole",
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
                    "storeId": "",
                    "storeUrl": "",
                    "developerConsoleUrl": "https://chrome.google.com/webstore/devconsole",
                    "buildScript": "zip -r initial-package.zip " + ext_dir,
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

    def serve_oauth_feedback(self, is_success, message):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        
        status_title = "Authorization Successful" if is_success else "Authorization Failed"
        status_color = "#10b981" if is_success else "#ef4444"
        badge_bg = "#e6fffa" if is_success else "#fde8e8"
        badge_color = "#047857" if is_success else "#9b1c1c"
        
        feedback_html = f"""
        <html>
        <head>
            <title>{status_title}</title>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                    background: linear-gradient(135deg, #0b0f19 0%, #1e293b 100%);
                    color: #f8fafc;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    height: 100vh;
                    margin: 0;
                }}
                .card {{
                    background: rgba(30, 41, 59, 0.7);
                    backdrop-filter: blur(12px);
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    padding: 40px;
                    border-radius: 16px;
                    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
                    text-align: center;
                    max-width: 480px;
                }}
                h1 {{ color: {status_color}; margin-top: 0; font-size: 24px; font-weight: 700; }}
                p {{ color: #cbd5e1; font-size: 16px; line-height: 1.5; }}
                .badge {{
                    background: {badge_bg};
                    color: {badge_color};
                    padding: 6px 14px;
                    border-radius: 20px;
                    font-size: 13px;
                    font-weight: 600;
                    display: inline-block;
                    margin-bottom: 20px;
                }}
                .close-hint {{
                    margin-top: 24px;
                    font-size: 13px;
                    color: #64748b;
                }}
            </style>
        </head>
        <body>
            <div class="card">
                <span class="badge">Google APIs</span>
                <h1>{status_title}!</h1>
                <p>{message}</p>
                <p class="close-hint">You can now close this tab and return to the web onboarding console dashboard to complete repository secrets setup.</p>
            </div>
        </body>
        </html>
        """
        self.wfile.write(feedback_html.encode('utf-8'))

# --- Embedded Static HTML/CSS/JS Frontend Source ---
INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Saturn App Console & Registry</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Outfit:wght@500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #0b0f17;
            --bg-gradient: radial-gradient(circle at 50% 0%, #1c1d30 0%, #080b11 80%);
            --card-bg: rgba(22, 27, 38, 0.65);
            --card-border: rgba(255, 255, 255, 0.07);
            --accent-cyan: #06b6d4;
            --accent-cyan-glow: rgba(6, 182, 212, 0.3);
            --accent-purple: #8b5cf6;
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --text-muted: #64748b;
            --success: #10b981;
            --error: #f43f5e;
            --warning: #f59e0b;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: 'Inter', sans-serif;
            background: var(--bg-color);
            background-image: var(--bg-gradient);
            color: var(--text-primary);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            overflow-x: hidden;
        }

        header {
            border-bottom: 1px solid var(--card-border);
            padding: 16px 40px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: rgba(8, 11, 17, 0.7);
            backdrop-filter: blur(16px);
            position: sticky;
            top: 0;
            z-index: 100;
        }

        .logo-container {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .logo {
            font-family: 'Outfit', sans-serif;
            font-size: 22px;
            font-weight: 800;
            letter-spacing: -0.5px;
            background: linear-gradient(to right, var(--accent-cyan), var(--accent-purple));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .logo::before {
            content: "🪐";
            font-size: 24px;
            -webkit-text-fill-color: initial;
        }

        .logo-version {
            font-size: 11px;
            font-weight: 700;
            background: rgba(255, 255, 255, 0.08);
            border: 1px solid var(--card-border);
            padding: 2px 8px;
            border-radius: 12px;
            color: var(--text-secondary);
        }

        .header-actions {
            display: flex;
            align-items: center;
            gap: 16px;
        }

        .gh-badge {
            background: rgba(30, 41, 59, 0.4);
            border: 1px solid var(--card-border);
            border-radius: 20px;
            padding: 6px 14px;
            font-size: 13px;
            display: flex;
            align-items: center;
            gap: 8px;
            font-weight: 500;
            color: var(--text-secondary);
        }

        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            display: inline-block;
        }

        .status-dot.success { background: var(--success); box-shadow: 0 0 8px var(--success); }
        .status-dot.error { background: var(--error); box-shadow: 0 0 8px var(--error); }
        .status-dot.warning { background: var(--warning); box-shadow: 0 0 8px var(--warning); }

        /* Navigation Tabs */
        .nav-tabs {
            display: flex;
            background: rgba(30, 41, 59, 0.2);
            border: 1px solid var(--card-border);
            border-radius: 12px;
            padding: 4px;
            gap: 4px;
            margin: 24px auto 0 auto;
            width: fit-content;
        }

        .nav-tab {
            padding: 10px 20px;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 600;
            color: var(--text-secondary);
            cursor: pointer;
            border: none;
            background: transparent;
            transition: all 0.2s;
        }

        .nav-tab:hover {
            color: var(--text-primary);
        }

        .nav-tab.active {
            background: rgba(255, 255, 255, 0.07);
            color: var(--accent-cyan);
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
        }

        .container {
            max-width: 1240px;
            margin: 20px auto 40px auto;
            width: 100%;
            padding: 0 20px;
            flex: 1;
            display: flex;
            flex-direction: column;
            gap: 24px;
        }

        /* Tab Contents */
        .tab-content {
            display: none;
            animation: fadeIn 0.4s cubic-bezier(0.16, 1, 0.3, 1);
        }

        .tab-content.active {
            display: flex;
            flex-direction: column;
            gap: 24px;
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(8px); }
            to { opacity: 1; transform: translateY(0); }
        }

        /* Dashboard Overview Grid */
        .dashboard-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
            gap: 24px;
        }

        .app-card {
            background: var(--card-bg);
            backdrop-filter: blur(12px);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            padding: 24px;
            display: flex;
            flex-direction: column;
            gap: 16px;
            transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
            position: relative;
            overflow: hidden;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
        }

        .app-card::before {
            content: "";
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 4px;
            background: linear-gradient(90deg, var(--accent-cyan), var(--accent-purple));
            opacity: 0.7;
        }

        .app-card:hover {
            transform: translateY(-4px);
            border-color: rgba(255, 255, 255, 0.15);
            box-shadow: 0 12px 30px rgba(0, 0, 0, 0.25), 0 0 20px var(--accent-cyan-glow);
        }

        .app-card-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
        }

        .app-title-section {
            display: flex;
            flex-direction: column;
            gap: 4px;
        }

        .app-card-title {
            font-family: 'Outfit', sans-serif;
            font-size: 18px;
            font-weight: 700;
            color: var(--text-primary);
        }

        .app-card-path {
            font-size: 11px;
            color: var(--text-muted);
            font-family: 'JetBrains Mono', monospace;
            word-break: break-all;
        }

        .badge {
            font-size: 10px;
            font-weight: 700;
            text-transform: uppercase;
            padding: 4px 10px;
            border-radius: 12px;
            border: 1px solid transparent;
            display: inline-flex;
            align-items: center;
            gap: 4px;
            width: fit-content;
        }

        .badge-cyan { background: rgba(6, 182, 212, 0.1); color: var(--accent-cyan); border-color: rgba(6, 182, 212, 0.2); }
        .badge-purple { background: rgba(139, 92, 246, 0.1); color: var(--accent-purple); border-color: rgba(139, 92, 246, 0.2); }
        .badge-success { background: rgba(16, 185, 129, 0.1); color: var(--success); border-color: rgba(16, 185, 129, 0.2); }
        .badge-warning { background: rgba(245, 158, 11, 0.1); color: var(--warning); border-color: rgba(245, 158, 11, 0.2); }
        .badge-error { background: rgba(244, 63, 94, 0.1); color: var(--error); border-color: rgba(244, 63, 94, 0.2); }

        .app-description {
            font-size: 13px;
            color: var(--text-secondary);
            line-height: 1.5;
            min-height: 40px;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }

        .app-card-modules {
            border-top: 1px solid rgba(255, 255, 255, 0.05);
            padding-top: 12px;
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        .module-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 12px;
        }

        .module-info {
            display: flex;
            align-items: center;
            gap: 6px;
            color: var(--text-secondary);
        }

        .cicd-run-status {
            background: rgba(0, 0, 0, 0.2);
            border-radius: 8px;
            padding: 10px 14px;
            font-size: 11px;
            display: flex;
            flex-direction: column;
            gap: 4px;
            border: 1px solid rgba(255, 255, 255, 0.03);
        }

        .cicd-run-header {
            display: flex;
            justify-content: space-between;
            color: var(--text-muted);
            font-weight: 600;
            text-transform: uppercase;
            font-size: 9px;
            letter-spacing: 0.5px;
        }

        .cicd-run-info {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 8px;
        }

        .cicd-name {
            font-weight: 500;
            color: var(--text-secondary);
            text-overflow: ellipsis;
            white-space: nowrap;
            overflow: hidden;
            max-width: 180px;
        }

        .btn-row {
            display: flex;
            gap: 12px;
            margin-top: auto;
        }

        .btn {
            padding: 10px 16px;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            border: none;
            transition: all 0.2s;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
            flex: 1;
            text-decoration: none;
        }

        .btn-primary {
            background: linear-gradient(to right, var(--accent-cyan), var(--accent-purple));
            color: white;
            box-shadow: 0 4px 12px rgba(139, 92, 246, 0.15);
        }

        .btn-primary:hover {
            transform: translateY(-1px);
            box-shadow: 0 6px 16px rgba(139, 92, 246, 0.25);
        }

        .btn-secondary {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--card-border);
            color: var(--text-primary);
        }

        .btn-secondary:hover {
            background: rgba(255, 255, 255, 0.1);
        }

        .btn:disabled {
            opacity: 0.4;
            cursor: not-allowed;
            transform: none !important;
            box-shadow: none !important;
        }

        /* Split Workspace view */
        .workspace-layout {
            display: grid;
            grid-template-columns: 340px 1fr;
            gap: 24px;
            align-items: start;
        }

        .panel {
            background: var(--card-bg);
            backdrop-filter: blur(16px);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            padding: 24px;
            display: flex;
            flex-direction: column;
            gap: 20px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.15);
        }

        h2 {
            font-family: 'Outfit', sans-serif;
            font-size: 20px;
            font-weight: 700;
            letter-spacing: -0.5px;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .panel-subtitle {
            font-size: 13px;
            color: var(--text-secondary);
            margin-top: -10px;
            line-height: 1.5;
        }

        .list-items {
            display: flex;
            flex-direction: column;
            gap: 10px;
        }

        .list-item {
            background: rgba(30, 41, 59, 0.2);
            border: 1px solid var(--card-border);
            border-radius: 10px;
            padding: 12px 16px;
            cursor: pointer;
            transition: all 0.2s;
            display: flex;
            flex-direction: column;
            gap: 4px;
        }

        .list-item:hover {
            border-color: rgba(255, 255, 255, 0.12);
            background: rgba(30, 41, 59, 0.35);
        }

        .list-item.selected {
            border-color: var(--accent-cyan);
            background: rgba(6, 182, 212, 0.05);
            box-shadow: 0 0 12px rgba(6, 182, 212, 0.1);
        }

        .list-item-title {
            font-weight: 700;
            font-size: 14px;
        }

        .list-item-desc {
            font-size: 11px;
            color: var(--text-muted);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        /* Form styling */
        .form-group {
            display: flex;
            flex-direction: column;
            gap: 6px;
        }

        label {
            font-size: 12px;
            font-weight: 600;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        input, select, textarea {
            background: rgba(10, 14, 23, 0.6);
            border: 1px solid var(--card-border);
            padding: 10px 14px;
            border-radius: 8px;
            color: var(--text-primary);
            font-size: 13px;
            outline: none;
            transition: all 0.2s;
            width: 100%;
            font-family: inherit;
        }

        input:focus, select:focus, textarea:focus {
            border-color: var(--accent-cyan);
            box-shadow: 0 0 0 3px rgba(6, 182, 212, 0.15);
        }

        textarea {
            resize: vertical;
            min-height: 80px;
        }

        .tab-section {
            border-top: 1px solid rgba(255, 255, 255, 0.05);
            padding-top: 20px;
            display: flex;
            flex-direction: column;
            gap: 16px;
        }

        .sub-header {
            font-size: 14px;
            font-weight: 700;
            color: var(--accent-cyan);
            margin-bottom: 4px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .form-row {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 16px;
        }

        /* Terminal Console styles */
        .terminal-panel {
            background: rgba(4, 6, 10, 0.85);
            border: 1px solid var(--card-border);
            border-radius: 12px;
            padding: 20px;
            display: flex;
            flex-direction: column;
            gap: 12px;
            box-shadow: inset 0 0 15px rgba(0, 0, 0, 0.6), 0 8px 32px rgba(0, 0, 0, 0.3);
            backdrop-filter: blur(8px);
            transition: border-color 0.3s;
        }

        .terminal-panel.active-build {
            border-color: rgba(6, 182, 212, 0.4);
            box-shadow: inset 0 0 20px rgba(6, 182, 212, 0.05), 0 8px 32px rgba(6, 182, 212, 0.1);
        }

        .terminal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid rgba(255, 255, 255, 0.08);
            padding-bottom: 10px;
        }

        .terminal-title {
            font-family: 'JetBrains Mono', monospace;
            font-size: 11px;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 1px;
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .terminal-output {
            font-family: 'JetBrains Mono', monospace;
            font-size: 12.5px;
            color: #e2e8f0;
            height: 280px;
            overflow-y: auto;
            white-space: pre-wrap;
            line-height: 1.7;
            scroll-behavior: smooth;
            padding-right: 8px;
        }

        /* Custom scrollbar for terminal */
        .terminal-output::-webkit-scrollbar {
            width: 6px;
        }
        .terminal-output::-webkit-scrollbar-track {
            background: rgba(0, 0, 0, 0.2);
            border-radius: 3px;
        }
        .terminal-output::-webkit-scrollbar-thumb {
            background: rgba(6, 182, 212, 0.4);
            border-radius: 3px;
        }
        .terminal-output::-webkit-scrollbar-thumb:hover {
            background: rgba(6, 182, 212, 0.6);
        }

        /* SVG Build Spinner */
        .build-spinner {
            animation: spin 1s linear infinite;
            width: 14px;
            height: 14px;
            display: inline-block;
            vertical-align: middle;
        }
        @keyframes spin {
            100% { transform: rotate(360deg); }
        }

        /* Copy fields */
        .copy-field {
            display: flex;
            gap: 8px;
            position: relative;
        }

        .copy-field input, .copy-field textarea {
            padding-right: 60px;
        }

        .copy-btn-inline {
            position: absolute;
            right: 8px;
            top: 50%;
            transform: translateY(-50%);
            background: rgba(255, 255, 255, 0.06);
            border: 1px solid var(--card-border);
            color: var(--accent-cyan);
            font-size: 10px;
            font-weight: 600;
            padding: 4px 8px;
            border-radius: 4px;
            cursor: pointer;
            transition: all 0.2s;
        }

        .copy-btn-inline:hover {
            background: rgba(6, 182, 212, 0.15);
        }

        /* Asset list */
        .asset-list {
            display: flex;
            flex-direction: column;
            gap: 10px;
        }

        .asset-item {
            background: rgba(15, 23, 42, 0.4);
            border: 1px solid var(--card-border);
            border-radius: 10px;
            padding: 12px 16px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .asset-info {
            display: flex;
            flex-direction: column;
            gap: 4px;
        }

        .asset-name {
            font-weight: 600;
            font-size: 13px;
        }

        .asset-meta {
            font-size: 11px;
            color: var(--text-muted);
            font-family: 'JetBrains Mono', monospace;
        }

        .download-btn {
            background: rgba(16, 185, 129, 0.1);
            color: var(--success);
            border: 1px solid rgba(16, 185, 129, 0.2);
            padding: 6px 12px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
            text-decoration: none;
            display: flex;
            align-items: center;
            gap: 4px;
        }

        .download-btn:hover {
            background: rgba(16, 185, 129, 0.2);
        }

        .auth-status-container {
            background: rgba(30, 41, 59, 0.3);
            border: 1px solid var(--card-border);
            padding: 20px;
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 16px;
        }

        .instructions-panel {
            background: rgba(15, 23, 42, 0.5);
            border: 1px solid var(--card-border);
            border-radius: 10px;
            padding: 20px;
            font-size: 13px;
            display: flex;
            flex-direction: column;
            gap: 10px;
            line-height: 1.6;
        }

        .instructions-panel strong {
            color: var(--text-primary);
        }

        .instructions-panel ol {
            padding-left: 20px;
            display: flex;
            flex-direction: column;
            gap: 8px;
            color: var(--text-secondary);
        }

        .instructions-panel a {
            color: var(--accent-cyan);
            text-decoration: none;
        }

        .instructions-panel a:hover {
            text-decoration: underline;
        }
    </style>
</head>
<body>
    <header>
        <div class="logo-container">
            <div class="logo">Saturn Console</div>
            <div class="logo-version">v2.0</div>
        </div>
        <div class="header-actions">
            <div class="gh-badge" id="gh-status-badge">
                <span class="status-dot warning"></span> Loading GitHub CLI status...
            </div>
        </div>
    </header>

    <div class="nav-tabs">
        <button class="nav-tab active" onclick="switchTab('dashboard')">📊 App Dashboard</button>
        <button class="nav-tab" id="tab-nav-workspace" onclick="switchTab('workspace')" disabled>🛠️ App Workspace</button>
        <button class="nav-tab" id="tab-nav-builds" onclick="switchTab('builds')" disabled>📦 Builds & Assets</button>
        <button class="nav-tab" id="tab-nav-secrets" onclick="switchTab('secrets')" disabled>🔒 Secrets & CI/CD</button>
    </div>

    <div class="container">
        <!-- TAB 1: App Dashboard -->
        <div id="tab-content-dashboard" class="tab-content active">
            <div style="display: flex; flex-direction: column; gap: 8px;">
                <h2 style="font-family: 'Outfit'; font-size: 24px;">Central Application Registry</h2>
                <p style="color: var(--text-secondary); font-size: 14px;">Review and manage deployment details, store listings, and CI/CD status for all your projects.</p>
            </div>
            
            <div class="dashboard-grid" id="repos-dashboard-grid">
                <!-- Repos are rendered dynamically here -->
            </div>
        </div>

        <!-- TAB 2: Workspace Panel -->
        <div id="tab-content-workspace" class="tab-content">
            <div class="workspace-layout">
                <!-- Sidebar: App Info & Module List -->
                <div class="panel">
                    <h2 id="workspace-sidebar-title">Select App</h2>
                    <p class="panel-subtitle" id="workspace-sidebar-desc">Configure registry metadata details</p>
                    
                    <div style="display: flex; flex-direction: column; gap: 10px;">
                        <label>Application Modules</label>
                        <div class="list-items" id="workspace-module-list">
                            <!-- Modules listed dynamically -->
                        </div>
                    </div>
                    
                    <div id="init-metadata-banner" style="display: none; flex-direction: column; gap: 12px;">
                        <span class="badge badge-warning" style="width:100%;">No Metadata Found</span>
                        <p style="font-size: 12px; color: var(--text-secondary); line-height: 1.4;">This app repository is missing the compliance <code>app-metadata.json</code> file. Click below to initialize it.</p>
                        <button class="btn btn-primary" onclick="initializeMetadata()">Initialize app-metadata.json</button>
                    </div>
                </div>

                <!-- Main Content: Registry Metadata Form Editor -->
                <div class="panel" id="workspace-metadata-panel">
                    <h2>Application Configuration Standard</h2>
                    <p class="panel-subtitle">Edit metadata fields to serve as the single source of truth for CI/CD pipelines and manual onboarding</p>
                    
                    <div id="save-metadata-success" class="badge badge-success" style="display: none; padding: 10px; width: 100%; justify-content: center; font-size: 12px; margin-bottom: 10px;">
                        ✓ Metadata saved successfully to app-metadata.json!
                    </div>

                    <div class="form-row">
                        <div class="form-group">
                            <label for="meta-app-name">Application Name</label>
                            <input type="text" id="meta-app-name" placeholder="e.g. StellarTab">
                        </div>
                        <div class="form-group">
                            <label for="meta-app-type">Application Type</label>
                            <select id="meta-app-type" onchange="adjustFormFieldsForType()">
                                <option value="chrome-extension">Chrome Extension</option>
                                <option value="flutter-app">Flutter App</option>
                                <option value="android-app">Android App</option>
                                <option value="multi-module">Multi-Module/Hybrid App</option>
                            </select>
                        </div>
                    </div>

                    <div class="form-group">
                        <label for="meta-app-desc">Application Description</label>
                        <textarea id="meta-app-desc" placeholder="Write a short description of the application..."></textarea>
                    </div>

                    <!-- Dynamic Module Fields Section -->
                    <div class="tab-section" id="meta-module-section">
                        <h3 class="sub-header" id="meta-module-header">Module Configurations</h3>
                        
                        <div class="form-row">
                            <div class="form-group">
                                <label for="meta-mod-name">Module Name</label>
                                <input type="text" id="meta-mod-name" placeholder="e.g. Chrome Extension">
                            </div>
                            <div class="form-group">
                                <label for="meta-mod-type">Module Type</label>
                                <select id="meta-mod-type" onchange="toggleListingSchemaFields()">
                                    <option value="chrome-extension">Chrome Extension</option>
                                    <option value="android-app">Android App</option>
                                    <option value="flutter-app">Flutter App</option>
                                </select>
                            </div>
                        </div>

                        <div class="form-row">
                            <div class="form-group">
                                <label for="meta-mod-path">Relative Folder Path</label>
                                <input type="text" id="meta-mod-path" placeholder="e.g. extension or .">
                            </div>
                            <div class="form-group">
                                <label for="meta-mod-status">Listing Status</label>
                                <select id="meta-mod-status" onchange="toggleStoreRequirements()">
                                    <option value="draft">Draft (Manual Upload Ready)</option>
                                    <option value="beta">Beta (Testing State)</option>
                                    <option value="published">Published / Live in Store</option>
                                    <option value="unpublished">Unpublished</option>
                                </select>
                            </div>
                        </div>

                        <div class="form-row" id="store-requirements-row" style="display: none;">
                            <div class="form-group">
                                <label for="meta-mod-storeid">Store / Package ID</label>
                                <input type="text" id="meta-mod-storeid" placeholder="e.g. nkbihfbeogaeaoehlefnkodbefgpgknn">
                            </div>
                            <div class="form-group">
                                <label for="meta-mod-storeurl">Public Store URL</label>
                                <input type="text" id="meta-mod-storeurl" placeholder="https://chromewebstore.google.com/...">
                            </div>
                        </div>

                        <div class="form-row">
                            <div class="form-group">
                                <label for="meta-mod-buildscript">Build Script Command</label>
                                <input type="text" id="meta-mod-buildscript" placeholder="e.g. npm run build or flutter build apk">
                            </div>
                            <div class="form-group">
                                <label for="meta-mod-artifact">Artifact Path (Target ZIP/APK/AAB)</label>
                                <input type="text" id="meta-mod-artifact" placeholder="e.g. initial-package.zip or build/app/outputs/bundle/release/app-release.aab">
                            </div>
                        </div>

                        <!-- Chrome Web Store Listing Fields -->
                        <div id="cws-listing-fields" style="display: flex; flex-direction: column; gap: 16px;">
                            <h4 class="sub-header" style="font-size: 11px; margin-top: 10px;">Store Listing Details (Chrome Web Store)</h4>
                            <div class="form-group">
                                <label for="meta-cws-short">Short Description (max 130 chars)</label>
                                <input type="text" id="meta-cws-short" placeholder="A brief user-facing description...">
                            </div>
                            <div class="form-group">
                                <label for="meta-cws-long">Detailed Description</label>
                                <textarea id="meta-cws-long" placeholder="Describe the extension features, how to use it..."></textarea>
                            </div>
                            <div class="form-row">
                                <div class="form-group">
                                    <label for="meta-cws-purpose">Single Purpose (max 70 chars)</label>
                                    <input type="text" id="meta-cws-purpose" placeholder="Define the primary action of this extension...">
                                </div>
                                <div class="form-group">
                                    <label for="meta-cws-category">Category</label>
                                    <select id="meta-cws-category">
                                        <option value="productivity">Productivity</option>
                                        <option value="developer">Developer Tools</option>
                                        <option value="search">Search Tools</option>
                                        <option value="fun">Fun & Games</option>
                                        <option value="accessibility">Accessibility</option>
                                        <option value="social">Social & Communication</option>
                                    </select>
                                </div>
                            </div>
                            <div class="form-group">
                                <label for="meta-cws-privacy">Privacy Policy URL</label>
                                <input type="text" id="meta-cws-privacy" placeholder="https://...">
                            </div>
                        </div>

                        <!-- Google Play Store Listing Fields -->
                        <div id="play-listing-fields" style="display: none; flex-direction: column; gap: 16px;">
                            <h4 class="sub-header" style="font-size: 11px; margin-top: 10px;">Store Listing Details (Google Play Store)</h4>
                            <div class="form-group">
                                <label for="meta-play-title">Play Store App Title</label>
                                <input type="text" id="meta-play-title" placeholder="User-facing app name...">
                            </div>
                            <div class="form-group">
                                <label for="meta-play-short">Short Description (max 80 chars)</label>
                                <input type="text" id="meta-play-short" placeholder="Summary of what the app does...">
                            </div>
                            <div class="form-group">
                                <label for="meta-play-full">Full Description</label>
                                <textarea id="meta-play-full" placeholder="Detailed product marketing description..."></textarea>
                            </div>
                            <div class="form-row">
                                <div class="form-group">
                                    <label for="meta-play-category">Category</label>
                                    <input type="text" id="meta-play-category" placeholder="e.g. utilities, finance, health">
                                </div>
                                <div class="form-group">
                                    <label for="meta-play-privacy">Privacy Policy URL</label>
                                    <input type="text" id="meta-play-privacy" placeholder="https://...">
                                </div>
                            </div>
                        </div>
                    </div>

                    <div class="btn-row" style="margin-top: 20px; border-top: 1px solid rgba(255, 255, 255, 0.05); padding-top: 20px;">
                        <div></div>
                        <button class="btn btn-primary" onclick="saveMetadataChanges()" style="max-width: 200px;">Save Metadata standard</button>
                    </div>
                </div>
            </div>
        </div>

        <!-- TAB 3: Builds & Assets Console -->
        <div id="tab-content-builds" class="tab-content">
            <div class="workspace-layout" style="grid-template-columns: 1fr 400px;">
                <!-- Build Runner & Terminal -->
                <div class="panel">
                    <h2>Execute App Build</h2>
                    <p class="panel-subtitle">Trigger the app-defined build script locally. Standard output is redirected to the log viewer below.</p>
                    
                    <div style="background: rgba(30, 41, 59, 0.2); border: 1px solid var(--card-border); border-radius: 10px; padding: 20px; display: flex; align-items: center; justify-content: space-between;">
                        <div>
                            <div id="build-module-name" style="font-weight: 700; font-size: 16px;">Chrome Extension</div>
                            <div id="build-script-command" style="font-family: 'JetBrains Mono', monospace; font-size: 12px; color: var(--text-secondary); margin-top: 4px;">Command: npm run build</div>
                        </div>
                        <button class="btn btn-primary" id="btn-run-build" onclick="triggerBuild()">Execute Build</button>
                    </div>

                    <div class="terminal-panel">
                        <div class="terminal-header">
                            <span class="terminal-title">Build Log Output</span>
                            <span class="badge badge-cyan" id="build-status-badge" style="display: none;">Idle</span>
                        </div>
                        <div class="terminal-output" id="build-terminal-output">Ready to execute build command...</div>
                    </div>
                </div>

                <!-- Asset Browser -->
                <div class="panel">
                    <h2>Local Assets Directory</h2>
                    <p class="panel-subtitle">Download the compiled ZIP, APK, or AAB files generated locally for upload to the developer console.</p>
                    
                    <div class="asset-list" id="workspace-asset-list">
                        <!-- Loaded dynamically -->
                    </div>
                </div>
            </div>
        </div>

        <!-- TAB 4: Secrets & CI/CD Onboarding -->
        <div id="tab-content-secrets" class="tab-content">
            <div class="panel">
                <h2>Store Onboarding Copy-Paste Listing Guide</h2>
                <p class="panel-subtitle">Step-by-step instructions and listing parameters copyable to speed up initial manual store submission</p>
                
                <div class="workspace-layout" style="grid-template-columns: 1fr 1fr; margin-bottom: 20px;">
                    <div class="instructions-panel">
                        <strong>Developer Console Onboarding Guide:</strong>
                        <ol id="onboarding-guide-steps">
                            <!-- Populated dynamically -->
                        </ol>
                    </div>

                    <div style="display: flex; flex-direction: column; gap: 16px;">
                        <h3 class="sub-header" style="font-size: 12px;">Store Listing Copyable Assets</h3>
                        <div class="form-group">
                            <label>Short Description</label>
                            <div class="copy-field">
                                <input type="text" id="copy-field-short" readonly>
                                <button class="copy-btn-inline" onclick="copyValue('copy-field-short')">Copy</button>
                            </div>
                        </div>
                        <div class="form-group">
                            <label>Detailed Description</label>
                            <div class="copy-field">
                                <textarea id="copy-field-long" readonly style="min-height: 120px;"></textarea>
                                <button class="copy-btn-inline" onclick="copyValue('copy-field-long')" style="top: 20px;">Copy</button>
                            </div>
                        </div>
                        <div class="form-group" id="copy-field-purpose-group">
                            <label>Single Purpose</label>
                            <div class="copy-field">
                                <input type="text" id="copy-field-purpose" readonly>
                                <button class="copy-btn-inline" onclick="copyValue('copy-field-purpose')">Copy</button>
                            </div>
                        </div>
                        <div class="form-group">
                            <label>Privacy Policy Link</label>
                            <div class="copy-field">
                                <input type="text" id="copy-field-privacy" readonly>
                                <button class="copy-btn-inline" onclick="copyValue('copy-field-privacy')">Copy</button>
                            </div>
                        </div>
                    </div>
                </div>

                <h2>Automated GitHub Actions Secret Provisioning</h2>
                <p class="panel-subtitle">Link your app with central reusable workflows by securely sending Client credentials to GitHub secrets</p>

                <div class="instructions-panel" style="margin-bottom: 20px;">
                    <strong>Google Developer API Integration steps:</strong>
                    <ol>
                        <li>Access the <a href="https://console.cloud.google.com" target="_blank">Google Cloud Console</a>.</li>
                        <li>Enable the <strong>Chrome Web Store API</strong> or <strong>Google Play Android Developer API</strong>.</li>
                        <li>Configure the OAuth client ID for a Web Application and add the redirect URI: <code style="color:var(--accent-cyan);">http://localhost:3000/oauth-callback</code>.</li>
                        <li>Input your Client ID and Client Secret below, click Authorize, then send secrets directly to GitHub.</li>
                    </ol>
                </div>

                <div id="secrets-alert-box" class="alert alert-error" style="display: none; padding: 12px; border-radius: 8px; font-size: 13px; margin-bottom: 16px;"></div>

                <div class="form-row" style="margin-bottom: 16px;">
                    <div class="form-group">
                        <label for="secrets-client-id">OAuth Client ID</label>
                        <input type="text" id="secrets-client-id" placeholder="Enter Client ID">
                    </div>
                    <div class="form-group">
                        <label for="secrets-client-secret">OAuth Client Secret</label>
                        <input type="password" id="secrets-client-secret" placeholder="Enter Client Secret">
                    </div>
                </div>

                <div class="auth-status-container" id="oauth-status-panel">
                    <div>
                        <h3 style="font-size: 14px; margin-bottom: 4px;">Google API Authorization</h3>
                        <p style="font-size: 12px; color: var(--text-secondary);" id="oauth-status-text">Click authorize to authenticate your account.</p>
                    </div>
                    <button class="btn btn-primary" id="btn-oauth-trigger" onclick="triggerGoogleOAuth()" style="max-width: 240px;">
                        🔒 Authorize with Google
                    </button>
                </div>

                <div class="btn-row" style="margin-top: 24px; border-top: 1px solid rgba(255, 255, 255, 0.05); padding-top: 20px;">
                    <div></div>
                    <button class="btn btn-primary" id="btn-provision-secrets" onclick="provisionSecrets()" disabled style="max-width: 280px;">
                        🚀 Send API Secrets to GitHub Repository
                    </button>
                </div>
            </div>
        </div>
    </div>

    <script>
        let state = {
            repos: [],
            selectedRepo: null,
            selectedModuleIdx: 0,
            ghStatus: { authenticated: false },
            credentials: {
                client_id: "",
                client_secret: "",
                extension_id: "",
                refresh_token: ""
            },
            currentTab: 'dashboard',
            activeBuildInterval: null,
            activeBuildId: null
        };

        document.addEventListener("DOMContentLoaded", () => {
            fetchReposAndStatus();
        });

        function fetchReposAndStatus() {
            fetch('/api/repos')
                .then(res => res.json())
                .then(data => {
                    state.repos = data.repos;
                    state.ghStatus = data.gh_status;
                    
                    // Render Github Badge
                    const badge = document.getElementById("gh-status-badge");
                    if (state.ghStatus.authenticated) {
                        badge.innerHTML = `<span class="status-dot success"></span> GitHub CLI: Logged in as ${state.ghStatus.user}`;
                    } else {
                        badge.innerHTML = `<span class="status-dot error"></span> GitHub CLI: Not logged in`;
                    }

                    // Pre-fill credentials if cached
                    if (data.cached_credentials && data.cached_credentials.client_id) {
                        document.getElementById("secrets-client-id").value = data.cached_credentials.client_id;
                        document.getElementById("secrets-client-secret").value = data.cached_credentials.client_secret;
                        state.credentials.client_id = data.cached_credentials.client_id;
                        state.credentials.client_secret = data.cached_credentials.client_secret;
                    }

                    renderReposDashboard();
                    
                    // If a repo was selected previously, refresh its state
                    if (state.selectedRepo) {
                        const updated = state.repos.find(r => r.path === state.selectedRepo.path);
                        if (updated) {
                            selectRepo(updated);
                        }
                    }
                })
                .catch(err => console.error("Error fetching repository details:", err));
        }

        function switchTab(tabName) {
            const tabs = ['dashboard', 'workspace', 'builds', 'secrets'];
            tabs.forEach(t => {
                const content = document.getElementById(`tab-content-${t}`);
                if (content) content.classList.remove('active');
            });
            
            document.getElementById(`tab-content-${tabName}`).classList.add('active');
            
            document.querySelectorAll('.nav-tab').forEach(btn => {
                btn.classList.remove('active');
            });
            
            // Highlight tab button
            const activeBtn = Array.from(document.querySelectorAll('.nav-tab')).find(btn => btn.innerText.includes(tabName.charAt(0).toUpperCase() + tabName.slice(1)));
            if (activeBtn) activeBtn.classList.add('active');
            
            state.currentTab = tabName;
        }

        function renderReposDashboard() {
            const container = document.getElementById("repos-dashboard-grid");
            container.innerHTML = "";

            if (state.repos.length === 0) {
                container.innerHTML = "<p style='color:var(--text-secondary); text-align:center; grid-column:1/-1; padding: 40px;'>No repositories detected in the git-personal folder.</p>";
                return;
            }

            state.repos.forEach(repo => {
                const card = document.createElement("div");
                card.className = "app-card";

                // Resolve type labels & badges
                let typeBadge = `<span class="badge badge-cyan">${repo.appType}</span>`;
                if (repo.appType === "chrome-extension") {
                    typeBadge = `<span class="badge badge-cyan">Chrome Extension</span>`;
                } else if (repo.appType === "flutter-app") {
                    typeBadge = `<span class="badge badge-purple">Flutter App</span>`;
                } else if (repo.appType === "android-app") {
                    typeBadge = `<span class="badge badge-success">Android App</span>`;
                } else if (repo.appType === "multi-module") {
                    typeBadge = `<span class="badge badge-purple">Multi-Module / Hybrid</span>`;
                }

                // Resolve metadata status badge
                let statusBadge = `<span class="badge badge-error">Missing Metadata</span>`;
                let desc = repo.metadata ? repo.metadata.description : "No app-metadata.json file configured in this repository yet.";
                
                if (repo.metadata_exists && repo.metadata.modules) {
                    const primaryModule = repo.metadata.modules[0];
                    const status = primaryModule ? primaryModule.status : "draft";
                    if (status === "published") {
                        statusBadge = `<span class="badge badge-success">Live Store</span>`;
                    } else if (status === "beta") {
                        statusBadge = `<span class="badge badge-cyan">Beta State</span>`;
                    } else {
                        statusBadge = `<span class="badge badge-warning">Draft Listing</span>`;
                    }
                }

                // Render modules listing
                let modulesHtml = "";
                if (repo.metadata_exists && repo.metadata.modules) {
                    repo.metadata.modules.forEach(m => {
                        modulesHtml += `
                            <div class="module-row">
                                <span class="module-info">📦 <strong>${m.name}</strong></span>
                                <span class="badge badge-cyan" style="font-size:8px; padding:2px 6px;">${m.status}</span>
                            </div>
                        `;
                    });
                } else {
                    modulesHtml = `<div style="font-size:11px; color:var(--text-muted);">Inferred Module: ${repo.inferredType}</div>`;
                }

                card.innerHTML = `
                    <div class="app-card-header">
                        <div class="app-title-section">
                            <div class="app-card-title">${repo.appName}</div>
                            <div class="app-card-path">${repo.name}/</div>
                        </div>
                        <div style="display:flex; flex-direction:column; align-items:flex-end; gap:6px;">
                            ${typeBadge}
                            ${statusBadge}
                        </div>
                    </div>
                    
                    <div class="app-description">${desc}</div>
                    
                    <div class="app-card-modules">
                        ${modulesHtml}
                    </div>

                    <div class="cicd-run-status" id="run-status-${repo.name}" style="display:none;">
                        <!-- Updated asynchronously via JS -->
                    </div>

                    <div class="btn-row">
                        <button class="btn btn-primary" onclick="openRepoWorkspace('${repo.name}')">🛠️ Manage App</button>
                    </div>
                `;

                container.appendChild(card);
                
                // Proactively trigger CI/CD status fetch for this card
                fetchRepoRuns(repo);
            });
        }

        function fetchRepoRuns(repo) {
            fetch(`/api/cicd-status?path=${encodeURIComponent(repo.path)}`)
                .then(res => res.json())
                .then(data => {
                    const statusBox = document.getElementById(`run-status-${repo.name}`);
                    if (!statusBox) return;

                    if (data.success && data.runs && data.runs.length > 0) {
                        const run = data.runs[0];
                        statusBox.style.display = "flex";
                        
                        let dotClass = "warning";
                        if (run.conclusion === "success") dotClass = "success";
                        else if (run.conclusion === "failure") dotClass = "error";
                        
                        statusBox.innerHTML = `
                            <div class="cicd-run-header">
                                <span>CI/CD RUN</span>
                                <span>${new Date(run.createdAt).toLocaleDateString()}</span>
                            </div>
                            <div class="cicd-run-info">
                                <span class="cicd-name">${run.name}</span>
                                <span class="badge badge-${dotClass === 'success' ? 'success' : dotClass === 'error' ? 'error' : 'warning'}" style="font-size:8px; padding:2px 6px;">
                                    ${run.conclusion || run.status}
                                </span>
                            </div>
                        `;
                    }
                })
                .catch(err => console.error("Error fetching run status:", err));
        }

        function openRepoWorkspace(repoName) {
            const repo = state.repos.find(r => r.name === repoName);
            if (repo) {
                selectRepo(repo);
                switchTab('workspace');
            }
        }

        function selectRepo(repo) {
            state.selectedRepo = repo;
            state.selectedModuleIdx = 0;
            
            // Enable workspace tabs
            document.getElementById("tab-nav-workspace").disabled = false;
            document.getElementById("tab-nav-builds").disabled = false;
            document.getElementById("tab-nav-secrets").disabled = false;

            // Render workspace titles
            document.getElementById("workspace-sidebar-title").innerText = repo.appName;
            document.getElementById("workspace-sidebar-desc").innerText = `Folder: ${repo.name}`;
            
            // Render Module list in sidebar
            renderModuleList();

            // Setup forms
            if (repo.metadata_exists) {
                document.getElementById("workspace-metadata-panel").style.display = "flex";
                document.getElementById("init-metadata-banner").style.display = "none";
                populateMetadataForm();
            } else {
                document.getElementById("workspace-metadata-panel").style.display = "none";
                document.getElementById("init-metadata-banner").style.display = "flex";
            }

            // Load assets directory
            fetchRepoAssets();
            
            // Setup build module specs
            setupBuildExecutorPanel();

            // Populate copy paste list
            populateOnboardingChecklist();
        }

        function renderModuleList() {
            const list = document.getElementById("workspace-module-list");
            list.innerHTML = "";

            if (state.selectedRepo.metadata_exists && state.selectedRepo.metadata.modules) {
                state.selectedRepo.metadata.modules.forEach((mod, idx) => {
                    const item = document.createElement("div");
                    const isSel = idx === state.selectedModuleIdx;
                    item.className = `list-item ${isSel ? 'selected' : ''}`;
                    item.onclick = () => {
                        state.selectedModuleIdx = idx;
                        renderModuleList();
                        populateMetadataForm();
                        setupBuildExecutorPanel();
                        populateOnboardingChecklist();
                    };
                    
                    item.innerHTML = `
                        <div class="list-item-title">📦 ${mod.name}</div>
                        <div class="list-item-desc">Type: ${mod.type} | Folder: ${mod.path}</div>
                    `;
                    list.appendChild(item);
                });
            } else {
                const item = document.createElement("div");
                item.className = "list-item selected";
                item.innerHTML = `
                    <div class="list-item-title">Inferred Module</div>
                    <div class="list-item-desc">${state.selectedRepo.inferredType}</div>
                `;
                list.appendChild(item);
            }
        }

        function initializeMetadata() {
            fetch('/api/init-metadata', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    path: state.selectedRepo.path,
                    type: state.selectedRepo.inferredType,
                    ext_dir: state.selectedRepo.ext_dir
                })
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    fetchReposAndStatus();
                }
            })
            .catch(err => console.error("Error initializing metadata:", err));
        }

        function populateMetadataForm() {
            const meta = state.selectedRepo.metadata;
            if (!meta) return;

            document.getElementById("meta-app-name").value = meta.appName || "";
            document.getElementById("meta-app-type").value = meta.appType || "chrome-extension";
            document.getElementById("meta-app-desc").value = meta.description || "";

            // Populate currently selected module details
            const mod = meta.modules[state.selectedModuleIdx];
            if (mod) {
                document.getElementById("meta-mod-name").value = mod.name || "";
                document.getElementById("meta-mod-type").value = mod.type || "chrome-extension";
                document.getElementById("meta-mod-path").value = mod.path || "";
                document.getElementById("meta-mod-status").value = mod.status || "draft";
                document.getElementById("meta-mod-storeid").value = mod.storeId || "";
                document.getElementById("meta-mod-storeurl").value = mod.storeUrl || "";
                document.getElementById("meta-mod-buildscript").value = mod.buildScript || "";
                document.getElementById("meta-mod-artifact").value = mod.artifactPath || "";

                // Populate cws Listing Details
                if (mod.type === "chrome-extension" && mod.cwsListing) {
                    document.getElementById("meta-cws-short").value = mod.cwsListing.shortDescription || "";
                    document.getElementById("meta-cws-long").value = mod.cwsListing.detailedDescription || "";
                    document.getElementById("meta-cws-purpose").value = mod.cwsListing.singlePurpose || "";
                    document.getElementById("meta-cws-category").value = mod.cwsListing.category || "productivity";
                    document.getElementById("meta-cws-privacy").value = mod.cwsListing.privacyPolicyUrl || "";
                }

                // Populate play Listing Details
                if ((mod.type === "android-app" || mod.type === "flutter-app") && mod.playStoreListing) {
                    document.getElementById("meta-play-title").value = mod.playStoreListing.title || "";
                    document.getElementById("meta-play-short").value = mod.playStoreListing.shortDescription || "";
                    document.getElementById("meta-play-full").value = mod.playStoreListing.fullDescription || "";
                    document.getElementById("meta-play-category").value = mod.playStoreListing.category || "utilities";
                    document.getElementById("meta-play-privacy").value = mod.playStoreListing.privacyPolicyUrl || "";
                }
            }

            adjustFormFieldsForType();
            toggleListingSchemaFields();
            toggleStoreRequirements();
        }

        function adjustFormFieldsForType() {
            // Nothing special, standard field adjustments
        }

        function toggleListingSchemaFields() {
            const mType = document.getElementById("meta-mod-type").value;
            const cwsBox = document.getElementById("cws-listing-fields");
            const playBox = document.getElementById("play-listing-fields");

            if (mType === "chrome-extension") {
                cwsBox.style.display = "flex";
                playBox.style.display = "none";
            } else {
                cwsBox.style.display = "none";
                playBox.style.display = "flex";
            }
        }

        function toggleStoreRequirements() {
            const status = document.getElementById("meta-mod-status").value;
            const row = document.getElementById("store-requirements-row");
            
            if (status === "published" || status === "beta") {
                row.style.display = "grid";
            } else {
                row.style.display = "none";
            }
        }

        function saveMetadataChanges() {
            const meta = JSON.parse(JSON.stringify(state.selectedRepo.metadata));
            
            meta.appName = document.getElementById("meta-app-name").value;
            meta.appType = document.getElementById("meta-app-type").value;
            meta.description = document.getElementById("meta-app-desc").value;

            // Update selected module
            const mod = meta.modules[state.selectedModuleIdx];
            if (mod) {
                mod.name = document.getElementById("meta-mod-name").value;
                mod.type = document.getElementById("meta-mod-type").value;
                mod.path = document.getElementById("meta-mod-path").value;
                mod.status = document.getElementById("meta-mod-status").value;
                mod.storeId = document.getElementById("meta-mod-storeid").value;
                mod.storeUrl = document.getElementById("meta-mod-storeurl").value;
                mod.buildScript = document.getElementById("meta-mod-buildscript").value;
                mod.artifactPath = document.getElementById("meta-mod-artifact").value;

                if (mod.type === "chrome-extension") {
                    mod.cwsListing = {
                        shortDescription: document.getElementById("meta-cws-short").value,
                        detailedDescription: document.getElementById("meta-cws-long").value,
                        singlePurpose: document.getElementById("meta-cws-purpose").value,
                        category: document.getElementById("meta-cws-category").value,
                        privacyPolicyUrl: document.getElementById("meta-cws-privacy").value
                    };
                } else {
                    mod.playStoreListing = {
                        title: document.getElementById("meta-play-title").value,
                        shortDescription: document.getElementById("meta-play-short").value,
                        fullDescription: document.getElementById("meta-play-full").value,
                        category: document.getElementById("meta-play-category").value,
                        privacyPolicyUrl: document.getElementById("meta-play-privacy").value
                    };
                }
            }

            fetch('/api/save-metadata', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    path: state.selectedRepo.path,
                    metadata: meta
                })
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    // Show saved alert
                    const alert = document.getElementById("save-metadata-success");
                    alert.style.display = "flex";
                    setTimeout(() => {
                        alert.style.display = "none";
                    }, 3000);
                    
                    fetchReposAndStatus();
                }
            })
            .catch(err => console.error("Error saving metadata:", err));
        }

        // --- TAB 3: Build & Assets Operations ---
        
        function setupBuildExecutorPanel() {
            const nameEl = document.getElementById("build-module-name");
            const scriptEl = document.getElementById("build-script-command");
            
            if (state.selectedRepo.metadata_exists && state.selectedRepo.metadata.modules) {
                const mod = state.selectedRepo.metadata.modules[state.selectedModuleIdx];
                if (mod) {
                    nameEl.innerText = `${state.selectedRepo.appName} — ${mod.name}`;
                    scriptEl.innerText = `Command: ${mod.buildScript || "No build script defined"}`;
                    document.getElementById("btn-run-build").disabled = !mod.buildScript;
                }
            } else {
                nameEl.innerText = `${state.selectedRepo.appName}`;
                scriptEl.innerText = "Command: Inferred (initialize metadata to edit)";
                document.getElementById("btn-run-build").disabled = true;
            }
        }

        function colorizeLog(text) {
            if (!text) return "";
            const tempDiv = document.createElement("div");
            tempDiv.innerText = text;
            const escaped = tempDiv.innerHTML;
            
            return escaped.split("\\n").map(line => {
                const lineLower = line.toLowerCase();
                if (line.startsWith("❌") || lineLower.includes("failed") || lineLower.includes("exception") || lineLower.includes("error")) {
                    return `<span style="color: var(--error); font-weight: 600;">${line}</span>`;
                } else if (line.startsWith("✅") || lineLower.includes("success") || lineLower.includes("completed successfully") || line.startsWith("--- Build succeeded")) {
                    return `<span style="color: var(--success); font-weight: 600;">${line}</span>`;
                } else if (line.startsWith("Command:") || line.startsWith("Directory:") || line.startsWith("--- Build started")) {
                    return `<span style="color: var(--accent-cyan); font-weight: 500;">${line}</span>`;
                }
                return line;
            }).join("\\n");
        }

        function triggerBuild() {
            const mod = state.selectedRepo.metadata.modules[state.selectedModuleIdx];
            if (!mod || !mod.buildScript) return;

            const consoleOutput = document.getElementById("build-terminal-output");
            const badge = document.getElementById("build-status-badge");
            const btn = document.getElementById("btn-run-build");
            const terminalPanel = document.querySelector(".terminal-panel");
            
            btn.disabled = true;
            if (terminalPanel) terminalPanel.classList.add("active-build");
            badge.style.display = "inline-flex";
            badge.className = "badge badge-cyan";
            badge.innerHTML = `<svg class="build-spinner" viewBox="0 0 50 50" style="margin-right: 6px;"><circle cx="25" cy="25" r="20" fill="none" stroke="currentColor" stroke-width="5" stroke-dasharray="80, 200" stroke-linecap="round"></circle></svg> Running...`;
            consoleOutput.innerHTML = colorizeLog(`Spawning build process in background...\nCommand: ${mod.buildScript}\n\n`);

            fetch('/api/build', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    path: state.selectedRepo.path,
                    build_script: mod.buildScript
                })
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    state.activeBuildId = data.build_id;
                    startBuildLogPolling();
                } else {
                    consoleOutput.innerHTML += colorizeLog(`❌ Failed to trigger build: ${data.error}`);
                    badge.className = "badge badge-error";
                    badge.innerHTML = "❌ Error";
                    btn.disabled = false;
                    if (terminalPanel) terminalPanel.classList.remove("active-build");
                }
            })
            .catch(err => {
                consoleOutput.innerHTML += colorizeLog(`❌ Connection error triggering build: ${err}`);
                badge.className = "badge badge-error";
                badge.innerHTML = "❌ Failed";
                btn.disabled = false;
                if (terminalPanel) terminalPanel.classList.remove("active-build");
            });
        }

        function startBuildLogPolling() {
            if (state.activeBuildInterval) clearInterval(state.activeBuildInterval);
            
            const consoleOutput = document.getElementById("build-terminal-output");
            const badge = document.getElementById("build-status-badge");
            const btn = document.getElementById("btn-run-build");
            const terminalPanel = document.querySelector(".terminal-panel");

            state.activeBuildInterval = setInterval(() => {
                fetch(`/api/build-status?build_id=${state.activeBuildId}`)
                    .then(res => res.json())
                    .then(data => {
                        if (data.success) {
                            consoleOutput.innerHTML = colorizeLog(data.log);
                            consoleOutput.scrollTop = consoleOutput.scrollHeight;

                            if (data.status !== "running") {
                                clearInterval(state.activeBuildInterval);
                                btn.disabled = false;
                                if (terminalPanel) terminalPanel.classList.remove("active-build");
                                
                                if (data.status === "success") {
                                    badge.className = "badge badge-success";
                                    badge.innerHTML = "✅ Success";
                                    
                                    // Refresh assets
                                    fetchRepoAssets();
                                } else {
                                    badge.className = "badge badge-error";
                                    badge.innerHTML = "❌ Failed";
                                }
                            }
                        }
                    })
                    .catch(err => console.error("Error polling build logs:", err));
            }, 1000);
        }

        function fetchRepoAssets() {
            const list = document.getElementById("workspace-asset-list");
            list.innerHTML = "<p style='color:var(--text-muted); font-size:12px;'>Scanning for built assets...</p>";

            fetch(`/api/assets?path=${encodeURIComponent(state.selectedRepo.path)}`)
                .then(res => res.json())
                .then(data => {
                    list.innerHTML = "";
                    if (data.success && data.assets && data.assets.length > 0) {
                        data.assets.forEach(a => {
                            const item = document.createElement("div");
                            item.className = "asset-item";
                            item.innerHTML = `
                                <div class="asset-info">
                                    <div class="asset-name">${a.name}</div>
                                    <div class="asset-meta">${a.size_mb} MB | Path: ${a.rel_path}</div>
                                </div>
                                <a href="/api/download?path=${encodeURIComponent(a.abs_path)}" class="download-btn">
                                    📥 Download
                                </a>
                            `;
                            list.appendChild(item);
                        });
                    } else {
                        list.innerHTML = "<p style='color:var(--text-muted); font-size:12px;'>No local ZIP, APK, or AAB files found in common project folders.</p>";
                    }
                })
                .catch(err => {
                    list.innerHTML = `<p style='color:var(--error); font-size:12px;'>Failed to load assets: ${err}</p>`;
                });
        }

        // --- TAB 4: Secrets Onboarding Copy Pastable UI ---
        
        function populateOnboardingChecklist() {
            const meta = state.selectedRepo.metadata;
            if (!meta) return;
            const mod = meta.modules[state.selectedModuleIdx];
            if (!mod) return;

            const guideList = document.getElementById("onboarding-guide-steps");
            const shortEl = document.getElementById("copy-field-short");
            const longEl = document.getElementById("copy-field-long");
            const purposeEl = document.getElementById("copy-field-purpose");
            const privacyEl = document.getElementById("copy-field-privacy");
            
            if (mod.type === "chrome-extension") {
                document.getElementById("copy-field-purpose-group").style.display = "flex";
                
                shortEl.value = (mod.cwsListing && mod.cwsListing.shortDescription) || "";
                longEl.value = (mod.cwsListing && mod.cwsListing.detailedDescription) || "";
                purposeEl.value = (mod.cwsListing && mod.cwsListing.singlePurpose) || "";
                privacyEl.value = (mod.cwsListing && mod.cwsListing.privacyPolicyUrl) || "";

                guideList.innerHTML = `
                    <li>Go to the <a href="https://chrome.google.com/webstore/devconsole" target="_blank">Chrome Web Store Developer Console</a>.</li>
                    <li>Click <strong>Add new item</strong> and drag-and-drop the generated ZIP package found in the <strong>Builds & Assets</strong> console.</li>
                    <li>Once uploaded, go to <strong>Store listing</strong>. Copy-paste the title, descriptions, category, and single-purpose text from the right panel.</li>
                    <li>Go to the <strong>Privacy tab</strong>. Copy and paste the Privacy Policy link. Select justifications for requested permissions.</li>
                    <li>Save the draft, and copy your assigned <strong>Extension ID</strong> from the Developer dashboard address URL. Paste it into your module configuration in the <strong>Workspace tab</strong>.</li>
                `;
            } else {
                document.getElementById("copy-field-purpose-group").style.display = "none";
                
                shortEl.value = (mod.playStoreListing && mod.playStoreListing.shortDescription) || "";
                longEl.value = (mod.playStoreListing && mod.playStoreListing.fullDescription) || "";
                privacyEl.value = (mod.playStoreListing && mod.playStoreListing.privacyPolicyUrl) || "";

                guideList.innerHTML = `
                    <li>Go to the <a href="https://play.google.com/console" target="_blank">Google Play Console</a> and select your Developer account.</li>
                    <li>Click <strong>Create app</strong>. Enter App name, default language, and choose App type.</li>
                    <li>Go to <strong>Dashboard -> Set up your app</strong>. Configure declarations, categories, and copy-paste details from the right panel.</li>
                    <li>Go to <strong>App content -> Privacy Policy</strong>. Copy and paste the Privacy Policy link.</li>
                    <li>Go to <strong>Production / Testing</strong> and upload the APK or AAB bundle found in your <strong>Builds & Assets</strong> tab.</li>
                </ul>
                `;
            }
        }

        function copyValue(elementId) {
            const input = document.getElementById(elementId);
            input.select();
            input.setSelectionRange(0, 99999);
            navigator.clipboard.writeText(input.value).then(() => {
                const btn = Array.from(document.querySelectorAll('.copy-btn-inline')).find(b => b.previousElementSibling === input || b.previousElementSibling.firstElementChild === input || b.parentElement.firstElementChild === input);
                if (btn) {
                    const originalText = btn.innerText;
                    btn.innerText = 'Copied!';
                    setTimeout(() => {
                        btn.innerText = originalText;
                    }, 2000);
                }
            });
        }

        // --- STEP 4 Google OAuth & Secret Provisioning ---
        
        let pollInterval = null;

        function triggerGoogleOAuth() {
            const btn = document.getElementById("btn-oauth-trigger");
            const text = document.getElementById("oauth-status-text");
            
            const client_id = document.getElementById("secrets-client-id").value.trim();
            const client_secret = document.getElementById("secrets-client-secret").value.trim();
            const alertBox = document.getElementById("secrets-alert-box");

            if (!client_id || !client_secret) {
                alertBox.style.display = "block";
                alertBox.innerText = "OAuth Client ID and Client Secret are required before authorizing.";
                return;
            }

            alertBox.style.display = "none";
            btn.disabled = true;
            btn.innerHTML = `<span class="status-dot success spinning" style="width:12px; height:12px; border-width:2px; border-style:solid; border-color:transparent var(--success) var(--success); background:none; box-shadow:none;"></span> Waiting for login...`;
            text.innerText = "Browser opened. Please grant access to Chrome Web Store on the Google authorization screen.";

            fetch('/api/start-oauth', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    client_id: client_id,
                    client_secret: client_secret,
                    save_credentials: true
                })
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    state.credentials.client_id = client_id;
                    state.credentials.client_secret = client_secret;
                    startPolling();
                } else {
                    text.innerText = "Error starting OAuth: " + data.error;
                    btn.disabled = false;
                    btn.innerText = "🔒 Authorize with Google";
                }
            })
            .catch(err => {
                text.innerText = "Connection error starting OAuth: " + err;
                btn.disabled = false;
                btn.innerText = "🔒 Authorize with Google";
            });
        }

        function startPolling() {
            if (pollInterval) clearInterval(pollInterval);

            const btn = document.getElementById("btn-oauth-trigger");
            const text = document.getElementById("oauth-status-text");
            const nextBtn = document.getElementById("btn-provision-secrets");

            pollInterval = setInterval(() => {
                fetch('/api/oauth-status')
                    .then(res => res.json())
                    .then(data => {
                        if (data.status === "success") {
                            clearInterval(pollInterval);
                            state.credentials.refresh_token = data.refresh_token;
                            
                            text.innerHTML = `<span class="badge badge-success">✓ Google Account Connected!</span> Refresh Token captured. Ready to provision secrets.`;
                            btn.style.display = "none";
                            nextBtn.disabled = false;
                        } else if (data.status === "error") {
                            clearInterval(pollInterval);
                            text.innerText = "OAuth Failed: " + data.error;
                            btn.disabled = false;
                            btn.innerText = "🔒 Authorize with Google";
                        }
                    })
                    .catch(err => console.error("Polling error:", err));
            }, 1000);
        }

        function provisionSecrets() {
            const finalBtn = document.getElementById("btn-provision-secrets");
            const alertBox = document.getElementById("secrets-alert-box");

            // Extension ID check
            const meta = state.selectedRepo.metadata;
            const mod = meta.modules[state.selectedModuleIdx];
            if (!mod || !mod.storeId) {
                alertBox.style.display = "block";
                alertBox.className = "alert alert-error badge-error";
                alertBox.innerText = "Please input the Extension/App Store ID inside the Workspace configurations first.";
                return;
            }

            finalBtn.disabled = true;
            alertBox.style.display = "block";
            alertBox.className = "alert badge-cyan";
            alertBox.innerText = "Encrypting and uploading Client ID, Secret, Extension ID, and Refresh Token to GitHub Secrets...";

            fetch('/api/secrets', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    path: state.selectedRepo.path,
                    client_id: state.credentials.client_id,
                    client_secret: state.credentials.client_secret,
                    extension_id: mod.storeId,
                    refresh_token: state.credentials.refresh_token
                })
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    alertBox.className = "alert badge-success";
                    alertBox.innerText = "🎉 GitHub Secrets configured successfully! Centralized workflows are now linked.";
                    
                    fetchReposAndStatus();
                } else {
                    alertBox.className = "alert badge-error";
                    alertBox.innerText = "Failed to upload secrets: " + data.error;
                    finalBtn.disabled = false;
                }
            })
            .catch(err => {
                alertBox.className = "alert badge-error";
                alertBox.innerText = "Connection error setting secrets: " + err;
                finalBtn.disabled = false;
            });
        }
    </script>
</body>
</html>
"""

def main():
    print("====================================================")
    print("🚀 Starting Saturn App Console & Registry Web Server...")
    print("====================================================")
    
    server = HTTPServer(('localhost', SERVER_PORT), WebConsoleHandler)
    
    url = f"http://localhost:{SERVER_PORT}"
    print(f"\n🌐 Web Console is listening at: {url}")
    print("Opening the dashboard in your default browser now...")
    
    webbrowser.open(url)
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n❌ Web Server stopped. Exiting.")
        sys.exit(0)

if __name__ == "__main__":
    main()
