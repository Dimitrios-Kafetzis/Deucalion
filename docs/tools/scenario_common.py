# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Dimitrios Kafetzis

"""Helpers shared by the documentation scenarios (they run on this computer and drive a VM)."""

from __future__ import annotations

import shlex
import shutil
import subprocess
import time
from pathlib import Path

from vm import CACHE, VM, log

REPO = Path(__file__).resolve().parent.parent.parent
WORK = CACHE / "run"
DRIVES = WORK / "drives"
PASSWORD = "correct horse battery"   # the demo backup password (shown in no screenshot or output)
CAPTURE = "python3 ~/Deucalion/docs/tools/capture.py"
POLKIT_RULE = """// Documentation VM only: no password dialogs (there is no screen to show them on).
polkit.addRule(function(action, subject) {
    if (subject.isInGroup("sudo")) return polkit.Result.YES;
});
"""


class Scenario:
    def __init__(self, vm: VM):
        self.vm = vm

    # -- running things in the VM ------------------------------------------------------------------
    def sh(self, command: str, check: bool = True, capture: bool = False, timeout: float | None = None):
        """A command in a login shell (so ~/.local/bin is on the PATH, as in a new terminal)."""
        return self.vm.ssh("bash -lc " + shlex.quote(command), check=check, capture=capture, timeout=timeout)

    def cli(self, name: str, command: str, show: str | None = None, answers: list[tuple[str, str]] = (),
            elide: list[tuple[str, str]] = (), cwd: str = "~", expect: int | None = 0,
            timeout: float = 1800, elide_apt: bool = False) -> int:
        """Run a command in a terminal and keep what it printed (docs/snippets/cli/NAME.txt)."""
        args = [CAPTURE, "cli", name, "--show", shlex.quote(show or command), "--timeout", str(timeout)]
        for rx, text in answers:  # text starting with '>' : use the answer every time it matches
            args += ["--answer", shlex.quote(f"{rx}=>{text}")]
        for a, b in elide:
            args += ["--elide", shlex.quote(f"{a}=>{b}")]
        if elide_apt:
            args.append("--elide-apt")
        args += ["--", shlex.quote(f"cd {cwd} && {command}")]
        r = self.vm.ssh(" ".join(args), check=False, timeout=timeout + 120)
        if expect is not None and r.returncode != expect:
            raise SystemExit(f"capture {name}: exit {r.returncode}, expected {expect}")
        return r.returncode

    def gui(self, folder: str, pages: str, size: str = "1024x760", theme: str = "light", wait: int = 1500) -> None:
        """Take app screenshots (docs/assets/screenshots/FOLDER/*.png); see deucalion/gui/shots.py."""
        pages = " ".join(pages.split())
        self.vm.ssh(f"{CAPTURE} gui {folder} --pages {shlex.quote(pages)} --size {size} --theme {theme} "
                    f"--wait {wait}", timeout=1800)

    # -- drives ----------------------------------------------------------------------------------------
    def new_drive(self, name: str, size: str) -> Path:
        """A new, empty drive (an image file)."""
        DRIVES.mkdir(parents=True, exist_ok=True)
        img = DRIVES / f"{name}.img"
        img.unlink(missing_ok=True)
        subprocess.run(["truncate", "-s", size, str(img)], check=True)
        return img

    def plug(self, name: str, product: str, write_mbps: int = 0) -> str:
        """Plug the drive in; returns its device name in the VM (e.g. /dev/sdb)."""
        self.vm.plug(name, DRIVES / f"{name}.img", product, write_mbps=write_mbps)
        for _ in range(30):
            dev = self.device(product)
            if dev:
                return dev
            time.sleep(1)
        raise SystemExit(f"{product} did not appear in the VM")

    def unplug(self, name: str) -> None:
        self.vm.unplug(name)

    def device(self, product: str) -> str:
        out = self.vm.ssh("lsblk -dnJ -o PATH,MODEL", capture=True, quiet=True).stdout
        import json
        for d in json.loads(out).get("blockdevices", []):
            if (d.get("model") or "").strip() == product:
                return d["path"]
        return ""

    # -- preparing a machine ------------------------------------------------------------------------------
    def prepare(self, home: bool = True, big: bool = True) -> None:
        """Copy Deucalion into ~/Deucalion (as after 'git clone'), allow admin steps without a password
        (there is nobody to type it), set the app's icon theme like Ubuntu's, fill the demo home folder."""
        self.vm.put(REPO, f"/home/{self.vm.user}")
        self.vm.ssh(f"sudo tee /etc/polkit-1/rules.d/49-docs-vm.rules >/dev/null", input=POLKIT_RULE)
        self.vm.ssh("mkdir -p ~/.config/gtk-4.0 && printf '[Settings]\\ngtk-icon-theme-name=Yaru\\n' "
                    "> ~/.config/gtk-4.0/settings.ini && sudo rm -rf /var/tmp/docs-out && mkdir -p /var/tmp/docs-out")
        if home:
            self.vm.ssh("python3 ~/Deucalion/docs/tools/demo_home.py" + (" --big" if big else ""))


def sparse_copy(src: Path, dest: Path) -> None:
    """Copy a drive image without filling its empty space."""
    dest.unlink(missing_ok=True)
    subprocess.run(["cp", "--sparse=always", str(src), str(dest)], check=True)


def boot(base: Path, name: str, user: str, hostname: str, fullname: str = "Alex") -> VM:
    work = WORK / name
    shutil.rmtree(work, ignore_errors=True)
    vm = VM(VM.overlay(base, work / "disk.qcow2"), work, user=user, hostname=hostname, fullname=fullname)
    vm.boot()
    return vm


def collect(vm: VM) -> None:
    """Copy the screenshots and captured output out of the VM into the docs."""
    from screenshots import SHOTS, SNIPPETS, _shrink
    out = WORK / f"out-{vm.hostname}"
    shutil.rmtree(out, ignore_errors=True)
    vm.get("/var/tmp/docs-out", out)
    if (out / "cli").is_dir():
        SNIPPETS.mkdir(parents=True, exist_ok=True)
        for f in (out / "cli").glob("*.txt"):
            shutil.copy2(f, SNIPPETS / f.name)
    if (out / "shots").is_dir():
        for folder in (out / "shots").iterdir():
            dest = SHOTS / folder.name
            dest.mkdir(parents=True, exist_ok=True)
            for png in folder.glob("*.png"):
                shutil.copy2(png, dest / png.name)
                _shrink(dest / png.name)
    log(f"collected {sum(1 for _ in out.rglob('*.txt'))} outputs and {sum(1 for _ in out.rglob('*.png'))} screenshots")
