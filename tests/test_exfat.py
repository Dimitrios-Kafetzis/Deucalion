"""Runs the whole backup/restore suite against a real exFAT filesystem.

Set DEUCALION_TEST_EXFAT to the mount point of an exFAT test volume, e.g. a
disk image created with:
    truncate -s 256M test.img && mkfs.exfat test.img
    udisksctl loop-setup -f test.img        # mounts it under /media/$USER/
Skipped when the variable is not set.
"""

import os
import unittest
from pathlib import Path

import test_backup
from deucalion.util import fs_type

MOUNT = os.environ.get("DEUCALION_TEST_EXFAT")


@unittest.skipUnless(MOUNT, "set DEUCALION_TEST_EXFAT to an exFAT mount point")
class ExfatDriveTest(test_backup.BackupTest):
    drive_dir = Path(MOUNT) if MOUNT else None

    def setUp(self):
        self.assertEqual(fs_type(MOUNT), "exfat")
        super().setUp()
        self.assertEqual(self.target.policy.kind, "exfat")  # chosen automatically
