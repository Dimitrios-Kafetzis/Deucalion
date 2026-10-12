#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Dimitrios Kafetzis
"""Make every screenshot and every piece of command output in the documentation, from scratch.

    python3 docs/tools/screenshots.py                   # everything, from scratch (about an hour)
    python3 docs/tools/screenshots.py --stage old       # only the "old laptop" part
    python3 docs/tools/screenshots.py --stage layouts   # only the drive layouts
    python3 docs/tools/screenshots.py --stage new       # only the rebuild (needs a previous 'old' run)

Everything runs in throwaway Ubuntu virtual machines (QEMU/KVM), never on this computer:

  base   Two prepared VM disks (Ubuntu 24.04 and 26.04), made once and cached in
         ~/.cache/deucalion-docs/: a server image plus what a Ubuntu Desktop already has that
         Deucalion uses, and the screenshot tools.
  old    "Alex's laptop" (Ubuntu 24.04, user alex): a demo home folder, demo USB drives (image
         files the VM sees as USB disks), a backup drive set up in the app, backups, restores, the app's
         pages and the command line.
  layouts  every drive layout set up in the app and in a terminal, and opening encrypted backups
         without Deucalion.
  new    "Alex's new laptop" (Ubuntu 26.04, user alexk): the backup drive from the old laptop is
         plugged in, Deucalion is run from the drive's Deucalion-Tool folder, and the machine is
         rebuilt step by step, in the app and in a terminal; also how Deucalion behaves without a
         desktop.

Results:  docs/assets/screenshots/<section>/<name>.png  and  docs/snippets/cli/<name>.txt
Needs:    qemu-system-x86, qemu-utils, gpgv, ssh (and KVM). Optional: pngquant (smaller images).
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))

from vm import CACHE, VM, fetch, log  # noqa: E402

SHOTS = REPO / "docs" / "assets" / "screenshots"
SNIPPETS = REPO / "docs" / "snippets" / "cli"
WORK = CACHE / "run"

# What a Ubuntu Desktop already has that Deucalion uses, plus what the screenshots need (GTK's
# Broadway backend, fonts, icons). VeraCrypt is left out: the docs show install.sh installing it.
DESKTOP_PACKAGES = ("python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 udisks2 cryptsetup exfatprogs pkexec dconf-cli gnupg "
                    "libgtk-4-bin librsvg2-common fonts-ubuntu fonts-noto-color-emoji yaru-theme-icon "
                    "adwaita-icon-theme network-manager ntfs-3g dbus-user-session polkitd cron sqlite3 libsm6 "
                    "$(apt-cache show linux-modules-extra-$(uname -r) >/dev/null 2>&1 && echo linux-modules-extra-$(uname -r))")
BASE_PACKAGES = {"24.04": DESKTOP_PACKAGES, "26.04": DESKTOP_PACKAGES}


def base_disk(version: str, rebuild: bool = False) -> Path:
    disk = CACHE / f"base-{version}.qcow2"
    if disk.exists() and not rebuild:
        return disk
    image = fetch(version)
    work = CACHE / f"build-{version}"
    shutil.rmtree(work, ignore_errors=True)
    tmp = VM.overlay(image, work / "disk.qcow2", "40G")
    vm = VM(tmp, work, user="builder", hostname="ubuntu")
    vm.boot()
    vm.ssh("sudo apt-get update -q")
    vm.ssh("sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends "
           + BASE_PACKAGES[version])
    vm.ssh("sudo timedatectl set-timezone Europe/London")
    vm.ssh("sudo apt-get clean")
    # Forget this build: the next boot is a new machine with its own user and hostname.
    vm.ssh("sudo bash -c 'cloud-init clean --logs --machine-id; rm -f /etc/sudoers.d/90-cloud-init-users; "
           "(sleep 2; userdel -rf builder; sync; poweroff) >/dev/null 2>&1 &'", check=False)
    vm.proc.wait(timeout=180)
    vm.proc = None
    if vm._httpd:
        vm._httpd.shutdown()
    shutil.move(str(tmp), str(disk))
    shutil.rmtree(work, ignore_errors=True)
    log(f"prepared {disk}")
    return disk


def _shrink(png: Path) -> None:
    if shutil.which("pngquant"):
        subprocess.run(["pngquant", "--force", "--skip-if-larger", "--quality=80-95", "--speed=1",
                        "--output", str(png), str(png)], capture_output=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage", choices=["base", "old", "layouts", "new", "all"], default="all")
    ap.add_argument("--rebuild-base", action="store_true", help="prepare the base VM disks again")
    ap.add_argument("--keep", action="store_true", help="leave the VMs running at the end (for poking around)")
    args = ap.parse_args()
    t0 = time.time()
    if args.stage == "all":  # start from nothing, so no old picture or output survives
        shutil.rmtree(SHOTS, ignore_errors=True)
        shutil.rmtree(SNIPPETS, ignore_errors=True)
    if args.stage in ("base", "all", "old", "layouts"):
        base_disk("24.04", args.rebuild_base)
    if args.stage in ("base", "all", "new"):
        base_disk("26.04", args.rebuild_base)
    if args.stage in ("old", "all"):
        import scenario_old
        scenario_old.run(base_disk("24.04"), keep=args.keep)
    if args.stage in ("layouts", "all"):
        import scenario_layouts
        scenario_layouts.run(base_disk("24.04"), keep=args.keep)
    if args.stage in ("new", "all"):
        import scenario_new
        scenario_new.run(base_disk("26.04"), keep=args.keep)
    if args.stage == "all":
        shutil.rmtree(WORK / "drives", ignore_errors=True)  # the demo drives (several GB)
    log(f"finished in {(time.time() - t0) / 60:.0f} minutes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
