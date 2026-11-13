"""
The API access token: a random 32-character alphanumeric secret stored in
token.txt and sent by every client as the X-API-Key header.

Shared by api.py, start.py and utils/manage_token.py so the format is
defined in one place. A token.txt in any other format (e.g. the old
8-character tokens) is treated as invalid and replaced on the next start.
"""

import secrets
import string
from pathlib import Path

TOKEN_LENGTH = 32
TOKEN_FILE = Path(__file__).resolve().parent.parent / "token.txt"
_ALPHABET = string.ascii_letters + string.digits


def generate_token() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(TOKEN_LENGTH))


def is_valid_token(token: str) -> bool:
    return len(token) == TOKEN_LENGTH and token.isascii() and token.isalnum()


def read_token():
    """The token in token.txt if it exists and is valid, else None."""
    if not TOKEN_FILE.exists():
        return None
    content = TOKEN_FILE.read_text(encoding="utf-8", errors="ignore").strip()
    return content if is_valid_token(content) else None


def write_token(token: str) -> None:
    TOKEN_FILE.write_text(token, encoding="utf-8")
    try:
        TOKEN_FILE.chmod(0o600)
    except OSError:
        pass


def mask(token: str) -> str:
    """For logs: enough to tell tokens apart, not enough to use one."""
    return f"{token[:4]}...{token[-2:]}" if token else ""
