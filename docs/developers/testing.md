# Tests

## Unit and integration tests

```bash
python3 -m unittest discover -s tests
```

They run on plain folders in a temporary directory (a fake home folder and a fake drive), so they need
no drive and no administrator rights. Tests that need GTK skip themselves where it isn't installed.

For every push and pull request, GitHub Actions runs them on Ubuntu 22.04 and 24.04, and once more on
a real exFAT volume (a disk image), with Ubuntu's own Python and PyGObject. The workflow is
`.github/workflows/tests.yml`.

Two optional variants:

```bash
# also run the suite on a real exFAT volume (for example a mounted disk image)
DEUCALION_TEST_EXFAT=/media/$USER/TEST python3 -m unittest discover -s tests

# also run the LUKS drive-setup test on a disk image (needs a desktop session, for UDisks)
DEUCALION_TEST_UDISKS=1 python3 -m unittest discover -s tests
```

| File | Covers |
|---|---|
| `test_backup.py` | Backups, Removed Files, partial backups, exclusions, restores. |
| `test_names.py`, `test_exfat.py` | exFAT-safe names; the suite on real exFAT. |
| `test_rebuild.py` | apt sources, and the rebuild steps with a fake administrator helper. |
| `test_drivesetup.py` | Drive setup, the READ-ME and tool copy, refusing the system disk, LUKS (opt-in). |
| `test_regressions.py`, `test_audit.py`, `test_review3.py` | Regression tests for problems found in three code reviews. |
| `test_docs_findings.py` | Regression tests for problems found while writing this documentation. |
| `test_gui_dialogs.py` | The app's password dialog, run for real with GTK's Broadway backend. |
| `test_screenshots.py` | The screenshot mode's entry syntax. |

!!! note "In the VS Code snap's terminal"
    The VS Code snap sets GTK variables that make GTK 4 crash. The GUI test removes them itself. To
    start the app from that terminal, unset `GSETTINGS_SCHEMA_DIR`, `GTK_PATH`, `GTK_EXE_PREFIX`,
    `GIO_MODULE_DIR`, `GTK_IM_MODULE_FILE`, `GDK_PIXBUF_MODULE_FILE`, `GDK_PIXBUF_MODULEDIR` and
    `LOCPATH` first.

## Test drives

To try Deucalion on a disk image instead of a real drive, attach it and register it with the hidden
`--allow-internal` option (`register` and `setup-drive` accept it); without it, a disk image on the
system disk is refused like any folder on the system disk:

```bash
truncate -s 2G /tmp/test.img && mkfs.exfat -L TEST /tmp/test.img
udisksctl loop-setup --no-user-interaction -f /tmp/test.img     # then mount it in Files
deucalion register /media/$USER/TEST --allow-internal --name Test
```

Detach it afterwards (`udisksctl unmount -b /dev/loopN` then `udisksctl loop-delete -b /dev/loopN`).
Never point tests at a drive that holds data.

## The torture test

`tests/torture.py` builds a random home folder full of awkward cases (odd names, case twins, links,
permissions, big and empty files). Then, for many rounds, it changes the folder, backs it up
(sometimes partially, sometimes killing the process at a random moment), and restores into a changed
copy (sometimes killing that too). After every step it checks that:

- a backup never changes the source;
- after a full backup, a restore reproduces the source exactly;
- every file content that was ever in a completed backup is still on the drive;
- `verify --full` passes, the manifest is intact, and the drive holds no untracked files;
- a restore never loses a local file, and restored files equal what was backed up.

```bash
python3 tests/torture.py --drive /media/$USER/TESTDRIVE --rounds 50 --seed 1 --kill
```

Use a mounted test filesystem (a disk image), never a drive with data on it.

## Manual checks (administrator password)

These ask for the administrator password once, and use test drives only.

| Script | Checks |
|---|---|
| `tests/manual/admin_checks.py /media/$USER/<test drive>` | A full backup with protected settings, with `/etc` fingerprinted before and after (it must not change); a symbolic-link attack on the helper; malicious requests to the helper (all must be refused). |
| `tests/manual/veracrypt_checks.py /media/$USER/<exFAT test drive>` | VeraCrypt create, back up, restore, lock, wrong password and unlock, for the folder, whole-drive and split layouts, on disk images. |
| `tests/manual/vm_rebuild_check.py /mnt/backup` | Runs **inside a throwaway VM**: rebuilds it from a test backup and checks that nothing local was lost, everything was restored, paths were updated only as whole paths, no package was removed, Ubuntu's own sources are untouched, and a second run changes nothing. |

For `vm_rebuild_check.py` you need a fresh Ubuntu VM. `docs/tools/vm.py` makes one: it downloads an
Ubuntu cloud image (checked against Ubuntu's signed `SHA256SUMS`), configures it with cloud-init, and
boots it with QEMU/KVM. `python3 docs/tools/vm.py shell 26.04` gives you a shell in a fresh 26.04 VM.
