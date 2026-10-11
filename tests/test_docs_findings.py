"""Regression tests for problems found while following the documentation step by step."""

import argparse
import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from deucalion import cli, drivesetup, util
from deucalion.config import Config
from deucalion.target import Target


def findmnt_json(mounts: list[tuple[str, str]]):
    """A fake util.run that answers findmnt like the real one: with -J (JSON) paths are exact; in its
    raw/list formats a space is written as \\x20, which is what used to be taken literally."""
    real_run = util.run

    def fake(cmd, *a, **k):
        if cmd[0] != "findmnt":
            return real_run(cmd, *a, **k)
        rows = [{"target": t, "source": s, "fstype": "exfat", "options": "rw"} for t, s in mounts]
        if "--target" in cmd:
            path = cmd[cmd.index("--target") + 1]
            best = max((r for r in rows if path == r["target"] or path.startswith(r["target"] + "/")),
                       key=lambda r: len(r["target"]), default=None)
            rows = [best] if best else []
        if "--source" in cmd:
            src = cmd[cmd.index("--source") + 1]
            rows = [r for r in rows if r["source"] == src]
        if "-J" in cmd:
            out = json.dumps({"filesystems": rows}) if rows else ""
        else:  # e.g. findmnt -rno TARGET
            col = "source" if "SOURCE" in cmd else "target"
            out = "".join(r[col].replace(" ", "\\x20") + "\n" for r in rows)
        return util.subprocess.CompletedProcess(cmd, 0 if rows else 1, out, "")
    return fake


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="deucalion-docs-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        os.environ["DEUCALION_CONFIG_DIR"] = str(self.tmp / "config")
        os.environ["DEUCALION_STATE_DIR"] = str(self.tmp / "state")


class RegisterKeepsUnlockInformation(Base):
    def test_registering_again_keeps_how_to_unlock_the_drive(self):
        """'deucalion register <drive> --default' (the way to change the default drive) used to replace
        the drive's settings, losing how to unlock it: open/close/backup then treated it as unencrypted."""
        cfg = Config.load()
        (self.tmp / "drive").mkdir()
        (self.tmp / "other").mkdir()
        target = Target.create(self.tmp / "drive", name="Alex Backup", allow_internal=True)
        target.register(cfg, allow_internal=True)
        access = {"method": "veracrypt", "kind": "partition", "partuuid": "1234", "mount_name": "Alex Backup"}
        cfg["targets"][target.id]["access"] = access
        other = Target.create(self.tmp / "other", name="Spare", allow_internal=True)
        other.register(cfg, allow_internal=True, make_default=True)
        cfg.save()

        with contextlib.redirect_stdout(io.StringIO()):
            cli.main(["register", str(self.tmp / "drive"), "--default", "--allow-internal"])

        cfg = Config.load()
        self.assertEqual(cfg["default_target"], target.id)
        self.assertEqual(cfg["targets"][target.id]["access"], access)


class MountPointsWithSpaces(Base):
    """Drives named with a space ('Alex Backup') are mounted at /media/<user>/Alex Backup. findmnt's -r
    output writes that as 'Alex\\x20Backup', which used to be taken literally."""

    def test_discover_finds_an_encrypted_backup_on_a_drive_with_a_space(self):
        plain = self.tmp / "media" / "Alex Backup1"
        (plain / drivesetup.TOOL_DIRNAME).mkdir(parents=True)
        info = {"method": "veracrypt", "kind": "partition", "partuuid": "1234", "version": "0.2.0"}
        (plain / drivesetup.TOOL_DIRNAME / "drive.json").write_text(json.dumps(info))
        with mock.patch.object(util, "run", findmnt_json([("/", "/dev/vda1"), (str(plain), "/dev/sda1")])), \
                mock.patch.object(drivesetup, "_REMOVABLE_MOUNTS", (str(self.tmp / "media") + "/",)):
            found = drivesetup.discover()
        self.assertEqual([root for root, _ in found], [plain])

    def test_mount_points_of_a_device_keep_spaces(self):
        with mock.patch.object(util, "run", findmnt_json([("/media/alex/Alex Backup1", "/dev/sda1"),
                                                          ("/", "/dev/vda1")])):
            self.assertEqual(util.mount_points("/dev/sda1"), ["/media/alex/Alex Backup1"])
            self.assertEqual(util.mount_points(), ["/media/alex/Alex Backup1", "/"])

    def test_close_unmounts_an_unencrypted_drive_with_a_space_in_its_name(self):
        cfg = Config.load()
        mp = self.tmp / "media" / "My Backup"
        mp.mkdir(parents=True)
        target = Target.create(mp, name="My Backup", allow_internal=True)
        target.register(cfg, allow_internal=True)
        cfg["targets"][target.id]["access"] = {"method": "none"}
        cfg.save()
        fake_u = mock.Mock()
        fake_u.resolve.side_effect = lambda dev: f"udisks:{dev}"
        fake_ds = mock.Mock(u=fake_u)
        with mock.patch.object(util, "run", findmnt_json([(str(mp), "/dev/sdb1"), ("/", "/dev/vda1")])), \
                mock.patch.object(cli, "run", util.run), \
                mock.patch.object(cli, "_REMOVABLE_MOUNTS", (str(self.tmp / "media") + "/",)), \
                mock.patch.object(drivesetup, "DriveSetup", return_value=fake_ds), \
                contextlib.redirect_stdout(io.StringIO()):
            code = cli.cmd_close(Config.load(), argparse.Namespace(target=None))
        self.assertEqual(code, 0)
        fake_u.unmount.assert_called_once_with("udisks:/dev/sdb1")


if __name__ == "__main__":
    unittest.main()
