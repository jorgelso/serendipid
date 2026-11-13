"""
View or regenerate the Serendipid API access token (token.txt).

    python utils/manage_token.py          # interactive menu
    python utils/manage_token.py show     # print the current token
    python utils/manage_token.py rotate   # generate a new one

Restart the server after rotating, and update every client (web app
SERENDIPID_API_KEY, mobile app settings, browser extension).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.access_token import TOKEN_FILE, TOKEN_LENGTH, generate_token, read_token, write_token  # noqa: E402


def show() -> int:
    token = read_token()
    if not token:
        print(f"No valid token in {TOKEN_FILE}. Start the server or run 'rotate' to create one.")
        return 1
    print(token)
    return 0


def rotate() -> int:
    token = generate_token()
    write_token(token)
    print(f"New {TOKEN_LENGTH}-character token saved to {TOKEN_FILE}:")
    print(token)
    print("Restart the server and update every client with this token.")
    return 0


def main() -> int:
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "show":
            return show()
        if cmd == "rotate":
            return rotate()
        print(__doc__)
        return 1

    token = read_token()
    print(f"Current token: {token}" if token else "No valid token found.")
    print("\n  1. Generate a new token\n  2. Exit")
    choice = input("\nChoice (1-2): ").strip()
    if choice == "1":
        return rotate()
    return 0


if __name__ == "__main__":
    sys.exit(main())
