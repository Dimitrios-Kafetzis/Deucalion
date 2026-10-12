#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Dimitrios Kafetzis
"""The "new laptop" part of the documentation: Alex installs Ubuntu 26.04 on a new computer (user
alexk this time), plugs in the backup drive from the old laptop, and rebuilds the computer with
Deucalion run from the drive's Deucalion-Tool folder: once in the app (VM 1), once in a terminal
(VM 2, which first shows how Deucalion behaves without a desktop, e.g. over SSH).

    python3 docs/tools/screenshots.py --stage new       (needs the 'old' stage's drive)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scenario_common import DRIVES, PASSWORD, REPO, Scenario, boot, collect, sparse_copy  # noqa: E402
from vm import VM, log  # noqa: E402

TOOLS = "/var/tmp/deucalion-docs"     # the docs' capture tools (not part of what Alex has)
PW = [("[Pp]assword:", PASSWORD)]


class NewScenario(Scenario):
    plain = ""   # where the drive's normal part is mounted (Ubuntu 26.04: /run/media/<user>/<name>)

    @property
    def tool(self) -> str:
        return f"{self.plain}/Deucalion-Tool"

    def mount_plain(self, dev: str) -> None:
        """What the desktop does when the drive is plugged in: mount its normal part."""
        self.vm.ssh(f"udisksctl mount -b {dev}1 >/dev/null")
        self.plain = self.vm.ssh(f"findmnt -no TARGET {dev}1", capture=True).stdout.strip()

    def prepare_new(self, polkit: bool = True) -> None:
        """A fresh Ubuntu: no Deucalion in the home folder; the capture tools live outside it."""
        self.vm.put(REPO, TOOLS)
        self.vm.ssh(f"mkdir -p ~/.config/gtk-4.0 && printf '[Settings]\\ngtk-icon-theme-name=Yaru\\n' "
                    f"> ~/.config/gtk-4.0/settings.ini && sudo rm -rf /var/tmp/docs-out && mkdir -p /var/tmp/docs-out")
        # Something that is only on the new computer (it must survive the rebuild)
        self.vm.ssh("mkdir -p ~/Documents && echo 'Written on the new laptop.' > ~/Documents/new-laptop.txt")
        if polkit:
            self.allow_admin()

    def allow_admin(self) -> None:
        from scenario_common import POLKIT_RULE
        self.vm.ssh("sudo tee /etc/polkit-1/rules.d/49-docs-vm.rules >/dev/null", input=POLKIT_RULE)

    def plug_backup_drive(self) -> str:
        if self.device("USB Drive"):  # already plugged in (a development run attached to this VM)
            return self.device("USB Drive")
        img = DRIVES / f"new-{self.vm.work.name}.img"
        sparse_copy(DRIVES / "for-new-laptop.img", img)
        self.vm.plug("usb", img, "USB Drive")
        dev = ""
        for _ in range(30):
            dev = self.device("USB Drive")
            if dev:
                break
        return dev

    def cli(self, name, command, **kw):
        kw.setdefault("cwd", f'"{self.tool}"')
        return super().cli(name, command, **kw)

    def gui(self, folder, pages, **kw):
        pages = " ".join(pages.split())
        import shlex
        self.vm.ssh(f"DEUCALION_REPO={shlex.quote(self.tool)} python3 {TOOLS}/Deucalion/docs/tools/capture.py gui {folder} "
                    f"--pages {shlex.quote(pages)} --size {kw.get('size', '1024x760')} --theme light --wait 1500",
                    timeout=7200)


def _capture_cmd_fix(s: NewScenario) -> None:
    import scenario_common
    scenario_common.CAPTURE = f"python3 {TOOLS}/Deucalion/docs/tools/capture.py"


# -- VM 1: the rebuild in the app -------------------------------------------------------------------------


def app_rebuild(s: NewScenario) -> None:
    dev = s.plug_backup_drive()
    s.mount_plain(dev)
    s.cli("new-open", "bin/deucalion open", answers=PW)
    s.cli("new-status", "bin/deucalion status")
    s.cli("new-other-machine", "bin/deucalion backup --dry-run")
    s.cli("new-rebuild-dry-run", "bin/deucalion rebuild --dry-run")
    # The app, from the drive: every step's plan, then apply them one by one
    s.gui("rebuild", """
        rebuild-start=rebuild@4000;
        rebuild-step-1=rebuild:step(1)@6000;
        rebuild-step-8=rebuild:step(8)@8000;
        rebuild-step-7=rebuild:step(7)@8000;
        rebuild-etc-changes=rebuild:diff(1)@3500;
        _=win:close@1000;
        _=rebuild:root@1500;
        _=rebuild:step(1)@6000;
        _=rebuild:apply@3000;
        rebuild-repos=win:wait@20000;
        _=rebuild:apply@2000;
        rebuild-repos-working=win:wait@3000;
        rebuild-repos-done=rebuild:applied@1500;
        _=rebuild:next@20000;
        rebuild-packages-chosen=rebuild:tick(htop|tree|hello-world|hello-tool)@1500;
        _=rebuild:apply@2000;
        rebuild-packages-working=win:wait@8000;
        rebuild-packages-done=rebuild:applied@1500;
        _=rebuild:next@6000;
        _=rebuild:apply@1500;
        rebuild-home-working=win:wait@1500;
        rebuild-home-done=rebuild:applied@1500;
        rebuild-paths=rebuild:next@6000;
        _=rebuild:apply@1500;
        rebuild-paths-done=rebuild:applied@1500;
        rebuild-desktop=rebuild:next@6000;
        _=rebuild:apply@1500;
        rebuild-desktop-done=rebuild:applied@1500;
        _=rebuild:next@6000;
        _=rebuild:apply@1500;
        rebuild-etc-done=rebuild:applied@1500;
        rebuild-services=rebuild:next@6000;
        _=rebuild:apply@1500;
        rebuild-services-done=rebuild:applied@1500;
        rebuild-all-done=rebuild:root@3000
    """)
    # What the rebuild did
    s.cli("after-gitconfig", "cat ~/.gitconfig", cwd="~")
    s.cli("after-link", "readlink ~/.local/bin/tool", cwd="~")
    s.cli("after-new-file", "cat ~/Documents/new-laptop.txt", cwd="~")
    s.cli("after-undo", "ls ~/Deucalion-before-restore", cwd="~")
    s.cli("after-sources", "ls /etc/apt/sources.list.d", cwd="~")
    s.cli("after-groups", "id -nG alexk", cwd="~")


# -- VM 2: no desktop first, then the rebuild in a terminal ------------------------------------------------


def headless_and_cli(s: NewScenario) -> None:
    dev = s.plug_backup_drive()
    # Without a desktop session (SSH), Ubuntu's disk service asks for the administrator password: here
    # there is no polkit agent to ask, so mounting the normal part is refused. sudo works.
    s.cli("headless-udisks-mount", f"udisksctl mount --no-user-interaction -b {dev}1", cwd="~", expect=None,
          timeout=120)
    s.plain = "/mnt/backup-drive"
    s.cli("headless-sudo-mount", f'sudo mkdir -p {s.plain} && sudo mount -o uid=$(id -u),gid=$(id -g) {dev}1 '
                                 f'{s.plain} && ls {s.plain}', cwd="~")
    s.cli("headless-open", "bin/deucalion open", answers=PW)
    s.cli("headless-deps", "bin/deucalion deps", expect=None)
    s.cli("headless-gui", "bin/deucalion", expect=None)
    s.allow_admin()  # the rest as on a desktop
    s.cli("rebuild-cli", "bin/deucalion rebuild", answers=[
        (r"Continue\? \[y/N\] $", "y"),       # step 1: after reading the check
        (r"Step 7/8[\s\S]*> $", "d 1"),          # step 7: show the change of the first /etc file
        (r"> $", ">")], timeout=5400, elide_apt=True)            # every other step (and step 7 after the diff): apply
    s.cli("rebuild-again", "bin/deucalion rebuild", answers=[(r"> $", "q")], expect=None)
    s.cli("rebuild-step-again", "bin/deucalion rebuild --step paths --dry-run")


def run(base: Path, keep: bool = False) -> None:
    for name, host, func in (("new-app", "alex-new-laptop", app_rebuild),
                             ("new-cli", "alex-new-laptop", headless_and_cli)):
        vm = boot(base, name, "alexk", host)
        s = NewScenario(vm)
        _capture_cmd_fix(s)
        try:
            log(f"--- new laptop: {func.__name__}")
            s.prepare_new(polkit=func is app_rebuild)
            func(s)
        finally:
            collect(vm)  # keep what was made, even when a later step failed
            if not keep:
                vm.shutdown()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--attach", required=True)
    ap.add_argument("--part", choices=["app", "cli"], required=True)
    ap.add_argument("--collect", action="store_true")
    a = ap.parse_args()
    vm = VM.attach(Path(a.attach))
    s = NewScenario(vm)
    _capture_cmd_fix(s)
    try:
        (app_rebuild if a.part == "app" else headless_and_cli)(s)
        if a.collect:
            collect(vm)
    finally:
        vm.release()
    return 0


if __name__ == "__main__":
    sys.exit(main())
