"""Regression tests for the second (restore/rebuild) safety audit."""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from deucalion import aptsources, drivesetup, helper, rebuild
from deucalion.restore import Restorer

from helpers import BackupTestCase
from test_rebuild import FakePrivileged


class PathsStepTest(BackupTestCase):
    def test_only_whole_paths_change_and_rerun_is_harmless(self):
        old = self.tmp / "home" / "dim"
        old.mkdir(parents=True)
        self.cfg["home_path"] = str(old)
        (old / ".config").mkdir()
        (old / ".config/app.conf").write_text(f"a={old}/x\nb={self.tmp}/home/dimension/y\n")
        os.symlink(str(self.tmp / "dotfiles/bashrc"), old / ".bashrc")
        (self.tmp / "dotfiles").mkdir()
        (self.tmp / "dotfiles/bashrc").write_text(f"cd {old}\n")
        from deucalion.backup import ALL, BackupJob, Source
        from deucalion.config import Excluder
        recipe = self.tmp / "recipe"
        recipe.mkdir()
        (recipe / "info.json").write_text(json.dumps({"user": {"name": "dim", "home": str(old)}}))
        job = BackupJob(self.cfg, self.target)
        job.sources.append(Source("system", recipe, "recipe", Excluder([])))
        job.scope["system"] = ALL
        try:
            job.execute(job.scan())
        finally:
            job.close()
        new = self.tmp / "home" / "dimitris"
        new.mkdir()
        self.cfg["home_path"] = str(new)
        m = self.target.manifest()
        self.addCleanup(m.close)
        ctx = rebuild.Context(self.cfg, self.target, m, privileged=FakePrivileged())
        rebuild.HomeStep().apply(ctx, rebuild.HomeStep().plan(ctx).actionable, out=lambda s: None)
        plan = rebuild.PathsStep().plan(ctx)
        self.assertEqual({i.key for i in plan.items}, {".config/app.conf"})   # the symlinked dotfile is left alone
        rebuild.PathsStep().apply(ctx, plan.items, out=lambda s: None)
        text = (new / ".config/app.conf").read_text()
        self.assertEqual(text, f"a={new}/x\nb={self.tmp}/home/dimension/y\n")
        self.assertEqual(rebuild.PathsStep().plan(ctx).items, [])          # nothing left to change
        undo_copies = list((new / "Deucalion-before-restore").rglob("app.conf"))
        self.assertEqual(len(undo_copies), 1)
        self.assertIn(f"a={old}/x", undo_copies[0].read_text())


class RestoreSafetyTest(BackupTestCase):
    def test_folder_in_read_only_parent_is_never_copied_and_deleted(self):
        if os.geteuid() == 0:
            self.skipTest("root ignores permissions")
        os.makedirs(self.home / "P")
        os.symlink("/nonexistent", self.home / "P/Data")
        self.backup()
        (self.home / "P/Data").unlink()
        (self.home / "P/Data").mkdir()
        (self.home / "P/Data/photo.jpg").write_bytes(b"precious")
        os.chmod(self.home / "P", 0o555)
        self.addCleanup(os.chmod, self.home / "P", 0o755)
        plan, res = self.restore([str(self.home / "P/Data")])
        self.assertEqual((self.home / "P/Data/photo.jpg").read_bytes(), b"precious")
        self.assertTrue(any("left untouched" in w or "not restored" in w for w in res.warnings), res.warnings)

    def test_interrupted_copy_puts_the_original_back(self):
        self.write("f.bin", b"backup" * 100000)
        self.backup()
        self.write("f.bin", b"LOCAL ORIGINAL")
        m = self.target.manifest()
        self.addCleanup(m.close)
        r = Restorer(self.cfg, self.target, m)
        plan = r.plan([str(self.home / "f.bin")])

        def stop(_p):
            r.cancel.set()
        r.on_progress = stop
        res = r.execute(plan)
        self.assertEqual(res.status, "cancelled")
        self.assertEqual((self.home / "f.bin").read_bytes(), b"LOCAL ORIGINAL")
        self.assertEqual([p.name for p in self.home.iterdir() if "deucalion-restore" in p.name], [])


class DriveFilesTest(unittest.TestCase):
    def test_users_own_tool_folder_and_readme_are_kept(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        (tmp / "Deucalion-Tool").mkdir()
        (tmp / "Deucalion-Tool/my-notes.txt").write_text("mine")
        (tmp / "READ-ME-FIRST.txt").write_text("my own readme")
        dest = drivesetup.install_tool_copy(tmp, None, {"method": "none"})
        self.assertEqual((tmp / "Deucalion-Tool/my-notes.txt").read_text(), "mine")
        self.assertEqual((tmp / "READ-ME-FIRST.txt").read_text(), "my own readme")
        self.assertEqual(dest.name, "Deucalion-Tool (Deucalion)")
        self.assertTrue((tmp / "READ-ME-FIRST (Deucalion).txt").exists())
        drivesetup.install_tool_copy(tmp, None, {"method": "none"})   # updating our own copy is fine


class ReposTest(unittest.TestCase):
    def test_ubuntu_mirror_is_ubuntu(self):
        [r] = aptsources.parse("Types: deb\nURIs: http://ftp.cc.uoc.gr/mirrors/linux/ubuntu/packages/\n"
                               "Suites: noble noble-updates\nComponents: main universe\n", "ubuntu.sources")
        self.assertEqual(r.kind, "ubuntu")

    def test_helper_never_replaces_source_files(self):
        with self.assertRaises(helper.OpError):
            helper.op_apt_add_source(print, filename="ubuntu.sources", content="x", keys=[])
        with self.assertRaises(helper.OpError):
            helper.op_put_crontab(print, user="root", src="/etc/hostname", undo_dir="/tmp/x")


if __name__ == "__main__":
    unittest.main()
