#!/usr/bin/env python3
"""
â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—
â•‘               SuperBrain â€” First-Time Setup & Launcher           â•‘
â•‘         Run this once to configure everything, then again        â•‘
â•‘                    any time to start the server.                 â•‘
â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

Usage:
    python start.py          â€” interactive setup on first run, then start server
    python start.py --reset  â€” re-run the full setup wizard
"""

import sys
import os
import subprocess
import platform
import shutil
import json
import secrets
import string
import textwrap
import time
import importlib
import re
from pathlib import Path

# â”€â”€ Paths â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
BASE_DIR    = Path(__file__).parent.resolve()
VENV_DIR    = BASE_DIR / ".venv"
API_KEYS    = BASE_DIR / "config" / ".api_keys"
TOKEN_FILE  = BASE_DIR / "token.txt"
SETUP_DONE  = BASE_DIR / ".setup_done"

IS_WINDOWS  = platform.system() == "Windows"
PYTHON      = sys.executable          # path that launched this script
VENV_PYTHON = (VENV_DIR / "Scripts" / "python.exe") if IS_WINDOWS else (VENV_DIR / "bin" / "python")
VENV_PIP    = (VENV_DIR / "Scripts" / "pip.exe")    if IS_WINDOWS else (VENV_DIR / "bin" / "pip")

# â”€â”€ ANSI colours (stripped on Windows unless ANSICON / Windows Terminal) â”€â”€â”€â”€â”€â”€
def _ansi(code): return f"\033[{code}m"
RESET  = _ansi(0);  BOLD   = _ansi(1)
RED    = _ansi(31); GREEN  = _ansi(32); YELLOW = _ansi(33)
BLUE   = _ansi(34); CYAN   = _ansi(36); WHITE  = _ansi(37)
DIM    = _ansi(2)
MAGENTA = _ansi(35)
MAG    = MAGENTA

def link(url: str, text: str | None = None) -> str:
    """OSC 8 terminal hyperlink â€” clickable in most modern terminals."""
    label = text or url
    return f"\033]8;;{url}\033\\{label}\033]8;;\033\\"

def banner():
    art = f"""{CYAN}{BOLD}
  â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•—â–ˆâ–ˆâ•—   â–ˆâ–ˆâ•—â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•— â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•—â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•—
  â–ˆâ–ˆâ•”â•â•â•â•â•â–ˆâ–ˆâ•‘   â–ˆâ–ˆâ•‘â–ˆâ–ˆâ•”â•â•â–ˆâ–ˆâ•—â–ˆâ–ˆâ•”â•â•â•â•â•â–ˆâ–ˆâ•”â•â•â–ˆâ–ˆâ•—
  â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•—â–ˆâ–ˆâ•‘   â–ˆâ–ˆâ•‘â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•”â•â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•—  â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•”â•
  â•šâ•â•â•â•â–ˆâ–ˆâ•‘â–ˆâ–ˆâ•‘   â–ˆâ–ˆâ•‘â–ˆâ–ˆâ•”â•â•â•â• â–ˆâ–ˆâ•”â•â•â•  â–ˆâ–ˆâ•”â•â•â–ˆâ–ˆâ•—
  â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•‘â•šâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•”â•â–ˆâ–ˆâ•‘     â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•—â–ˆâ–ˆâ•‘  â–ˆâ–ˆâ•‘
  â•šâ•â•â•â•â•â•â• â•šâ•â•â•â•â•â• â•šâ•â•     â•šâ•â•â•â•â•â•â•â•šâ•â•  â•šâ•â•

  â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•— â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•—  â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•— â–ˆâ–ˆâ•—â–ˆâ–ˆâ–ˆâ•—   â–ˆâ–ˆâ•—
  â–ˆâ–ˆâ•”â•â•â–ˆâ–ˆâ•—â–ˆâ–ˆâ•”â•â•â–ˆâ–ˆâ•—â–ˆâ–ˆâ•”â•â•â–ˆâ–ˆâ•—â–ˆâ–ˆâ•‘â–ˆâ–ˆâ–ˆâ–ˆâ•—  â–ˆâ–ˆâ•‘
  â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•”â•â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•”â•â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•‘â–ˆâ–ˆâ•‘â–ˆâ–ˆâ•”â–ˆâ–ˆâ•— â–ˆâ–ˆâ•‘
  â–ˆâ–ˆâ•”â•â•â–ˆâ–ˆâ•—â–ˆâ–ˆâ•”â•â•â–ˆâ–ˆâ•—â–ˆâ–ˆâ•”â•â•â–ˆâ–ˆâ•‘â–ˆâ–ˆâ•‘â–ˆâ–ˆâ•‘â•šâ–ˆâ–ˆâ•—â–ˆâ–ˆâ•‘
  â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•”â•â–ˆâ–ˆâ•‘  â–ˆâ–ˆâ•‘â–ˆâ–ˆâ•‘  â–ˆâ–ˆâ•‘â–ˆâ–ˆâ•‘â–ˆâ–ˆâ•‘ â•šâ–ˆâ–ˆâ–ˆâ–ˆâ•‘
  â•šâ•â•â•â•â•â• â•šâ•â•  â•šâ•â•â•šâ•â•  â•šâ•â•â•šâ•â•â•šâ•â•  â•šâ•â•â•â•
{RESET}"""
    credit = (f"    {DIM}made with {RESET}{MAG}â¤{RESET}{DIM}  by "
              f"{link('https://github.com/sidinsearch', f'{BOLD}sidinsearch{RESET}{DIM}')}"
              f"{RESET}\n")
    print(art + credit)

def h1(msg):  print(f"\n{BOLD}{CYAN}{'â”'*64}{RESET}\n{BOLD}  {msg}{RESET}\n{BOLD}{CYAN}{'â”'*64}{RESET}")
def h2(msg):  print(f"\n{BOLD}{BLUE}  â–¶  {msg}{RESET}")
def ok(msg):  print(f"  {GREEN}âœ“{RESET}  {msg}")
def warn(msg):print(f"  {YELLOW}âš {RESET}  {msg}")
def err(msg): print(f"  {RED}âœ—{RESET}  {msg}")
def info(msg):print(f"  {DIM}{msg}{RESET}")
def nl():     print()

def ask(prompt, default=None, secret=False, paste=False):
    """
    Prompt for input.
      secret=True  â€” uses getpass (hidden, no echo) â€” good for passwords typed char-by-char.
      paste=True   â€” uses plain input (visible) so Ctrl+V / right-click paste works;
                     existing value is shown as â—â—â—â— to indicate something is already set.
    """
    if paste and default:
        display_default = f" [{DIM}â—â—â—â— (already set â€” paste to replace){RESET}]"
    elif default:
        display_default = f" [{DIM}{default}{RESET}]"
    else:
        display_default = ""

    full_prompt = f"\n  {BOLD}{prompt}{RESET}{display_default}: "

    if secret:
        import getpass
        val = getpass.getpass(full_prompt)
    else:
        val = input(full_prompt).strip()
    return val if val else default

def ask_yn(prompt, default=True):
    suffix = f"[{BOLD}Y{RESET}/n]" if default else f"[y/{BOLD}N{RESET}]"
    val = input(f"\n  {BOLD}{prompt}{RESET} {suffix}: ").strip().lower()
    if not val:
        return default
    return val in ("y", "yes")

def run(cmd, **kwargs):
    """Run a command, raise on failure."""
    return subprocess.run(cmd, check=True, **kwargs)

def run_q(cmd, **kwargs):
    """Run a command silently, capture output."""
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kwargs)


def _load_saved_api_keys() -> dict[str, str]:
    """Load saved API keys and credentials from config/.api_keys."""
    keys: dict[str, str] = {}
    if API_KEYS.exists():
        for line in API_KEYS.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                keys[k.strip()] = v.strip()
    return keys


CORE_PACKAGES = [
    "fastapi>=0.111.0",
    "uvicorn[standard]>=0.29.0",
    "pydantic>=2.0.0",
    "python-multipart>=0.0.9",
    "requests>=2.31.0",
    "httpx>=0.27.0",
    "groq>=0.9.0",
    "google-genai>=0.8.0",
    "beautifulsoup4>=4.12.0",
    "trafilatura>=1.12.0",
    "newspaper4k>=0.9.0",
    "lxml>=5.0.0",
    "lxml_html_clean>=0.1.0",
    "htmldate>=1.9.0",
    "instaloader>=4.11.0",
    "rich>=13.0.0",
    "segno>=1.6.0",
]


def ensure_runtime_dependencies():
    """Install must-have runtime packages if missing in the active venv."""
    required = [
        ("fastapi", "fastapi"),
        ("uvicorn", "uvicorn"),
        ("multipart", "python-multipart"),
        ("pyngrok", "pyngrok"),
        ("instaloader", "instaloader"),
        ("segno", "segno"),
    ]
    missing: list[str] = []

    for module_name, package_name in required:
        # Check if the module is actually importable in the virtual environment
        rc = subprocess.run(
            [str(VENV_PYTHON), "-c", f"import {module_name}"],
            capture_output=True
        ).returncode
        if rc != 0:
            missing.append(package_name)

    if not missing:
        return

    warn(f"Missing runtime package(s): {', '.join(missing)}")
    info("Installing missing runtime package(s) automatically â€¦")
    try:
        run([str(VENV_PYTHON), "-m", "pip", "install", *missing])
        ok("Runtime dependencies installed")
    except Exception as e:
        err(f"Failed to install runtime dependencies: {e}")
        info(f"Run manually: {VENV_PYTHON} -m pip install {' '.join(missing)}")
        sys.exit(1)

# â”€â”€ Helpers for live output displays â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
BAR_WIDTH = 36

def _ascii_bar(completed: int, total: int, width: int = BAR_WIDTH) -> str:
    """Return a coloured ASCII progress bar string."""
    if total <= 0:
        return ""
    pct  = min(completed / total, 1.0)
    fill = int(width * pct)
    bar  = f"{GREEN}{'â–ˆ' * fill}{DIM}{'â–‘' * (width - fill)}{RESET}"
    mb_d = completed / 1_048_576
    mb_t = total    / 1_048_576
    return f"[{bar}] {mb_d:6.1f} / {mb_t:.1f} MB  {pct*100:5.1f}%"

def _overwrite(line: str):
    """Overwrite the current terminal line in-place."""
    sys.stdout.write(f"\r  {line}")
    sys.stdout.flush()

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# Step 1 â€” Virtual Environment
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
def setup_venv():
    h1("Step 1 of 6 â€” Python Virtual Environment")
    if VENV_DIR.exists():
        ok(f"Virtual environment already exists at {VENV_DIR}")
        return
    h2("Creating virtual environment â€¦")
    run([PYTHON, "-m", "venv", str(VENV_DIR)])
    ok(f"Virtual environment created at {VENV_DIR}")

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# Step 2 â€” Install Dependencies
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
def install_deps():
    h1("Step 2 of 7 â€” Installing Core Python Dependencies")

    h2("Upgrading pip â€¦")
    run([str(VENV_PYTHON), "-m", "pip", "install", "--quiet", "--upgrade", "pip"])
    ok("pip up to date")

    h2("Installing core runtime packages â€¦")
    info("Optional packages such as local Whisper, OpenCV, and music ID are installed only when enabled.")
    run([str(VENV_PIP), "install", "--progress-bar", "off", *CORE_PACKAGES])
    ok(f"Installed {len(CORE_PACKAGES)} core package(s)")

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# â”€â”€ API key validators â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Return values:
#   (True,  detail)  â€” key is definitely valid
#   (False, detail)  â€” key is definitely INVALID  (401 / explicit auth error)
#   (None,  detail)  â€” could not verify (network, 403 scope, timeout, etc.)

def _validate_gemini(key: str):
    """Hit the Gemini models list endpoint â€” any valid key returns 200."""
    try:
        import urllib.request as _r, json as _j
        req = _r.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models?key={key}",
            headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"})
        with _r.urlopen(req, timeout=8) as resp:
            data = _j.loads(resp.read())
            count = len(data.get("models", []))
            return True, f"{count} models accessible"
    except Exception as e:
        msg = str(e)
        if "400" in msg:
            return False, "invalid key (400 Bad Request)"
        if "401" in msg:
            return False, "invalid key (401 Unauthorized)"
        # 403, timeouts, etc. â€” cannot determine validity
        return None, f"could not verify ({msg[:70]})"

def _validate_groq(key: str):
    """
    Test with a minimal chat completion (max_tokens=1).
    Must include User-Agent to pass Cloudflare (error 1010 without it).
    """
    try:
        import urllib.request as _r, urllib.error as _e, json as _j
        body = _j.dumps({
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 1,
        }).encode()
        req = _r.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=body,
            headers={"Authorization": f"Bearer {key}",
                     "Content-Type": "application/json",
                     "Accept": "application/json",
                     "User-Agent": "Mozilla/5.0"},
            method="POST",
        )
        with _r.urlopen(req, timeout=10) as resp:
            return True, "key valid"
    except _e.HTTPError as e:
        if e.code in (401, 400):
            return False, f"invalid key ({e.code} {e.reason})"
        # 403, 429, 503, etc. â€” key may be fine
        return None, f"could not verify ({e.code} {e.reason})"
    except Exception as e:
        return None, f"could not verify ({str(e)[:70]})"

def _validate_openrouter(key: str):
    try:
        import urllib.request as _r, urllib.error as _e, json as _j
        req = _r.Request("https://openrouter.ai/api/v1/auth/key",
                         headers={"Authorization": f"Bearer {key}",
                                  "Accept": "application/json",
                                  "User-Agent": "Mozilla/5.0"})
        with _r.urlopen(req, timeout=8) as resp:
            data = _j.loads(resp.read())
            label = data.get("data", {}).get("label", "")
            return True, label or "key valid"
    except _e.HTTPError as e:
        if e.code in (401, 400):
            return False, f"invalid key ({e.code})"
        return None, f"could not verify ({e.code} {e.reason})"
    except Exception as e:
        return None, f"could not verify ({str(e)[:70]})"

def _check_and_report(name: str, key: str, validator) -> str:
    """Validate `key`, print result inline, return the key unchanged."""
    if not key:
        return key
    print(f"  {DIM}Checking {name} key â€¦{RESET}", end="", flush=True)
    result, detail = validator(key)
    if result is True:
        print(f"\r  {GREEN}âœ“{RESET}  {name}: {detail}                            ")
    elif result is False:
        print(f"\r  {RED}âœ—{RESET}  {name}: {detail}                            ")
        warn(f"That key looks invalid â€” double-check at the provider dashboard.")
    else:
        # None â€” ambiguous, don't cry wolf
        print(f"\r  {YELLOW}~{RESET}  {name}: {detail}                            ")
        info("Could not reach the API right now â€” key saved, will be tested on first use.")
    return key

# Step 3 â€” API Keys
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
def setup_api_keys():
    h1("Step 3 of 7 â€” AI Provider Keys")

    print(f"""
  SuperBrain uses AI providers to analyse your saved content.
  You need {BOLD}at least one{RESET} key â€” the router tries them in order and
  falls back automatically.

  Recommended: {GREEN}Gemini{RESET} (most generous free tier â€” 1 500 req/day)

  Get free keys:
    Gemini      â†’  {CYAN}https://aistudio.google.com/apikey{RESET}
    Groq        â†’  {CYAN}https://console.groq.com/keys{RESET}
    OpenRouter  â†’  {CYAN}https://openrouter.ai/keys{RESET}

  Press {BOLD}Enter{RESET} to skip any key you don't have yet.
  {DIM}Keys and passwords are visible as you paste â€” don't run setup in a screen share.{RESET}
""")

    # Load existing values if re-running
    existing = {}
    if API_KEYS.exists():
        for line in API_KEYS.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                existing[k.strip()] = v.strip()

    gemini   = ask("Gemini API key",      default=existing.get("GEMINI_API_KEY"),      paste=True) or ""
    gemini   = _check_and_report("Gemini",      gemini, _validate_gemini)
    groq_k   = ask("Groq API key",        default=existing.get("GROQ_API_KEY"),        paste=True) or ""
    groq_k   = _check_and_report("Groq",        groq_k, _validate_groq)
    openr    = ask("OpenRouter API key",  default=existing.get("OPENROUTER_API_KEY"),  paste=True) or ""
    openr    = _check_and_report("OpenRouter",  openr,  _validate_openrouter)

    if not any([gemini, groq_k, openr]):
        warn("No AI keys entered. SuperBrain will still work but can only use")
        warn("local Ollama models (configured in the next step).")

    # Instagram credentials
    nl()
    print(f"  {BOLD}Instagram Credentials{RESET}")
    print(f"""
  Used for downloading private/public Instagram posts.
  {YELLOW}Use a secondary / burner account â€” NOT your main account.{RESET}
  The session is cached after first login so you won't be asked again.

  {DIM}Without credentials:{RESET}
    SuperBrain can still save and analyse {BOLD}YouTube videos{RESET} and {BOLD}Websites{RESET}
    without any Instagram account. However, Instagram posts will be limited:
    â€¢ Only {BOLD}public posts{RESET} that are accessible without login may work.
    â€¢ You {BOLD}cannot process multiple Instagram posts back-to-back{RESET} â€”
      Instagram enforces a rate-limit cool-down between unauthenticated
      requests. You may need to wait several minutes between saves.
    Adding credentials removes these restrictions entirely.

  Press {BOLD}Enter{RESET} to skip.
""")
    ig_user = ask("Instagram username", default=existing.get("INSTAGRAM_USERNAME")) or ""
    ig_pass = ask("Instagram password", default=existing.get("INSTAGRAM_PASSWORD"), paste=True) or ""

    # Write .api_keys
    API_KEYS.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# SuperBrain API Keys â€” DO NOT COMMIT THIS FILE\n",
        f"GEMINI_API_KEY={gemini}\n",
        f"GROQ_API_KEY={groq_k}\n",
        f"OPENROUTER_API_KEY={openr}\n",
        "\n",
        f"INSTAGRAM_USERNAME={ig_user}\n",
        f"INSTAGRAM_PASSWORD={ig_pass}\n",
    ]
    API_KEYS.write_text("".join(lines))
    ok(f"Keys saved to {API_KEYS}")

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# Step 4 â€” Ollama / Offline Model
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
OLLAMA_MODEL = "qwen3-vl:4b"   # vision-language model, fits ~6 GB VRAM / ~8 GB RAM

def setup_ollama():
    h1("Step 4 of 7 â€” Offline AI Model (Ollama)")

    keys = _load_saved_api_keys()
    has_cloud_key = any(keys.get(k) for k in ("GEMINI_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY"))

    print(f"""
  Ollama runs AI models {BOLD}locally on your machine{RESET} â€” no internet or API
  key required. SuperBrain uses it as a last-resort fallback if all
  cloud providers fail or run out of quota.

  Recommended model: {BOLD}{OLLAMA_MODEL}{RESET}  (~3 GB download, needs ~8 GB RAM)
    â†’ Vision-language model: understands both text AND images.
  Other options: llama3.2:3b (2 GB / 4 GB RAM), gemma2:2b (1.5 GB / 4 GB RAM)
""")

    if has_cloud_key:
        info("Cloud API key(s) detected â€” Ollama is optional and skipped by default.")

    if not ask_yn("Set up Ollama offline model?", default=not has_cloud_key):
        warn("Skipping Ollama. Cloud providers only â€” make sure you have API keys.")
        return

    # Check if ollama binary is available
    if not shutil.which("ollama"):
        print(f"""
  {YELLOW}Ollama is not installed.{RESET}

  Install it first:
    Linux / macOS  â†’  {CYAN}curl -fsSL https://ollama.com/install.sh | sh{RESET}
    Windows        â†’  Download from {CYAN}https://ollama.com/download{RESET}

  After installing, re-run {BOLD}python start.py{RESET} to continue.
""")
        if not ask_yn("Continue setup anyway (skip model pull for now)?", default=False):
            sys.exit(0)
        warn("Skipping model pull. Run  ollama pull {OLLAMA_MODEL}  manually later.")
        return

    ok("Ollama binary found")

    # Check if model already pulled
    try:
        result = run_q(["ollama", "list"])
        if OLLAMA_MODEL.split(":")[0] in result.stdout:
            ok(f"Model {OLLAMA_MODEL} already available")
            return
    except Exception:
        pass

    custom = ask(f"Model to pull", default=OLLAMA_MODEL)
    model  = custom or OLLAMA_MODEL

    h2(f"Pulling {model} â€” this downloads ~3 GB, grab a coffee â˜•")
    nl()
    try:
        _ollama_pull_with_progress(model)
    except subprocess.CalledProcessError:
        err(f"Failed to pull {model}.")
        warn(f"Run manually later:  ollama pull {model}")

def _ollama_pull_with_progress(model: str):
    """Run `ollama pull` and render a live per-layer progress bar."""
    import json as _json

    cmd = ["ollama", "pull", model]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, bufsize=1)

    # digest â†’ (total_bytes, completed_bytes, short_label)
    layers: dict[str, tuple[int, int, str]] = {}
    last_status = ""
    active_digest = ""
    render_line   = False   # True while a progress bar is being overwritten

    for raw in proc.stdout:  # type: ignore[union-attr]
        raw = raw.strip()
        if not raw:
            continue

        # Ollama outputs plain-text lines (not JSON) when not a TTY â€” accept both
        try:
            data = _json.loads(raw)
        except _json.JSONDecodeError:
            # plain text line from older Ollama or piped output
            if render_line:
                sys.stdout.write("\n"); render_line = False
            if raw != last_status:
                last_status = raw
                print(f"  {CYAN}â†’{RESET}  {raw}")
            continue

        status   = data.get("status",    "")
        digest   = data.get("digest",    "")
        total    = int(data.get("total",    0))
        completed= int(data.get("completed",0))

        if digest and total > 0:
            short = (digest.split(":")[-1])[:12]  # e.g. "a1b2c3d4e5f6"
            layers[digest] = (total, completed, short)
            active_digest  = digest
            bar = _ascii_bar(completed, total)
            _overwrite(f"{DIM}{short}{RESET}  {bar}")
            render_line = True

        elif status and status != last_status:
            if render_line:
                sys.stdout.write("\n"); render_line = False
            last_status = status
            # Show a checkmark when a layer finishes
            done_statuses = ("verifying sha256 digest", "writing manifest",
                             "removing any unused layers", "success")
            if any(s in status.lower() for s in done_statuses):
                print(f"  {GREEN}âœ“{RESET}  {status}")
            else:
                print(f"  {CYAN}â†’{RESET}  {status}")

    if render_line:
        sys.stdout.write("\n"); render_line = False

    proc.wait()
    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, cmd)

    ok(f"Model {model} ready")

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# Step 5 â€” Whisper / Offline Transcription
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
WHISPER_MODELS = {
    "tiny":   (" ~74 MB", "fastest, lower accuracy"),
    "base":   ("~142 MB", "good balance  â­ recommended"),
    "small":  ("~461 MB", "higher accuracy"),
    "medium": ("~1.5 GB", "high accuracy, slower"),
    "large":  ("~2.9 GB", "best accuracy, needs 10 GB RAM"),
}

def setup_whisper():
    h1("Step 5 of 7 â€” Offline Audio Transcription (Whisper)")

    keys = _load_saved_api_keys()
    has_groq_key = bool(keys.get("GROQ_API_KEY") or os.getenv("GROQ_API_KEY"))

    print(f"""
  OpenAI Whisper transcribes audio and video {BOLD}entirely on your machine{RESET}.
  SuperBrain uses it to extract speech from Instagram Reels, YouTube
  videos, and any other saved media â€” no API key needed.

  Whisper requires {BOLD}ffmpeg{RESET} to be installed on your system.
  It also pre-downloads a speech model the first time it runs.
""")

    if has_groq_key:
        info("Groq API key detected â€” cloud Whisper is available, so local Whisper is optional.")
        if not ask_yn("Also install local Whisper fallback?", default=False):
            warn("Skipping local Whisper. Groq Whisper will be used when Groq is available.")
            return
    else:
        if not ask_yn("Set up local Whisper offline transcription?", default=True):
            warn("Skipping Whisper setup. Audio transcription will rely on cloud providers if available.")
            return

    # â”€â”€ ffmpeg check â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if shutil.which("ffmpeg"):
        ok("ffmpeg is installed")
    else:
        warn("ffmpeg is NOT installed â€” Whisper cannot run without it.")
        print(f"""
  Install ffmpeg:
    Linux / WSL  â†’  {CYAN}sudo apt install ffmpeg{RESET}
    macOS        â†’  {CYAN}brew install ffmpeg{RESET}
    Windows      â†’  {CYAN}winget install ffmpeg{RESET}
                    or download from {CYAN}https://ffmpeg.org/download.html{RESET}

  After installing ffmpeg, re-run {BOLD}python start.py --reset{RESET} or just
  restart â€” Whisper will work automatically once ffmpeg is present.
""")
        if not ask_yn("Continue setup anyway?", default=True):
            sys.exit(0)

    # â”€â”€ Whisper package check / install â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    try:
        result = run_q([str(VENV_PYTHON), "-c", "import whisper; print(whisper.__version__)"])
        ok(f"openai-whisper installed (version {result.stdout.strip()})")
    except Exception:
        warn("openai-whisper not found â€” installing now â€¦")
        nl()
        try:
            cmd = [str(VENV_PIP), "install", "--progress-bar", "off", "openai-whisper>=20231117"]
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, bufsize=1)
            for raw in proc.stdout:  # type: ignore[union-attr]
                line = raw.rstrip()
                if not line:
                    continue
                if line.startswith("Collecting "):
                    print(f"  {CYAN}â†“{RESET}  {BOLD}{line.split()[1]}{RESET}")
                elif "Downloading" in line and (".whl" in line or ".tar.gz" in line):
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        print(f"       {DIM}â†“ {parts[1]}  {' '.join(parts[2:]).strip('()')}{RESET}")
                elif line.startswith("Successfully installed"):
                    print(f"  {GREEN}âœ“  {line}{RESET}")
                elif "error" in line.lower() or "ERROR" in line:
                    print(f"  {RED}{line}{RESET}")
            proc.wait()
            if proc.returncode == 0:
                result = run_q([str(VENV_PYTHON), "-c", "import whisper; print(whisper.__version__)"])
                ok(f"openai-whisper installed (version {result.stdout.strip()})")
            else:
                err("openai-whisper install failed â€” offline transcription will not work.")
                if not ask_yn("Continue setup anyway?", default=True):
                    sys.exit(0)
                return
        except Exception as e:
            err(f"openai-whisper install failed: {e}")
            if not ask_yn("Continue setup anyway?", default=True):
                sys.exit(0)
            return

    # â”€â”€ Model pre-download â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    nl()
    print(f"  {BOLD}Whisper model pre-download{RESET}")
    print(f"  Pre-downloading a model now avoids a delay on first use.\n")

    rows = ""
    for name, (size, note) in WHISPER_MODELS.items():
        star = f"  {YELLOW}â† default if skipped{RESET}" if name == "base" else ""
        rows += f"    {BOLD}{name:<8}{RESET} {size}  {DIM}{note}{RESET}{star}\n"
    print(rows)

    choice = ask("Model to pre-download", default="base")
    model  = choice.strip().lower() if choice else "base"
    if model not in WHISPER_MODELS:
        warn(f"Unknown model '{model}' â€” defaulting to 'base'.")
        model = "base"

    # â”€â”€ Save model choice to config â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    whisper_cfg = BASE_DIR / "config" / "whisper_model.txt"
    (BASE_DIR / "config").mkdir(exist_ok=True)
    whisper_cfg.write_text(model)
    ok(f"Whisper model set to '{model}' (saved to config/whisper_model.txt)")

    h2(f"Pre-downloading Whisper '{model}' model â€¦")
    print(f"  {DIM}(Whisper's own progress bar will appear below){RESET}\n")
    try:
        # Don't capture: let tqdm's download progress bars stream to the terminal
        run([str(VENV_PYTHON), "-c",
             f"import whisper; print('Loading model â€¦'); whisper.load_model('{model}'); print('Done.')"])
        nl()
        ok(f"Whisper '{model}' model downloaded and cached")
    except subprocess.CalledProcessError:
        err(f"Pre-download failed â€” Whisper will download '{model}' automatically on first use.")

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# Step 6 â€” Remote Access / Port Forwarding
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
NGROK_ENABLED = BASE_DIR / "config" / "ngrok_enabled.txt"
NGROK_TOKEN = BASE_DIR / "config" / "ngrok_token.txt"
LOCALTUNNEL_LOG = BASE_DIR / "config" / "localtunnel.log"
LOCALTUNNEL_LOG = BASE_DIR / "config" / "localtunnel.log"

def setup_remote_access():
    h1("Step 6 of 7 â€” Remote Access (ngrok / localtunnel)")

    print(f"""
  The SuperBrain backend runs locally. Your phone needs to reach it over the internet.
  We recommend {BOLD}ngrok{RESET} for a secure tunnel.
  If ngrok is not configured or fails, {BOLD}localtunnel{RESET} will be used as a fallback.

  Requires a free account from: {CYAN}https://dashboard.ngrok.com/signup{RESET}
  Get your Authtoken at: {CYAN}https://dashboard.ngrok.com/get-started/your-authtoken{RESET}
""")

    choice = ask_yn("Enable ngrok on startup?", default=True)
    if not choice:
        NGROK_ENABLED.unlink(missing_ok=True)
        warn("Skipping ngrok. Will use localtunnel as fallback.")
        return

    ok("ngrok auto-start enabled")
    NGROK_ENABLED.parent.mkdir(parents=True, exist_ok=True)
    NGROK_ENABLED.write_text("enabled")

    existing_token = NGROK_TOKEN.read_text().strip() if NGROK_TOKEN.exists() else ""
    print(f"\n  {YELLOW}Please paste your ngrok Authtoken.{RESET}")
    if existing_token:
         print(f"  {DIM}(Leave blank to keep existing token){RESET}")
         
    auth_token = ask("Authtoken", default=existing_token, paste=True)
    if auth_token.strip():
        NGROK_TOKEN.write_text(auth_token.strip())
        ok("ngrok token saved.")
    else:
        warn("No ngrok token provided. ngrok may disconnect. To fix, re-run setup.")

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# Step 6 â€” Access Token & Database
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
def setup_token_and_db():
    h1("Step 7 of 7 â€” Access Token & Database")

    # Token
    if TOKEN_FILE.exists():
        token = TOKEN_FILE.read_text().strip()
        if token and len(token) == 8 and token.isalnum():
            ok(f"Access Token already exists: {BOLD}{token}{RESET}")
            if not ask_yn("Generate a new Access Token?", default=False):
                return
        elif token:
            warn("Existing token uses old format. A new 8-character Access Token will be generated.")
    else:
        token = None

    alphabet = string.ascii_uppercase + string.digits
    new_token = ''.join(secrets.choice(alphabet) for _ in range(8))
    TOKEN_FILE.write_text(new_token)
    ok(f"Access Token saved: {BOLD}{GREEN}{new_token}{RESET}")
    nl()
    print(f"  {YELLOW}Copy this token into the mobile app â†’ Settings â†’ Access Token.{RESET}")

    # DB is auto-created on first backend start; just let the user know
    nl()
    info("The SQLite database (superbrain.db) will be created automatically")
    info("the first time the backend starts.")

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# Launch Backend
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
def _find_localtunnel_url_from_log() -> str | None:
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

def _find_localtunnel_url_from_log() -> str | None:
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

def _start_ngrok(port: int) -> str | None:
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
        return None

def _get_windows_pids_on_port(port: int) -> list[int]:
    """Return listener PIDs on Windows using Get-NetTCPConnection when available."""
    pids: set[int] = set()
    try:
        ps_cmd = (
            f"Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction SilentlyContinue "
            "| Select-Object -ExpandProperty OwningProcess -Unique"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            check=False,
            capture_output=True,
            text=True,
        )
        for row in (result.stdout or "").splitlines():
            row = row.strip()
            if row.isdigit():
                pids.add(int(row))
    except Exception:
        pass
    return sorted(pids)

def _check_port(port: int) -> int | None:
    """Return the PID occupying `port`, or None if free."""
    import socket as _socket
    with _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        if s.connect_ex(("127.0.0.1", port)) != 0:
            return None   # port is free

    # Port is busy â€” try to find the PID
    try:
        if IS_WINDOWS:
            out = run_q(["netstat", "-ano"]).stdout
            for line in out.splitlines():
                parts = line.strip().split()
                if len(parts) >= 5 and parts[0].upper() == "TCP" and parts[3].upper() == "LISTENING":
                    local_addr = parts[1]
                    if local_addr.endswith(f":{port}"):
                        return int(parts[-1])
        else:
            out = run_q(["lsof", "-ti", f"TCP:{port}", "-sTCP:LISTEN"]).stdout.strip()
            if out:
                return int(out.splitlines()[0])
    except Exception:
        pass
    return -1   # busy but PID unknown


def _find_pids_on_port(port: int) -> list[int]:
    """Return all PIDs listening on a given port."""
    pids: set[int] = set()
    try:
        if IS_WINDOWS:
            for pid in _get_windows_pids_on_port(port):
                pids.add(pid)

            out = run_q(["netstat", "-ano"]).stdout
            for line in out.splitlines():
                parts = line.strip().split()
                if len(parts) >= 5 and parts[0].upper() == "TCP" and parts[3].upper() == "LISTENING":
                    local_addr = parts[1]
                    if local_addr.endswith(f":{port}"):
                        try:
                            pids.add(int(parts[-1]))
                        except ValueError:
                            pass
        else:
            out = run_q(["lsof", "-ti", f"TCP:{port}", "-sTCP:LISTEN"]).stdout.strip()
            if out:
                for row in out.splitlines():
                    try:
                        pids.add(int(row.strip()))
                    except ValueError:
                        pass
    except Exception:
        pass
    return sorted(pids)


def _kill_pid_windows(pid: int) -> bool:
    """Best-effort kill for a Windows PID. Returns True if command succeeded."""
    try:
        result = subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return True

        # Fallback for cases where taskkill can't resolve a rapidly-exiting process.
        ps = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"Stop-Process -Id {pid} -Force -ErrorAction SilentlyContinue",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        return ps.returncode == 0
    except Exception:
        return False


def _clear_port_listeners(port: int, attempts: int = 6) -> bool:
    """Try multiple passes to free a busy port by killing all listeners."""
    for _ in range(attempts):
        if _check_port(port) is None:
            return True

        pids = _find_pids_on_port(port)
        if not pids:
            time.sleep(0.8)
            continue

        for ep in pids:
            try:
                if IS_WINDOWS:
                    _kill_pid_windows(ep)
                else:
                    os.kill(ep, 9)
            except Exception:
                pass
        time.sleep(0.8)

    return _check_port(port) is None


def _detect_local_ip() -> str:
    """Best-effort LAN IP detection for same-network mobile access."""
    import socket

    # Most reliable route-based detection.
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass

    # Hostname fallback.
    try:
        ip = socket.gethostbyname(socket.gethostname())
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass

    return "127.0.0.1"

def _display_connect_qr(url: str, token: str):
    """Display a QR code in the terminal without depending on the active interpreter."""

    payload = json.dumps({"url": url, "token": token}, separators=(',', ':'))
    qr_script = textwrap.dedent(r'''
        import json
        import sys

        import segno

        payload = sys.argv[1]
        qr = segno.make(payload, error='L')

        matrix = [list(row) for row in qr.matrix]
        rows = len(matrix)
        cols = len(matrix[0]) if rows else 0

        quiet = 2
        padded_cols = cols + quiet * 2
        padded_rows = rows + quiet * 2
        padded = []
        empty_row = [0] * padded_cols
        for _ in range(quiet):
            padded.append(list(empty_row))
        for row in matrix:
            padded.append([0] * quiet + row + [0] * quiet)
        for _ in range(quiet):
            padded.append(list(empty_row))

        print(f"  â”Œ{'â”€' * (padded_cols + 4)}â”")
        
        # Center the title within the inner frame
        inner_width = padded_cols + 4
        title = "Scan with SuperBrain App"
        # If the width is too small, truncate it just in case, though QR is usually wider
        if len(title) > inner_width - 2:
            title = title[:inner_width - 2]
        
        print(f"  â”‚{title.center(inner_width)}â”‚")
        print(f"  â”œ{'â”€' * inner_width}â”¤")

        for y in range(0, padded_rows, 2):
            line_chars = []
            for x in range(padded_cols):
                top = padded[y][x] if y < padded_rows else 0
                bottom = padded[y + 1][x] if y + 1 < padded_rows else 0

                if top and bottom:
                    line_chars.append("â–ˆ")
                elif top and not bottom:
                    line_chars.append("â–€")
                elif not top and bottom:
                    line_chars.append("â–„")
                else:
                    line_chars.append(" ")

            print(f"  â”‚  {''.join(line_chars)}  â”‚")

        print(f"  â””{'â”€' * (padded_cols + 4)}â”˜")
    ''')

    interpreters = []
    if VENV_PYTHON.exists():
        interpreters.append(str(VENV_PYTHON))
    if sys.executable not in interpreters:
        interpreters.append(sys.executable)

    import os
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    
    for python_executable in interpreters:
        try:
            result = subprocess.run(
                [python_executable, "-c", qr_script, payload],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
            )
            nl()
            print(result.stdout, end="")
            nl()
            return
        except subprocess.CalledProcessError as e:
            try:
                run([python_executable, "-m", "pip", "install", "--quiet", "segno"])
                result = run_q([python_executable, "-c", qr_script, payload], encoding="utf-8", errors="replace", env=env)
                nl()
                print(result.stdout, end="")
                nl()
                return
            except subprocess.CalledProcessError as e2:
                warn(f"Failed to generate QR code using {python_executable}. STDOUT: {e2.stdout} STDERR: {e2.stderr}")
                continue
            except Exception as ex:
                warn(f"Failed to generate QR code using {python_executable}: {ex}")
                continue

    warn("Could not generate QR code.")
    info("Use the server URL and Access Token shown below to connect manually.")


def launch_backend():
    h1("Launching SuperBrain Backend")

    # Ensure upload endpoints won't crash FastAPI at import time.
    ensure_runtime_dependencies()

    # â”€â”€ Port conflict check â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    PORT = 5000
    pid = _check_port(PORT)
    if pid is not None:
        if pid > 0:
            warn(f"Port {PORT} is already in use by PID {BOLD}{pid}{RESET}.")
        else:
            warn(f"Port {PORT} is already in use (PID unknown).")

        nl()
        print(f"  This is usually a previous SuperBrain server that wasn't stopped.")
        print(f"  Options:")
        print(f"    {BOLD}1{RESET}  Kill the existing process and start fresh  {DIM}(recommended){RESET}")
        print(f"    {BOLD}2{RESET}  Exit â€” I'll stop it manually then re-run start.py")
        nl()
        choice = input(f"  {BOLD}Choose [1/2]{RESET}: ").strip()

        if choice != "1":
            nl()
            if pid and pid > 0:
                info(f"Stop it with:  kill {pid}")
            else:
                info(f"Find what's on port {PORT}:  lsof -i :{PORT}   (Linux/macOS)")
                info(f"                              netstat -ano | findstr :{PORT}   (Windows)")
            info("Then re-run:  python start.py")
            sys.exit(0)

        # Kill it
        try:
            import signal as _sig
            if pid and pid > 0:
                if IS_WINDOWS:
                    killed = _kill_pid_windows(pid)
                    if not killed:
                        warn(f"PID {pid} is no longer active. Trying current listeners on port {PORT} â€¦")
                else:
                    os.kill(pid, _sig.SIGTERM)
                time.sleep(1)
                # If still alive, SIGKILL
                if not IS_WINDOWS:
                    try:
                        os.kill(pid, 0)   # check if process exists
                        os.kill(pid, _sig.SIGKILL)
                        time.sleep(0.5)
                    except ProcessLookupError:
                        pass

                # Verify port is free; if not, keep clearing listeners until stable.
                _clear_port_listeners(PORT)

                if _check_port(PORT) is None:
                    ok(f"Process {pid} stopped")
                else:
                    err(f"Port {PORT} is still in use after kill attempt.")
                    if IS_WINDOWS:
                        info(f"Run manually:  netstat -ano | findstr :{PORT}")
                        info("Then:         taskkill /PID <pid> /T /F")
                        info("Or inspect:    powershell Get-NetTCPConnection -LocalPort 5000 -State Listen")
                    else:
                        info(f"Run:  lsof -ti TCP:{PORT} -sTCP:LISTEN | xargs kill -9")
                    sys.exit(1)
            else:
                # Unknown PID â€” try to kill all listeners we can find
                extra_pids = _find_pids_on_port(PORT)
                if not extra_pids:
                    err("Cannot determine PID automatically.")
                    if IS_WINDOWS:
                        info(f"Run manually:  netstat -ano | findstr :{PORT}")
                        info("Then:         taskkill /PID <pid> /F")
                    else:
                        info(f"Run:  lsof -ti TCP:{PORT} -sTCP:LISTEN | xargs kill -9")
                    info("Then re-run:  python start.py")
                    sys.exit(1)

                _clear_port_listeners(PORT)
                if _check_port(PORT) is None:
                    ok(f"Cleared port {PORT} by terminating PID(s): {', '.join(str(x) for x in extra_pids)}")
                else:
                    err(f"Port {PORT} is still busy.")
                    if IS_WINDOWS:
                        info(f"Run manually:  netstat -ano | findstr :{PORT}")
                        info("Then:         taskkill /PID <pid> /T /F")
                    else:
                        info(f"Run:  lsof -ti TCP:{PORT} -sTCP:LISTEN | xargs kill -9")
                    sys.exit(1)
        except Exception as e:
            err(f"Failed to kill process: {e}")
            if IS_WINDOWS:
                if pid and pid > 0:
                    info(f"Try manually:  taskkill /PID {pid} /F")
                info(f"Or list listeners:  netstat -ano | findstr :{PORT}")
            else:
                info(f"Try manually:  kill -9 {pid}")
            sys.exit(1)

    token = TOKEN_FILE.read_text().strip() if TOKEN_FILE.exists() else "â€”"
    local_ip = _detect_local_ip()

    # tunnel startup
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
            ok(f"ngrok active  â†’  {GREEN}{BOLD}{public_url}{RESET}")
        else:
            warn("ngrok failed. Falling back to localtunnel...")

    if not public_url:
        public_url = _start_localtunnel(PORT)
        if public_url:
            tunnel_type = "localtunnel"
            ok(f"localtunnel active  â†’  {GREEN}{BOLD}{public_url}{RESET}")
        
    tunnel_line = ""
    tunnel_hint = ""
    
    if public_url:
        tunnel_line = f"    Public URL   â†’  {GREEN}{BOLD}{public_url}{RESET}  {DIM}({tunnel_type}){RESET}"
        tunnel_hint = f"           Â· public     â†’  {GREEN}{public_url}{RESET}"
    elif NGROK_ENABLED.exists():
        tunnel_line = f"    Public URL   â†’  {YELLOW}(failed to start ngrok and localtunnel){RESET}"
        tunnel_hint = f"           Â· public     â†’  run manually: {DIM}ngrok http {PORT}{RESET}"
    else:
        tunnel_line = f"    Public URL   â†’  {YELLOW}(failed to start localtunnel){RESET}"
        tunnel_hint = f"           Â· public     â†’  configure ngrok via {DIM}python start.py --reset{RESET} or ensure node/npx is installed"

    # â”€â”€ Generate and display QR code â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    qr_url = public_url if public_url else f"http://{local_ip}:{PORT}"
    _display_connect_qr(qr_url, token)

    print(f"""
  {GREEN}{BOLD}Backend is starting up!{RESET}

    Local URL      â†’  {CYAN}http://127.0.0.1:{PORT}{RESET}
    Network URL    â†’  {CYAN}http://{local_ip}:{PORT}{RESET}
{(tunnel_line + chr(10)) if tunnel_line else ''}    API docs       â†’  {CYAN}http://127.0.0.1:{PORT}/docs{RESET}
    Access Token   â†’  {BOLD}{MAGENTA}{token}{RESET}

  {DIM}Keep this terminal open. Press Ctrl+C to stop the server.{RESET}

  {YELLOW}Mobile app setup:{RESET}
    {BOLD}Option A â€” Scan QR code (easiest):{RESET}
      1. Open the app  â†’  Settings  â†’  tap the {BOLD}QR icon{RESET} ðŸ“·
      2. Scan the QR code shown above
      3. Done â€” auto-connected!

    {BOLD}Option B â€” Manual setup:{RESET}
      1. Build / install the SuperBrain APK on your Android device.
      2. Open the app  â†’  tap the âš™ settings icon.
      3. Set {BOLD}Server URL{RESET} to:
           Â· Same WiFi  â†’  http://{local_ip}:{PORT}
{tunnel_hint}
           Â· Port fwd   â†’  http://<your-public-ip>:{PORT}
      4. Set {BOLD}Access Token{RESET} to: {BOLD}{MAGENTA}{token}{RESET}
      5. Tap {BOLD}Save{RESET}  â†’  Connected!

  {YELLOW}Data Management:{RESET}
    â€¢ {BOLD}Export:{RESET}   In app Settings  â†’  Data Import/Export  â†’  choose format (JSON/ZIP)
    â€¢ {BOLD}Import:{RESET}   Upload backup file in app  â†’  Data Import/Export  â†’  select file
    â€¢ {BOLD}Reset:{RESET}    Run  {BOLD}python reset.py{RESET}  for safe data cleanup options

  {DIM}Security Note: Keep token.txt private. Anyone with this token can use your API.{RESET}
  {DIM}The app securely stores your Access Token locally â€” it's never transmitted anywhere but your server.{RESET}
""")

    os.chdir(BASE_DIR)
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), "-m", "uvicorn", "api:app",
                                 "--host", "0.0.0.0", "--port", str(PORT), "--reload"])

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# Main
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def launch_backend_status():
    h1("SuperBrain Status")
    
    token = "UNKNOWN"
    if TOKEN_FILE.exists():
        token = TOKEN_FILE.read_text(encoding="utf-8").strip()

    # Fetch ngrok status via API
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
    print(f"    Local URL      â†’  {CYAN}{local_url}{RESET}")
    print(f"    Network URL    â†’  {CYAN}{network_url}{RESET}")
    print(f"    Public URL   â†’  {CYAN}{url}{RESET}  ({tunnel_type})")
    print(f"    API docs       â†’  {CYAN}{local_url}/docs{RESET}")
    nl()

def main():
    os.chdir(BASE_DIR)
    banner()

    status_mode = "--status" in sys.argv
    if status_mode:
        launch_backend_status()
        return

    ngrok_mode = "--ngrok" in sys.argv
    if ngrok_mode:
        h1("SuperBrain Ngrok Configuration")
        setup_remote_access()
        nl()
        ok("Ngrok configuration finished. Run 'superbrain-server' to start the backend.")
        return

    reset_mode = "--reset" in sys.argv

    if SETUP_DONE.exists() and not reset_mode:
        # Already configured â€” just launch
        print(f"  {GREEN}Setup already complete.{RESET}  Starting backend â€¦")
        print(f"  {DIM}Run  python start.py --reset  to redo the setup wizard.{RESET}")
        launch_backend()
        return

    print(f"""
  Welcome to SuperBrain!  This wizard will guide you through:

    1 Â· Create Python virtual environment
    2 Â· Install all required packages
    3 Â· Configure AI provider keys + Instagram credentials
    4 Â· Set up an offline AI model via Ollama  (qwen3-vl:4b)
    5 Â· Set up offline audio transcription     (Whisper + ffmpeg)
    6 Â· Configure remote access (localtunnel or port forwarding)
    7 Â· Generate Access Token & initialise database

  Press {BOLD}Enter{RESET} to accept defaults shown in [{DIM}brackets{RESET}].
  You can re-run this wizard any time with:  {BOLD}python start.py --reset{RESET}
""")
    input(f"  Press {BOLD}Enter{RESET} to begin â€¦ ")

    try:
        setup_venv()
        install_deps()
        setup_api_keys()
        setup_ollama()
        setup_whisper()
        setup_remote_access()
        setup_token_and_db()
    except KeyboardInterrupt:
        nl()
        warn("Setup interrupted. Re-run  python start.py  to continue.")
        sys.exit(1)

    # Mark setup done
    SETUP_DONE.write_text("ok")

    nl()
    print(f"  {GREEN}{BOLD}{'â•'*60}{RESET}")
    print(f"  {GREEN}{BOLD}  âœ“  Setup complete!{RESET}")
    print(f"  {GREEN}{BOLD}{'â•'*60}{RESET}")
    nl()

    if ask_yn("Start the backend now?", default=True):
        launch_backend()
    else:
        info("Run  python start.py  whenever you want to start the backend.")

if __name__ == "__main__":
    main()

