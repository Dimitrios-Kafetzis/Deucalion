#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Dimitrios Kafetzis
"""Every drive layout, set up for real in the app and from the command line, on demo USB drives
(image files). Also how to open an encrypted backup without Deucalion.

    python3 docs/tools/screenshots.py --stage layouts
    python3 docs/tools/scenario_layouts.py --attach DIR --from STEP [--to STEP]   (development)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scenario_common import PASSWORD, Scenario, boot, collect  # noqa: E402
from vm import VM, log  # noqa: E402

PW = [("Backup password:", PASSWORD), ("Type it again:", PASSWORD)]


def forget_all(s: Scenario) -> None:
    """Close and forget every registered drive (between the app runs and the terminal runs)."""
    s.vm.ssh("""python3 - <<'EOF'
import json, os, subprocess
p = os.path.expanduser("~/.config/deucalion/config.json")
c = json.load(open(p))
for t in c["targets"].values():
    subprocess.run(["bash", "-lc", f"deucalion close --target '{t['name']}'"], capture_output=True)
c["targets"], c["default_target"] = {}, None
json.dump(c, open(p, "w"), indent=2)
EOF""")


def ntfs_drive(s: Scenario, name: str, product: str, label: str, files: dict[str, int]) -> str:
    """A drive that came from a shop (NTFS) and already holds some of your files."""
    s.new_drive(name, "32G")
    dev = s.plug(name, product)
    s.vm.ssh(f"echo 'type=7' | sudo sfdisk -q {dev} && sudo udevadm settle && sudo mkfs.ntfs -Q -q -L {label} {dev}1 "
             f"&& sudo udevadm settle && udisksctl mount -b {dev}1 >/dev/null")
    for rel, size in files.items():
        s.vm.ssh(f'mkdir -p "$(dirname "/media/alex/{label}/{rel}")" && head -c {size} /dev/urandom > "/media/alex/{label}/{rel}"')
    return dev


PHOTO_FILES = {"Photos 2019/beach.jpg": 3_000_000, "Photos 2019/mountains.jpg": 2_500_000,
               "Photos 2020/wedding.jpg": 3_200_000, "Scans/passport.pdf": 400_000}
WORK_FILES = {"Contracts/2025/client-a.pdf": 300_000, "Presentations/kick-off.odp": 1_500_000}


def step_prepare(s: Scenario):
    s.prepare(big=False)
    s.vm.ssh("cd ~/Deucalion && ./install.sh --veracrypt --yes >/dev/null 2>&1 && "
             "./install.sh --system-helper >/dev/null 2>&1")


def gui_setup(s: Scenario, prefix: str, dev: str, layout: str, method: str = "", details: str = "",
              erases: bool = True) -> None:
    """Run the app's wizard for one layout, photographing its pages."""
    pages = [f"{prefix}-storage=drives:setup({dev})@4500", f"_=drives:pick({layout})"]
    if method:
        pages += ["_=drives:next", f"_=drives:pick({method})"]
    pages += ["_=drives:next", f"{prefix}-details=drives:fill({details})", "_=drives:next"]
    if erases:
        pages += [f"{prefix}-confirm=drives:confirm@1500"]
    else:
        pages += [f"{prefix}-confirm=win:wait@1200"]
    pages += [f"{prefix}-working=drives:next@4000", f"{prefix}-done=drives:finished@2000", "_=win:close@1500"]
    s.gui("layouts", "; ".join(pages))


def step_gui(s: Scenario):
    """Each layout in the app (the encrypted part + normal part layout is in the 'old' stage)."""
    s.new_drive("travel", "4G")
    dev = s.plug("travel", "Travel Drive")
    gui_setup(s, "veracrypt-whole", dev, "encrypt-all", "veracrypt", f"Travel|{PASSWORD}")
    s.gui("layouts", "drives-veracrypt-whole=drives:expand@2000")
    forget_all(s)
    s.unplug("travel")

    s.new_drive("big", "64G")
    dev = s.plug("big", "Big Drive")
    gui_setup(s, "luks-whole", dev, "encrypt-all", "luks", f"Big|{PASSWORD}")
    forget_all(s)
    s.unplug("big")

    dev = ntfs_drive(s, "photos", "Photo Drive", "Photos", PHOTO_FILES)
    gui_setup(s, "folder", dev, "encrypt-folder", "veracrypt", f"Photo Vault|{PASSWORD}|2", erases=False)
    forget_all(s)
    s.unplug("photos")

    s.new_drive("spare", "32G")
    dev = s.plug("spare", "Spare Drive")
    gui_setup(s, "plain", dev, "plain", "", "Spare")
    forget_all(s)
    s.unplug("spare")

    dev = ntfs_drive(s, "work", "Work Drive", "Work", WORK_FILES)
    gui_setup(s, "as-is", dev, "as-is", "", "Work", erases=False)
    forget_all(s)
    s.unplug("work")


def step_cli(s: Scenario):
    """The same layouts from the terminal, on fresh drives."""
    # Encrypted part + normal part (VeraCrypt)
    s.new_drive("backup", "8G")
    dev = s.plug("backup", "Backup Drive")
    name = dev.rsplit("/", 1)[1]
    s.cli("setup-split-cli", "deucalion setup-drive", answers=[
        (r"Which drive\?[\s\S]*Choose", ""), (r"How should the backup be stored\?[\s\S]*Choose", "2"),
        (r"Which encryption\?[\s\S]*Choose", "1"), (r"Size of the encrypted part", "5"),
        (r"A name for this backup drive", "Backup"), (r"type the drive name", name)] + PW)
    s.cli("backup-first", "deucalion backup")
    s.cli("status-first", "deucalion status")
    s.cli("close-split", "deucalion close")
    s.unplug("backup")

    # Whole drive, VeraCrypt
    s.new_drive("travel", "4G")
    dev = s.plug("travel", "Travel Drive")
    name = dev.rsplit("/", 1)[1]
    s.cli("setup-veracrypt-whole", "deucalion setup-drive", answers=[
        (r"Which drive\?[\s\S]*Choose", ""), (r"How should the backup be stored\?[\s\S]*Choose", "1"),
        (r"Which encryption\?[\s\S]*Choose", "1"), (r"A name for this backup drive", "Travel"),
        (r"type the drive name", name)] + PW)
    s.cli("drives-veracrypt-whole", "deucalion drives")
    s.cli("close-veracrypt-whole", "deucalion close")
    s.unplug("travel")

    # Whole drive, LUKS (with options instead of questions)
    s.new_drive("big", "64G")
    dev = s.plug("big", "Big Drive")
    name = dev.rsplit("/", 1)[1]
    s.cli("setup-luks-whole", f"deucalion setup-drive {dev} --layout encrypt-all --method luks --name Big",
          answers=[(r"type the drive name", name)] + PW)
    s.vm.ssh("bash -lc 'deucalion backup --no-admin' >/dev/null")  # something to look at below
    s.cli("close-luks", "deucalion close")
    # Opening a LUKS backup without Deucalion (Ubuntu's disk tools)
    s.cli("udisks-unlock", f"udisksctl unlock -b {dev}1", answers=[("Passphrase:", PASSWORD)])
    unlocked = s.vm.ssh("cat /var/tmp/docs-out/cli/udisks-unlock.txt", capture=True).stdout.split(" as ")[-1].strip().rstrip(".")
    s.cli("udisks-mount", f"udisksctl mount -b {unlocked}")
    s.cli("udisks-ls", "ls /media/alex/Big /media/alex/Big/Deucalion-Backup")
    s.vm.ssh(f"udisksctl unmount -b {unlocked} >/dev/null && udisksctl lock -b {dev}1 >/dev/null")
    s.unplug("big")

    # Encrypted folder on a drive with files (VeraCrypt)
    ntfs_drive(s, "photos", "Photo Drive", "Photos", PHOTO_FILES)
    s.cli("setup-folder", "deucalion setup-drive", answers=[
        (r"Which drive\?[\s\S]*Choose", ""), (r"How should the backup be stored\?[\s\S]*Choose", "3"),
        (r"Which encryption\?[\s\S]*Choose", "1"), (r"Size of the encrypted folder", "2"),
        (r"A name for this backup drive", "Photo Vault"), (r"Continue\?", "y")] + PW)
    s.cli("photos-drive", "ls /media/alex/Photos")
    s.cli("readme-folder", 'cat "/media/alex/Photos/READ-ME-FIRST.txt"')
    s.vm.ssh("bash -lc 'deucalion backup --no-admin' >/dev/null")
    s.cli("close-folder", "deucalion close")
    # Opening a VeraCrypt backup without Deucalion and without VeraCrypt (cryptsetup, built into Ubuntu)
    s.cli("cryptsetup-open", "sudo cryptsetup open --type tcrypt --veracrypt /media/alex/Photos/Deucalion-Backup.hc "
          "mybackup", answers=[("Enter passphrase", PASSWORD)])
    s.cli("cryptsetup-mount", "sudo mkdir -p /mnt/mybackup && sudo mount /dev/mapper/mybackup /mnt/mybackup && "
          "ls /mnt/mybackup/Deucalion-Backup")
    s.cli("cryptsetup-close", "sudo umount /mnt/mybackup && sudo cryptsetup close mybackup")
    s.unplug("photos")

    # Plain exFAT
    s.new_drive("spare", "32G")
    dev = s.plug("spare", "Spare Drive")
    name = dev.rsplit("/", 1)[1]
    s.cli("setup-plain", "deucalion setup-drive", answers=[
        (r"Which drive\?[\s\S]*Choose", ""), (r"How should the backup be stored\?[\s\S]*Choose", "3"),
        (r"A name for this backup drive", "Spare"), (r"type the drive name", name)])
    s.cli("readme-plain", 'cat "/media/alex/Spare/READ-ME-FIRST.txt"')
    s.cli("unmount-plain", "deucalion close")

    # As it is (NTFS, keeps the files)
    ntfs_drive(s, "work", "Work Drive", "Work", WORK_FILES)
    s.cli("setup-as-is", "deucalion setup-drive", answers=[
        (r"Which drive\?[\s\S]*Choose", "2"), (r"How should the backup be stored\?[\s\S]*Choose", "5"),
        (r"A name for this backup drive", "Work"), (r"Continue\?", "y")])
    s.cli("work-drive", "ls /media/alex/Work")
    s.cli("targets-all", "deucalion targets")
    s.cli("drives-all", "deucalion drives")
    s.gui("layouts", "drives-all=drives:expand@2500")


STEPS = [step_prepare, step_gui, step_cli]


def run_steps(s: Scenario, first: str | None = None, last: str | None = None) -> None:
    names = [f.__name__[5:] for f in STEPS]
    i = names.index(first) if first else 0
    j = names.index(last) + 1 if last else len(STEPS)
    for f in STEPS[i:j]:
        log(f"--- layouts: {f.__name__[5:]}")
        f(s)


def run(base: Path, keep: bool = False) -> None:
    vm = boot(base, "layouts", "alex", "alex-laptop")
    try:
        run_steps(Scenario(vm))
        collect(vm)
    finally:
        if not keep:
            vm.shutdown()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--attach", required=True)
    ap.add_argument("--from", dest="first")
    ap.add_argument("--to", dest="last")
    ap.add_argument("--collect", action="store_true")
    a = ap.parse_args()
    vm = VM.attach(Path(a.attach))
    try:
        run_steps(Scenario(vm), a.first, a.last)
        if a.collect:
            collect(vm)
    finally:
        vm.release()
    return 0


if __name__ == "__main__":
    sys.exit(main())
