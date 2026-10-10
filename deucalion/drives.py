"""Detect drives connected to the machine."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .target import BACKUP_DIRNAME, _drive_info
from .util import backing_disks, run


@dataclass
class Volume:
    path: str
    fstype: str
    label: str
    size: int
    mountpoints: list[str]
    encrypted: bool = False       # a LUKS/VeraCrypt container (locked or unlocked)
    has_backup: bool = False


@dataclass
class Drive:
    path: str
    model: str
    size: int
    transport: str
    external: bool
    system: bool
    volumes: list[Volume] = field(default_factory=list)


def _volumes(node: dict, out: list[Volume], parent_encrypted: bool = False) -> None:
    fstype = node.get("fstype") or ""
    encrypted = parent_encrypted or fstype in ("crypto_LUKS", "BitLocker") or node.get("type") == "crypt"
    mps = [m for m in (node.get("mountpoints") or []) if m]
    if node.get("type") in ("part", "crypt", "disk", "lvm") and (fstype or mps):
        has_backup = any(_drive_info(Path(m) / BACKUP_DIRNAME) or _drive_info(Path(m)) for m in mps)
        out.append(Volume(node.get("path", ""), fstype, node.get("label") or "", int(node.get("size") or 0),
                          mps, encrypted, has_backup))
    for child in node.get("children", []) or []:
        _volumes(child, out, encrypted)


def list_drives(include_loops: bool = False) -> list[Drive]:
    res = run(["lsblk", "-J", "-b", "-o",
               "NAME,PATH,SIZE,TYPE,TRAN,RM,HOTPLUG,FSTYPE,LABEL,MOUNTPOINTS,MODEL"])
    if res.returncode != 0:
        return []
    system = backing_disks("/") | backing_disks(Path.home())
    drives = []
    for d in json.loads(res.stdout).get("blockdevices", []):
        if d.get("type") != "disk" and not (include_loops and d.get("type") == "loop"):
            continue
        vols: list[Volume] = []
        _volumes(d, vols)
        drives.append(Drive(
            path=d.get("path", ""),
            model=(d.get("model") or "").strip(),
            size=int(d.get("size") or 0),
            transport=d.get("tran") or "",
            external=bool(d.get("hotplug") or d.get("rm") or d.get("tran") == "usb"),
            system=d.get("path") in system,
            volumes=vols,
        ))
    return drives
