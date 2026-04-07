import pathlib
p = pathlib.Path("backend/start.py")
TEXT = p.read_text(encoding="utf-8")

# 1. Add LOCALTUNNEL_LOG to paths
TEXT = TEXT.replace(
    'NGROK_TOKEN = BASE_DIR / "config" / "ngrok_token.txt"',
    'NGROK_TOKEN = BASE_DIR / "config" / "ngrok_token.txt"\nLOCALTUNNEL_LOG = BASE_DIR / "config" / "localtunnel.log"'
)

# 2. Modify setup_remote_access
TEXT = TEXT.replace(
    '    h1("Step 6 of 7 — Remote Access (ngrok)")',
    '    h1("Step 6 of 7 — Remote Access (ngrok / localtunnel)")'
)

old_text1 = """  The SuperBrain backend runs locally. Your phone needs to reach it over the internet.
  We recommend {BOLD}ngrok{RESET} for a secure tunnel.

  Requires a free account from: {CYAN}https://dashboard.ngrok.com/signup{RESET}"""

new_text1 = """  The SuperBrain backend runs locally. Your phone needs to reach it over the internet.
  We recommend {BOLD}ngrok{RESET} for a secure tunnel.
  If ngrok is not configured or fails, {BOLD}localtunnel{RESET} will be used as a fallback.

  Requires a free account from: {CYAN}https://dashboard.ngrok.com/signup{RESET}"""
TEXT = TEXT.replace(old_text1, new_text1)

TEXT = TEXT.replace(
    '        warn("Skipping ngrok. Local WiFi only.")',
    '        warn("Skipping ngrok. Will use localtunnel as fallback.")'
)

# 3. Insert localtunnel functions before _get_windows_pids_on_port
# I need to find `def _get_windows_pids_on_port`
funcs = """def _find_localtunnel_url_from_log() -> str | None:
    try:
        import re
        if not LOCALTUNNEL_LOG.exists():
            return None
        text = LOCALTUNNEL_LOG.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r"https://[\\w.-]+\\.loca\\.lt\\b", text)
        return m.group(0) if m else None
    except Exception:
        return None

def _stop_localtunnel_processes():
    try:
        if IS_WINDOWS:
            script = (
                "Get-CimInstance Win32_Process "
                "| Where-Object { $_.CommandLine -match 'localtunnel|\\\\.loca\\\\.lt' } "
                "| ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
            )
            import subprocess
            subprocess.run(["powershell", "-NoProfile", "-Command", script], check=False)
        else:
            import subprocess
            subprocess.run(["pkill", "-f", "localtunnel"], check=False)
    except Exception:
        pass

def _start_localtunnel(port: int, timeout: int = 25) -> str | None:
    import time
    npx_exec = shutil.which("npx") or shutil.which("npx.cmd")
    if not npx_exec:
        warn("Node.js (npx) not found. Cannot start localtunnel.")
        return None

    _stop_localtunnel_processes()
    time.sleep(0.8)

    info("Starting localtunnel in background...")
    try:
        LOCALTUNNEL_LOG.parent.mkdir(parents=True, exist_ok=True)
        LOCALTUNNEL_LOG.write_text("")
        log_handle = open(LOCALTUNNEL_LOG, "a", encoding="utf-8", buffering=1)
        kwargs = {
            "start_new_session": True,
            "stdout": log_handle,
            "stderr": subprocess.STDOUT,
            "text": True,
        }
        if IS_WINDOWS and npx_exec.lower().endswith(".cmd"):
            cmd = ["cmd", "/c", npx_exec, "-y", "localtunnel", "--port", str(port)]
        else:
            cmd = [npx_exec, "-y", "localtunnel", "--port", str(port)]
        subprocess.Popen(cmd, **kwargs)
    except Exception as e:
        warn(f"Could not start localtunnel: {e}")
        return None

    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(1)
        url = _find_localtunnel_url_from_log()
        if url:
            return url
    return None

def _get_windows_pids_on_port"""

TEXT = TEXT.replace("def _get_windows_pids_on_port", funcs)

# 4. Modify launch_backend 
old_launch = """    # ngrok startup
    public_url: str | None = None
    if NGROK_ENABLED.exists():
        token_txt = NGROK_TOKEN.read_text().strip() if NGROK_TOKEN.exists() else ""
        if not token_txt:
            warn("Ngrok is enabled but no Authtoken was found.")
            setup_remote_access()

        info("Starting ngrok in background...")
        public_url = _start_ngrok(PORT)
        
    tunnel_line = ""
    tunnel_hint = ""
    
    if public_url:
        tunnel_line = f"    Public URL   →  {GREEN}{BOLD}{public_url}{RESET}  {DIM}(ngrok){RESET}"
        tunnel_hint = f"           · public     →  {GREEN}{public_url}{RESET}"
        ok(f"ngrok active  →  {GREEN}{BOLD}{public_url}{RESET}")
    elif NGROK_ENABLED.exists():
        tunnel_line = f"    Public URL   →  {YELLOW}(failed to start ngrok){RESET}"
        tunnel_hint = f"           · public     →  run manually: {DIM}ngrok http {PORT}{RESET}"
    else:
        tunnel_hint = f"           · public     →  enable ngrok via {DIM}python start.py --reset{RESET}"

    # ── Generate and display QR code"""

new_launch = """    # tunnel startup
    public_url: str | None = None
    tunnel_type: str = ""
    
    if NGROK_ENABLED.exists():
        token_txt = NGROK_TOKEN.read_text().strip() if NGROK_TOKEN.exists() else ""
        if not token_txt:
            warn("Ngrok is enabled but no Authtoken was found.")
            setup_remote_access()

        info("Starting ngrok in background...")
        public_url = _start_ngrok(PORT)
        if public_url:
            tunnel_type = "ngrok"
            ok(f"ngrok active  →  {GREEN}{BOLD}{public_url}{RESET}")
        else:
            warn("ngrok failed. Falling back to localtunnel...")

    if not public_url:
        public_url = _start_localtunnel(PORT)
        if public_url:
            tunnel_type = "localtunnel"
            ok(f"localtunnel active  →  {GREEN}{BOLD}{public_url}{RESET}")
        
    tunnel_line = ""
    tunnel_hint = ""
    
    if public_url:
        tunnel_line = f"    Public URL   →  {GREEN}{BOLD}{public_url}{RESET}  {DIM}({tunnel_type}){RESET}"
        tunnel_hint = f"           · public     →  {GREEN}{public_url}{RESET}"
    elif NGROK_ENABLED.exists():
        tunnel_line = f"    Public URL   →  {YELLOW}(failed to start ngrok and localtunnel){RESET}"
        tunnel_hint = f"           · public     →  run manually: {DIM}ngrok http {PORT}{RESET}"
    else:
        tunnel_line = f"    Public URL   →  {YELLOW}(failed to start localtunnel){RESET}"
        tunnel_hint = f"           · public     →  configure ngrok via {DIM}python start.py --reset{RESET} or ensure node/npx is installed"

    # ── Generate and display QR code"""

TEXT = TEXT.replace(old_launch, new_launch)

old_status = """    # Fetch ngrok status via API
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
        warn("Could not find a running ngrok URL. Is the server running?")
        nl()
        print("  Wait 5 seconds, or run 'superbrain-server' to start the server.")
        return

    _display_connect_qr(url, token)
    
    local_url = "http://127.0.0.1:5000"
    local_ip = _detect_local_ip()
    network_url = f"http://{local_ip}:5000"
    
    nl()
    print(f"    Local URL      →  {CYAN}{local_url}{RESET}")
    print(f"    Network URL    →  {CYAN}{network_url}{RESET}")
    print(f"    Public URL   →  {CYAN}{url}{RESET}  (localtunnel)")
    print(f"    API docs       →  {CYAN}{local_url}/docs{RESET}")"""

new_status = """    # Fetch ngrok status via API
    url = "NOT_FOUND"
    tunnel_type = "tunnel"
    try:
        import urllib.request, json
        req = urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels", timeout=2)
        data = json.loads(req.read())
        for tunnel in data.get("tunnels", []):
            if tunnel.get("proto") == "https":
                url = tunnel.get("public_url")
                tunnel_type = "ngrok"
                break
    except Exception:
        pass
        
    if url == "NOT_FOUND":
        # Fallback to localtunnel log
        url_lt = _find_localtunnel_url_from_log()
        if url_lt:
            url = url_lt
            tunnel_type = "localtunnel"
            
    if url == "NOT_FOUND":
        warn("Could not find a running ngrok or localtunnel URL. Is the server running?")
        nl()
        print("  Wait 5 seconds, or run 'superbrain-server' to start the server.")
        return

    _display_connect_qr(url, token)
    
    local_url = "http://127.0.0.1:5000"
    local_ip = _detect_local_ip()
    network_url = f"http://{local_ip}:5000"
    
    nl()
    print(f"    Local URL      →  {CYAN}{local_url}{RESET}")
    print(f"    Network URL    →  {CYAN}{network_url}{RESET}")
    print(f"    Public URL   →  {CYAN}{url}{RESET}  ({tunnel_type})")
    print(f"    API docs       →  {CYAN}{local_url}/docs{RESET}")"""

TEXT = TEXT.replace(old_status, new_status)

p.write_text(TEXT, encoding="utf-8")
print("Done patching backend/start.py")
