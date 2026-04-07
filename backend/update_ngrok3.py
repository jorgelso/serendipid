import io
import re

fpath = r"d:\superbrain\backend\start.py"
with open(fpath, "r", encoding="utf-8") as f:
    text = f.read()

# Add pyngrok into deps
text = re.sub(
    r'(\("multipart", "python-multipart"\),)',
    r'\1\n        ("pyngrok", "pyngrok"),',
    text, count=1
)

text = re.sub(
    r'LOCALTUNNEL_ENABLED\s*=\s*BASE_DIR\s*/\s*"config"\s*/\s*"localtunnel_enabled\.txt"\nLOCALTUNNEL_LOG\s*=\s*BASE_DIR\s*/\s*"config"\s*/\s*"localtunnel\.log"',
    r'NGROK_ENABLED = BASE_DIR / "config" / "ngrok_enabled.txt"\nNGROK_TOKEN = BASE_DIR / "config" / "ngrok_token.txt"',
    text
)

text = re.sub(
    r'def\s+_stop_localtunnel_processes\(\):.+?return\s+killed',
    r'def _stop_ngrok_processes():\n    return False # Handled by pyngrok internally or main loop process termination',
    text, flags=re.DOTALL
)

text = re.sub(
    r'def\s+_find_public_url_from_log\(\).+?return\s+None',
    r'',
    text, flags=re.DOTALL
)

old_remote = 'def setup_remote_access():\n    h1("Step 6 of 7 — Remote Access (localtunnel / Port Forwarding)")'
if old_remote not in text:
    print("Could not find old_remote, falling back to bytes match")
    old_remote = old_remote.encode("utf-8").decode("utf-8") # try normal

# Use regex to replace setup_remote_access
text = re.sub(
    r'def\s+setup_remote_access\(\):.+?info\("localtunnel\s+will.+?start\.py\."\)',
    r'''def setup_remote_access():
    h1("Step 6 of 7 — Remote Access (ngrok)")
    print(f"""
  The backend runs on {BOLD}port 5000{RESET}. You need to access it from the SuperBrain app.
  We use {BOLD}ngrok{RESET} to create a secure tunnel.

  You need a free ngrok account: {CYAN}https://dashboard.ngrok.com/signup{RESET}
""")

    choice = ask_yn("Enable remote access via ngrok?", default=True)
    if not choice:
        NGROK_ENABLED.unlink(missing_ok=True)
        warn("Skipping ngrok. Local WiFi only.")
        return

    ok("ngrok auto-start enabled")
    NGROK_ENABLED.parent.mkdir(parents=True, exist_ok=True)
    NGROK_ENABLED.write_text("enabled")

    existing_token = NGROK_TOKEN.read_text().strip() if NGROK_TOKEN.exists() else ""
    print(f"\\n  {YELLOW}Paste your ngrok Authtoken.{RESET}")
    auth_token = ask("Authtoken", default=existing_token, paste=True)
    if auth_token.strip():
        NGROK_TOKEN.write_text(auth_token.strip())
        ok("ngrok token saved.")
    else:
        warn("No token provided. ngrok may fail to start.")''',
    text, flags=re.DOTALL
)


# Re-work the launch block exactly
text = re.sub(
    r'_stop_localtunnel_processes\(\).*?_time\.sleep\(0\.8\).*?info\("Starting\s+localtunnel\s+in\s+background.+?public_url = "\(!skipped — localtunnel not enabled\)"',
    r'''# Start ngrok
    public_url = "http://127.0.0.1:5000"
    if NGROK_ENABLED.exists():
        info("Starting ngrok in background...")
        try:
            import pyngrok
            from pyngrok import ngrok
            auth = NGROK_TOKEN.read_text().strip() if NGROK_TOKEN.exists() else None
            if auth:
                ngrok.set_auth_token(auth)
            
            http_tunnel = ngrok.connect(5000, bind_tls=True)
            public_url = http_tunnel.public_url
            ok(f"ngrok active → {GREEN}{BOLD}{public_url}{RESET}")
        except Exception as e:
            warn(f"Could not start ngrok: {e}")
            public_url = "(failed to start ngrok)"
    else:
        public_url = "(skipped — ngrok not enabled)"
''',
    text, flags=re.DOTALL
)


# Additional blind replaces
text = text.replace("LOCALTUNNEL_ENABLED", "NGROK_ENABLED")
text = text.replace("localtunnel", "ngrok")
text = text.replace("loca.lt", "ngrok.app")

with open(fpath, "w", encoding="utf-8") as f:
    f.write(text)
print("Updated start.py")
