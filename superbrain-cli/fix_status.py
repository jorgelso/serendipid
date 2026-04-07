import sys, shutil

path1 = 'D:/superbrain/backend/start.py'
path2 = 'D:/superbrain/superbrain-cli/payload/start.py'

status_code = '''
def launch_backend_status():
    h1("SuperBrain Server Status")
    PORT = 5000
    token = TOKEN_FILE.read_text().strip() if TOKEN_FILE.exists() else "—"
    local_ip = _detect_local_ip()

    localtunnel_enabled = bool(shutil.which("npx") or shutil.which("npx.cmd"))
    localtunnel_url: str | None = None
    if localtunnel_enabled:
        localtunnel_url = _find_localtunnel_url_from_log()

    if localtunnel_url:
        tunnel_line = f"    Public URL   ?  {GREEN}{BOLD}{localtunnel_url}{RESET}  {DIM}(localtunnel){RESET}"
        tunnel_hint = f"         · public     ?  {GREEN}{localtunnel_url}{RESET}"
    elif localtunnel_enabled:
        tunnel_line = f"    Public URL   ?  {YELLOW}(running — URL in localtunnel.log){RESET}"
        tunnel_hint = f"         · public     ?  run:  {DIM}npx localtunnel --port {PORT}{RESET}"
    else:
        tunnel_line = ""
        tunnel_hint = f"         · public     ?  install Node.js first, then run: {DIM}npx localtunnel --port {PORT}{RESET}"

    qr_url = localtunnel_url if localtunnel_url else f"http://{local_ip}:{PORT}"
    _display_connect_qr(qr_url, token)

    print(f\"\"\"
    {GREEN}{BOLD}Server Status{RESET}

    Local URL      ?  {CYAN}http://127.0.0.1:{PORT}{RESET}
    Network URL    ?  {CYAN}http://{local_ip}:{PORT}{RESET}
{(tunnel_line + chr(10)) if tunnel_line else ''}    API docs       ?  {CYAN}http://127.0.0.1:{PORT}/docs{RESET}
    Access Token   ?  {BOLD}{MAGENTA}{token}{RESET}

  {YELLOW}Mobile app setup:{RESET}
    {BOLD}Option A — Scan QR code:{RESET}
      1. Open the app  ?  Settings  ?  tap the {BOLD}QR icon{RESET} ??
      2. Scan the QR code shown above

    {BOLD}Option B — Manual setup:{RESET}
      1. Go to app  ?  ? settings
      2. Set {BOLD}Server URL{RESET} to:
{tunnel_hint}
           · Same WiFi  ?  http://{local_ip}:{PORT}
      3. Set {BOLD}Access Token{RESET} to: {BOLD}{MAGENTA}{token}{RESET}
\"\"\")
    sys.exit(0)
'''

for path in [path1, path2]:
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()

    if 'def launch_backend_status()' not in content:
        content = content.replace('def main():', status_code + '\n\ndef main():')

    target = '    reset_mode = "--reset" in sys.argv'
    replacement = '''    status_mode = "--status" in sys.argv
    if status_mode:
        launch_backend_status()
        return

    reset_mode = "--reset" in sys.argv'''
    if 'status_mode = "--status"' not in content:
        content = content.replace(target, replacement)

    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)

print("Status command added!")
