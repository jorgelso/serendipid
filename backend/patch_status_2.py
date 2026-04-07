import sys
import re
from pathlib import Path

content = Path('d:/superbrain/backend/start.py').read_text('utf-8')

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
    print(f"    Local URL      \\u2192  {CYAN}{local_url}{RESET}")
    print(f"    Network URL    \\u2192  {CYAN}{network_url}{RESET}")
    print(f"    Public URL   \\u2192  {CYAN}{url}{RESET}  ({tunnel_type})")
    print(f"    API docs       \\u2192  {CYAN}{local_url}/docs{RESET}")
    nl()

def main():"""

pattern = r'    # Fetch ngrok status via API.*?def main\(\):'
content = re.sub(pattern, new_status, content, flags=re.DOTALL)

Path('d:/superbrain/backend/start.py').write_text(content, 'utf-8')
print("Patched start.py successfully")
