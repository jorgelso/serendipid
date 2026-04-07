import os
import re

for filepath in [r"d:\superbrain\backend\start.py", r"d:\superbrain\superbrain-cli\payload\start.py"]:
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Add pyngrok to dependencies
    if repr('pyngrok') not in content and repr("pyngrok") not in content:
        content = re.sub(
            r'(\("multipart", "python-multipart"\),)',
            r'\1\n          ("pyngrok", "pyngrok"),',
            content, count=1
        )

    # 1. Replace step 6 setup
    content = re.sub(
        r'LOCALTUNNEL_ENABLED\s*=\s*BASE_DIR\s*/\s*"config"\s*/\s*"localtunnel_enabled\.txt"\nLOCALTUNNEL_LOG.*?info\("localtunnel will be started automatically every time you run start\.py\."\)',
        r'''NGROK_ENABLED = BASE_DIR / "config" / "ngrok_enabled.txt"
NGROK_AUTH_TOKEN_FILE = BASE_DIR / "config" / "ngrok_token.txt"

def setup_remote_access():
    h1("Step 6 of 7 — Remote Access (ngrok / Port Forwarding)")

    print(f"""
  The SuperBrain backend runs on {BOLD}port 5000{RESET} on your machine.
  Your phone needs to reach this port over the internet.

  You have two options:

    {BOLD}Option A — ngrok (easiest + free){RESET}
        ngrok creates a secure public HTTPS URL that tunnels to your local port 5000.
        Requires a free account from: {CYAN}https://dashboard.ngrok.com/signup{RESET}
        Get your Authtoken at: {CYAN}https://dashboard.ngrok.com/get-started/your-authtoken{RESET}

  {BOLD}Option B — Your own port forwarding (advanced){RESET}
    Forward {BOLD}TCP port 5000{RESET} on your router to your machine's local IP.
    Then use {BOLD}http://<your-public-ip>:5000{RESET} in the mobile app.

  {DIM}You can also run only on your local WiFi — both phone and PC must be on
  the same network. Use your PC's local IP (e.g. 192.168.x.x) in the app.{RESET}
""")

    choice = ask_yn("Enable ngrok on startup?", default=True)
    if not choice:
        NGROK_ENABLED.unlink(missing_ok=True)
        warn("Skipping ngrok. Use either your own port forwarding or local WiFi.")
        info("Remember: set the correct server URL in the mobile app Settings.")
        return

    ok("ngrok auto-start enabled")
    NGROK_ENABLED.parent.mkdir(parents=True, exist_ok=True)
    NGROK_ENABLED.write_text("enabled")

    existing_token = NGROK_AUTH_TOKEN_FILE.read_text().strip() if NGROK_AUTH_TOKEN_FILE.exists() else ""
    nl()
    print(f"  {YELLOW}Please paste your ngrok Authtoken.{RESET}")
    if existing_token:
        print(f"  {DIM}(Leave blank to keep existing token: {existing_token[:8]}...){RESET}")
        
    auth_token = ask("Authtoken", default=existing_token, paste=True)
    if not auth_token:
        warn("No ngrok token provided. ngrok will run but may disconnect. To fix, re-run setup.")
    else:
        NGROK_AUTH_TOKEN_FILE.write_text(auth_token.strip())
        ok("ngrok token saved.")''',
        content, flags=re.DOTALL
    )

    # 2. Replace the background worker block
    content = re.sub(
        r'def _run_localtunnel_background\(\):.*?return None\n\ndef _find_localtunnel_url_from_log\(\) -> str \| None:.*?return None',
        r'''def _start_ngrok_tunnel() -> str | None:
    try:
        from pyngrok import ngrok, conf
        ngrok_token = ""
        if NGROK_AUTH_TOKEN_FILE.exists():
            ngrok_token = NGROK_AUTH_TOKEN_FILE.read_text().strip()
        if ngrok_token:
            ngrok.set_auth_token(ngrok_token)
        
        # Connect to port 5000
        http_tunnel = ngrok.connect(5000, bind_tls=True)
        return http_tunnel.public_url
    except Exception as e:
        NGROK_ENABLED.parent.mkdir(parents=True, exist_ok=True)
        (BASE_DIR / "config" / "ngrok.log").write_text(f"Failed to start ngrok: {e}")
        return None''',
        content, flags=re.DOTALL
    )

    # 3. Replace the main execution block where it starts localtunnel
    content = re.sub(
        r'lt_proc = None.*?public_url = "\(skipped — localtunnel not enabled\)"',
        r'''if NGROK_ENABLED.exists():
            print(f"  Starting ngrok background tunnel …")
            from pyngrok import ngrok
            public_url = _start_ngrok_tunnel()
            if not public_url:
                print(f"  {YELLOW}⚠  ngrok failed to start.{RESET}")
                print(f"  Check logs in config/ngrok.log if it exists.{RESET}")
                public_url = "(failed — could not start ngrok)"
            else:
                ok(f"ngrok active: {BOLD}{public_url}{RESET}")
        else:
            public_url = "(skipped — ngrok not enabled)"''',
        content, flags=re.DOTALL
    )

    # 4. Replace prints referencing `npx localtunnel --port 5000`
    content = content.replace("npx localtunnel --port 5000", "ngrok http 5000")
    content = content.replace("localtunnel.log", "ngrok.log")

    # Write it out
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
