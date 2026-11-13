"""
Instagram-folder policies that change what Serendipid imports and shows.

Two user-configured lists (excluded_import_folders / sensitive_folders in
config/user_config.json, see core/app_config.py), both matched on the folder/collection *name*
case-insensitively with surrounding whitespace ignored (Instagram's export
keeps trailing spaces):

- excluded_import_folders — folders that are never imported or stored. A post
  saved only in one of these is skipped by the import scripts entirely; a
  post also saved in some other folder is imported, but never assigned to the
  excluded folder, and no collection row is ever created for it (the backend
  refuses to, see POST /collections).

- sensitive_folders — folders that ARE imported and stored normally,
  but whose posts are hidden from every client-facing read path unless the
  backend was started with --show-sensitive (or SERENDIPID_SHOW_SENSITIVE=1).
  Independently of that flag, their posts are never used as a
  recommendation/suggestion signal or candidate: views aren't logged, they're
  left out of view/study-guide history and chat retrieval, and every post
  payload carries `is_sensitive` so clients can drop them from their own
  client-side recommenders and "Related" rails.
"""

import os

from core import app_config

SHOW_SENSITIVE_ENV = "SERENDIPID_SHOW_SENSITIVE"


def _norm(name) -> str:
    return (name or "").strip().casefold()


def sensitive_collection_names() -> set:
    return app_config.sensitive_folders()


def is_excluded_folder(name) -> bool:
    return _norm(name) in app_config.excluded_import_folders()


def is_sensitive_collection_name(name) -> bool:
    return _norm(name) in app_config.sensitive_folders()


def show_sensitive() -> bool:
    """True when the backend was started with --show-sensitive. Read from the
    environment on every call so start.py / api.py only need to export it
    before uvicorn imports the app (including uvicorn --reload's child)."""
    return os.getenv(SHOW_SENSITIVE_ENV, "").strip().lower() in ("1", "true", "yes", "on")


def enable_from_argv(argv) -> bool:
    """Consume a --show-sensitive flag from argv (in place) and export it to
    the environment. Returns whether the flag was present."""
    if "--show-sensitive" in argv:
        argv.remove("--show-sensitive")
        os.environ[SHOW_SENSITIVE_ENV] = "1"
        return True
    return False
