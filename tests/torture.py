#!/usr/bin/env python3
"""Randomized torture test of Deucalion's data-safety guarantees.

It builds a random home folder full of awkward cases (odd names, case twins, symlinks,
permissions, big and empty files), then for many rounds: mutates it randomly, backs it up
(sometimes partially, sometimes killing the process at a random moment), restores into a
modified copy (sometimes killing that too), and after every step checks:

  I1  a backup never changes anything in the source (content, mode, times, links)
  I2  after a full backup, a restore reproduces the source exactly
  I3  every file content that was ever in a completed backup is still on the drive
      (in the mirror or in _removed/): nothing backed up is ever lost
  I4  `verify --full` passes and the manifest database is intact
  I5  the drive holds no untracked files in the mirror
  R1  a restore never loses a local file: each one is untouched or in the undo folder
  R2  restored files equal what the backup recorded

Usage:
  python3 tests/torture.py --drive /media/$USER/SOMEDRIVE --rounds 50 --seed 1 [--kill]
The drive folder must be a mounted filesystem you can write to (a test disk image).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import shutil
import signal
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from deucalion.backup import BackupJob  # noqa: E402
from deucalion.config import Config  # noqa: E402
from deucalion.restore import UNDO_DIRNAME, Restorer  # noqa: E402
from deucalion.target import Target  # noqa: E402
from deucalion.verify import verify  # noqa: E402

FILE_MODES = [0o600, 0o644, 0o755, 0o444, 0o400, 0o640]
DIR_MODES = [0o700, 0o755, 0o750]


class Failure(Exception):
    pass


# ------------------------------------------------------------------------------------------------
# Random names and trees


def rand_name(rng: random.Random, siblings: set[str]) -> str:
    style = rng.random()
    word = "".join(rng.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(rng.randint(1, 10)))
    if style < 0.35:
        name = word + rng.choice(["", ".txt", ".pdf", ".tar.gz", ".JPG", ".c"])
    elif style < 0.45:
        name = rng.choice(["Report", "Notes", "IMG", "Readme"]) + rng.choice(["", ".txt"])
    elif style < 0.52:
        name = word + rng.choice([":", "?", "*", '"', "<", ">", "|", "\\"]) + word
    elif style < 0.57:
        name = word + rng.choice([".", "..", " ", ". "])
    elif style < 0.62:
        name = rng.choice(["αρχείο", "Ελληνικά έγγραφα", "日本語", "emoji😀", "ünïcødé", "Ñandú"]) + str(rng.randint(0, 99))
    elif style < 0.65:
        name = rng.choice(["CON", "nul.txt", "AUX.log", "com1"])
    elif style < 0.69:
        name = rng.choice(["α", "b", "ü"]) * rng.randint(60, 120)  # long, multibyte names
        while len(os.fsencode(name)) > 250:
            name = name[:-1]
    elif style < 0.72:
        name = os.fsdecode(b"bad\xff" + word.encode())  # not valid UTF-8
    elif style < 0.78 and siblings:
        base = rng.choice(sorted(siblings))
        name = base.swapcase() if base.swapcase() != base else base.upper() + "x"  # case twin
    elif style < 0.83:
        name = " " + word
    else:
        name = "." + word
    if name in (".", "..") or "/" in name or "\0" in name:
        name = word
    while name in siblings:
        name += "_"
    return name


def rand_content(rng: random.Random) -> bytes:
    r = rng.random()
    if r < 0.1:
        return b""
    if r < 0.7:
        return rng.randbytes(rng.randint(1, 200))
    if r < 0.97:
        return rng.randbytes(rng.randint(1000, 30000))
    return rng.randbytes(rng.randint(300_000, 2_000_000))


def populate(rng: random.Random, home: Path, n_dirs: int = 80, n_files: int = 1500) -> None:
    dirs = [home]
    for _ in range(n_dirs):
        parent = rng.choice(dirs)
        d = parent / rand_name(rng, set(os.listdir(parent)))
        try:
            d.mkdir()
            dirs.append(d)
        except OSError:
            pass
    for _ in range(n_files):
        d = rng.choice(dirs)
        try:
            p = d / rand_name(rng, set(os.listdir(d)))
            p.write_bytes(rand_content(rng))
            os.chmod(p, rng.choice(FILE_MODES))
        except OSError:
            pass
    for d in dirs[1:]:
        os.chmod(d, rng.choice(DIR_MODES))


def entries(root: Path) -> tuple[list[Path], list[Path], list[Path]]:
    files, dirs, links = [], [], []
    for dirpath, dnames, fnames in os.walk(root):
        for n in dnames + fnames:
            p = Path(dirpath) / n
            st = os.lstat(p)
            if stat.S_ISLNK(st.st_mode):
                links.append(p)
            elif stat.S_ISDIR(st.st_mode):
                dirs.append(p)
            else:
                files.append(p)
    return files, dirs, links


def mutate(rng: random.Random, home: Path, n: int) -> None:
    for _ in range(n):
        files, dirs, links = entries(home)
        alldirs = [home] + dirs
        op = rng.random()
        try:
            if op < 0.25 or not files:
                d = rng.choice(alldirs)
                p = d / rand_name(rng, set(os.listdir(d)))
                p.write_bytes(rand_content(rng))
                os.chmod(p, rng.choice(FILE_MODES))
            elif op < 0.33:
                d = rng.choice(alldirs)
                p = d / rand_name(rng, set(os.listdir(d)))
                p.mkdir()
                os.chmod(p, rng.choice(DIR_MODES))
            elif op < 0.38:
                d = rng.choice(alldirs)
                target = rng.choice([str(rng.choice(files)), "relative/path", "../up", "/nonexistent"]) if files else "x"
                os.symlink(target, d / rand_name(rng, set(os.listdir(d))))
            elif op < 0.50:
                p = rng.choice(files)
                os.chmod(p, 0o644)
                with open(p, "ab" if rng.random() < 0.5 else "wb") as f:
                    f.write(rand_content(rng))
                os.chmod(p, rng.choice(FILE_MODES))
            elif op < 0.56:  # sneaky edit: same size, modification time put back
                p = rng.choice(files)
                st = p.stat()
                if st.st_size:
                    os.chmod(p, 0o644)
                    p.write_bytes(rng.randbytes(st.st_size))
                    os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns))
                    os.chmod(p, stat.S_IMODE(st.st_mode))
            elif op < 0.64:
                rng.choice(files + links).unlink()
            elif op < 0.68 and dirs:
                shutil.rmtree(rng.choice(dirs))
            elif op < 0.76:
                src = rng.choice(files + dirs + links)
                d = rng.choice(alldirs)
                if src.is_dir() and not src.is_symlink() and (d == src or src in d.parents):
                    continue
                os.rename(src, d / rand_name(rng, set(os.listdir(d))))
            elif op < 0.80:  # case-only rename
                p = rng.choice(files + dirs)
                new = p.with_name(p.name.swapcase())
                if new != p and not os.path.lexists(new):
                    os.rename(p, new)
            elif op < 0.83:  # file becomes folder
                p = rng.choice(files)
                p.unlink()
                p.mkdir()
                (p / "inside.txt").write_bytes(rand_content(rng))
            elif op < 0.85 and dirs:  # folder becomes file
                p = rng.choice(dirs)
                shutil.rmtree(p)
                p.write_bytes(rand_content(rng))
            elif op < 0.92:
                p = rng.choice(files + dirs)
                os.chmod(p, rng.choice(DIR_MODES if p.is_dir() else FILE_MODES))
            elif op < 0.96:
                p = rng.choice(files)
                t = rng.randint(1_000_000_000, 1_800_000_000) * 10**9 + rng.randint(0, 10**9 - 1)
                os.utime(p, ns=(t, t))
            elif links:
                p = rng.choice(links)
                p.unlink()
                os.symlink(rng.choice(["new/target", "/etc/hostname", "../x"]), p)
        except OSError:
            pass  # e.g. a name too long after renaming; harmless for the test


# ------------------------------------------------------------------------------------------------
# Snapshots and checks


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while buf := f.read(1 << 20):
            h.update(buf)
    return h.hexdigest()


def snapshot(root: Path, with_ctime: bool) -> dict:
    snap = {}
    for dirpath, dnames, fnames in os.walk(root):
        for n in dnames + fnames:
            p = Path(dirpath) / n
            rel = os.fsencode(p.relative_to(root))
            st = os.lstat(p)
            if stat.S_ISLNK(st.st_mode):
                snap[rel] = ("l", os.readlink(p))
            elif stat.S_ISDIR(st.st_mode):
                snap[rel] = ("d", stat.S_IMODE(st.st_mode))
            else:
                snap[rel] = ("f", stat.S_IMODE(st.st_mode), sha(p), st.st_mtime_ns) + ((st.st_ctime_ns,) if with_ctime else ())
    return snap


def hashes_under(*roots: Path) -> set[str]:
    out = set()
    for root in roots:
        if root.exists():
            for dirpath, _, fnames in os.walk(root):
                for n in fnames:
                    p = Path(dirpath) / n
                    if not p.is_symlink():
                        out.add(sha(p))
    return out


def diff(a: dict, b: dict, limit: int = 8) -> str:
    out = []
    for k in sorted(set(a) | set(b)):
        if a.get(k) != b.get(k):
            out.append(f"  {k!r}: {a.get(k)} != {b.get(k)}")
            if len(out) >= limit:
                break
    return "\n".join(out)


class Harness:
    def __init__(self, drive: Path, seed: int, work: Path, verbose: bool):
        self.rng = random.Random(seed)
        self.seed = seed
        self.work = work
        self.verbose = verbose
        self.home = work / "home" / "tester"
        self.home.mkdir(parents=True)
        os.environ["DEUCALION_CONFIG_DIR"] = str(work / "config")
        os.environ["DEUCALION_STATE_DIR"] = str(work / "state")
        self.cfg = Config.load()
        self.cfg["home_path"] = str(self.home)
        self.cfg["home_excludes"] = ["skipme/"]
        self.cfg.save()
        self.drive_dir = Path(tempfile.mkdtemp(prefix=f"torture-{seed}-", dir=drive))
        self.target = Target.create(self.drive_dir, name="Torture", allow_internal=True)
        self.target.register(self.cfg, allow_internal=True)
        self.history: set[str] = set()
        self.stats = {"backups": 0, "partial": 0, "killed_backups": 0, "restores": 0, "killed_restores": 0,
                      "sneaky": 0, "checks": 0}

    def log(self, msg: str) -> None:
        if self.verbose:
            print(msg, flush=True)

    # -- running Deucalion ------------------------------------------------------------------------------
    def backup(self, only=None):
        job = BackupJob(self.cfg, self.target, only)
        try:
            plan = job.scan()
            res = job.execute(plan)
        finally:
            job.close()
        if res.status not in ("completed", "completed_with_warnings"):
            raise Failure(f"backup status {res.status}: {res.error}")
        unexpected = [w for w in res.warnings if "changed while" not in w]
        if plan.skipped or unexpected:
            raise Failure(f"unexpected warnings/skips: {unexpected[:3]} {plan.skipped[:3]}")
        return plan, res

    def run_killed(self, kind: str, args: dict, delay: float) -> int:
        code = (f"import sys,json; sys.path.insert(0,{str(REPO)!r}); from tests.torture import child_main; "
                f"child_main({kind!r}, json.loads({json.dumps(json.dumps(args))}))")
        p = subprocess.Popen([sys.executable, "-c", code], env=os.environ.copy(),
                             stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        time.sleep(delay)
        p.send_signal(signal.SIGKILL)
        _, err = p.communicate()
        if p.returncode not in (0, -9):
            raise Failure(f"child {kind} failed: {err.decode()[-500:]}")
        return p.returncode

    # -- invariants ------------------------------------------------------------------------------------------
    def check_drive(self) -> None:
        self.stats["checks"] += 1
        m = self.target.manifest()
        try:
            if m.db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise Failure("I4: manifest database is damaged")
            res = verify(self.target, m, full=True)
            if not res.ok:
                raise Failure(f"I4: verify failed: missing={res.missing[:3]} size={res.wrong_size[:3]} "
                              f"damaged={res.damaged[:3]}")
            tracked = {self.target.root / e.stored for e in m.iter_tree("home") if e.kind in ("f", "d")}
        finally:
            m.close()
        on_drive = {Path(dp) / n for dp, dn, fn in os.walk(self.target.root / "home") for n in dn + fn}
        on_drive.add(self.target.root / "home")
        orphans = on_drive - tracked
        if orphans:
            raise Failure(f"I5: untracked items on the drive: {sorted(map(str, orphans))[:5]}")
        missing = self.history - hashes_under(self.target.root / "home", self.target.root / "_removed")
        if missing:
            raise Failure(f"I3: {len(missing)} previously backed-up contents are gone from the drive")

    def check_restore_equals_source(self) -> None:
        out = Path(tempfile.mkdtemp(prefix="restore-", dir=self.work))
        m = self.target.manifest()
        try:
            r = Restorer(self.cfg, self.target, m)
            plan = r.plan(["home"], to=out)
            res = r.execute(plan)
        finally:
            m.close()
        if res.warnings:
            raise Failure(f"I2: restore warnings: {res.warnings[:3]}")
        full = snapshot(self.home, False)
        skip_dirs = [k for k, v in full.items() if v[0] == "d" and k.rsplit(b"/", 1)[-1] == b"skipme"]
        want = {k: v for k, v in full.items()
                if not any(k == d or k.startswith(d + b"/") for d in skip_dirs)}
        got = snapshot(out / self.home.name, False)
        if want != got:
            raise Failure("I2: restore differs from the source:\n" + diff(want, got))
        shutil.rmtree(out, onerror=_force_remove)

    # -- one round ----------------------------------------------------------------------------------------
    def round(self, i: int, kill: bool) -> None:
        mutate(self.rng, self.home, self.rng.randint(5, 40))
        if self.rng.random() < 0.1 and not (self.home / "skipme").is_symlink() and \
                ((self.home / "skipme").is_dir() or not os.path.lexists(self.home / "skipme")):
            (self.home / "skipme").mkdir(exist_ok=True)
            (self.home / "skipme" / "f").write_bytes(rand_content(self.rng))
        partial = self.rng.random() < 0.2 and any(self.home.iterdir())
        only = None
        if partial:
            _, dirs, _ = entries(self.home)
            dirs = [d for d in dirs if "skipme" not in d.relative_to(self.home).parts]
            if dirs:
                only = [str(self.rng.choice(dirs))]
        if kill and self.rng.random() < 0.6:
            self.run_killed("backup", {"only": only}, self.rng.uniform(0.05, 1.5))
            self.stats["killed_backups"] += 1
            self.check_drive_light()
        before = snapshot(self.home, True)
        self.backup(only)
        after = snapshot(self.home, True)
        if before != after:
            raise Failure("I1: the backup changed the source:\n" + diff(before, after))
        scope = Path(only[0]) if only else self.home
        if scope.exists():
            self.history |= hashes_under(scope) - (hashes_under(self.home / "skipme") if not only else set())
        self.stats["partial" if only else "backups"] += 1
        self.check_drive()
        if not only:
            self.check_restore_equals_source()
        if self.rng.random() < 0.35:
            self.restore_round(kill)
        if self.rng.random() < 0.08:  # the user empties _removed now and then
            self.target.empty_removed()
            self.history = hashes_under(self.target.root / "home")
        self.stats["max_items"] = max(self.stats.get("max_items", 0), len(before))
        self.stats["max_mb"] = max(self.stats.get("max_mb", 0),
                                   sum(v[2] and os.path.getsize(self.home / os.fsdecode(k)) for k, v in before.items()
                                       if v[0] == "f") // 2**20)
        self.log(f"round {i}: ok ({len(before)} items)")

    def check_drive_light(self) -> None:
        m = self.target.manifest()
        try:
            if m.db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise Failure("I4: manifest damaged after a killed backup")
        finally:
            m.close()

    def restore_round(self, kill: bool) -> None:
        """Restore parts of the backup over a modified copy of the home folder."""
        local = self.work / "home" / f"local{self.rng.randint(0, 10**9)}"
        shutil.copytree(self.home, local, symlinks=True)
        mutate(self.rng, local, self.rng.randint(5, 30))
        local_before = snapshot(local, False)
        m = self.target.manifest()
        try:
            items = [e.path for e in m.iter_tree("home") if e.path != "home"]
        finally:
            m.close()
        chosen = self.rng.sample(items, min(len(items), self.rng.randint(1, 6))) if items else []
        if self.rng.random() < 0.3:
            chosen = ["home"]
        cfg = Config.load()
        cfg["home_path"] = str(local)
        cfg.save()
        try:
            if kill and self.rng.random() < 0.5:
                self.run_killed("restore", {"items": chosen}, self.rng.uniform(0.01, 0.6))
                self.stats["killed_restores"] += 1
                self.check_nothing_lost(local, local_before)
            m = self.target.manifest()
            try:
                r = Restorer(cfg, self.target, m)
                try:
                    plan = r.plan(chosen)
                except Exception as e:  # e.g. two items with the same destination: refused, fine
                    if "same place" in str(e):
                        return
                    raise
                res = r.execute(plan)
                for it in plan.items:
                    if it.entry.kind == "f" and it.op != "missing" and it.entry.sha256:
                        if not it.dest.is_file() or it.dest.is_symlink():
                            # allowed only if the restore said so (e.g. a parent folder is now a file here)
                            if not any(str(it.dest) in w for w in res.warnings):
                                raise Failure(f"R2: {it.dest} silently not restored")
                        elif sha(it.dest) != it.entry.sha256:
                            raise Failure(f"R2: restored {it.dest} differs from the backup")
            finally:
                m.close()
            self.check_nothing_lost(local, local_before)
            self.stats["restores"] += 1
        finally:
            self.cfg["home_path"] = str(self.home)
            self.cfg.save()
            shutil.rmtree(local, onerror=_force_remove)
            shutil.rmtree(local.parent / UNDO_DIRNAME, onerror=_force_remove) if False else None

    def check_nothing_lost(self, local: Path, before: dict) -> None:
        undo = local / UNDO_DIRNAME
        undo_hashes = hashes_under(undo)
        undo_links = set()
        if undo.exists():
            for dp, dn, fn in os.walk(undo):
                for n in dn + fn:
                    p = Path(dp) / n
                    if p.is_symlink():
                        undo_links.add(os.readlink(p))
        now = snapshot(local, False)
        for rel, info in before.items():
            if info[0] == "f":
                cur = now.get(rel)
                if not (cur and cur[0] == "f" and cur[2] == info[2]) and info[2] not in undo_hashes:
                    raise Failure(f"R1: local file {rel!r} was lost (not in place, not in the undo folder)")
            elif info[0] == "l":
                cur = now.get(rel)
                if cur != info and info[1] not in undo_links:
                    raise Failure(f"R1: local symlink {rel!r} was lost")


def child_main(kind: str, args: dict) -> None:
    """Runs inside the subprocess that gets killed."""
    cfg = Config.load()
    target = Target.find(cfg)
    if kind == "backup":
        job = BackupJob(cfg, target, args.get("only"))
        try:
            job.execute(job.scan())
        finally:
            job.close()
    else:
        m = target.manifest()
        r = Restorer(cfg, target, m)
        try:
            r.execute(r.plan(args["items"]))
        except Exception:
            pass


def _force_remove(func, path, exc):
    try:
        os.chmod(os.path.dirname(path), 0o755)
        os.chmod(path, 0o755)
        func(path)
    except OSError:
        pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--drive", required=True, help="a mounted test filesystem")
    ap.add_argument("--rounds", type=int, default=30)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--kill", action="store_true", help="also kill backups/restores at random moments")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    work = Path(tempfile.mkdtemp(prefix=f"deucalion-torture-{args.seed}-"))
    h = Harness(Path(args.drive), args.seed, work, args.verbose)
    populate(h.rng, h.home)
    mutate(h.rng, h.home, 50)
    t0 = time.monotonic()
    try:
        for i in range(args.rounds):
            h.round(i, args.kill)
    except Failure as e:
        print(f"FAILED (seed {args.seed}, round {i}): {e}\nwork dir kept: {work}\ndrive dir kept: {h.drive_dir}")
        return 1
    print(f"seed {args.seed}: {args.rounds} rounds OK in {time.monotonic() - t0:.0f}s  {json.dumps(h.stats)}")
    shutil.rmtree(work, onerror=_force_remove)
    shutil.rmtree(h.drive_dir, onerror=_force_remove)
    return 0


if __name__ == "__main__":
    sys.exit(main())
