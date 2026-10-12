# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Dimitrios Kafetzis

import os
import unittest
from pathlib import Path

from deucalion.backup import BackupJob
from deucalion.manifest import Manifest
from deucalion.verify import verify

from helpers import BackupTestCase, snapshot


def populate(t: BackupTestCase) -> None:
    t.write("Documents/report.pdf", b"%PDF" * 1000, mtime=1_600_000_000_123_456_789)
    t.write("Documents/notes.txt", "hello")
    t.write("Documents/Notes.txt", "HELLO")           # case-only twin
    t.write("Documents/a:b?.txt", "colon")            # not allowed on exFAT
    t.write("Documents/trail.", "dot")                # exFAT would drop the dot
    t.write("Documents/trail", "nodot")
    t.write(".ssh/id_ed25519", "secret", mode=0o600)
    os.chmod(t.home / ".ssh", 0o700)
    t.write("bin/tool.sh", "#!/bin/sh\necho hi\n", mode=0o755)
    t.write(".cache/big.bin", b"0" * 5000)            # excluded by default
    t.write("Music/song.mp3", b"\x01" * 3000)
    os.symlink("Documents/report.pdf", t.home / "latest-report")
    os.symlink("/nonexistent/target", t.home / "dangling")
    bad = os.fsdecode(b"weird\xffname")
    (t.home / bad).write_text("non-utf8 name")
    (t.home / "empty-dir").mkdir()


class BackupTest(BackupTestCase):
    def test_full_backup_then_nothing_to_do(self):
        populate(self)
        plan, res = self.backup()
        self.assertEqual(res.status, "completed")
        self.assertEqual(plan.copy_files, 10)
        self.assertNotIn("home/.cache/big.bin", self.stored_files())
        # second run: nothing changes
        plan2 = self.dry_run()
        self.assertTrue(plan2.nothing_to_do, [a.entry.path for a in plan2.actions + plan2.removals])

    def test_drive_names_are_exfat_safe_and_unique(self):
        populate(self)
        self.backup()
        names = os.listdir(self.target.root / "home" / "Documents")
        folded = [n.upper() for n in names]
        self.assertEqual(len(folded), len(set(folded)), names)
        for n in names:
            self.assertFalse(set(n) & set(':*?"<>|\\'), n)
            self.assertFalse(n.endswith("."), n)
        self.assertIn("a：b？.txt", names)
        self.assertIn("weird%FFname", os.listdir(self.target.root / "home"))

    def test_restore_roundtrip_is_exact(self):
        populate(self)
        self.backup()
        out = self.tmp / "restored"
        plan, res = self.restore(["home"], to=out)
        self.assertEqual(res.status, "completed", res.warnings)
        expected = snapshot(self.home)
        del expected[b".cache"], expected[b".cache/big.bin"]
        self.assertEqual(snapshot(out / self.home.name), expected)

    def test_changed_file_keeps_old_version_in_removed(self):
        populate(self)
        self.backup()
        self.write("Music/song.mp3", "v2")
        plan, res = self.backup()
        self.assertEqual((plan.changed_files, plan.new_files), (1, 0))
        self.assertEqual({"home/Music/song.mp3"}, self.removed_files())
        stored = self.target.root / "home/Music/song.mp3"
        self.assertEqual(stored.read_text(), "v2")

    def test_deleted_file_and_folder_go_to_removed(self):
        populate(self)
        self.backup()
        (self.home / "Music/song.mp3").unlink()
        (self.home / "Music").rmdir()
        (self.home / "Documents/trail").unlink()
        plan, res = self.backup()
        self.assertEqual(plan.removed_items, 2)
        self.assertEqual({"home/Music/song.mp3", "home/Documents/trail"}, self.removed_files())
        self.assertFalse((self.target.root / "home/Music").exists())

    def test_new_exclusion_moves_existing_copy_to_removed(self):
        populate(self)
        self.backup()
        self.cfg["home_excludes"].append("Music/")
        plan, _ = self.backup()
        self.assertEqual(plan.removed_items, 1)
        self.assertIn("home/Music/song.mp3", self.removed_files())

    def test_partial_backup_leaves_everything_else_alone(self):
        populate(self)
        self.backup()
        (self.home / "Music/song.mp3").unlink()          # would be removed by a full backup
        self.write("Documents/new.txt", "new")
        plan, res = self.backup(only=[str(self.home / "Documents")])
        self.assertEqual((plan.new_files, plan.removed_items), (1, 0))
        self.assertTrue((self.target.root / "home/Music/song.mp3").exists())
        self.assertTrue((self.target.root / "home/Documents/new.txt").exists())
        self.assertEqual(res.kind, "partial")

    def test_partial_backup_of_single_file(self):
        populate(self)
        self.backup()
        self.write("Documents/notes.txt", "v2")
        self.write("Documents/report.pdf", "v2")
        plan, _ = self.backup(only=[str(self.home / "Documents/notes.txt")])
        self.assertEqual([a.entry.path for a in plan.actions if a.op == "copy"], ["home/Documents/notes.txt"])

    def test_unreadable_file_is_kept_not_removed(self):
        if os.geteuid() == 0:
            self.skipTest("root can read everything")
        populate(self)
        self.backup()
        self.write("Music/song.mp3", "changed but unreadable", mode=0)
        self.addCleanup(os.chmod, self.home / "Music/song.mp3", 0o644)
        plan, res = self.backup()
        self.assertEqual(plan.removed_items, 0)
        self.assertTrue(any("song.mp3" in w for w in res.warnings))
        self.assertEqual(res.status, "completed_with_warnings")
        self.assertEqual((self.target.root / "home/Music/song.mp3").read_bytes(), b"\x01" * 3000)

    def test_file_becomes_folder(self):
        self.write("thing", "file")
        self.backup()
        (self.home / "thing").unlink()
        self.write("thing/inside.txt", "now a folder")
        plan, res = self.backup()
        self.assertEqual(res.status, "completed")
        self.assertIn("home/thing", self.removed_files())
        self.assertTrue((self.target.root / "home/thing/inside.txt").exists())
        self.assertTrue(self.dry_run().nothing_to_do)

    def test_case_only_rename(self):
        self.write("Photos/IMG.jpg", "1")
        self.backup()
        os.rename(self.home / "Photos/IMG.jpg", self.home / "Photos/img.jpg")
        self.backup()
        out = self.tmp / "r"
        self.restore(["home"], to=out)
        self.assertEqual(os.listdir(out / self.home.name / "Photos"), ["img.jpg"])

    def test_cancel_then_resume(self):
        for i in range(30):
            self.write(f"many/file{i:02d}.txt", f"content {i}" * 100)
        plan, res = self.backup(cancel_after_checks=25)
        self.assertEqual(res.status, "cancelled")
        self.assertLess(res.copied_files, 30)
        self.assertEqual(os.listdir(self.target.root / ".deucalion").count("staging"), 0)
        plan2, res2 = self.backup()
        self.assertEqual(res2.status, "completed")
        self.assertEqual(plan2.copy_files, 30 - res.copied_files)
        m = self.target.manifest()
        try:
            self.assertTrue(verify(self.target, m, full=True).ok)
        finally:
            m.close()

    def test_verify_detects_damage_and_missing(self):
        populate(self)
        self.backup()
        (self.target.root / "home/Music/song.mp3").write_bytes(b"\x02" * 3000)   # same size, other bytes
        (self.target.root / "home/bin/tool.sh").unlink()
        m = self.target.manifest()
        try:
            self.assertTrue(verify(self.target, m, full=False).missing)
            res = verify(self.target, m, full=True)
        finally:
            m.close()
        self.assertEqual(res.damaged, ["home/Music/song.mp3"])
        self.assertEqual(res.missing, ["home/bin/tool.sh"])
        # verify flagged both, so the next backup repairs them
        plan, _ = self.backup()
        self.assertEqual({a.entry.path for a in plan.actions if a.op == "copy"},
                         {"home/bin/tool.sh", "home/Music/song.mp3"})
        m = self.target.manifest()
        try:
            self.assertTrue(verify(self.target, m, full=True).ok)
        finally:
            m.close()

    def test_restore_moves_current_files_aside(self):
        populate(self)
        self.backup()
        self.write("Documents/notes.txt", "local edit")
        plan, res = self.restore([str(self.home / "Documents")])
        self.assertEqual(plan.count("overwrite"), 1)
        self.assertEqual((self.home / "Documents/notes.txt").read_text(), "hello")
        self.assertIsNotNone(res.undo_dir)
        aside = res.undo_dir / str(self.home / "Documents/notes.txt").lstrip("/")
        self.assertEqual(aside.read_text(), "local edit")
        # restoring again changes nothing
        plan2, _ = self.restore([str(self.home / "Documents")])
        self.assertEqual(plan2.count("overwrite") + plan2.count("create"), 0)

    def test_restore_to_new_username(self):
        populate(self)
        self.backup()
        new_home = self.tmp / "home" / "bob"
        new_home.mkdir()
        self.cfg["home_path"] = str(new_home)
        plan, res = self.restore(["home/Documents"])
        self.assertTrue((new_home / "Documents/report.pdf").exists())
        # old-style absolute paths still work
        plan, res = self.restore([str(self.home / "bin/tool.sh")])
        self.assertEqual(plan.roots[0][1], new_home / "bin/tool.sh")

    def test_manifest_keeps_permissions(self):
        populate(self)
        self.backup()
        m = Manifest(self.target.meta_dir / "manifest.sqlite")
        try:
            self.assertEqual(m.get("home/.ssh/id_ed25519").mode, 0o600)
            self.assertEqual(m.get("home/.ssh").mode, 0o700)
            self.assertEqual(m.get("home/latest-report").link, "Documents/report.pdf")
        finally:
            m.close()

    def test_check_drive_finds_files_deleted_from_drive(self):
        populate(self)
        self.backup()
        (self.target.root / "home/bin/tool.sh").unlink()
        self.assertTrue(self.dry_run().nothing_to_do)       # fast mode trusts the manifest
        job = BackupJob(self.cfg, self.target, check_drive=True)
        try:
            plan = job.scan()
            self.assertEqual([a.entry.path for a in plan.actions if a.op == "copy"], ["home/bin/tool.sh"])
        finally:
            job.close()

    def test_backup_of_other_machine_is_flagged(self):
        populate(self)
        self.backup()
        job = BackupJob(self.cfg, self.target)
        self.assertIsNone(job.identity_problem())
        self.cfg["home_path"] = str(self.tmp)
        self.assertIn("mirror this machine", BackupJob(self.cfg, self.target).identity_problem())

    def test_plan_is_not_kept_in_memory(self):
        populate(self)
        job = BackupJob(self.cfg, self.target)
        try:
            plan = job.scan()
            store = plan.actions.path
            self.assertTrue(store.exists())
            self.assertEqual(len(plan.actions), len(list(plan.actions)))
        finally:
            job.close()
        self.assertFalse(store.exists())

    def test_sneaky_edit_with_same_size_and_mtime_is_detected(self):
        p = self.write("doc.txt", "AAAA", mtime=1_600_000_000_000_000_000)
        self.backup()
        p.write_text("BBBB")                                   # same size
        os.utime(p, ns=(1_600_000_000_000_000_000, 1_600_000_000_000_000_000))  # mtime put back
        plan, _ = self.backup()
        self.assertEqual([a.entry.path for a in plan.actions if a.op == "copy"], ["home/doc.txt"])
        self.assertEqual((self.target.root / "home/doc.txt").read_text(), "BBBB")
        self.assertIn("home/doc.txt", self.removed_files())

    def test_chmod_only_does_not_recopy(self):
        p = self.write("big.bin", b"x" * 100000)
        self.backup()
        os.chmod(p, 0o600)
        plan, _ = self.backup()
        self.assertEqual(plan.copy_files, 0)
        self.assertEqual(Manifest(self.target.meta_dir / "manifest.sqlite").get("home/big.bin").mode, 0o600)

    def test_summary_written(self):
        populate(self)
        self.backup()
        s = self.target.read_summary()
        self.assertEqual(s["last_run"]["status"], "completed")
        self.assertEqual(s["user"]["home"], str(self.home))
        self.assertIn("last_full_backup", s)


class PosixTargetTest(BackupTest):
    name_policy = "posix"

    def test_drive_names_are_exfat_safe_and_unique(self):
        self.skipTest("names are stored as-is on Linux filesystems")


if __name__ == "__main__":
    unittest.main()
