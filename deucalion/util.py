"""Small helpers shared by the engine, the CLI and (later) the GUI."""

from __future__ import annotations

import datetime as _dt
import json
import os
import subprocess
from pathlib import Path

# Filesystems that keep Linux permissions, owners and symlinks natively.
POSIX_FILESYSTEMS = {"ext2", "ext3", "ext4", "btrfs", "xfs", "f2fs", "zfs", "jfs", "tmpfs", "reiserfs"}


class DeucalionError(Exception):
    """An error with a message that is safe to show to the user as-is."""


DRIVE_FULL = ("The backup drive is full. Free some space (for example empty _removed/ with: "
              "deucalion removed empty, or leave out large folders) and run again.")


def human_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def plural(n: int, word: str, words: str | None = None) -> str:
    """plural(1, 'file') -> '1 file', plural(3, 'file') -> '3 files' (with thousands separators)."""
    return f"{n:,} {word if n == 1 else (words or word + 's')}"


def human_duration(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {seconds:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


def run_stamp() -> str:
    """Timestamp used for folder names (sortable, valid on every filesystem)."""
    return _dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")


def now_iso() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def run(cmd: list[str], check: bool = False, timeout: float | None = 60) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=check, timeout=timeout)


def write_json_atomic(path: Path, data) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=True)  # also safe for names that aren't valid UTF-8
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def read_json(path: Path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def mount_info(path: str | os.PathLike) -> dict:
    """Return {'target', 'source', 'fstype', 'options'} for the mount containing path."""
    res = run(["findmnt", "-J", "-n", "-o", "TARGET,SOURCE,FSTYPE,OPTIONS", "--target", str(path)])
    if res.returncode != 0:
        return {}
    fs = json.loads(res.stdout).get("filesystems", [])
    return fs[0] if fs else {}


# Where desktops mount removable drives.
REMOVABLE_MOUNTS = ("/media/", "/run/media/", "/mnt/")


def mount_points(source: str | None = None) -> list[str]:
    """Mount points of every filesystem, or of one device. Uses findmnt's JSON output: its other
    formats write spaces in paths as '\\x20' (a drive named 'Alex Backup')."""
    res = run(["findmnt", "-J", "-l", "-o", "TARGET"] + (["--source", source] if source else []))
    if res.returncode != 0 or not res.stdout.strip():
        return []
    return [fs["target"] for fs in json.loads(res.stdout).get("filesystems", [])]


def fs_type(path: str | os.PathLike) -> str:
    return mount_info(path).get("fstype", "unknown")


def is_posix_fs(path: str | os.PathLike) -> bool:
    return fs_type(path) in POSIX_FILESYSTEMS


def _device_of(path: str | os.PathLike) -> str | None:
    src = mount_info(path).get("source") or ""
    src = src.split("[", 1)[0]  # btrfs subvolume notation: /dev/sda1[/@home]
    return src if src.startswith("/dev/") else None


def _lsblk_inverse(dev: str) -> list[dict]:
    res = run(["lsblk", "-s", "-J", "-o", "NAME,PATH,TYPE", dev])
    if res.returncode != 0:
        return []
    return json.loads(res.stdout).get("blockdevices", [])


def _walk_tree(nodes: list[dict]):
    for n in nodes:
        yield n
        yield from _walk_tree(n.get("children", []))


def backing_disks(path: str | os.PathLike, _depth: int = 0) -> set[str]:
    """Physical disks that hold `path`. Loop devices are followed to their backing file."""
    dev = _device_of(path)
    if not dev or _depth > 4:
        return set()
    disks: set[str] = set()
    for node in _walk_tree(_lsblk_inverse(dev)):
        if node.get("type") == "disk":
            disks.add(node["path"])
        elif node.get("type") == "loop":
            backing = Path("/sys/block") / node["name"] / "loop" / "backing_file"
            try:
                disks |= backing_disks(backing.read_text().strip(), _depth + 1)
            except OSError:
                pass
    return disks


def is_on_system_disk(path: str | os.PathLike) -> bool:
    """True if `path` lives on the same physical disk as the running system or home."""
    target = backing_disks(path)
    if not target:
        # Could not resolve (e.g. tmpfs): fall back to comparing filesystems.
        st = os.stat(path).st_dev
        return st in (os.stat("/").st_dev, os.stat(Path.home()).st_dev)
    return bool(target & (backing_disks("/") | backing_disks(Path.home())))


def is_encrypted(path: str | os.PathLike) -> bool:
    """True if the filesystem holding `path` sits on an encrypted (dm-crypt) device."""
    dev = _device_of(path)
    if not dev:
        return False
    return any(n.get("type") == "crypt" for n in _walk_tree(_lsblk_inverse(dev)))


def os_release() -> dict:
    info = {}
    try:
        for line in Path("/etc/os-release").read_text().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                info[k] = v.strip().strip('"')
    except OSError:
        pass
    return info


def dir_size(path: Path) -> tuple[int, int]:
    """(bytes, files) of everything below path, without following symlinks."""
    total = files = 0
    for root, dirs, names in os.walk(path):
        for n in names:
            try:
                total += os.lstat(os.path.join(root, n)).st_size
                files += 1
            except OSError:
                pass
    return total, files
