"""
Instagram-folder policies that change what SuperBrain imports and shows.

Two explicit, code-level lists, both matched on the folder/collection *name*
case-insensitively with surrounding whitespace ignored (Instagram's export
keeps trailing spaces, e.g. "Italia "):

- EXCLUDED_IMPORT_FOLDERS — folders that are never imported or stored. A post
  saved only in one of these is skipped by the import scripts entirely; a
  post also saved in some other folder is imported, but never assigned to the
  excluded folder, and no collection row is ever created for it (the backend
  refuses to, see POST /collections).

- SENSITIVE_COLLECTION_NAMES — folders that ARE imported and stored normally,
  but whose posts are hidden from every client-facing read path unless the
  backend was started with --show-sensitive (or SUPERBRAIN_SHOW_SENSITIVE=1).
  Independently of that flag, their posts are never used as a
  recommendation/suggestion signal or candidate: views aren't logged, they're
  left out of view/study-guide history and chat retrieval, and every post
  payload carries `is_sensitive` so clients can drop them from their own
  client-side recommenders and "Related" rails.
"""

import os

EXCLUDED_IMPORT_FOLDERS = {"enviar a amigos"}
SENSITIVE_COLLECTION_NAMES = {"depression"}

SHOW_SENSITIVE_ENV = "SUPERBRAIN_SHOW_SENSITIVE"


def _norm(name) -> str:
    return (name or "").strip().casefold()


def is_excluded_folder(name) -> bool:
    return _norm(name) in EXCLUDED_IMPORT_FOLDERS


def is_sensitive_collection_name(name) -> bool:
    return _norm(name) in SENSITIVE_COLLECTION_NAMES


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
