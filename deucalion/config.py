"""User configuration, stored as JSON in ~/.config/deucalion/config.json."""

from __future__ import annotations

import copy
import os
import re
from pathlib import Path

from .util import DeucalionError, read_json, write_json_atomic

# Exclusion pattern rules (relative to the source folder, e.g. your home):
#   - a pattern without "/" matches a file or folder name anywhere ("node_modules")
#   - a pattern with "/" matches a path from the top of the source (".local/share/Trash")
#   - a trailing "/" matches folders only
#   - "*" matches within one name, "**" matches across folders, "?" one character
DEFAULT_HOME_EXCLUDES = [
    ".cache/",
    ".thumbnails/",
    ".local/share/Trash/",
    ".local/share/recently-used.xbel",
    ".local/share/containers/",
    ".var/app/*/cache/",
    ".npm/_cacache/",
    ".config/**/Cache/",
    ".config/**/Code Cache/",
    ".config/**/GPUCache/",
    ".config/**/DawnCache/",
    ".config/**/DawnGraphiteCache/",
    ".config/**/DawnWebGPUCache/",
    ".config/**/GrShaderCache/",
    ".config/**/ShaderCache/",
    ".config/**/CacheStorage/",
    ".config/**/CachedData/",
    ".config/**/CachedExtensionVSIXs/",
    "Deucalion-before-restore/",
]

# Off by default; shown in the GUI as one-click additions.
OPTIONAL_EXCLUDES = ["node_modules/", "__pycache__/", ".venv/", "venv/", ".tox/", "target/debug/"]

DEFAULTS = {
    "version": 1,
    "targets": {},            # id -> {"name", "path", "registered", "allow_internal"}
    "default_target": None,
    "home_path": None,        # None = your home folder
    "home_excludes": DEFAULT_HOME_EXCLUDES,
    "extra_folders": [],      # [{"name": "srv", "path": "/srv", "excludes": []}]
    "profiles": {},           # name -> [paths]
    "keep_overwritten": True, # keep old versions of changed files in _removed/
}


def config_dir() -> Path:
    env = os.environ.get("DEUCALION_CONFIG_DIR")
    if env:
        return Path(env)
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "deucalion"


def state_dir() -> Path:
    env = os.environ.get("DEUCALION_STATE_DIR")
    if env:
        return Path(env)
    return Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state") / "deucalion"


class Config(dict):
    path: Path

    @classmethod
    def load(cls, path: Path | None = None) -> "Config":
        path = path or config_dir() / "config.json"
        cfg = cls(copy.deepcopy(DEFAULTS))
        data = read_json(path, {})
        if not isinstance(data, dict):
            raise DeucalionError(f"Configuration file is damaged: {path}")
        cfg.update(data)
        cfg.path = path
        return cfg

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(self.path, dict(self))

    @property
    def home(self) -> Path:
        return Path(self.get("home_path") or Path.home())


def _glob_to_regex(pattern: str) -> str:
    out, i = [], 0
    while i < len(pattern):
        c = pattern[i]
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
            continue
        if pattern.startswith("**", i):
            out.append(".*")
            i += 2
            continue
        if c == "*":
            out.append("[^/]*")
        elif c == "?":
            out.append("[^/]")
        else:
            out.append(re.escape(c))
        i += 1
    return "".join(out)


class Excluder:
    """Decides whether a path inside a source folder is excluded."""

    def __init__(self, patterns: list[str]):
        name_any, name_dir, path_any, path_dir = [], [], [], []
        for p in patterns:
            p = p.strip()
            if not p or p.startswith("#"):
                continue
            dir_only = p.endswith("/")
            p = p.rstrip("/").lstrip("/")
            rx = _glob_to_regex(p)
            if "/" in p:
                (path_dir if dir_only else path_any).append(rx)
            else:
                (name_dir if dir_only else name_any).append(rx)
        self._name_any = self._compile(name_any)
        self._name_dir = self._compile(name_dir)
        self._path_any = self._compile(path_any)
        self._path_dir = self._compile(path_dir)

    @staticmethod
    def _compile(parts: list[str]):
        return re.compile("(?:" + "|".join(parts) + r")\Z", re.S) if parts else None

    def excluded(self, rel: str, name: str, is_dir: bool) -> bool:
        if self._name_any and self._name_any.match(name):
            return True
        if self._path_any and self._path_any.match(rel):
            return True
        if is_dir:
            if self._name_dir and self._name_dir.match(name):
                return True
            if self._path_dir and self._path_dir.match(rel):
                return True
        return False
