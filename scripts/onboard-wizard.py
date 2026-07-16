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

# Clean GITHUB_TOKEN from environment to let gh CLI use keychain login
if "GITHUB_TOKEN" in os.environ:
    del os.environ["GITHUB_TOKEN"]

# Global configurations
CREDENTIALS_PATH = os.path.expanduser("~/.chrome-api-credentials.json")
SERVER_PORT = 3005
EXCLUDED_FOLDERS = {"gstack", "echokit-action"}

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
            
            assets = []
            for root, dirs, files in os.walk(repo_path):
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ["node_modules", "build", "dist", "out", "gradle"]]
                for file in files:
                    if file.lower().endswith(('.zip', '.apk', '.aab')):
                        abs_path = os.path.join(root, file)
                        rel_path = os.path.relpath(abs_path, repo_path)
                        try:
                            size_bytes = os.path.getsize(abs_path)
                            size_mb = round(size_bytes / (1024 * 1024), 2)
                        except Exception:
                            size_mb = 0.0
                        assets.append({
                            "name": file,
                            "rel_path": rel_path,
                            "abs_path": abs_path,
                            "size_mb": size_mb
                        })
            self.send_json_response({"success": True, "assets": assets})
            return

        # API: Check Privacy Policy URL Reachability
        if path == "/api/check-privacy-url":
            params = urllib.parse.parse_qs(parsed_url.query)
            url = params.get('url', [None])[0]
            reachable, err_msg = self.check_url_reachability(url)
            self.send_json_response({"success": True, "reachable": reachable, "error": err_msg})
            return

        # API: Download Asset File or View Image
        if path == "/api/download" or path == "/api/view-image":
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
            
            # Detect content type
            content_type = 'application/octet-stream'
            fn_lower = abs_file_path.lower()
            if fn_lower.endswith('.png'):
                content_type = 'image/png'
            elif fn_lower.endswith('.jpg') or fn_lower.endswith('.jpeg'):
                content_type = 'image/jpeg'
            elif fn_lower.endswith('.gif'):
                content_type = 'image/gif'
            elif fn_lower.endswith('.webp'):
                content_type = 'image/webp'
                
            self.send_header('Content-Type', content_type)
            if path == "/api/download" and not params.get('inline', ['false'])[0] == 'true':
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

        # API: Generate privacy.html
        if path == "/api/generate-privacy-html":
            repo_path = req_data.get("path")
            if not repo_path or not os.path.exists(repo_path):
                self.send_json_response({"success": False, "error": "Invalid repository path."}, status=400)
                return
            
            try:
                md_file = os.path.join(repo_path, "PRIVACY.md")
                if not os.path.exists(md_file):
                    app_name = os.path.basename(repo_path)
                    default_md = f"""# Privacy Policy for {app_name}

Last updated: {datetime.now().strftime('%Y-%m-%d')}

## Overview
We take your privacy seriously. This extension is designed to operate securely and keep your data safe.

## What Data We Collect
**{app_name} does not collect, store, or transmit any personal data, telemetry, or browsing history.**
All preferences and user configurations are stored strictly on your local device.

## How Data Is Stored
All data is stored locally on the device using standard browser storage APIs. No data is uploaded or synced to external servers.

## Third-Party Services
This extension does not use any third-party services, APIs, analytics platforms, or external tracking services.

## Contact
If you have any questions or feedback regarding this policy, please open a GitHub Issue in the project repository.
"""
                    with open(md_file, "w", encoding="utf-8") as f:
                        f.write(default_md)
                
                with open(md_file, "r", encoding="utf-8") as f:
                    md_text = f.read()
                
                app_name = os.path.basename(repo_path)
                html_content = self.compile_markdown_to_html(md_text, title=f"Privacy Policy - {app_name}")
                
                html_file = os.path.join(repo_path, "privacy.html")
                with open(html_file, "w", encoding="utf-8") as f:
                    f.write(html_content)
                
                self.send_json_response({"success": True, "message": "privacy.html generated successfully."})
            except Exception as e:
                self.send_json_response({"success": False, "error": str(e)}, status=500)
            return

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
                "redirect_uri=http://localhost:3005/oauth-callback&"
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
            'redirect_uri': 'http://localhost:3005/oauth-callback',
            'grant_type': 'authorization_code'
        }).encode('utf-8')
        
        req = urllib.request.Request(url, data=data)
        try:
            with urllib.request.urlopen(req) as response:
                res_data = json.loads(response.read().decode('utf-8'))
                return res_data.get('refresh_token')
        except Exception:
            return None

    def check_url_reachability(self, url):
        if not url:
            return False, "URL is empty"
        try:
            req = urllib.request.Request(
                url, 
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/100.0.0.0 Safari/537.36'}
            )
            # Try HEAD first
            req.get_method = lambda: 'HEAD'
            try:
                with urllib.request.urlopen(req, timeout=3) as response:
                    if response.status == 200:
                        return True, "Reachable"
            except Exception:
                # Fallback to GET
                req.get_method = lambda: 'GET'
                with urllib.request.urlopen(req, timeout=3) as response:
                    if response.status == 200:
                        return True, "Reachable"
            return False, f"HTTP status {response.status if 'response' in locals() else 'unknown'}"
        except Exception as e:
            return False, str(e)

    def compile_markdown_to_html(self, md_text, title="Privacy Policy"):
        lines = md_text.splitlines()
        html_lines = []
        in_list = False
        
        for line in lines:
            stripped = line.strip()
            if not stripped:
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                continue
                
            # Headers
            if stripped.startswith("# "):
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                val = stripped[2:].strip()
                html_lines.append(f"<h1>{val}</h1>")
            elif stripped.startswith("## "):
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                val = stripped[3:].strip()
                html_lines.append(f"<h2>{val}</h2>")
            elif stripped.startswith("### "):
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                val = stripped[4:].strip()
                html_lines.append(f"<h3>{val}</h3>")
            # List items
            elif stripped.startswith("- ") or stripped.startswith("* "):
                if not in_list:
                    html_lines.append("<ul>")
                    in_list = True
                val = stripped[2:].strip()
                val = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', val)
                html_lines.append(f"<li>{val}</li>")
            # Paragraphs
            else:
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                val = stripped
                val = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', val)
                html_lines.append(f"<p>{val}</p>")
                
        if in_list:
            html_lines.append("</ul>")
            
        content_html = "\n".join(html_lines)
        
        template = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            line-height: 1.6;
            color: #f3f4f6;
            max-width: 800px;
            margin: 0 auto;
            padding: 40px 20px;
            background-color: #0b0f19;
        }}
        h1, h2, h3 {{
            color: #38bdf8;
            font-family: 'Outfit', sans-serif;
            font-weight: 700;
        }}
        h1 {{
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
            padding-bottom: 12px;
            font-size: 2.2rem;
            margin-bottom: 30px;
        }}
        h2 {{
            font-size: 1.5rem;
            margin-top: 30px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            padding-bottom: 6px;
        }}
        p, li {{
            font-size: 1.05rem;
            color: #d1d5db;
        }}
        ul {{
            padding-left: 20px;
            margin-bottom: 20px;
        }}
        li {{
            margin-bottom: 8px;
        }}
        strong {{
            color: #38bdf8;
        }}
        .footer {{
            margin-top: 60px;
            border-top: 1px solid rgba(255, 255, 255, 0.1);
            padding-top: 20px;
            font-size: 0.9rem;
            color: #9ca3af;
            text-align: center;
        }}
    </style>
</head>
<body>
    {content_html}
    <div class="footer">
        &copy; {datetime.now().year} {title}. Hosted securely via GitHub Pages.
    </div>
</body>
</html>
"""
        return template

    def detect_remote_code_and_permissions(self, repo_path, chrome_folder):
        extension_dir = os.path.normpath(os.path.join(repo_path, chrome_folder))
        findings = []
        
        # 1. Scan manifest.json for remote scripts/CSP
        manifest_path = os.path.join(extension_dir, "manifest.json")
        manifest_data = {}
        if os.path.exists(manifest_path):
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest_data = json.load(f)
                    csp = manifest_data.get("content_security_policy")
                    if csp:
                        if isinstance(csp, str):
                            if "http://" in csp or "https://" in csp:
                                findings.append(f"manifest.json: content_security_policy allows remote scripts ('{csp}')")
                        elif isinstance(csp, dict):
                            for k, v in csp.items():
                                if isinstance(v, str) and ("http://" in v or "https://" in v):
                                    findings.append(f"manifest.json: content_security_policy.{k} allows remote scripts ('{v}')")
            except Exception:
                pass

        # 2. Scan JavaScript and HTML files
        for root, dirs, files in os.walk(extension_dir):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ["node_modules", "build", "dist", "out"]]
            for file in files:
                if file.lower().endswith(('.js', '.html')):
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()
                            
                            # eval check
                            if "eval(" in content:
                                for idx, line in enumerate(content.splitlines(), 1):
                                    if "eval(" in line and not line.strip().startswith("//"):
                                        findings.append(f"{os.path.relpath(file_path, extension_dir)}:L{idx}: Usage of eval()")
                                        
                            # new Function check
                            if "new Function(" in content:
                                for idx, line in enumerate(content.splitlines(), 1):
                                    if "new Function(" in line and not line.strip().startswith("//"):
                                        findings.append(f"{os.path.relpath(file_path, extension_dir)}:L{idx}: Usage of new Function()")
                                        
                            # HTTP/HTTPS scripts or source tags
                            remote_matches = re.findall(r'src=["\'](https?://[^"\']+)["\']', content)
                            for src in remote_matches:
                                if "chrome-extension://" not in src and "localhost" not in src:
                                    findings.append(f"{os.path.relpath(file_path, extension_dir)}: Reference to remote script '{src}'")
                                    
                            # Dynamic src matches
                            dyn_src = re.findall(r'\.src\s*=\s*["\'](https?://[^"\']+)["\']', content)
                            for src in dyn_src:
                                if "localhost" not in src:
                                    findings.append(f"{os.path.relpath(file_path, extension_dir)}: Dynamic script src set to remote URL '{src}'")
                    except Exception:
                        pass
                        
        remote_used = len(findings) > 0
        if remote_used:
            justification = "The extension references remote code or dynamic script loading. Occurrences: " + "; ".join(findings[:3])
            if len(findings) > 3:
                justification += f" (and {len(findings) - 3} more)"
        else:
            justification = "The extension does not use remote code. All files, scripts, and libraries are packaged locally within the extension ZIP file."
            
        return remote_used, justification

    def get_default_permission_justification(self, perm):
        mapping = {
            "storage": "The 'storage' permission is required to save the user's custom preferences, selected themes, and cached Bhagavad Gita verses locally on their device, ensuring settings persist across sessions and function offline.",
            "activeTab": "The 'activeTab' permission is required to interact with the current tab when the user explicitly clicks the extension browser action, enabling features like page screenshotting or element reading on demand.",
            "tabs": "The 'tabs' permission is used to safely navigate the user to settings, help pages, or other extension-related internal pages in a new browser tab.",
            "cookies": "The 'cookies' permission is used to verify session credentials and ensure smooth authentication sync with the extension's cloud synchronization service.",
            "alarms": "The 'alarms' permission is used to schedule periodic checks for new Bhagavad Gita verses or schedule daily notification updates for the user.",
            "contextMenus": "The 'contextMenus' permission allows adding quick access options in the browser's right-click context menu to copy shlokas or shuffle verses.",
            "unlimitedStorage": "The 'unlimitedStorage' permission is required to store larger local database files containing Bhagavad Gita translation assets and audio recitations for offline usage.",
            "identity": "The 'identity' permission is used to authenticate the user using Google OAuth to sync their settings, notes, and progress securely across multiple devices.",
            "notifications": "The 'notifications' permission is required to send user-facing daily shloka notifications and mindfulness reminders.",
            "declarativeNetRequest": "The 'declarativeNetRequest' permission is used to safely intercept and redirect specific API requests to local fallback endpoints if the network is disconnected."
        }
        if "://" in perm or perm == "<all_urls>":
            return f"This permission is required to communicate with remote API endpoint '{perm}' to fetch dynamic shlokas, daily quotes, and perform language translations on the fly."
            
        return mapping.get(perm, f"The '{perm}' permission is required for core extension functions, specifically to enable the user-facing features related to this capability.")

    def get_local_repos(self):
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        repos = []
        
        if not os.path.exists(base_dir):
            return repos
            
        for name in os.listdir(base_dir):
            if name in EXCLUDED_FOLDERS:
                continue
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
                except Exception:
                    pass
                    
            # Supplement CWS Listing fields dynamically if metadata is present
            if metadata and metadata.get("modules"):
                modified = False
                for mod in metadata["modules"]:
                    if mod.get("type") == "chrome-extension":
                        if "cwsListing" not in mod:
                            mod["cwsListing"] = {}
                            modified = True
                        
                        cws = mod["cwsListing"]
                        
                        # 1. Infer remote code usage
                        if "remoteCodeUsed" not in cws:
                            ext_folder = mod.get("path", ".")
                            remote_used, remote_just = self.detect_remote_code_and_permissions(path, ext_folder)
                            cws["remoteCodeUsed"] = remote_used
                            cws["remoteCodeJustification"] = remote_just
                            modified = True
                        elif not cws.get("remoteCodeJustification"):
                            ext_folder = mod.get("path", ".")
                            _, remote_just = self.detect_remote_code_and_permissions(path, ext_folder)
                            cws["remoteCodeJustification"] = remote_just
                            modified = True
                            
                        # 2. Certify policy defaults to True
                        if "dataUsageCertified" not in cws:
                            cws["dataUsageCertified"] = True
                            modified = True
                            
                        # 3. Default single purpose from manifest description if missing
                        manifest_folder = mod.get("path", ".")
                        manifest_file = os.path.normpath(os.path.join(path, manifest_folder, "manifest.json"))
                        m_desc = ""
                        m_perms = []
                        if os.path.exists(manifest_file):
                            try:
                                with open(manifest_file, "r") as mf:
                                    m_data = json.load(mf)
                                    m_desc = m_data.get("description", "")
                                    m_perms = m_data.get("permissions", []) + m_data.get("host_permissions", []) + m_data.get("optional_permissions", [])
                            except Exception:
                                pass
                                
                        if not cws.get("singlePurpose") and m_desc:
                            cws["singlePurpose"] = m_desc[:70]
                            modified = True
                            
                        # 4. Smart default permission justifications
                        if "permissionJustifications" not in cws:
                            cws["permissionJustifications"] = {}
                            modified = True
                            
                        p_justs = cws["permissionJustifications"]
                        for perm in m_perms:
                            if not p_justs.get(perm) or p_justs.get(perm) == "":
                                p_justs[perm] = self.get_default_permission_justification(perm)
                                modified = True
                                
                if modified:
                    try:
                        with open(meta_path, "w") as f:
                            json.dump(metadata, f, indent=2)
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
            
            # Parse manifest_info if chrome-extension or multi-module with chrome path
            manifest_info = None
            chrome_folder = chrome_paths[0] if chrome_paths else (ext_dir if inferred_type == "chrome-extension" else None)
            if chrome_folder:
                manifest_file = os.path.normpath(os.path.join(path, chrome_folder, "manifest.json"))
                if os.path.exists(manifest_file):
                    try:
                        with open(manifest_file, "r") as f:
                            m_data = json.load(f)
                            
                            # Verify if declared icons exist on disk
                            icons_decl = m_data.get("icons", {})
                            verified_icons = {}
                            for size, rel_path in icons_decl.items():
                                icon_abs_path = os.path.normpath(os.path.join(path, chrome_folder, rel_path))
                                verified_icons[size] = {
                                    "rel_path": rel_path,
                                    "exists": os.path.exists(icon_abs_path),
                                    "abs_path": icon_abs_path
                                }
                            
                            # Scan for promotional images / screenshots in the root or chrome path
                            screenshots = []
                            try:
                                for file_name in os.listdir(path):
                                    file_path = os.path.join(path, file_name)
                                    if os.path.isfile(file_path) and file_name.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                                        if "icon" not in file_name.lower() and not file_name.startswith('.'):
                                            screenshots.append({
                                                "name": file_name,
                                                "rel_path": file_name,
                                                "abs_path": file_path
                                            })
                            except Exception:
                                pass
                                
                            if chrome_folder and chrome_folder != ".":
                                try:
                                    chrome_abs_path = os.path.join(path, chrome_folder)
                                    for file_name in os.listdir(chrome_abs_path):
                                        file_path = os.path.join(chrome_abs_path, file_name)
                                        if os.path.isfile(file_path) and file_name.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                                            if "icon" not in file_name.lower() and not file_name.startswith('.'):
                                                rel_path = os.path.join(chrome_folder, file_name)
                                                if not any(s["name"] == file_name for s in screenshots):
                                                    screenshots.append({
                                                        "name": file_name,
                                                        "rel_path": rel_path,
                                                        "abs_path": file_path
                                                    })
                                except Exception:
                                    pass
                                
                            manifest_info = {
                                "name": m_data.get("name", ""),
                                "version": m_data.get("version", ""),
                                "description": m_data.get("description", ""),
                                "permissions": m_data.get("permissions", []),
                                "host_permissions": m_data.get("host_permissions", []),
                                "optional_permissions": m_data.get("optional_permissions", []),
                                "icons": verified_icons,
                                "screenshots": screenshots
                            }
                    except Exception:
                        pass

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
                "metadata": metadata,
                "manifest_info": manifest_info
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
            # Run code scanner on template creation
            remote_used, remote_just = self.detect_remote_code_and_permissions(repo_path, cp)
            
            p_justs = {}
            if os.path.exists(manifest_path):
                try:
                    with open(manifest_path, "r") as mf:
                        m_data = json.load(mf)
                        all_perms = m_data.get("permissions", []) + m_data.get("host_permissions", []) + m_data.get("optional_permissions", [])
                        for perm in all_perms:
                            p_justs[perm] = self.get_default_permission_justification(perm)
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
                "buildScript": "zip -r initial-package.zip . -x '*.git*' -x '*.zip' -x '*.log' -x '.*'" if cp == "." else f"zip -r initial-package.zip {cp} -x '*/.git*' -x '*/.zip' -x '*/.log'",
                "artifactPath": "initial-package.zip",
                "cwsListing": {
                    "shortDescription": mod_description[:130] if mod_description else "Short description here.",
                    "detailedDescription": mod_description or "Detailed description here.",
                    "category": "tools",
                    "singlePurpose": mod_description[:70] if mod_description else "Single purpose here.",
                    "privacyPolicyUrl": f"https://ravitejakamalapuram.github.io/{repo_basename}/privacy.html",
                    "remoteCodeUsed": remote_used,
                    "remoteCodeJustification": remote_just,
                    "dataUsageCertified": True,
                    "permissionJustifications": p_justs
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
                        "category": "tools",
                        "singlePurpose": "Single purpose here.",
                        "privacyPolicyUrl": f"https://ravitejakamalapuram.github.io/{repo_basename}/privacy.html",
                        "remoteCodeUsed": False,
                        "remoteCodeJustification": "The extension does not use remote code. All files, scripts, and libraries are packaged locally within the extension ZIP file.",
                        "dataUsageCertified": True,
                        "permissionJustifications": {}
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
            --bg-color: #131314;
            --bg-gradient: radial-gradient(circle at 50% 0%, #201f20 0%, #131314 85%);
            --card-bg: rgba(26, 26, 27, 0.65);
            --card-border: rgba(255, 255, 255, 0.08);
            --accent-cyan: #00f1fb;
            --accent-cyan-glow: rgba(0, 241, 251, 0.2);
            --accent-purple: #6200ea;
            --accent-purple-glow: rgba(98, 0, 234, 0.15);
            --accent-gold: #ffd700;
            --accent-gold-glow: rgba(255, 215, 0, 0.2);
            --text-primary: #ffffff;
            --text-secondary: #94a3b8;
            --text-muted: #64748b;
            --success: #00f1fb;
            --error: #ffb4ab;
            --warning: #ffd700;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: 'Inter', sans-serif;
            background: var(--bg-color);
            color: var(--text-primary);
            min-height: 100vh;
            overflow: hidden;
        }

        .app-layout {
            display: flex;
            min-height: 100vh;
            width: 100vw;
            overflow: hidden;
        }

        .sidebar {
            width: 280px;
            background: rgba(19, 19, 20, 0.85);
            backdrop-filter: blur(20px);
            border-right: 1px solid var(--card-border);
            display: flex;
            flex-direction: column;
            padding: 24px;
            gap: 24px;
            flex-shrink: 0;
            z-index: 100;
        }

        .main-content {
            flex-grow: 1;
            overflow-y: auto;
            height: 100vh;
            display: flex;
            flex-direction: column;
            position: relative;
            background-image: 
                radial-gradient(circle at 50% 0%, rgba(98, 0, 234, 0.04) 0%, transparent 60%),
                linear-gradient(rgba(255, 255, 255, 0.003) 1px, transparent 1px),
                linear-gradient(90deg, rgba(255, 255, 255, 0.003) 1px, transparent 1px);
            background-size: 100% 100%, 24px 24px, 24px 24px;
            background-position: center top, -1px -1px, -1px -1px;
        }

        /* Sidebar Logo */
        .logo-container {
            display: flex;
            align-items: center;
            justify-content: space-between;
            border-bottom: 1px solid var(--card-border);
            padding-bottom: 20px;
        }

        .logo {
            font-family: 'Outfit', sans-serif;
            font-size: 20px;
            font-weight: 800;
            letter-spacing: -0.5px;
            background: linear-gradient(to right, var(--accent-gold), var(--accent-cyan));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .logo::before {
            content: "🪐";
            font-size: 22px;
            -webkit-text-fill-color: initial;
        }

        .logo-version {
            font-size: 10px;
            font-weight: 700;
            background: rgba(255, 255, 255, 0.06);
            border: 1px solid var(--card-border);
            padding: 2px 6px;
            border-radius: 8px;
            color: var(--text-secondary);
        }

        /* Sidebar navigation */
        .sidebar-nav {
            display: flex;
            flex-direction: column;
            gap: 6px;
            flex-grow: 1;
        }

        .nav-section-title {
            font-size: 10px;
            font-weight: 700;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 1px;
            margin: 16px 0 6px 12px;
        }

        .nav-btn {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 12px 16px;
            border-radius: 8px;
            font-size: 13.5px;
            font-weight: 600;
            color: var(--text-secondary);
            cursor: pointer;
            border: 1px solid transparent;
            background: transparent;
            text-align: left;
            transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
            width: 100%;
        }

        .nav-btn:hover:not(:disabled) {
            color: var(--text-primary);
            background: rgba(255, 255, 255, 0.03);
            transform: translateX(4px);
        }

        .nav-btn.active {
            background: rgba(255, 215, 0, 0.06);
            color: var(--accent-gold);
            border: 1px solid rgba(255, 215, 0, 0.2);
            box-shadow: 0 0 15px rgba(255, 215, 0, 0.05);
            position: relative;
        }

        .nav-btn.active::before {
            content: "";
            position: absolute;
            left: -4px;
            top: 25%;
            height: 50%;
            width: 3px;
            background: var(--accent-gold);
            border-radius: 2px;
        }

        .nav-btn:disabled {
            opacity: 0.3;
            cursor: not-allowed;
        }

        .sidebar-footer {
            border-top: 1px solid var(--card-border);
            padding-top: 16px;
        }

        .gh-badge {
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid var(--card-border);
            border-radius: 8px;
            padding: 8px 12px;
            font-size: 12.5px;
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

        /* Sidebar active workspace picker */
        .sidebar-picker-section {
            border-bottom: 1px solid var(--card-border);
            padding-bottom: 16px;
        }

        .workspace-pill {
            display: flex;
            align-items: center;
            gap: 8px;
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid var(--card-border);
            padding: 8px 12px;
            border-radius: 8px;
            margin-top: 4px;
        }

        /* Active App Bar */
        .active-app-bar {
            display: none;
            background: rgba(19, 19, 20, 0.8);
            backdrop-filter: blur(16px);
            border-bottom: 1px solid var(--card-border);
            padding: 16px 40px;
            justify-content: space-between;
            align-items: center;
            position: sticky;
            top: 0;
            z-index: 99;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
            transition: all 0.3s ease;
        }

        /* Container & Tabs */
        .container {
            max-width: 1200px;
            margin: 32px auto 48px auto;
            width: 100%;
            padding: 0 40px;
            flex: 1;
            display: flex;
            flex-direction: column;
            gap: 32px;
        }

        .tab-content {
            display: none;
            animation: fadeIn 0.3s cubic-bezier(0.16, 1, 0.3, 1);
        }

        .tab-content.active {
            display: flex;
            flex-direction: column;
            gap: 32px;
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(6px); }
            to { opacity: 1; transform: translateY(0); }
        }

        /* Cards & Bento Grid */
        /* KPI Metrics Cards */
        .kpi-row {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 20px;
            margin-bottom: 28px;
        }

        .kpi-card {
            background: var(--card-bg);
            backdrop-filter: blur(16px);
            border: 1px solid var(--card-border);
            border-radius: 12px;
            padding: 20px;
            display: flex;
            flex-direction: column;
            gap: 8px;
            position: relative;
            overflow: hidden;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
        }

        .kpi-card::before {
            content: "";
            position: absolute;
            top: 0;
            left: 0;
            width: 4px;
            height: 100%;
            background: var(--accent-purple);
        }

        .kpi-card.kpi-gold::before { background: var(--accent-gold); }
        .kpi-card.kpi-cyan::before { background: var(--accent-cyan); }

        .kpi-label {
            font-size: 11px;
            font-weight: 700;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .kpi-value {
            font-family: 'Outfit', sans-serif;
            font-size: 32px;
            font-weight: 800;
            color: var(--text-primary);
            line-height: 1;
        }

        .kpi-sub {
            font-size: 11px;
            color: var(--text-secondary);
        }

        /* Controls Row (Search & Filters) */
        .controls-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 20px;
            margin-bottom: 24px;
            flex-wrap: wrap;
        }

        .search-container {
            position: relative;
            flex: 1;
            min-width: 280px;
            max-width: 400px;
        }

        .search-input {
            width: 100%;
            background: rgba(10, 14, 23, 0.6);
            border: 1px solid var(--card-border);
            border-radius: 8px;
            padding: 10px 14px 10px 38px;
            color: var(--text-primary);
            font-size: 13px;
            transition: all 0.3s ease;
        }

        .search-input:focus {
            border-color: var(--accent-cyan);
            box-shadow: 0 0 12px rgba(6, 182, 212, 0.15);
            outline: none;
        }

        .search-icon {
            position: absolute;
            left: 14px;
            top: 50%;
            transform: translateY(-50%);
            color: var(--text-muted);
            font-size: 13px;
            pointer-events: none;
        }

        .sort-container {
            display: flex;
            align-items: center;
            gap: 10px;
            font-size: 13px;
            color: var(--text-secondary);
        }

        .sort-select {
            background: rgba(10, 14, 23, 0.8);
            border: 1px solid var(--card-border);
            border-radius: 8px;
            padding: 8px 12px;
            color: var(--text-primary);
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
        }

        .sort-select:focus {
            border-color: var(--accent-gold);
            outline: none;
        }

        /* Registry Table Styles */
        .table-wrapper {
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 4px 24px rgba(0, 0, 0, 0.15);
        }

        .registry-table {
            width: 100%;
            border-collapse: collapse;
            text-align: left;
        }

        .registry-table th {
            background: rgba(255, 255, 255, 0.02);
            padding: 14px 20px;
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            color: var(--text-muted);
            letter-spacing: 0.5px;
            border-bottom: 1px solid var(--card-border);
        }

        .registry-table td {
            padding: 16px 20px;
            font-size: 13px;
            color: var(--text-secondary);
            border-bottom: 1px solid rgba(255, 255, 255, 0.03);
            vertical-align: middle;
            transition: all 0.2s ease;
        }

        .registry-table tbody tr {
            cursor: pointer;
            transition: background 0.2s ease;
        }

        .registry-table tbody tr:hover {
            background: rgba(255, 255, 255, 0.02);
        }

        .registry-table tbody tr:hover td {
            color: var(--text-primary);
        }

        .project-name-col {
            display: flex;
            flex-direction: column;
            gap: 4px;
        }

        .project-title {
            font-family: 'Outfit', sans-serif;
            font-size: 15px;
            font-weight: 700;
            color: var(--text-primary);
        }

        .project-path {
            font-family: 'JetBrains Mono', monospace;
            font-size: 11px;
            color: var(--text-muted);
        }

        .btn-table-action {
            background: rgba(255, 193, 7, 0.06);
            border: 1px solid rgba(255, 193, 7, 0.15);
            color: var(--accent-gold);
            padding: 6px 12px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.2s ease;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }

        .registry-table tr:hover .btn-table-action {
            background: var(--accent-gold);
            color: #0c0f16;
            box-shadow: 0 0 10px var(--accent-gold-glow);
            border-color: var(--accent-gold);
        }

        .dashboard-filters {
            display: flex;
            gap: 12px;
            margin-top: 8px;
            margin-bottom: 24px;
        }

        .filter-btn {
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid rgba(255, 255, 255, 0.08);
            color: var(--text-secondary);
            padding: 8px 16px;
            border-radius: 20px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .filter-btn:hover {
            background: rgba(255, 255, 255, 0.06);
            color: var(--text-primary);
            border-color: rgba(255, 255, 255, 0.15);
        }

        .filter-btn.active {
            background: rgba(255, 193, 7, 0.12);
            border-color: var(--accent-gold);
            color: var(--accent-gold);
            box-shadow: 0 0 12px rgba(255, 193, 7, 0.1);
        }

        .filter-count {
            background: rgba(255, 255, 255, 0.07);
            padding: 2px 6px;
            border-radius: 10px;
            font-size: 11px;
            color: var(--text-muted);
            font-weight: 500;
        }

        .filter-btn.active .filter-count {
            background: rgba(255, 193, 7, 0.2);
            color: var(--accent-gold);
        }

        .app-card-modules-inline {
            border-top: 1px solid rgba(255, 255, 255, 0.05);
            padding-top: 12px;
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }

        .module-chip {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 8px;
            padding: 4px 8px;
            font-size: 11px;
            color: var(--text-secondary);
        }

        .module-chip .dot {
            width: 6px;
            height: 6px;
            border-radius: 50%;
            display: inline-block;
        }

        .module-chip .dot-published { background-color: var(--success); box-shadow: 0 0 6px var(--success); }
        .module-chip .dot-beta { background-color: var(--accent-cyan); box-shadow: 0 0 6px var(--accent-cyan); }
        .module-chip .dot-draft { background-color: var(--warning); box-shadow: 0 0 6px var(--warning); }
        .module-chip .dot-missing { background-color: var(--error); box-shadow: 0 0 6px var(--error); }

        .cicd-run-bar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            background: rgba(0, 0, 0, 0.15);
            border-radius: 8px;
            padding: 8px 12px;
            font-size: 11px;
            color: var(--text-muted);
            border: 1px solid rgba(255, 255, 255, 0.02);
        }

        .cicd-run-bar .run-conclusion {
            font-weight: 700;
            text-transform: uppercase;
            font-size: 9px;
            letter-spacing: 0.5px;
        }

        .cicd-run-bar .run-conclusion.success { color: var(--success); }
        .cicd-run-bar .run-conclusion.failure { color: var(--error); }
        .cicd-run-bar .run-conclusion.running { color: var(--warning); }

        .btn-manage {
            width: 100%;
            background: rgba(255, 193, 7, 0.06);
            border: 1px solid rgba(255, 193, 7, 0.15);
            color: var(--accent-gold);
            padding: 10px 18px;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
        }

        .app-card:hover .btn-manage {
            background: var(--accent-gold);
            color: #0c0f16;
            box-shadow: 0 0 16px var(--accent-gold-glow);
            border-color: var(--accent-gold);
        }

        .btn-row {
            display: flex;
            gap: 12px;
            margin-top: auto;
        }

        .btn {
            padding: 10px 18px;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            border: 1px solid transparent;
            transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
            text-decoration: none;
        }

        .btn-primary {
            background: var(--accent-gold);
            color: #131314;
            font-weight: 700;
            box-shadow: 0 4px 12px var(--accent-gold-glow);
        }

        .btn-primary:hover:not(:disabled):not([aria-disabled="true"]) {
            transform: translateY(-1px);
            background: #ffe16d;
            box-shadow: 0 6px 20px rgba(255, 215, 0, 0.35);
        }

        .btn-secondary {
            background: rgba(98, 0, 234, 0.03);
            border: 1px solid var(--accent-purple);
            color: var(--text-primary);
        }

        .btn-secondary:hover:not(:disabled):not([aria-disabled="true"]) {
            background: rgba(98, 0, 234, 0.1);
            box-shadow: 0 0 12px var(--accent-purple-glow);
        }

        .btn:disabled, .btn[aria-disabled="true"] {
            opacity: 0.4;
            cursor: not-allowed;
            transform: none !important;
            box-shadow: none !important;
        }

        /* Split Workspace view */
        .workspace-layout {
            display: grid;
            grid-template-columns: 1.2fr 1fr;
            gap: 28px;
            align-items: start;
        }

        @media (max-width: 1024px) {
            .workspace-layout {
                grid-template-columns: 1fr !important;
            }
        }

        /* Scrollbar styling for main content */
        .main-content::-webkit-scrollbar {
            width: 8px;
        }
        .main-content::-webkit-scrollbar-track {
            background: rgba(0, 0, 0, 0.1);
        }
        .main-content::-webkit-scrollbar-thumb {
            background: rgba(255, 255, 255, 0.1);
            border-radius: 4px;
        }
        .main-content::-webkit-scrollbar-thumb:hover {
            background: rgba(255, 255, 255, 0.2);
        }

        @media (max-width: 600px) {
            .form-row {
                grid-template-columns: 1fr !important;
            }
        }

        .panel {
            background: var(--card-bg);
            backdrop-filter: blur(16px);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            padding: 28px;
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
            background: rgba(255, 255, 255, 0.02);
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
            background: rgba(255, 255, 255, 0.04);
        }

        .list-item.selected {
            border-color: var(--accent-gold);
            background: rgba(255, 215, 0, 0.05);
            box-shadow: 0 0 12px var(--accent-gold-glow);
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
            font-size: 11px;
            font-weight: 700;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        input, select, textarea {
            background: rgba(0, 0, 0, 0.3);
            border: 1px solid var(--card-border);
            padding: 10px 14px;
            border-radius: 8px;
            color: var(--text-primary);
            font-size: 13.5px;
            outline: none;
            transition: all 0.2s;
            width: 100%;
            font-family: inherit;
        }

        select optgroup {
            background: #1a1a24;
            color: var(--text-secondary);
            font-weight: 600;
        }

        select option {
            background: #1a1a24;
            color: var(--text-primary);
        }

        input:focus, select:focus, textarea:focus {
            border-color: var(--accent-purple);
            box-shadow: 0 0 0 3px var(--accent-purple-glow);
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
            font-size: 13px;
            font-weight: 700;
            color: var(--accent-gold);
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
            background: rgba(4, 6, 10, 0.9);
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
            border-color: rgba(0, 241, 251, 0.3);
            box-shadow: inset 0 0 20px rgba(0, 241, 251, 0.05), 0 8px 32px rgba(0, 241, 251, 0.1);
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
            background: rgba(0, 241, 251, 0.3);
            border-radius: 3px;
        }
        .terminal-output::-webkit-scrollbar-thumb:hover {
            background: rgba(0, 241, 251, 0.5);
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
            background: rgba(0, 241, 251, 0.15);
        }

        .copy-btn-inline:focus-visible {
            outline: 2px solid var(--accent-cyan);
            outline-offset: 2px;
            background: rgba(0, 241, 251, 0.15);
        }

        /* Asset list */
        .asset-list {
            display: flex;
            flex-direction: column;
            gap: 10px;
        }

        .asset-item {
            background: rgba(255, 255, 255, 0.02);
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
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid var(--card-border);
            padding: 20px;
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 16px;
        }

        .instructions-panel {
            background: rgba(255, 255, 255, 0.01);
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
    <div class="app-layout">
        <aside class="sidebar">
            <div class="logo-container">
                <div class="logo">Saturn Console</div>
                <div class="logo-version">v2.0</div>
            </div>
            
            <!-- Active Workspace Picker in Sidebar -->
            <div class="sidebar-picker-section" id="sidebar-picker-section" style="display: none;">
                <label style="font-size: 10px; font-weight: 700; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 6px; display: block;">Active Workspace</label>
                <div class="workspace-pill">
                    <span class="badge badge-cyan" id="sidebar-app-type" style="font-size: 8px; padding: 2px 6px;">Chrome</span>
                    <span id="sidebar-app-title" style="font-weight: 700; font-size: 13.5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 140px;">App Name</span>
                </div>
            </div>

            <nav class="sidebar-nav">
                <button class="nav-btn active" id="tab-nav-dashboard" onclick="backToDashboard()">
                    <span class="nav-icon">📊</span> App Dashboard
                </button>
                <div class="nav-section-title" id="onboarding-nav-title" style="display: none;">Onboarding Steps</div>
                <button class="nav-btn" id="tab-nav-package" onclick="switchTab('package')" style="display: none;" disabled>
                    <span class="nav-icon">📦</span> 1. Package & Build
                </button>
                <button class="nav-btn" id="tab-nav-store" onclick="switchTab('store')" style="display: none;" disabled>
                    <span class="nav-icon">🎨</span> 2. Store Listing
                </button>
                <button class="nav-btn" id="tab-nav-secrets" onclick="switchTab('secrets')" style="display: none;" disabled>
                    <span class="nav-icon">🚀</span> 3. Secrets & CI/CD
                </button>
            </nav>
            
            <div class="sidebar-footer">
                <div class="gh-badge" id="gh-status-badge">
                    <span class="status-dot warning"></span> Loading GitHub CLI...
                </div>
            </div>
        </aside>

        <main class="main-content">
            <!-- Active App Bar (Sticky) -->
            <div id="active-app-bar" class="active-app-bar">
                <div style="display: flex; align-items: center; gap: 16px;">
                    <span class="badge badge-cyan" id="active-app-type-badge">Chrome Extension</span>
                    <div style="display: flex; flex-direction: column;">
                        <span id="active-app-title" style="font-family: 'Outfit', sans-serif; font-size: 16px; font-weight: 800; color: var(--text-primary);">App Name</span>
                        <span id="active-app-path" style="font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--text-muted);">Folder: git-personal/</span>
                    </div>
                    <div id="active-app-metadata-status"></div>
                </div>
                <div style="display: flex; align-items: center; gap: 16px;">
                    <!-- Dropdown to select module (shown if multi-module) -->
                    <div id="active-app-module-selector-container" style="display: none; align-items: center; gap: 8px;">
                        <label for="active-app-module-select" style="font-size: 11px; font-weight: 700; color: var(--text-secondary);">Select Module:</label>
                        <select id="active-app-module-select" onchange="onModuleSelectChange(this.value)" style="width: auto; padding: 6px 12px; background: rgba(10, 14, 23, 0.8); border: 1px solid var(--accent-cyan); border-radius: 6px; color: var(--text-primary); font-size: 13px; font-weight: 600;">
                        </select>
                    </div>
                    <button class="btn btn-secondary" onclick="backToDashboard()" style="padding: 8px 16px; font-size: 13px; font-weight: 600; border-radius: 8px;">
                        ← Back to Dashboard
                    </button>
                </div>
            </div>

            <div class="container">
        <!-- TAB 1: App Dashboard -->
        <div id="tab-content-dashboard" class="tab-content active">
            <div id="registry-dashboard-view" style="display: flex; flex-direction: column; gap: 24px; width: 100%;">
                <div style="display: flex; justify-content: space-between; align-items: center; gap: 20px; flex-wrap: wrap;">
                    <div style="display: flex; flex-direction: column; gap: 8px;">
                        <h2 style="font-family: 'Outfit'; font-size: 24px;">Central Application Registry</h2>
                        <p style="color: var(--text-secondary); font-size: 14px;">Review and manage deployment details, store listings, and CI/CD status for all your projects.</p>
                    </div>
                    <button class="btn btn-secondary" onclick="fetchReposAndStatus()" style="padding: 8px 16px; font-size: 13px; font-weight: 600; border-radius: 8px; display: flex; align-items: center; gap: 8px;">
                        🔄 Refresh Registry
                    </button>
                </div>

                <!-- KPI Row -->
                <div class="kpi-row">
                    <div class="kpi-card">
                        <div class="kpi-label">Total Applications</div>
                        <div class="kpi-value" id="kpi-total-apps">0</div>
                        <div class="kpi-sub">Monitored repositories</div>
                    </div>
                    <div class="kpi-card kpi-cyan">
                        <div class="kpi-label">Published Modules</div>
                        <div class="kpi-value" id="kpi-published-modules">0</div>
                        <div class="kpi-sub">Live in Production</div>
                    </div>
                    <div class="kpi-card kpi-gold">
                        <div class="kpi-label">Pending Setup</div>
                        <div class="kpi-value" id="kpi-pending-setup">0</div>
                        <div class="kpi-sub">Drafts or unconfigured</div>
                    </div>
                </div>

                <!-- Controls Row (Search, Filters, Sort) -->
                <div class="controls-row">
                    <div style="display: flex; gap: 12px; align-items: center; flex-wrap: wrap; flex: 1;">
                        <div class="search-container">
                            <span class="search-icon">🔍</span>
                            <input type="text" id="search-input" class="search-input" placeholder="Search applications..." aria-label="Search applications" oninput="handleSearch(this.value)">
                        </div>
                        <div class="dashboard-filters" style="margin: 0; padding: 0;">
                            <button class="filter-btn active" onclick="filterDashboard('all')" id="filter-btn-all" style="padding: 8px 16px; border-radius: 8px;">
                                All <span class="filter-count" id="filter-count-all">0</span>
                            </button>
                            <button class="filter-btn" onclick="filterDashboard('published')" id="filter-btn-published" style="padding: 8px 16px; border-radius: 8px;">
                                Published <span class="filter-count" id="filter-count-published">0</span>
                            </button>
                            <button class="filter-btn" onclick="filterDashboard('pending')" id="filter-btn-pending" style="padding: 8px 16px; border-radius: 8px;">
                                Pending <span class="filter-count" id="filter-count-pending">0</span>
                            </button>
                        </div>
                    </div>
                    <div class="sort-container">
                        <label for="sort-select" style="font-weight: 500;">Sort by:</label>
                        <select id="sort-select" class="sort-select" onchange="handleSort(this.value)">
                            <option value="name">Name (A-Z)</option>
                            <option value="build_date">Latest Build Date</option>
                        </select>
                    </div>
                </div>

                <!-- Registry Table Wrapper -->
                <div class="table-wrapper">
                    <table class="registry-table">
                        <thead>
                            <tr>
                                <th>Project Name & Path</th>
                                <th>Supported Modules</th>
                                <th>CI/CD Pipeline Run</th>
                                <th style="text-align: right;">Actions</th>
                            </tr>
                        </thead>
                        <tbody id="repos-table-body">
                            <!-- Repos are rendered dynamically here -->
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <!-- MISSING METADATA VIEW -->
        <div id="missing-metadata-view" style="display: none; flex-direction: column; align-items: center; justify-content: center; padding: 60px 20px; text-align: center; background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 16px; max-width: 600px; margin: 40px auto; gap: 20px; box-shadow: 0 8px 32px rgba(0,0,0,0.15);">
            <div style="font-size: 60px;">📄</div>
            <h2 id="missing-meta-title" style="font-family:'Outfit',sans-serif; font-size:22px;">Compliance metadata missing</h2>
            <p id="missing-meta-desc" style="color: var(--text-secondary); font-size: 14px; line-height: 1.6; max-width: 440px;">This app repository is missing the compliance <code>app-metadata.json</code> file. Click below to initialize it.</p>
            <button class="btn btn-primary" onclick="initializeMetadata()" style="padding: 12px 24px; font-size: 14px; font-weight:600; border-radius:8px;">Initialize app-metadata.json</button>
        </div>

        <!-- TAB 2: Package (formerly Builds & Assets) -->
        <div id="tab-content-package" class="tab-content" style="display: none;">
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
                    
                    <div id="save-metadata-success" class="badge badge-success" aria-live="polite" style="display: none; padding: 10px; width: 100%; justify-content: center; font-size: 12px; margin-bottom: 10px;">
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
                                <input type="text" id="meta-cws-short" maxlength="130" placeholder="A brief user-facing description...">
                            </div>
                            <div class="form-group">
                                <label for="meta-cws-long">Detailed Description</label>
                                <textarea id="meta-cws-long" placeholder="Describe the extension features, how to use it..."></textarea>
                            </div>
                            <div class="form-row">
                                <div class="form-group">
                                    <label for="meta-cws-purpose">Single Purpose (max 70 chars)</label>
                                    <input type="text" id="meta-cws-purpose" maxlength="70" placeholder="Define the primary action of this extension...">
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
                                <input type="text" id="meta-play-short" maxlength="80" placeholder="Summary of what the app does...">
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
                    <p class="panel-subtitle">Trigger the app-defined build script locally.</p>
                    
                    <div class="form-group">
                        <label for="package-build-script">Build Script Command</label>
                        <input type="text" id="package-build-script" placeholder="e.g. npm run build">
                    </div>
                    <div class="form-group" style="margin-top: 12px;">
                        <label for="package-artifact-path">Artifact Path (Target ZIP/APK/AAB)</label>
                        <input type="text" id="package-artifact-path" placeholder="e.g. initial-package.zip">
                    </div>
                    
                    <div style="background: rgba(30, 41, 59, 0.2); border: 1px solid var(--card-border); border-radius: 10px; padding: 16px; display: flex; align-items: center; justify-content: space-between; gap:12px; flex-wrap: wrap; margin-top: 8px;">
                        <div>
                            <div id="build-module-name-label" style="font-weight: 700; font-size: 14px;">Module name</div>
                            <div style="font-size: 11px; color: var(--text-muted); margin-top: 2px;">Ensure build generates artifact file.</div>
                        </div>
                        <div style="display: flex; gap: 8px; flex-wrap: wrap;">
                            <button class="btn btn-secondary" onclick="saveActiveTabMetadata('package')">Save Package Config</button>
                            <button class="btn btn-primary" id="btn-run-build" onclick="triggerBuild()">Execute Build</button>
                        </div>
                    </div>
                </div>

                <!-- Right column: Local Assets & Manifest Diagnostics -->
                <div style="display: flex; flex-direction: column; gap: 24px;">
                    <div class="panel">
                        <h2>Manifest & Compliance Diagnostics</h2>
                        <p class="panel-subtitle">Checks if local files conform to store upload rules.</p>
                        <div id="manifest-diagnostics-box" style="display: flex; flex-direction: column; gap: 10px;">
                            <!-- Populated dynamically via JS -->
                        </div>
                    </div>
                    
                    <div class="panel">
                        <h2>Local Assets Directory</h2>
                        <p class="panel-subtitle">Compiled ZIP, APK, or AAB files generated locally.</p>
                        <div class="asset-list" id="workspace-asset-list">
                            <!-- Loaded dynamically -->
                        </div>
                    </div>
                </div>

                <!-- Full-Width Bottom Section: Terminal Logs -->
                <div class="panel" style="grid-column: 1 / -1;">
                    <h2>Build Log Output</h2>
                    <p class="panel-subtitle">Standard output redirect from the background build executor.</p>
                    <div class="terminal-panel">
                        <div class="terminal-header">
                            <span class="terminal-title">Console Logs</span>
                            <span class="badge badge-cyan" id="build-status-badge" style="display: none;">Idle</span>
                        </div>
                        <div class="terminal-output" id="build-terminal-output">Ready to execute build command...</div>
                    </div>
                </div>
            </div>
        </div>

        <!-- TAB 3: Store Listing -->
        <div id="tab-content-store" class="tab-content" style="display: none;">
            <div class="workspace-layout" style="grid-template-columns: 1.2fr 1fr;">
                <!-- Left column: Product Details & Config -->
                <div class="panel">
                    <h2>Store Listing Configuration</h2>
                    <p class="panel-subtitle">Define the store listing details, privacy policies, reviewer instructions, and visibility settings.</p>
                    
                    <!-- Section: General Info -->
                    <div style="border-bottom: 1px solid rgba(255, 255, 255, 0.05); padding-bottom: 16px; margin-bottom: 8px;">
                        <h3 style="font-size: 14px; color: var(--accent-cyan); font-family: 'Outfit'; margin-bottom: 12px;">1. General Information</h3>
                        <div class="form-row">
                            <div class="form-group">
                                <label>Title from package</label>
                                <input type="text" id="store-title-package" readonly style="background: rgba(255,255,255,0.03); color: var(--text-secondary);">
                            </div>
                            <div class="form-group">
                                <label>Summary from package</label>
                                <input type="text" id="store-summary-package" readonly style="background: rgba(255,255,255,0.03); color: var(--text-secondary);">
                            </div>
                        </div>

                        <!-- Android Title (editable) -->
                        <div class="form-group" id="store-title-android-group" style="display: none; margin-top: 12px;">
                            <label for="store-title-android">Play Store App Title <span style="color: var(--error);" aria-hidden="true">*</span></label>
                            <input type="text" id="store-title-android" placeholder="User-facing app name..." required aria-required="true">
                        </div>

                        <!-- Short Description (editable for android) -->
                        <div class="form-group" id="store-short-android-group" style="display: none; margin-top: 12px;">
                            <label for="store-short-android">Short Description <span style="color: var(--error);" aria-hidden="true">*</span> (max 80 chars)</label>
                            <input type="text" id="store-short-android" placeholder="Summary of what the app does..." required aria-required="true">
                        </div>

                        <div class="form-group" style="margin-top: 12px;">
                            <label for="store-detailed-desc" id="store-desc-label">Detailed Description <span style="color: var(--error);" aria-hidden="true">*</span></label>
                            <textarea id="store-detailed-desc" style="min-height: 120px;" placeholder="Describe the extension features, how to use it, and why users should install it..." required aria-required="true"></textarea>
                        </div>

                        <div class="form-row" style="margin-top: 12px;">
                            <div class="form-group">
                                <label for="store-category">Category <span style="color: var(--error);" aria-hidden="true">*</span></label>
                                <select id="store-category" required aria-required="true">
                                    <!-- Dynamically populated based on type -->
                                </select>
                            </div>
                            <div class="form-group">
                                <label for="store-language">Default Language <span style="color: var(--error);" aria-hidden="true">*</span></label>
                                <select id="store-language" required aria-required="true">
                                    <option value="en">English</option>
                                    <option value="hi">Hindi</option>
                                    <option value="te">Telugu</option>
                                    <option value="es">Spanish</option>
                                    <option value="fr">French</option>
                                    <option value="de">German</option>
                                </select>
                            </div>
                        </div>
                    </div>

                    <!-- Section: Privacy & Policies -->
                    <div style="border-bottom: 1px solid rgba(255, 255, 255, 0.05); padding-bottom: 16px; margin-bottom: 8px;">
                        <h3 style="font-size: 14px; color: var(--accent-cyan); font-family: 'Outfit'; margin-bottom: 12px;">2. Privacy & Policies</h3>
                        
                        <div class="form-group" id="privacy-purpose-group">
                            <label for="privacy-single-purpose">Single Purpose Description <span style="color: var(--error);" aria-hidden="true">*</span> (max 1000 chars)</label>
                            <textarea id="privacy-single-purpose" style="min-height: 80px;" placeholder="Explain the single, narrow, and easy-to-understand purpose of your extension..." required aria-required="true"></textarea>
                        </div>
                        
                        <div class="form-group" style="margin-top: 12px;">
                            <label for="privacy-policy-url">Privacy Policy URL <span style="color: var(--error);" aria-hidden="true">*</span></label>
                            <input type="text" id="privacy-policy-url" placeholder="https://yourwebsite.com/privacy" required aria-required="true">
                        </div>

                        <!-- Chrome Extension specific CWS privacy questions -->
                        <div id="cws-privacy-extensions" style="margin-top: 12px; display: none; flex-direction: column; gap: 12px;">
                            <div class="form-group">
                                <label style="margin-bottom: 4px; display: block;">Are you using remote code? <span style="color: var(--error);" aria-hidden="true">*</span></label>
                                <div style="display: flex; gap: 24px; align-items: center; margin-top: 4px;">
                                    <label style="display: flex; align-items: center; gap: 8px; font-weight: normal; cursor: pointer; font-size: 12px;">
                                        <input type="radio" name="privacy-remote-code" id="remote-code-no" value="no" checked onchange="toggleRemoteCodeJustification(false)" required aria-required="true">
                                        <span>No, I am not using remote code</span>
                                    </label>
                                    <label style="display: flex; align-items: center; gap: 8px; font-weight: normal; cursor: pointer; font-size: 12px;">
                                        <input type="radio" name="privacy-remote-code" id="remote-code-yes" value="yes" onchange="toggleRemoteCodeJustification(true)" required aria-required="true">
                                        <span>Yes, I am using remote code</span>
                                    </label>
                                </div>
                            </div>

                            <div class="form-group" id="privacy-remote-justification-group" style="display: none;">
                                <label for="privacy-remote-justification">Remote Code Justification <span style="color: var(--error);" aria-hidden="true">*</span> (max 1000 chars)</label>
                                <textarea id="privacy-remote-justification" style="min-height: 80px;" placeholder="Explain why your extension requires remote code and what functions it performs..." required aria-required="true"></textarea>
                            </div>

                            <div class="form-group">
                                <label style="display: flex; align-items: flex-start; gap: 8px; font-weight: normal; cursor: pointer; font-size: 12px;">
                                    <input type="checkbox" id="privacy-certify-policy" style="margin-top: 3px;" required aria-required="true">
                                    <span>I certify that my data usage complies with the Chrome Web Store Developer Program Policies. <span style="color: var(--error);" aria-hidden="true">*</span></span>
                                </label>
                            </div>
                        </div>
                    </div>


                    <!-- Section: Distribution & Access -->
                    <div>
                        <h3 style="font-size: 14px; color: var(--accent-cyan); font-family: 'Outfit'; margin-bottom: 12px;">3. Distribution & Reviewer Access</h3>
                        
                        <div class="form-row">
                            <div class="form-group">
                                <label for="dist-visibility">Visibility / Publish State <span style="color: var(--error);" aria-hidden="true">*</span></label>
                                <select id="dist-visibility" required aria-required="true">
                                    <option value="public">Public (Everyone can see it)</option>
                                    <option value="unlisted">Unlisted (Only users with link)</option>
                                    <option value="private">Private (Only developer account / test group)</option>
                                </select>
                            </div>
                            <div class="form-group">
                                <label for="dist-regions">Target Regions <span style="color: var(--error);" aria-hidden="true">*</span></label>
                                <select id="dist-regions" required aria-required="true">
                                    <option value="all">All Regions / Global</option>
                                    <option value="selected">Selected Regions (India, USA)</option>
                                </select>
                            </div>
                        </div>

                        <div class="form-row" style="margin-top: 12px;">
                            <div class="form-group">
                                <label for="dist-store-id">Store App / Package ID</label>
                                <input type="text" id="dist-store-id" placeholder="e.g. nkbihfbeogaeaoehlefnkodbefgpgknn (chrome) or com.app.package (android)">
                            </div>
                            <div class="form-group">
                                <label for="dist-store-url">Public Store Listing URL</label>
                                <input type="text" id="dist-store-url" placeholder="https://chromewebstore.google.com/detail/...">
                            </div>
                        </div>

                        <div class="form-group" style="margin-top: 12px;">
                            <label for="access-test-instructions">Reviewer Test Instructions <span style="color: var(--error);" aria-hidden="true">*</span></label>
                            <textarea id="access-test-instructions" style="min-height: 80px;" placeholder="Provide step-by-step instructions on how to test the extension features. Mention if mock credentials or setup is required..." required aria-required="true"></textarea>
                        </div>
                    </div>

                    <div class="btn-row" style="margin-top: 20px; border-top: 1px solid rgba(255, 255, 255, 0.05); padding-top: 20px;">
                        <div></div>
                        <button class="btn btn-primary" onclick="saveActiveTabMetadata('store')" style="max-width: 200px;">Save Store Listing</button>
                    </div>
                </div>

                <!-- Right column: Graphic Assets & Permission Justifications -->
                <div style="display: flex; flex-direction: column; gap: 24px;">
                    <div class="panel" id="cws-preflight-panel" style="display: none;">
                        <h2>Pre-flight Checklist</h2>
                        <p class="panel-subtitle">Verifies that the extension meets all Chrome Web Store listing rules.</p>
                        <div id="cws-preflight-box" style="display: flex; flex-direction: column; gap: 14px;">
                            <!-- Populated dynamically via JS -->
                        </div>
                    </div>

                    <div class="panel">
                        <h2>Graphic Assets</h2>
                        <p class="panel-subtitle">Verifies that the required store graphics exist locally.</p>
                        <div id="graphic-assets-box" style="display: flex; flex-direction: column; gap: 12px;">
                            <!-- Populated dynamically via JS -->
                        </div>
                    </div>

                    <div class="panel" id="privacy-permissions-panel" style="display: none;">
                        <h2>Permission Justifications</h2>
                        <p class="panel-subtitle">Chrome Web Store requires explanations for each permission declared in manifest.json.</p>
                        <div id="permissions-justifications-box" style="display: flex; flex-direction: column; gap: 14px;">
                            <!-- Populated dynamically via JS -->
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- TAB 7: Secrets & CI/CD Onboarding -->
        <div id="tab-content-secrets" class="tab-content" style="display: none;">
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

                    <div id="secrets-copy-assets-container" style="display: flex; flex-direction: column; gap: 16px;">
                        <!-- Dynamically populated via JS -->
                    </div>
                </div>

                <h2>Automated GitHub Actions Secret Provisioning</h2>
                <p class="panel-subtitle">Link your app with central reusable workflows by securely sending Client credentials to GitHub secrets</p>

                <div class="instructions-panel" style="margin-bottom: 20px;">
                    <strong>Google Developer API Integration steps:</strong>
                    <ol>
                        <li>Access the <a href="https://console.cloud.google.com" target="_blank">Google Cloud Console</a>.</li>
                        <li>Enable the <strong>Chrome Web Store API</strong> or <strong>Google Play Android Developer API</strong>.</li>
                        <li>Configure the OAuth client ID for a Web Application and add the redirect URI: <code style="color:var(--accent-cyan);">http://localhost:3005/oauth-callback</code>.</li>
                        <li>Input your Client ID and Client Secret below, click Authorize, then send secrets directly to GitHub.</li>
                    </ol>
                </div>

                <div id="secrets-alert-box" class="alert alert-error" aria-live="polite" style="display: none; padding: 12px; border-radius: 8px; font-size: 13px; margin-bottom: 16px;"></div>

                <div class="form-row" style="margin-bottom: 16px;">
                    <div class="form-group">
                        <label for="secrets-client-id">OAuth Client ID <span style="color: var(--error);" aria-hidden="true">*</span></label>
                        <input type="text" id="secrets-client-id" placeholder="Enter Client ID" required aria-required="true">
                    </div>
                    <div class="form-group">
                        <label for="secrets-client-secret">OAuth Client Secret <span style="color: var(--error);" aria-hidden="true">*</span></label>
                        <input type="password" id="secrets-client-secret" placeholder="Enter Client Secret" required aria-required="true">
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
                    <button class="btn btn-primary" id="btn-provision-secrets" onclick="provisionSecrets()" aria-disabled="true" title="Authenticate with Google OAuth first to enable secret provisioning." style="max-width: 280px;">
                        🚀 Send API Secrets to GitHub Repository
                    </button>
                </div>
            </div>
        </div>
    </div>
        </main>
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
            activeBuildId: null,
            dashboardFilter: 'all',
            searchQuery: '',
            sortBy: 'name'
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

                    // Initial render of dashboard to show "checking runs"
                    renderReposDashboard();
                    
                    // Fetch runs for all repos proactively
                    state.repos.forEach(repo => {
                        fetchRepoRuns(repo);
                    });
                    
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

        function toggleRemoteCodeJustification(show) {
            const group = document.getElementById("privacy-remote-justification-group");
            if (group) {
                group.style.display = show ? "block" : "none";
            }
        }

        function renderPreflightChecklist() {
            const repo = state.selectedRepo;
            const mod = repo.metadata.modules[state.selectedModuleIdx];
            const panel = document.getElementById("cws-preflight-panel");
            const box = document.getElementById("cws-preflight-box");
            
            if (mod.type !== "chrome-extension") {
                panel.style.display = "none";
                return;
            }
            
            panel.style.display = "flex";
            box.innerHTML = `<p style="font-size:12px; color:var(--text-secondary);">Analyzing pre-flight parameters...</p>`;
            
            const info = repo.manifest_info || {};
            const cws = mod.cwsListing || {};
            
            // 1. Description Length check
            const desc = info.description || "";
            const descOk = desc.length > 0 && desc.length <= 132;
            const descMsg = descOk 
                ? `🟢 Description is CWS-compliant (${desc.length}/132 chars)`
                : `🔴 Description length must be 1-132 chars (currently ${desc.length} chars)`;
                
            // 2. Icon 128x128 check
            const icons = info.icons || {};
            const icon128 = icons["128"] || {};
            const iconOk = icon128.exists === true;
            const iconMsg = iconOk
                ? `🟢 Store Icon (128x128) exists locally`
                : `🔴 Missing Store Icon (128x128) in manifest or on disk`;
                
            // 3. Screenshots check
            const screens = info.screenshots || [];
            const screenOk = screens.length >= 1;
            const screenMsg = screenOk
                ? `🟢 Found ${screens.length} screenshots (at least 1 required)`
                : `🔴 CWS requires at least 1 screenshot (1280x800 or 640x400)`;
                
            // 4. Privacy policy link check
            const privacyUrl = cws.privacyPolicyUrl || "";
            const privacySet = privacyUrl.trim().length > 0;
            
            box.innerHTML = `
                <div class="preflight-item" style="display:flex; flex-direction:column; gap:6px; padding:10px; background:rgba(255,255,255,0.02); border-radius:6px; border:1px solid rgba(255,255,255,0.05);">
                    <div style="font-size:12px; color: ${descOk ? 'var(--success)' : 'var(--error)'}; font-weight: 500;">
                        ${descOk ? '✅' : '❌'} Description: ${descMsg}
                    </div>
                </div>
                <div class="preflight-item" style="display:flex; flex-direction:column; gap:6px; padding:10px; background:rgba(255,255,255,0.02); border-radius:6px; border:1px solid rgba(255,255,255,0.05);">
                    <div style="font-size:12px; color: ${iconOk ? 'var(--success)' : 'var(--error)'}; font-weight: 500;">
                        ${iconOk ? '✅' : '❌'} Icon Check: ${iconMsg}
                    </div>
                </div>
                <div class="preflight-item" style="display:flex; flex-direction:column; gap:6px; padding:10px; background:rgba(255,255,255,0.02); border-radius:6px; border:1px solid rgba(255,255,255,0.05);">
                    <div style="font-size:12px; color: ${screenOk ? 'var(--success)' : 'var(--error)'}; font-weight: 500;">
                        ${screenOk ? '✅' : '❌'} Screenshots: ${screenMsg}
                    </div>
                </div>
                <div class="preflight-item" id="preflight-privacy-item" style="display:flex; flex-direction:column; gap:6px; padding:10px; background:rgba(255,255,255,0.02); border-radius:6px; border:1px solid rgba(255,255,255,0.05);">
                    <div style="font-size:12px; color:var(--text-primary); font-weight:500;">
                        ⏳ Privacy Policy: Checking URL reachability...
                    </div>
                </div>
            `;
            
            if (privacySet) {
                fetch(`/api/check-privacy-url?url=${encodeURIComponent(privacyUrl)}`)
                    .then(res => res.json())
                    .then(data => {
                        const item = document.getElementById("preflight-privacy-item");
                        if (!item) return;
                        
                        if (data.success && data.reachable) {
                            item.innerHTML = `
                                <div style="font-size:12px; color:var(--success); font-weight: 500;">
                                    ✅ Privacy Policy URL is reachable (HTTP 200)
                                </div>
                                <div style="font-size:11px; color:var(--text-muted); margin-top:2px;">
                                    URL: <a href="${privacyUrl}" target="_blank" style="color:var(--accent-cyan); text-decoration:underline;">${privacyUrl}</a>
                                </div>
                            `;
                        } else {
                            item.innerHTML = `
                                <div style="font-size:12px; color:var(--error); font-weight: 500;">
                                    ❌ Privacy Policy URL is unreachable (${data.error || 'Connection Failed'})
                                </div>
                                <div style="font-size:11px; color:var(--text-muted); margin-top:2px; margin-bottom: 6px;">
                                    URL: <a href="${privacyUrl}" target="_blank" style="color:var(--error); text-decoration:underline;">${privacyUrl}</a>
                                </div>
                                <button class="btn btn-secondary" onclick="generatePrivacyHtml()" style="padding: 4px 8px; font-size: 11px; max-width: 200px;">
                                    🔧 Fix / Generate privacy.html
                                </button>
                            `;
                        }
                    })
                    .catch(err => {
                        const item = document.getElementById("preflight-privacy-item");
                        if (item) {
                            item.innerHTML = `
                                <div style="font-size:12px; color:var(--error); font-weight: 500;">
                                    ❌ Reachability check failed: ${err}
                                </div>
                            `;
                        }
                    });
            } else {
                const item = document.getElementById("preflight-privacy-item");
                if (item) {
                    item.innerHTML = `
                        <div style="font-size:12px; color:var(--error); font-weight: 500;">
                            ❌ Privacy Policy URL is not set
                        </div>
                        <button class="btn btn-secondary" onclick="generatePrivacyHtml()" style="padding: 4px 8px; font-size: 11px; max-width: 200px; margin-top: 6px;">
                            🔧 Fix / Generate privacy.html
                        </button>
                    `;
                }
            }
        }

        function showToast(message, isError = false) {
            const toast = document.createElement("div");
            toast.setAttribute("aria-live", "polite");
            toast.style.position = "fixed";
            toast.style.bottom = "20px";
            toast.style.right = "20px";
            toast.style.background = isError ? "var(--error)" : "var(--success)";
            toast.style.color = "white";
            toast.style.padding = "12px 24px";
            toast.style.borderRadius = "8px";
            toast.style.boxShadow = "0 4px 12px rgba(0,0,0,0.2)";
            toast.style.zIndex = "1000";
            toast.style.fontWeight = "bold";
            toast.style.whiteSpace = "pre-line";
            toast.innerText = message;
            document.body.appendChild(toast);
            setTimeout(() => toast.remove(), 4000);
        }

        function generatePrivacyHtml() {
            const repo = state.selectedRepo;
            fetch('/api/generate-privacy-html', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: repo.path })
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    showToast("✅ Generated privacy.html in your repository root.\n\nTo make it public:\n1. Commit and push it.\n2. Enable GitHub Pages.");
                    renderPreflightChecklist();
                } else {
                    showToast("❌ Failed to generate privacy.html: " + data.error, true);
                }
            })
            .catch(err => showToast("Error: " + err, true));
        }

        function switchTab(tabName) {
            const tabs = ['dashboard', 'package', 'store', 'secrets'];
            tabs.forEach(t => {
                const content = document.getElementById(`tab-content-${t}`);
                if (content) {
                    content.classList.remove('active');
                    content.style.display = 'none';
                }
            });
            
            const activeContent = document.getElementById(`tab-content-${tabName}`);
            if (activeContent) {
                activeContent.classList.add('active');
                activeContent.style.display = 'flex';
            }
            
            document.querySelectorAll('.nav-btn').forEach(btn => {
                btn.classList.remove('active');
            });
            
            const activeBtn = document.getElementById(`tab-nav-${tabName}`);
            if (activeBtn) activeBtn.classList.add('active');
            
            state.currentTab = tabName;

            // Reset main content scroll position to top on tab transitions
            const mainContent = document.querySelector('.main-content');
            if (mainContent) {
                mainContent.scrollTop = 0;
            }
        }

        function filterDashboard(filterName) {
            state.dashboardFilter = filterName;
            document.querySelectorAll('.filter-btn').forEach(btn => {
                btn.classList.remove('active');
            });
            const activeBtn = document.getElementById(`filter-btn-${filterName}`);
            if (activeBtn) activeBtn.classList.add('active');
            renderReposDashboard();
        }

        function handleSearch(query) {
            state.searchQuery = query;
            renderReposDashboard();
        }

        function handleSort(sortBy) {
            state.sortBy = sortBy;
            renderReposDashboard();
        }

        function formatRelativeTime(isoString) {
            if (!isoString) return "";
            const date = new Date(isoString);
            const now = new Date();
            const diffMs = now - date;
            const diffMins = Math.floor(diffMs / 60000);
            const diffHours = Math.floor(diffMins / 60);
            const diffDays = Math.floor(diffHours / 24);
            
            if (diffMins < 1) return "Just now";
            if (diffMins < 60) return `${diffMins}m ago`;
            if (diffHours < 24) return `${diffHours}h ago`;
            if (diffDays === 1) return "Yesterday";
            return `${diffDays}d ago`;
        }

        function updateFilterCounts() {
            let publishedCount = 0;
            let pendingCount = 0;

            state.repos.forEach(repo => {
                let isPublished = false;
                if (repo.metadata_exists && repo.metadata.modules) {
                    isPublished = repo.metadata.modules.some(m => m.status === "published");
                }
                if (isPublished) publishedCount++;
                else pendingCount++;
            });

            const allCountEl = document.getElementById("filter-count-all");
            const pubCountEl = document.getElementById("filter-count-published");
            const penCountEl = document.getElementById("filter-count-pending");
            if (allCountEl) allCountEl.innerText = state.repos.length;
            if (pubCountEl) pubCountEl.innerText = publishedCount;
            if (penCountEl) penCountEl.innerText = pendingCount;
        }

        function updateKpiStats() {
            let totalApps = state.repos.length;
            let publishedModules = 0;
            let pendingSetup = 0;

            state.repos.forEach(repo => {
                if (repo.metadata_exists && repo.metadata.modules) {
                    repo.metadata.modules.forEach(m => {
                        if (m.status === "published") {
                            publishedModules++;
                        } else {
                            pendingSetup++;
                        }
                    });
                } else {
                    pendingSetup++;
                }
            });

            const totalAppsEl = document.getElementById("kpi-total-apps");
            const pubModsEl = document.getElementById("kpi-published-modules");
            const penSetupEl = document.getElementById("kpi-pending-setup");

            if (totalAppsEl) totalAppsEl.innerText = totalApps;
            if (pubModsEl) pubModsEl.innerText = publishedModules;
            if (penSetupEl) penSetupEl.innerText = pendingSetup;
        }

        function renderReposDashboard() {
            const registryView = document.getElementById("registry-dashboard-view");
            if (state.selectedRepo) {
                if (registryView) registryView.style.display = "none";
                return;
            } else {
                if (registryView) registryView.style.display = "flex";
            }

            const tbody = document.getElementById("repos-table-body");
            if (!tbody) return;
            tbody.innerHTML = "";

            updateFilterCounts();
            updateKpiStats();

            if (state.repos.length === 0) {
                tbody.innerHTML = `<tr><td colspan="4" style="text-align: center; padding: 40px; color: var(--text-secondary);">No repositories detected in the git-personal folder.</td></tr>`;
                return;
            }

            // Filter
            let filteredRepos = state.repos.filter(repo => {
                // Search query match
                const matchSearch = repo.appName.toLowerCase().includes(state.searchQuery.toLowerCase()) || 
                                    repo.name.toLowerCase().includes(state.searchQuery.toLowerCase());
                if (!matchSearch) return false;

                // Status filter match
                let isPublished = false;
                if (repo.metadata_exists && repo.metadata.modules) {
                    isPublished = repo.metadata.modules.some(m => m.status === "published");
                }

                if (state.dashboardFilter === "published" && !isPublished) return false;
                if (state.dashboardFilter === "pending" && isPublished) return false;

                return true;
            });

            // Sort
            filteredRepos.sort((a, b) => {
                if (state.sortBy === "name") {
                    return a.appName.toLowerCase().localeCompare(b.appName.toLowerCase());
                } else if (state.sortBy === "build_date") {
                    const timeA = a.latestRun ? new Date(a.latestRun.createdAt).getTime() : 0;
                    const timeB = b.latestRun ? new Date(b.latestRun.createdAt).getTime() : 0;
                    return timeB - timeA; // Latest first
                }
                return 0;
            });

            if (filteredRepos.length === 0) {
                tbody.innerHTML = `<tr><td colspan="4" style="text-align: center; padding: 40px; color: var(--text-secondary);">No repositories match the selected filters.</td></tr>`;
                return;
            }

            filteredRepos.forEach(repo => {
                // Resolve icon
                let icon = "📁";
                if (repo.appType === "chrome-extension") icon = "🧩";
                else if (repo.appType === "flutter-app" || repo.appType === "android-app") icon = "📱";

                // Render modules inline listing (chips)
                let modulesHtml = "";
                if (repo.metadata_exists && repo.metadata.modules) {
                    repo.metadata.modules.forEach(m => {
                        let dotClass = "dot-draft";
                        if (m.status === "published") dotClass = "dot-published";
                        else if (m.status === "beta") dotClass = "dot-beta";
                        
                        modulesHtml += `
                            <div class="module-chip" style="margin-right: 6px; margin-bottom: 6px; display: inline-flex;">
                                <span class="dot ${dotClass}"></span>
                                <span>${m.name}</span>
                            </div>
                        `;
                    });
                } else {
                    modulesHtml = `
                        <div class="module-chip" style="display: inline-flex;">
                            <span class="dot dot-missing"></span>
                            <span>Inferred: ${repo.inferredType}</span>
                        </div>
                    `;
                }

                // Resolve CI/CD status
                let cicdHtml = `<span style="color: var(--text-muted); font-style: italic;">No runs detected</span>`;
                if (repo.latestRun) {
                    const run = repo.latestRun;
                    let dot = "🟡";
                    if (run.conclusion === "success") {
                        dot = "🟢";
                    } else if (run.conclusion === "failure") {
                        dot = "🔴";
                    }
                    const timeStr = formatRelativeTime(run.createdAt);
                    cicdHtml = `
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <span style="font-size: 14px;">${dot}</span>
                            <div style="display: flex; flex-direction: column;">
                                <span style="font-weight: 600; color: var(--text-primary); font-size: 13px;">${run.name}</span>
                                <span style="font-size: 11px; color: var(--text-muted);">${timeStr}</span>
                            </div>
                        </div>
                    `;
                } else if (repo.latestRun === undefined) {
                    // still checking runs
                    cicdHtml = `
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <span class="status-dot warning" style="animation: pulse 1.5s infinite; width: 8px; height: 8px;"></span>
                            <span style="font-size: 12px; color: var(--text-muted);">Checking runs...</span>
                        </div>
                    `;
                }

                const tr = document.createElement("tr");
                tr.onclick = () => openRepoWorkspace(repo.name);
                tr.innerHTML = `
                    <td>
                        <div style="display: flex; align-items: center; gap: 12px;">
                            <span style="font-size: 20px;">${icon}</span>
                            <div class="project-name-col">
                                <span class="project-title">${repo.appName}</span>
                                <span class="project-path">git-personal/${repo.name}/</span>
                            </div>
                        </div>
                    </td>
                    <td>
                        <div style="display: flex; flex-wrap: wrap; max-width: 320px;">
                            ${modulesHtml}
                        </div>
                    </td>
                    <td>
                        ${cicdHtml}
                    </td>
                    <td style="text-align: right;">
                        <button class="btn-table-action" onclick="event.stopPropagation(); openRepoWorkspace('${repo.name}')">Manage Workspace →</button>
                    </td>
                `;
                tbody.appendChild(tr);
            });
        }

        function fetchRepoRuns(repo) {
            // Set to undefined first to show loading state
            repo.latestRun = undefined;
            renderReposDashboard();

            fetch(`/api/cicd-status?path=${encodeURIComponent(repo.path)}`)
                .then(res => res.json())
                .then(data => {
                    if (data.success && data.runs && data.runs.length > 0) {
                        repo.latestRun = data.runs[0];
                    } else {
                        repo.latestRun = null;
                    }
                    renderReposDashboard();
                })
                .catch(err => {
                    console.error("Error fetching run status:", err);
                    repo.latestRun = null;
                    renderReposDashboard();
                });
        }

        function openRepoWorkspace(repoName) {
            const repo = state.repos.find(r => r.name === repoName);
            if (repo) {
                selectRepo(repo);
            }
        }

        function selectRepo(repo) {
            state.selectedRepo = repo;
            state.selectedModuleIdx = 0;
            
            // Hide the registry dashboard view
            const registryView = document.getElementById("registry-dashboard-view");
            if (registryView) registryView.style.display = "none";
            
            // Show Active App Bar
            const appBar = document.getElementById("active-app-bar");
            appBar.style.display = "flex";
            
            document.getElementById("active-app-title").innerText = repo.appName;
            document.getElementById("active-app-path").innerText = `Folder: git-personal/${repo.name}/`;
            
            // App Type badge
            let typeBadge = repo.appType;
            if (repo.appType === "chrome-extension") typeBadge = "Chrome Extension";
            else if (repo.appType === "flutter-app") typeBadge = "Flutter App";
            else if (repo.appType === "android-app") typeBadge = "Android App";
            else if (repo.appType === "multi-module") typeBadge = "Multi-Module / Hybrid";
            document.getElementById("active-app-type-badge").innerText = typeBadge;
            
            // Set metadata status
            const statusEl = document.getElementById("active-app-metadata-status");
            if (repo.metadata_exists) {
                statusEl.innerHTML = `<span class="badge badge-success">Metadata Compliant</span>`;
            } else {
                statusEl.innerHTML = `<span class="badge badge-error">Missing Metadata</span>`;
            }
            
            // Update sidebar workspace picker
            const sidebarPicker = document.getElementById("sidebar-picker-section");
            if (sidebarPicker) {
                sidebarPicker.style.display = "block";
                document.getElementById("sidebar-app-title").innerText = repo.appName;
                
                let typeText = "App";
                if (repo.appType === "chrome-extension") typeText = "Chrome";
                else if (repo.appType === "flutter-app") typeText = "Flutter";
                else if (repo.appType === "android-app") typeText = "Android";
                else if (repo.appType === "multi-module") typeText = "Hybrid";
                
                const typeBadge = document.getElementById("sidebar-app-type");
                typeBadge.innerText = typeText;
                
                // Clear type badge classes and set the correct one
                typeBadge.className = "badge";
                if (repo.appType === "chrome-extension") typeBadge.classList.add("badge-cyan");
                else if (repo.appType === "flutter-app") typeBadge.classList.add("badge-purple");
                else if (repo.appType === "android-app") typeBadge.classList.add("badge-success");
                else typeBadge.classList.add("badge-purple");
            }
            
            // Update dashboard button to back button indicator
            const dashboardBtn = document.getElementById("tab-nav-dashboard");
            if (dashboardBtn) {
                dashboardBtn.innerHTML = `<span class="nav-icon">⬅️</span> Back to Dashboard`;
            }
            
            // Setup module selector if multi-module
            setupModuleSelector();
            
            // If metadata exists, show tabs and populate forms
            if (repo.metadata_exists) {
                document.getElementById("missing-metadata-view").style.display = "none";
                enableOnboardingTabs(true);
                populateMetadataForms();
                switchTab('package'); // Auto switch to first onboarding tab
            } else {
                document.getElementById("missing-metadata-view").style.display = "flex";
                enableOnboardingTabs(false);
                hideAllOnboardingContents();
                // Ensure only dashboard is active
                switchTab('dashboard');
                // Selectively show the missing metadata banner instead of onboarding contents
                document.getElementById("missing-metadata-view").style.display = "flex";
                document.getElementById("active-app-bar").style.display = "flex";
            }
        }

        function enableOnboardingTabs(enable) {
            const tabs = ['package', 'store', 'secrets'];
            tabs.forEach(t => {
                const btn = document.getElementById(`tab-nav-${t}`);
                if (btn) {
                    btn.disabled = !enable;
                    btn.style.display = enable ? "flex" : "none";
                }
            });
            const onboardingTitle = document.getElementById("onboarding-nav-title");
            if (onboardingTitle) onboardingTitle.style.display = enable ? "block" : "none";
        }

        function hideAllOnboardingContents() {
            const tabs = ['package', 'store', 'secrets'];
            tabs.forEach(t => {
                const content = document.getElementById(`tab-content-${t}`);
                if (content) content.classList.remove('active');
            });
        }

        function setupModuleSelector() {
            const container = document.getElementById("active-app-module-selector-container");
            const select = document.getElementById("active-app-module-select");
            
            if (state.selectedRepo.metadata_exists && state.selectedRepo.metadata.modules && state.selectedRepo.metadata.modules.length > 1) {
                container.style.display = "flex";
                select.innerHTML = "";
                state.selectedRepo.metadata.modules.forEach((mod, idx) => {
                    const opt = document.createElement("option");
                    opt.value = idx;
                    opt.text = `${mod.name} (${mod.type})`;
                    if (idx === state.selectedModuleIdx) opt.selected = true;
                    select.appendChild(opt);
                });
            } else {
                container.style.display = "none";
            }
        }

        function onModuleSelectChange(val) {
            state.selectedModuleIdx = parseInt(val);
            populateMetadataForms();
        }

        function backToDashboard() {
            state.selectedRepo = null;
            state.selectedModuleIdx = 0;
            
            // Hide active app bar and missing metadata banner
            document.getElementById("active-app-bar").style.display = "none";
            document.getElementById("missing-metadata-view").style.display = "none";
            
            // Disable and hide onboarding tabs
            enableOnboardingTabs(false);
            
            // Hide sidebar workspace picker and onboarding title
            const sidebarPicker = document.getElementById("sidebar-picker-section");
            if (sidebarPicker) sidebarPicker.style.display = "none";
            const onboardingTitle = document.getElementById("onboarding-nav-title");
            if (onboardingTitle) onboardingTitle.style.display = "none";
            
            // Restore dashboard button text
            const dashboardBtn = document.getElementById("tab-nav-dashboard");
            if (dashboardBtn) {
                dashboardBtn.innerHTML = `<span class="nav-icon">📊</span> App Dashboard`;
            }
            
            // Switch to dashboard tab
            switchTab('dashboard');
            
            // Refresh dashboard
            fetchReposAndStatus();
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

        function populateMetadataForms() {
            const repo = state.selectedRepo;
            const meta = repo.metadata;
            if (!meta) return;
            
            const mod = meta.modules[state.selectedModuleIdx];
            if (!mod) return;
            
            // Package tab inputs
            document.getElementById("package-build-script").value = mod.buildScript || "";
            document.getElementById("package-artifact-path").value = mod.artifactPath || "";
            document.getElementById("build-module-name-label").innerText = `${repo.appName} — ${mod.name}`;
            
            // Execute assets reload
            fetchRepoAssets();
            setupBuildExecutorPanel();
            
            // Diagnostics
            runManifestDiagnostics();
            
            // Store Listing tab inputs
            const isChrome = mod.type === "chrome-extension";
            
            // Populate category select list dynamically
            const categorySelect = document.getElementById("store-category");
            categorySelect.innerHTML = "";
            if (isChrome) {
                // Chrome Web Store grouped categories
                const cwsGroups = {
                    "PRODUCTIVITY": [
                        { value: "communication", label: "Communication" },
                        { value: "developer", label: "Developer Tools" },
                        { value: "education", label: "Education" },
                        { value: "tools", label: "Tools" },
                        { value: "workflow", label: "Workflow and planning" }
                    ],
                    "LIFESTYLE": [
                        { value: "art", label: "Art & Design" },
                        { value: "entertainment", label: "Entertainment" },
                        { value: "games", label: "Games" },
                        { value: "household", label: "Household" },
                        { value: "news", label: "News" },
                        { value: "shopping", label: "Shopping" },
                        { value: "social", label: "Social" },
                        { value: "travel", label: "Travel" },
                        { value: "wellbeing", label: "Well-being" }
                    ],
                    "MAKE CHROME YOURS": [
                        { value: "accessibility", label: "Accessibility" },
                        { value: "functionality", label: "Functionality" },
                        { value: "privacy", label: "Privacy & Security" }
                    ]
                };

                for (const [groupLabel, categories] of Object.entries(cwsGroups)) {
                    const group = document.createElement("optgroup");
                    group.label = groupLabel;
                    categories.forEach(c => {
                        const opt = document.createElement("option");
                        opt.value = c.value;
                        opt.text = c.label;
                        group.appendChild(opt);
                    });
                    categorySelect.appendChild(group);
                }
                
                // Set store titles from manifest/package
                document.getElementById("store-title-package").value = (repo.manifest_info && repo.manifest_info.name) || repo.appName;
                document.getElementById("store-summary-package").value = (repo.manifest_info && repo.manifest_info.description) || "";
                
                // Hide Android specific title/short desc
                document.getElementById("store-title-android-group").style.display = "none";
                document.getElementById("store-short-android-group").style.display = "none";
                
                // Populate description and category
                if (mod.cwsListing) {
                    document.getElementById("store-detailed-desc").value = mod.cwsListing.detailedDescription || "";
                    let catVal = mod.cwsListing.category || "tools";
                    // Map legacy/invalid values to clean defaults
                    if (catVal === "productivity") catVal = "tools";
                    if (catVal === "search") catVal = "tools";
                    if (catVal === "fun") catVal = "games";
                    if (catVal === "social") catVal = "social";
                    categorySelect.value = catVal;
                    document.getElementById("store-language").value = mod.cwsListing.language || "en";
                }
                
                // Populate Privacy Single Purpose
                document.getElementById("privacy-purpose-group").style.display = "flex";
                if (mod.cwsListing) {
                    document.getElementById("privacy-single-purpose").value = mod.cwsListing.singlePurpose || "";
                    document.getElementById("privacy-policy-url").value = mod.cwsListing.privacyPolicyUrl || "";
                    
                    // Show CWS privacy questions
                    document.getElementById("cws-privacy-extensions").style.display = "flex";
                    
                    const remoteUsed = mod.cwsListing.remoteCodeUsed === true;
                    document.getElementById("remote-code-yes").checked = remoteUsed;
                    document.getElementById("remote-code-no").checked = !remoteUsed;
                    toggleRemoteCodeJustification(remoteUsed);
                    
                    document.getElementById("privacy-remote-justification").value = mod.cwsListing.remoteCodeJustification || "";
                    document.getElementById("privacy-certify-policy").checked = mod.cwsListing.dataUsageCertified === true;
                } else {
                    document.getElementById("cws-privacy-extensions").style.display = "none";
                }
                
                // Permissions justifications panel
                document.getElementById("privacy-permissions-panel").style.display = "flex";
                renderPermissionJustifications();
                
            } else { // Flutter/Android App
                // Google Play Console grouped categories (Apps vs Games)
                const playGroups = {
                    "APPS": [
                        { value: "art-design", label: "Art & Design" },
                        { value: "auto-vehicles", label: "Auto & Vehicles" },
                        { value: "beauty", label: "Beauty" },
                        { value: "books-reference", label: "Books & Reference" },
                        { value: "business", label: "Business" },
                        { value: "comics", label: "Comics" },
                        { value: "communication", label: "Communication" },
                        { value: "dating", label: "Dating" },
                        { value: "education", label: "Education" },
                        { value: "entertainment", label: "Entertainment" },
                        { value: "events", label: "Events" },
                        { value: "finance", label: "Finance" },
                        { value: "food-drink", label: "Food & Drink" },
                        { value: "health-fitness", label: "Health & Fitness" },
                        { value: "house-home", label: "House & Home" },
                        { value: "libraries-demo", label: "Libraries & Demo" },
                        { value: "lifestyle", label: "Lifestyle" },
                        { value: "maps-navigation", label: "Maps & Navigation" },
                        { value: "medical", label: "Medical" },
                        { value: "music-audio", label: "Music & Audio" },
                        { value: "news-magazines", label: "News & Magazines" },
                        { value: "parenting", label: "Parenting" },
                        { value: "personalization", label: "Personalization" },
                        { value: "photography", label: "Photography" },
                        { value: "productivity", label: "Productivity" },
                        { value: "shopping", label: "Shopping" },
                        { value: "social", label: "Social" },
                        { value: "sports", label: "Sports" },
                        { value: "tools", label: "Tools" },
                        { value: "travel-local", label: "Travel & Local" },
                        { value: "video-players", label: "Video Players & Editors" },
                        { value: "weather", label: "Weather" }
                    ],
                    "GAMES": [
                        { value: "game-action", label: "Action" },
                        { value: "game-adventure", label: "Adventure" },
                        { value: "game-arcade", label: "Arcade" },
                        { value: "game-board", label: "Board" },
                        { value: "game-card", label: "Card" },
                        { value: "game-casino", label: "Casino" },
                        { value: "game-casual", label: "Casual" },
                        { value: "game-educational", label: "Educational" },
                        { value: "game-music", label: "Music" },
                        { value: "game-puzzle", label: "Puzzle" },
                        { value: "game-racing", label: "Racing" },
                        { value: "game-role-playing", label: "Role Playing" },
                        { value: "game-simulation", label: "Simulation" },
                        { value: "game-sports", label: "Sports" },
                        { value: "game-strategy", label: "Strategy" },
                        { value: "game-trivia", label: "Trivia" },
                        { value: "game-word", label: "Word" }
                    ]
                };

                for (const [groupLabel, categories] of Object.entries(playGroups)) {
                    const group = document.createElement("optgroup");
                    group.label = groupLabel;
                    categories.forEach(c => {
                        const opt = document.createElement("option");
                        opt.value = c.value;
                        opt.text = c.label;
                        group.appendChild(opt);
                    });
                    categorySelect.appendChild(group);
                }
                
                // Show Android specific title/short desc
                document.getElementById("store-title-android-group").style.display = "block";
                document.getElementById("store-short-android-group").style.display = "block";
                
                document.getElementById("store-title-package").value = repo.appName;
                document.getElementById("store-summary-package").value = "";
                
                if (mod.playStoreListing) {
                    document.getElementById("store-title-android").value = mod.playStoreListing.title || repo.appName;
                    document.getElementById("store-short-android").value = mod.playStoreListing.shortDescription || "";
                    document.getElementById("store-detailed-desc").value = mod.playStoreListing.fullDescription || "";
                    let catVal = mod.playStoreListing.category || "tools";
                    // Map legacy values
                    if (catVal === "utilities") catVal = "tools";
                    if (catVal === "health") catVal = "health-fitness";
                    if (catVal === "games") catVal = "game-casual";
                    categorySelect.value = catVal;
                    document.getElementById("store-language").value = mod.playStoreListing.language || "en";
                }
                
                // Hide Privacy Single Purpose
                document.getElementById("privacy-purpose-group").style.display = "none";
                document.getElementById("cws-privacy-extensions").style.display = "none";
                if (mod.playStoreListing) {
                    document.getElementById("privacy-policy-url").value = mod.playStoreListing.privacyPolicyUrl || "";
                }
                
                // Hide permissions justifications panel
                document.getElementById("privacy-permissions-panel").style.display = "none";
            }
            
            // Graphic Assets
            renderGraphicAssetsStatus();
            
            // Distribution inputs
            document.getElementById("dist-visibility").value = mod.status === "published" ? "public" : (mod.status === "beta" ? "unlisted" : "private");
            document.getElementById("dist-store-id").value = mod.storeId || "";
            document.getElementById("dist-store-url").value = mod.storeUrl || "";
            
            // Access inputs
            document.getElementById("access-test-instructions").value = (isChrome ? (mod.cwsListing && mod.cwsListing.testInstructions) : (mod.playStoreListing && mod.playStoreListing.testInstructions)) || "";
            
            // Secrets tab inputs
            document.getElementById("secrets-client-id").value = state.credentials.client_id || "";
            document.getElementById("secrets-client-secret").value = state.credentials.client_secret || "";
            
            // Checklist copyable fields
            populateOnboardingChecklist();
            
            // Pre-flight checklist
            renderPreflightChecklist();
        }

        function runManifestDiagnostics() {
            const repo = state.selectedRepo;
            const mod = repo.metadata.modules[state.selectedModuleIdx];
            const box = document.getElementById("manifest-diagnostics-box");
            box.innerHTML = "";
            
            if (mod.type !== "chrome-extension") {
                box.innerHTML = `<p style="font-size:12px; color:var(--text-secondary);">No manifest diagnostics required for ${mod.type} modules.</p>`;
                return;
            }
            
            if (!repo.manifest_info) {
                box.innerHTML = `
                    <div class="badge badge-error" style="width:100%; justify-content:center; padding:10px;">
                        ❌ manifest.json not found or invalid
                    </div>
                    <p style="font-size:11px; color:var(--text-muted); margin-top:4px;">Please check that manifest.json exists in folder: <code>${mod.path || '.'}</code>.</p>
                `;
                return;
            }
            
            const info = repo.manifest_info;
            let checks = [];
            
            // Check 1: manifest version
            checks.push({
                name: "Manifest File Structure",
                status: "success",
                message: `Valid JSON found with name: <strong>${info.name}</strong>, version: <strong>${info.version}</strong>`
            });
            
            // Check 2: description length
            const descLen = info.description ? info.description.length : 0;
            if (descLen === 0) {
                checks.push({
                    name: "Description Property",
                    status: "error",
                    message: "Missing 'description' property in manifest.json."
                });
            } else if (descLen > 132) {
                checks.push({
                    name: "Description Length Limit",
                    status: "error",
                    message: `Description is too long: <strong>${descLen} chars</strong>. Max limit is 132 chars.`
                });
            } else {
                checks.push({
                    name: "Description Length Limit",
                    status: "success",
                    message: `Description length: <strong>${descLen} chars</strong> (Complies with 132 chars limit).`
                });
            }
            
            // Check 3: icons
            const hasIcons = info.icons && Object.keys(info.icons).length > 0;
            if (!hasIcons) {
                checks.push({
                    name: "Icons Declaration",
                    status: "error",
                    message: "No icons declared in manifest.json."
                });
            } else {
                const sizes = Object.keys(info.icons);
                checks.push({
                    name: "Icons Declaration",
                    status: "success",
                    message: `Declared icons: <strong>${sizes.join(', ')}</strong>`
                });
            }
            
            // Render checks
            checks.forEach(c => {
                const item = document.createElement("div");
                item.style.display = "flex";
                item.style.flexDirection = "column";
                item.style.gap = "4px";
                item.style.padding = "8px 12px";
                item.style.borderRadius = "8px";
                item.style.background = "rgba(0,0,0,0.15)";
                item.style.borderLeft = `3px solid var(--${c.status})`;
                
                item.innerHTML = `
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <span style="font-size:11px; font-weight:700; color:var(--text-secondary); text-transform:uppercase;">${c.name}</span>
                        <span class="status-dot ${c.status}"></span>
                    </div>
                    <div style="font-size:12px; color:var(--text-primary);">${c.message}</div>
                `;
                box.appendChild(item);
            });
        }

        function renderPermissionJustifications() {
            const repo = state.selectedRepo;
            const mod = repo.metadata.modules[state.selectedModuleIdx];
            const box = document.getElementById("permissions-justifications-box");
            box.innerHTML = "";
            
            if (!repo.manifest_info) {
                box.innerHTML = `<p style="font-size:12px; color:var(--text-secondary);">Initialize or correct manifest.json to show requested permissions.</p>`;
                return;
            }
            
            const info = repo.manifest_info;
            const allPermissions = [
                ...(info.permissions || []),
                ...(info.host_permissions || []),
                ...(info.optional_permissions || [])
            ];
            
            if (allPermissions.length === 0) {
                box.innerHTML = `<p style="font-size:12px; color:var(--text-secondary);">No permissions declared in manifest.json. No justifications needed!</p>`;
                return;
            }
            
            // Get existing justifications
            const justifications = (mod.cwsListing && mod.cwsListing.permissionJustifications) || {};
            
            allPermissions.forEach(perm => {
                const value = justifications[perm] || "";
                const group = document.createElement("div");
                group.className = "form-group";
                
                group.innerHTML = `
                    <label style="color:var(--accent-cyan); font-family:'JetBrains Mono',monospace; font-size:11.5px; text-transform:none;">${perm}</label>
                    <textarea class="perm-justification-input" data-permission="${perm}" placeholder="Explain why the extension requires the '${perm}' permission..." style="min-height:60px; font-size:12px;">${value}</textarea>
                `;
                box.appendChild(group);
            });
        }

        function renderGraphicAssetsStatus() {
            const repo = state.selectedRepo;
            const mod = repo.metadata.modules[state.selectedModuleIdx];
            const box = document.getElementById("graphic-assets-box");
            box.innerHTML = "";
            
            if (mod.type !== "chrome-extension") {
                box.innerHTML = `<p style="font-size:12px; color:var(--text-secondary);">No graphic assets verification needed for ${mod.type} modules.</p>`;
                return;
            }
            
            if (!repo.manifest_info || !repo.manifest_info.icons) {
                box.innerHTML = `<p style="font-size:12px; color:var(--text-secondary);">No icons declared in manifest.</p>`;
                return;
            }
            
            const icons = repo.manifest_info.icons;
            const sizes = Object.keys(icons);
            
            if (sizes.length === 0) {
                box.innerHTML = `
                    <div style="background:rgba(244,63,94,0.1); border:1px solid rgba(244,63,94,0.2); border-radius:8px; padding:12px; color:var(--error); font-size:12px;">
                        ⚠️ No icons declared in manifest.json. Store listing requires at least a 128x128 store icon.
                    </div>
                `;
                return;
            }
            
            // Add a sub-header for Icons
            const iconHeader = document.createElement("h3");
            iconHeader.innerText = "Store Icons";
            iconHeader.className = "sub-header";
            iconHeader.style.fontSize = "12px";
            iconHeader.style.marginBottom = "8px";
            box.appendChild(iconHeader);

            const iconContainer = document.createElement("div");
            iconContainer.style.display = "flex";
            iconContainer.style.flexDirection = "column";
            iconContainer.style.gap = "10px";

            sizes.forEach(size => {
                const icon = icons[size];
                const exists = icon.exists;
                const statusColor = exists ? "success" : "error";
                const statusSymbol = exists ? "✓" : "✗";
                
                const card = document.createElement("div");
                card.style.display = "flex";
                card.style.alignItems = "center";
                card.style.justifyContent = "space-between";
                card.style.padding = "10px 14px";
                card.style.borderRadius = "8px";
                card.style.background = "rgba(0,0,0,0.15)";
                card.style.border = `1px solid var(--card-border)`;
                
                let imgPreview = "";
                if (exists) {
                    const imgUrl = `/api/view-image?path=${encodeURIComponent(icon.abs_path)}`;
                    imgPreview = `<img src="${imgUrl}" alt="Icon ${size}" style="width: 32px; height: 32px; object-fit: contain; background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); border-radius: 4px; margin-right: 12px;" />`;
                } else {
                    imgPreview = `<div style="width: 32px; height: 32px; display: flex; align-items: center; justify-content: center; background: rgba(244,63,94,0.1); border: 1px solid rgba(244,63,94,0.2); border-radius: 4px; font-size: 14px; color: var(--error); margin-right: 12px;">⚠️</div>`;
                }
                
                let downloadBtn = "";
                if (exists) {
                    const downloadUrl = `/api/download?path=${encodeURIComponent(icon.abs_path)}`;
                    downloadBtn = `
                        <a class="btn btn-secondary" href="${downloadUrl}" download="${repo.name}-icon-${size}.png" style="padding: 4px 8px; font-size: 11px; border-radius: 4px; display: inline-flex; align-items: center; gap: 4px; margin-left: 8px;">
                            📥 Download
                        </a>
                    `;
                }

                card.innerHTML = `
                    <div style="display:flex; align-items:center; flex-grow:1; min-width:0;">
                        ${imgPreview}
                        <div style="display:flex; flex-direction:column; gap:2px; min-width:0;">
                            <span style="font-size:13px; font-weight:700;">Icon ${size}x${size}</span>
                            <span style="font-size:11px; color:var(--text-muted); font-family:'JetBrains Mono',monospace; text-overflow:ellipsis; overflow:hidden; white-space:nowrap;">${icon.rel_path}</span>
                        </div>
                    </div>
                    <div style="display:flex; align-items:center; gap:8px; flex-shrink:0;">
                        <span class="badge badge-${statusColor}" style="font-size:10px;">
                            ${statusSymbol} ${exists ? 'Detected' : 'Missing'}
                        </span>
                        ${downloadBtn}
                    </div>
                `;
                iconContainer.appendChild(card);
            });
            box.appendChild(iconContainer);

            // Add Screenshots section
            const screenshots = repo.manifest_info.screenshots || [];
            
            const screenHeader = document.createElement("h3");
            screenHeader.innerText = "Promotional Screenshots & Banners";
            screenHeader.className = "sub-header";
            screenHeader.style.fontSize = "12px";
            screenHeader.style.marginTop = "20px";
            screenHeader.style.marginBottom = "8px";
            box.appendChild(screenHeader);

            if (screenshots.length > 0) {
                const container = document.createElement("div");
                container.style.display = "grid";
                container.style.gridTemplateColumns = "repeat(auto-fill, minmax(130px, 1fr))";
                container.style.gap = "10px";
                
                screenshots.forEach(scr => {
                    const imgUrl = `/api/view-image?path=${encodeURIComponent(scr.abs_path)}`;
                    const downloadUrl = `/api/download?path=${encodeURIComponent(scr.abs_path)}`;
                    const scrCard = document.createElement("div");
                    scrCard.style.background = "rgba(0,0,0,0.15)";
                    scrCard.style.border = "1px solid var(--card-border)";
                    scrCard.style.borderRadius = "8px";
                    scrCard.style.padding = "8px";
                    scrCard.style.display = "flex";
                    scrCard.style.flexDirection = "column";
                    scrCard.style.gap = "6px";

                    scrCard.innerHTML = `
                        <div style="width:100%; height:70px; display:flex; align-items:center; justify-content:center; background:rgba(255,255,255,0.02); border-radius:4px; overflow:hidden; border:1px solid rgba(255,255,255,0.05);">
                            <img src="${imgUrl}" alt="${scr.name}" style="max-width:100%; max-height:100%; object-fit:contain;" />
                        </div>
                        <div style="display:flex; flex-direction:column; gap:4px;">
                            <span style="font-size:10px; color:var(--text-secondary); text-overflow:ellipsis; overflow:hidden; white-space:nowrap;" title="${scr.name}">${scr.name}</span>
                            <a class="btn btn-secondary" href="${downloadUrl}" download="${scr.name}" style="padding: 4px 6px; font-size: 10px; border-radius: 4px; text-align:center; display:block;">
                                📥 Download
                            </a>
                        </div>
                    `;
                    container.appendChild(scrCard);
                });
                box.appendChild(container);
            } else {
                const emptyMsg = document.createElement("div");
                emptyMsg.style.fontSize = "11px";
                emptyMsg.style.color = "var(--text-muted)";
                emptyMsg.innerHTML = "⚠️ No promotional screenshots detected in repository root. Please add them to your repository.";
                box.appendChild(emptyMsg);
            }
        }

        function saveActiveTabMetadata(tabName) {
            const meta = JSON.parse(JSON.stringify(state.selectedRepo.metadata));
            const mod = meta.modules[state.selectedModuleIdx];
            if (!mod) return;
            
            if (tabName === 'package') {
                mod.buildScript = document.getElementById("package-build-script").value.trim();
                mod.artifactPath = document.getElementById("package-artifact-path").value.trim();
            } else if (tabName === 'store') {
                if (mod.type === "chrome-extension") {
                    if (!mod.cwsListing) mod.cwsListing = {};
                    mod.cwsListing.detailedDescription = document.getElementById("store-detailed-desc").value;
                    mod.cwsListing.category = document.getElementById("store-category").value;
                    mod.cwsListing.language = document.getElementById("store-language").value;
                    mod.cwsListing.singlePurpose = document.getElementById("privacy-single-purpose").value;
                    mod.cwsListing.privacyPolicyUrl = document.getElementById("privacy-policy-url").value.trim();
                    mod.cwsListing.testInstructions = document.getElementById("access-test-instructions").value;
                    
                    // Save CWS specific privacy fields
                    mod.cwsListing.remoteCodeUsed = document.getElementById("remote-code-yes").checked;
                    mod.cwsListing.remoteCodeJustification = document.getElementById("privacy-remote-justification").value.trim();
                    mod.cwsListing.dataUsageCertified = document.getElementById("privacy-certify-policy").checked;
                    
                    const justifications = {};
                    document.querySelectorAll(".perm-justification-input").forEach(ta => {
                        const perm = ta.getAttribute("data-permission");
                        justifications[perm] = ta.value.trim();
                    });
                    mod.cwsListing.permissionJustifications = justifications;
                } else {
                    if (!mod.playStoreListing) mod.playStoreListing = {};
                    mod.playStoreListing.title = document.getElementById("store-title-android").value.trim();
                    mod.playStoreListing.shortDescription = document.getElementById("store-short-android").value.trim();
                    mod.playStoreListing.fullDescription = document.getElementById("store-detailed-desc").value;
                    mod.playStoreListing.category = document.getElementById("store-category").value;
                    mod.playStoreListing.language = document.getElementById("store-language").value;
                    mod.playStoreListing.privacyPolicyUrl = document.getElementById("privacy-policy-url").value.trim();
                    mod.playStoreListing.testInstructions = document.getElementById("access-test-instructions").value;
                }
                
                const visibility = document.getElementById("dist-visibility").value;
                mod.status = visibility === "public" ? "published" : (visibility === "unlisted" ? "beta" : "draft");
                mod.storeId = document.getElementById("dist-store-id").value.trim();
                mod.storeUrl = document.getElementById("dist-store-url").value.trim();
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
                    showToast("✓ Saved changes to app-metadata.json");
                    
                    fetchReposAndStatus();
                } else {
                    showToast("Failed to save changes: " + data.error, true);
                }
            })
            .catch(err => {
                console.error("Error saving metadata:", err);
                showToast("Connection error: " + err, true);
            });
        }

        function setupBuildExecutorPanel() {
            const nameEl = document.getElementById("build-module-name-label");
            const btn = document.getElementById("btn-run-build");
            
            if (state.selectedRepo.metadata_exists && state.selectedRepo.metadata.modules) {
                const mod = state.selectedRepo.metadata.modules[state.selectedModuleIdx];
                if (mod) {
                    nameEl.innerText = `${state.selectedRepo.appName} — ${mod.name}`;
                    const isDisabled = !document.getElementById("package-build-script").value;
                    btn.setAttribute("aria-disabled", isDisabled ? "true" : "false");
                    btn.title = isDisabled ? "Configure a build script first to enable execution." : "";
                }
            } else {
                nameEl.innerText = `${state.selectedRepo.appName}`;
                btn.setAttribute("aria-disabled", "true");
                btn.title = "Configure a build script first to enable execution.";
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
            const btn = document.getElementById("btn-run-build");
            if (btn.getAttribute("aria-disabled") === "true") return;
            const buildScript = document.getElementById("package-build-script").value.trim();
            if (!buildScript) {
                showToast("Please enter a build script first.", true);
                return;
            }

            const consoleOutput = document.getElementById("build-terminal-output");
            const badge = document.getElementById("build-status-badge");
            const terminalPanel = document.querySelector(".terminal-panel");
            
            btn.setAttribute("aria-disabled", "true");
            if (terminalPanel) terminalPanel.classList.add("active-build");
            badge.style.display = "inline-flex";
            badge.className = "badge badge-cyan";
            badge.innerHTML = `<svg class="build-spinner" viewBox="0 0 50 50" style="margin-right: 6px;"><circle cx="25" cy="25" r="20" fill="none" stroke="currentColor" stroke-width="5" stroke-dasharray="80, 200" stroke-linecap="round"></circle></svg> Running...`;
            consoleOutput.innerHTML = colorizeLog(`Spawning build process in background...\nCommand: ${buildScript}\n\n`);

            fetch('/api/build', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    path: state.selectedRepo.path,
                    build_script: buildScript
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
                    btn.setAttribute("aria-disabled", "false");
                    if (terminalPanel) terminalPanel.classList.remove("active-build");
                }
            })
            .catch(err => {
                consoleOutput.innerHTML += colorizeLog(`❌ Connection error triggering build: ${err}`);
                badge.className = "badge badge-error";
                badge.innerHTML = "❌ Failed";
                btn.setAttribute("aria-disabled", "false");
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
                                btn.setAttribute("aria-disabled", "false");
                                if (terminalPanel) terminalPanel.classList.remove("active-build");
                                
                                if (data.status === "success") {
                                    badge.className = "badge badge-success";
                                    badge.innerHTML = "✅ Success";
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

        function populateOnboardingChecklist() {
            const repo = state.selectedRepo;
            const meta = repo.metadata;
            if (!meta) return;
            const mod = meta.modules[state.selectedModuleIdx];
            if (!mod) return;

            const guideList = document.getElementById("onboarding-guide-steps");
            const assetsContainer = document.getElementById("secrets-copy-assets-container");
            assetsContainer.innerHTML = "";
            
            const isChrome = mod.type === "chrome-extension";
            
            if (isChrome) {
                guideList.innerHTML = `
                    <li>Go to the <a href="https://chrome.google.com/webstore/devconsole" target="_blank">Chrome Web Store Developer Console</a>.</li>
                    <li>Click <strong>Add new item</strong> and drag-and-drop the generated ZIP package found in your local build directory.</li>
                    <li>Once uploaded, go to <strong>Store listing</strong>. Copy-paste the descriptions, category, language, and upload the store icon and screenshots below.</li>
                    <li>Go to the <strong>Privacy tab</strong>. Copy and paste the Privacy Policy link. Select justifications for requested permissions.</li>
                    <li>Save the draft, and copy your assigned <strong>Extension ID</strong> from the Developer dashboard address URL. Paste it into your module configuration in the <strong>Store Listing</strong> tab as the Store App ID.</li>
                `;

                const shortDesc = (mod.cwsListing && mod.cwsListing.shortDescription) || (repo.manifest_info && repo.manifest_info.description) || "";
                const detailedDesc = (mod.cwsListing && mod.cwsListing.detailedDescription) || "";
                const singlePurpose = (mod.cwsListing && mod.cwsListing.singlePurpose) || "";
                const privacyUrl = (mod.cwsListing && mod.cwsListing.privacyPolicyUrl) || "";
                const category = (mod.cwsListing && mod.cwsListing.category) || "";
                const language = (mod.cwsListing && mod.cwsListing.language) || "en";
                const remoteUsed = (mod.cwsListing && mod.cwsListing.remoteCodeUsed === true);
                const remoteJustification = (mod.cwsListing && mod.cwsListing.remoteCodeJustification) || "";
                const permissionJustifications = (mod.cwsListing && mod.cwsListing.permissionJustifications) || {};

                let iconHtml = `<p style="font-size: 12px; color: var(--text-secondary);">No icons found.</p>`;
                if (repo.manifest_info && repo.manifest_info.icons) {
                    const icons = repo.manifest_info.icons;
                    let selectedIconSize = "128";
                    if (!icons[selectedIconSize]) {
                        const sizes = Object.keys(icons).map(Number).sort((a,b) => b-a);
                        if (sizes.length > 0) selectedIconSize = String(sizes[0]);
                    }
                    
                    const icon = icons[selectedIconSize];
                    if (icon && icon.exists) {
                        const iconUrl = `/api/view-image?path=${encodeURIComponent(icon.abs_path)}`;
                        const downloadUrl = `/api/download?path=${encodeURIComponent(icon.abs_path)}`;
                        iconHtml = `
                            <div style="display: flex; align-items: center; gap: 16px; background: rgba(0,0,0,0.15); border: 1px solid var(--card-border); border-radius: 8px; padding: 12px;">
                                <img src="${iconUrl}" alt="Store Icon" style="width: 64px; height: 64px; object-fit: contain; background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); border-radius: 8px;" />
                                <div style="display: flex; flex-direction: column; gap: 4px; flex-grow: 1;">
                                    <span style="font-size: 13px; font-weight: 700;">Store Icon (${selectedIconSize}x${selectedIconSize})</span>
                                    <span style="font-size: 11px; color: var(--text-muted); font-family: monospace;">Right-click to Copy or Save</span>
                                </div>
                                <a class="btn btn-secondary" href="${downloadUrl}" download="${repo.name}-icon-${selectedIconSize}.png" style="padding: 6px 12px; font-size: 12px;">Download</a>
                            </div>
                        `;
                    }
                }

                let screenshotsHtml = `<p style="font-size: 12px; color: var(--text-secondary);">No promotional screenshots detected.</p>`;
                if (repo.manifest_info && repo.manifest_info.screenshots && repo.manifest_info.screenshots.length > 0) {
                    const screens = repo.manifest_info.screenshots;
                    screenshotsHtml = `
                        <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; max-height: 240px; overflow-y: auto; padding: 4px;">
                            ${screens.map(scr => {
                                const imgUrl = `/api/view-image?path=${encodeURIComponent(scr.abs_path)}`;
                                const downloadUrl = `/api/download?path=${encodeURIComponent(scr.abs_path)}`;
                                return `
                                    <div style="background: rgba(0,0,0,0.15); border: 1px solid var(--card-border); border-radius: 8px; padding: 8px; display: flex; flex-direction: column; gap: 8px; position: relative;">
                                        <div style="width: 100%; height: 100px; display: flex; align-items: center; justify-content: center; background: rgba(255,255,255,0.02); border-radius: 4px; overflow: hidden; border: 1px solid rgba(255,255,255,0.05);">
                                            <img src="${imgUrl}" alt="${scr.name}" style="max-width: 100%; max-height: 100%; object-fit: contain;" />
                                        </div>
                                        <div style="display: flex; align-items: center; justify-content: space-between; gap: 4px;">
                                            <span style="font-size: 11px; color: var(--text-secondary); text-overflow: ellipsis; overflow: hidden; white-space: nowrap; max-width: 100px;">${scr.name}</span>
                                            <a class="btn btn-secondary" href="${downloadUrl}" download="${scr.name}" style="padding: 4px 8px; font-size: 10px; border-radius: 4px;">Download</a>
                                        </div>
                                    </div>
                                `;
                            }).join('')}
                        </div>
                    `;
                }

                let remoteCodeHtml = `
                    <div class="form-group" style="margin-top: 12px;">
                        <label>Remote Code Declarations</label>
                        <div style="font-size: 12px; color: var(--text-secondary); margin-bottom: 6px;">
                            Are you using remote code? <strong>${remoteUsed ? 'Yes, I am using remote code' : 'No, I am not using remote code'}</strong>
                        </div>
                    </div>
                `;
                if (remoteUsed) {
                    remoteCodeHtml += `
                        <div class="form-group" style="padding-left: 8px; border-left: 2px solid var(--accent-cyan); margin-bottom: 12px;">
                            <label style="font-size: 11px; color: var(--accent-cyan);">Remote Code Justification</label>
                            <div class="copy-field">
                                <textarea id="copy-field-remote-just" readonly style="min-height: 50px; font-size: 11px;">${remoteJustification}</textarea>
                                <button class="copy-btn-inline" onclick="copyValue('copy-field-remote-just')" style="top: 10px; padding: 2px 6px; font-size: 10px;">Copy</button>
                            </div>
                        </div>
                    `;
                }

                let permsHtml = "";
                const permKeys = Object.keys(permissionJustifications);
                if (permKeys.length > 0) {
                    permsHtml += `
                        <div class="form-group" style="margin-top: 12px; margin-bottom: 4px;">
                            <label>Permission Justifications</label>
                        </div>
                    `;
                    permKeys.forEach((perm, idx) => {
                        const val = permissionJustifications[perm] || "";
                        const inputId = `copy-field-perm-${idx}`;
                        permsHtml += `
                            <div class="form-group" style="padding-left: 8px; border-left: 2px solid var(--accent-cyan); margin-bottom: 8px;">
                                <label style="font-family: monospace; font-size: 11px; color: var(--accent-cyan);">${perm} justification</label>
                                <div class="copy-field">
                                    <textarea id="${inputId}" readonly style="min-height: 45px; font-size: 11px;">${val}</textarea>
                                    <button class="copy-btn-inline" onclick="copyValue('${inputId}')" style="top: 10px; padding: 2px 6px; font-size: 10px;">Copy</button>
                                </div>
                            </div>
                        `;
                    });
                }

                assetsContainer.innerHTML = `
                    <h3 class="sub-header" style="font-size: 12px;">Store Listing Copyable Assets</h3>
                    
                    <div class="form-group">
                        <label>Short Description (Summary)</label>
                        <div class="copy-field">
                            <input type="text" id="copy-field-short" value="${shortDesc}" readonly>
                            <button class="copy-btn-inline" onclick="copyValue('copy-field-short')">Copy</button>
                        </div>
                    </div>

                    <div class="form-group">
                        <label>Detailed Description</label>
                        <div class="copy-field">
                            <textarea id="copy-field-long" readonly style="min-height: 120px;">${detailedDesc}</textarea>
                            <button class="copy-btn-inline" onclick="copyValue('copy-field-long')" style="top: 20px;">Copy</button>
                        </div>
                    </div>

                    <div class="form-group">
                        <label>Single Purpose Description</label>
                        <div class="copy-field">
                            <input type="text" id="copy-field-purpose" value="${singlePurpose}" readonly>
                            <button class="copy-btn-inline" onclick="copyValue('copy-field-purpose')">Copy</button>
                        </div>
                    </div>

                    <div class="form-row">
                        <div class="form-group">
                            <label>Category</label>
                            <div class="copy-field">
                                <input type="text" id="copy-field-category" value="${category}" readonly>
                                <button class="copy-btn-inline" onclick="copyValue('copy-field-category')">Copy</button>
                            </div>
                        </div>
                        <div class="form-group">
                            <label>Default Language</label>
                            <div class="copy-field">
                                <input type="text" id="copy-field-language" value="${language}" readonly>
                                <button class="copy-btn-inline" onclick="copyValue('copy-field-language')">Copy</button>
                            </div>
                        </div>
                    </div>

                    <div class="form-group">
                        <label>Privacy Policy Link</label>
                        <div class="copy-field">
                            <input type="text" id="copy-field-privacy" value="${privacyUrl}" readonly>
                            <button class="copy-btn-inline" onclick="copyValue('copy-field-privacy')">Copy</button>
                        </div>
                    </div>

                    ${remoteCodeHtml}
                    ${permsHtml}

                    <div class="form-group">
                        <label style="margin-bottom: 6px;">Store Icons (128x128 required)</label>
                        ${iconHtml}
                    </div>

                    <div class="form-group">
                        <label style="margin-bottom: 6px;">Promotional Screenshots & Banners</label>
                        ${screenshotsHtml}
                    </div>
                `;
            } else {
                guideList.innerHTML = `
                    <li>Go to the <a href="https://play.google.com/console" target="_blank">Google Play Console</a>.</li>
                    <li>Click <strong>Create app</strong> or select your app.</li>
                    <li>Go to <strong>Set up your app</strong>. Configure declarations, categories, and copy-paste details from the right panel.</li>
                    <li>Go to <strong>Production / Testing</strong> and upload the APK or AAB bundle found in your local build directory.</li>
                `;

                const title = (mod.playStoreListing && mod.playStoreListing.title) || repo.appName;
                const shortDesc = (mod.playStoreListing && mod.playStoreListing.shortDescription) || "";
                const detailedDesc = (mod.playStoreListing && mod.playStoreListing.fullDescription) || "";
                const privacyUrl = (mod.playStoreListing && mod.playStoreListing.privacyPolicyUrl) || "";
                const category = (mod.playStoreListing && mod.playStoreListing.category) || "";
                const language = (mod.playStoreListing && mod.playStoreListing.language) || "en";

                assetsContainer.innerHTML = `
                    <h3 class="sub-header" style="font-size: 12px;">Store Listing Copyable Assets</h3>
                    
                    <div class="form-group">
                        <label>Play Store App Title</label>
                        <div class="copy-field">
                            <input type="text" id="copy-field-title" value="${title}" readonly>
                            <button class="copy-btn-inline" onclick="copyValue('copy-field-title')">Copy</button>
                        </div>
                    </div>

                    <div class="form-group">
                        <label>Short Description</label>
                        <div class="copy-field">
                            <input type="text" id="copy-field-short" value="${shortDesc}" readonly>
                            <button class="copy-btn-inline" onclick="copyValue('copy-field-short')">Copy</button>
                        </div>
                    </div>

                    <div class="form-group">
                        <label>Full Description</label>
                        <div class="copy-field">
                            <textarea id="copy-field-long" readonly style="min-height: 120px;">${detailedDesc}</textarea>
                            <button class="copy-btn-inline" onclick="copyValue('copy-field-long')" style="top: 20px;">Copy</button>
                        </div>
                    </div>

                    <div class="form-row">
                        <div class="form-group">
                            <label>Category</label>
                            <div class="copy-field">
                                <input type="text" id="copy-field-category" value="${category}" readonly>
                                <button class="copy-btn-inline" onclick="copyValue('copy-field-category')">Copy</button>
                            </div>
                        </div>
                        <div class="form-group">
                            <label>Default Language</label>
                            <div class="copy-field">
                                <input type="text" id="copy-field-language" value="${language}" readonly>
                                <button class="copy-btn-inline" onclick="copyValue('copy-field-language')">Copy</button>
                            </div>
                        </div>
                    </div>

                    <div class="form-group">
                        <label>Privacy Policy Link</label>
                        <div class="copy-field">
                            <input type="text" id="copy-field-privacy" value="${privacyUrl}" readonly>
                            <button class="copy-btn-inline" onclick="copyValue('copy-field-privacy')">Copy</button>
                        </div>
                    </div>
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
                            nextBtn.setAttribute("aria-disabled", "false");
                            nextBtn.removeAttribute("title");
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
            if (finalBtn.getAttribute("aria-disabled") === "true") return;
            const alertBox = document.getElementById("secrets-alert-box");

            const meta = state.selectedRepo.metadata;
            const mod = meta.modules[state.selectedModuleIdx];
            if (!mod || !mod.storeId) {
                alertBox.style.display = "block";
                alertBox.className = "alert alert-error badge-error";
                alertBox.innerText = "Please input the Extension/App Store ID inside the Distribution tab first.";
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
    print("Please open this link in your browser to access the console.")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n❌ Web Server stopped. Exiting.")
        sys.exit(0)

if __name__ == "__main__":
    main()
