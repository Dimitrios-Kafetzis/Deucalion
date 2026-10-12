#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Dimitrios Kafetzis
"""Throwaway Ubuntu virtual machines for the documentation (screenshots, real command output,
rebuild walk-throughs). Nothing here touches a real drive: the demo drives are image files that
the VM sees as USB drives.

  python3 docs/tools/vm.py fetch 24.04         download + verify an Ubuntu cloud image
  python3 docs/tools/vm.py shell 24.04         boot a fresh VM and open a shell in it (for poking around)

Images are verified against Ubuntu's signed SHA256SUMS (SHA256SUMS.gpg, checked with the
ubuntu-cloudimage keyring) and cached in ~/.cache/deucalion-docs/.
The VM is configured with cloud-init (NoCloud, served over HTTP from this machine), booted with
QEMU/KVM, and reached over SSH on a forwarded local port.
"""

from __future__ import annotations

import argparse
import hashlib
import http.server
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

CACHE = Path(os.environ.get("DEUCALION_DOCS_CACHE", Path.home() / ".cache" / "deucalion-docs"))
RELEASES = "https://cloud-images.ubuntu.com/releases/{v}/release/"
IMAGE = "ubuntu-{v}-server-cloudimg-amd64.img"
KEYRING = "/usr/share/keyrings/ubuntu-cloudimage-keyring.gpg"


def log(msg: str) -> None:
    print(f"[vm] {msg}", flush=True)


# ------------------------------------------------------------------------------------------------
# Images


def _download(url: str, dest: Path) -> None:
    tmp = dest.with_name(dest.name + ".part")
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "deucalion-docs"}),
                                timeout=60) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f, 4 * 1024 * 1024)
    os.replace(tmp, dest)


def fetch(version: str) -> Path:
    """The verified cloud image for an Ubuntu version (downloaded once)."""
    folder = CACHE / f"cloudimg-{version}"
    image = folder / IMAGE.format(v=version)
    ok = folder / "verified"
    if image.exists() and ok.exists() and ok.read_text().strip() == _sha256(image):
        return image
    folder.mkdir(parents=True, exist_ok=True)
    base = RELEASES.format(v=version)
    log(f"downloading SHA256SUMS for {version}")
    _download(base + "SHA256SUMS", folder / "SHA256SUMS")
    _download(base + "SHA256SUMS.gpg", folder / "SHA256SUMS.gpg")
    r = subprocess.run(["gpgv", "--keyring", KEYRING, str(folder / "SHA256SUMS.gpg"), str(folder / "SHA256SUMS")],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"SHA256SUMS signature is not valid:\n{r.stderr}")
    want = None
    for line in (folder / "SHA256SUMS").read_text().splitlines():
        digest, _, name = line.partition(" ")
        if name.lstrip("*") == image.name:
            want = digest
    if not want:
        raise SystemExit(f"{image.name} is not listed in SHA256SUMS")
    if not image.exists() or _sha256(image) != want:
        log(f"downloading {image.name} (about 600 MB)")
        _download(base + image.name, image)
    got = _sha256(image)
    if got != want:
        image.unlink()
        raise SystemExit(f"{image.name}: checksum mismatch (got {got}, expected {want})")
    ok.write_text(got + "\n")
    log(f"{image.name} verified")
    return image


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while buf := f.read(4 * 1024 * 1024):
            h.update(buf)
    return h.hexdigest()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ------------------------------------------------------------------------------------------------
# A running VM


class VM:
    def __init__(self, disk: Path, workdir: Path, user: str = "alex", hostname: str = "alex-laptop",
                 memory: int = 4096, cpus: int = 4, fullname: str = "Alex"):
        self.disk = Path(disk)
        self.work = Path(workdir)
        self.work.mkdir(parents=True, exist_ok=True)
        self.user, self.hostname, self.fullname = user, hostname, fullname
        self.memory, self.cpus = memory, cpus
        self.ssh_port = _free_port()
        # One key for every VM, as one person's computers would have: a rebuild restores ~/.ssh
        # (including authorized_keys) from the old laptop onto the new one.
        self.key = CACHE / "id_ed25519"
        self.proc: subprocess.Popen | None = None
        self.qmp: socket.socket | None = None
        self._qmp_buf = b""
        self._httpd = None
        self.drives: dict[str, dict] = {}

    # -- creating disks -------------------------------------------------------------------------
    @staticmethod
    def overlay(base: Path, dest: Path, size: str | None = None) -> Path:
        """A new disk that starts as a copy of `base` (only changes are stored). Never smaller than base."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.unlink(missing_ok=True)
        subprocess.run(["qemu-img", "create", "-q", "-f", "qcow2", "-F", "qcow2", "-b", str(base), str(dest)]
                       + ([size] if size else []), check=True)
        return dest

    # -- cloud-init seed --------------------------------------------------------------------------
    def _seed(self) -> int:
        if not self.key.exists():
            subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(self.key)], check=True)
        pub = (self.key.with_suffix(".pub")).read_text().strip()
        seed = self.work / "seed"
        seed.mkdir(exist_ok=True)
        (seed / "meta-data").write_text(f"instance-id: {self.hostname}-{int(time.time())}\n"
                                        f"local-hostname: {self.hostname}\n")
        (seed / "user-data").write_text(f"""#cloud-config
hostname: {self.hostname}
users:
  - name: {self.user}
    gecos: {self.fullname}
    shell: /bin/bash
    groups: [sudo, adm, plugdev]
    sudo: "ALL=(ALL) NOPASSWD:ALL"
    lock_passwd: true
    ssh_authorized_keys: ["{pub}"]
ssh_pwauth: false
package_update: false
""")
        (seed / "vendor-data").write_text("")
        handler = lambda *a, **k: http.server.SimpleHTTPRequestHandler(*a, directory=str(seed), **k)  # noqa: E731

        class Quiet(http.server.ThreadingHTTPServer):
            def handle_error(self, *a):
                pass

        http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
        self._httpd = Quiet(("127.0.0.1", 0), handler)
        threading.Thread(target=self._httpd.serve_forever, daemon=True).start()
        return self._httpd.server_address[1]

    # -- life cycle --------------------------------------------------------------------------------
    def boot(self, timeout: int = 600) -> None:
        port = self._seed()
        self.qmp_port = _free_port()
        cmd = ["qemu-system-x86_64", "-machine", "q35,accel=kvm", "-cpu", "host", "-m", str(self.memory), "-smp", str(self.cpus),
               "-drive", f"file={self.disk},if=virtio,format=qcow2,discard=unmap",
               "-netdev", f"user,id=n0,hostfwd=tcp:127.0.0.1:{self.ssh_port}-:22",
               "-device", "virtio-net-pci,netdev=n0",
               "-device", "qemu-xhci,id=xhci",
               "-smbios", f"type=1,serial=ds=nocloud;s=http://10.0.2.2:{port}/",
               "-qmp", f"tcp:127.0.0.1:{self.qmp_port},server=on,wait=off",
               "-display", "none", "-serial", f"file:{self.work / 'console.log'}"]
        log(f"booting {self.disk.name} as {self.user}@{self.hostname} (ssh port {self.ssh_port})")
        self.proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL)
        self._qmp_connect()
        (self.work / "vm.json").write_text(json.dumps({"user": self.user, "hostname": self.hostname,
                                                       "ssh_port": self.ssh_port, "qmp_port": self.qmp_port,
                                                       "pid": self.proc.pid}))
        end = time.time() + timeout
        while time.time() < end:
            if self.proc.poll() is not None:
                raise SystemExit("QEMU stopped; see " + str(self.work / "console.log"))
            r = self.ssh("cloud-init status --wait >/dev/null 2>&1; echo ready", check=False, capture=True,
                         timeout=300, quiet=True)
            if r.returncode == 0 and "ready" in r.stdout:
                log("VM is up")
                return
            time.sleep(3)
        raise SystemExit("the VM did not come up in time")

    @classmethod
    def attach(cls, workdir: Path) -> "VM":
        """Reconnect to a VM that another process booted (and left running) in workdir."""
        info = json.loads((Path(workdir) / "vm.json").read_text())
        vm = cls(Path(workdir) / "disk.qcow2", workdir, user=info["user"], hostname=info["hostname"])
        vm.ssh_port, vm.qmp_port = info["ssh_port"], info["qmp_port"]
        vm._qmp_connect()
        return vm

    def release(self) -> None:
        """Let another process take over (QMP accepts one client at a time)."""
        if self.qmp is not None:
            self.qmp.close()
            self.qmp = None

    def shutdown(self) -> None:
        if self.proc is None:
            if self.qmp is not None:  # attached: power off through the guest
                self.ssh("sudo systemctl poweroff", check=False, quiet=True, timeout=30)
            return
        self.ssh("sudo systemctl poweroff", check=False, quiet=True, timeout=30)
        try:
            self.proc.wait(timeout=120)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
        self.proc = None
        if self._httpd:
            self._httpd.shutdown()
        log("VM stopped")

    # -- QMP ----------------------------------------------------------------------------------------
    def _qmp_connect(self) -> None:
        for _ in range(100):
            try:
                self.qmp = socket.create_connection(("127.0.0.1", self.qmp_port), timeout=60)
                break
            except OSError:
                time.sleep(0.1)
        self._qmp_buf = b""
        self._qmp_read()  # greeting
        self.qmp_cmd("qmp_capabilities")

    def _qmp_read(self) -> dict:
        while b"\n" not in self._qmp_buf:
            self._qmp_buf += self.qmp.recv(65536)
        line, _, self._qmp_buf = self._qmp_buf.partition(b"\n")
        return json.loads(line)

    def qmp_cmd(self, execute: str, **arguments) -> dict:
        self.qmp.sendall(json.dumps({"execute": execute, "arguments": arguments}).encode() + b"\n")
        while True:
            msg = self._qmp_read()
            if "return" in msg:
                return msg["return"]
            if "error" in msg:
                raise RuntimeError(f"QMP {execute}: {msg['error']}")

    def hmp(self, command: str) -> str:
        return self.qmp_cmd("human-monitor-command", **{"command-line": command})

    # -- USB drives -----------------------------------------------------------------------------------
    def plug(self, name: str, image: Path, product: str, vendor: str = "Generic", serial: str | None = None,
             write_mbps: int = 0) -> None:
        """Attach an image file as a USB drive (like plugging in a USB disk)."""
        throttle = f",throttling.bps-write={write_mbps * 1024 * 1024}" if write_mbps else ""
        out = self.hmp(f"drive_add 0 if=none,id=blk-{name},file={image},format=raw,cache=unsafe{throttle}")
        if "OK" not in out:
            raise RuntimeError(out)
        serial = serial or hashlib.sha1(name.encode()).hexdigest()[:12].upper()
        self.qmp_cmd("device_add", driver="usb-bot", id=f"bot-{name}", bus="xhci.0", attached=False,
                     serial=serial)
        self.qmp_cmd("device_add", driver="scsi-hd", id=f"hd-{name}", bus=f"bot-{name}.0", drive=f"blk-{name}",
                     vendor=vendor[:8], product=product[:16], removable=True, serial=serial)
        self.qmp_cmd("qom-set", path=f"/machine/peripheral/bot-{name}", property="attached", value=True)
        self.drives[name] = {"image": str(image), "product": product}
        time.sleep(2)
        self.ssh("udevadm settle", check=False, quiet=True)

    def throttle(self, name: str, write_mbps: int) -> None:
        """Make a USB drive slower (0 = full speed), e.g. to photograph a backup in progress."""
        bps = write_mbps * 1024 * 1024
        self.qmp_cmd("block_set_io_throttle", id=f"hd-{name}", bps=0, bps_rd=0, bps_wr=bps,
                     iops=0, iops_rd=0, iops_wr=0)

    def unplug(self, name: str) -> None:
        """Pull the USB drive out (the guest should have unmounted it first)."""
        self.qmp_cmd("device_del", id=f"bot-{name}")
        for _ in range(50):
            if not any(d.get("qdev") == f"bot-{name}" for d in self.qmp_cmd("query-pci")) and \
                    f"bot-{name}" not in json.dumps(self.qmp_cmd("qom-list", path="/machine/peripheral")):
                break
            time.sleep(0.2)
        self.drives.pop(name, None)
        time.sleep(1)
        self.ssh("udevadm settle", check=False, quiet=True)

    # -- running things -------------------------------------------------------------------------------
    def _ssh_base(self, tty: bool = False) -> list[str]:
        return ["ssh", "-i", str(self.key), "-p", str(self.ssh_port), "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null", "-o", "LogLevel=ERROR", "-o", "ConnectTimeout=10",
                "-o", "ServerAliveInterval=15"] + (["-tt"] if tty else []) + [f"{self.user}@127.0.0.1"]

    def ssh(self, command: str, check: bool = True, capture: bool = False, timeout: float | None = None,
            quiet: bool = False, tty: bool = False, input: str | None = None) -> subprocess.CompletedProcess:
        if not quiet:
            log(f"$ {command[:200]}")
        try:
            r = subprocess.run(self._ssh_base(tty) + [command], capture_output=capture, text=True, timeout=timeout,
                               input=input, stdin=None if input is not None else subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            r = subprocess.CompletedProcess([], 124, "", "timeout")
        if check and r.returncode != 0:
            raise SystemExit(f"command failed in the VM ({r.returncode}): {command}\n{r.stdout or ''}{r.stderr or ''}")
        return r

    def put(self, src: Path, dest: str) -> None:
        """Copy a local file or folder into the VM (dest is a folder in the VM)."""
        src = Path(src)
        tar = subprocess.Popen(["tar", "-C", str(src.parent), "--exclude=__pycache__", "--exclude=*.img",
                                "--exclude=.git", "--exclude=site", "-cf", "-", src.name], stdout=subprocess.PIPE)  # noqa: E501
        r = subprocess.run(self._ssh_base() + [f"mkdir -p {dest} && tar -C {dest} -xf -"], stdin=tar.stdout)
        tar.wait()
        if r.returncode != 0:
            raise SystemExit(f"copy into the VM failed: {src}")

    def get(self, src: str, dest: Path) -> None:
        """Copy a folder from the VM into a local folder (its contents)."""
        dest = Path(dest)
        dest.mkdir(parents=True, exist_ok=True)
        ssh = subprocess.Popen(self._ssh_base() + [f"tar -C {src} -cf - ."], stdout=subprocess.PIPE)
        r = subprocess.run(["tar", "-C", str(dest), "-m", "-xf", "-"], stdin=ssh.stdout)
        ssh.wait()
        if r.returncode != 0:
            raise SystemExit(f"copy from the VM failed: {src}")


# ------------------------------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["fetch", "shell"])
    ap.add_argument("version", nargs="?", default="24.04")
    args = ap.parse_args()
    image = fetch(args.version)
    if args.action == "fetch":
        print(image)
        return 0
    work = CACHE / "shell"
    shutil.rmtree(work, ignore_errors=True)
    vm = VM(VM.overlay(image, work / "disk.qcow2"), work)
    vm.boot()
    try:
        subprocess.call(vm._ssh_base(tty=True))
    finally:
        vm.shutdown()
        shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
