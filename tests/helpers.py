# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Dimitrios Kafetzis

import os
import shutil
import stat
import tempfile
import threading
import unittest
from pathlib import Path

from deucalion.backup import BackupJob
from deucalion.config import Config
from deucalion.restore import Restorer
from deucalion.target import Target


def snapshot(root: Path) -> dict:
    """Everything that matters about a tree: kinds, contents, link targets, modes, mtimes."""
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames + filenames:
            p = Path(dirpath) / name
            rel = os.fsencode(p.relative_to(root))
            st = os.lstat(p)
            if stat.S_ISLNK(st.st_mode):
                out[rel] = ("l", os.readlink(p))
            elif stat.S_ISDIR(st.st_mode):
                out[rel] = ("d", stat.S_IMODE(st.st_mode))
            else:
                out[rel] = ("f", stat.S_IMODE(st.st_mode), p.read_bytes(), st.st_mtime_ns)
    return out


class CountdownEvent(threading.Event):
    """A cancel flag that turns itself on after it has been checked `n` times."""

    def __init__(self, n: int | None):
        super().__init__()
        self.n = n

    def is_set(self) -> bool:
        if self.n is not None:
            self.n -= 1
            if self.n <= 0:
                self.set()
        return super().is_set()


class BackupTestCase(unittest.TestCase):
    """A fake home folder and a fake drive in a temp dir."""

    drive_dir: Path | None = None   # override to back up to a real exFAT mount
    name_policy = "exfat"

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="deucalion-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = self.tmp / "home" / "alice"
        self.home.mkdir(parents=True)
        drive_parent = self.drive_dir or self.tmp
        self.drive = Path(tempfile.mkdtemp(prefix="drive-", dir=drive_parent))
        self.addCleanup(shutil.rmtree, self.drive, True)
        os.environ["DEUCALION_CONFIG_DIR"] = str(self.tmp / "config")
        os.environ["DEUCALION_STATE_DIR"] = str(self.tmp / "state")
        self.cfg = Config.load()
        self.cfg["home_path"] = str(self.home)
        policy = None if self.drive_dir else self.name_policy
        self.target = Target.create(self.drive, name="TestDrive", allow_internal=True, name_policy=policy)
        self.target.register(self.cfg, allow_internal=True)

    # -- building the fake home --------------------------------------------------------------
    def write(self, rel: str, content: bytes | str = b"x", mode: int | None = None, mtime: int | None = None) -> Path:
        p = self.home / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content.encode() if isinstance(content, str) else content)
        if mode is not None:
            os.chmod(p, mode)
        if mtime is not None:
            os.utime(p, ns=(mtime, mtime))
        return p

    # -- running Deucalion -----------------------------------------------------------------------
    def backup(self, only=None, cancel_after_checks: int | None = None):
        cancel = CountdownEvent(None)
        job = BackupJob(self.cfg, self.target, only, cancel=cancel)
        try:
            plan = job.scan()
            cancel.n = cancel_after_checks
            result = job.execute(plan)
            plan.actions = list(plan.actions)  # keep them readable after the job is closed
        finally:
            job.close()
        return plan, result

    def dry_run(self, only=None):
        job = BackupJob(self.cfg, self.target, only)
        try:
            plan = job.scan()
            plan.actions = list(plan.actions)
            return plan
        finally:
            job.close()

    def restore(self, items, to=None):
        m = self.target.manifest()
        try:
            r = Restorer(self.cfg, self.target, m)
            plan = r.plan(items, to)
            return plan, r.execute(plan)
        finally:
            m.close()

    def stored_files(self) -> set[str]:
        out = set()
        for dirpath, dirnames, filenames in os.walk(self.target.root / "home"):
            for n in filenames:
                out.add(str((Path(dirpath) / n).relative_to(self.target.root)))
        return out

    def removed_files(self) -> set[str]:
        out = set()
        for dirpath, _, filenames in os.walk(self.target.removed_root):
            for n in filenames:
                rel = (Path(dirpath) / n).relative_to(self.target.removed_root)
                out.add(str(Path(*rel.parts[1:])))  # drop the run folder
        return out
