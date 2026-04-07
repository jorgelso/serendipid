import sys
from pathlib import Path

content = Path('d:/superbrain/backend/start.py').read_text('utf-8')

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
    print(f"    Local URL      \u2192  {CYAN}{local_url}{RESET}")
    print(f"    Network URL    \u2192  {CYAN}{network_url}{RESET}")
    print(f"    Public URL   \u2192  {CYAN}{url}{RESET}  (localtunnel)")
    print(f"    API docs       \u2192  {CYAN}{local_url}/docs{RESET}")"""

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
    print(f"    Local URL      \u2192  {CYAN}{local_url}{RESET}")
    print(f"    Network URL    \u2192  {CYAN}{network_url}{RESET}")
    print(f"    Public URL   \u2192  {CYAN}{url}{RESET}  ({tunnel_type})")
    print(f"    API docs       \u2192  {CYAN}{local_url}/docs{RESET}")"""

content = content.replace(old_status, new_status)
if "tunnel_type = \"tunnel\"" in content:
    Path('d:/superbrain/backend/start.py').write_text(content, 'utf-8')
    print("Patched start.py successfully")
else:
    print("Patch failed! old_status not found.")
