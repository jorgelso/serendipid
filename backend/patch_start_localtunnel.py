import sys
from pathlib import Path

content = Path('d:/superbrain/backend/start.py').read_text('utf-8')

# 1. Add LOCALTUNNEL_LOG to paths
content = content.replace(
    'NGROK_TOKEN = BASE_DIR / "config" / "ngrok_token.txt"',
    'NGROK_TOKEN = BASE_DIR / "config" / "ngrok_token.txt"\nLOCALTUNNEL_LOG = BASE_DIR / "config" / "localtunnel.log"'
)

# 2. Modify setup_remote_access
old_setup = """def setup_remote_access():
    h1("Step 6 of 7 — Remote Access (ngrok)")

    print(f\"\"\"
  The SuperBrain backend runs locally. Your phone needs to reach it over the internet.
  We recommend {BOLD}ngrok{RESET} for a secure tunnel.

  Requires a free account from: {CYAN}https://dashboard.ngrok.com/signup{RESET}
  Get your Authtoken at: {CYAN}https://dashboard.ngrok.com/get-started/your-authtoken{RESET}
\"\"\")

    choice = ask_yn("Enable ngrok on startup?", default=True)
    if not choice:
        NGROK_ENABLED.unlink(missing_ok=True)
        warn("Skipping ngrok. Local WiFi only.")
        return"""

new_setup = """def setup_remote_access():
    h1("Step 6 of 7 — Remote Access (ngrok / localtunnel)")

    print(f\"\"\"
  The SuperBrain backend runs locally. Your phone needs to reach it over the internet.
  We recommend {BOLD}ngrok{RESET} for a secure tunnel.
  If ngrok is not configured or fails, {BOLD}localtunnel{RESET} will be used as a fallback.

  Requires a free account from: {CYAN}https://dashboard.ngrok.com/signup{RESET}
  Get your Authtoken at: {CYAN}https://dashboard.ngrok.com/get-started/your-authtoken{RESET}
\"\"\")

    choice = ask_yn("Enable ngrok on startup?", default=True)
    if not choice:
        NGROK_ENABLED.unlink(missing_ok=True)
        warn("Skipping ngrok. Will use localtunnel as fallback.")
        return"""

content = content.replace(old_setup, new_setup)

# 3. Insert localtunnel functions before _start_ngrok
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
            subprocess.run(["powershell", "-NoProfile", "-Command", script], check=False)
        else:
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

def _start_ngrok
"""

content = content.replace("def _start_ngrok", funcs)

# 4. Modify launch_backend to use both ngrok and localtunnel
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

    # ── Generate and display QR code ──────────────────────────────────────────"""

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

    # ── Generate and display QR code ──────────────────────────────────────────"""

content = content.replace('    # ngrok startup\n    public_url: str | None = None\n    if NGROK_ENABLED.exists():\n        token_txt = NGROK_TOKEN.read_text().strip() if NGROK_TOKEN.exists() else ""\n        if not token_txt:\n            warn("Ngrok is enabled but no Authtoken was found.")\n            setup_remote_access()\n\n        info("Starting ngrok in background...")\n        public_url = _start_ngrok(PORT)\n        \n    tunnel_line = ""\n    tunnel_hint = ""\n    \n    if public_url:\n        tunnel_line = f"    Public URL   →  {GREEN}{BOLD}{public_url}{RESET}  {DIM}(ngrok){RESET}"\n        tunnel_hint = f"           · public     →  {GREEN}{public_url}{RESET}"\n        ok(f"ngrok active  →  {GREEN}{BOLD}{public_url}{RESET}")\n    elif NGROK_ENABLED.exists():\n        tunnel_line = f"    Public URL   →  {YELLOW}(failed to start ngrok){RESET}"\n        tunnel_hint = f"           · public     →  run manually: {DIM}ngrok http {PORT}{RESET}"\n    else:\n        tunnel_hint = f"           · public     →  enable ngrok via {DIM}python start.py --reset{RESET}"\n\n    # ── Generate and display QR code ──────────────────────────────────────────', new_launch)

Path('d:/superbrain/backend/start.py').write_text(content, 'utf-8')
print("Patched start.py successfully")
