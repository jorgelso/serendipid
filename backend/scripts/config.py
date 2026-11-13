#!/usr/bin/env python3
"""
Show, export, import, or validate the Serendipid configuration
(categories, languages, trusted authors/creators, excluded and sensitive
folders, priority folder). See core/app_config.py for the file format.

Usage:
    python scripts/config.py show                     # print the effective config
    python scripts/config.py export my-config.json    # write it to a file
    python scripts/config.py import my-config.json    # merge a file into config/user_config.json
    python scripts/config.py import my-config.json --replace   # replace it entirely
    python scripts/config.py validate my-config.json  # check a file without saving

A running server reads the config once at startup; after importing from the
CLI, restart it (or import through POST /config/import instead, which
applies immediately).
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import app_config  # noqa: E402


def _load(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("show")
    ex = sub.add_parser("export")
    ex.add_argument("path")
    im = sub.add_parser("import")
    im.add_argument("path")
    im.add_argument("--replace", action="store_true", help="replace the whole user config instead of merging")
    va = sub.add_parser("validate")
    va.add_argument("path")
    args = p.parse_args()

    try:
        if args.cmd == "show":
            print(json.dumps(app_config.export_config(), indent=2, ensure_ascii=False))
        elif args.cmd == "export":
            Path(args.path).write_text(json.dumps(app_config.export_config(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"Wrote {args.path}")
        elif args.cmd == "import":
            app_config.import_config(_load(args.path), replace=args.replace)
            print(f"Saved to {app_config.user_config_path()}")
        elif args.cmd == "validate":
            app_config.validate(_load(args.path))
            print("OK")
    except (app_config.ConfigError, json.JSONDecodeError, OSError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
