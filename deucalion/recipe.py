# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Dimitrios Kafetzis

"""The system recipe: what makes this Ubuntu installation yours, saved as readable
text files so it can be replayed on a new machine or a newer Ubuntu release.

The recipe is generated into a local folder (~/.local/state/deucalion/system)
and then backed up like any other folder, to `system/` on the drive. Files are
only rewritten when their content changes, so unchanged parts are not copied
again on every backup.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import pwd
import grp
import re
import shutil
import socket
from dataclasses import dataclass, field
from pathlib import Path

from . import helper
from .config import state_dir
from .util import DeucalionError, os_release, run

FORMAT = 1
APT_KEY_DIRS = [Path("/etc/apt/keyrings"), Path("/etc/apt/trusted.gpg.d")]
UBUNTU_KEYS = re.compile(r"^ubuntu-(keyring|archive|master|cloudimage|oem|pro)")
# snaps that are pulled in automatically as dependencies
SNAP_DEPENDENCY = re.compile(r"^(core\d*|bare|snapd|gnome-\d|gtk-common-themes|kf\d|mesa-\d|"
                             r"gpu-\d|snapd-desktop-integration)")

README = """\
Deucalion system recipe
=======================

These files describe the system this backup was made from, so it can be rebuilt
on a new machine or a newer Ubuntu release (run: deucalion rebuild).

info.json                     Ubuntu version, machine, user, groups
packages/apt-manual.txt       apt packages you installed
packages/apt-installed.tsv    every installed apt package (for reference)
packages/apt-local.json       packages installed from downloaded .deb files, and
                              where those .deb files were found in your home folder
packages/apt/                 apt repositories (sources) and their signing keys
packages/snaps.json           snaps, with channel and confinement
packages/flatpaks.json        flatpak apps and remotes
packages/other.json           npm / pipx global tools, VS Code extensions
desktop/dconf.ini             all GNOME / desktop settings (dconf dump /)
desktop/gnome-extensions.json enabled GNOME Shell extensions
services/                     crontabs and enabled systemd services
etc/changed.json              files in /etc you (or programs) changed or added
etc/files/                    copies of those files
network/                      saved Wi-Fi / VPN connections (contain passwords)
software/manual-installs.json software installed by hand in /opt and /usr/local
"""


@dataclass
class RecipeResult:
    folder: Path
    warnings: list[str] = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    admin: bool = False


def recipe_dir() -> Path:
    return state_dir() / "system"


class _Writer:
    def __init__(self, root: Path):
        self.root = root
        self.written: set[str] = set()

    def write(self, rel: str, data: str | bytes, mode: int = 0o644) -> None:
        if isinstance(data, str):
            data = data.encode("utf-8", "surrogateescape")
        path = self.root / rel
        real_root = os.path.realpath(self.root)
        if not os.path.realpath(path.parent).startswith(real_root + os.sep) and \
                os.path.realpath(path.parent) != real_root:
            raise DeucalionError(f"refusing to write outside the recipe folder: {rel}")
        if path.is_symlink():
            path.unlink()  # never write through a link someone placed here
        helper._write_if_changed(str(path), data, mode)
        self.written.add(str(path))

    def json(self, rel: str, obj) -> None:
        self.write(rel, json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + "\n")

    def copy(self, rel: str, src: Path, mode: int = 0o644) -> bool:
        try:
            self.write(rel, src.read_bytes(), mode)
            return True
        except OSError:
            return False

    def keep_tree(self, rel: str) -> None:
        """Keep files below rel that were written by someone else (the admin helper)."""
        base = self.root / rel
        if base.is_file():
            self.written.add(str(base))
        for dirpath, _, files in os.walk(base):
            for n in files:
                self.written.add(os.path.join(dirpath, n))

    def prune(self) -> None:
        helper._prune(str(self.root), self.written)


def _lines(cmd: list[str], timeout: float = 60) -> list[str] | None:
    try:
        res = run(cmd, timeout=timeout)
    except (OSError, Exception):
        return None
    if res.returncode != 0:
        return None
    return [l for l in res.stdout.splitlines() if l.strip()]


# -------------------------------------------------------------------------------------------
# Collectors


def _info(w: _Writer, home: Path) -> dict:
    osr = os_release()
    user = pwd.getpwuid(os.getuid())
    groups = sorted({grp.getgrgid(g).gr_name for g in os.getgrouplist(user.pw_name, user.pw_gid)
                     if _safe_group(g)})

    def dmi(name):
        try:
            return Path(f"/sys/class/dmi/id/{name}").read_text().strip()
        except OSError:
            return ""

    gnome = (_lines(["gnome-shell", "--version"]) or [""])[0]
    info = {
        "format": FORMAT,
        "os": {"name": osr.get("NAME", ""), "version_id": osr.get("VERSION_ID", ""),
               "codename": osr.get("VERSION_CODENAME", ""), "pretty": osr.get("PRETTY_NAME", "")},
        "machine": {"hostname": socket.gethostname(), "arch": platform.machine(),
                    "vendor": dmi("sys_vendor"), "model": dmi("product_name")},
        "user": {"name": user.pw_name, "uid": user.pw_uid, "gid": user.pw_gid, "home": str(home),
                 "shell": user.pw_shell, "groups": groups},
        "desktop": {"session": os.environ.get("XDG_CURRENT_DESKTOP", ""), "gnome": gnome},
        "installed": helper.install_time(),
    }
    w.json("info.json", info)
    return info


def _safe_group(gid: int) -> bool:
    try:
        grp.getgrgid(gid)
        return True
    except KeyError:
        return False


def _apt(w: _Writer, home: Path, warnings: list[str]) -> dict:
    manual = _lines(["apt-mark", "showmanual"]) or []
    w.write("packages/apt-manual.txt", "\n".join(sorted(manual)) + "\n")
    installed = _lines(["dpkg-query", "-W", "-f", "${binary:Package}\t${Version}\t${db:Status-Abbrev}\n"]) or []
    installed = [l for l in installed if l.split("\t")[-1].startswith("ii")]
    w.write("packages/apt-installed.tsv", "\n".join(sorted(installed)) + "\n")

    # Packages that came from a downloaded .deb (not from any repository)
    local = []
    for line in _lines(["apt", "list", "--installed"], timeout=120) or []:
        if ",local]" in line:
            name, _, rest = line.partition("/")
            parts = rest.split()
            local.append({"package": name, "version": parts[1] if len(parts) > 1 else ""})
    debs = _find_debs(home)
    for item in local:
        item["deb_files"] = [str(p.relative_to(home)) for p, (pkg, _) in debs.items() if pkg == item["package"]]
    w.json("packages/apt-local.json", local)

    # Repositories and keys
    sources = [Path("/etc/apt/sources.list")] + sorted(Path("/etc/apt/sources.list.d").glob("*"))
    sources += sorted(Path("/etc/apt/preferences.d").glob("*"))
    for src in sources:
        if src.is_file() and not src.name.endswith((".save", ".distUpgrade", ".orig", ".bak")):
            w.copy(f"packages/apt/{src.relative_to('/etc/apt')}", src)
    keys = set()
    for d in APT_KEY_DIRS:
        keys |= {p for p in d.glob("*") if p.is_file() and not UBUNTU_KEYS.match(p.name)}
    for src in sources:
        try:
            text = src.read_text(errors="replace")
        except OSError:
            continue
        for m in re.finditer(r"(?:signed-by=|Signed-By:\s*)(/[^\s\]]+)", text, re.I):
            p = Path(m.group(1))
            if p.is_file() and not UBUNTU_KEYS.match(p.name):
                keys.add(p)
    for k in sorted(keys):
        if not w.copy(f"packages/apt/keys{k}", k):
            warnings.append(f"Could not read apt key {k}.")
    return {"apt_manual": len(manual), "apt_local": len(local), "apt_sources": len(sources)}


def _find_debs(home: Path) -> dict[Path, tuple[str, str]]:
    """.deb files in the usual download places: {path: (package, version)}."""
    found = {}
    places = [(home, 1), (home / "Downloads", 3), (home / "Desktop", 2), (home / "Documents", 2)]
    for base, depth in places:
        if not base.is_dir():
            continue
        base_depth = len(base.parts)
        for dirpath, dirs, files in os.walk(base):
            if len(Path(dirpath).parts) - base_depth >= depth:
                dirs[:] = []
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for n in files:
                if n.endswith(".deb"):
                    p = Path(dirpath) / n
                    info = _lines(["dpkg-deb", "-f", str(p), "Package", "Version"], timeout=20)
                    if info:
                        fields = dict(l.split(": ", 1) for l in info if ": " in l)
                        found[p] = (fields.get("Package", ""), fields.get("Version", ""))
    return found


def _snaps(w: _Writer) -> dict:
    out = []
    lines = _lines(["snap", "list", "--unicode=never", "--color=never"]) or []
    for line in lines[1:]:
        parts = line.split()
        if len(parts) < 6:
            continue
        name, version, rev, tracking, publisher, notes = parts[:6]
        out.append({"name": name, "version": version, "revision": rev,
                    "channel": "" if tracking == "-" else tracking, "publisher": publisher.rstrip("*"),
                    "classic": "classic" in notes, "devmode": "devmode" in notes,
                    "dependency": bool(SNAP_DEPENDENCY.match(name)) or "base" in notes or "snapd" in notes})
    w.json("packages/snaps.json", out)
    return {"snaps": sum(not s["dependency"] for s in out)}


def _flatpaks(w: _Writer) -> dict:
    if not shutil.which("flatpak"):
        w.json("packages/flatpaks.json", {"apps": [], "remotes": []})
        return {"flatpaks": 0}
    apps = []
    for line in _lines(["flatpak", "list", "--app", "--columns=application,origin,branch,installation"]) or []:
        p = line.split("\t")
        if len(p) >= 4:
            apps.append({"id": p[0], "remote": p[1], "branch": p[2], "installation": p[3]})
    remotes = []
    for line in _lines(["flatpak", "remotes", "--columns=name,url,options"]) or []:
        p = line.split("\t")
        if len(p) >= 2:
            remotes.append({"name": p[0], "url": p[1], "options": p[2] if len(p) > 2 else ""})
    w.json("packages/flatpaks.json", {"apps": apps, "remotes": remotes})
    return {"flatpaks": len(apps)}


def _other_tools(w: _Writer) -> None:
    other: dict = {}
    if shutil.which("npm"):
        res = _lines(["npm", "ls", "-g", "--depth=0", "--json"])
        try:
            deps = json.loads("\n".join(res or [])).get("dependencies", {})
            other["npm_global"] = sorted(k for k in deps if k not in ("npm", "corepack"))
        except ValueError:
            pass
    if shutil.which("pipx"):
        res = _lines(["pipx", "list", "--short"])
        if res is not None:
            other["pipx"] = [l.split()[0] for l in res]
    if shutil.which("code"):
        res = _lines(["code", "--list-extensions"], timeout=60)
        if res is not None:
            other["vscode_extensions"] = res
    w.json("packages/other.json", other)


def _desktop(w: _Writer, warnings: list[str]) -> None:
    res = run(["dconf", "dump", "/"]) if shutil.which("dconf") else None
    if res is not None and res.returncode == 0:
        w.write("desktop/dconf.ini", res.stdout)
    else:
        warnings.append("Could not save desktop settings (dconf).")
    if shutil.which("gnome-extensions"):
        w.json("desktop/gnome-extensions.json", {
            "enabled": _lines(["gnome-extensions", "list", "--enabled"]) or [],
            "user": _lines(["gnome-extensions", "list", "--user"]) or [],
        })


def _services(w: _Writer) -> dict:
    res = run(["crontab", "-l"]) if shutil.which("crontab") else None
    if res is not None and res.returncode == 0 and res.stdout.strip():
        w.write("services/user-crontab.txt", res.stdout, 0o600)
    user_units = _lines(["systemctl", "--user", "list-unit-files", "--state=enabled", "--no-legend", "--no-pager"])
    sys_units = _lines(["systemctl", "list-unit-files", "--state=enabled", "--no-legend", "--no-pager"])
    w.write("services/user-enabled.txt", "\n".join(l.split()[0] for l in user_units or []) + "\n")
    w.write("services/system-enabled.txt", "\n".join(l.split()[0] for l in sys_units or []) + "\n")
    return {"system_services": len(sys_units or [])}


def _software(w: _Writer) -> None:
    items = []
    for base in (Path("/opt"), Path("/usr/local")):
        if not base.is_dir():
            continue
        for d in sorted(base.iterdir()):
            if base == Path("/usr/local") and d.name in ("bin", "sbin", "lib", "include", "share", "etc",
                                                           "games", "src", "man"):
                for sub in sorted(d.iterdir()) if d.is_dir() else []:
                    if d.name in ("bin", "sbin") or (sub.is_dir() and not sub.name.startswith(("python", "lib", "man"))):
                        items.append({"path": str(sub), "kind": "dir" if sub.is_dir() else "file"})
            else:
                items.append({"path": str(d), "kind": "dir" if d.is_dir() else "file"})
    w.json("software/manual-installs.json", items)


def _containers(w: _Writer) -> None:
    info: dict = {}
    if shutil.which("docker"):
        info["docker_images"] = _lines(["docker", "image", "ls", "--format", "{{.Repository}}:{{.Tag}}"]) or []
        info["docker_volumes"] = _lines(["docker", "volume", "ls", "--format", "{{.Name}}"]) or []
    if shutil.which("virsh"):
        info["libvirt_user_vms"] = _lines(["virsh", "list", "--all", "--name"]) or []
    if info:
        w.json("software/containers-and-vms.json", info)


# -------------------------------------------------------------------------------------------


def collect(home: Path, privileged=None, log: logging.Logger | None = None) -> RecipeResult:
    """Generate the recipe. `privileged` is a Privileged helper connection, or None to
    collect only what a normal user can read."""
    log = log or logging.getLogger("deucalion")
    root = recipe_dir()
    root.mkdir(parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    w = _Writer(root)
    res = RecipeResult(root)
    w.write("README.txt", README)
    steps = [
        ("system information", lambda: _info(w, home)),
        ("apt packages and repositories", lambda: res.summary.update(_apt(w, home, res.warnings))),
        ("snaps", lambda: res.summary.update(_snaps(w))),
        ("flatpaks", lambda: res.summary.update(_flatpaks(w))),
        ("other tools", lambda: _other_tools(w)),
        ("desktop settings", lambda: _desktop(w, res.warnings)),
        ("services", lambda: res.summary.update(_services(w))),
        ("manually installed software", lambda: _software(w)),
        ("containers and virtual machines", lambda: _containers(w)),
    ]
    for name, func in steps:
        try:
            func()
        except Exception as e:  # one failing collector must not stop the backup
            res.warnings.append(f"Could not save {name}: {e}")
            log.exception("recipe step %s failed", name)

    # /etc, network connections, root crontab
    marker = root / "etc" / "collected-by.txt"
    if privileged is not None:
        try:
            r = privileged.call("collect_admin", uid=os.getuid(), gid=os.getgid())
            _take_admin_folder(w, Path(r["folder"]))
            res.admin = True
            res.summary["etc_files"] = r.get("files", 0)
            res.summary["network_connections"] = r.get("network_connections", 0)
            w.write("etc/collected-by.txt", "administrator\n")
        except Exception as e:
            res.warnings.append(f"System settings needing administrator access were not saved: {e}")
    if not res.admin:
        previous_admin = marker.exists() and marker.read_text().startswith("administrator")
        if previous_admin:
            res.warnings.append("System settings (/etc, network) were not updated because administrator "
                                "access was not used; the copy from an earlier backup is kept.")
        else:
            r = helper.collect_etc(str(root))
            res.summary["etc_files"] = r["files"]
            w.write("etc/collected-by.txt", "user\n")
            if r["unreadable"]:
                res.warnings.append(f"{r['unreadable']} system files (and network connections) can only be "
                                    "saved with administrator access.")
    if not res.admin:
        for kept in ("etc", "network", "services/root-crontab.txt"):
            w.keep_tree(kept)
    w.prune()
    return res


def _take_admin_folder(w: _Writer, folder: Path) -> None:
    """Copy what the administrator helper collected into the recipe (as the normal user)."""
    if not str(folder).startswith("/tmp/deucalion-admin-") or folder.is_symlink() or not folder.is_dir() \
            or folder.stat().st_uid != os.getuid():
        raise DeucalionError("unexpected folder from the administrator helper")
    try:
        for dirpath, dirs, files in os.walk(folder):
            for n in files:
                p = Path(dirpath) / n
                if not p.is_symlink():
                    w.write(str(p.relative_to(folder)), p.read_bytes(), 0o600)
    finally:
        shutil.rmtree(folder, ignore_errors=True)
