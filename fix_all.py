import os
import re

# 1. start.py fixes
start_path = r'd:\superbrain\backend\start.py'
content = open(start_path, 'r', encoding='utf-8').read()

if 'def launch_backend_status' not in content:
    func_str = '''
def launch_backend_status():
    h1("SuperBrain Status")
    
    token = "UNKNOWN"
    if TOKEN_FILE.exists():
        token = TOKEN_FILE.read_text(encoding="utf-8").strip()

    url = "NOT_FOUND"
    log_file = BASE_DIR / "config" / "localtunnel.log"
    if log_file.exists():
        match = re.search(r"your url is: (https://[^\s]+)", log_file.read_text(encoding="utf-8"))
        if match:
            url = match.group(1)
            
    if url == "NOT_FOUND":
        warn("Could not find a running localtunnel URL in config/localtunnel.log.")
        nl()
        print("  Wait 5 seconds, or run 'superbrain-server' to start the server.")
        return

    _display_connect_qr(url, token)
    
    local_url = "http://127.0.0.1:5000"
    local_ip = _detect_local_ip()
    network_url = f"http://{local_ip}:5000"
    
    nl()
    print(f"    Local URL      \\u2192  {CYAN}{local_url}{RESET}")
    print(f"    Network URL    \\u2192  {CYAN}{network_url}{RESET}")
    print(f"    Public URL   \\u2192  {CYAN}{url}{RESET}  (localtunnel)")
    print(f"    API docs       \\u2192  {CYAN}{local_url}/docs{RESET}")
    print(f"    Access Token   \\u2192  {BOLD}{MAGENTA}{token}{RESET}")
    nl()
'''
    content = content.replace('def main():', func_str + '\ndef main():')
    content = content.replace('BACKEND_DIR', 'BASE_DIR')
    open(start_path, 'w', encoding='utf-8').write(content)
