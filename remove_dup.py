import re
import pathlib
p = pathlib.Path("backend/start.py")
text = p.read_text(encoding="utf-8")

# Let's remove the duplicated block
marker = """def _find_localtunnel_url_from_log() -> str | None:
    try:
        import re
        if not LOCALTUNNEL_LOG.exists():
            return None
        text = LOCALTUNNEL_LOG.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r"https://[\w.-]+\.loca\.lt\b", text)
        return m.group(0) if m else None
    except Exception:
        return None

def _stop_localtunnel_processes():
    try:
        if IS_WINDOWS:
            script = (
                "Get-CimInstance Win32_Process "
                "| Where-Object { $_.CommandLine -match 'localtunnel|\\.loca\\.lt' } "
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
    return None"""

text = text.replace(f"{marker}\n\n{marker}", f"{marker}")
p.write_text(text, encoding="utf-8")
print("Deduplicated code blocks")
