"""Deucalion's administrator helper.

This file runs as root (started with pkexec or sudo) and does only the fixed
list of operations in OPS below, after checking every argument. It talks to
the normal-user Deucalion process with one JSON object per line on
stdin/stdout. It is deliberately self-contained (standard library only, no
imports from the rest of Deucalion), because it runs with `python3 -I`.

The /etc scanning functions are also imported by the normal Deucalion process
when no administrator access is used (then only readable files are copied).
"""

from __future__ import annotations

import base64
import grp
import hashlib
import json
import os
import pwd
import re
import shutil
import stat
import subprocess
import sys
import time

ETC = "/etc"
DPKG_INFO = "/var/lib/dpkg/info"
DPKG_STATUS = "/var/lib/dpkg/status"

# Never copied: password hashes, private TLS keys, caches and generated files.
ETC_NEVER = {
    "/etc/shadow", "/etc/shadow-", "/etc/gshadow", "/etc/gshadow-", "/etc/passwd-", "/etc/group-",
    "/etc/subuid-", "/etc/subgid-", "/etc/ld.so.cache", "/etc/.pwd.lock", "/etc/adjtime",
    "/etc/machine-id", "/etc/udev/hwdb.bin", "/etc/mtab", "/etc/blkid.tab",
}
ETC_NEVER_DIRS = (
    "/etc/ssl/private/", "/etc/ssl/certs/", "/etc/alternatives/", "/etc/apparmor.d/cache/",
    "/etc/NetworkManager/system-connections/",  # collected separately (contains passwords)
    "/etc/cups/ssl/", "/etc/.java/", "/etc/rc0.d/", "/etc/rc1.d/", "/etc/rc2.d/", "/etc/rc3.d/",
    "/etc/rc4.d/", "/etc/rc5.d/", "/etc/rc6.d/", "/etc/rcS.d/", "/etc/ssh/ssh_host_",
)
# Regenerated automatically by snapd, xml-core, console-setup etc.: never worth restoring.
ETC_GENERATED = re.compile(
    r"^/etc/(systemd/(system|user)/snap[-.]|udev/rules\.d/70-snap\.|xml/|console-setup/cached_"
    r"|\.updated$|perl/XML/SAX/ParserDetails\.ini$|cups/.*\.O$)")
MAX_ETC_FILE = 2 * 1024 * 1024


# ----------------------------------------------------------------------------------------------
# /etc analysis


def _dpkg_conffiles() -> dict[str, tuple[str, str]]:
    """path -> (md5, package) for every dpkg conffile."""
    out: dict[str, tuple[str, str]] = {}
    pkg = None
    in_conf = False
    try:
        with open(DPKG_STATUS, encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.startswith("Package:"):
                    pkg = line.split(":", 1)[1].strip()
                    in_conf = False
                elif line.startswith("Conffiles:"):
                    in_conf = True
                elif in_conf and line.startswith(" "):
                    parts = line.split()
                    if len(parts) >= 2 and parts[0].startswith("/"):
                        out[parts[0]] = (parts[1], pkg or "")
                else:
                    in_conf = False
    except OSError:
        pass
    return out


def _dpkg_owned_etc() -> dict[str, tuple[str | None, str]]:
    """path under /etc -> (md5 or None, package) for files listed by installed packages."""
    out: dict[str, tuple[str | None, str]] = {}
    try:
        names = os.listdir(DPKG_INFO)
    except OSError:
        return out
    for n in names:
        if n.endswith(".list"):
            pkg = n[:-5].split(":")[0]
            try:
                with open(os.path.join(DPKG_INFO, n), encoding="utf-8", errors="surrogateescape") as f:
                    for line in f:
                        if line.startswith("/etc/"):
                            out.setdefault(line.rstrip("\n"), (None, pkg))
            except OSError:
                pass
    for n in names:
        if n.endswith(".md5sums"):
            pkg = n[:-8].split(":")[0]
            try:
                with open(os.path.join(DPKG_INFO, n), encoding="utf-8", errors="surrogateescape") as f:
                    for line in f:
                        md5, _, rel = line.rstrip("\n").partition("  ")
                        if rel.startswith("etc/"):
                            out["/" + rel] = (md5, pkg)
            except OSError:
                pass
    return out


def _packaged_md5s() -> set[bytes]:
    """The checksum of every file every installed package ships (to spot verbatim copies)."""
    out: set[bytes] = set()
    try:
        names = os.listdir(DPKG_INFO)
    except OSError:
        return out
    for n in names:
        if n.endswith(".md5sums"):
            try:
                with open(os.path.join(DPKG_INFO, n), "rb") as f:
                    for line in f:
                        out.add(line[:32])
            except OSError:
                pass
    return out


def install_time() -> float:
    """When the OS was installed (0 if unknown)."""
    for marker in ("/var/log/installer", "/etc/machine-id"):
        try:
            return os.stat(marker).st_mtime
        except OSError:
            pass
    return 0.0


def _md5(path: str) -> str | None:
    h = hashlib.md5()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    except OSError:
        return None
    return h.hexdigest()


def scan_etc() -> list[dict]:
    """Files in /etc that differ from what the installed packages ship, or that no package owns.

    status: "modified"  - a package's config file you (or a program) changed
            "added"     - not from any package, created after the OS was installed
            "installer" - not from any package, unchanged since the OS was installed
    Files identical to a file some package ships (e.g. /etc/profile, copied from
    /usr/share/base-files) are defaults and are left out.
    """
    conffiles = _dpkg_conffiles()
    owned = _dpkg_owned_etc()
    packaged = _packaged_md5s()
    installed_at = install_time()
    found = []
    for root, dirs, files in os.walk(ETC):
        dirs[:] = sorted(d for d in dirs if not (os.path.join(root, d) + "/").startswith(ETC_NEVER_DIRS))
        for name in sorted(files):
            path = os.path.join(root, name)
            if path in ETC_NEVER or path.startswith(ETC_NEVER_DIRS) or ETC_GENERATED.match(path) \
                    or name.endswith(("~", ".dpkg-old", ".dpkg-dist", ".swp")):
                continue
            try:
                st = os.lstat(path)
            except OSError:
                continue
            if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_ETC_FILE:
                continue
            item = {"path": path, "mode": stat.S_IMODE(st.st_mode), "uid": st.st_uid, "gid": st.st_gid,
                    "size": st.st_size, "readable": os.access(path, os.R_OK)}
            if path in conffiles:
                md5, pkg = conffiles[path]
                cur = _md5(path)
                if cur is None or cur == md5:
                    continue
                item.update(status="modified", package=pkg)
            elif path in owned:
                md5, pkg = owned[path]
                if md5 is None:
                    continue  # created by the package's install scripts; not something you changed
                cur = _md5(path)
                if cur is None or cur == md5:
                    continue
                item.update(status="modified", package=pkg)
            else:
                cur = _md5(path) if item["readable"] else None
                if cur is not None and cur.encode() in packaged:
                    continue
                recent = st.st_mtime > installed_at + 3600
                item.update(status="added" if recent else "installer", package="")
            found.append(item)
    return found


def _write_if_changed(path: str, data: bytes, mode: int = 0o644) -> None:
    try:
        with open(path, "rb") as f:
            if f.read() == data:
                return
    except OSError:
        pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def collect_etc(outdir: str) -> dict:
    """Copy changed/added /etc files to outdir/etc/files/ and write outdir/etc/changed.json."""
    items = scan_etc()
    base = os.path.join(outdir, "etc")
    written = set()
    unreadable = 0
    for it in items:
        if not it["readable"] and os.geteuid() != 0:
            unreadable += 1
            it["copied"] = False
            continue
        try:
            with open(it["path"], "rb") as f:
                data = f.read()
        except OSError:
            it["copied"] = False
            continue
        dest = os.path.join(base, "files", it["path"].lstrip("/"))
        _write_if_changed(dest, data, 0o600)
        written.add(dest)
        it["copied"] = True
    _write_if_changed(os.path.join(base, "changed.json"),
                      json.dumps(items, indent=1).encode(), 0o644)
    _prune(os.path.join(base, "files"), written)
    return {"files": len(items), "unreadable": unreadable}


def _prune(folder: str, keep: set[str]) -> None:
    """Remove files below folder that are not in keep (and then empty folders)."""
    if not os.path.isdir(folder):
        return
    for root, dirs, files in os.walk(folder, topdown=False):
        for n in files:
            p = os.path.join(root, n)
            if p not in keep:
                os.remove(p)
        for d in dirs:
            try:
                os.rmdir(os.path.join(root, d))
            except OSError:
                pass


def _chown_tree(path: str, uid: int, gid: int) -> None:
    for root, dirs, files in os.walk(path):
        for n in dirs + files:
            os.lchown(os.path.join(root, n), uid, gid)
    os.lchown(path, uid, gid)


# ----------------------------------------------------------------------------------------------
# Operations (run as root)

_PKG_RE = re.compile(r"^[a-z0-9][a-z0-9+.\-]+(:[a-z0-9]+)?$")
_SNAP_RE = re.compile(r"^[a-z0-9][a-z0-9\-]*$")
_CHANNEL_RE = re.compile(r"^[a-z0-9.\-/]+$")
_UNIT_RE = re.compile(r"^[A-Za-z0-9@_.:\-]+\.(service|timer|socket|path|target|mount)$")
_GROUP_RE = re.compile(r"^[a-z_][a-z0-9_\-]*\$?$")
_SOURCE_FILE_RE = re.compile(r"^[A-Za-z0-9._\-]+\.(list|sources)$")
KEY_DIRS = ("/etc/apt/keyrings/", "/usr/share/keyrings/", "/etc/apt/trusted.gpg.d/")


class OpError(Exception):
    pass


def _check_dir(path: str) -> str:
    path = os.path.realpath(path)
    if not os.path.isdir(path):
        raise OpError(f"not a folder: {path}")
    return path


def _run_streaming(cmd: list[str], emit) -> int:
    env = dict(os.environ, DEBIAN_FRONTEND="noninteractive", LC_ALL="C.UTF-8",
               PATH="/usr/sbin:/usr/bin:/sbin:/bin:/snap/bin")
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                         text=True, errors="replace", env=env)
    for line in p.stdout:
        emit(line.rstrip("\n"))
    return p.wait()


def op_collect_admin(emit, outdir: str, uid: int, gid: int) -> dict:
    outdir = _check_dir(outdir)
    result = collect_etc(outdir)
    # Network connections (Wi-Fi passwords, VPNs)
    nm_src = "/etc/NetworkManager/system-connections"
    nm_dst = os.path.join(outdir, "network", "system-connections")
    written = set()
    if os.path.isdir(nm_src):
        for n in sorted(os.listdir(nm_src)):
            p = os.path.join(nm_src, n)
            if os.path.isfile(p) and not os.path.islink(p):
                with open(p, "rb") as f:
                    dest = os.path.join(nm_dst, n)
                    _write_if_changed(dest, f.read(), 0o600)
                    written.add(dest)
    _prune(nm_dst, written)
    result["network_connections"] = len(written)
    # root's crontab
    root_cron = "/var/spool/cron/crontabs/root"
    dest = os.path.join(outdir, "services", "root-crontab.txt")
    if os.path.isfile(root_cron):
        with open(root_cron, "rb") as f:
            _write_if_changed(dest, f.read(), 0o600)
    elif os.path.exists(dest):
        os.remove(dest)
    _chown_tree(outdir, uid, gid)
    return result


def op_apt_add_source(emit, filename: str, content: str, keys: list[dict]) -> dict:
    if not _SOURCE_FILE_RE.match(filename):
        raise OpError(f"bad source file name: {filename}")
    added_keys = []
    for k in keys:
        path = os.path.normpath(k["path"])
        if not path.startswith(KEY_DIRS) or "/../" in path:
            raise OpError(f"key outside the apt key folders: {path}")
        data = base64.b64decode(k["data"])
        if os.path.exists(path):
            continue  # keep the key that is already there
        os.makedirs(os.path.dirname(path), mode=0o755, exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        os.chmod(path, 0o644)
        added_keys.append(path)
    dest = os.path.join("/etc/apt/sources.list.d", filename)
    if os.path.exists(dest):
        shutil.copy2(dest, dest + ".deucalion-old")
    with open(dest, "w", encoding="utf-8") as f:
        f.write(content)
    os.chmod(dest, 0o644)
    return {"source": dest, "keys": added_keys}


def op_apt_update(emit) -> dict:
    return {"code": _run_streaming(["apt-get", "update"], emit)}


def op_apt_install(emit, packages: list[str]) -> dict:
    bad = [p for p in packages if not _PKG_RE.match(p)]
    if bad:
        raise OpError(f"bad package names: {bad}")
    if not packages:
        return {"code": 0}
    return {"code": _run_streaming(["apt-get", "install", "-y", *packages], emit)}


def op_apt_install_debs(emit, paths: list[str]) -> dict:
    files = []
    for p in paths:
        p = os.path.realpath(p)
        if not (p.endswith(".deb") and os.path.isfile(p)):
            raise OpError(f"not a .deb file: {p}")
        files.append(p)
    return {"code": _run_streaming(["apt-get", "install", "-y", *files], emit)}


def op_snap_install(emit, name: str, channel: str = "", classic: bool = False) -> dict:
    if not _SNAP_RE.match(name) or (channel and not _CHANNEL_RE.match(channel)):
        raise OpError(f"bad snap: {name} {channel}")
    cmd = ["snap", "install", name]
    if channel:
        cmd.append(f"--channel={channel}")
    if classic:
        cmd.append("--classic")
    return {"code": _run_streaming(cmd, emit)}


def op_put_etc_file(emit, src: str, dest: str, mode: int, undo_dir: str) -> dict:
    dest = os.path.normpath(dest)
    if not dest.startswith("/etc/") or "/../" in dest or dest in ETC_NEVER:
        raise OpError(f"not an allowed /etc file: {dest}")
    if not os.path.isfile(src):
        raise OpError(f"missing source: {src}")
    if not undo_dir.startswith("/var/backups/deucalion/"):
        raise OpError("bad undo folder")
    if os.path.lexists(dest):
        aside = os.path.join(undo_dir, dest.lstrip("/"))
        os.makedirs(os.path.dirname(aside), exist_ok=True)
        shutil.copy2(dest, aside, follow_symlinks=False)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".deucalion-tmp"
    shutil.copyfile(src, tmp)
    os.chmod(tmp, int(mode) & 0o7777)
    os.chown(tmp, 0, 0)
    os.replace(tmp, dest)
    return {"dest": dest}


def op_nm_import(emit, files: list[str]) -> dict:
    target = "/etc/NetworkManager/system-connections"
    os.makedirs(target, mode=0o700, exist_ok=True)
    imported = []
    for src in files:
        name = os.path.basename(src)
        if not os.path.isfile(src) or name.startswith("."):
            raise OpError(f"bad connection file: {src}")
        dest = os.path.join(target, name)
        if os.path.exists(dest):
            continue
        shutil.copyfile(src, dest)
        os.chmod(dest, 0o600)
        os.chown(dest, 0, 0)
        imported.append(name)
    if imported:
        _run_streaming(["nmcli", "connection", "reload"], emit)
    return {"imported": imported}


def op_enable_units(emit, units: list[str]) -> dict:
    bad = [u for u in units if not _UNIT_RE.match(u)]
    if bad:
        raise OpError(f"bad unit names: {bad}")
    return {"code": _run_streaming(["systemctl", "enable", *units], emit) if units else 0}


def op_add_groups(emit, user: str, groups: list[str]) -> dict:
    pwd.getpwnam(user)
    bad = [g for g in groups if not _GROUP_RE.match(g)]
    if bad:
        raise OpError(f"bad group names: {bad}")
    added = []
    for g in groups:
        try:
            grp.getgrnam(g)
        except KeyError:
            continue
        if _run_streaming(["usermod", "-aG", g, user], emit) == 0:
            added.append(g)
    return {"added": added}


def op_put_crontab(emit, user: str, src: str) -> dict:
    pwd.getpwnam(user)
    if not os.path.isfile(src):
        raise OpError(f"missing crontab file: {src}")
    return {"code": _run_streaming(["crontab", "-u", user, src], emit)}


def op_netplan_import(emit, files: list[str]) -> dict:
    """NetworkManager connections saved as netplan files (Ubuntu 23.10+)."""
    imported = []
    for src in files:
        name = os.path.basename(src)
        if not re.match(r"^90-NM-[0-9a-f-]+\.yaml$", name) or not os.path.isfile(src):
            raise OpError(f"bad netplan connection file: {src}")
        dest = os.path.join("/etc/netplan", name)
        if os.path.exists(dest):
            continue
        shutil.copyfile(src, dest)
        os.chmod(dest, 0o600)
        os.chown(dest, 0, 0)
        imported.append(name)
    if imported:
        _run_streaming(["netplan", "generate"], emit)
        _run_streaming(["nmcli", "connection", "reload"], emit)
    return {"imported": imported}


_RELOADS = {
    "udev": [["udevadm", "control", "--reload-rules"], ["udevadm", "trigger"]],
    "cups": [["systemctl", "restart", "cups"]],
    "apparmor": [["systemctl", "reload", "apparmor"]],
    "sysctl": [["sysctl", "--system"]],
    "systemd": [["systemctl", "daemon-reload"]],
}


def op_reload(emit, what: list[str]) -> dict:
    done = []
    for w in what:
        for cmd in _RELOADS.get(w, []):
            _run_streaming(cmd, emit)
        if w in _RELOADS:
            done.append(w)
    return {"reloaded": done}


# ----------------------------------------------------------------------------------------------
# VeraCrypt volumes (creating and unlocking them needs root; plain exFAT and LUKS drives are
# handled by UDisks without administrator rights)

_PART_RE = re.compile(r"^/dev/(sd[a-z]+\d+|nvme\d+n\d+p\d+|mmcblk\d+p\d+|vd[a-z]+\d+|loop\d+p\d+)$")
_NAME_RE = re.compile(r"^deucalion-[a-z0-9-]{1,40}$")
_LABEL_RE = re.compile(r"^[A-Za-z0-9 _.-]{1,15}$")
_CONTAINER_DIRS = ("/media/", "/run/media/", "/mnt/")


def _out(cmd: list[str], input_text: str | None = None) -> str:
    r = subprocess.run(cmd, input=input_text, capture_output=True, text=True,
                       env=dict(os.environ, LC_ALL="C.UTF-8", PATH="/usr/sbin:/usr/bin:/sbin:/bin"))
    if r.returncode != 0:
        raise OpError(f"{os.path.basename(cmd[0])} failed: {(r.stderr or r.stdout).strip()[-400:]}")
    return r.stdout


def _system_disks() -> set[str]:
    """Disks that hold the running system: never touched, whatever the caller says."""
    disks = set()
    mounts = {}
    for line in _out(["findmnt", "-rn", "-o", "TARGET,SOURCE"]).splitlines():
        t, _, src = line.partition(" ")
        mounts[t] = src
    for mp in ("/", "/boot", "/boot/efi", "/home", "/usr", "/var"):
        src = mounts.get(mp, "").split("[")[0]
        if src.startswith("/dev/"):
            tree = json.loads(_out(["lsblk", "-s", "-J", "-o", "NAME,PATH,TYPE", src]))
            stack = list(tree.get("blockdevices", []))
            while stack:
                n = stack.pop()
                if n.get("type") == "disk":
                    disks.add(n["path"])
                stack.extend(n.get("children") or [])
    return disks


def _check_source(source: str, must_exist: bool = True) -> None:
    """A VeraCrypt volume is either a partition of a non-system disk or a file on a mounted drive."""
    if source.startswith("/dev/"):
        if not _PART_RE.match(source):
            raise OpError(f"not a partition: {source}")
        parent = "/dev/" + _out(["lsblk", "-no", "PKNAME", source]).strip()
        if parent in _system_disks():
            raise OpError(f"{source} is on the system disk; refusing to touch it")
        return
    real = os.path.realpath(source)
    if not real.startswith(_CONTAINER_DIRS) or not real.endswith(".hc"):
        raise OpError(f"not an allowed container file: {source}")
    if must_exist and not os.path.isfile(real):
        raise OpError(f"no such container file: {source}")


def _settle() -> None:
    subprocess.run(["udevadm", "settle"], capture_output=True)


def _vc_open(device: str, name: str, passphrase: str, emit) -> str:
    if not _NAME_RE.match(name):
        raise OpError(f"bad mapping name {name}")
    emit("Unlocking (VeraCrypt volumes can take up to a minute)…")
    _out(["cryptsetup", "open", "--type", "tcrypt", "--veracrypt", device, name], passphrase + "\n")
    _settle()
    return f"/dev/mapper/{name}"


def op_veracrypt_create(emit, source: str, passphrase: str, label: str, uid: int, gid: int,
                        size_bytes: int = 0, veracrypt: str = "") -> dict:
    """Create a VeraCrypt volume on a partition, or as a new container file, with exFAT inside."""
    if len(passphrase) < 8:
        raise OpError("the password is too short")
    if not _LABEL_RE.match(label):
        raise OpError(f"bad label {label!r}")
    is_file = not source.startswith("/dev/")
    _check_source(source, must_exist=False)
    if is_file and os.path.exists(source):
        raise OpError(f"{source} already exists")
    vc = os.path.realpath(veracrypt or shutil.which("veracrypt") or "/usr/bin/veracrypt")
    if not os.path.basename(vc).startswith("veracrypt") or not os.access(vc, os.X_OK):
        raise OpError("VeraCrypt is not installed")
    if not shutil.which("mkfs.exfat"):
        raise OpError("mkfs.exfat is missing (install the exfatprogs package)")
    cmd = [vc, "--text", "--non-interactive", "--create", source, "--volume-type=normal",
           "--encryption=AES", "--hash=SHA-512", "--filesystem=none", "--pim=0", "--keyfiles=",
           "--random-source=/dev/urandom", "--stdin"]
    if is_file:
        if int(size_bytes) < 64 * 1024 * 1024:
            raise OpError("the encrypted folder must be at least 64 MB")
        cmd.append(f"--size={int(size_bytes)}")
    if source.startswith("/dev/"):
        subprocess.run(["wipefs", "-a", source], capture_output=True)
    emit("Encrypting (VeraCrypt)…")
    _out(cmd, passphrase + "\n")
    loop = None
    device = source
    if is_file:
        loop = _out(["losetup", "--find", "--show", source]).strip()
        device = loop
    name = f"deucalion-new-{os.getpid()}"
    try:
        mapper = _vc_open(device, name, passphrase, emit)
        emit("Creating the exFAT filesystem inside")
        _out(["mkfs.exfat", "-L", label, mapper])
    finally:
        subprocess.run(["cryptsetup", "close", name], capture_output=True)
        if loop:
            subprocess.run(["losetup", "-d", loop], capture_output=True)
    if is_file:
        os.chown(source, int(uid), int(gid))
    return {"source": source}


def op_veracrypt_open(emit, source: str, passphrase: str, name: str, mount_name: str, user: str) -> dict:
    """Unlock a VeraCrypt partition or container file and mount it at /media/<user>/<mount_name>."""
    pw = pwd.getpwnam(user)
    _check_source(source)
    if not _LABEL_RE.match(mount_name):
        raise OpError(f"bad mount name {mount_name!r}")
    if os.path.exists(f"/dev/mapper/{name}"):
        raise OpError("this drive is already unlocked")
    loop = None
    device = source
    if not source.startswith("/dev/"):
        loop = _out(["losetup", "--find", "--show", source]).strip()
        device = loop
    try:
        mapper = _vc_open(device, name, passphrase, emit)
    except OpError:
        if loop:
            subprocess.run(["losetup", "-d", loop], capture_output=True)
        raise OpError("wrong password, or this is not a VeraCrypt volume") from None
    base = f"/media/{user}"
    os.makedirs(base, exist_ok=True)
    mountpoint = os.path.join(base, mount_name)
    n = 2
    while os.path.ismount(mountpoint):
        mountpoint = os.path.join(base, f"{mount_name}{n}")
        n += 1
    os.makedirs(mountpoint, exist_ok=True)
    try:
        _out(["mount", "-o", f"uid={pw.pw_uid},gid={pw.pw_gid},fmask=0022,dmask=0022", mapper, mountpoint])
    except OpError:
        subprocess.run(["cryptsetup", "close", name], capture_output=True)
        if loop:
            subprocess.run(["losetup", "-d", loop], capture_output=True)
        raise
    return {"mountpoint": mountpoint, "mapper": mapper, "loop": loop}


def op_veracrypt_close(emit, mountpoint: str, name: str, loop: str | None = None) -> dict:
    if not _NAME_RE.match(name):
        raise OpError(f"bad mapping name {name}")
    if mountpoint and os.path.ismount(mountpoint):
        if not mountpoint.startswith("/media/"):
            raise OpError("not a Deucalion mount point")
        subprocess.run(["sync"])
        _out(["umount", mountpoint])
        try:
            os.rmdir(mountpoint)
        except OSError:
            pass
    if os.path.exists(f"/dev/mapper/{name}"):
        _out(["cryptsetup", "close", name])
    if loop and re.match(r"^/dev/loop\d+$", loop):
        subprocess.run(["losetup", "-d", loop], capture_output=True)
    return {"closed": True}


OPS = {
    "veracrypt_create": op_veracrypt_create,
    "veracrypt_open": op_veracrypt_open,
    "veracrypt_close": op_veracrypt_close,
    "netplan_import": op_netplan_import,
    "reload": op_reload,
    "collect_admin": op_collect_admin,
    "apt_add_source": op_apt_add_source,
    "apt_update": op_apt_update,
    "apt_install": op_apt_install,
    "apt_install_debs": op_apt_install_debs,
    "snap_install": op_snap_install,
    "put_etc_file": op_put_etc_file,
    "nm_import": op_nm_import,
    "enable_units": op_enable_units,
    "add_groups": op_add_groups,
    "put_crontab": op_put_crontab,
}


def serve() -> int:
    """Answer requests until stdin closes or {"op": "quit"} arrives."""
    out = sys.stdout

    def send(obj):
        out.write(json.dumps(obj) + "\n")
        out.flush()

    os.umask(0o022)
    send({"ready": True, "uid": os.geteuid()})
    for line in sys.stdin:
        try:
            req = json.loads(line)
        except ValueError:
            continue
        rid, op = req.get("id"), req.get("op")
        if op == "quit":
            break
        func = OPS.get(op)
        if func is None:
            send({"id": rid, "ok": False, "error": f"unknown operation {op!r}"})
            continue
        last = [0.0]

        def emit(text, rid=rid):
            send({"id": rid, "progress": text})

        try:
            result = func(emit, **(req.get("args") or {}))
            send({"id": rid, "ok": True, "result": result})
        except (OpError, OSError, KeyError, TypeError, ValueError) as e:
            send({"id": rid, "ok": False, "error": f"{type(e).__name__}: {e}"})
    return 0


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "serve":
        sys.exit(serve())
    print("usage: helper.py serve", file=sys.stderr)
    sys.exit(2)
