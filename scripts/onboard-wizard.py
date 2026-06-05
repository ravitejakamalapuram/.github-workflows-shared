#!/usr/bin/env python3

import sys
import os
import urllib.parse
import urllib.request
import json
import webbrowser
import subprocess
import re
from http.server import HTTPServer, BaseHTTPRequestHandler

# Global configurations
CREDENTIALS_PATH = os.path.expanduser("~/.chrome-api-credentials.json")
SERVER_PORT = 3000

# Server State
SERVER_CLIENT_ID = None
SERVER_CLIENT_SECRET = None
OAUTH_STATE = {"status": "idle", "refresh_token": None, "error": None}

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
                    return

                # Exchange code for Refresh Token
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
            
            # Open browser tab automatically
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
                # Execute onboarding script
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
                # Set secrets inside repository using gh CLI
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
        except Exception as e:
            return None

    def get_local_repos(self):
        # Scan parent folder of workflows repository (which is git-personal)
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        repos = []
        
        if not os.path.exists(base_dir):
            return repos
            
        for name in os.listdir(base_dir):
            path = os.path.join(base_dir, name)
            if not os.path.isdir(path) or name.startswith('.'):
                continue
                
            # Detect extension directories
            ext_dir = None
            if os.path.exists(os.path.join(path, "manifest.json")):
                ext_dir = "."
            elif os.path.exists(os.path.join(path, "extension", "manifest.json")):
                ext_dir = "extension"
            elif os.path.exists(os.path.join(path, "chrome-extension", "manifest.json")):
                ext_dir = "chrome-extension"
                
            is_git = os.path.exists(os.path.join(path, ".git"))
            
            if ext_dir is not None or is_git:
                # Check for existing workflow
                wf_exists = os.path.exists(os.path.join(path, ".github", "workflows", "ci-cd.yml"))
                repos.append({
                    "name": name,
                    "path": path,
                    "is_extension": ext_dir is not None,
                    "ext_dir": ext_dir or "Not Detected",
                    "is_git": is_git,
                    "workflow_exists": wf_exists
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
    <title>Chrome Extension Onboarding Console</title>
    <style>
        :root {
            --bg-color: #080b11;
            --card-bg: rgba(17, 24, 39, 0.7);
            --card-border: rgba(255, 255, 255, 0.06);
            --accent-cyan: #06b6d4;
            --accent-cyan-hover: #0891b2;
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
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: linear-gradient(135deg, var(--bg-color) 0%, #111827 100%);
            color: var(--text-primary);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            overflow-x: hidden;
        }

        header {
            border-bottom: 1px solid var(--card-border);
            padding: 20px 40px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: rgba(8, 11, 17, 0.8);
            backdrop-filter: blur(10px);
            z-index: 10;
            position: sticky;
            top: 0;
        }

        .logo {
            font-size: 20px;
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
            font-size: 22px;
            -webkit-text-fill-color: initial;
        }

        .gh-badge {
            background: rgba(30, 41, 59, 0.8);
            border: 1px solid var(--card-border);
            border-radius: 20px;
            padding: 6px 14px;
            font-size: 13px;
            display: flex;
            align-items: center;
            gap: 8px;
            font-weight: 500;
        }

        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            display: inline-block;
        }

        .status-dot.success { background: var(--success); box-shadow: 0 0 8px var(--success); }
        .status-dot.error { background: var(--error); box-shadow: 0 0 8px var(--error); }

        .container {
            max-width: 1100px;
            margin: 40px auto;
            width: 100%;
            padding: 0 20px;
            flex: 1;
            display: flex;
            flex-direction: column;
            gap: 30px;
        }

        .stepper {
            display: flex;
            justify-content: space-between;
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 12px;
            padding: 16px 24px;
            gap: 16px;
        }

        .step {
            display: flex;
            align-items: center;
            gap: 10px;
            color: var(--text-muted);
            font-size: 14px;
            font-weight: 600;
            position: relative;
            flex: 1;
            justify-content: center;
        }

        .step-number {
            width: 28px;
            height: 28px;
            border-radius: 50%;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--card-border);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 12px;
            color: var(--text-muted);
            transition: all 0.3s;
        }

        .step.active {
            color: var(--accent-cyan);
        }

        .step.active .step-number {
            background: rgba(6, 182, 212, 0.1);
            border-color: var(--accent-cyan);
            color: var(--accent-cyan);
            box-shadow: 0 0 10px rgba(6, 182, 212, 0.2);
        }

        .step.completed {
            color: var(--success);
        }

        .step.completed .step-number {
            background: rgba(16, 185, 129, 0.1);
            border-color: var(--success);
            color: var(--success);
        }

        .step:not(:last-child)::after {
            content: "";
            position: absolute;
            right: -25px;
            top: 50%;
            transform: translateY(-50%);
            width: 16px;
            height: 1px;
            background: var(--card-border);
        }

        .card {
            background: var(--card-bg);
            backdrop-filter: blur(16px);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            padding: 30px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
            transition: transform 0.3s;
            display: none;
            flex-direction: column;
            gap: 20px;
        }

        .card.active {
            display: flex;
            animation: fadeIn 0.4s ease-out;
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }

        h2 {
            font-size: 22px;
            font-weight: 700;
            letter-spacing: -0.5px;
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .subtitle {
            font-size: 14px;
            color: var(--text-secondary);
            margin-top: -10px;
            line-height: 1.5;
        }

        .form-group {
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        label {
            font-size: 13px;
            font-weight: 600;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        input, select {
            background: rgba(15, 23, 42, 0.6);
            border: 1px solid var(--card-border);
            padding: 12px 16px;
            border-radius: 8px;
            color: var(--text-primary);
            font-size: 14px;
            outline: none;
            transition: all 0.2s;
            width: 100%;
        }

        input:focus, select:focus {
            border-color: var(--accent-cyan);
            box-shadow: 0 0 0 3px rgba(6, 182, 212, 0.15);
        }

        .checkbox-group {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-top: 10px;
            cursor: pointer;
            user-select: none;
            font-size: 14px;
            color: var(--text-secondary);
        }

        .checkbox-group input {
            width: 18px;
            height: 18px;
            cursor: pointer;
        }

        .repo-list {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
            gap: 16px;
            margin-top: 10px;
        }

        .repo-item {
            background: rgba(30, 41, 59, 0.3);
            border: 1px solid var(--card-border);
            border-radius: 12px;
            padding: 20px;
            cursor: pointer;
            transition: all 0.2s;
            display: flex;
            flex-direction: column;
            gap: 12px;
            position: relative;
            overflow: hidden;
        }

        .repo-item:hover {
            border-color: rgba(255, 255, 255, 0.15);
            background: rgba(30, 41, 59, 0.4);
            transform: translateY(-2px);
        }

        .repo-item.selected {
            border-color: var(--accent-cyan);
            background: rgba(6, 182, 212, 0.05);
            box-shadow: 0 0 15px rgba(6, 182, 212, 0.1);
        }

        .repo-item:focus-visible {
            outline: none;
            border-color: var(--accent-cyan);
            box-shadow: 0 0 0 3px rgba(6, 182, 212, 0.15);
        }

        .repo-name {
            font-weight: 700;
            font-size: 16px;
        }

        .repo-meta {
            font-size: 12px;
            color: var(--text-secondary);
            display: flex;
            flex-direction: column;
            gap: 4px;
        }

        .badge-small {
            padding: 3px 8px;
            border-radius: 12px;
            font-size: 10px;
            font-weight: 700;
            text-transform: uppercase;
            width: fit-content;
        }

        .badge-cyan { background: rgba(6, 182, 212, 0.1); color: var(--accent-cyan); border: 1px solid rgba(6, 182, 212, 0.2); }
        .badge-success { background: rgba(16, 185, 129, 0.1); color: var(--success); border: 1px solid rgba(16, 185, 129, 0.2); }
        .badge-warning { background: rgba(245, 158, 11, 0.1); color: var(--warning); border: 1px solid rgba(245, 158, 11, 0.2); }

        .btn-row {
            display: flex;
            justify-content: space-between;
            margin-top: 20px;
            gap: 16px;
        }

        .btn {
            padding: 12px 24px;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            border: none;
            transition: all 0.2s;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .btn-primary {
            background: linear-gradient(to right, var(--accent-cyan), var(--accent-purple));
            color: white;
            box-shadow: 0 4px 12px rgba(139, 92, 246, 0.2);
        }

        .btn-primary:hover {
            transform: translateY(-1px);
            box-shadow: 0 6px 16px rgba(139, 92, 246, 0.3);
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
            opacity: 0.5;
            cursor: not-allowed;
            transform: none !important;
            box-shadow: none !important;
        }

        .btn:focus-visible {
            outline: 2px solid var(--accent-cyan);
            outline-offset: 2px;
        }

        .instructions-panel {
            background: rgba(15, 23, 42, 0.6);
            border: 1px solid var(--card-border);
            border-radius: 8px;
            padding: 20px;
            font-size: 14px;
            display: flex;
            flex-direction: column;
            gap: 12px;
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

        .instructions-panel li::marker {
            color: var(--accent-cyan);
            font-weight: bold;
        }

        .instructions-panel a {
            color: var(--accent-cyan);
            text-decoration: none;
        }

        .instructions-panel a:hover {
            text-decoration: underline;
        }

        .terminal-output {
            background: #04060a;
            border: 1px solid var(--card-border);
            border-radius: 8px;
            padding: 16px;
            font-family: "Courier New", Courier, monospace;
            font-size: 12px;
            color: #10b981;
            max-height: 200px;
            overflow-y: auto;
            white-space: pre-wrap;
            line-height: 1.5;
        }

        .alert {
            padding: 12px 16px;
            border-radius: 8px;
            font-size: 13px;
            display: flex;
            align-items: center;
            gap: 10px;
            font-weight: 500;
        }

        .alert-info { background: rgba(6, 182, 212, 0.08); border: 1px solid rgba(6, 182, 212, 0.15); color: var(--accent-cyan); }
        .alert-warning { background: rgba(245, 158, 11, 0.08); border: 1px solid rgba(245, 158, 11, 0.15); color: var(--warning); }
        .alert-error { background: rgba(244, 63, 94, 0.08); border: 1px solid rgba(244, 63, 94, 0.15); color: var(--error); }

        .auth-status-container {
            display: flex;
            align-items: center;
            justify-content: space-between;
            background: rgba(30, 41, 59, 0.4);
            border: 1px solid var(--card-border);
            padding: 20px;
            border-radius: 12px;
        }

        .oauth-success-badge {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 14px;
            font-weight: 700;
            color: var(--success);
        }

        .spinning {
            animation: spin 1s linear infinite;
        }

        @keyframes spin {
            from { transform: rotate(0deg); }
            to { transform: rotate(360deg); }
        }

        .confetti-container {
            text-align: center;
            padding: 30px 0;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 16px;
        }

        .success-icon {
            font-size: 60px;
            animation: bounce 1s infinite alternate;
        }

        @keyframes bounce {
            from { transform: translateY(0); }
            to { transform: translateY(-8px); }
        }

        .code-box {
            background: #04060a;
            border: 1px solid var(--card-border);
            padding: 16px;
            border-radius: 8px;
            font-family: monospace;
            text-align: left;
            width: 100%;
            position: relative;
        }

        .copy-btn {
            position: absolute;
            right: 12px;
            top: 12px;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--card-border);
            color: var(--text-secondary);
            padding: 4px 8px;
            font-size: 11px;
            border-radius: 4px;
            cursor: pointer;
            transition: all 0.2s;
        }
        
        .copy-btn:hover {
            color: var(--text-primary);
            background: rgba(255, 255, 255, 0.1);
        }

        .copy-btn:focus-visible {
            outline: 2px solid var(--accent-cyan);
            outline-offset: 2px;
        }
    </style>
</head>
<body>
    <header>
        <div class="logo">Chrome Extension Onboarding Console</div>
        <div class="gh-badge" id="gh-status-badge">
            <span class="status-dot error"></span> Checking GitHub CLI...
        </div>
    </header>

    <div class="container">
        <!-- Progress Stepper -->
        <div class="stepper">
            <div class="step active" id="step-indicator-1">
                <span class="step-number">1</span>
                Project Setup
            </div>
            <div class="step" id="step-indicator-2">
                <span class="step-number">2</span>
                Google Credentials
            </div>
            <div class="step" id="step-indicator-3">
                <span class="step-number">3</span>
                Store Upload
            </div>
            <div class="step" id="step-indicator-4">
                <span class="step-number">4</span>
                Authenticate & Publish
            </div>
        </div>

        <!-- STEP 1: Select Project -->
        <div class="card active" id="card-step-1">
            <h2>Select Project to Onboard</h2>
            <p class="subtitle">Select the Chrome Extension from your git-personal folder that you want to integrate with centralized CI/CD workflows.</p>
            
            <div id="gh-cli-warning" class="alert alert-error" style="display: none;">
                <strong>GitHub CLI Error:</strong> Please authenticate the GitHub CLI locally by running <code>gh auth login</code> before proceeding.
            </div>

            <div class="form-group">
                <label>Detected Repositories</label>
                <div class="repo-list" id="repo-list-container">
                    <!-- Loaded dynamically -->
                </div>
            </div>

            <div id="selected-repo-details" style="display: none;">
                <div class="alert alert-info">
                    <span id="onboard-status-text">Ready to onboard: StellarTab</span>
                </div>
            </div>

            <div class="btn-row">
                <div></div>
                <button class="btn btn-primary" id="btn-to-step-2" disabled>
                    Proceed to Step 2 &rarr;
                </button>
            </div>
        </div>

        <!-- STEP 2: Google Developer Credentials -->
        <div class="card" id="card-step-2">
            <h2>Google Cloud API Configuration</h2>
            <p class="subtitle">Set up authorization credentials in Google Cloud Console. These credentials allow GitHub Actions to safely access the Chrome Web Store API.</p>

            <div class="instructions-panel">
                <strong>How to get Google API Client Credentials:</strong>
                <ol>
                    <li>Open the <a href="https://console.cloud.google.com" target="_blank">Google Cloud Console</a> and create or select a project.</li>
                    <li>Enable the <strong>Chrome Web Store API</strong> for your project.</li>
                    <li>Configure the <strong>OAuth Consent Screen</strong> (External user type), and add the scope: <code>https://www.googleapis.com/auth/chromewebstore</code>.</li>
                    <li>Go to <strong>Credentials</strong> &rarr; <strong>Create Credentials</strong> &rarr; <strong>OAuth client ID</strong>.</li>
                    <li>Select <strong>Web application</strong> as the Application Type.</li>
                    <li>Add this exact URL as an <strong>Authorized Redirect URI</strong>: <code style="color:var(--accent-cyan);">http://localhost:3000/oauth-callback</code>.</li>
                    <li>Click Save and note down your <strong>Client ID</strong> and <strong>Client Secret</strong>.</li>
                </ol>
            </div>

            <div class="form-group">
                <label for="input-client-id">OAuth Client ID</label>
                <input type="text" id="input-client-id" placeholder="Enter your Google OAuth Client ID">
            </div>

            <div class="form-group">
                <label for="input-client-secret">OAuth Client Secret</label>
                <input type="password" id="input-client-secret" placeholder="Enter your Google OAuth Client Secret">
            </div>

            <div class="checkbox-group">
                <input type="checkbox" id="checkbox-save-creds" checked>
                <label for="checkbox-save-creds" style="text-transform:none; cursor:pointer;">Save these credentials locally on this machine for future extensions</label>
            </div>

            <div class="btn-row">
                <button class="btn btn-secondary" onclick="goToStep(1)">&larr; Back</button>
                <button class="btn btn-primary" id="btn-to-step-3" onclick="validateStep2()">
                    Save & Proceed &rarr;
                </button>
            </div>
        </div>

        <!-- STEP 3: Store Draft Creation & Upload -->
        <div class="card" id="card-step-3">
            <h2>Create Draft Listing & Initial Upload</h2>
            <p class="subtitle">Upload the initial package to the Developer Console. This registers your listing and assigns you an Extension ID.</p>

            <div class="instructions-panel">
                <strong>Why is this step manual?</strong>
                <p style="color:var(--text-secondary); margin-bottom: 8px;">Google Web Store API does not support programmatic creation of new items. A developer must create the first listing manually via the web interface.</p>
                <ol>
                    <li>Click the button below to bundle your extension code into a deployable ZIP.</li>
                    <li>Go to the <a href="https://chrome.google.com/webstore/devconsole" target="_blank">Chrome Web Store Developer Console</a>.</li>
                    <li>Click <strong>Add new item</strong> and drag-and-drop the generated <strong>initial-package.zip</strong>.</li>
                    <li>Save the draft, and copy your assigned <strong>Extension ID</strong> from the dashboard dashboard URL or listing.</li>
                </ol>
            </div>

            <div class="btn-row" style="margin-top: 10px; justify-content: center;">
                <button class="btn btn-primary" id="btn-onboard-action" onclick="runOnboardScript()">
                    📦 Generate Onboarding ZIP & Workflows
                </button>
            </div>

            <div id="onboard-logs-container" style="display: none;">
                <label>Onboarding Log Output</label>
                <div class="terminal-output" id="onboard-terminal-logs">Running onboarding scripts...</div>
            </div>

            <div class="form-group" id="extension-id-group" style="display: none; margin-top: 10px;">
                <label for="input-extension-id">Chrome Extension ID (or listing URL)</label>
                <input type="text" id="input-extension-id" placeholder="e.g., nkbihfbeogaeaoehlefnkodbefgpgknn or complete devconsole URL" oninput="parseExtIdInput()">
                <div id="ext-id-success-badge" class="alert alert-info" style="display: none; padding: 6px 12px; margin-top: 6px;">
                    🎯 Parsed Extension ID: <strong id="parsed-id-display"></strong>
                </div>
            </div>

            <div class="btn-row">
                <button class="btn btn-secondary" onclick="goToStep(2)">&larr; Back</button>
                <button class="btn btn-primary" id="btn-to-step-4" onclick="validateStep3()" disabled>
                    Proceed &rarr;
                </button>
            </div>
        </div>

        <!-- STEP 4: Google OAuth & Secret Provisioning -->
        <div class="card" id="card-step-4">
            <h2>OAuth Authorization & GitHub Provisioning</h2>
            <p class="subtitle">Log in to Google to generate a long-lived API Refresh Token and automatically upload secrets to GitHub.</p>

            <div class="auth-status-container" id="oauth-status-panel">
                <div>
                    <h3 style="font-size: 16px; margin-bottom: 4px;">Google API Authorization</h3>
                    <p style="font-size: 13px; color: var(--text-secondary);" id="oauth-status-text">Click authorize to authenticate your account.</p>
                </div>
                <button class="btn btn-primary" id="btn-oauth-trigger" onclick="triggerGoogleOAuth()">
                    🔒 Authorize with Google
                </button>
            </div>

            <div id="provision-status-alert" class="alert" style="display: none;">
                Setting up secrets...
            </div>

            <div class="btn-row" id="final-btn-row">
                <button class="btn btn-secondary" id="btn-final-back" onclick="goToStep(3)">&larr; Back</button>
                <button class="btn btn-primary" id="btn-provision-secrets" onclick="provisionSecrets()" disabled>
                    🚀 Set Secrets in GitHub Repository
                </button>
            </div>

            <!-- SUCCESS PANEL -->
            <div class="confetti-container" id="success-panel" style="display: none;">
                <span class="success-icon">🎉</span>
                <h2 style="color: var(--success); text-align: center;">Onboarding Fully Completed!</h2>
                <p style="color: var(--text-secondary); max-width: 600px;">GitHub Secrets are successfully provisioned. StellarTab is now linked with your centralized reusable workflows. Any push to the main branch will build, test, and auto-deploy updates directly to the Chrome Web Store.</p>
                
                <div class="code-box">
                    <button class="copy-btn" aria-label="Copy git commands to clipboard" onclick="copyGitCommands(this)">Copy</button>
                    <span style="color: var(--text-muted);"># Push your changes to Git:</span><br>
                    <span style="color: var(--accent-cyan);">git add .</span><br>
                    <span style="color: var(--accent-cyan);">git commit -m "Onboard extension to centralized workflows"</span><br>
                    <span style="color: var(--accent-cyan);">git push origin main</span>
                </div>
                
                <button class="btn btn-secondary" style="margin-top: 20px;" onclick="window.location.reload()">Onboard Another Project</button>
            </div>
        </div>
    </div>

    <script>
        // State management
        let state = {
            repos: [],
            selectedRepo: null,
            ghStatus: { authenticated: false },
            credentials: {
                client_id: "",
                client_secret: "",
                extension_id: "",
                refresh_token: ""
            },
            currentStep: 1
        };

        // Initialize On page load
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
                        document.getElementById("gh-cli-warning").style.display = "none";
                    } else {
                        badge.innerHTML = `<span class="status-dot error"></span> GitHub CLI: Not logged in`;
                        const warning = document.getElementById("gh-cli-warning");
                        warning.style.display = "block";
                        warning.innerHTML = `<strong>GitHub CLI Error:</strong> ${state.ghStatus.error}. Please run <code>gh auth login</code> inside your terminal and refresh.`;
                    }

                    // Pre-fill cached credentials
                    if (data.cached_credentials && data.cached_credentials.client_id) {
                        document.getElementById("input-client-id").value = data.cached_credentials.client_id;
                        document.getElementById("input-client-secret").value = data.cached_credentials.client_secret;
                        state.credentials.client_id = data.cached_credentials.client_id;
                        state.credentials.client_secret = data.cached_credentials.client_secret;
                    }

                    // Render Repositories list
                    renderRepos();
                })
                .catch(err => console.error("Error fetching repository details:", err));
        }

        function renderRepos() {
            const container = document.getElementById("repo-list-container");
            container.innerHTML = "";
            
            if (state.repos.length === 0) {
                container.innerHTML = "<p style='color:var(--text-secondary); grid-column: 1/-1;'>No local repositories found. Verify directory layout.</p>";
                return;
            }

            state.repos.forEach(repo => {
                const item = document.createElement("div");
                const isSelected = state.selectedRepo && state.selectedRepo.path === repo.path;
                item.className = `repo-item ${isSelected ? 'selected' : ''}`;
                item.tabIndex = 0;
                item.setAttribute("role", "button");
                item.setAttribute("aria-pressed", isSelected ? "true" : "false");
                
                const metaBadges = [];
                if (repo.is_extension) {
                    metaBadges.push(`<span class="badge-small badge-cyan">Extension (${repo.ext_dir})</span>`);
                } else {
                    metaBadges.push(`<span class="badge-small badge-warning">No manifest.json</span>`);
                }
                
                if (repo.workflow_exists) {
                    metaBadges.push(`<span class="badge-small badge-success">CI/CD Configured</span>`);
                }

                item.innerHTML = `
                    <div class="repo-name">${repo.name}</div>
                    <div class="repo-meta">
                        <span>Directory: ${repo.ext_dir}</span>
                        <span style="font-size:10px; color:var(--text-muted); word-break:break-all;">${repo.path}</span>
                    </div>
                    <div style="display:flex; gap:5px; flex-wrap:wrap; margin-top:auto;">
                        ${metaBadges.join("")}
                    </div>
                `;

                item.addEventListener("click", () => {
                    document.querySelectorAll(".repo-item").forEach(el => {
                        el.classList.remove("selected");
                        el.setAttribute("aria-pressed", "false");
                    });
                    item.classList.add("selected");
                    item.setAttribute("aria-pressed", "true");
                    selectRepository(repo);
                });

                item.addEventListener("keydown", (e) => {
                    if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        item.click();
                    }
                });

                container.appendChild(item);
            });
        }

        function selectRepository(repo) {
            state.selectedRepo = repo;
            const details = document.getElementById("selected-repo-details");
            const btn = document.getElementById("btn-to-step-2");
            const text = document.getElementById("onboard-status-text");

            details.style.display = "block";
            btn.disabled = false;

            if (repo.is_extension) {
                text.innerHTML = `🎯 Target project: <strong>${repo.name}</strong> (${repo.ext_dir}). Reusable workflow will bind build actions to this directory.`;
            } else {
                text.innerHTML = `⚠️ Target project: <strong>${repo.name}</strong> has no <code>manifest.json</code>. The onboarding script will generate a new boilerplate popup extension in `/extension` folder.`;
            }
            
            // Set target directory on step 2 & 3
            document.getElementById("btn-to-step-2").onclick = () => goToStep(2);
        }

        function goToStep(stepNum) {
            // Update Stepper Headers
            for (let i = 1; i <= 4; i++) {
                const el = document.getElementById(`step-indicator-${i}`);
                el.classList.remove("active", "completed");
                if (i < stepNum) {
                    el.classList.add("completed");
                } else if (i === stepNum) {
                    el.classList.add("active");
                }
            }

            // Update Cards Display
            for (let i = 1; i <= 4; i++) {
                const card = document.getElementById(`card-step-${i}`);
                card.classList.remove("active");
            }
            document.getElementById(`card-step-${stepNum}`).classList.add("active");
            state.currentStep = stepNum;
        }

        function validateStep2() {
            const client_id = document.getElementById("input-client-id").value.strip();
            const client_secret = document.getElementById("input-client-secret").value.strip();

            if (!client_id || !client_secret) {
                alert("Please fill in OAuth Client ID and Client Secret.");
                return;
            }

            state.credentials.client_id = client_id;
            state.credentials.client_secret = client_secret;
            
            goToStep(3);
        }

        // --- STEP 3 Actions ---

        function runOnboardScript() {
            const btn = document.getElementById("btn-onboard-action");
            const logsContainer = document.getElementById("onboard-logs-container");
            const logsOutput = document.getElementById("onboard-terminal-logs");
            
            btn.disabled = true;
            logsContainer.style.display = "block";
            logsOutput.innerText = "Spawning onboarding scripts and packaging zip. Please wait...";

            fetch('/api/onboard', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: json.dumps({ path: state.selectedRepo.path })
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    logsOutput.innerText = data.output;
                    logsOutput.scrollTop = logsOutput.scrollHeight;
                    
                    // Reveal extension id input field
                    document.getElementById("extension-id-group").style.display = "flex";
                    btn.innerText = "✅ Package Generated Successfully";
                    
                    // Enable next step validation if extension ID is filled
                    parseExtIdInput();
                } else {
                    logsOutput.innerText = "❌ ONBOARD SCRIPT ERROR:\\n" + data.error;
                    btn.disabled = false;
                    btn.innerText = "❌ Execution Failed. Click to Retry";
                }
            })
            .catch(err => {
                logsOutput.innerText = "❌ Connection error during execution: " + err;
                btn.disabled = false;
            });
        }

        function parseExtIdInput() {
            const input = document.getElementById("input-extension-id").value.strip().toLowerCase();
            const badge = document.getElementById("ext-id-success-badge");
            const display = document.getElementById("parsed-id-display");
            const btn = document.getElementById("btn-to-step-4");

            // Look for a 32-character string of letters a-p
            const regex = /([a-p]{32})/;
            const match = input.match(regex);

            if (match) {
                state.credentials.extension_id = match[1];
                display.innerText = match[1];
                badge.style.display = "flex";
                badge.className = "alert alert-info";
                btn.disabled = false;
            } else {
                state.credentials.extension_id = "";
                badge.style.display = "none";
                btn.disabled = true;
            }
        }

        function validateStep3() {
            if (!state.credentials.extension_id) {
                alert("Please input a valid Chrome Extension ID or developer dashboard URL.");
                return;
            }
            goToStep(4);
        }

        // --- STEP 4 Actions ---

        let pollInterval = null;

        function triggerGoogleOAuth() {
            const btn = document.getElementById("btn-oauth-trigger");
            const panel = document.getElementById("oauth-status-panel");
            const text = document.getElementById("oauth-status-text");
            const saveCreds = document.getElementById("checkbox-save-creds").checked;

            btn.disabled = true;
            btn.innerHTML = `<span class="status-dot success spinning" style="width:12px; height:12px; border-width:2px; border-style:solid; border-color:transparent var(--success) var(--success); background:none; box-shadow:none;"></span> Waiting for login...`;
            text.innerText = "Browser opened. Please grant access to Chrome Web Store on the Google authorization screen.";

            // Save credentials first and initiate OAuth
            fetch('/api/start-oauth', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: json.dumps({
                    client_id: state.credentials.client_id,
                    client_secret: state.credentials.client_secret,
                    save_credentials: saveCreds
                })
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    // Start polling for refresh token
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
                            
                            // Update UI
                            text.innerHTML = `<span class="oauth-success-badge">✓ Google Account Connected!</span> Refresh Token captured.`;
                            btn.style.display = "none";
                            nextBtn.disabled = false;
                        } else if (data.status === "error") {
                            clearInterval(pollInterval);
                            text.innerText = "OAuth Failed: " + data.error;
                            btn.disabled = false;
                            btn.innerText = "🔒 Authorize with Google";
                        }
                    })
                    .catch(err => {
                        console.error("Polling error:", err);
                    });
            }, 1000);
        }

        function provisionSecrets() {
            const alertBox = document.getElementById("provision-status-alert");
            const finalBtn = document.getElementById("btn-provision-secrets");
            const backBtn = document.getElementById("btn-final-back");

            finalBtn.disabled = true;
            backBtn.disabled = true;
            alertBox.style.display = "flex";
            alertBox.className = "alert alert-info";
            alertBox.innerText = "Encrypting and uploading Client ID, Secret, Extension ID, and Refresh Token to GitHub Secrets...";

            fetch('/api/secrets', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: json.dumps({
                    path: state.selectedRepo.path,
                    client_id: state.credentials.client_id,
                    client_secret: state.credentials.client_secret,
                    extension_id: state.credentials.extension_id,
                    refresh_token: state.credentials.refresh_token
                })
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    alertBox.style.display = "none";
                    document.getElementById("oauth-status-panel").style.display = "none";
                    document.getElementById("final-btn-row").style.display = "none";
                    document.getElementById("success-panel").style.display = "flex";
                    
                    // Mark step completed
                    const finalStep = document.getElementById("step-indicator-4");
                    finalStep.classList.remove("active");
                    finalStep.classList.add("completed");
                } else {
                    alertBox.className = "alert alert-error";
                    alertBox.innerText = "Failed to upload secrets: " + data.error;
                    finalBtn.disabled = false;
                    backBtn.disabled = false;
                }
            })
            .catch(err => {
                alertBox.className = "alert alert-error";
                alertBox.innerText = "Connection error setting secrets: " + err;
                finalBtn.disabled = false;
                backBtn.disabled = false;
            });
        }

        function copyGitCommands(btn) {
            const code = `git add .\\ngit commit -m "Onboard extension to centralized workflows"\\ngit push origin main`;
            navigator.clipboard.writeText(code).then(() => {
                const originalText = btn.innerText;
                const originalColor = btn.style.color;
                const originalBorder = btn.style.borderColor;

                btn.innerText = "✓ Copied!";
                btn.style.color = "var(--success)";
                btn.style.borderColor = "var(--success)";

                setTimeout(() => {
                    btn.innerText = originalText;
                    btn.style.color = originalColor;
                    btn.style.borderColor = originalBorder;
                }, 2000);
            });
        }

        // Standard helpers
        String.prototype.strip = function() {
            return this.replace(/^\\s+|\\s+$/g, '');
        };
    </script>
</body>
</html>
"""

def main():
    print("====================================================")
    print("🚀 Starting Chrome Extension Onboarding Web Server...")
    print("====================================================")
    
    server = HTTPServer(('localhost', SERVER_PORT), WebConsoleHandler)
    
    # Inform user
    url = f"http://localhost:{SERVER_PORT}"
    print(f"\n🌐 Web Console is listening at: {url}")
    print("Opening the dashboard in your default browser now...")
    
    # Launch browser automatically
    webbrowser.open(url)
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n❌ Web Server stopped. Exiting.")
        sys.exit(0)

if __name__ == "__main__":
    main()
