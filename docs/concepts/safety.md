# How your data is protected

These are the promises Deucalion makes about your data, and how they were checked.

## The promises

**A backup only reads your computer.** It never changes, moves or deletes anything on your
computer. Tests compare every file's content, permissions and change time before and after each
backup.

**Nothing on the drive is deleted by a backup.** Changed and deleted files go to
[Removed Files](mirror-and-removed.md). A test checks that every version ever backed up is still
on the drive afterwards, either in the backup or in Removed Files.

**Backups go only to a drive you registered.** A backup drive is recognised by an identifier
written on it, not by its name or where it is mounted. Deucalion refuses to back up to the disk your
system runs from: *"… is on the same disk as your system. A backup there would be lost together
with the system. Choose an external drive."*

**A restore never loses a file on your computer.** Anything a restore replaces is first *renamed*
into the undo folder `~/Deucalion-before-restore/` (never copied and then deleted). If a restore
fails or is stopped, the original is put back. Folders where another drive is mounted are never
touched. Every restore shows a preview first.

**A rebuild keeps what it replaces.** Desktop settings, crontabs and `/etc` files are saved first.
Packages are never removed. Ubuntu's own software sources are never changed. Paths in settings are
updated only as whole paths (`/home/alex/…` is updated, `/home/alexandra` is not). Running a
rebuild twice changes nothing more.

**Interruptions are safe.** You can stop a backup, kill it, unplug the drive or let the drive run
full at any moment: the next backup repairs the backup, with no duplicates and no damage. See
[FAQ: power cut or unplugged drive](../troubleshooting/faq.md#the-power-went-off-or-i-unplugged-the-drive-during-a-backup).

**Erasing a drive needs you to type its name.** Preparing a drive in a way that erases it asks you
to type its device name (such as `sdb`). Your system disk is never offered, and the administrator
helper checks this again on its own.

**Edits that keep the same size and date are still found.** Some programs change a file and put its
modification date back. Deucalion also checks the file's *change time*, which programs can't set,
and compares the content when in doubt.

**VeraCrypt is installed only after its signature is checked** against VeraCrypt's own key (see
[How VeraCrypt is installed](../getting-started/install.md#how-veracrypt-is-installed)).

**Your backup password is never stored.** Deucalion passes it straight to the encryption software
and forgets it.

## How this was tested

- **Unit and integration tests** (`tests/`): on plain folders, real exFAT and LUKS volumes, including
  regression tests for every problem found in three independent code reviews and while writing this
  documentation.
- **A randomized torture test** (`tests/torture.py`): random folders full of awkward names, and
  backups and restores killed at random moments. Hundreds of runs passed on plain, exFAT and LUKS
  drives.
- **Administrator checks** (`tests/manual/admin_checks.py`, `veracrypt_checks.py`): backups with
  protected settings, with `/etc` fingerprinted before and after; an attack on the administrator
  helper with symbolic links, and refused malicious requests; VeraCrypt create, open, wrong password
  and close in all three encrypted layouts.
- **A full rebuild of a fresh Ubuntu 26.04 virtual machine** from a 24.04 backup, under a different
  user name, run twice (`tests/manual/vm_rebuild_check.py`).
- **A real-data backup** of about 700,000 files (49 GB): verified, restored and compared byte for
  byte.
- **This documentation**: every tutorial was followed step by step, in the app and in the terminal,
  on throwaway Ubuntu 24.04 and 26.04 virtual machines with demo drives. The screenshots and the
  terminal output on this site come from those runs.

See [Tests](../developers/testing.md) for how to run them.

## What Deucalion can't protect you from

- **A forgotten password.** An encrypted backup can't be opened without its password. Nobody can
  recover it.
- **One drive is one point of failure.** If your only backup drive breaks, is lost or is stolen
  together with your computer, the backup is gone. Keep the drive somewhere else when you don't use
  it, and consider a second drive.
- **Files you never backed up.** Deucalion runs only when you start it.
