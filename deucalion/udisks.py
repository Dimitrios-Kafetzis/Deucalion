"""A small UDisks2 client (Ubuntu's disk service), used to partition, format, encrypt
(LUKS), unlock and mount drives *without* administrator rights: UDisks allows the
logged-in user to do this on removable, non-system drives."""

from __future__ import annotations

import os
import time

from .util import DeucalionError, run

UD = "org.freedesktop.UDisks2"
MANAGER = "/org/freedesktop/UDisks2/Manager"
GPT_DATA = "ebd0a0a2-b9e5-4433-87c0-68b6b72699c7"    # "Microsoft basic data": exFAT that every OS shows
GPT_LINUX = "0fc63daf-8483-4772-8e79-3d69d8477de4"   # hidden from Windows/macOS (encrypted parts)
LONG = 60 * 60 * 1000  # formatting a big drive can take a while


class UDisks:
    def __init__(self):
        try:
            import gi  # noqa: F401
            from gi.repository import Gio, GLib
        except ImportError as e:
            raise DeucalionError("The python3-gi package is needed to manage drives.") from e
        self.Gio, self.GLib = Gio, GLib
        self.bus = Gio.bus_get_sync(Gio.BusType.SYSTEM)

    # -- plumbing ------------------------------------------------------------------------------------
    def _v(self, value):
        GLib = self.GLib
        if isinstance(value, bool):
            return GLib.Variant("b", value)
        if isinstance(value, int):
            return GLib.Variant("t", value)
        return GLib.Variant("s", str(value))

    def opts(self, **kw) -> dict:
        """Python names to UDisks option names: encrypt_type -> encrypt.type, take_ownership -> take-ownership."""
        out = {}
        for k, v in kw.items():
            key = "encrypt." + k[8:] if k.startswith("encrypt_") else k.replace("_", "-")
            out[key] = self._v(v)
        return out

    def call(self, path: str, iface: str, method: str, sig: str | None, args, timeout: int = 120_000):
        try:
            res = self.bus.call_sync(UD, path, f"{UD}.{iface}", method,
                                     self.GLib.Variant(sig, args) if sig else None, None,
                                     self.Gio.DBusCallFlags.ALLOW_INTERACTIVE_AUTHORIZATION, timeout, None)
        except self.GLib.Error as e:
            msg = e.message.split(": ", 1)[-1] if "GDBus.Error" in e.message else e.message
            raise DeucalionError(msg) from None
        return res.unpack() if res is not None else ()

    def props(self, path: str, iface: str) -> dict:
        try:
            res = self.bus.call_sync(UD, path, "org.freedesktop.DBus.Properties", "GetAll",
                                     self.GLib.Variant("(s)", (f"{UD}.{iface}",)), None,
                                     self.Gio.DBusCallFlags.NONE, -1, None)
        except self.GLib.Error:
            return {}
        return res.unpack()[0]

    def resolve(self, device: str) -> str:
        res = self.call(MANAGER, "Manager", "ResolveDevice", "(a{sv}a{sv})",
                        ({"path": self.GLib.Variant("s", os.path.realpath(device))}, {}))
        if not res or not res[0]:
            raise DeucalionError(f"{device} is not known to the disk service.")
        return res[0][0]

    def device(self, obj: str) -> str:
        dev = self.props(obj, "Block").get("Device", b"")
        return bytes(dev).rstrip(b"\0").decode() if dev else ""

    @staticmethod
    def settle() -> None:
        run(["udevadm", "settle"], timeout=30)

    def can_format(self, fstype: str) -> tuple[bool, str]:
        ok, missing = self.call(MANAGER, "Manager", "CanFormat", "(s)", (fstype,))
        return bool(ok), missing

    # -- operations ---------------------------------------------------------------------------------
    def format(self, obj: str, fstype: str, **options) -> None:
        self.call(obj, "Block", "Format", "(sa{sv})", (fstype, self.opts(**options)), LONG)
        self.settle()

    def create_partition(self, disk: str, size: int, ptype: str, name: str, offset: int = 0,
                         fstype: str | None = None, **fs_options) -> str:
        if fstype:
            obj = self.call(disk, "PartitionTable", "CreatePartitionAndFormat", "(ttssa{sv}sa{sv})",
                            (offset, size, ptype, name, {}, fstype, self.opts(**fs_options)), LONG)[0]
        else:
            obj = self.call(disk, "PartitionTable", "CreatePartition", "(ttssa{sv})",
                            (offset, size, ptype, name, {}))[0]
        self.settle()
        return obj

    def partition_info(self, obj: str) -> dict:
        return self.props(obj, "Partition")

    def cleartext(self, crypt_obj: str) -> str | None:
        o = self.props(crypt_obj, "Encrypted").get("CleartextDevice", "/")
        return None if o in ("/", "") else o

    def unlock(self, crypt_obj: str, passphrase: str) -> str:
        existing = self.cleartext(crypt_obj)
        if existing:
            return existing
        try:
            obj = self.call(crypt_obj, "Encrypted", "Unlock", "(sa{sv})", (passphrase, {}))[0]
        except DeucalionError as e:
            if "passphrase" in str(e).lower() or "key" in str(e).lower():
                raise DeucalionError("Wrong password.") from None
            raise
        self.settle()
        return obj

    def lock(self, crypt_obj: str) -> None:
        if self.cleartext(crypt_obj):
            self.call(crypt_obj, "Encrypted", "Lock", "(a{sv})", ({},))
            self.settle()

    def mountpoints(self, fs_obj: str) -> list[str]:
        mps = self.props(fs_obj, "Filesystem").get("MountPoints", [])
        return [bytes(m).rstrip(b"\0").decode() for m in mps]

    def mount(self, fs_obj: str) -> str:
        mps = self.mountpoints(fs_obj)
        if mps:
            return mps[0]
        return self.call(fs_obj, "Filesystem", "Mount", "(a{sv})", ({},))[0]

    def unmount(self, fs_obj: str) -> None:
        """Unmount, retrying for a few seconds: file indexers often open a freshly mounted drive."""
        for attempt in range(10):
            if not self.mountpoints(fs_obj):
                return
            try:
                self.call(fs_obj, "Filesystem", "Unmount", "(a{sv})", ({},))
                return
            except DeucalionError as e:
                if "busy" not in str(e).lower():
                    raise
                time.sleep(1)
        raise DeucalionError("The drive is in use. Close any window or program that shows its files, "
                             "then try again.")

    def loop_setup(self, path: str) -> str:
        """Attach a file as a block device (the device goes away by itself when locked/unused)."""
        res = run(["udisksctl", "loop-setup", "--no-user-interaction", "-f", path])
        if res.returncode != 0:
            raise DeucalionError(res.stderr.strip() or "Could not attach the encrypted folder.")
        dev = res.stdout.strip().rsplit(" ", 1)[-1].rstrip(".")
        self.settle()
        return self.resolve(dev)

    def loop_for_file(self, path: str) -> str | None:
        res = run(["losetup", "-j", os.path.realpath(path), "-O", "NAME", "-n"])
        dev = res.stdout.strip().splitlines()[0] if res.returncode == 0 and res.stdout.strip() else ""
        return self.resolve(dev) if dev else None

    def wait_for(self, predicate, timeout: float = 10.0):
        end = time.monotonic() + timeout
        while True:
            value = predicate()
            if value or time.monotonic() > end:
                return value
            time.sleep(0.2)
