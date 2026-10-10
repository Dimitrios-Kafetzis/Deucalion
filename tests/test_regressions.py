"""Regression tests for issues found in review."""

import os
import unittest

from deucalion.manifest import Manifest
from deucalion.util import DeucalionError

from helpers import BackupTestCase


class RegressionTest(BackupTestCase):
    def test_overlapping_restore_items_keep_the_undo_copy(self):
        self.write("A/b.txt", "backup version")
        self.backup()
        self.write("A/b.txt", "LOCAL ORIGINAL")
        plan, res = self.restore([str(self.home / "A"), str(self.home / "A/b.txt")])
        self.assertEqual(len(plan.roots), 1)
        aside = res.undo_dir / str(self.home / "A/b.txt").lstrip("/")
        self.assertEqual(aside.read_text(), "LOCAL ORIGINAL")
        self.assertEqual((self.home / "A/b.txt").read_text(), "backup version")

    def test_restore_items_with_the_same_destination_are_refused(self):
        self.write("x/notes.txt", "x")
        self.write("y/notes.txt", "y")
        self.backup()
        with self.assertRaises(DeucalionError):
            self.restore([str(self.home / "x/notes.txt"), str(self.home / "y/notes.txt")], to=self.tmp / "out")

    def test_restore_long_multibyte_name(self):
        name = "α" * 120 + ".txt"  # 244 bytes: valid on Linux
        self.write(name, "greek")
        self.backup()
        self.write(name, "changed")
        plan, res = self.restore([str(self.home / name)])
        self.assertEqual(res.status, "completed", res.warnings)
        self.assertEqual((self.home / name).read_text(), "greek")

    def test_unsearchable_folder_is_kept(self):
        if os.geteuid() == 0:
            self.skipTest("root can read everything")
        self.write("secret/a.txt", "a")
        self.backup()
        os.chmod(self.home / "secret", 0o644)  # listable, but entries can't be looked at
        self.addCleanup(os.chmod, self.home / "secret", 0o755)
        plan, _ = self.backup()
        self.assertEqual(plan.removed_items, 0)
        self.assertTrue((self.target.root / "home/secret/a.txt").exists())

    def test_empty_extra_folder_is_not_mirrored(self):
        data = self.tmp / "mnt-data"
        (data / "sub").mkdir(parents=True)
        (data / "sub/f.txt").write_text("data")
        self.cfg["extra_folders"] = [{"name": "data", "path": str(data), "excludes": []}]
        self.backup()
        (data / "sub/f.txt").unlink()
        (data / "sub").rmdir()  # like an unplugged drive: the mount point folder is empty
        plan, res = self.backup()
        self.assertEqual(plan.removed_items, 0)
        self.assertTrue(any("is empty" in w for w in plan.warnings))
        self.assertTrue((self.target.root / "extras/data/sub/f.txt").exists())

    def test_leftover_from_interrupted_run_is_not_duplicated(self):
        self.write("f.txt", "content")
        self.backup()
        m = Manifest(self.target.meta_dir / "manifest.sqlite")
        m.delete_tree("home/f.txt")  # as if the run died after copying, before recording
        m.close()
        plan, _ = self.backup()
        self.assertEqual(sorted(os.listdir(self.target.root / "home")), ["f.txt"])
        self.assertEqual(self.removed_files(), {"home/f.txt"})

    def test_partial_backup_with_file_that_became_folder(self):
        self.write("foo", "a file")
        self.backup()
        (self.home / "foo").unlink()
        self.write("foo/bar/x.txt", "now a folder")
        self.backup(only=[str(self.home / "foo/bar")])
        self.assertEqual(os.listdir(self.target.root / "home"), ["foo"])
        self.assertIn("home/foo", self.removed_files())
        self.assertTrue((self.target.root / "home/foo/bar/x.txt").exists())

    def test_partial_backup_with_new_item_keeps_out_of_scope_siblings(self):
        self.write("Docs/Personal/a.txt", "a")
        self.write("Docs/Work/b.txt", "b")
        self.backup()
        self.write("Docs/New/c.txt", "c")           # a new sibling: the drive folder gets listed
        plan, _ = self.backup(only=[str(self.home / "Docs/New")])
        self.assertEqual(plan.removed_items, 0)
        self.assertTrue((self.target.root / "home/Docs/Personal/a.txt").exists())
        self.assertTrue((self.target.root / "home/Docs/Work/b.txt").exists())
        m = self.target.manifest()
        try:
            from deucalion.verify import verify
            self.assertTrue(verify(self.target, m, full=True).ok)
        finally:
            m.close()

    def test_case_twin_leftovers_from_killed_run_are_cleaned(self):
        self.write("x/Notes", "1")
        self.write("x/notes", "2")
        self.backup()
        m = Manifest(self.target.meta_dir / "manifest.sqlite")
        m.delete_tree("home/x/Notes")
        m.delete_tree("home/x/notes")              # as if both were copied but never recorded
        m.close()
        self.backup()
        self.assertEqual(sorted(os.listdir(self.target.root / "home/x")), ["Notes", "notes (2)"])
        m = self.target.manifest()
        try:
            stored = {e.stored for e in m.iter_tree("home/x") if e.kind == "f"}
        finally:
            m.close()
        self.assertEqual(stored, {"home/x/Notes", "home/x/notes (2)"})

    def test_manifest_copy_after_completed_run(self):
        self.write("f.txt", "x")
        self.backup()
        self.assertTrue((self.target.meta_dir / "manifest.sqlite.bak").exists())


if __name__ == "__main__":
    unittest.main()
