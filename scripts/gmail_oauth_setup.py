#!/usr/bin/env python3
"""One-time Gmail API OAuth2 setup for the WorldTwin nightly audit.

Run this ONCE — interactively — and it will write a refresh token to
/home/opc/worldtwin/.gmail_oauth.json that the nightly audit then uses
forever (refresh tokens don't expire unless revoked or unused for 6 months).

Setup prerequisites (one-time, in Google Cloud Console):
  1. Open https://console.cloud.google.com/ and select the project that
     holds your existing API key (the one used for Gemini).
  2. Navigate to: APIs & Services -> Library -> search "Gmail API" -> Enable.
  3. Navigate to: APIs & Services -> OAuth consent screen
     - User Type: External
     - App name: WorldTwin Audit
     - User support email: jannolouwrens@gmail.com
     - Developer contact: jannolouwrens@gmail.com
     - Scopes: add "https://www.googleapis.com/auth/gmail.send"
     - Test users: add jannolouwrens@gmail.com (so the app can be used
       even though it's in "Testing" status — this is normal for personal
       use, you do NOT need to publish the app)
  4. Navigate to: APIs & Services -> Credentials -> Create Credentials
     -> OAuth client ID
     - Application type: Desktop app
     - Name: WorldTwin Audit Desktop
     - Click Create. Copy the Client ID and Client Secret.

Now run this script:
  python3 gmail_oauth_setup.py

It will:
  - Prompt for client_id and client_secret
  - Print a Google consent URL — open it in any browser, sign in as
    jannolouwrens@gmail.com, accept the gmail.send scope
  - Google redirects you to http://localhost/?code=... — the page will
    fail to load (no server listening) but the URL bar contains the code.
    Copy the value of the `code=` parameter and paste it back here.
  - Exchanges the code for a refresh token + writes it to disk

The helper writes the file with mode 0600 so only the owner can read it.
"""
from __future__ import annotations
import json
import os
import stat
import sys
import urllib.parse
import urllib.request

OUT_PATH = "/home/opc/worldtwin/.gmail_oauth.json"
SCOPE = "https://www.googleapis.com/auth/gmail.send"
REDIRECT_URI = "http://localhost"   # Desktop OAuth flow — code comes back in URL


def prompt(label: str) -> str:
    v = input(f"{label}: ").strip()
    if not v:
        sys.exit(f"abort: {label} cannot be empty")
    return v


def main() -> int:
    print("=" * 70)
    print("  WorldTwin · Gmail API OAuth2 Setup")
    print("=" * 70)
    print()
    print("Make sure you have followed the setup prerequisites in the")
    print("docstring at the top of this file (enable Gmail API in your")
    print("Google Cloud project, configure OAuth consent screen, create")
    print("a Desktop OAuth client).")
    print()
    client_id = prompt("Paste OAuth client_id")
    client_secret = prompt("Paste OAuth client_secret")
    user_email = prompt("Gmail address that consented (default jannolouwrens@gmail.com)") or "jannolouwrens@gmail.com"

    # Build consent URL
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",     # gives us a refresh token
        "prompt": "consent",          # force a refresh token even if already consented
    })

    print()
    print("-" * 70)
    print("STEP 1: Open this URL in your browser, sign in as the Gmail")
    print("        account that should send the audit emails, and accept:")
    print()
    print(auth_url)
    print()
    print("STEP 2: Google will redirect you to http://localhost/?code=XXX...")
    print("        The page will fail to load (no server is listening on")
    print("        port 80 of your laptop). That is expected. Look at your")
    print("        browser's address bar and copy ONLY the value of the")
    print("        `code=` parameter (everything between `code=` and `&` if")
    print("        there's an `&`, otherwise to the end of the URL).")
    print()
    code = prompt("Paste the auth code from the URL")

    # Exchange code for tokens
    print()
    print("Exchanging code for refresh token...")
    body = urllib.parse.urlencode({
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    }).encode()
    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=body, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            tok = json.loads(r.read())
    except urllib.error.HTTPError as e:
        print(f"FAILED: HTTP {e.code} — {e.read().decode('utf-8', 'ignore')}")
        return 1
    except Exception as e:
        print(f"FAILED: {e}")
        return 1

    refresh_token = tok.get("refresh_token")
    if not refresh_token:
        print("FAILED: response had no refresh_token. Full response:")
        print(json.dumps(tok, indent=2))
        print()
        print("Tip: if you already consented to this client before, Google")
        print("won't re-issue a refresh token. Revoke the previous grant at")
        print("https://myaccount.google.com/permissions and re-run this script.")
        return 1

    cfg = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "user_email": user_email,
    }
    out_dir = os.path.dirname(OUT_PATH)
    if not os.path.exists(out_dir):
        print(f"NOTE: directory {out_dir} does not exist on this machine.")
        print(f"      Writing the config to ./gmail_oauth.json in current dir instead.")
        out_path = "gmail_oauth.json"
    else:
        out_path = OUT_PATH
    with open(out_path, "w") as f:
        json.dump(cfg, f, indent=2)
    os.chmod(out_path, stat.S_IRUSR | stat.S_IWUSR)
    print()
    print("=" * 70)
    print(f"SUCCESS · refresh token saved to {out_path} (mode 0600)")
    print("=" * 70)
    print()
    print("If you ran this on your laptop, scp the file to the server now:")
    print(f"  scp {out_path} opc@129.151.191.74:/home/opc/worldtwin/.gmail_oauth.json")
    print()
    print("Then test the audit:")
    print("  ssh opc@129.151.191.74 python3 /home/opc/worldtwin/scripts/nightly_audit.py")
    print()
    print("Then install the cron (already shown in nightly_audit.py docstring).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
