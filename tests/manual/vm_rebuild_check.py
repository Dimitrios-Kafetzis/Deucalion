#!/usr/bin/env python3
"""Runs INSIDE a throwaway VM: rebuild it from a test backup, then check that nothing local was
lost, everything was restored, and a second run is harmless.
    python3 vm_rebuild_check.py /mnt/backup"""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

drive = Path(sys.argv[1])
sys.path.insert(0, str(drive / "Deucalion-Tool"))
from deucalion import rebuild  # noqa: E402
from deucalion.config import Config  # noqa: E402
from deucalion.target import Target  # noqa: E402

SAMPLE_APT = {"minicom", "picocom", "sqlite3", "arp-scan", "speedtest-cli", "dfu-util"}
SAMPLE_SNAPS = {"obsidian"}
HOME = Path.home()
results, failures = {}, []


def check(cond, msg):
    print(("  ok   " if cond else "  FAIL ") + msg, flush=True)
    if not cond:
        failures.append(msg)


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def home_snapshot():
    snap = {}
    for dp, dn, fn in os.walk(HOME):
        if "/Deucalion-before-restore" in dp or "/.cache" in dp or "/snap" in dp:
            continue
        for n in fn:
            p = Path(dp) / n
            if p.is_file() and not p.is_symlink():
                snap[str(p)] = sha(p)
    return snap


def undo_hashes():
    out = set()
    for dp, dn, fn in os.walk(HOME / "Deucalion-before-restore"):
        for n in fn:
            p = Path(dp) / n
            if p.is_file() and not p.is_symlink():
                out.add(sha(p))
    return out


def dpkg_installed():
    r = subprocess.run(["dpkg-query", "-W", "-f", "${binary:Package} ${db:Status-Abbrev}\n"], capture_output=True, text=True)
    return {l.split()[0] for l in r.stdout.splitlines() if l.endswith("ii ")}


def run_all_steps(label, select_packages):
    cfg = Config.load()
    target = Target.find(cfg)
    m = target.manifest()
    ctx = rebuild.Context(cfg, target, m)
    report = {}
    try:
        for step in rebuild.STEPS:
            plan = step.plan(ctx)
            if step.name == "packages":
                for it in plan.actionable:
                    it.selected = (it.data["type"] == "apt" and it.data["name"] in SAMPLE_APT) or \
                                  (it.data["type"] == "snap" and it.data["name"] in SAMPLE_SNAPS)
            chosen = [i for i in plan.actionable if i.selected]
            lines = []
            warnings = step.apply(ctx, chosen, lines.append) if chosen else []
            report[step.name] = {"offered": len(plan.actionable), "applied": [i.key for i in chosen],
                                 "warnings": warnings, "notes": plan.notes[:3]}
            print(f"  [{label}] {step.name}: offered {len(plan.actionable)}, applied {len(chosen)}, "
                  f"warnings {len(warnings)}", flush=True)
            for w in warnings[:5]:
                print(f"      ! {w}", flush=True)
    finally:
        ctx.close()
        m.close()
    return report


print("== Preparing the new machine (local files that must not be lost)")
(HOME / "Documents").mkdir(exist_ok=True)
(HOME / "Documents" / "a.txt").write_text("LOCAL VERSION on the new machine\n")
(HOME / "local-only.txt").write_text("only on the new machine\n")
ubuntu_sources = sha("/etc/apt/sources.list.d/ubuntu.sources")
local_before = home_snapshot()
pkgs_before = dpkg_installed()

print("== Register the backup drive and a full dry run")
cfg = Config.load()
t = Target.create(drive)
t.register(cfg)
dry = subprocess.run([sys.executable, str(drive / "Deucalion-Tool/bin/deucalion"), "rebuild", "--dry-run"],
                     capture_output=True, text=True)
Path("/tmp/rebuild-dry-run.txt").write_text(dry.stdout + dry.stderr)
check(dry.returncode == 0, "full rebuild dry run completed")

print("== First rebuild")
results["first"] = run_all_steps("1st", True)

print("== Checks after the first rebuild")
check(sha("/etc/apt/sources.list.d/ubuntu.sources") == ubuntu_sources, "Ubuntu's own sources file untouched")
added = sorted(p.name for p in Path("/etc/apt/sources.list.d").glob("deucalion-*"))
check(bool(added), f"repositories added as new deucalion-* files: {added}")
for f in Path("/etc/apt/sources.list.d").glob("deucalion-*"):
    check("noble" not in f.read_text(), f"{f.name}: no 24.04 (noble) suites left")
pkgs_after = dpkg_installed()
check(SAMPLE_APT <= pkgs_after, f"sample packages installed: {sorted(SAMPLE_APT - pkgs_after) or 'all'}")
check(not (pkgs_before - pkgs_after), f"no package was removed: {sorted(pkgs_before - pkgs_after)[:10]}")
snaps = subprocess.run(["snap", "list"], capture_output=True, text=True).stdout
check("obsidian" in snaps, "sample snap installed")
undo = undo_hashes()
now = home_snapshot()
lost = [p for p, h in local_before.items() if now.get(p) != h and h not in undo]
check(not lost, f"no local file lost (each one unchanged or in the undo folder): {lost[:5]}")
check((HOME / "Documents" / "a.txt").read_text() == "backup version of a\n", "backup version restored")
check((HOME / "local-only.txt").exists(), "a file only on the new machine was kept")
check((HOME / "Documents" / "Work" / "report: final?.txt").read_text() == "quarterly report\n", "odd names restored")
check({p.name for p in (HOME / "Documents").glob("*otes.txt")} == {"Notes.txt", "notes.txt"}, "case twins restored")
check(oct((HOME / ".ssh" / "id_ed25519").stat().st_mode & 0o777) == "0o600", ".ssh key permissions kept")
check(f"{HOME}/.gitignore_global" in (HOME / ".gitconfig").read_text(), ".gitconfig path updated to the new home")
check(os.readlink(HOME / ".local/bin/tool") == f"{HOME}/Projects/tool.sh", "absolute symlink updated to the new home")
check(f'"{HOME}/Projects"' in (HOME / ".config/myapp/settings.json").read_text(), "settings.json path updated")
check("/home/dkafetzisothers" in (HOME / ".config/myapp/settings.json").read_text(), "a different path was not touched")
groups = subprocess.run(["id", "-Gn"], capture_output=True, text=True).stdout.split()
results["groups"] = groups
results["udev"] = sorted(p.name for p in Path("/etc/udev/rules.d").glob("99-*"))
results["netplan"] = sorted(p.name for p in Path("/etc/netplan").glob("90-NM-*"))

print("== Second rebuild (must be harmless)")
local_before2 = home_snapshot()
undo_before2 = undo_hashes()
pkgs_before2 = dpkg_installed()
results["second"] = run_all_steps("2nd", True)
undo2 = undo_hashes()
now2 = home_snapshot()
lost2 = [p for p, h in local_before2.items() if now2.get(p) != h and h not in undo2]
check(not lost2, f"second run: no local file lost: {lost2[:5]}")
check(not (pkgs_before2 - dpkg_installed()), "second run: no package removed")
check(results["second"]["paths"]["offered"] == 0, "second run: no paths left to update")
check(results["second"]["repositories"]["applied"] == [], "second run: no repository added again")
check(undo_hashes() == undo_before2, "second run: nothing new had to be set aside (the rebuild is repeatable)")
check(results["second"]["services"]["applied"] == [], f"second run: nothing re-applied in services {results['second']['services']['applied']}")
check(not any(k.startswith("/etc/cups/") for k in results["first"]["system-config"]["applied"]),
      "printer settings not restored where CUPS is not installed")

print("\nRESULT:", "ALL CHECKS PASSED" if not failures else f"{len(failures)} FAILED: {failures}")
Path("/tmp/vm-results.json").write_text(json.dumps(results, indent=1, default=str))
sys.exit(1 if failures else 0)
