# `deucalion restore`

Copies files or folders from the backup back to your computer: to where they were, or into another
folder. It always shows a plan first and asks before changing anything. Anything it replaces is kept
in the [undo folder](../tutorials/undo-restore.md) `~/Deucalion-before-restore/`.

```text
--8<-- "snippets/cli/help-restore.txt"
```

| Option | What it does |
|---|---|
| `PATH …` | What to restore: one or more files or folders, as paths on your computer (`~/Documents/report.pdf`) or in the backup (`home/Documents`). A folder includes everything inside it. |
| `--to DIR` | Restore into this folder instead: each item is restored inside `DIR` with its own name (`--to ~/Desktop/Recovered` puts `~/Documents/Work` in `~/Desktop/Recovered/Work`). Nothing in the original place is touched. |
| `--dry-run` | Show the plan and change nothing. |
| `--details` | List every file that would be replaced (normally the first 15). |
| `-y`, `--yes` | Don't ask **Restore now?** |
| `--target NAME` | Which backup drive. |

## Example

```text
--8<-- "snippets/cli/restore.txt"
```

The plan shows:

| Line | Meaning |
|---|---|
| `… → …` | Each item and where it goes. |
| **New** | Files and folders that don't exist there now. |
| **Overwrite** | Items that exist there and are different. They are moved aside to the undo folder first (renamed, never copied and deleted). |
| **Already the same** | Identical already (same size, date and content); not copied. |
| **To copy** | Number and size of files to copy. |
| **Missing on drive** | In the manifest, but missing on the drive (for example after a drive problem). They can't be restored; the others are. |
| **Will overwrite** | The files that will be replaced. |

Into another folder:

```text
--8<-- "snippets/cli/restore-to.txt"
```

## Restoring for a different user name

Your home folder in the backup is restored into **your current home folder**, whatever its path. A
backup made as `/home/alex` restores into `/home/alexk` if that is your home folder now. (A
[rebuild](rebuild.md) also updates paths inside settings files.)

## The system recipe

The `system/` part can't be restored in place. Restore it into a folder to read it:

```text
--8<-- "snippets/cli/restore-system.txt"
```

Without `--to`, it goes to a `deucalion-system` folder in the current folder.

## Messages

| Message | Meaning |
|---|---|
| `… is not part of the backup.` / `… is not in the backup.` | The path isn't in the backup (check with [`ls`](ls.md)). |
| `“…” and “…” would be restored to the same place (…). Restore them separately, or into different folders.` | Two items with the same name with `--to`. |
| `Nothing to restore: everything is already the same.` | Nothing to do. |
| `… : not restored (…); the version that was there has been kept (see above).` | A file couldn't be restored; your version is safe. |
| `… : restored, but its content does not match the checksum recorded at backup time. The copy on the drive may be damaged.` | Check the drive with [`verify --full`](verify.md). |

## Exit codes

`0` restored (or nothing to do, or `--dry-run`); `1` an error, or you answered no (*"Nothing was
changed."*); `130` stopped (what was restored stays; a file being replaced is put back).

## Related

- [Find and restore a file](../tutorials/restore-file.md) · [Restore a folder to another place](../tutorials/restore-elsewhere.md) · [Undo a restore](../tutorials/undo-restore.md)
- The app's [Restore](../app/restore.md) page
