"""Talk to the administrator helper (helper.py), started once with pkexec or sudo,
so the password is asked only once per task."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

from .util import DeucalionError

HELPER = Path(__file__).with_name("helper.py")
SYSTEM_HELPER = Path("/usr/local/libexec/deucalion/helper.py")   # installed by install.sh --system-helper


def helper_path() -> Path:
    """Prefer the root-owned system copy: code that runs as root should not be user-writable."""
    try:
        st = SYSTEM_HELPER.stat()
        if st.st_uid == 0 and not st.st_mode & 0o022:
            return SYSTEM_HELPER
    except OSError:
        pass
    return HELPER


class Privileged:
    def __init__(self, method: str | None = None):
        """method: 'pkexec', 'sudo', or 'direct' (tests / already root)."""
        if method is None:
            if os.geteuid() == 0:
                method = "direct"
            elif shutil.which("pkexec") and (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
                                             or not sys.stdin.isatty()):
                method = "pkexec"
            else:
                method = "sudo"
        self.method = method
        self.proc: subprocess.Popen | None = None
        self._id = 0

    def start(self) -> None:
        if self.proc is not None:
            return
        helper = helper_path()
        if helper == SYSTEM_HELPER:
            cmd = [str(SYSTEM_HELPER), "serve"]  # its own path is what the polkit policy names
        else:
            python = "/usr/bin/python3" if Path("/usr/bin/python3").exists() else sys.executable
            cmd = [python, "-I", str(helper), "serve"]
        if self.method == "pkexec":
            cmd = ["pkexec"] + cmd
        elif self.method == "sudo":
            cmd = ["sudo", "--prompt=[Deucalion] administrator password for %u: "] + cmd
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
        line = self.proc.stdout.readline()
        try:
            ready = json.loads(line) if line else {}
        except ValueError:
            ready = {}
        if not ready.get("ready"):
            self.proc.wait()
            self.proc = None
            raise DeucalionError("Administrator access was not granted.")

    def call(self, op: str, on_progress: Callable[[str], None] | None = None, **args):
        self.start()
        self._id += 1
        rid = self._id
        self.proc.stdin.write(json.dumps({"id": rid, "op": op, "args": args}) + "\n")
        self.proc.stdin.flush()
        for line in self.proc.stdout:
            msg = json.loads(line)
            if msg.get("id") != rid:
                continue
            if "progress" in msg:
                if on_progress:
                    on_progress(msg["progress"])
                continue
            if msg.get("ok"):
                return msg.get("result")
            raise DeucalionError(f"Administrator step '{op}' failed: {msg.get('error')}")
        raise DeucalionError("The administrator helper stopped unexpectedly.")

    def close(self) -> None:
        if self.proc is None:
            return
        try:
            self.proc.stdin.write(json.dumps({"op": "quit"}) + "\n")
            self.proc.stdin.close()
        except OSError:
            pass
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self.proc = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False
