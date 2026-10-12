#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Dimitrios Kafetzis
"""Checks that need the administrator password (one prompt). Run by hand:
    python3 tests/manual/admin_checks.py /media/$USER/<test drive>
They never change the system: the backup goes to the given test drive, and every request
sent to the root helper below must be refused."""

import glob
import hashlib
import os
import stat
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
work = Path(tempfile.mkdtemp(prefix="dcl-admincheck-"))
os.environ["DEUCALION_CONFIG_DIR"] = str(work / "cfg")
os.environ["DEUCALION_STATE_DIR"] = str(work / "state")

from deucalion.backup import BackupJob  # noqa: E402
from deucalion.config import Config  # noqa: E402
from deucalion.privileged import Privileged, helper_path  # noqa: E402
from deucalion.target import Target  # noqa: E402
from deucalion.util import DeucalionError  # noqa: E402

failures = []


def check(cond, msg):
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        failures.append(msg)


def etc_snapshot():
    snap = {}
    for root, dirs, files in os.walk("/etc"):
        for n in dirs + files:
            p = os.path.join(root, n)
            try:
                st = os.lstat(p)
            except OSError:
                continue
            h = None
            if stat.S_ISREG(st.st_mode) and os.access(p, os.R_OK):
                try:
                    h = hashlib.sha256(open(p, "rb").read()).hexdigest()
                except OSError:
                    pass
            snap[p] = (st.st_mode, st.st_uid, st.st_gid, st.st_size, st.st_mtime_ns, h)
    return snap


drive = Path(sys.argv[1])
home = work / "home"
(home / "Documents").mkdir(parents=True)
(home / "Documents" / "a.txt").write_text("hello")
cfg = Config.load()
cfg["home_path"] = str(home)
cfg.save()
target = Target.create(Path(tempfile.mkdtemp(prefix="admin-check-", dir=drive)), name="AdminCheck", allow_internal=True)
target.register(cfg, allow_internal=True)
print(f"helper: {helper_path()}")

etc_before = etc_snapshot()
with Privileged(method="pkexec") as priv:
    print("1. Full backup with protected settings (one password prompt)")
    job = BackupJob(cfg, target)
    try:
        warnings = job.prepare_system(priv)
        res = job.execute(job.scan())
    finally:
        job.close()
    rec = work / "state" / "system"
    check(res.status.startswith("completed"), f"backup finished: {res.status} {res.error or ''}")
    check(not warnings, f"no recipe warnings {warnings[:2]}")
    check((rec / "etc" / "collected-by.txt").read_text().startswith("administrator"), "collected as administrator")
    nm = list((rec / "network" / "system-connections").glob("*")) if (rec / "network").exists() else []
    netplan = list((rec / "etc" / "files" / "etc" / "netplan").glob("90-NM-*")) if (rec / "etc/files/etc/netplan").exists() else []
    check(len(nm) + len(netplan) > 0, f"network connections saved ({len(nm)} keyfiles, {len(netplan)} netplan files)")
    check(all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in netplan + nm), "saved connection files are private (0600)")
    check(not glob.glob("/tmp/deucalion-admin-*"), "the root hand-over folder was removed")
    check(etc_snapshot() == etc_before, "nothing in /etc changed")

    print("2. Symlink attack on the recipe folder")
    decoy = work / "decoy"
    decoy.mkdir()
    (decoy / "canary").write_text("do not touch")
    import shutil
    for sub in ("etc/files", "network"):
        shutil.rmtree(rec / sub, ignore_errors=True)
        (rec / sub).parent.mkdir(parents=True, exist_ok=True)
        os.symlink(decoy, rec / sub)
    (rec / "README.txt").unlink()
    os.symlink(decoy / "canary", rec / "README.txt")
    job = BackupJob(cfg, target)
    try:
        job.prepare_system(priv)
    except DeucalionError as e:
        print(f"       (refused: {e})")
    finally:
        job.close()
    check((decoy / "canary").read_text() == "do not touch", "decoy file untouched")
    check(sorted(os.listdir(decoy)) == ["canary"], f"nothing written into the decoy folder: {sorted(os.listdir(decoy))[:5]}")
    check(etc_snapshot() == etc_before, "nothing in /etc changed")

    print("3. Bad requests to the root helper must be refused")
    src = work / "src.txt"
    src.write_text("x")
    bad = [
        ("put_etc_file", dict(src=str(src), dest="/etc/shadow", mode=0o644, undo_dir="/var/backups/deucalion/t")),
        ("put_etc_file", dict(src=str(src), dest="/etc/../root/x", mode=0o644, undo_dir="/var/backups/deucalion/t")),
        ("put_etc_file", dict(src=str(src), dest="/etc/deucalion-check-never", mode=0o644,
                              undo_dir="/var/backups/deucalion/../../tmp/x")),
        ("apt_add_source", dict(filename="ubuntu.sources", content="x", keys=[])),
        ("apt_add_source", dict(filename="../../evil.list", content="x", keys=[])),
        ("apt_install", dict(packages=["ok", "--purge foo"])),
        ("veracrypt_open", dict(source="/etc/shadow", passphrase="x" * 10, name="deucalion-x", mount_name="X",
                                user=os.environ.get("USER", "nobody"))),
        ("no_such_operation", {}),
    ]
    for op, args in bad:
        try:
            priv.call(op, **args)
            check(False, f"{op} {list(args.values())[:2]} was ACCEPTED")
        except DeucalionError as e:
            check(True, f"{op}: refused ({str(e).split(': ', 2)[-1][:60]})")
    check(not os.path.exists("/etc/deucalion-check-never"), "no file was created in /etc")
    check(etc_snapshot() == etc_before, "nothing in /etc changed")

print("\nRESULT:", "ALL CHECKS PASSED" if not failures else f"{len(failures)} FAILED: {failures}")
print(f"(test backup left in {target.root}; work folder {work})")
sys.exit(1 if failures else 0)
