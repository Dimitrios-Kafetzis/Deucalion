"""The backup engine.

A backup runs in two phases:
  1. scan   - walk the selected folders, compare with the manifest, and build a
              plan (what to copy, what to move to _removed/, warnings). Nothing
              is written. This is also what --dry-run shows.
  2. copy   - carry out the plan. Old versions of changed files and files that
              no longer exist on the machine are moved to _removed/<run>/,
              never deleted.

The machine is only ever read. The engine never prints; it reports through a
progress callback so the CLI and the GUI can show it their own way.
"""

from __future__ import annotations

import errno
import grp
import hashlib
import json
import logging
import os
import pwd
import shutil
import socket
import sqlite3
import stat
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import __version__
from .config import INTERNAL_HOME_EXCLUDES, Config, Excluder, state_dir
from .manifest import Entry, Manifest
from .target import Target
from .util import DeucalionError, human_size, now_iso, os_release, run_stamp

ALL = "ALL"  # scope marker: the whole subtree
CHUNK = 4 * 1024 * 1024
SPARSE_MIN = 64 * 1024 * 1024
SPACE_MARGIN = 256 * 1024 * 1024

# Places in a home folder that hold keys, passwords or logged-in sessions.
SENSITIVE = [".ssh", ".gnupg", ".password-store", ".local/share/keyrings", ".mozilla",
             ".config/google-chrome", ".config/chromium", ".config/BraveSoftware", "snap/firefox"]


class Cancelled(Exception):
    pass


@dataclass
class Source:
    name: str      # logical prefix on the drive: 'home' or 'extras/<name>'
    origin: Path   # folder on this machine
    kind: str      # 'home' | 'folder'
    excluder: Excluder


def sources_from_config(cfg: Config) -> list[Source]:
    out = [Source("home", cfg.home, "home", Excluder(cfg.get("home_excludes", []) + INTERNAL_HOME_EXCLUDES))]
    for ef in cfg.get("extra_folders", []):
        out.append(Source(f"extras/{ef['name']}", Path(ef["path"]), "folder",
                          Excluder(ef.get("excludes", []))))
    return out


def build_scope(sources: list[Source], only: list[str] | None) -> dict:
    """Turn --only paths into a tree per source: {source: ALL | {name: subtree}}."""
    if not only:
        return {s.name: ALL for s in sources}
    scope: dict = {}
    for raw in only:
        p = Path(os.path.abspath(os.path.expanduser(raw)))
        best = None
        for s in sources:
            o = Path(os.path.abspath(s.origin))
            if p == o or o in p.parents:
                if best is None or len(str(o)) > len(str(best[1])):
                    best = (s, o)
        if best is None:
            raise DeucalionError(f"{raw} is not inside your home folder or a configured extra folder.")
        s, o = best
        parts = p.relative_to(o).parts
        if not parts:
            scope[s.name] = ALL
            continue
        node = scope.setdefault(s.name, {})
        if node is ALL:
            continue
        for i, part in enumerate(parts):
            if i == len(parts) - 1:
                node[part] = ALL
            else:
                child = node.setdefault(part, {})
                if child is ALL:
                    break
                node = child
    return scope


@dataclass
class Progress:
    phase: str = "scan"          # scan | copy | done
    files_done: int = 0
    files_total: int = 0
    bytes_done: int = 0
    bytes_total: int = 0
    current: str = ""
    started: float = field(default_factory=time.monotonic)

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started

    @property
    def rate(self) -> float:
        return self.bytes_done / self.elapsed if self.elapsed > 0.5 else 0.0

    @property
    def eta(self) -> float | None:
        if self.phase != "copy" or not self.rate:
            return None
        return max(self.bytes_total - self.bytes_done, 0) / self.rate


@dataclass(slots=True)
class Action:
    op: str                 # remove | mkdir | copy | record
    entry: Entry
    src: str | None = None
    replace: bool = False   # copy over an existing (older) stored file


class ActionStore:
    """Planned actions, kept in a temporary SQLite file instead of in memory:
    a first backup of a home folder can easily plan millions of files."""

    _COLS = "op, replace, path, stored, kind, mode, uid, gid, owner, grp, size, mtime_ns, link, sha256"

    def __init__(self, sources: list[Source]):
        d = state_dir() / "tmp"
        d.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix="plan-", suffix=".sqlite", dir=d)
        os.close(fd)
        self.path = Path(name)
        self.db = sqlite3.connect(name, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=OFF")
        self.db.execute("PRAGMA synchronous=OFF")
        self.db.execute(
            "CREATE TABLE a (seq INTEGER PRIMARY KEY, op TEXT, replace INTEGER, path BLOB, stored BLOB, "
            "kind TEXT, mode INTEGER, uid INTEGER, gid INTEGER, owner TEXT, grp TEXT, size INTEGER, "
            "mtime_ns INTEGER, link BLOB, sha256 TEXT)")
        self._buf: list[tuple] = []
        self._count = 0
        self._origins = sorted(((s.name, str(s.origin)) for s in sources), key=lambda x: -len(x[0]))

    def append(self, a: Action) -> None:
        e = a.entry
        self._buf.append((a.op, int(a.replace), os.fsencode(e.path), os.fsencode(e.stored), e.kind, e.mode,
                          e.uid, e.gid, e.owner, e.grp, e.size, e.mtime_ns,
                          None if e.link is None else os.fsencode(e.link), e.sha256))
        self._count += 1
        if len(self._buf) >= 10000:
            self._flush()

    def _flush(self) -> None:
        if self._buf:
            self.db.executemany(f"INSERT INTO a ({self._COLS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", self._buf)
            self.db.commit()
            self._buf.clear()

    def _src_of(self, path: str) -> str:
        for name, origin in self._origins:
            if path == name:
                return origin
            if path.startswith(name + "/"):
                return origin + path[len(name):]
        raise ValueError(path)

    def __len__(self) -> int:
        return self._count

    def __iter__(self):
        self._flush()
        for r in self.db.execute(f"SELECT {self._COLS} FROM a ORDER BY seq"):
            path = os.fsdecode(r[2])
            e = Entry(path, os.fsdecode(r[3]), r[4], r[5], r[6], r[7], r[8], r[9], r[10], r[11],
                      None if r[12] is None else os.fsdecode(r[12]), r[13])
            yield Action(r[0], e, self._src_of(path) if r[0] == "copy" else None, bool(r[1]))

    def close(self) -> None:
        try:
            self.db.close()
        finally:
            self.path.unlink(missing_ok=True)


@dataclass
class Plan:
    kind: str = "full"
    scope_text: str = ""
    removals: list[Action] = field(default_factory=list)
    actions: "ActionStore | list[Action]" = field(default_factory=list)
    new_files: int = 0
    changed_files: int = 0
    new_bytes: int = 0
    changed_bytes: int = 0
    copy_files: int = 0
    copy_bytes: int = 0
    unchanged_files: int = 0
    unchanged_bytes: int = 0
    removed_items: int = 0
    removed_bytes: int = 0
    replaced_bytes: int = 0   # old versions that will move to _removed/
    scanned_files: int = 0
    warnings: list[str] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    folders: dict[str, list[int]] = field(default_factory=dict)  # top folder -> [files, bytes]

    @property
    def selection_bytes(self) -> int:
        return self.copy_bytes + self.unchanged_bytes

    @property
    def nothing_to_do(self) -> bool:
        return not self.removals and len(self.actions) == 0

    def largest_folders(self, n: int = 10) -> list[tuple[str, int, int]]:
        """[(folder, files, bytes)] biggest first."""
        rows = [(k, v[0], v[1]) for k, v in self.folders.items()]
        return sorted(rows, key=lambda r: -r[2])[:n]

    def close(self) -> None:
        if isinstance(self.actions, ActionStore):
            self.actions.close()


def _uname(uid: int, cache: dict = {}) -> str:
    if uid not in cache:
        try:
            cache[uid] = pwd.getpwuid(uid).pw_name
        except KeyError:
            cache[uid] = ""
    return cache[uid]


def _gname(gid: int, cache: dict = {}) -> str:
    if gid not in cache:
        try:
            cache[gid] = grp.getgrgid(gid).gr_name
        except KeyError:
            cache[gid] = ""
    return cache[gid]


def _meta_differs(a: Entry, b: Entry) -> bool:
    return (a.mode, a.uid, a.gid, a.owner, a.grp) != (b.mode, b.uid, b.gid, b.owner, b.grp)


def _basename(p: str) -> str:
    return p.rsplit("/", 1)[-1]


class Scanner:
    def __init__(self, target: Target, manifest: Manifest, sources: list[Source], scope: dict,
                 on_progress: Callable[[Progress], None] | None = None,
                 cancel: threading.Event | None = None, check_drive: bool = False):
        self.t = target
        self.m = manifest
        self.policy = target.policy
        self.check_drive = check_drive  # also confirm each file is really on the drive (slower)
        self.sources = sources
        self.scope = scope
        self.cancel = cancel or threading.Event()
        self.on_progress = on_progress
        self.progress = Progress(phase="scan")
        self._last_report = 0.0
        st = os.stat(target.root)
        self._target_ident = (st.st_dev, st.st_ino)
        self.plan = Plan(actions=ActionStore(sources))
        self._src_name = ""

    # -- helpers ---------------------------------------------------------------------------
    def _report(self, current: str, force: bool = False) -> None:
        now = time.monotonic()
        if self.on_progress and (force or now - self._last_report > 0.1):
            self._last_report = now
            self.progress.current = current
            self.on_progress(self.progress)

    def _skip(self, path: str, reason: str) -> None:
        self.plan.skipped.append((path, reason))

    def _entry(self, path: str, stored: str, kind: str, st: os.stat_result, link: str | None = None) -> Entry:
        return Entry(path=path, stored=stored, kind=kind, mode=stat.S_IMODE(st.st_mode),
                     uid=st.st_uid, gid=st.st_gid, owner=_uname(st.st_uid), grp=_gname(st.st_gid),
                     size=st.st_size if kind == "f" else 0, mtime_ns=st.st_mtime_ns, link=link)

    def _drive_listing(self, stored_dir: str) -> set[str]:
        try:
            return set(os.listdir(self.t.root / stored_dir))
        except (FileNotFoundError, NotADirectoryError):
            return set()

    def _plan_remove(self, e: Entry) -> None:
        self.plan.removals.append(Action("remove", e))
        self.plan.removed_items += 1
        if e.kind == "f":
            self.plan.removed_bytes += e.size
        elif e.kind == "d":
            self.plan.removed_bytes += self.m.tree_totals(e.path)[0]

    def _plan_dir(self, prev: Entry | None, e: Entry, exists: bool) -> None:
        if prev is None or not exists:
            self.plan.actions.append(Action("mkdir", e))
        elif _meta_differs(prev, e) or prev.mtime_ns != e.mtime_ns:
            self.plan.actions.append(Action("record", e))

    def _plan_file(self, prev: Entry | None, e: Entry, src: str, st: os.stat_result, exists: bool) -> None:
        p = self.plan
        p.scanned_files += 1
        self.progress.files_total = p.scanned_files
        rel = e.path[len(self._src_name) + 1:]
        top = f"{self._src_name}/{rel.split('/', 1)[0]}" if "/" in rel else f"{self._src_name} (files)"
        stats = p.folders.setdefault(top, [0, 0])
        stats[0] += 1
        stats[1] += e.size
        if prev is not None and exists and prev.size == e.size and prev.mtime_ns == e.mtime_ns:
            p.unchanged_files += 1
            p.unchanged_bytes += e.size
            if _meta_differs(prev, e):
                e.sha256 = prev.sha256
                p.actions.append(Action("record", e))
            return
        replace = prev is not None and exists
        p.actions.append(Action("copy", e, src=src, replace=replace))
        p.copy_files += 1
        p.copy_bytes += e.size
        if replace:
            p.changed_files += 1
            p.changed_bytes += e.size
            p.replaced_bytes += prev.size
        else:
            p.new_files += 1
            p.new_bytes += e.size
        if e.size >= SPARSE_MIN and st.st_blocks * 512 < e.size // 2:
            p.warnings.append(
                f"{e.path}: sparse file; it uses {human_size(st.st_blocks * 512)} on this machine "
                f"but will take {human_size(e.size)} on the drive.")

    # -- scan ---------------------------------------------------------------------------------
    def scan(self) -> Plan:
        for src in self.sources:
            tree = self.scope.get(src.name)
            if tree is None:
                continue
            try:
                st = os.stat(src.origin)
            except OSError as e:
                self.plan.warnings.append(f"{src.origin}: cannot be read ({e.strerror}); skipped.")
                continue
            self._src_name = src.name
            root_entry = self._entry(src.name, src.name, "d", st)
            self._plan_dir(self.m.get(src.name), root_entry, (self.t.root / src.name).is_dir())
            self._walk(src, st.st_dev, tree)
        self._report("", force=True)
        return self.plan

    def _walk(self, src: Source, dev: int, tree) -> None:
        stack = [(str(src.origin), src.name, src.name, tree, "")]
        while stack:
            if self.cancel.is_set():
                raise Cancelled()
            abs_dir, L, S, tree, rel = stack.pop()
            self._report(L)
            try:
                with os.scandir(abs_dir) as it:
                    listing = list(it)
            except OSError as e:
                self._skip(L, f"cannot read folder ({e.strerror}); keeping what is already backed up")
                continue
            prev = self.m.children(L)
            current: dict[str, tuple[str, os.stat_result, str]] = {}
            keep: set[str] = set()

            for de in listing:
                name = de.name
                if tree is not ALL and name not in tree:
                    continue
                try:
                    st = de.stat(follow_symlinks=False)
                except OSError:
                    continue  # vanished while scanning
                mode = st.st_mode
                kind = "d" if stat.S_ISDIR(mode) else "f" if stat.S_ISREG(mode) else "l" if stat.S_ISLNK(mode) else None
                child_rel = f"{rel}/{name}" if rel else name
                child_L = f"{L}/{name}"
                if src.excluder.excluded(child_rel, name, kind == "d"):
                    if tree is not ALL:
                        self.plan.warnings.append(f"{child_L}: excluded by your exclusion rules; skipped.")
                        keep.add(name)
                    continue
                if tree is not ALL and tree[name] is not ALL and kind != "d":
                    self.plan.warnings.append(f"{child_L}: is not a folder any more; skipped.")
                    keep.add(name)
                    continue
                if kind is None:
                    self._skip(child_L, "special file (socket, pipe or device)")
                    continue
                if kind == "d":
                    if (st.st_dev, st.st_ino) == self._target_ident:
                        keep.add(name)
                        continue
                    if st.st_dev != dev:
                        self._skip(child_L, "another filesystem is mounted here; not followed")
                        keep.add(name)
                        continue
                current[name] = (de.path, st, kind)

            if tree is not ALL:
                for name, sub in tree.items():
                    if name not in current and name not in keep and not (sub is ALL and name in prev):
                        self.plan.warnings.append(f"{L}/{name}: not found on this machine; skipped.")

            # Things in the backup that are gone (or excluded) now. In a partial backup only
            # the exact folders/files that were asked for are mirrored this way.
            freed: set[str] = set()
            for name, pe in prev.items():
                if (tree is not ALL and tree.get(name) is not ALL) or name in keep:
                    continue
                cur = current.get(name)
                if cur is None or cur[2] != pe.kind:
                    self._plan_remove(pe)
                    if pe.kind != "l":
                        freed.add(self.policy.fold(_basename(pe.stored)))

            # Drive names: keep existing ones stable, choose new ones without clashes.
            # The drive folder is only listed when needed (it is slow on USB hard disks).
            stored_of: dict[str, str] = {}
            fresh = []
            for name, (_, _, kind) in current.items():
                pe = prev.get(name)
                if pe is not None and pe.kind == kind:
                    stored_of[name] = pe.stored
                else:
                    fresh.append(name)
            need_listing = self.check_drive or any(current[n][2] != "l" for n in fresh)
            on_drive = self._drive_listing(S) if need_listing else None
            used = {self.policy.fold(n) for n in on_drive or ()} - freed
            used |= {self.policy.fold(_basename(s)) for s in stored_of.values() if s}
            for name in sorted(fresh):
                stored_of[name] = "" if current[name][2] == "l" else f"{S}/{self.policy.choose(name, used)}"

            subdirs = []
            for name in sorted(current):
                path, st, kind = current[name]
                child_L = f"{L}/{name}"
                pe = prev.get(name)
                if pe is not None and pe.kind != kind:
                    pe = None
                stored = stored_of[name]
                exists = kind != "l" and pe is not None and (
                    _basename(stored) in on_drive if self.check_drive else True)
                if kind == "f":
                    self._plan_file(pe, self._entry(child_L, stored, "f", st), path, st, exists)
                elif kind == "l":
                    try:
                        target = os.readlink(path)
                    except OSError:
                        continue
                    e = self._entry(child_L, "", "l", st, link=target)
                    if pe is None or pe.link != e.link or _meta_differs(pe, e) or pe.mtime_ns != e.mtime_ns:
                        self.plan.actions.append(Action("record", e))
                else:
                    self._plan_dir(pe, self._entry(child_L, stored, "d", st), exists)
                    child_rel = f"{rel}/{name}" if rel else name
                    subdirs.append((path, child_L, stored, ALL if tree is ALL else tree[name], child_rel))
            stack.extend(reversed(subdirs))


class Executor:
    def __init__(self, target: Target, manifest: Manifest, plan: Plan, keep_overwritten: bool = True,
                 on_progress: Callable[[Progress], None] | None = None,
                 cancel: threading.Event | None = None, log: logging.Logger | None = None):
        self.t = target
        self.m = manifest
        self.plan = plan
        self.keep_overwritten = keep_overwritten
        self.on_progress = on_progress
        self.cancel = cancel or threading.Event()
        self.log = log or logging.getLogger("deucalion")
        self.stamp = run_stamp()
        self.removed_dir = target.removed_root / self.stamp
        self.posix = target.policy.kind == "posix"
        self.progress = Progress(phase="copy", files_total=plan.copy_files, bytes_total=plan.copy_bytes)
        self._last_report = 0.0
        self._tmp_counter = 0
        self.warnings: list[str] = []
        self.copied_files = 0
        self.copied_bytes = 0
        self.removed_items = 0

    def _report(self, force: bool = False) -> None:
        now = time.monotonic()
        if self.on_progress and (force or now - self._last_report > 0.1):
            self._last_report = now
            self.on_progress(self.progress)

    def _warn(self, msg: str) -> None:
        self.warnings.append(msg)
        self.log.warning(msg)

    def _move_to_removed(self, stored: str) -> None:
        src = self.t.root / stored
        dst = self.removed_dir / stored
        dst.parent.mkdir(parents=True, exist_ok=True)
        n = 2
        while os.path.lexists(dst):
            dst = dst.with_name(f"{(self.removed_dir / stored).name} ({n})")
            n += 1
        os.rename(src, dst)

    def run(self) -> None:
        shutil.rmtree(self.t.staging_dir, ignore_errors=True)
        self.t.staging_dir.mkdir(parents=True, exist_ok=True)
        try:
            for a in self.plan.removals:
                self._check_cancel()
                self._remove(a)
            for a in self.plan.actions:
                self._check_cancel()
                if a.op == "copy":
                    self._copy(a)
                elif a.op == "mkdir":
                    self._mkdir(a.entry)
                elif a.op == "record":
                    self.m.put(a.entry)
        finally:
            self.m.commit()
            shutil.rmtree(self.t.staging_dir, ignore_errors=True)
            os.sync()
            self.progress.phase = "done"
            self._report(force=True)

    def _check_cancel(self) -> None:
        if self.cancel.is_set():
            raise Cancelled()

    def _remove(self, a: Action) -> None:
        e = a.entry
        if e.kind != "l" and os.path.lexists(self.t.root / e.stored):
            self._move_to_removed(e.stored)
        self.m.delete_tree(e.path)
        self.removed_items += 1
        self.log.info("moved to _removed: %s", e.path)

    def _mkdir(self, e: Entry) -> None:
        d = self.t.root / e.stored
        if os.path.lexists(d) and not d.is_dir():
            self._move_to_removed(e.stored)
        d.mkdir(parents=True, exist_ok=True)
        if self.posix:
            os.chmod(d, e.mode & 0o7777 | 0o700)
        self.m.put(e)

    def _copy(self, a: Action) -> None:
        e = a.entry
        self.progress.current = e.path
        self._tmp_counter += 1
        tmp = self.t.staging_dir / f"{self._tmp_counter}.part"
        dest = self.t.root / e.stored
        planned = e.size
        copied = 0
        h = hashlib.sha256()
        try:
            with open(a.src, "rb") as fi, open(tmp, "wb") as fo:
                while True:
                    if self.cancel.is_set():
                        raise Cancelled()
                    buf = fi.read(CHUNK)
                    if not buf:
                        break
                    fo.write(buf)
                    h.update(buf)
                    copied += len(buf)
                    self.progress.bytes_done += len(buf)
                    self._report()
            os.utime(tmp, ns=(e.mtime_ns, e.mtime_ns))
            if self.posix:
                os.chmod(tmp, e.mode & 0o777 | 0o600)  # the real mode is in the manifest
            after = os.stat(a.src, follow_symlinks=False)
        except (Cancelled, KeyboardInterrupt):
            tmp.unlink(missing_ok=True)
            raise
        except OSError as err:
            tmp.unlink(missing_ok=True)
            if err.errno == errno.ENOSPC:
                raise DeucalionError("The backup drive is full. Free some space (for example "
                                     "empty _removed/ with: deucalion removed empty) and run again.") from None
            if err.errno == errno.ENOENT and err.filename == a.src:
                self.log.info("vanished before copy: %s", e.path)
            else:
                self._warn(f"{e.path}: could not be copied ({err.strerror}).")
            self.progress.bytes_done += planned - copied
            return

        if after.st_size != e.size or after.st_mtime_ns != e.mtime_ns:
            self._warn(f"{e.path}: changed while it was being copied; it will be copied again next time.")
            e.mtime_ns = -1
            e.size = copied
        self.progress.bytes_done += planned - copied  # keep the total consistent if the size changed
        dest.parent.mkdir(parents=True, exist_ok=True)
        if os.path.lexists(dest):
            if a.replace and not self.keep_overwritten:
                os.remove(dest) if not dest.is_dir() else shutil.rmtree(dest)
            else:
                self._move_to_removed(e.stored)
        os.replace(tmp, dest)
        e.sha256 = h.hexdigest()
        self.m.put(e)
        self.copied_files += 1
        self.copied_bytes += copied
        self.progress.files_done += 1
        self.log.info("copied: %s", e.path)


@dataclass
class RunResult:
    status: str               # completed | completed_with_warnings | cancelled | failed
    kind: str
    started: str
    finished: str
    duration: float
    copied_files: int
    copied_bytes: int
    removed_items: int
    warnings: list[str]
    skipped: list[tuple[str, str]]
    error: str | None = None


class BackupJob:
    """Scan + copy, as used by both the CLI and the GUI."""

    def __init__(self, cfg: Config, target: Target, only: list[str] | None = None,
                 on_progress: Callable[[Progress], None] | None = None,
                 cancel: threading.Event | None = None, log: logging.Logger | None = None,
                 check_drive: bool = False):
        self.cfg = cfg
        self.check_drive = check_drive
        self._plans: list[Plan] = []
        self.target = target
        self.only = only or []
        self.on_progress = on_progress
        self.cancel = cancel or threading.Event()
        self.log = log or logging.getLogger("deucalion")
        self.sources = sources_from_config(cfg)
        self.scope = build_scope(self.sources, self.only)
        self.manifest: Manifest | None = None

    @property
    def kind(self) -> str:
        return "partial" if self.only else "full"

    def prepare_system(self, privileged=None) -> list[str]:
        """Generate the system recipe and include it in this (full) backup. Returns warnings."""
        from .recipe import collect
        res = collect(self.cfg.home, privileged, self.log)
        self.sources.append(Source("system", res.folder, "recipe", Excluder([])))
        self.scope["system"] = ALL
        self.system_warnings = res.warnings
        return res.warnings

    def scan(self) -> Plan:
        self.target.check_filesystem()
        if self.manifest is None:
            self.manifest = self.target.manifest()
        scanner = Scanner(self.target, self.manifest, self.sources, self.scope,
                          self.on_progress, self.cancel, self.check_drive)
        self._plans.append(scanner.plan)
        plan = scanner.scan()
        plan.kind = self.kind
        plan.scope_text = ", ".join(self.only) if self.only else "everything"
        plan.warnings[:0] = getattr(self, "system_warnings", [])
        return plan

    def space_problem(self, plan: Plan) -> str | None:
        total = shutil.disk_usage(self.target.root).total
        needed = plan.copy_bytes + max(16 * 1024**2, min(SPACE_MARGIN, total // 50))
        if not self.cfg.get("keep_overwritten", True):
            needed -= plan.replaced_bytes
        free = self.target.free_bytes()
        if needed > free:
            return (f"Not enough space on the drive: this backup needs about {human_size(needed)} "
                    f"but only {human_size(free)} is free. You can free space by emptying "
                    "_removed/ (deucalion removed empty) or excluding large folders.")
        return None

    def identity_problem(self) -> str | None:
        """A warning if the drive holds a backup of a different machine, user or home folder."""
        s = self.target.read_summary()
        old_user, old_machine = s.get("user") or {}, s.get("machine") or {}
        if not old_user:
            return None
        old = (old_machine.get("hostname"), old_user.get("name"), old_user.get("home"))
        new = (socket.gethostname(), _uname(os.getuid()), str(self.cfg.home))
        if old == new:
            return None
        return (f"This drive holds the backup of {old[1]}@{old[0]} (home folder {old[2]}), but this is "
                f"{new[1]}@{new[0]} (home folder {new[2]}). Backing up will make the drive mirror this "
                "machine: anything that is only in the old backup will be moved to _removed/. "
                "If this is a new machine, restore your files first.")

    def sensitive_found(self) -> list[str]:
        home = self.cfg.home
        return [p for p in SENSITIVE if (home / p).exists()]

    def execute(self, plan: Plan) -> RunResult:
        assert self.manifest is not None, "scan() first"
        m = self.manifest
        started = now_iso()
        t0 = time.monotonic()
        for s in self.sources:
            if s.name in self.scope:
                m.set_source(s.name, str(s.origin), s.kind)
        m.set_meta("name_policy", self.target.policy.kind)
        run_id = m.start_run(plan.kind, started, plan.scope_text)
        ex = Executor(self.target, m, plan, self.cfg.get("keep_overwritten", True),
                      self.on_progress, self.cancel, self.log)
        status, error = "completed", None
        try:
            ex.run()
        except Cancelled:
            status = "cancelled"
        except DeucalionError as e:
            status, error = "failed", str(e)
        except Exception as e:  # unexpected: record it in the run history and the log
            status, error = "failed", f"{type(e).__name__}: {e}"
            self.log.exception("backup failed")
        warnings = plan.warnings + ex.warnings
        if status == "completed" and (warnings or plan.skipped):
            status = "completed_with_warnings"
        result = RunResult(status, plan.kind, started, now_iso(), time.monotonic() - t0,
                           ex.copied_files, ex.copied_bytes, ex.removed_items, warnings, plan.skipped, error)
        stats = {k: getattr(result, k) for k in ("copied_files", "copied_bytes", "removed_items")}
        stats["warnings"] = len(warnings)
        m.finish_run(run_id, result.finished, status, json.dumps(stats))
        self._write_summary(result)
        return result

    def _write_summary(self, r: RunResult) -> None:
        osr = os_release()
        summary = self.target.read_summary()
        summary.update({
            "tool": "Deucalion",
            "tool_version": __version__,
            "format": 1,
            "machine": {
                "hostname": socket.gethostname(),
                "os": osr.get("PRETTY_NAME", ""),
                "version_id": osr.get("VERSION_ID", ""),
                "kernel": os.uname().release,
            },
            "user": {"name": _uname(os.getuid()), "uid": os.getuid(), "home": str(self.cfg.home)},
            "sources": [{"name": s.name, "origin": str(s.origin)} for s in self.sources],
            "last_run": {
                "kind": r.kind, "started": r.started, "finished": r.finished, "status": r.status,
                "copied_files": r.copied_files, "copied_bytes": r.copied_bytes,
                "removed_items": r.removed_items, "warnings": len(r.warnings), "error": r.error,
            },
        })
        if r.kind == "full" and r.status.startswith("completed"):
            summary["last_full_backup"] = r.finished
        self.target.write_summary(summary)

    def close(self) -> None:
        for p in self._plans:
            p.close()
        self._plans.clear()
        if self.manifest is not None:
            self.manifest.close()
            self.manifest = None
