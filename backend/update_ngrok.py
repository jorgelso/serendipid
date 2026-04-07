import re

fpath = r"d:\superbrain\backend\start.py"
with open(fpath, "r", encoding="utf-8") as f:
    text = f.read()

# 1. Add pyngrok
text = re.sub(
    r'(\("multipart", "python-multipart"\),)',
    r'\1\n        ("pyngrok", "pyngrok"),',
    text
)

# 2. setup_remote_access
old_setup_remote_access = """LOCALTUNNEL_ENABLED = BASE_DIR / "config" / "localtunnel_enabled.txt"
LOCALTUNNEL_LOG = BASE_DIR / "config" / "localtunnel.log"

def setup_remote_access():
    h1("Step 6 of 7 — Remote Access (localtunnel / Port Forwarding)")

    print(f\"\"\"
  The SuperBrain backend runs on {BOLD}port 5000{RESET} on your machine.
  Your phone needs to reach this port over the internet.

  You have two options:

    {BOLD}Option A — localtunnel (easiest + free){RESET}
        localtunnel creates a public HTTPS URL that tunnels to your local port 5000.
        No account required.
        Official site: {CYAN}https://theboroer.github.io/localtunnel-www/{RESET}

  {BOLD}Option B — Your own port forwarding (advanced){RESET}
    Forward {BOLD}TCP port 5000{RESET} on your router to your machine's local IP.
    Then use {BOLD}http://<your-public-ip>:5000{RESET} in the mobile app.
    Steps:
      1. Find your machine's local IP  →  ip addr  (Linux) / ipconfig (Windows)
      2. Log into your router admin panel (usually http://192.168.1.1)
      3. Add a port forwarding rule: External 5000 → Internal <your-local-IP>:5000
      4. Use your public IP (check https://ipify.org) in the mobile app.
    {YELLOW}Note: dynamic public IPs change on router restart — consider a DDNS service.{RESET}

  {DIM}You can also run only on your local WiFi — both phone and PC must be on
  the same network. Use your PC's local IP (e.g. 192.168.x.x) in the app.{RESET}
\"\"\")

    choice = ask_yn("Enable localtunnel on startup?", default=True)
    if not choice:
        LOCALTUNNEL_ENABLED.unlink(missing_ok=True)
        warn("Skipping localtunnel. Use either your own port forwarding or local WiFi.")
        info("Remember: set the correct server URL in the mobile app Settings.")
        return

    if not shutil.which("npx"):
        print(f\"\"\"
    {YELLOW}npx is not installed / not on PATH.{RESET}

    Install it:
        Linux   →  {CYAN}Install Node.js (includes npm + npx){RESET}
        macOS   →  {CYAN}brew install node{RESET}
        Windows →  Install Node.js LTS from {CYAN}https://nodejs.org/{RESET}

    After installing, re-run {BOLD}python start.py{RESET}.
\"\"\")
        warn("Skipping localtunnel setup.")
        return

    ok("npx binary found")
    LOCALTUNNEL_ENABLED.parent.mkdir(parents=True, exist_ok=True)
    LOCALTUNNEL_ENABLED.write_text("enabled")
    ok("localtunnel auto-start enabled")
    nl()
    info("localtunnel will be started automatically every time you run start.py.")"""

new_setup_remote_access = """NGROK_ENABLED = BASE_DIR / "config" / "ngrok_enabled.txt"
NGROK_AUTH_TOKEN_FILE = BASE_DIR / "config" / "ngrok_token.txt"

def setup_remote_access():
    h1("Step 6 of 7 — Remote Access (ngrok / Port Forwarding)")

    print(f\"\"\"
  The SuperBrain backend runs on {BOLD}port 5000{RESET} on your machine.
  Your phone needs to reach this port over the internet.

  You have two options:

    {BOLD}Option A — ngrok (easiest){RESET}
        ngrok creates a secure public HTTPS URL that tunnels to your local port 5000.
        Requires a free account from: {CYAN}https://dashboard.ngrok.com/signup{RESET}
        Get your Authtoken at: {CYAN}https://dashboard.ngrok.com/get-started/your-authtoken{RESET}

  {BOLD}Option B — Your own port forwarding (advanced){RESET}
    Forward {BOLD}TCP port 5000{RESET} on your router to your machine's local IP.
    Then use {BOLD}http://<your-public-ip>:5000{RESET} in the mobile app.

  {DIM}You can also run only on your local WiFi — both phone and PC must be on
  the same network. Use your PC's local IP (e.g. 192.168.x.x) in the app.{RESET}
\"\"\")

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
    if auth_token.strip():
        NGROK_AUTH_TOKEN_FILE.write_text(auth_token.strip())
        ok("ngrok token saved.")
    else:
        warn("No ngrok token provided. ngrok will run but may disconnect. To fix, re-run setup.")"""

text = text.replace(old_setup_remote_access, new_setup_remote_access)

# 3. Replace background functions
old_funcs = """def _run_localtunnel_background():
    \"\"\"Run localtunnel in the background and write output to log.\"\"\"
    try:
        # Start npx localtunnel --port 5000 >> config/localtunnel.log 2>&1
        with open(LOCALTUNNEL_LOG, "w") as f:
            proc = subprocess.Popen(
                ["npx", "--yes", "localtunnel", "--port", "5000"],
                stdout=f,
                stderr=f,
                stdin=subprocess.DEVNULL,
                start_new_session=True  # Prevent Ctrl+C from killing it directly
            )
        return proc
    except Exception as e:
        LOCALTUNNEL_LOG.write_text(f"Failed to start localtunnel: {e}\\n")
        return None

def _extract_localtunnel_url(text: str) -> str | None:
    \"\"\"Extract first localtunnel public URL from text.\"\"\"
    match = re.search(r'(https://[^\\s]+loca\.lt)', text)
    if match: return match.group(1)
    return None

def _find_localtunnel_url_from_log() -> str | None:
    \"\"\"Wait and parse the log for the URL.\"\"\"
    for _ in range(15):
        if not LOCALTUNNEL_LOG.exists():
            time.sleep(0.5)
            continue
        text = LOCALTUNNEL_LOG.read_text(encoding="utf-8", errors="ignore")
        url = _extract_localtunnel_url(text)
        if url: return url
        time.sleep(0.5)
    return None"""

new_funcs = """def _start_ngrok_tunnel() -> str | None:
    \"\"\"Start ngrok locally and return the public URL\"\"\"
    try:
        from pyngrok import ngrok
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
        (BASE_DIR / "config" / "ngrok.log").write_text(f"Failed to start ngrok: {e}\\n")
        return None"""

text = text.replace(old_funcs, new_funcs)

# 4. Replace starting the background proc in launch_backend
old_launch = """        lt_proc = None
        if LOCALTUNNEL_ENABLED.exists():
            print(f"  Starting localtunnel in background …")
            if LOCALTUNNEL_LOG.exists(): LOCALTUNNEL_LOG.unlink()
            lt_proc = _run_localtunnel_background()

            public_url = _find_localtunnel_url_from_log()
            if not public_url:
                print(f"  {YELLOW}⚠  localtunnel started but URL is not available yet.{RESET}")
                print(f"  Check tunnel logs in: {CYAN}{LOCALTUNNEL_LOG}{RESET}")
                public_url = "(starting — URL pending, check localtunnel.log)"
            else:
                ok(f"localtunnel active: {BOLD}{public_url}{RESET}")
        else:
            public_url = "(skipped — localtunnel not enabled)\""""

new_launch = """        if NGROK_ENABLED.exists():
            print(f"  Starting ngrok background tunnel …")
            public_url = _start_ngrok_tunnel()
            if not public_url:
                print(f"  {YELLOW}⚠  ngrok failed to start.{RESET}")
                print(f"  Check logs in config/ngrok.log if it exists.{RESET}")
                public_url = "(failed — could not start ngrok)"
            else:
                ok(f"ngrok active: {BOLD}{public_url}{RESET}")
        else:
            public_url = "(skipped — ngrok not enabled)\""""

text = text.replace(old_launch, new_launch)

# 5. Fix status cmd log checking
old_status = """    url = "NOT_FOUND"
    log_file = BASE_DIR / "config" / "localtunnel.log"
    if log_file.exists():
        match = re.search(r"your url is: (https://[^\\s]+)", log_file.read_text(encoding="utf-8"))
        if match:
            url = match.group(1)
            
    if url == "NOT_FOUND":
        warn("Could not find a running localtunnel URL in config/localtunnel.log.")"""

new_status = """    # Fetch ngrok status via API
    url = "NOT_FOUND"
    try:
        import urllib.request, json
        req = urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels", timeout=2)
        data = json.loads(req.read())
        for tunnel in data.get("tunnels", []):
            if tunnel.get("proto") == "https":
                url = tunnel.get("public_url")
                break
    except Exception:
        pass
        
    if url == "NOT_FOUND":
        warn("Could not find a running ngrok URL. Is the server running?")"""

text = text.replace(old_status, new_status)

# Final smaller textual replacements that do not affect the rest of the file logic
text = text.replace("localtunnel_url", "public_url")
text = text.replace("LOCALTUNNEL_ENABLED.exists()", "NGROK_ENABLED.exists()")

with open(fpath, "w", encoding="utf-8") as f:
    f.write(text)
print("Updated start.py")
