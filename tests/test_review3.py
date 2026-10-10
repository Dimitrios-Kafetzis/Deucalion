"""Regression tests for the third safety review."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from deucalion import aptsources, deps, rebuild
from deucalion.util import DeucalionError

from helpers import BackupTestCase
from test_rebuild import FakePrivileged


class MirrorDetectionTest(unittest.TestCase):
    def kind(self, line):
        return aptsources.parse(line + "\n", "x.list")[0].kind

    def test_third_party_with_ubuntu_in_the_address(self):
        for line in ["deb https://dl.winehq.org/wine-builds/ubuntu/ noble main",
                     "deb http://packages.ros.org/ros2/ubuntu noble main",
                     "deb https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/7.0 multiverse",
                     "deb https://packages.microsoft.com/ubuntu/24.04/prod noble main"]:
            self.assertEqual(self.kind(line), "third-party", line)

    def test_real_mirror(self):
        text = ("deb http://ftp.example.org/ubuntu/ noble main universe\n"
                "deb http://ftp.example.org/ubuntu/ noble-updates main universe\n")
        self.assertEqual(aptsources.parse(text, "sources.list")[0].kind, "ubuntu")


@unittest.skipUnless(shutil.which("gpg"), "gpg needed")
class SignatureTest(unittest.TestCase):
    def test_revoked_key_is_rejected(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        home = tmp / "g"
        home.mkdir(mode=0o700)
        env = dict(os.environ, GNUPGHOME=str(home))
        run = lambda *a, **k: subprocess.run(["gpg", "--batch", "--quiet", "--pinentry-mode", "loopback",
                                              "--passphrase", "", *a], env=env, capture_output=True, **k)
        run("--quick-gen-key", "Test Signer <t@example.org>", "rsa2048", "sign", "never")
        fpr = [l.split(":")[9] for l in run("--with-colons", "--list-keys", text=True).stdout.splitlines()
               if l.startswith("fpr:")][0]
        deb = tmp / "pkg.deb"
        deb.write_bytes(b"package")
        run("--detach-sign", "-o", str(tmp / "pkg.deb.sig"), str(deb))
        run("--armor", "--export", "-o", str(tmp / "key.asc"), fpr)
        old = deps.VERACRYPT_FINGERPRINT
        deps.VERACRYPT_FINGERPRINT = fpr
        self.addCleanup(setattr, deps, "VERACRYPT_FINGERPRINT", old)
        (tmp / "w1").mkdir()
        deps.verify_signature(deb, tmp / "pkg.deb.sig", tmp / "key.asc", tmp / "w1")   # accepted
        # gpg pre-creates a revocation certificate for every new key; its first line is "disarmed"
        cert = (home / "openpgp-revocs.d" / f"{fpr}.rev").read_text().replace("\n:-----BEGIN", "\n-----BEGIN")
        (tmp / "rev.asc").write_text(cert)
        run("--import", str(tmp / "rev.asc"))
        run("--armor", "--export", "-o", str(tmp / "key-revoked.asc"), fpr)
        (tmp / "w2").mkdir()
        with self.assertRaises(DeucalionError):
            deps.verify_signature(deb, tmp / "pkg.deb.sig", tmp / "key-revoked.asc", tmp / "w2")


class LoopsTest(BackupTestCase):
    def test_removed_being_a_file_stops_cleanly(self):
        self.write("a.txt", "1")
        self.backup()
        (self.target.root / "_removed").write_text("not a folder")
        self.write("a.txt", "2")
        from deucalion.backup import BackupJob
        job = BackupJob(self.cfg, self.target)
        try:
            res = job.execute(job.scan())
        finally:
            job.close()
        self.assertEqual(res.status, "failed")
        self.assertIn("should be a folder", res.error)
        self.assertEqual((self.target.root / "home/a.txt").read_text(), "1")   # old copy still in place

    def test_undo_folder_being_a_dangling_link(self):
        os.symlink("/nonexistent-drive/x", self.home / "Deucalion-before-restore")
        m = self.target.manifest()
        self.addCleanup(m.close)
        ctx = rebuild.Context(self.cfg, self.target, m, privileged=FakePrivileged())
        ctx.new_home = str(self.home)
        with self.assertRaises(DeucalionError):
            ctx.undo_dir("paths")


class RestoreThroughLinkTest(BackupTestCase):
    def test_folder_that_is_now_a_link_gets_its_files(self):
        self.write("Docs/a.txt", "A")
        self.backup()
        other = self.tmp / "elsewhere"
        shutil.move(str(self.home / "Docs"), other)   # Docs moved elsewhere, a link left in its place
        os.symlink(other, self.home / "Docs")
        plan, res = self.restore([str(self.home / "Docs")])
        self.assertFalse((self.home / "Docs").is_symlink())
        self.assertEqual((self.home / "Docs/a.txt").read_text(), "A")
        self.assertEqual((other / "a.txt").read_text(), "A")       # the link's target is untouched


class ClutterTest(BackupTestCase):
    def test_macos_and_windows_files_are_left_alone(self):
        self.write("Docs/a.txt", "A")
        self.backup()
        for n in (".DS_Store", "._a.txt", "Thumbs.db"):
            (self.target.root / "home/Docs" / n).write_text("x")
        self.write("Docs/b.txt", "B")  # makes the backup look at that folder on the drive
        plan, _ = self.backup()
        self.assertEqual(plan.removed_items, 0)
        self.assertTrue((self.target.root / "home/Docs/.DS_Store").exists())



class SpaceEstimateTest(BackupTestCase):
    def test_small_files_count_whole_clusters(self):
        for i in range(20):
            self.write(f"small/{i}.txt", "x")
        plan = self.dry_run()
        cluster = os.statvfs(self.target.root).f_frsize
        self.assertEqual(plan.copy_bytes, 20)
        self.assertGreaterEqual(plan.copy_alloc, 20 * cluster)


if __name__ == "__main__":
    unittest.main()
