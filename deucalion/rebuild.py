"""Rebuild a machine from a backup: the new-machine wizard.

Each step first *plans* (reads the backup and this machine, changes nothing),
then the user reviews the items and the step *applies* only the selected ones.
Steps can be skipped, re-run and resumed; progress is kept in
~/.local/state/deucalion/rebuild.json.
"""

from __future__ import annotations

import base64
import difflib
import errno
import json
import logging
import os
import re
import shutil
import stat
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from . import aptsources
from .config import Config, state_dir
from .manifest import Manifest
from .privileged import Privileged
from .restore import Restorer, UNDO_DIRNAME
from .target import Target
from .util import DeucalionError, human_size, now_iso, os_release, read_json, run, run_stamp, write_json_atomic

Out = Callable[[str], None]


@dataclass
class Item:
    key: str
    label: str
    detail: str = ""
    selected: bool = True
    selectable: bool = True       # False: shown for information only
    data: Any = None


@dataclass
class StepPlan:
    items: list[Item] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def actionable(self) -> list[Item]:
        return [i for i in self.items if i.selectable]


class Context:
    """Everything the steps need: the backup, its recipe, and old → new mappings."""

    def __init__(self, cfg: Config, target: Target, manifest: Manifest, log: logging.Logger | None = None,
                 privileged: Privileged | None = None):
        self.cfg = cfg
        self.t = target
        self.m = manifest
        self.log = log or logging.getLogger("deucalion")
        self._priv = privileged
        self.info = self.read_json("info.json") or {}
        summary = target.read_summary()
        old_user = self.info.get("user") or summary.get("user") or {}
        self.old_home = old_user.get("home") or ""
        self.old_user = old_user.get("name") or ""
        self.new_home = str(cfg.home)
        self.new_user = Path(self.new_home).name if cfg.get("home_path") else os.environ.get("USER", "")
        self.old_codename = (self.info.get("os") or {}).get("codename", "")
        osr = os_release()
        self.new_codename = osr.get("VERSION_CODENAME", "")
        self.new_version = osr.get("VERSION_ID", "")
        self.has_recipe = bool(self.info)
        self.stamp = run_stamp()
        self.cancel = threading.Event()   # set to stop a long step (the home restore) safely

    # -- reading the backup ---------------------------------------------------------------------
    def drive_path(self, logical: str) -> Path | None:
        e = self.m.get(logical)
        if e is None or e.kind != "f":
            return None
        p = self.t.root / e.stored
        return p if p.is_file() else None

    def recipe_file(self, rel: str) -> Path | None:
        return self.drive_path(f"system/{rel}")

    def read_text(self, rel: str) -> str | None:
        p = self.recipe_file(rel)
        try:
            return p.read_text(encoding="utf-8", errors="surrogateescape") if p else None
        except OSError:
            return None

    def read_json(self, rel: str):
        text = self.read_text(rel)
        try:
            return json.loads(text) if text else None
        except ValueError:
            return None

    def recipe_files(self, rel: str) -> dict[str, Path]:
        """{name: path on drive} for the files directly in a recipe folder."""
        out = {}
        for name, e in self.m.children(f"system/{rel}").items():
            if e.kind == "f":
                out[name] = self.t.root / e.stored
        return out

    # -- this machine -----------------------------------------------------------------------------
    @property
    def home_changed(self) -> bool:
        return bool(self.old_home) and self.old_home != self.new_home

    def _home_re(self, as_bytes: bool):
        # The old home path only as a whole path: '/home/dim' in '/home/dim/x' or '/home/dim"', never
        # inside '/home/dimension' or '/home/dimitris' (which may be the NEW home path).
        old = re.escape(self.old_home.encode() if as_bytes else self.old_home)
        return re.compile(old + (rb"(?=[/\s\"':;,]|$)" if as_bytes else r"(?=[/\s\"':;,]|$)"), re.M)

    def map_paths(self, text: str) -> str:
        if not self.home_changed:
            return text
        return self._home_re(False).sub(lambda m: self.new_home, text)

    def map_paths_bytes(self, data: bytes) -> bytes:
        if not self.home_changed:
            return data
        return self._home_re(True).sub(lambda m: self.new_home.encode(), data)

    def count_old_home(self, data: bytes) -> int:
        return len(self._home_re(True).findall(data)) if self.home_changed else 0

    def undo_dir(self, what: str) -> Path:
        """A new, empty folder for the originals changed by one step run (never reused)."""
        base = Path(self.new_home) / UNDO_DIRNAME
        n = 1
        while True:
            d = base / f"{run_stamp()}-{what}" if n == 1 else base / f"{run_stamp()}-{what}-{n}"
            try:
                d.mkdir(parents=True)
                return d
            except FileExistsError:
                n += 1

    def priv(self) -> Privileged:
        if self._priv is None:
            self._priv = Privileged()
        self._priv.start()
        return self._priv

    def close(self) -> None:
        if self._priv is not None:
            self._priv.close()


# ------------------------------------------------------------------------------------------------
# Steps


class Step:
    name = ""
    title = ""
    needs_admin = False

    def plan(self, ctx: Context) -> StepPlan:
        raise NotImplementedError

    def apply(self, ctx: Context, items: list[Item], out: Out) -> list[str]:
        """Apply the selected items; returns warnings."""
        return []


class CheckStep(Step):
    name, title = "check", "Check the backup and this machine"

    def plan(self, ctx: Context) -> StepPlan:
        p = StepPlan()
        s = ctx.t.read_summary()
        old_os = (ctx.info.get("os") or {}).get("pretty") or (s.get("machine") or {}).get("os", "?")
        old_host = (ctx.info.get("machine") or {}).get("hostname") or (s.get("machine") or {}).get("hostname", "?")
        p.notes.append(f"Backup of {ctx.old_user}@{old_host} ({old_os}), last backup {(s.get('last_run') or {}).get('finished', '?')}.")
        p.notes.append(f"This machine: {os.environ.get('USER', '')}@{os.uname().nodename} "
                       f"({os_release().get('PRETTY_NAME', '?')}).")
        size, files = ctx.m.tree_totals("home")
        p.notes.append(f"Home folder in the backup: {files:,} files, {human_size(size)}.")
        free = shutil.disk_usage(ctx.new_home).free
        if size > free:
            p.notes.append(f"WARNING: only {human_size(free)} is free here; you can restore part of the home folder.")
        if ctx.home_changed:
            p.notes.append(f"Your home folder moves from {ctx.old_home} to {ctx.new_home}; "
                           "paths inside settings files will be updated.")
        if not ctx.has_recipe:
            p.notes.append("This backup has no system recipe (it was a partial backup); only your files can be restored.")
        old_arch = (ctx.info.get("machine") or {}).get("arch")
        if old_arch and old_arch != os.uname().machine:
            p.notes.append(f"WARNING: the backup is from a {old_arch} machine; this one is {os.uname().machine}.")
        return p


DISTRO_SOURCE_FILES = {"ubuntu.sources", "ubuntu-esm-apps.sources", "ubuntu-esm-infra.sources"}


class ReposStep(Step):
    name, title, needs_admin = "repositories", "Software sources (apt repositories)", True

    def plan(self, ctx: Context) -> StepPlan:
        p = StepPlan()
        files = {f"sources.list.d/{n}": path for n, path in ctx.recipe_files("packages/apt/sources.list.d").items()}
        main = ctx.recipe_file("packages/apt/sources.list")
        if main:
            files["sources.list"] = main
        current_uris = _current_repo_uris()
        old_model = (ctx.info.get("machine") or {}).get("model", "")
        this_model = _dmi("product_name")
        candidates = []
        for rel, path in sorted(files.items()):
            name = rel.rsplit("/", 1)[-1]
            if not name.endswith((".list", ".sources")):
                continue
            try:
                repos = aptsources.parse(path.read_text(errors="replace"), name)
            except OSError:
                continue
            if name in DISTRO_SOURCE_FILES:
                continue  # the new system's own sources: never touched
            repos = [r for r in repos if r.enabled and r.kind != "ubuntu" and "deb" in r.types]
            if repos:
                candidates.append((name, repos))
        if any(r.kind == "ubuntu" for _, rs in candidates for r in rs) or files:
            p.notes.append("Ubuntu's own repositories are already set up by the installer and are not changed.")

        def check(entry):
            name, repos = entry
            suites = [[aptsources.map_suite(s, ctx.old_codename, ctx.new_codename) for s in r.suites] for r in repos]
            avail = [aptsources.available(r.uris[0], ss[0]) if ss else None for r, ss in zip(repos, suites)]
            return name, repos, suites, avail

        with ThreadPoolExecutor(max_workers=8) as pool:
            checked = list(pool.map(check, candidates))
        for name, repos, suites, avail in checked:
            r0 = repos[0]
            already = all(r.uris[0].rstrip("/") in current_uris for r in repos)
            content = "".join(aptsources.render(r, ss) for r, ss in zip(repos, suites))
            keys = self._keys(ctx, repos)
            if already:
                p.items.append(Item(name, r0.label, "already set up on this machine", False, False))
                continue
            state = ("available" if all(a is True for a in avail)
                     else "NOT available for this Ubuntu version" if any(a is False for a in avail)
                     else "could not check (offline?)")
            detail = f"{r0.uris[0]}  {' '.join(suites[0])}  — {state}"
            selected = all(a is not False for a in avail)
            if r0.kind == "oem":
                same = old_model and old_model == this_model
                detail += f"  (hardware-specific: {old_model or 'other model'})"
                selected = selected and bool(same)
            p.items.append(Item(name, r0.label, detail, selected, True,
                                {"file": "deucalion-" + (name if name != "sources.list" else "restored.list"),
                                 "content": content, "keys": keys}))
        return p

    @staticmethod
    def _keys(ctx: Context, repos) -> list[dict]:
        keys = []
        wanted = {r.signed_by for r in repos if r.signed_by and r.signed_by.startswith("/")}
        if not wanted:  # old-style: trusted by all keys in trusted.gpg.d
            wanted = {f"/etc/apt/trusted.gpg.d/{n}" for n in ctx.recipe_files("packages/apt/keys/etc/apt/trusted.gpg.d")}
        for k in sorted(wanted):
            path = ctx.recipe_file(f"packages/apt/keys{k}")
            if path:
                keys.append({"path": k, "data": base64.b64encode(path.read_bytes()).decode()})
        return keys

    def apply(self, ctx: Context, items: list[Item], out: Out) -> list[str]:
        warnings = []
        if not items:
            return warnings
        priv = ctx.priv()
        for it in items:
            try:
                priv.call("apt_add_source", filename=it.data["file"], content=it.data["content"], keys=it.data["keys"])
                out(f"Added {it.label}")
            except DeucalionError as e:
                warnings.append(f"{it.label}: {e}")
        out("Refreshing package lists (apt update)…")
        res = priv.call("apt_update", on_progress=out)
        if res.get("code"):
            warnings.append("apt update reported problems; some repositories may not work.")
        return warnings


class PackagesStep(Step):
    name, title, needs_admin = "packages", "Applications and packages", True
    SKIP_PREFIXES = ("linux-image", "linux-headers", "linux-modules", "linux-generic", "linux-oem",
                     "linux-firmware", "oem-", "nvidia-driver", "grub-", "shim-signed")

    def plan(self, ctx: Context) -> StepPlan:
        p = StepPlan()
        installed = _installed_packages()
        manual = [l.strip() for l in (ctx.read_text("packages/apt-manual.txt") or "").splitlines() if l.strip()]
        local = ctx.read_json("packages/apt-local.json") or []
        local_names = {x["package"] for x in local}
        missing = [m for m in manual if m not in installed and m not in local_names
                   and not m.startswith(self.SKIP_PREFIXES)]
        lists_empty = not any(Path("/var/lib/apt/lists").glob("*_Packages*"))
        if lists_empty:
            p.notes.append("This machine's package lists are empty (a new installation); they are refreshed "
                           "first, and any package that turns out not to exist is reported then.")
        candidates = _apt_candidates(missing) if not lists_empty else {m: True for m in missing}
        unavailable = []
        for pkg in missing:
            if candidates.get(pkg):
                p.items.append(Item(f"apt:{pkg}", pkg, "apt package", True, True, {"type": "apt", "name": pkg}))
            else:
                unavailable.append(pkg)
        if unavailable:
            p.items.append(Item("apt:unavailable", "Not available here", ", ".join(unavailable) +
                                " (add their repositories first, or they no longer exist)", False, False))
        skipped = [m for m in manual if m.startswith(self.SKIP_PREFIXES) and m not in installed]
        if skipped:
            p.notes.append(f"Hardware/kernel packages are left to the installer: {', '.join(skipped)}.")

        current_snaps = _current_snaps()
        for s in ctx.read_json("packages/snaps.json") or []:
            if s.get("dependency") or s["name"] in current_snaps:
                continue
            extra = " (classic)" if s.get("classic") else ""
            p.items.append(Item(f"snap:{s['name']}", s["name"], f"snap, {s.get('channel') or 'stable'}{extra}", True, True,
                                {"type": "snap", **s}))

        for x in local:
            if x["package"] in installed:
                continue
            files = [f for f in x.get("deb_files", []) if ctx.drive_path(f"home/{f}")]
            if files:
                p.items.append(Item(f"deb:{x['package']}", x["package"], f"from your downloaded file ~/{files[0]}",
                                    True, True, {"type": "deb", "path": str(ctx.drive_path(f'home/{files[0]}'))}))
            else:
                p.items.append(Item(f"deb:{x['package']}", x["package"],
                                    f"was installed from a downloaded .deb (version {x.get('version')}); "
                                    "download it again from its website", False, False))
        flat = (ctx.read_json("packages/flatpaks.json") or {}).get("apps", [])
        if flat:
            p.notes.append(f"Flatpak apps in the backup: {', '.join(a['id'] for a in flat)} "
                           "(install flatpak and add them from their remotes).")
        other = ctx.read_json("packages/other.json") or {}
        if other.get("npm_global"):
            p.notes.append(f"Global npm tools in the backup: {', '.join(other['npm_global'])}.")
        if other.get("pipx"):
            p.notes.append(f"pipx tools in the backup: {', '.join(other['pipx'])}.")
        manual_sw = ctx.read_json("software/manual-installs.json") or []
        if manual_sw:
            p.notes.append("Installed by hand (reinstall them yourself if you need them): "
                           + ", ".join(x["path"] for x in manual_sw[:15]) + (" …" if len(manual_sw) > 15 else ""))
        return p

    def apply(self, ctx: Context, items: list[Item], out: Out) -> list[str]:
        warnings = []
        if not items:
            return warnings
        priv = ctx.priv()
        apt = [i.data["name"] for i in items if i.data["type"] == "apt"]
        if apt:
            out("Refreshing package lists (apt update)…")
            priv.call("apt_update", on_progress=out)
            out(f"Installing {len(apt)} apt packages…")
            if priv.call("apt_install", packages=apt, on_progress=out).get("code"):
                out("Installing all at once failed; trying one by one…")
                for pkg in apt:
                    if priv.call("apt_install", packages=[pkg], on_progress=out).get("code"):
                        warnings.append(f"apt package {pkg} could not be installed.")
        for i in items:
            if i.data["type"] == "snap":
                out(f"Installing snap {i.label}…")
                if priv.call("snap_install", name=i.data["name"], channel=i.data.get("channel", ""),
                             classic=bool(i.data.get("classic")), on_progress=out).get("code"):
                    warnings.append(f"snap {i.label} could not be installed.")
            elif i.data["type"] == "deb":
                out(f"Installing {i.label} from {i.data['path']}…")
                if priv.call("apt_install_debs", paths=[i.data["path"]], on_progress=out).get("code"):
                    warnings.append(f"{i.label} could not be installed from its .deb file.")
        return warnings


class HomeStep(Step):
    name, title = "home", "Your home folder"

    def plan(self, ctx: Context) -> StepPlan:
        p = StepPlan()
        loose_size = loose_files = 0
        for name, e in sorted(ctx.m.children("home").items(), key=lambda kv: kv[0].lower()):
            if e.kind == "d":
                size, files = ctx.m.tree_totals(e.path)
                p.items.append(Item(e.path, name + "/", f"{files:,} files, {human_size(size)}", True, True, e.path))
            else:
                loose_size += e.size
                loose_files += 1
        if loose_files:
            p.items.insert(0, Item("home:files", "Files directly in your home folder",
                                   f"{loose_files:,} files, {human_size(loose_size)}", True, True, "files"))
        p.notes.append(f"Restores into {ctx.new_home}. Files that would be overwritten are first moved to "
                       f"~/{UNDO_DIRNAME}/. Close other apps before you continue.")
        return p

    def apply(self, ctx: Context, items: list[Item], out: Out, on_progress=None) -> list[str]:
        paths = []
        for i in items:
            if i.data == "files":
                paths += [e.path for e in ctx.m.children("home").values() if e.kind != "d"]
            else:
                paths.append(i.data)
        if not paths:
            return []
        r = Restorer(ctx.cfg, ctx.t, ctx.m, on_progress=on_progress, cancel=ctx.cancel, log=ctx.log,
                     equivalent=_after_path_update(ctx))
        plan = r.plan(paths)
        out(f"Restoring {plan.copy_files:,} files ({human_size(plan.copy_bytes)}); "
            f"{plan.count('overwrite'):,} existing files will be moved aside first…")
        res = r.execute(plan)
        if res.status == "cancelled":
            out("Stopped. Files restored so far stay; run this step again to finish.")
        if res.undo_dir:
            out(f"Replaced files are kept in {res.undo_dir}")
        out(f"Restored {res.restored_files:,} files.")
        return res.warnings


def _after_path_update(ctx: Context):
    """A local settings file that equals the backup's version with the home path updated (what the
    Paths step produces) counts as already restored, so running the rebuild again changes nothing."""
    if not ctx.home_changed:
        return None

    def same(local: Path, e) -> bool:
        if e.size > PathsStep.MAX_SIZE:
            return False
        src = ctx.t.root / e.stored
        try:
            return ctx.map_paths_bytes(src.read_bytes()) == local.read_bytes()
        except OSError:
            return False
    same.link = ctx.map_paths  # symlinks whose target was updated count as the same too
    return same


class PathsStep(Step):
    name, title = "paths", "Update paths in your settings (new home folder)"
    MAX_SIZE = 1024 * 1024

    def plan(self, ctx: Context) -> StepPlan:
        p = StepPlan()
        if not ctx.home_changed:
            p.notes.append("Your home folder path did not change; nothing to do.")
            return p
        home = Path(ctx.new_home)
        for e in ctx.m.iter_tree("home"):
            rel = e.path[len("home/"):] if e.path != "home" else ""
            if not rel or not (rel.startswith(".") or rel.endswith(".desktop")):
                continue
            path = home / rel
            if e.kind == "l":
                if not path.is_symlink():
                    continue
                current = os.readlink(path)
                if ctx.map_paths(current) != current:  # still points into the old home folder
                    p.items.append(Item(rel, f"~/{rel}", f"link → {current}", True, True, {"type": "link", "path": str(path)}))
            elif e.kind == "f" and e.size <= self.MAX_SIZE:
                try:
                    st = os.lstat(path)
                    if not stat.S_ISREG(st.st_mode):
                        continue  # e.g. now a symlink to a dotfiles repository: leave it alone
                    data = path.read_bytes()
                except OSError:
                    continue
                n = ctx.count_old_home(data)
                if n and b"\0" not in data[:4096]:
                    p.items.append(Item(rel, f"~/{rel}", f"{n} mention(s) of {ctx.old_home}", True, True,
                                        {"type": "file", "path": str(path)}))
        if not p.items:
            p.notes.append(f"No settings files mention {ctx.old_home}.")
        return p

    def apply(self, ctx: Context, items: list[Item], out: Out) -> list[str]:
        warnings = []
        if not items:
            return warnings
        undo = ctx.undo_dir("paths")
        for i in items:
            path = Path(i.data["path"])
            try:
                aside = undo / path.relative_to("/")
                aside.parent.mkdir(parents=True, exist_ok=True)
                st = os.lstat(path)
                if i.data["type"] == "link":
                    if not stat.S_ISLNK(st.st_mode):
                        raise OSError(errno.EEXIST, "it is not a link any more; left unchanged")
                    target = os.readlink(path)
                    os.symlink(target, aside)
                    tmp = path.with_name(f".{path.name[:100]}.deucalion-tmp")
                    os.symlink(ctx.map_paths(target), tmp)
                    os.replace(tmp, path)  # atomic: the link is never missing
                else:
                    if not stat.S_ISREG(st.st_mode) or st.st_nlink > 1:
                        raise OSError(errno.EEXIST, "it is a link or has other names now; left unchanged")
                    shutil.copy2(path, aside)
                    data = ctx.map_paths_bytes(path.read_bytes())
                    tmp = path.with_name(path.name + ".deucalion-tmp")
                    tmp.write_bytes(data)
                    os.chmod(tmp, st.st_mode & 0o7777)
                    os.utime(tmp, ns=(st.st_atime_ns, st.st_mtime_ns))
                    os.replace(tmp, path)
            except OSError as e:
                warnings.append(f"{path}: {e.strerror}")
        out(f"Updated {len(items) - len(warnings)} files (originals in {undo}).")
        return warnings


class DesktopStep(Step):
    name, title = "desktop", "Desktop settings (GNOME)"

    def plan(self, ctx: Context) -> StepPlan:
        p = StepPlan()
        text = ctx.read_text("desktop/dconf.ini")
        if not text:
            p.notes.append("The backup has no desktop settings.")
            return p
        if not shutil.which("dconf"):
            p.notes.append("This machine has no GNOME settings tool (dconf), so desktop settings can't be "
                           "loaded here. Install the 'dconf-cli' package (on a GNOME desktop) and run this step again.")
            return p
        sections = sum(1 for l in text.splitlines() if l.startswith("["))
        p.items.append(Item("dconf", "Load all desktop settings",
                            f"{sections} groups: wallpaper, dock, keyboard shortcuts, app settings…", True, True))
        ext = ctx.read_json("desktop/gnome-extensions.json") or {}
        if ext.get("enabled"):
            p.notes.append(f"GNOME extensions that were enabled: {', '.join(ext['enabled'])}. They are re-enabled "
                           "with the settings; ones not made for this GNOME version stay off.")
        old_gnome = (ctx.info.get("desktop") or {}).get("gnome", "")
        new_gnome = (_lines(["gnome-shell", "--version"]) or [""])[0]
        if old_gnome and new_gnome and old_gnome != new_gnome:
            p.notes.append(f"{old_gnome} → {new_gnome}: a few settings may no longer apply.")
        return p

    def apply(self, ctx: Context, items: list[Item], out: Out) -> list[str]:
        if not items:
            return []
        if not shutil.which("dconf"):
            return ["dconf is not installed here; desktop settings were not changed."]
        text = ctx.map_paths(ctx.read_text("desktop/dconf.ini") or "")
        current = subprocess.run(["dconf", "dump", "/"], capture_output=True, text=True)
        if current.returncode != 0:
            return ["The current desktop settings could not be saved first, so nothing was changed."]
        keep = ctx.undo_dir("desktop") / "dconf-before.ini"
        keep.write_text(current.stdout)
        out(f"Your current desktop settings are saved in {keep} (undo: dconf load / < that file)")
        res = subprocess.run(["dconf", "load", "/"], input=text, text=True, capture_output=True)
        if res.returncode != 0:
            return [f"Desktop settings could not be loaded: {res.stderr.strip()}"]
        out("Desktop settings loaded. Log out and back in to see all of them.")
        return []


# /etc files that are never restored automatically: they describe this specific installation.
ETC_REFERENCE_ONLY = {"/etc/passwd", "/etc/group", "/etc/subuid", "/etc/subgid", "/etc/fstab", "/etc/crypttab",
                      "/etc/hostname", "/etc/machine-id", "/etc/timezone", "/etc/locale.gen", "/etc/.updated"}
ETC_HANDLED_ELSEWHERE = ("/etc/apt/", "/etc/netplan/", "/etc/NetworkManager/", "/etc/pam.d/", "/etc/cloud/",
                         "/etc/initramfs-tools/", "/etc/default/grub")
ETC_SAFE = ("/etc/udev/rules.d/", "/etc/modprobe.d/", "/etc/sysctl.d/", "/etc/X11/xorg.conf.d/", "/etc/cups/",
            "/etc/environment", "/etc/security/limits.d/", "/etc/sudoers.d/")
RELOAD_FOR = {"/etc/udev/": "udev", "/etc/cups/": "cups", "/etc/apparmor.d/": "apparmor", "/etc/sysctl.d/": "sysctl",
              "/etc/systemd/": "systemd"}


class SystemConfigStep(Step):
    name, title, needs_admin = "system-config", "System settings (/etc)", True

    def plan(self, ctx: Context) -> StepPlan:
        p = StepPlan()
        changed = ctx.read_json("etc/changed.json") or []
        hidden = 0
        for it in changed:
            path = it["path"]
            if it.get("status") == "installer" or path in ETC_REFERENCE_ONLY or path.startswith(ETC_HANDLED_ELSEWHERE):
                hidden += 1
                continue
            src = ctx.recipe_file(f"etc/files{path}")
            if src is None:
                continue
            try:
                new = src.read_bytes()
                cur = Path(path).read_bytes() if os.access(path, os.R_OK) else None
            except OSError:
                cur = None
            exists = os.path.lexists(path)
            if cur is not None and cur == new:
                continue
            what = "new file" if not exists else "differs from this machine" if cur is not None else "exists (admin-only, can't compare)"
            detail = f"{it.get('status')}{' (' + it['package'] + ')' if it.get('package') else ''}, {what}"
            # Pre-selected only in well-understood places, and only when nothing would be overwritten
            # or it is a package's own config file you had changed.
            # ...and only where the program using it exists here (its folder is present).
            safe = path.startswith(ETC_SAFE) and (not exists or it.get("status") == "modified") \
                and os.path.isdir(os.path.dirname(path))
            p.items.append(Item(path, path, detail, safe, True,
                                {"src": str(src), "mode": it.get("mode", 0o644), "current": cur, "new": new,
                                 "owner": it.get("owner", ""), "group": it.get("group", "")}))
        if hidden:
            p.notes.append(f"{hidden} more files are kept in the backup for reference only (system identity, "
                           "disks, login, repositories and network are handled separately or by the installer).")
        return p

    @staticmethod
    def diff(item: Item) -> str:
        cur = (item.data.get("current") or b"").decode("utf-8", "replace").splitlines()
        new = (item.data.get("new") or b"").decode("utf-8", "replace").splitlines()
        return "\n".join(difflib.unified_diff(cur, new, f"{item.key} (this machine)", f"{item.key} (backup)", lineterm=""))

    def apply(self, ctx: Context, items: list[Item], out: Out) -> list[str]:
        warnings = []
        if not items:
            return warnings
        priv = ctx.priv()
        undo = f"/var/backups/deucalion/{run_stamp()}"
        reloads = set()
        for i in items:
            try:
                priv.call("put_etc_file", src=i.data["src"], dest=i.key, mode=i.data["mode"], undo_dir=undo,
                          owner=i.data.get("owner", ""), group=i.data.get("group", ""))
                out(f"Restored {i.key}")
                reloads |= {v for k, v in RELOAD_FOR.items() if i.key.startswith(k)}
            except DeucalionError as e:
                warnings.append(str(e))
        if reloads:
            priv.call("reload", what=sorted(reloads), on_progress=out)
        out(f"Previous versions of replaced files are in {undo}")
        return warnings


class ServicesStep(Step):
    name, title, needs_admin = "services", "Groups, scheduled tasks, services and network connections", True

    def plan(self, ctx: Context) -> StepPlan:
        p = StepPlan()
        # Groups
        old_groups = set((ctx.info.get("user") or {}).get("groups", []))
        user = os.environ.get("USER") or ctx.new_user
        cur_groups = set(((_lines(["id", "-Gn", user]) or [""])[0]).split())  # the group database, not this session
        existing = {l.split(":")[0] for l in Path("/etc/group").read_text().splitlines() if l}
        for g in sorted(old_groups - cur_groups - {ctx.old_user}):
            if g in existing:
                p.items.append(Item(f"group:{g}", f"Add you to the '{g}' group", _GROUP_HINTS.get(g, ""), True, True,
                                    {"type": "group", "group": g, "user": user}))
        # Crontabs
        cron = ctx.read_text("services/user-crontab.txt")
        if cron and not shutil.which("crontab"):
            p.notes.append("Your scheduled tasks (crontab) are in the backup, but cron is not installed here. "
                           "Install the 'cron' package and run this step again.")
            cron = None
        if cron:
            current = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
            if current.strip() != cron.strip():
                p.items.append(Item("cron:user", "Your scheduled tasks (crontab)",
                                    "replaces your current crontab" if current.strip() else f"{len(cron.splitlines())} lines",
                                    not current.strip(), True, {"type": "cron", "text": ctx.map_paths(cron)}))
        if ctx.recipe_file("services/root-crontab.txt"):
            p.items.append(Item("cron:root", "Administrator's scheduled tasks (root crontab)", "replaces root's crontab",
                                False, True, {"type": "rootcron", "src": str(ctx.recipe_file("services/root-crontab.txt"))}))
        # systemd units
        user_states = _unit_states(user=True)
        for u in (ctx.read_text("services/user-enabled.txt") or "").split():
            if user_states.get(u) == "disabled":
                p.items.append(Item(f"uunit:{u}", f"Enable your service {u}", "", True, True, {"type": "uunit", "unit": u}))
        sys_states = _unit_states(user=False)
        for u in (ctx.read_text("services/system-enabled.txt") or "").split():
            if sys_states.get(u) == "disabled":
                p.items.append(Item(f"unit:{u}", f"Enable system service {u}", "was enabled on the old machine", True, True,
                                    {"type": "unit", "unit": u}))
        # Network connections (only where NetworkManager runs)
        keyfiles = ctx.recipe_files("network/system-connections")
        if not shutil.which("nmcli"):
            if keyfiles or any(it["path"].startswith("/etc/netplan/90-NM-") for it in ctx.read_json("etc/changed.json") or []):
                p.notes.append("Wi-Fi/VPN connections are in the backup, but NetworkManager is not installed here; "
                               "they were left out.")
            return p
        current_nm = set(os.listdir("/etc/NetworkManager/system-connections")) if os.access(
            "/etc/NetworkManager/system-connections", os.R_OK) else set()
        for name, path in sorted(keyfiles.items()):
            if name not in current_nm:
                p.items.append(Item(f"nm:{name}", f"Network connection {name.rsplit('.', 1)[0]}", "Wi-Fi/VPN/wired", True, True,
                                    {"type": "nm", "src": str(path)}))
        for it in ctx.read_json("etc/changed.json") or []:
            path = it["path"]
            if path.startswith("/etc/netplan/90-NM-") and not os.path.exists(path):
                src = ctx.recipe_file(f"etc/files{path}")
                if src:
                    label = _netplan_name(src) or Path(path).name
                    p.items.append(Item(f"np:{path}", f"Network connection {label}", "Wi-Fi/VPN/wired", True, True,
                                        {"type": "netplan", "src": str(src)}))
        if (ctx.read_text("etc/collected-by.txt") or "").startswith("user"):
            p.notes.append("Network connections were not in the backup (it was made without administrator access).")
        return p

    def apply(self, ctx: Context, items: list[Item], out: Out) -> list[str]:
        """Each kind of item is applied on its own: one failing part doesn't stop the others."""
        warnings: list[str] = []
        by_type: dict[str, list[Item]] = {}
        for i in items:
            by_type.setdefault(i.data["type"], []).append(i)
        for kind in ("group", "cron", "rootcron", "uunit", "unit", "nm", "netplan"):
            if kind in by_type:
                try:
                    self._apply_kind(ctx, kind, by_type[kind], out, warnings)
                except (DeucalionError, OSError) as e:
                    warnings.append(f"{kind}: {e}")
        return warnings

    def _apply_kind(self, ctx: Context, kind: str, items: list[Item], out: Out, warnings: list[str]) -> None:
        by_type = {kind: items}
        if "group" in by_type:
            res = ctx.priv().call("add_groups", user=by_type["group"][0].data["user"],
                                  groups=[i.data["group"] for i in by_type["group"]])
            out(f"Added you to: {', '.join(res.get('added', []))} (takes effect after you log in again)")
        for i in by_type.get("cron", []):
            current = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
            if current.returncode == 0 and current.stdout.strip():
                keep = ctx.undo_dir("crontab") / "crontab-before.txt"
                keep.write_text(current.stdout)
                out(f"Your current crontab is saved in {keep}")
            r = subprocess.run(["crontab", "-"], input=i.data["text"], text=True, capture_output=True)
            if r.returncode:
                warnings.append(f"crontab: {r.stderr.strip()}")
            else:
                out("Restored your crontab")
        for i in by_type.get("rootcron", []):
            r = ctx.priv().call("put_crontab", user="root", src=i.data["src"],
                                undo_dir=f"/var/backups/deucalion/{run_stamp()}")
            out("Restored root's crontab" + (f" (the previous one is kept in {r['kept']})" if r.get("kept") else ""))
        if "uunit" in by_type:
            units = [i.data["unit"] for i in by_type["uunit"]]
            try:
                r = subprocess.run(["systemctl", "--user", "enable", *units], capture_output=True, text=True)
            except OSError as e:
                r = subprocess.CompletedProcess([], 1, "", str(e))
            if r.returncode:
                warnings.append(f"Could not enable {', '.join(units)}: {r.stderr.strip()}")
        if "unit" in by_type:
            ctx.priv().call("enable_units", units=[i.data["unit"] for i in by_type["unit"]], on_progress=out)
        if "nm" in by_type:
            r = ctx.priv().call("nm_import", files=[i.data["src"] for i in by_type["nm"]], on_progress=out)
            out(f"Imported {len(r.get('imported', []))} network connections")
        if "netplan" in by_type:
            r = ctx.priv().call("netplan_import", files=[i.data["src"] for i in by_type["netplan"]], on_progress=out)
            out(f"Imported {len(r.get('imported', []))} network connections")
        return warnings


_GROUP_HINTS = {
    "dialout": "serial ports and USB debug probes", "plugdev": "USB devices", "docker": "use Docker without sudo",
    "libvirt": "virtual machines", "kvm": "virtual machines", "vboxusers": "VirtualBox USB", "wireshark": "packet capture",
    "lpadmin": "manage printers", "sudo": "administrator rights",
}

STEPS: list[Step] = [CheckStep(), ReposStep(), PackagesStep(), HomeStep(), PathsStep(), DesktopStep(),
                     SystemConfigStep(), ServicesStep()]


# ------------------------------------------------------------------------------------------------
# Progress between sessions


def state_path() -> Path:
    return state_dir() / "rebuild.json"


def load_state(target: Target) -> dict:
    s = read_json(state_path(), {}) or {}
    if s.get("target") != target.id:
        s = {"target": target.id, "steps": {}}
    return s


def save_state(state: dict, step: str, status: str, warnings: list[str]) -> None:
    state.setdefault("steps", {})[step] = {"status": status, "when": now_iso(), "warnings": warnings}
    state_path().parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(state_path(), state)


# ------------------------------------------------------------------------------------------------
# Small helpers about this machine


def _lines(cmd: list[str]) -> list[str] | None:
    try:
        r = run(cmd)
    except Exception:
        return None
    return [l for l in r.stdout.splitlines() if l.strip()] if r.returncode == 0 else None


def _dmi(name: str) -> str:
    try:
        return Path(f"/sys/class/dmi/id/{name}").read_text().strip()
    except OSError:
        return ""


def _installed_packages() -> set[str]:
    out = set()
    for l in _lines(["dpkg-query", "-W", "-f", "${binary:Package}\t${db:Status-Abbrev}\n"]) or []:
        name, _, status = l.partition("\t")
        if status.startswith("ii"):
            out.add(name)
            out.add(name.split(":")[0])
    return out


def _apt_candidates(pkgs: list[str]) -> dict[str, bool]:
    out = {}
    for i in range(0, len(pkgs), 200):
        chunk = pkgs[i:i + 200]
        res = run(["apt-cache", "policy", *chunk], timeout=120)
        current = None
        for line in res.stdout.splitlines():
            if line and not line.startswith(" ") and line.endswith(":"):
                current = line[:-1]
                out[current] = False
            elif current and line.strip().startswith("Candidate:"):
                out[current] = line.split(":", 1)[1].strip() != "(none)"
    return out


def _current_snaps() -> set[str]:
    return {l.split()[0] for l in (_lines(["snap", "list", "--unicode=never", "--color=never"]) or [])[1:]}


def _unit_states(user: bool) -> dict[str, str]:
    cmd = ["systemctl"] + (["--user"] if user else []) + ["list-unit-files", "--no-legend", "--no-pager"]
    out = {}
    for l in _lines(cmd) or []:
        parts = l.split()
        if len(parts) >= 2:
            out[parts[0]] = parts[1]
    return out


def _current_repo_uris() -> set[str]:
    uris = set()
    files = [Path("/etc/apt/sources.list")] + list(Path("/etc/apt/sources.list.d").glob("*"))
    for f in files:
        if f.suffix in (".list", ".sources") or f.name == "sources.list":
            try:
                for r in aptsources.parse(f.read_text(errors="replace"), f.name):
                    uris |= {u.rstrip("/") for u in r.uris}
            except OSError:
                pass
    return uris


def _netplan_name(path: Path) -> str:
    try:
        for line in path.read_text(errors="replace").splitlines():
            s = line.strip()
            if s.startswith("name:"):
                return s.split(":", 1)[1].strip().strip('"')
    except OSError:
        pass
    return ""
