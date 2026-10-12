# Deucalion

Back up your Ubuntu machine to an external drive, and rebuild it later: on a new
Ubuntu LTS or on a new machine, even with a different username.

- **Plain files on the drive.** The backup is normal folders and files you can open on
  Linux, macOS and Windows, with no special tool needed.
- **Nothing is lost silently.** Files that changed or were deleted on your machine are
  moved to `_removed/` on the drive, never deleted. Only you empty it.
- **Exact restores.** Permissions, symlinks and file names that exFAT can't store are kept
  in a manifest on the drive and put back when you restore.
- **Safe by default.** Every restore shows a preview first, and anything it would overwrite
  is kept in `~/Deucalion-before-restore/`.
- **Rebuild a machine.** A full backup also saves a *system recipe* (packages, repositories,
  snaps, desktop settings, services, groups, changed `/etc` files, Wi-Fi/VPN connections).
  `deucalion rebuild` replays it on a new machine or a newer Ubuntu, step by step, with a
  preview at every step.

- **Optional encryption.** Encrypt the whole drive, an encrypted part of it, or an encrypted
  folder on it: VeraCrypt (opens on Linux, macOS and Windows) or LUKS (Linux only).

> **Status:** version 0.2: backup, restore, rebuild, drive setup and encryption, as a GNOME app and
> from the command line, after an extensive safety campaign (see *How Deucalion protects your data*).

## Documentation

The full documentation, with step-by-step tutorials for the app and the command line, is at
**https://dimitrios-kafetzis.github.io/Deucalion/** (its source is in [`docs/`](docs/)).
To read it locally:

```bash
python3 -m venv ~/.venvs/deucalion-docs
~/.venvs/deucalion-docs/bin/pip install -r docs/requirements.txt
~/.venvs/deucalion-docs/bin/mkdocs serve      # then open http://127.0.0.1:8000
```

## Install

```bash
git clone https://github.com/Dimitrios-Kafetzis/Deucalion.git
cd Deucalion
./install.sh                    # checks/installs what is needed (asks before installing), then
                                # adds the app menu entry and the 'deucalion' command
./install.sh --system-helper    # recommended: also installs the administrator helper system-wide
```

`--system-helper` asks for your password once. It puts a root-owned copy of the small
administrator helper in `/usr/local/libexec/deucalion/`, so code that runs as root can't be
changed by other programs. It also adds a clear password prompt ("Deucalion needs administrator
access…") that is remembered for a few minutes. `./install.sh --uninstall` removes everything
except your backups and settings.

You can also run Deucalion without installing it: `bin/deucalion` (from a clone, or from the
`Deucalion-Tool` folder on a backup drive).

### Requirements

Ubuntu 22.04 or newer (Python 3.10+). `./install.sh` (or `deucalion deps --install`) checks
everything and installs what is missing: the GTK/libadwaita libraries, UDisks, cryptsetup,
`exfatprogs`, dconf and gnupg. It can also install VeraCrypt (needed only for
VeraCrypt-encrypted drives), downloading the official package and checking its signature first.

## Quick start

Run `bin/deucalion` with no arguments to open the app (GTK4/libadwaita, follows your light/dark
theme): Overview, Back Up, Restore, Rebuild, Drives, Removed Files and Settings. Everything below
can also be done from the command line:

```bash
# from this folder (or from the Deucalion-Tool folder on your backup drive)
bin/deucalion drives                               # see your connected drives
bin/deucalion setup-drive                          # prepare a drive: format and/or encrypt it
#   …or use a drive as it is:  bin/deucalion register /media/$USER/MyDrive
bin/deucalion backup --dry-run                     # see what would be copied (largest folders too)
bin/deucalion backup                               # back up
bin/deucalion status
```

### Common tasks

| Task | Command |
|---|---|
| Back up only some folders | `deucalion backup --only ~/Documents ~/Pictures` |
| Save a selection for later | `deucalion profile add work ~/Projects ~/Documents/Work` then `deucalion backup --profile work` |
| Leave something out | `deucalion exclude add "Videos/" "*.iso"` |
| Also back up a folder outside home | `deucalion folder add /srv/data` |
| See what's in the backup | `deucalion ls ~/Documents` |
| Restore a file or folder | `deucalion restore ~/Documents/report.pdf` |
| Restore somewhere else | `deucalion restore ~/Documents --to ~/Desktop/recovered` |
| Rebuild a new machine | `deucalion rebuild` (`--dry-run` to only look, `--step packages` to redo one step) |
| Back up without the admin password | `deucalion backup --no-admin` (network connections and root-only `/etc` files are then skipped) |
| Unlock / lock an encrypted drive | `deucalion open` / `deucalion close` (other commands ask for the password when needed) |
| Check the backup is intact | `deucalion verify` (sizes) or `deucalion verify --full` (checksums) |
| See / free space in `_removed/` | `deucalion removed` / `deucalion removed empty` |

Press Ctrl+C once to stop safely; the next backup continues where it stopped.

### Exclusion patterns

Patterns are relative to your home folder:

- `node_modules/`: a folder with that name, anywhere
- `*.iso`: files matching the pattern, anywhere
- `.local/share/Trash/`: that exact path
- `.config/**/Cache/`: `**` matches any number of folders

Caches, the Trash and browser caches are excluded by default (`deucalion exclude list`).

## What is on the drive

```
Deucalion-Backup/
├── backup.json          which machine/user this is, last run, results
├── home/                your home folder, as normal files
├── system/              the system recipe (readable text files, see system/README.txt)
├── extras/              extra folders you added
├── _removed/<date>/     old versions and deleted files, until you empty it
└── .deucalion/          manifest (permissions, original names, checksums) and logs
```

On exFAT, a name that isn't allowed there is stored with a look-alike character
(`report: v2?.txt` → `report： v2？.txt`). Names that differ only in case get a counter
(`Notes.txt` / `notes (2).txt`). Restoring always uses the original names.

## Rebuilding a machine

On the new machine (fresh Ubuntu install, any username):

1. Plug in the backup drive and open a terminal in its `Deucalion-Tool` folder (or clone this repo).
2. Encrypted drive: `bin/deucalion open` (finds and registers the backup).
   Unencrypted drive: `bin/deucalion register /media/$USER/<drive>`.
3. `bin/deucalion rebuild`.

The steps are:

1. **Check** the backup against this machine.
2. **Repositories**: each one is checked for the new Ubuntu version.
3. **Packages**: apt, snaps, and `.deb` files found in your Downloads.
4. **Home folder**: choose which folders to restore.
5. **Paths**: if your username changed, paths in settings files are updated.
6. **Desktop settings**.
7. **`/etc` files**: each one shown as a diff before you accept it.
8. **Groups, crontabs, services and network connections**.

Every step can be skipped, and `deucalion rebuild` continues where you stopped.

## Drive layouts

`deucalion setup-drive` offers:

| Layout | Erases the drive? | Readable on |
|---|---|---|
| Encrypt the whole drive | yes | VeraCrypt: Linux/macOS/Windows with VeraCrypt · LUKS: Linux |
| Encrypted part + normal exFAT part | yes | encrypted part as above; normal part everywhere |
| Encrypted folder (container file) on the drive | no | as above |
| exFAT, no encryption | yes | everywhere |
| Use the drive as it is (e.g. NTFS) | no | depends on the filesystem |

Plain exFAT and LUKS drives are prepared through Ubuntu's disk service, with no
administrator password. Creating or opening a VeraCrypt volume needs
[VeraCrypt](https://www.veracrypt.fr/en/Downloads.html) and the administrator password.
Each prepared drive gets a `READ-ME-FIRST.txt` and a copy of Deucalion on its
unencrypted part.

## How Deucalion protects your data

- **Backups only read your computer.** Tests compare every file's contents, permissions and
  change time before and after each backup.
- **Nothing on the drive is deleted by a backup.** Changed and deleted files go to `_removed/`,
  and a test checks that every version ever backed up is still on the drive afterwards.
- **Restores never lose a local file.** Anything replaced is renamed into
  `~/Deucalion-before-restore/` (never copied-then-deleted). If a restore fails or is stopped,
  the original is put back. Mount points are never touched.
- **Rebuilds keep what they replace.**
  - Desktop settings, crontabs and `/etc` files are saved first.
  - Packages are never removed (`apt --no-remove`).
  - Your system's own apt sources are never changed.
  - Paths are updated only as whole paths.
  - Running a rebuild twice changes nothing.
- **Interruptions are safe.** You can kill the process, unplug the drive or let it run full
  at any moment: the next run repairs the backup, with no duplicates or damage.
- **Administrator work is narrow.**
  - It goes through one small helper with a fixed list of checked operations, which refuses to
    touch the system disk.
  - The installed copy must match the app's own copy exactly.
  - VeraCrypt is installed only after its signature is checked against VeraCrypt's pinned key.
- **Edits that keep the same size and time are still caught.** The change time is checked, and
  the contents are compared when in doubt.

### How this was tested

- **Unit and integration tests** (`tests/`): on plain folders, real exFAT and LUKS volumes,
  including regression tests for every issue found in three independent code reviews.
- **A randomized torture test** (`tests/torture.py`): random trees with awkward names, and
  backups and restores killed at random moments. Hundreds of runs passed on plain, exFAT and
  LUKS drives.
- **Administrator checks** (`tests/manual/admin_checks.py`, `veracrypt_checks.py`):
  - protected-settings backups, with `/etc` fingerprinted before and after;
  - a symlink attack on the root helper, and refused malicious requests;
  - VeraCrypt create, open, wrong password and close in all three layouts.
- **A full rebuild of a fresh Ubuntu 26.04 virtual machine** from a 24.04 backup, under a
  different username, run twice (`tests/manual/vm_rebuild_check.py`).
- **A real-data backup** of about 700,000 files (49 GB): verified, restored and compared
  byte for byte.

## Development

See [For developers](docs/developers/index.md) and the [plan for version 1](docs/developers/plan.md).

```bash
python3 -m unittest discover -s tests            # unit + integration tests
# also run the suite on a real exFAT volume:
DEUCALION_TEST_EXFAT=/media/$USER/TEST python3 -m unittest discover -s tests
# and the LUKS drive-setup test on a disk image (needs a desktop session):
DEUCALION_TEST_UDISKS=1 python3 -m unittest discover -s tests
```
