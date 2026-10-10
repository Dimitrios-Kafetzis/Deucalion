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

> **Status:** milestone 1 of 5 (core backup and restore, command line). The system rebuild,
> drive encryption and the GNOME app are next. See [docs/PLAN.md](docs/PLAN.md).

## Requirements

Ubuntu 22.04 or newer with Python 3.10+. Nothing to install: Deucalion uses only what
Ubuntu ships with.

## Quick start

```bash
# from this folder (later: from the copy on your backup drive)
bin/deucalion drives                               # see your connected drives
bin/deucalion register /media/$USER/MyDrive        # use this drive for backups
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
├── extras/              extra folders you added
├── _removed/<date>/     old versions and deleted files, until you empty it
└── .deucalion/          manifest (permissions, original names, checksums) and logs
```

On exFAT, a name that isn't allowed there is stored with a look-alike character
(`report: v2?.txt` → `report： v2？.txt`). Names that differ only in case get a counter
(`notes.txt` / `Notes (2).txt`). Restoring always uses the original names.

## Development

```bash
python3 -m unittest discover -s tests            # unit + integration tests
# also run the suite on a real exFAT volume:
DEUCALION_TEST_EXFAT=/media/$USER/TEST python3 -m unittest discover -s tests
```
