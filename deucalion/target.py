"""A backup target: the Deucalion-Backup folder on an external drive."""

from __future__ import annotations

import fcntl
import itertools
import os
import re
import shutil
import uuid
from contextlib import contextmanager
from pathlib import Path

from . import __version__
from .config import Config
from .manifest import Manifest
from .names import NamePolicy
from .util import (DeucalionError, dir_size, is_on_system_disk, is_posix_fs, now_iso,
                   read_json, write_json_atomic)

BACKUP_DIRNAME = "Deucalion-Backup"
META_DIRNAME = ".deucalion"
REMOVED_DIRNAME = "_removed"


_SYSTEM_MOUNTS = ("/proc", "/sys", "/dev", "/run", "/snap", "/boot", "/var/lib/docker", "/var/snap")


def _drive_info(root: Path) -> dict | None:
    try:
        info = read_json(root / META_DIRNAME / "drive-id")
    except (OSError, ValueError):
        return None
    return info if isinstance(info, dict) and "id" in info else None


class Target:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.meta_dir = self.root / META_DIRNAME
        info = read_json(self.meta_dir / "drive-id")
        if not info:
            raise DeucalionError(f"{self.root} is not a Deucalion backup folder.")
        self.info = info
        self.id: str = info["id"]
        self.name: str = info.get("name", self.id[:8])
        self.policy = NamePolicy(info.get("name_policy", "exfat"))
        self._lock_fd = None

    # -- creation / discovery ---------------------------------------------------------
    @classmethod
    def create(cls, path: Path, name: str | None = None, allow_internal: bool = False,
               name_policy: str | None = None) -> "Target":
        """Turn `path` (a mounted drive or a folder on it) into a backup target."""
        path = Path(path).resolve()
        if not path.is_dir():
            raise DeucalionError(f"{path} is not a folder.")
        root = path if (path / META_DIRNAME / "drive-id").exists() else path / BACKUP_DIRNAME
        if (root / META_DIRNAME / "drive-id").exists():
            return cls(root)  # already a target: reuse it
        if not allow_internal and is_on_system_disk(path):
            raise DeucalionError(
                f"{path} is on the same disk as your system. A backup there would be lost "
                "together with the system. Choose an external drive.")
        if name_policy is None:
            name_policy = "posix" if is_posix_fs(path) else "exfat"
        (root / META_DIRNAME).mkdir(parents=True, exist_ok=True)
        info = {
            "id": str(uuid.uuid4()),
            "name": name or path.name,
            "created": now_iso(),
            "created_by": f"Deucalion {__version__}",
            "name_policy": name_policy,
        }
        write_json_atomic(root / META_DIRNAME / "drive-id", info)
        return cls(root)

    @staticmethod
    def candidate_roots():
        """Backup folders on currently mounted filesystems (system mounts are skipped)."""
        try:
            with open("/proc/self/mountinfo") as f:
                mounts = [re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), line.split()[4])
                          for line in f]
        except OSError:
            return
        for m in mounts:
            if m.startswith(_SYSTEM_MOUNTS) and not m.startswith("/run/media/"):
                continue
            for cand in (Path(m) / BACKUP_DIRNAME, Path(m)):
                if _drive_info(cand):
                    yield cand

    @classmethod
    def find(cls, cfg: Config, wanted: str | None = None) -> "Target":
        """Locate a registered target by name or id (or the default one)."""
        targets = cfg.get("targets", {})
        if not targets:
            raise DeucalionError("No backup drive registered yet. Run: deucalion register <drive folder>")
        if wanted:
            matches = [tid for tid, t in targets.items() if wanted in (tid, t.get("name"))]
            if not matches:
                raise DeucalionError(f"No registered backup drive called '{wanted}'.")
            tid = matches[0]
        elif cfg.get("default_target") in targets:
            tid = cfg["default_target"]
        elif len(targets) == 1:
            tid = next(iter(targets))
        else:
            raise DeucalionError("Several backup drives are registered; choose one with --target NAME.")
        t = targets[tid]
        for root in itertools.chain([Path(t["path"])], cls.candidate_roots()):
            info = _drive_info(root)
            if info and info.get("id") == tid:
                if str(root) != t["path"]:
                    t["path"] = str(root)  # drive was mounted somewhere else this time
                    cfg.save()
                return cls(root)
        raise DeucalionError(
            f"Backup drive '{t.get('name')}' is not connected (or not unlocked). "
            "Plug it in and try again.")

    def register(self, cfg: Config, allow_internal: bool = False, make_default: bool = False) -> None:
        cfg.setdefault("targets", {})[self.id] = {
            "name": self.name, "path": str(self.root), "registered": now_iso(),
            "allow_internal": allow_internal,
        }
        if make_default or not cfg.get("default_target"):
            cfg["default_target"] = self.id
        cfg.save()

    # -- layout -----------------------------------------------------------------------------
    @property
    def removed_root(self) -> Path:
        return self.root / REMOVED_DIRNAME

    @property
    def staging_dir(self) -> Path:
        return self.meta_dir / "staging"

    @property
    def logs_dir(self) -> Path:
        return self.meta_dir / "logs"

    def manifest(self) -> Manifest:
        return Manifest(self.meta_dir / "manifest.sqlite")

    def check_filesystem(self) -> None:
        if self.policy.kind == "posix" and not is_posix_fs(self.root):
            raise DeucalionError(
                "This backup was created on a Linux filesystem but the drive is now a different "
                "filesystem (e.g. exFAT). Register a new backup folder instead.")

    # -- backup.json --------------------------------------------------------------------------
    def read_summary(self) -> dict:
        return read_json(self.root / "backup.json", {}) or {}

    def write_summary(self, data: dict) -> None:
        write_json_atomic(self.root / "backup.json", data)

    # -- space ------------------------------------------------------------------------------
    def free_bytes(self) -> int:
        return shutil.disk_usage(self.root).free

    def removed_batches(self) -> list[tuple[str, int, int]]:
        """[(folder name, bytes, files)] for each run folder in _removed/, oldest first."""
        out = []
        if self.removed_root.is_dir():
            for d in sorted(self.removed_root.iterdir()):
                if d.is_dir():
                    size, files = dir_size(d)
                    out.append((d.name, size, files))
        return out

    def empty_removed(self, names: list[str] | None = None) -> int:
        """Permanently delete run folders from _removed/ (all if names is None). Returns bytes freed."""
        freed = 0
        for name, size, _ in self.removed_batches():
            if names is None or name in names:
                shutil.rmtree(self.removed_root / name)
                freed += size
        try:
            self.removed_root.rmdir()
        except OSError:
            pass
        return freed

    # -- locking ------------------------------------------------------------------------------
    @contextmanager
    def lock(self):
        """Prevent two Deucalion runs from using the same drive at once."""
        self.meta_dir.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.meta_dir / "lock", os.O_RDWR | os.O_CREAT, 0o644)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise DeucalionError("Another Deucalion task is already using this drive.") from None
            yield self
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
