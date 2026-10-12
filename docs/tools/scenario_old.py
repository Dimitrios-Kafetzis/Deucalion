#!/usr/bin/env python3
"""The "old laptop" part of the documentation: Alex (Ubuntu 24.04) installs Deucalion, sets up a
backup drive, backs up, restores, and looks after the backup. Every step is real; the screenshots
and terminal output in the docs come from here.

    python3 docs/tools/screenshots.py --stage old         (normal use)
    python3 docs/tools/scenario_old.py --attach DIR --from STEP [--to STEP]   (development)
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scenario_common import DRIVES, PASSWORD, Scenario, boot, collect, sparse_copy  # noqa: E402
from vm import VM, log  # noqa: E402

MAIN = "usb"                     # the main backup drive (image name)
MAIN_PRODUCT = "USB Drive"
MAIN_NAME = "Alex Backup"
PW = [("[Pp]assword:", PASSWORD)]
INSTALL_ELIDE = [("Signature OK", "Everything Deucalion needs is installed")]


def main_root(s: Scenario) -> str:
    """Where the main backup folder is mounted now: its mount name gets a number (Alex Backup2) when the
    drive's normal part was mounted first, so never guess it."""
    return s.vm.ssh("python3 -c \"import json, os; c = json.load(open(os.path.expanduser('~/.config/deucalion/config.json'))); "
                    f"print(next(t['path'] for t in c['targets'].values() if t['name'] == '{MAIN_NAME}'))\"",
                    capture=True, quiet=True).stdout.strip()


def step_prepare(s: Scenario):
    s.prepare(big=True)
    s.vm.ssh("bash ~/Deucalion/docs/tools/old_machine.sh", timeout=1200)
    s.new_drive(MAIN, "8G")
    s.new_drive("spare", "32G")


def step_welcome(s: Scenario):
    """Before installing: the app's first page, and the wizard before VeraCrypt is installed."""
    s.plug(MAIN, MAIN_PRODUCT)
    s.plug("spare", "Spare Drive")
    s.gui("app", """
        overview-welcome=overview;
        drives-connected=drives:expand;
        wizard-drive=drives:setup;
        _=drives:pick(/dev/sda);
        _=drives:next;
        _=drives:pick(encrypt-all);
        wizard-encryption-no-veracrypt=drives:next;
        _=win:close@800
    """)


def step_install(s: Scenario):
    s.cli("install", "./install.sh", answers=[(r"Install VeraCrypt\?.*\[y/N\]", "y")], elide=INSTALL_ELIDE,
          cwd="~/Deucalion")
    s.cli("install-system-helper", "./install.sh --system-helper", cwd="~/Deucalion")
    s.cli("deps", "deucalion deps")
    s.cli("version", "deucalion --version")
    s.cli("help", "deucalion --help")
    for cmd in ("gui", "deps", "drives", "register", "targets", "setup-drive", "open", "close", "backup", "status",
                "ls", "restore", "rebuild", "verify", "removed", "exclude", "folder", "profile", "config"):
        s.cli(f"help-{cmd}", f"deucalion {cmd} --help")


def step_setup_main(s: Scenario):
    """The app's drive wizard: encrypted part (VeraCrypt) + normal part, on the 16 GB USB drive."""
    s.gui("app", f"""
        wizard-drive-2=drives:setup;
        _=drives:pick(/dev/sda);
        _=drives:next;
        wizard-storage-split=drives:pick(encrypt-part);
        wizard-encryption=drives:next;
        _=drives:next;
        wizard-details=drives:fill({MAIN_NAME}|{PASSWORD}|6);
        _=drives:next;
        wizard-confirm=drives:confirm;
        wizard-working=drives:next@7000;
        wizard-done=drives:finished@2000;
        _=win:close@1500;
        overview-first=overview@3000;
        drives-backup-drive=drives:expand@2500
    """)
    s.cli("drives-after-setup", "deucalion drives")
    s.cli("targets", "deucalion targets")
    s.cli("readme-split", f'cat "/media/alex/{MAIN_NAME}1/READ-ME-FIRST.txt"',
          show=f'cat "/media/alex/{MAIN_NAME}1/READ-ME-FIRST.txt"')
    s.cli("tool-folder", f'ls "/media/alex/{MAIN_NAME}1" "/media/alex/{MAIN_NAME}1/Deucalion-Tool"')
    s.cli("drive-json", f'cat "/media/alex/{MAIN_NAME}1/Deucalion-Tool/drive.json"')


def step_first_backup(s: Scenario):
    """The first full backup in the app, photographed while it copies."""
    s.vm.ssh("sudo sysctl -q -w vm.dirty_bytes=8388608 vm.dirty_background_bytes=4194304")
    s.vm.throttle(MAIN, 12)
    s.gui("app", """
        backup-choose=backup;
        backup-scan=backup:scan@2500;
        backup-review=win:wait@40000;
        backup-review-notes=win:scroll(1)@1500;
        backup-running=backup:copy@9000;
        backup-stop-dialog=backup:stop@3500;
        _=win:close@1000;
        backup-done=backup:finished@2000;
        overview-ready=overview@3000;
        about=win:about@3500;
        _=win:close@800
    """)
    s.vm.throttle(MAIN, 0)
    s.vm.ssh("sudo sysctl -q -w vm.dirty_ratio=20 vm.dirty_background_ratio=10")


def step_cli_backup(s: Scenario):
    """A day later: some files changed. A dry run, then a backup from the terminal."""
    s.vm.ssh("""cd ~ && echo 'Ideas for the garden: tomatoes, basil.' > Documents/Notes.txt
        rm -f 'Desktop/todo.txt' && head -c 2400000 /dev/urandom > 'Pictures/Holidays 2026/IMG_0025.jpg'
        echo 'Agenda: backups, budget, holidays, new laptop.' > 'Documents/Work/Meeting notes 2026-09.txt'""")
    s.cli("backup-dry-run", "deucalion backup --dry-run")
    s.cli("backup", "deucalion backup")
    s.cli("status", "deucalion status")
    s.cli("ls", "deucalion ls")
    s.cli("ls-documents", "deucalion ls ~/Documents")
    root = main_root(s)
    s.cli("drive-names", f'ls "{root}/home/Documents"')
    s.cli("drive-top", f'ls -a "{root}" "{root}/.deucalion"')
    s.cli("backup-json", f'cat "{root}/backup.json"')
    s.cli("system-recipe", f'ls -R "{root}/system" | head -40', show=f'ls -R "{root}/system"')


def step_partial(s: Scenario):
    s.vm.ssh("cd ~ && echo 'Budget 2026, updated in October.' >> 'Documents/Notes.txt'")
    s.cli("backup-only", "deucalion backup --only ~/Documents ~/Pictures")
    s.cli("profile-add", "deucalion profile add work ~/Projects ~/Documents/Work")
    s.cli("profile-list", "deucalion profile")
    s.cli("backup-profile", "deucalion backup --profile work")
    s.gui("app", """
        backup-some=backup:some(Documents|Pictures);
        backup-some-review=backup:scan@8000;
        _=backup:back@1000
    """)


def step_exclude(s: Scenario):
    s.cli("exclude-list", "deucalion exclude")
    s.cli("exclude-add", 'deucalion exclude add "Videos/" "*.iso"')
    s.cli("exclude-remove", 'deucalion exclude remove "*.iso"')
    s.cli("exclude-add-node", "deucalion exclude add node_modules/")
    s.cli("folder-add", "deucalion folder add /srv/shared")
    s.cli("folder-list", "deucalion folder")
    s.cli("backup-after-exclude-dry-run", "deucalion backup --dry-run")
    s.cli("backup-no-admin", "deucalion backup --no-admin")
    s.cli("ls-after-folder", "deucalion ls")
    s.gui("app", """
        settings-top=settings;
        _=win:scroll(0.62)@1500;
        settings-typing=settings:typing(*.iso)@1500;
        settings-folders=win:scroll(1)@1500;
        settings-reset-dialog=settings:reset@3500;
        _=win:close@800
    """)


def step_restore(s: Scenario):
    s.vm.ssh("cd ~ && echo 'changed by mistake' > Documents/Notes.txt && rm -f Documents/notes.txt")
    s.gui("app", """
        restore-top=restore;
        restore-folder=restore:browse(home/Documents);
        restore-selected=restore:select(home/Documents/Notes.txt|home/Documents/notes.txt);
        restore-search=restore:search(receipt);
        _=restore:search();
        restore-preview=restore:preview@3500;
        _=win:close@800;
        restore-done=restore:restore@5000;
        _=restore:done;
        _=restore:browse(home/Pictures);
        _=restore:select(home/Pictures/Family);
        restore-other-place=restore:to(Desktop/Recovered);
        restore-other-preview=restore:preview@3500;
        _=win:close@800;
        restore-other-done=restore:restore@6000;
        _=restore:done
    """)
    s.vm.ssh("cd ~ && echo 'my own edit, made after the backup' > 'Documents/Budget 2026.ods'")
    s.cli("restore-dry-run", 'deucalion restore "~/Documents/Budget 2026.ods" --dry-run')
    s.cli("restore", 'deucalion restore "~/Documents/Budget 2026.ods"', answers=[(r"Restore now\?", "y")])
    s.cli("restore-to", "deucalion restore ~/Documents/Work --to ~/Desktop/Recovered",
          answers=[(r"Restore now\?", "y")])
    s.cli("undo-folder", "find ~/Deucalion-before-restore")
    s.cli("restore-system", "deucalion restore system/desktop --to ~/Desktop/recipe",
          answers=[(r"Restore now\?", "y")])


def step_removed(s: Scenario):
    s.cli("removed-list", "deucalion removed")
    s.gui("app", """
        removed-list=removed@2500;
        removed-ticked=removed:tick(1)@3000;
        removed-delete-dialog=removed:delete(1)@5000;
        _=win:close@800
    """)
    oldest = s.vm.ssh(f'ls "{main_root(s)}/_removed" | head -1', capture=True).stdout.strip()
    s.cli("removed-empty", f"deucalion removed empty {oldest}", answers=[(r"permanently\?", "y")])


def step_verify(s: Scenario):
    s.cli("verify", "deucalion verify")
    s.cli("verify-full", "deucalion verify --full")
    # Damage one file on the drive (same size), as a failing drive might
    s.vm.ssh(f"""f="{main_root(s)}/home/Documents/CV - Alex.pdf"
        printf 'XXXXXXXX' | dd of="$f" bs=1 seek=1000 conv=notrunc status=none""")
    s.cli("verify-damaged", "deucalion verify --full", expect=1)
    s.cli("backup-after-damage", "deucalion backup")
    s.cli("verify-again", "deucalion verify --full")


def step_lock(s: Scenario):
    s.gui("app", "drives-ready=drives")
    s.cli("close", "deucalion close")
    s.gui("app", """
        overview-locked=overview@2500;
        unlock-dialog=win:unlock@3500;
        _=win:close@800;
        restore-locked=restore;
        rebuild-locked=rebuild;
        drives-locked=drives
    """)
    s.cli("open", "deucalion open", answers=PW)
    s.cli("close-again", "deucalion close")
    s.cli("status-locked", "deucalion status", answers=PW)


def step_disconnected(s: Scenario):
    s.cli("close-before-unplug", "deucalion close")
    s.unplug(MAIN)
    s.gui("app", "overview-disconnected=overview@2500")
    s.cli("backup-not-connected", "deucalion backup", expect=1)
    dev = s.plug(MAIN, MAIN_PRODUCT)
    s.vm.ssh(f"udisksctl mount -b {dev}1 >/dev/null")  # what the desktop does when the drive is plugged in
    s.cli("open-after-plug", "deucalion open", answers=PW)


def step_busy(s: Scenario):
    s.vm.ssh("head -c 200000000 /dev/urandom > ~/Documents/scan-archive.zip")
    s.vm.throttle(MAIN, 4)
    s.vm.ssh("sudo sysctl -q -w vm.dirty_bytes=8388608 vm.dirty_background_bytes=4194304")
    s.vm.ssh("setsid bash -lc 'deucalion backup --no-admin' </dev/null >/var/tmp/bg-backup.log 2>&1 & "
             "echo $! > /var/tmp/bg-backup.pid; sleep 12")
    s.cli("another-task", "deucalion verify", expect=1)
    s.vm.throttle(MAIN, 0)
    s.vm.ssh("while kill -0 $(cat /var/tmp/bg-backup.pid) 2>/dev/null; do sleep 2; done")
    s.vm.ssh("sudo sysctl -q -w vm.dirty_ratio=20 vm.dirty_background_ratio=10")


def step_errors(s: Scenario):
    s.vm.ssh("mkdir -p ~/Backups")
    s.cli("register-system-disk", "deucalion register ~/Backups", expect=1)
    s.new_drive("small", "64M")
    dev = s.plug("small", "Small Drive")
    name = dev.rsplit("/", 1)[-1]
    s.cli("setup-small", f"deucalion setup-drive {dev} --layout plain --name Small --yes-erase {name}")
    s.cli("backup-full-drive", "deucalion backup --target Small", expect=1)
    # Change the default drive back: register the backup folder (the path 'deucalion targets' shows) again
    s.cli("register-default", f'deucalion register "{main_root(s)}" --default')
    s.cli("close-small", "deucalion close --target Small")
    s.gui("app", "drives-two=drives; forget-dialog=drives:forget(Small)@3500; _=win:answer(forget)@1500; "
                 "_=drives@1500")
    s.unplug("small")
    s.cli("config-path", "deucalion config path")
    s.cli("config-show", "deucalion config show")


def step_looks(s: Scenario):
    """Narrow window and dark style."""
    s.gui("narrow", "overview-narrow=overview@2500; sidebar-narrow=win:sidebar@1500; restore-narrow=restore",
          size="420x760")
    s.gui("dark", "overview-dark=overview@2500; restore-dark=restore:browse(home/Documents); drives-dark=drives; "
                  "settings-dark=settings", theme="dark")


def step_finish(s: Scenario):
    """Hand the drive over to the new laptop (stage 'new')."""
    s.cli("close-final", "deucalion close")
    s.unplug(MAIN)
    s.unplug("spare")
    (DRIVES / f"{MAIN}.img").replace(DRIVES / "for-new-laptop.img")
    (DRIVES / "spare.img").unlink(missing_ok=True)
    (DRIVES / "small.img").unlink(missing_ok=True)


STEPS = [step_prepare, step_welcome, step_install, step_setup_main, step_first_backup, step_cli_backup,
         step_partial, step_exclude, step_restore, step_removed, step_verify, step_lock, step_disconnected,
         step_busy, step_errors, step_looks, step_finish]


def run_steps(s: Scenario, first: str | None = None, last: str | None = None) -> None:
    names = [f.__name__[5:] for f in STEPS]
    i = names.index(first) if first else 0
    j = names.index(last) + 1 if last else len(STEPS)
    for f in STEPS[i:j]:
        log(f"--- old laptop: {f.__name__[5:]}")
        f(s)


def run(base: Path, keep: bool = False) -> None:
    vm = boot(base, "old", "alex", "alex-laptop")
    try:
        run_steps(Scenario(vm))
        collect(vm)
    finally:
        if not keep:
            vm.shutdown()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--attach", required=True, help="work folder of a running VM")
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
