"""
User-editable configuration: the taxonomy and personal lists that shape how
posts are classified, imported, and shown.

Two JSON files, merged key by key:

- core/default_config.json: committed, generic defaults (kept out of
  config/ so a Docker volume mounted there never shadows a newer default).
- config/user_config.json   : gitignored, this install's overrides. Any
  top-level key present here replaces the default for that key entirely
  (lists are not merged item by item). Path can be overridden with
  SERENDIPID_CONFIG.

Keys:
  categories              [{"name": str, "keywords": [str, ...]}, ...]
                          keywords feed the fallback classifier used only
                          when the model returns no usable CATEGORY field.
  languages               [str, ...]
  trusted_authors         [username, ...]: posts auto-added to the
                          "Trusted Authors" board on save.
  trusted_creators        {username: reason}: importance score floored at 4.
  excluded_import_folders [folder, ...]: never imported or stored.
  sensitive_folders       [folder, ...]: imported, but hidden from clients
                          unless the server runs with --show-sensitive, and
                          never used as a recommendation signal.
  priority_folder         str | null: default folder imported first in
                          by-collection imports.

"other" (categories) and "other" / "no dialogue / visual only" (languages)
are always present, appended if a config leaves them out, since the
classifiers fall back to them.

Values are read once per process and cached; reload() re-reads the files
(called after an import so a running server picks the change up without a
restart).
"""

import copy
import json
import os
import threading
from pathlib import Path

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "default_config.json"
CONFIG_PATH_ENV = "SERENDIPID_CONFIG"

CONFIG_VERSION = 1

REQUIRED_CATEGORIES = ["other"]
REQUIRED_LANGUAGES = ["other", "no dialogue / visual only"]

KEYS = (
    "categories",
    "languages",
    "trusted_authors",
    "trusted_creators",
    "excluded_import_folders",
    "sensitive_folders",
    "priority_folder",
)

_lock = threading.Lock()
_cache = None


class ConfigError(ValueError):
    pass


def user_config_path() -> Path:
    override = os.getenv(CONFIG_PATH_ENV, "").strip()
    return Path(override) if override else CONFIG_DIR / "user_config.json"


def _read_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must contain a JSON object")
    return data


def _clean_str_list(value, key: str) -> list:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ConfigError(f"'{key}' must be a list of strings")
    out, seen = [], set()
    for v in value:
        v = v.strip()
        if v and v.casefold() not in seen:
            seen.add(v.casefold())
            out.append(v)
    return out


def validate(data: dict) -> dict:
    """Validate and normalize a (partial) config dict. Unknown keys are an
    error so a typo doesn't silently do nothing. Returns a cleaned copy
    containing only the keys that were present."""
    if not isinstance(data, dict):
        raise ConfigError("config must be a JSON object")
    unknown = set(data) - set(KEYS) - {"version"}
    if unknown:
        raise ConfigError(f"unknown config key(s): {', '.join(sorted(unknown))}")

    out = {}
    if "categories" in data:
        cats = data["categories"]
        if not isinstance(cats, list):
            raise ConfigError("'categories' must be a list")
        cleaned, seen = [], set()
        for i, c in enumerate(cats):
            if isinstance(c, str):
                c = {"name": c, "keywords": []}
            if not isinstance(c, dict) or not isinstance(c.get("name"), str) or not c["name"].strip():
                raise ConfigError(f"categories[{i}] needs a non-empty 'name'")
            name = c["name"].strip().lower()
            if name in seen:
                continue
            seen.add(name)
            cleaned.append({"name": name, "keywords": _clean_str_list(c.get("keywords", []), f"categories[{i}].keywords")})
        out["categories"] = cleaned
    if "languages" in data:
        out["languages"] = [l.lower() for l in _clean_str_list(data["languages"], "languages")]
    for key in ("trusted_authors", "excluded_import_folders", "sensitive_folders"):
        if key in data:
            out[key] = _clean_str_list(data[key], key)
    if "trusted_creators" in data:
        tc = data["trusted_creators"]
        if not isinstance(tc, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in tc.items()):
            raise ConfigError("'trusted_creators' must be an object of {username: reason}")
        out["trusted_creators"] = {k.strip(): v.strip() for k, v in tc.items() if k.strip()}
    if "priority_folder" in data:
        pf = data["priority_folder"]
        if pf is not None and not isinstance(pf, str):
            raise ConfigError("'priority_folder' must be a string or null")
        out["priority_folder"] = (pf or "").strip() or None
    return out


def _ensure_required(cfg: dict) -> dict:
    names = {c["name"] for c in cfg["categories"]}
    for req in REQUIRED_CATEGORIES:
        if req not in names:
            cfg["categories"].append({"name": req, "keywords": []})
    for req in REQUIRED_LANGUAGES:
        if req not in cfg["languages"]:
            cfg["languages"].append(req)
    return cfg


def _load() -> dict:
    cfg = validate(_read_json(DEFAULT_CONFIG_PATH))
    missing = set(KEYS) - set(cfg)
    if missing:
        raise ConfigError(f"core/default_config.json is missing key(s): {', '.join(sorted(missing))}")
    path = user_config_path()
    if path.exists():
        try:
            cfg.update(validate(_read_json(path)))
        except (ConfigError, json.JSONDecodeError) as e:
            raise ConfigError(f"invalid {path}: {e}") from e
    return _ensure_required(cfg)


def get() -> dict:
    """The effective config (defaults + user overrides). Callers must not
    mutate the returned dict."""
    global _cache
    if _cache is None:
        with _lock:
            if _cache is None:
                _cache = _load()
    return _cache


def reload() -> dict:
    global _cache
    with _lock:
        _cache = _load()
    return _cache


def default_config() -> dict:
    """The shipped defaults only, ignoring any user overrides."""
    return {"version": CONFIG_VERSION, **_ensure_required(validate(_read_json(DEFAULT_CONFIG_PATH)))}


def export_config() -> dict:
    """The full effective config, in the same shape import_config() accepts."""
    return {"version": CONFIG_VERSION, **copy.deepcopy(get())}


def import_config(data: dict, replace: bool = False) -> dict:
    """Validate `data` and write it to user_config.json, then reload.

    replace=False merges the given keys over the existing user config (keys
    not mentioned keep their current user value). replace=True makes `data`
    the whole user config, so any key it omits falls back to the default.
    Raises ConfigError on invalid input without touching the file."""
    cleaned = validate(data)
    path = user_config_path()
    current = {}
    if not replace and path.exists():
        current = validate(_read_json(path))
    current.update(cleaned)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"version": CONFIG_VERSION, **current}, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)
    return reload()


# ── Convenience accessors ────────────────────────────────────────────────────

def category_names() -> list:
    return [c["name"] for c in get()["categories"]]


def category_keywords() -> dict:
    return {c["name"]: c["keywords"] for c in get()["categories"] if c["keywords"]}


def languages() -> list:
    return list(get()["languages"])


def _folded_set(key: str) -> set:
    return {v.strip().casefold() for v in get()[key]}


def trusted_authors() -> set:
    return _folded_set("trusted_authors")


def trusted_creators() -> dict:
    return {k.strip().lower(): v for k, v in get()["trusted_creators"].items()}


def excluded_import_folders() -> set:
    return _folded_set("excluded_import_folders")


def sensitive_folders() -> set:
    return _folded_set("sensitive_folders")


def priority_folder():
    return get()["priority_folder"]
