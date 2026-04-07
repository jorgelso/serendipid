import sys
import re

with open(r"d:\superbrain\backend\start.py", "r", encoding="utf-8") as f:
    text = f.read()

# 1. Dependency
text = re.sub(
    r'(\("multipart", "python-multipart"\),)',
    r'\1\n        ("pyngrok", "pyngrok"),',
    text
)

# 2. Config variables
text = re.sub(
    r'LOCALTUNNEL_ENABLED = BASE_DIR / "config" / "localtunnel_enabled\.txt"\nLOCALTUNNEL_LOG = BASE_DIR / "config" / "localtunnel\.log"',
    r'NGROK_ENABLED = BASE_DIR / "config" / "ngrok_enabled.txt"\nNGROK_TOKEN = BASE_DIR / "config" / "ngrok_token.txt"',
    text
)

# 3. Remove localtunnel background functions
text = re.sub(
    r'def _extract_localtunnel_url\(text: str\).*?return _check_port\(port\) is None',
    r'def _check_port(port: int) -> int | None:',
    text, flags=re.DOTALL
)

# 4. Inject _start_ngrok
ngrok_func = """def _start_ngrok(port: int) -> str | None:
    try:
        import pyngrok
        from pyngrok import ngrok
        
        token = NGROK_TOKEN.read_text().strip() if NGROK_TOKEN.exists() else None
        if token:
            ngrok.set_auth_token(token)
            
        tunnel = ngrok.connect(port, bind_tls=True)
        return tunnel.public_url
    except Exception as e:
        warn(f"Failed to start ngrok: {e}")
        return None\n\n"""
text = text.replace("def _check_port(", ngrok_func + "def _check_port(")


# 5. Remote Access Setup
old_remote_match = re.search(r'def setup_remote_access\(\):.+?every time you run start\.py\."\)', text, re.DOTALL)
if not old_remote_match:
    print("Could not find setup_remote_access")
    sys.exit(1)

new_remote = """def setup_remote_access():
    h1("Step 6 of 7 — Remote Access (ngrok)")

    print(f\\\"\\\"\\\"
  The SuperBrain backend runs locally. Your phone needs to reach it over the internet.
  We recommend {BOLD}ngrok{RESET} for a secure tunnel.

  Requires a free account from: {CYAN}https://dashboard.ngrok.com/signup{RESET}
  Get your Authtoken at: {CYAN}https://dashboard.ngrok.com/get-started/your-authtoken{RESET}
\\\"\\\"\\\")

    choice = ask_yn("Enable ngrok on startup?", default=True)
    if not choice:
        NGROK_ENABLED.unlink(missing_ok=True)
        warn("Skipping ngrok. Local WiFi only.")
        return

    ok("ngrok auto-start enabled")
    NGROK_ENABLED.parent.mkdir(parents=True, exist_ok=True)
    NGROK_ENABLED.write_text("enabled")

    existing_token = NGROK_TOKEN.read_text().strip() if NGROK_TOKEN.exists() else ""
    print(f"\\n  {YELLOW}Please paste your ngrok Authtoken.{RESET}")
    if existing_token:
         print(f"  {DIM}(Leave blank to keep existing token){RESET}")
         
    auth_token = ask("Authtoken", default=existing_token, paste=True)
    if auth_token.strip():
        NGROK_TOKEN.write_text(auth_token.strip())
        ok("ngrok token saved.")
    else:
        warn("No ngrok token provided. ngrok may disconnect. To fix, re-run setup.")"""

text = text[:old_remote_match.start()] + new_remote + text[old_remote_match.end():]

# 6. Launch Backend modifications
# Replace from `localtunnel_enabled = bool` up to `install Node.js first` line
launch_match = re.search(r'localtunnel_enabled\s*=\s*bool\(shutil\.which.*?"npx.*?\).*?\n.*?(?:install\s+Node\.js.*?localtunnel.*?{RESET}")', text, re.DOTALL)
if not launch_match:
    print("Could not find launch_backend localtunnel setup")
    sys.exit(1)

new_launch = """# ngrok startup
    public_url: str | None = None
    if NGROK_ENABLED.exists():
        info("Starting ngrok in background...")
        public_url = _start_ngrok(PORT)
        
    tunnel_line = ""
    tunnel_hint = ""
    
    if public_url:
        tunnel_line = f"    Public URL   →  {GREEN}{BOLD}{public_url}{RESET}  {DIM}(ngrok){RESET}"
        tunnel_hint = f"         · public     →  {GREEN}{public_url}{RESET}"
        ok(f"ngrok active  →  {GREEN}{BOLD}{public_url}{RESET}")
    elif NGROK_ENABLED.exists():
        tunnel_line = f"    Public URL   →  {YELLOW}(failed to start ngrok){RESET}"
        tunnel_hint = f"         · public     →  run manually: {DIM}ngrok http {PORT}{RESET}"
    else:
        tunnel_hint = f"         · public     →  enable ngrok via {DIM}python start.py --reset{RESET}\""""

text = text[:launch_match.start()] + new_launch + text[launch_match.end():]

# 7. QR target replace
text = re.sub(
    r'qr_url\s*=\s*localtunnel_url\s+if\s+localtunnel_url\s+else\s+f"http://\{local_ip\}:\{PORT\}"',
    r'qr_url = public_url if public_url else f"http://{local_ip}:{PORT}"',
    text
)

# 8. Check log loop
check_loop_match = re.search(r'while\s+True:\s+status\s*=\s*run_q\(\s*\[sys\.executable,\s*str\(\s*VENV_PYTHON\s*\).*?\}\).+?_time\.sleep\(6\)', text, re.DOTALL)
if check_loop_match:
    old_loop = check_loop_match.group(0)
    # The check loop normally waits. The original check loop doesn't have localtunnel.
    # Ah wait, I need to look for `_find_localtunnel_url_from_log` inside `def _run_server_check_loop` ... wait there isn't any in start.py!
    # Ah wait. `status` command.
pass

# Status command in cli
status_match = re.search(r'url\s*=\s*"NOT_FOUND"\s*log_file\s*=\s*BASE_DIR\s*/\s*"config"\s*/\s*"localtunnel\.log".*?warn\("Could not find a running localtunnel URL in config/localtunnel\.log\."\)', text, re.DOTALL)
if status_match:
    new_status = """# Fetch ngrok status via API
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
    text = text[:status_match.start()] + new_status + text[status_match.end():]

with open(r"d:\superbrain\backend\start_ngrok_clean.py", "w", encoding="utf-8") as f:
    f.write(text)
print("done")
