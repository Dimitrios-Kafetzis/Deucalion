# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Dimitrios Kafetzis

"""Restore files and folders from the backup.

Restoring is planned first (what will be created, what will be overwritten),
so the user can review it. Any local file that would be overwritten is first
moved to ~/Deucalion-before-restore/<time>/, so a restore can be undone.
"""

from __future__ import annotations

import errno
import hashlib
import logging
import os
import shutil
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .backup import CHUNK, Cancelled, Progress
from .config import Config
from .manifest import Entry, Manifest
from .target import Target
from .util import DeucalionError, run_stamp

UNDO_DIRNAME = "Deucalion-before-restore"


@dataclass(slots=True)
class RestoreItem:
    op: str        # mkdir | create | overwrite | same | missing
    entry: Entry
    dest: Path


@dataclass
class RestorePlan:
    items: list[RestoreItem] = field(default_factory=list)
    roots: list[tuple[str, Path]] = field(default_factory=list)  # (logical, destination)
    copy_bytes: int = 0
    copy_files: int = 0

    def count(self, op: str) -> int:
        return sum(1 for i in self.items if i.op == op)

    def of(self, op: str) -> list[RestoreItem]:
        return [i for i in self.items if i.op == op]


@dataclass
class RestoreResult:
    status: str                 # completed | completed_with_warnings | cancelled
    restored_files: int
    restored_bytes: int
    undo_dir: Path | None
    warnings: list[str]


class Restorer:
    def __init__(self, cfg: Config, target: Target, manifest: Manifest,
                 on_progress: Callable[[Progress], None] | None = None,
                 cancel: threading.Event | None = None, log: logging.Logger | None = None,
                 equivalent: Callable | None = None):
        self.cfg = cfg
        self.equivalent = equivalent   # optional: (local path, entry) -> True if it counts as the same
        self.t = target
        self.m = manifest
        self.on_progress = on_progress
        self.cancel = cancel or threading.Event()
        self.log = log or logging.getLogger("deucalion")
        self.is_root = os.geteuid() == 0
        # source name -> (origin on the old machine, where it goes on this machine)
        self.sources: dict[str, tuple[str, Path | None]] = {}
        for name, (origin, kind) in self.m.sources().items():
            here = self.cfg.home if kind == "home" else None if kind == "recipe" else Path(origin)
            self.sources[name] = (origin, here)

    # -- resolving what the user asked for ------------------------------------------------------
    def resolve(self, arg: str) -> tuple[str, Path]:
        """Map a user argument to (logical path, default destination)."""
        clean = arg.rstrip("/")
        if not clean.startswith(("/", "~", ".")) and self.m.get(clean) is not None:
            logical = clean
        else:
            p = Path(os.path.abspath(os.path.expanduser(arg)))
            best = None
            for name, (origin, here) in self.sources.items():
                for base in {Path(origin), here} - {None}:
                    if p == base or base in p.parents:
                        if best is None or len(str(base)) > len(str(best[1])):
                            best = (name, base)
            if best is None:
                raise DeucalionError(f"{arg} is not part of the backup.")
            name, base = best
            rel = p.relative_to(base).as_posix()
            logical = name if rel == "." else f"{name}/{rel}"
            if self.m.get(logical) is None:
                raise DeucalionError(f"{arg} is not in the backup.")
        return logical, self.default_destination(logical)

    def default_destination(self, logical: str) -> Path:
        for name, (_, here) in sorted(self.sources.items(), key=lambda kv: -len(kv[0])):
            if here is None and (logical == name or logical.startswith(name + "/")):
                return Path.cwd() / "deucalion-system" / logical[len(name):].lstrip("/")
            if logical == name:
                return here
            if logical.startswith(name + "/"):
                return here / logical[len(name) + 1:]
        raise DeucalionError(f"{logical} does not belong to a known backup source.")

    # -- planning ----------------------------------------------------------------------------------------
    def plan(self, args: list[str], to: Path | None = None) -> RestorePlan:
        plan = RestorePlan()
        roots: dict[str, Path] = {}
        for arg in args:
            logical, dest = self.resolve(arg)
            if to is not None:
                dest = Path(to).expanduser().absolute() / dest.name
            roots.setdefault(logical, dest)
        # An item inside another chosen folder is restored with that folder.
        chosen = {l: d for l, d in roots.items()
                  if not any(l != o and (o == "" or l.startswith(o + "/")) for o in roots)}
        dests: dict[Path, str] = {}
        for logical, dest in chosen.items():
            other = next((l for d, l in dests.items() if d == dest or dest in d.parents or d in dest.parents), None)
            if other is not None:
                raise DeucalionError(f"“{logical}” and “{other}” would be restored to the same place ({dest}). "
                                     "Restore them separately, or into different folders.")
            dests[dest] = logical
        for logical, dest in chosen.items():
            plan.roots.append((logical, dest))
            for e in self.m.iter_tree(logical):
                d = dest if e.path == logical else dest / e.path[len(logical) + 1:]
                plan.items.append(self._decide(e, d))
        for i in plan.items:
            if i.op in ("create", "overwrite") and i.entry.kind == "f":
                plan.copy_files += 1
                plan.copy_bytes += i.entry.size
        return plan

    def _decide(self, e: Entry, dest: Path) -> RestoreItem:
        exists = os.path.lexists(dest)
        if e.kind == "d":
            if exists and dest.is_dir() and not dest.is_symlink():
                return RestoreItem("same", e, dest)
            return RestoreItem("overwrite" if exists else "mkdir", e, dest)
        if e.kind == "f":
            if not (self.t.root / e.stored).is_file():
                return RestoreItem("missing", e, dest)
            if exists:
                try:
                    st = os.lstat(dest)
                except OSError:
                    st = None
                if st and os.path.isfile(dest) and not dest.is_symlink() \
                        and st.st_size == e.size and st.st_mtime_ns == e.mtime_ns and self._same_content(dest, e):
                    return RestoreItem("same", e, dest)
                if st and self.equivalent and os.path.isfile(dest) and not dest.is_symlink() \
                        and self.equivalent(dest, e):
                    return RestoreItem("same", e, dest)
                return RestoreItem("overwrite", e, dest)
            return RestoreItem("create", e, dest)
        # symlink
        if exists and dest.is_symlink() and os.readlink(dest) == e.link:
            return RestoreItem("same", e, dest)
        if exists and dest.is_symlink() and self.equivalent and getattr(self.equivalent, "link", None) \
                and os.readlink(dest) == self.equivalent.link(e.link):
            return RestoreItem("same", e, dest)
        return RestoreItem("overwrite" if exists else "create", e, dest)

    @staticmethod
    def _same_content(path: Path, e: Entry) -> bool:
        """Same size and time is not proof: a program can change a file and put its time back."""
        if not e.sha256:
            return True
        h = hashlib.sha256()
        try:
            with open(path, "rb") as f:
                while buf := f.read(CHUNK):
                    h.update(buf)
        except OSError:
            return False
        return h.hexdigest() == e.sha256

    # -- doing it -----------------------------------------------------------------------------------------
    def execute(self, plan: RestorePlan) -> RestoreResult:
        undo_root = self.cfg.home / UNDO_DIRNAME / run_stamp()
        progress = Progress(phase="restore", files_total=plan.copy_files, bytes_total=plan.copy_bytes)
        warnings: list[str] = []
        made_dirs: list[RestoreItem] = []
        restored_files = restored_bytes = 0
        used_undo = False
        last = 0.0

        def report(force=False):
            nonlocal last
            if self.on_progress and (force or time.monotonic() - last > 0.1):
                last = time.monotonic()
                self.on_progress(progress)

        stamp = undo_root.name
        set_aside: list[str] = []

        def move_aside(path: Path) -> Path:
            """Set the current version aside by RENAMING it (never copy-then-delete). Raises if that
            is not possible; then nothing was changed."""
            nonlocal used_undo
            if os.path.ismount(path):
                raise OSError(errno.EBUSY, "a drive is mounted here; it was left untouched")
            aside = undo_root / str(path).lstrip("/")
            n = 2
            while os.path.lexists(aside):  # never replace something already kept
                aside = aside.with_name(f"{path.name} ({n})")
                n += 1
            try:
                aside.parent.mkdir(parents=True, exist_ok=True)
                os.rename(path, aside)
                used_undo = True
            except OSError:
                # Another disk, or no permission there: keep it next to the original instead.
                aside = path.with_name(f"{path.name}.before-restore-{stamp}")
                n = 2
                while os.path.lexists(aside):
                    aside = path.with_name(f"{path.name}.before-restore-{stamp} ({n})")
                    n += 1
                os.rename(path, aside)
                set_aside.append(str(aside))
            self.log.info("moved aside: %s -> %s", path, aside)
            return aside

        replaced_dirs: list[str] = []   # e.g. a link to a folder that was set aside: restore what was "inside"
        status = "completed"
        try:
            for item in plan.items:
                if self.cancel.is_set():
                    raise Cancelled()
                e, dest = item.entry, item.dest
                if item.op == "same" and not any(str(dest).startswith(m + "/") for m in replaced_dirs):
                    continue
                if item.op == "missing":
                    warnings.append(f"{e.path}: missing on the drive; not restored.")
                    continue
                progress.current = str(dest)
                moved = False
                aside = None
                try:
                    # Check again now: something may have appeared here since the plan was made.
                    is_dir_now = dest.is_dir() and not dest.is_symlink()
                    if os.path.lexists(dest) and not (e.kind == "d" and is_dir_now):
                        aside = move_aside(dest)
                        moved = True
                        if e.kind == "d":
                            replaced_dirs.append(str(dest))
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    if e.kind == "d":
                        dest.mkdir(exist_ok=True)
                        made_dirs.append(item)
                    elif e.kind == "l":
                        os.symlink(e.link, dest)
                        self._apply_owner(dest, e)
                        try:
                            os.utime(dest, ns=(e.mtime_ns, e.mtime_ns), follow_symlinks=False)
                        except (OSError, NotImplementedError):
                            pass
                    else:
                        ok = self._copy(e, dest, progress, report, warnings)
                        if not ok and aside is not None and not os.path.lexists(dest):
                            os.rename(aside, dest)  # the copy failed: put the original back
                            aside, moved = None, False
                        if ok:
                            restored_files += 1
                            restored_bytes += e.size
                        progress.files_done += 1
                except BaseException as err:
                    # Interrupted or failed before the restored copy was in place: put the original back.
                    if aside is not None and not os.path.lexists(dest):
                        try:
                            os.rename(aside, dest)
                            moved = False
                        except OSError:
                            pass
                    if not isinstance(err, OSError):
                        raise
                    warnings.append(f"{dest}: not restored ({err.strerror})"
                                    + ("; the version that was there has been kept (see above)." if moved else
                                       "; what is there was left untouched."))
                report()
        except Cancelled:
            status = "cancelled"
        finally:
            # Folder permissions and times last, deepest first, so a read-only
            # folder doesn't block restoring what is inside it.
            for item in reversed(made_dirs):
                self._apply_owner(item.dest, item.entry)
                try:
                    os.chmod(item.dest, item.entry.mode & 0o7777)
                    os.utime(item.dest, ns=(item.entry.mtime_ns, item.entry.mtime_ns))
                except OSError as err:
                    warnings.append(f"{item.dest}: could not set permissions ({err.strerror}).")
            progress.phase = "done"
            report(force=True)
        if set_aside:
            warnings.insert(0, "Some files could not go to the undo folder and were kept next to their "
                               "original place instead: " + ", ".join(set_aside[:20])
                            + (" …" if len(set_aside) > 20 else ""))
        if status == "completed" and warnings:
            status = "completed_with_warnings"
        return RestoreResult(status, restored_files, restored_bytes, undo_root if used_undo else None, warnings)

    def _apply_owner(self, path: Path, e: Entry) -> None:
        if not self.is_root:
            return
        try:
            os.chown(path, e.uid, e.gid, follow_symlinks=False)
        except OSError:
            pass

    def _copy(self, e: Entry, dest: Path, progress: Progress, report, warnings: list[str]) -> bool:
        src = self.t.root / e.stored
        self._tmp_n = getattr(self, "_tmp_n", 0) + 1
        tmp = dest.with_name(f".deucalion-restore-{os.getpid()}-{self._tmp_n}")
        h = hashlib.sha256()
        copied = 0
        try:
            with open(src, "rb") as fi, open(tmp, "wb") as fo:
                while True:
                    if self.cancel.is_set():
                        raise Cancelled()
                    buf = fi.read(CHUNK)
                    if not buf:
                        break
                    fo.write(buf)
                    h.update(buf)
                    copied += len(buf)
                    progress.bytes_done += len(buf)
                    report()
            os.chmod(tmp, e.mode & 0o7777)
            if e.mtime_ns >= 0:
                os.utime(tmp, ns=(e.mtime_ns, e.mtime_ns))
            self._apply_owner(tmp, e)
            os.replace(tmp, dest)
        except OSError as err:
            _unlink_quietly(tmp)
            warnings.append(f"{dest}: could not be restored ({err.strerror}); what was there is unchanged.")
            return False
        except BaseException:  # stopped (Ctrl+C, Stop button): remove the half-written copy
            _unlink_quietly(tmp)
            raise
        if e.sha256 and h.hexdigest() != e.sha256:
            warnings.append(f"{dest}: restored, but its content does not match the checksum recorded "
                            "at backup time. The copy on the drive may be damaged.")
        self.log.info("restored: %s", dest)
        return True


def _unlink_quietly(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
