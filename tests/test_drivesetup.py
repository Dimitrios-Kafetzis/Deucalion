"""Drive setup tests.

The LUKS tests use a disk image attached through UDisks, which needs a desktop session.
They run only when DEUCALION_TEST_UDISKS=1 is set.
"""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from deucalion import drivesetup
from deucalion.config import Config
from deucalion.drivesetup import SetupRequest, label_for, missing_requirements, readme_text
from deucalion.target import Target
from deucalion.util import DeucalionError


class PureTest(unittest.TestCase):
    def test_label(self):
        self.assertEqual(label_for("My Backups 2026!"), "My Backups")
        self.assertEqual(label_for("ΑΒΓ"), "Deucalion")

    def test_requirements(self):
        req = SetupRequest("encrypt-all", device="/dev/sdx", method="luks", passphrase="short")
        codes = {c for c, _ in missing_requirements(req)}
        self.assertIn("password", codes)
        req = SetupRequest("encrypt-all", device="/dev/sdx", method="rot13", passphrase="long enough pw")
        self.assertIn("method", {c for c, _ in missing_requirements(req)})

    def test_readme_variants(self):
        self.assertIn("File Explorer", readme_text({"method": "none"}))
        vc = readme_text({"method": "veracrypt", "kind": "file", "file": "Deucalion-Backup.hc"})
        self.assertIn("Select File → Deucalion-Backup.hc", vc)
        self.assertIn("Not readable", readme_text({"method": "luks", "kind": "partition"}))
        self.assertIn("choose Cancel", readme_text({"method": "veracrypt", "kind": "partition"}))

    def test_tool_copy(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        drivesetup.install_tool_copy(tmp, None, {"method": "none"})
        self.assertTrue((tmp / "Deucalion-Tool/bin/deucalion").exists())
        self.assertTrue((tmp / "Deucalion-Tool/deucalion/cli.py").exists())
        self.assertFalse(list((tmp / "Deucalion-Tool").rglob("__pycache__")))
        out = subprocess.run([str(tmp / "Deucalion-Tool/bin/deucalion"), "--version"], capture_output=True, text=True)
        self.assertIn("Deucalion", out.stdout)
        self.assertTrue((tmp / "READ-ME-FIRST.txt").exists())

    def test_system_disk_refused(self):
        root_src = subprocess.run(["findmnt", "-rno", "SOURCE", "/"], capture_output=True, text=True).stdout.strip()
        disks = subprocess.run(["lsblk", "-sno", "PATH,TYPE", root_src], capture_output=True, text=True).stdout
        disk = next((l.split()[0] for l in disks.splitlines() if l.endswith("disk")), None)
        if not disk:
            self.skipTest("could not find the system disk")
        try:
            ds = drivesetup.DriveSetup(Config.load(Path(tempfile.mkdtemp()) / "c.json"))
        except DeucalionError:
            self.skipTest("UDisks not available")
        with self.assertRaises(DeucalionError):
            ds.check_disk(disk)


@unittest.skipUnless(os.environ.get("DEUCALION_TEST_UDISKS"), "set DEUCALION_TEST_UDISKS=1 (needs a desktop session)")
class LuksImageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="deucalion-ds-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        os.environ["DEUCALION_CONFIG_DIR"] = str(self.tmp / "config")
        os.environ["DEUCALION_STATE_DIR"] = str(self.tmp / "state")
        self.cfg = Config.load()
        self.ds = drivesetup.DriveSetup(self.cfg, out=lambda s: None)
        img = self.tmp / "disk.img"
        with open(img, "wb") as f:
            f.truncate(200 * 1024 ** 2)
        self.disk = self.ds.u.device(self.ds.u.loop_setup(str(img)))
        self.addCleanup(self._detach)

    def _detach(self):
        try:
            self.ds.release(self.disk)
        except DeucalionError:
            pass
        subprocess.run(["udisksctl", "loop-delete", "--no-user-interaction", "-b", self.disk], capture_output=True)

    def test_encrypt_all_luks_roundtrip(self):
        t = self.ds.run(SetupRequest("encrypt-all", device=self.disk, method="luks", name="T1",
                                     passphrase="correct horse battery", allow_internal=True))
        self.assertEqual(t.policy.kind, "posix")
        access = self.cfg["targets"][t.id]["access"]
        (t.root / "probe").write_text("x")
        self.ds.close_access(access)
        self.assertFalse(t.root.exists())
        with self.assertRaises(DeucalionError):
            self.ds.open(access, "wrong password!!")
        self.ds.open(access, "correct horse battery")
        self.assertEqual(Target.find(self.cfg, "T1").root.joinpath("probe").read_text(), "x")
        self.ds.close_access(access)


if __name__ == "__main__":
    unittest.main()
