"""Prepare a backup drive (format, encrypt) and open or close an encrypted backup.

Layouts
  encrypt-all     the whole drive is one encrypted volume
  encrypt-part    a normal exFAT part (readable everywhere) + an encrypted part for the backup
  encrypt-folder  an encrypted container file on a drive that keeps its current files
  plain           the whole drive formatted as exFAT, no encryption
  as-is           use a drive's existing filesystem (e.g. NTFS or exFAT), no encryption

Encryption methods
  veracrypt       readable on Linux, macOS and Windows (with VeraCrypt installed); creating
                  and unlocking it needs the administrator password on Linux
  luks            Linux only, built into Ubuntu; no administrator password needed
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import __version__
from .config import Config, state_dir
from .target import BACKUP_DIRNAME, Target, _drive_info
from .udisks import GPT_DATA, GPT_LINUX, UDisks
from .util import DeucalionError, backing_disks, mount_info, read_json, run, write_json_atomic

LAYOUTS = {
    "encrypt-all": "Encrypt the whole drive",
    "encrypt-part": "Encrypted part for the backup + a normal part for other files",
    "encrypt-folder": "Encrypted folder on this drive (keeps what is already on it)",
    "plain": "No encryption: erase and format the whole drive as exFAT",
    "as-is": "No encryption: use the drive as it is (keeps what is already on it)",
}
ERASING = {"encrypt-all", "encrypt-part", "plain"}
CONTAINER = {"veracrypt": "Deucalion-Backup.hc", "luks": "Deucalion-Backup.luks"}
TOOL_DIRNAME = "Deucalion-Tool"
README_NAME = "READ-ME-FIRST.txt"
VERACRYPT_URL = "https://www.veracrypt.fr/en/Downloads.html"

Out = Callable[[str], None]


@dataclass
class SetupRequest:
    layout: str
    device: str = ""          # whole drive (erasing layouts)
    folder: str = ""          # a mounted drive (encrypt-folder, as-is)
    method: str = ""          # veracrypt | luks (encrypted layouts)
    name: str = "Deucalion"
    size: int = 0             # bytes for the encrypted part / folder
    passphrase: str = ""
    allow_internal: bool = False  # tests only: allow disk images on the internal disk

    @property
    def encrypted(self) -> bool:
        return self.layout.startswith("encrypt")


def label_for(name: str) -> str:
    """exFAT allows 11 characters in a drive label."""
    clean = re.sub(r"[^A-Za-z0-9 _.-]", "", name).strip() or "Deucalion"
    return clean[:11].strip()


def veracrypt_binary() -> str | None:
    return shutil.which("veracrypt") or ("/usr/bin/veracrypt" if os.access("/usr/bin/veracrypt", os.X_OK) else None)


def missing_requirements(req: SetupRequest, u: UDisks | None = None) -> list[tuple[str, str]]:
    """[(code, message)] of what is missing. code 'exfatprogs' can be installed for the user."""
    out = []
    needs_exfat = req.layout in ("plain", "encrypt-part") or (req.encrypted and req.method == "veracrypt")
    if needs_exfat and not shutil.which("mkfs.exfat"):
        out.append(("exfatprogs", "The 'exfatprogs' package is needed to create exFAT filesystems."))
    if req.encrypted and req.method == "veracrypt" and not veracrypt_binary():
        out.append(("veracrypt", f"VeraCrypt is needed to create a VeraCrypt volume. Install it from "
                                 f"{VERACRYPT_URL} (Ubuntu .deb), then run this again."))
    if req.encrypted and req.method not in ("veracrypt", "luks"):
        out.append(("method", "Choose veracrypt or luks."))
    if req.encrypted and len(req.passphrase) < 8:
        out.append(("password", "The password must have at least 8 characters."))
    if req.layout == "encrypt-folder" and req.folder:
        fs = mount_info(req.folder).get("fstype", "")
        if fs == "vfat" and req.size >= 4 * 1024 ** 3:
            out.append(("size", "This drive is FAT32, which cannot hold files of 4 GB or more."))
        free = shutil.disk_usage(req.folder).free
        if req.size > free:
            out.append(("size", f"Only {free // 1024 ** 3} GB are free on this drive."))
    return out


class DriveSetup:
    def __init__(self, cfg: Config, out: Out = print, privileged_factory=None):
        self.cfg = cfg
        self.out = out
        self.u = UDisks()
        self._priv_factory = privileged_factory
        self._priv = None

    def priv(self):
        if self._priv is None:
            if self._priv_factory is None:
                from .privileged import Privileged
                self._priv_factory = Privileged
            self._priv = self._priv_factory()
        return self._priv

    def close(self) -> None:
        if self._priv is not None:
            self._priv.close()

    # -- safety -------------------------------------------------------------------------------------
    def check_disk(self, device: str, allow_internal: bool = False) -> None:
        res = run(["lsblk", "-dno", "TYPE", device])
        if res.returncode != 0 or res.stdout.strip() not in ("disk", "loop"):
            raise DeucalionError(f"{device} is not a whole drive.")
        system = _system_disks()
        if device in system:
            raise DeucalionError(f"{device} holds your system. Deucalion never changes it.")
        if not allow_internal:
            if res.stdout.strip() == "loop":
                raise DeucalionError(f"{device} is a disk image, not a drive.")

    def release(self, device: str) -> None:
        """Unmount everything on the drive and lock its encrypted parts."""
        tree = json.loads(run(["lsblk", "-J", "-o", "NAME,PATH,TYPE,MOUNTPOINTS", device]).stdout or "{}")
        nodes, stack = [], list(tree.get("blockdevices", []))
        while stack:
            n = stack.pop()
            nodes.append(n)
            stack.extend(n.get("children") or [])
        for n in nodes:
            if [m for m in (n.get("mountpoints") or []) if m]:
                self.out(f"Unmounting {n['path']}")
                self.u.unmount(self.u.resolve(n["path"]))
        for n in nodes:
            for child in n.get("children") or []:
                if child.get("type") == "crypt":
                    self.u.lock(self.u.resolve(n["path"]))

    # -- set up ---------------------------------------------------------------------------------------
    def run(self, req: SetupRequest) -> Target:
        problems = missing_requirements(req, self.u)
        if problems:
            raise DeucalionError("\n".join(m for _, m in problems))
        label = label_for(req.name)
        if req.layout in ERASING:
            self.check_disk(req.device, req.allow_internal)
            self.release(req.device)
            disk = self.u.resolve(req.device)
            self.out(f"Erasing {req.device} and creating a new partition table")
            self.u.format(disk, "gpt")
        if req.layout == "plain":
            part = self.u.create_partition(disk, 0, GPT_DATA, label, fstype="exfat", label=label)
            mp = self.u.mount(part)
            return self._finish(req, mp, {"method": "none"}, plain_root=mp)
        if req.layout == "as-is":
            folder = Path(req.folder)
            if not folder.is_dir():
                raise DeucalionError(f"{folder} is not a mounted drive.")
            return self._finish(req, str(folder), {"method": "none"}, plain_root=str(folder))
        if req.layout == "encrypt-all":
            part = self.u.create_partition(disk, 0, GPT_LINUX, label)
            mp, access = self._encrypt_partition(req, part, label)
            return self._finish(req, mp, access, plain_root=None)
        if req.layout == "encrypt-part":
            size = int(self.u.props(disk, "Block")["Size"])
            if not 64 * 1024 ** 2 <= req.size <= size - 128 * 1024 ** 2:
                raise DeucalionError("Choose a size for the encrypted part that leaves room for the normal part.")
            plain = self.u.create_partition(disk, size - req.size - 4 * 1024 ** 2, GPT_DATA, label,
                                            fstype="exfat", label=label)
            info = self.u.partition_info(plain)
            secret = self.u.create_partition(disk, 0, GPT_LINUX, f"{label} backup",
                                             offset=int(info["Offset"]) + int(info["Size"]))
            mp, access = self._encrypt_partition(req, secret, label)
            plain_mp = self.u.mount(plain)
            access["plain_uuid"] = self.u.props(plain, "Block").get("IdUUID", "")
            return self._finish(req, mp, access, plain_root=plain_mp)
        if req.layout == "encrypt-folder":
            return self._encrypt_folder(req, label)
        raise DeucalionError(f"Unknown layout {req.layout}.")

    def _encrypt_partition(self, req: SetupRequest, part: str, label: str) -> tuple[str, dict]:
        dev = self.u.device(part)
        partuuid = self.u.partition_info(part).get("UUID", "")
        access = {"method": req.method, "kind": "partition", "partuuid": partuuid, "mount_name": label}
        if req.method == "luks":
            self.out("Encrypting (LUKS)…")
            self.u.format(part, "ext4", label=label, encrypt_passphrase=req.passphrase, encrypt_type="luks2",
                          take_ownership=True)
            clear = self.u.wait_for(lambda: self.u.cleartext(part)) or self.u.unlock(part, req.passphrase)
            return self.u.mount(clear), access
        self.out("Creating the VeraCrypt volume (you will be asked for your administrator password)…")
        self.priv().call("veracrypt_create", on_progress=self.out, source=dev, passphrase=req.passphrase,
                         label=label, uid=os.getuid(), gid=os.getgid(), veracrypt=veracrypt_binary() or "")
        return self._veracrypt_open(access, dev, req.passphrase), access

    def _encrypt_folder(self, req: SetupRequest, label: str) -> Target:
        folder = Path(req.folder)
        if not folder.is_dir():
            raise DeucalionError(f"{folder} is not a mounted drive.")
        if not req.allow_internal and backing_disks(folder) & _system_disks():
            raise DeucalionError(f"{folder} is on your system disk. Choose an external drive.")
        path = folder / CONTAINER[req.method]
        if path.exists():
            raise DeucalionError(f"{path} already exists.")
        src = mount_info(folder).get("source", "")
        plain_uuid = self.u.props(self.u.resolve(src), "Block").get("IdUUID", "") if src.startswith("/dev/") else ""
        access = {"method": req.method, "kind": "file", "file": path.name, "plain_uuid": plain_uuid,
                  "plain_path": str(folder), "mount_name": label}
        if req.method == "luks":
            self.out(f"Creating {path.name} ({req.size // 1024 ** 2:,} MB)…")
            with open(path, "xb") as f:  # never over an existing file
                f.truncate(req.size)
            loop = self.u.loop_setup(str(path))
            self.out("Encrypting (LUKS)…")
            self.u.format(loop, "ext4", label=label, encrypt_passphrase=req.passphrase, encrypt_type="luks2",
                          take_ownership=True)
            clear = self.u.wait_for(lambda: self.u.cleartext(loop)) or self.u.unlock(loop, req.passphrase)
            mp = self.u.mount(clear)
        else:
            self.out("Creating the VeraCrypt folder (you will be asked for your administrator password)…")
            self.priv().call("veracrypt_create", on_progress=self.out, source=str(path), passphrase=req.passphrase,
                             label=label, uid=os.getuid(), gid=os.getgid(), size_bytes=req.size,
                             veracrypt=veracrypt_binary() or "")
            mp = self._veracrypt_open(access, str(path), req.passphrase)
        return self._finish(req, mp, access, plain_root=str(folder))

    def _veracrypt_open(self, access: dict, source: str, passphrase: str) -> str:
        name = f"deucalion-{hashlib.sha1(source.encode()).hexdigest()[:12]}"
        r = self.priv().call("veracrypt_open", on_progress=self.out, source=source, passphrase=passphrase,
                             name=name, mount_name=access["mount_name"], user=_username())
        _remember_open(source, {"mountpoint": r["mountpoint"], "name": name, "loop": r.get("loop")})
        return r["mountpoint"]

    def _finish(self, req: SetupRequest, mountpoint: str, access: dict, plain_root: str | None) -> Target:
        target = Target.create(Path(mountpoint), name=req.name, allow_internal=req.allow_internal)
        target.register(self.cfg, allow_internal=req.allow_internal, make_default=True)
        self.cfg["targets"][target.id]["access"] = access
        self.cfg.save()
        if plain_root:
            install_tool_copy(Path(plain_root), target, access)
        self.out(f"Backup drive '{target.name}' is ready: {target.root}")
        return target

    # -- open / close ---------------------------------------------------------------------------------
    def locate(self, access: dict) -> str:
        """The device (partition) or container file that holds an encrypted backup."""
        if access.get("source"):
            return access["source"]
        if access.get("kind") == "partition":
            dev = Path("/dev/disk/by-partuuid") / access.get("partuuid", "")
            if not dev.exists():
                raise DeucalionError("The backup drive is not connected.")
            return str(dev.resolve())
        plain = None
        if access.get("plain_uuid"):
            dev = Path("/dev/disk/by-uuid") / access["plain_uuid"]
            if dev.exists():
                plain = self.u.mount(self.u.resolve(str(dev.resolve())))
        if plain is None and access.get("plain_path") and (Path(access["plain_path"]) / access["file"]).exists():
            plain = access["plain_path"]
        if plain is None:
            raise DeucalionError("The backup drive is not connected.")
        return str(Path(plain) / access["file"])

    def open(self, access: dict, passphrase: str) -> str:
        """Unlock and mount; returns the mount point."""
        source = self.locate(access)
        if access["method"] == "veracrypt":
            prev = _open_state().get(source)
            if prev and os.path.ismount(prev["mountpoint"]):
                return prev["mountpoint"]
            self.out("Unlocking (you will be asked for your administrator password)…")
            return self._veracrypt_open(access, source, passphrase)
        crypt = self.u.loop_for_file(source) if access["kind"] == "file" else self.u.resolve(source)
        if crypt is None:
            crypt = self.u.loop_setup(source)
        clear = self.u.unlock(crypt, passphrase)
        return self.u.mount(clear)

    def close_access(self, access: dict) -> None:
        source = self.locate(access)
        if access["method"] == "veracrypt":
            st = _open_state().pop(source, None)
            if st:
                self.priv().call("veracrypt_close", mountpoint=st["mountpoint"], name=st["name"], loop=st.get("loop"))
                _save_open_state_without(source)
            return
        crypt = self.u.loop_for_file(source) if access["kind"] == "file" else self.u.resolve(source)
        if crypt is None:
            return
        clear = self.u.cleartext(crypt)
        if clear:
            self.u.unmount(clear)
            self.u.lock(crypt)
        if access["kind"] == "file":
            self.u.loop_delete(crypt)  # otherwise the drive holding the file stays busy


def _system_disks() -> set[str]:
    """Disks holding the running system. Refuses to guess: if they can't be found (e.g. a ZFS root),
    no drive may be changed."""
    disks: set[str] = set()
    for mp in ("/", "/boot", "/boot/efi", "/home", str(Path.home())):
        if os.path.ismount(mp) or mp in ("/", str(Path.home())):
            disks |= backing_disks(mp)
    if not disks:
        raise DeucalionError("Could not tell which disk holds your system, so no drive will be changed "
                             "(this protects your system disk).")
    return disks


def _username() -> str:
    import pwd
    return pwd.getpwuid(os.getuid()).pw_name


def _open_state_path() -> Path:
    return state_dir() / "open-drives.json"


def _open_state() -> dict:
    return read_json(_open_state_path(), {}) or {}


def _remember_open(source: str, info: dict) -> None:
    s = _open_state()
    s[source] = info
    _open_state_path().parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(_open_state_path(), s)


def _save_open_state_without(source: str) -> None:
    s = _open_state()
    s.pop(source, None)
    write_json_atomic(_open_state_path(), s)


# ------------------------------------------------------------------------------------------------
# The tool copy and the READ-ME-FIRST file on the unencrypted part of the drive

_HOW = {
    "none": {
        "where": "Your backup is the folder Deucalion-Backup. Your files are in Deucalion-Backup/home as\n"
                 "normal files and folders: you can open and copy them directly.",
        "linux": "Just open the drive in the Files app.",
        "mac": "Just open the drive in Finder (exFAT and NTFS drives are readable on macOS).",
        "win": "Just open the drive in File Explorer.",
        "open": "Plug in the drive.",
    },
    "veracrypt-file": {
        "where": "Your backup is inside the encrypted file {file} on this drive.\n"
                 "It opens as a normal folder after you enter its password.",
        "linux": "Run:  Deucalion-Tool/bin/deucalion open\n  or use VeraCrypt: Select File → {file} → Mount.",
        "mac": "Install VeraCrypt (and macFUSE) from " + VERACRYPT_URL + ",\n"
               "  then Select File → {file} → Mount.",
        "win": "Install VeraCrypt from " + VERACRYPT_URL + ",\n  then Select File → {file} → Mount.",
        "open": "Run Deucalion-Tool/bin/deucalion open and enter the backup password.",
    },
    "veracrypt-partition": {
        "where": "Your backup is on the encrypted second part (partition) of this drive.\n"
                 "This normal part only holds this file and the Deucalion tool.",
        "linux": "Run:  Deucalion-Tool/bin/deucalion open\n  or use VeraCrypt: Select Device → the drive's second partition → Mount.",
        "mac": "Install VeraCrypt (and macFUSE) from " + VERACRYPT_URL + ",\n"
               "  then Select Device → the drive's second partition → Mount.",
        "win": "Install VeraCrypt from " + VERACRYPT_URL + ",\n"
               "  then Select Device → the drive's second partition → Mount.\n"
               "  If Windows says a drive needs formatting, choose Cancel: never format it.",
        "open": "Run Deucalion-Tool/bin/deucalion open and enter the backup password.",
    },
    "luks-file": {
        "where": "Your backup is inside the encrypted file {file} (LUKS: Linux only).",
        "linux": "Run:  Deucalion-Tool/bin/deucalion open",
        "mac": "Not readable: LUKS encryption only works on Linux.",
        "win": "Not readable: LUKS encryption only works on Linux.",
        "open": "Run Deucalion-Tool/bin/deucalion open and enter the backup password.",
    },
    "luks-partition": {
        "where": "Your backup is on the encrypted second part (partition) of this drive (LUKS: Linux only).",
        "linux": "Ubuntu asks for the password when you plug in the drive.",
        "mac": "Not readable: LUKS encryption only works on Linux.",
        "win": "Not readable: LUKS encryption only works on Linux.",
        "open": "Plug in the drive and enter the backup password when Ubuntu asks.",
    },
}

README = """\
DEUCALION BACKUP DRIVE
======================

This drive holds a backup made with Deucalion {version}
(https://github.com/Dimitrios-Kafetzis/Deucalion).

{where}

Opening the backup
------------------
Linux (Ubuntu):
  {linux}

macOS:
  {mac}

Windows:
  {win}

Restoring files or rebuilding a machine (Ubuntu)
------------------------------------------------
  1. {open}
  2. Open a terminal in the Deucalion-Tool folder on this drive and run:
       bin/deucalion register <the backup folder>   (only the first time on a new machine)
       bin/deucalion rebuild                        rebuild a whole machine, step by step
       bin/deucalion restore ~/Documents            restore single folders or files

Notes
-----
- Never format this drive or rename the Deucalion-Backup folder.
- Deucalion-Backup/_removed holds older versions and deleted files; empty it with
  'deucalion removed empty' when you need space.
"""


def readme_text(access: dict) -> str:
    key = "none" if access.get("method", "none") == "none" else f"{access['method']}-{access['kind']}"
    how = {k: v.format(file=access.get("file", "")) for k, v in _HOW[key].items()}
    return README.format(version=__version__, **how)


def install_tool_copy(plain_root: Path, target: Target | None, access: dict) -> Path:
    """Copy Deucalion and a READ-ME-FIRST file to the unencrypted part of the drive."""
    src = Path(__file__).resolve().parent.parent
    dest = plain_root / TOOL_DIRNAME
    if dest.exists() and not _is_our_tool_copy(dest):
        # Something of the user's has this name: never replace it.
        dest = plain_root / f"{TOOL_DIRNAME} (Deucalion)"
        if dest.exists() and not _is_our_tool_copy(dest):
            raise DeucalionError(f"{plain_root / TOOL_DIRNAME} belongs to you, so the copy of Deucalion was not "
                                 "put on the drive.")
    tmp = plain_root / f".{TOOL_DIRNAME}.new"
    shutil.rmtree(tmp, ignore_errors=True)
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".git", "tests", "*.img")
    shutil.copytree(src / "deucalion", tmp / "deucalion", ignore=ignore)
    shutil.copytree(src / "bin", tmp / "bin", ignore=ignore)
    for extra in ("README.md", "docs"):
        p = src / extra
        if p.is_dir():
            shutil.copytree(p, tmp / extra, ignore=ignore)
        elif p.is_file():
            shutil.copy2(p, tmp / extra)
    info = dict(access, version=__version__)
    if target is not None:
        info.update(target_id=target.id, target_name=target.name)
    write_json_atomic(tmp / "drive.json", info)
    shutil.rmtree(dest, ignore_errors=True)
    os.rename(tmp, dest)
    readme = plain_root / README_NAME
    try:
        ours = not readme.exists() or readme.read_text(encoding="utf-8", errors="replace").startswith("DEUCALION BACKUP DRIVE")
    except OSError:
        ours = False
    if not ours:
        readme = plain_root / "READ-ME-FIRST (Deucalion).txt"
    readme.write_text(readme_text(access), encoding="utf-8")
    return dest


def _is_our_tool_copy(folder: Path) -> bool:
    """True only for a folder Deucalion itself put on the drive (it has our drive.json)."""
    info = read_json(folder / "drive.json") if (folder / "drive.json").is_file() else None
    return isinstance(info, dict) and "version" in info and "method" in info


def plain_root_of(cfg: Config, target: Target) -> Path | None:
    """Where the tool copy lives for this target (None for whole-drive encryption)."""
    access = cfg.get("targets", {}).get(target.id, {}).get("access", {"method": "none"})
    if access.get("method", "none") == "none":
        return target.root.parent
    if access.get("kind") == "file":
        p = access.get("plain_path")
        return Path(p) if p and Path(p).is_dir() else None
    if access.get("plain_uuid"):
        dev = Path("/dev/disk/by-uuid") / access["plain_uuid"]
        if dev.exists():
            mp = run(["findmnt", "-rno", "TARGET", str(dev.resolve())]).stdout.strip().splitlines()
            return Path(mp[0]) if mp else None
    return None


def discover() -> list[tuple[Path, dict]]:
    """Encrypted Deucalion backups described by Deucalion-Tool/drive.json on mounted drives."""
    found = []
    for root in _mounted_roots():
        info = read_json(root / TOOL_DIRNAME / "drive.json") if (root / TOOL_DIRNAME).is_dir() else None
        if info and info.get("method", "none") != "none":
            found.append((root, info))
    return found


def _mounted_roots() -> list[Path]:
    res = run(["findmnt", "-rno", "TARGET"])
    return [Path(m) for m in res.stdout.split() if m.startswith(("/media/", "/run/media/", "/mnt/"))]


def target_root_for(mountpoint: str) -> Path | None:
    for cand in (Path(mountpoint) / BACKUP_DIRNAME, Path(mountpoint)):
        if _drive_info(cand):
            return cand
    return None
