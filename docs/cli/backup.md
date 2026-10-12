# `deucalion backup`

Backs up to your backup drive: everything (a [full backup](../concepts/full-and-partial.md)), or only
the folders and files you choose (a partial backup). Only what is new or changed is copied; what is
gone from your computer moves to [Removed Files](../concepts/mirror-and-removed.md).

```text
--8<-- "snippets/cli/help-backup.txt"
```

## Options

| Option | What it does |
|---|---|
| *(none)* | A full backup: your home folder, your extra folders and the [system recipe](../concepts/system-recipe.md). |
| `--only PATH …` | A partial backup of these folders or files only. They must be inside your home folder or an [extra folder](folder.md). |
| `--profile NAME` | A partial backup of the folders saved in a [profile](profile.md). Can be combined with `--only`. |
| `--dry-run` | Show what would be copied, with the largest folders, and copy nothing. |
| `--details` | List every file that will be copied or moved to Removed Files, and every warning (normally the first 8 warnings are shown). |
| `--check-drive` | Also check that every file in the backup is really on the drive, and copy again any that is missing. Slower: it lists every folder on the drive. |
| `-y`, `--yes` | Don't ask when the drive holds another computer's or user's backup (see below). |
| `--no-system` | Don't save the system recipe (full backups only). |
| `--no-admin` | Don't ask for the administrator password: the [protected settings](../tutorials/protected-settings.md) (Wi-Fi/VPN connections, root-only `/etc` files) are not updated. |
| `--target NAME` | Which backup drive to use. |

## What it prints

First the drive, then (full backups) the system recipe being saved, then the **plan**, then the
result:

```text
--8<-- "snippets/cli/backup.txt"
```

| Line | Meaning |
|---|---|
| **New files** | Not in the backup yet; will be copied. |
| **Changed files** | Changed since the last backup; will be copied, and the previous versions go to Removed Files. |
| **Gone/excluded** | In the backup, but no longer on your computer (or now left out); moved to Removed Files. |
| **Unchanged** | Already backed up as they are. |

While copying, one line shows a progress bar, how much is copied, the speed, the time left and the
current file. At the end it says how many files were copied and how many items moved to Removed Files,
and where the log is. After a backup, the copy of Deucalion and the READ-ME file on the drive's normal
part are refreshed.

## A dry run

`--dry-run` stops after the plan and also lists the largest folders, so you can see what takes space:

```text
--8<-- "snippets/cli/backup-dry-run.txt"
```

!!! note "Dry runs don't ask for your password"
    So they can't read the [protected settings](../tutorials/protected-settings.md). The warning
    *"System settings (/etc, network) were not updated because administrator access was not used; the
    copy from an earlier backup is kept."* only means that; the real backup will ask for the password.

## A partial backup

```text
--8<-- "snippets/cli/backup-only.txt"
```

## Checks before copying

Deucalion checks, and stops without copying anything, when:

- **the drive is too small**: *"Not enough space on the drive: this backup needs about … but only … is
  free. You can free space by emptying \_removed/ (deucalion removed empty) or excluding large
  folders."* (exit code 1). See [Free space on the drive](../tutorials/free-space.md).
- **the drive holds another computer's or user's backup**: it prints *"This drive holds the backup of
  alex@alex-laptop (home folder /home/alex), but this is …"* and asks **Continue anyway?** Backing up
  would make the drive mirror *this* computer and move everything that is only in the old backup to
  Removed Files. On a new computer, [rebuild or restore](../tutorials/rebuild.md) first. `--yes`
  answers yes.

It also warns (without stopping) when the drive is **not encrypted** and your backup includes keys or
logged-in sessions (`.ssh`, `.gnupg`, password stores, keyrings, browser profiles).

## Stopping and interruptions

Press ++ctrl+c++ once to stop safely: *"Stopped. N files were copied; the next backup continues from
here."* (exit code 130). A backup that was killed, or whose drive was unplugged or ran full, is also
completed by the next backup, with no duplicates.

## Results

| End | Exit code |
|---|---|
| `Backup finished in …: copied N files (…), moved N items to _removed/.` | `0` |
| The same, followed by *"Some warnings above."*: some files couldn't be read or were skipped; see the log. | `0` |
| `Everything is already up to date.` then `Backup finished in 0s: copied 0 files …` (nothing to copy) | `0` |
| `Backup failed: …` (for example the drive filled up while copying) | `1` |
| `Stopped. …` | `130` |

## Related

- [Make a full backup](../tutorials/full-backup.md) · [Back up only some folders](../tutorials/some-folders.md) · [Save and use a profile](../tutorials/profiles.md)
- The app's [Back Up](../app/backup.md) page
