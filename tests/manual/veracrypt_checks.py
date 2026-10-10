#!/usr/bin/env python3
"""VeraCrypt checks (one administrator prompt). Run by hand:
    python3 tests/manual/veracrypt_checks.py /media/$USER/<exFAT test drive>
Creates throwaway disk images next to this run's work folder; never touches real drives."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
work = Path(tempfile.mkdtemp(prefix="dcl-vccheck-"))
os.environ["DEUCALION_CONFIG_DIR"] = str(work / "cfg")
os.environ["DEUCALION_STATE_DIR"] = str(work / "state")

from deucalion import drivesetup  # noqa: E402
from deucalion.backup import BackupJob  # noqa: E402
from deucalion.config import Config  # noqa: E402
from deucalion.restore import Restorer  # noqa: E402
from deucalion.verify import verify  # noqa: E402
from deucalion.util import DeucalionError  # noqa: E402

failures = []
PW = "a long test passphrase 123"


def check(cond, msg):
    print(("  ok   " if cond else "  FAIL ") + msg, flush=True)
    if not cond:
        failures.append(msg)


home = work / "home"
(home / "Docs").mkdir(parents=True)
(home / "Docs" / "report: v2?.txt").write_text("report")
(home / "Docs" / "Notes").write_text("N")
(home / "Docs" / "notes").write_text("n")
(home / "big.bin").write_bytes(os.urandom(5 * 1024 * 1024))
cfg = Config.load()
cfg["home_path"] = str(home)
cfg.save()
ds = drivesetup.DriveSetup(cfg, out=lambda s: print(f"       {s}", flush=True))


def roundtrip(target, label):
    job = BackupJob(cfg, target)
    try:
        res = job.execute(job.scan())
    finally:
        job.close()
    check(res.status == "completed", f"{label}: backup {res.status} {res.error or ''}")
    m = target.manifest()
    try:
        check(verify(target, m, full=True).ok, f"{label}: verify --full")
        out = work / f"restore-{label}"
        r = Restorer(cfg, target, m)
        r.execute(r.plan(["home"], to=out))
    finally:
        m.close()
    diff = subprocess.run(["diff", "-r", str(home), str(out / home.name)], capture_output=True, text=True)
    check(diff.returncode == 0, f"{label}: restore identical to the source {diff.stdout[:200]}")


def lock_cycle(target, access, label):
    ds.close_access(access)
    check(not target.root.exists(), f"{label}: locked (backup not reachable)")
    try:
        ds.open(access, "wrong password!!")
        check(False, f"{label}: wrong password ACCEPTED")
    except DeucalionError:
        check(True, f"{label}: wrong password refused")
    mp = ds.open(access, PW)
    m = target.manifest()
    try:
        check(verify(target, m, full=True).ok, f"{label}: after unlocking again, every file is intact ({mp})")
    finally:
        m.close()
    ds.close_access(access)


def image(name, mb):
    p = work / name
    with open(p, "wb") as f:
        f.truncate(mb * 1024 * 1024)
    return ds.u.device(ds.u.loop_setup(str(p)))


try:
    print("1. Encrypted folder (VeraCrypt) on the exFAT drive — one password prompt now")
    folder = Path(sys.argv[1])
    t = ds.run(drivesetup.SetupRequest("encrypt-folder", folder=str(folder), method="veracrypt", name="VCFolder",
                                       size=128 * 1024 ** 2, passphrase=PW, allow_internal=True))
    a = cfg["targets"][t.id]["access"]
    check((folder / "Deucalion-Backup.hc").exists(), "container file created on the drive")
    roundtrip(t, "vc-folder")
    lock_cycle(t, a, "vc-folder")

    print("2. Whole drive encrypted (VeraCrypt) on a disk image")
    disk = image("whole.img", 200)
    t = ds.run(drivesetup.SetupRequest("encrypt-all", device=disk, method="veracrypt", name="VCWhole",
                                       passphrase=PW, allow_internal=True))
    a = cfg["targets"][t.id]["access"]
    roundtrip(t, "vc-whole")
    lock_cycle(t, a, "vc-whole")
    ds.release(disk)
    subprocess.run(["udisksctl", "loop-delete", "--no-user-interaction", "-b", disk], capture_output=True)

    print("3. Encrypted part + normal exFAT part (VeraCrypt) on a disk image")
    disk = image("split.img", 300)
    t = ds.run(drivesetup.SetupRequest("encrypt-part", device=disk, method="veracrypt", name="VCSplit",
                                       size=128 * 1024 ** 2, passphrase=PW, allow_internal=True))
    a = cfg["targets"][t.id]["access"]
    plain = drivesetup.plain_root_of(cfg, t)
    check(plain is not None and (plain / "READ-ME-FIRST.txt").exists(), f"normal part has the READ-ME ({plain})")
    roundtrip(t, "vc-split")
    lock_cycle(t, a, "vc-split")
    ds.release(disk)
    subprocess.run(["udisksctl", "loop-delete", "--no-user-interaction", "-b", disk], capture_output=True)
finally:
    ds.close()

print("\nRESULT:", "ALL CHECKS PASSED" if not failures else f"{len(failures)} FAILED: {failures}")
sys.exit(1 if failures else 0)
