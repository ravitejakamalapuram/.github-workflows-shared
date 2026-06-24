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

# Clean GITHUB_TOKEN from environment to let gh CLI use keychain login
if "GITHUB_TOKEN" in os.environ:
    del os.environ["GITHUB_TOKEN"]

CREDENTIALS_PATH = os.path.expanduser("~/.chrome-api-credentials.json")

class OAuthHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress logging request info to console
        return

    def do_GET(self):
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        
        if 'code' in params:
            self.server.auth_code = params['code'][0]
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            
            # Premium feedback page
            success_html = """
            <html>
            <head>
                <title>Authorization Successful</title>
                <style>
                    body {
                        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
                        color: #2d3748;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        height: 100vh;
                        margin: 0;
                    }
                    .card {
                        background: white;
                        padding: 40px;
                        border-radius: 12px;
                        box-shadow: 0 10px 25px rgba(0, 0, 0, 0.05);
                        text-align: center;
                        max-width: 450px;
                    }
                    h1 { color: #38a169; margin-top: 0; }
                    p { color: #718096; font-size: 16px; line-height: 1.5; }
                    .badge {
                        background: #e6fffa;
                        color: #319795;
                        padding: 6px 12px;
                        border-radius: 20px;
                        font-size: 14px;
                        font-weight: bold;
                        display: inline-block;
                        margin-bottom: 20px;
                    }
                </style>
            </head>
            <body>
                <div class="card">
                    <span class="badge">Google OAuth</span>
                    <h1>Authorization Successful!</h1>
                    <p>Google API credentials captured successfully.</p>
                    <p style="font-size: 14px;">You can now close this tab and return to the terminal to finish configuring your secrets.</p>
                </div>
            </body>
            </html>
            """
            self.wfile.write(success_html.encode('utf-8'))
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Authorization failed. No code found.")

def run_local_server(client_id):
    server = HTTPServer(('localhost', 3000), OAuthHandler)
    server.auth_code = None
    
    # Authorized scopes for Chrome Web Store API
    auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={client_id}&"
        "redirect_uri=http://localhost:3000&"
        "response_type=code&"
        "scope=https://www.googleapis.com/auth/chromewebstore&"
        "access_type=offline&"
        "prompt=consent"
    )
    
    print("\n🌐 Opening your default web browser for Google API authorization...")
    print(f"If the browser doesn't open automatically, please click this link:\n\n   {auth_url}\n")
    
    # Open browser
    webbrowser.open(auth_url)
    
    # Wait for response
    try:
        server.handle_request()
    except KeyboardInterrupt:
        print("\n❌ Server stopped manually.")
        sys.exit(1)
        
    return server.auth_code

def exchange_code(client_id, client_secret, code):
    print("🔑 Exchanging authorization code for long-lived Refresh Token...")
    url = "https://oauth2.googleapis.com/token"
    
    data = urllib.parse.urlencode({
        'code': code,
        'client_id': client_id,
        'client_secret': client_secret,
        'redirect_uri': 'http://localhost:3000',
        'grant_type': 'authorization_code'
    }).encode('utf-8')
    
    req = urllib.request.Request(url, data=data)
    try:
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            return res_data.get('refresh_token')
    except Exception as e:
        print(f"\n❌ Error during token exchange: {e}")
        return None

def set_gh_secret(repo_path, secret_name, value):
    try:
        # Run gh secret set inside the target git repository
        subprocess.run(
            ["gh", "secret", "set", secret_name, "--body", value],
            cwd=repo_path,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE
        )
        print(f"  ✅ GitHub secret '{secret_name}' configured.")
    except subprocess.CalledProcessError as err:
        print(f"  ❌ Failed to set secret '{secret_name}': {err.stderr.decode('utf-8').strip()}")
    except FileNotFoundError:
        print("  ❌ 'gh' CLI not found. Please install the GitHub CLI and authenticate first.")
        sys.exit(1)

def check_gh_cli(repo_path):
    try:
        # Check if gh CLI is installed
        subprocess.run(["gh", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ Error: GitHub CLI ('gh') is not installed.")
        print("💡 Please install it (e.g., 'brew install gh' on macOS) and run 'gh auth login' before running this script.")
        sys.exit(1)
        
    try:
        # Check if authenticated
        subprocess.run(["gh", "auth", "status"], cwd=repo_path, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError:
        print("❌ Error: GitHub CLI is installed but not authenticated.")
        print("💡 Please run 'gh auth login' to authenticate with GitHub before running this script.")
        sys.exit(1)

def load_cached_credentials():
    if os.path.exists(CREDENTIALS_PATH):
        try:
            with open(CREDENTIALS_PATH, "r") as f:
                data = json.load(f)
                return data.get("client_id"), data.get("client_secret")
        except Exception:
            pass
    return None, None

def save_credentials(client_id, client_secret):
    try:
        os.makedirs(os.path.dirname(CREDENTIALS_PATH), exist_ok=True)
        with open(CREDENTIALS_PATH, "w") as f:
            json.dump({"client_id": client_id, "client_secret": client_secret}, f, indent=2)
        print(f"💾 Saved API credentials to {CREDENTIALS_PATH} for future use.")
    except Exception as e:
        print(f"⚠️ Failed to save credentials: {e}")

def parse_extension_id(input_str):
    # Extension IDs are 32 characters long and consist of letters 'a' through 'p'
    match = re.search(r'\b([a-p]{32})\b', input_str.lower().strip())
    if match:
        return match.group(1)
    
    # Try to extract the first 32-char [a-p] string even if it doesn't have boundary markers
    match_any = re.search(r'([a-p]{32})', input_str.lower().strip())
    if match_any:
        return match_any.group(1)
        
    return None

def main():
    print("====================================================")
    print("   Chrome Web Store API Secrets Configuration Helper")
    print("====================================================")
    
    if len(sys.argv) > 1:
        repo_path = sys.argv[1]
    else:
        repo_path = "."
        
    repo_path = os.path.abspath(repo_path)
    
    if not os.path.exists(os.path.join(repo_path, ".git")):
        print(f"❌ Error: {repo_path} is not a valid Git repository.")
        sys.exit(1)
        
    print(f"Target repository: {repo_path}")
    
    # Preemptively check if the environment has gh CLI setup
    check_gh_cli(repo_path)
    
    print("\nTo automate publishing, please provide the details from your Google Cloud Console credentials.")
    
    # Load cached credentials
    client_id, client_secret = load_cached_credentials()
    
    if client_id and client_secret:
        print(f"\nℹ️ Loaded saved Google API credentials from {CREDENTIALS_PATH}")
        use_saved = input("Use these credentials? [Y/n]: ").strip().lower()
        if use_saved == 'n':
            client_id = None
            client_secret = None

    try:
        if not client_id or not client_secret:
            client_id = input("\nEnter your OAuth Client ID: ").strip()
            if not client_id:
                print("❌ Client ID cannot be empty.")
                sys.exit(1)
                
            client_secret = input("Enter your OAuth Client Secret: ").strip()
            if not client_secret:
                print("❌ Client Secret cannot be empty.")
                sys.exit(1)
                
            save_opt = input("Save these credentials globally for future extensions? [Y/n]: ").strip().lower()
            if save_opt != 'n':
                save_credentials(client_id, client_secret)
        
        # Loop until a valid extension ID is provided/parsed
        while True:
            ext_input = input("\nEnter your Chrome Extension ID or Dashboard URL: ").strip()
            parsed_id = parse_extension_id(ext_input)
            if parsed_id:
                extension_id = parsed_id
                print(f"🎯 Extracted Extension ID: {extension_id}")
                break
            else:
                print("❌ Invalid Extension ID. It must contain a 32-character string using letters a-p.")
                
    except KeyboardInterrupt:
        print("\n\n❌ Exited setup.")
        sys.exit(0)

    # Step 1: Run local server to capture Auth Code
    auth_code = run_local_server(client_id)
    if not auth_code:
        print("❌ Failed to capture Google API authorization code.")
        sys.exit(1)
        
    # Step 2: Exchange for Refresh Token
    refresh_token = exchange_code(client_id, client_secret, auth_code)
    if not refresh_token:
        print("❌ Google Token exchange failed. Double check your Client ID/Secret and ensure redirect URI 'http://localhost:3000' is authorized.")
        sys.exit(1)
        
    # Step 3: Set secrets in GitHub via CLI
    print("\n⚙️ Setting up GitHub Actions Repository Secrets...")
    set_gh_secret(repo_path, "CHROME_CLIENT_ID", client_id)
    set_gh_secret(repo_path, "CHROME_CLIENT_SECRET", client_secret)
    set_gh_secret(repo_path, "CHROME_EXTENSION_ID", extension_id)
    set_gh_secret(repo_path, "CHROME_REFRESH_TOKEN", refresh_token)
    
    print("\n🎉 SUCCESS! GitHub secrets configured successfully.")
    print("You can now push your changes to trigger automatic deployments on release/merge.")

if __name__ == "__main__":
    main()
