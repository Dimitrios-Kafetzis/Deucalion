# `deucalion removed`

Lists or empties [Removed Files](../concepts/mirror-and-removed.md): the old versions of changed
files and the files deleted from your computer, kept on the drive in `Deucalion-Backup/_removed/`.

```text
--8<-- "snippets/cli/help-removed.txt"
```

## Listing

`deucalion removed` (or `deucalion removed list`) shows one line per *batch*: the folder of one
backup, named after the date and time the backup started (`2026-10-11_143005`), with its number of
files and size, oldest first:

```text
--8<-- "snippets/cli/removed-list.txt"
```

## Emptying

`deucalion removed empty` deletes **all** batches; `deucalion removed empty NAME …` only the batches
you name. It shows what it will delete and asks first:

```text
--8<-- "snippets/cli/removed-empty.txt"
```

!!! danger "This can't be undone"
    Deleted batches are gone from the drive. If those files are also gone from your computer, they
    are lost.

| Option | What it does |
|---|---|
| `list` | List the batches (the default). |
| `empty` | Delete batches: all of them, or those named after it. |
| `NAME …` | Batches to delete, as listed (e.g. `2026-10-11_143005`). An unknown name stops it: *"Not found in \_removed/: …"*. |
| `-y`, `--yes` | Don't ask **Delete them permanently?** |
| `--target NAME` | Which backup drive. |

You can also look at a batch with the Files app first: open the backup drive, then
`Deucalion-Backup/_removed/<batch>/`. Inside, files are in the same folders as in the backup
(`home/Documents/…`), with the names [as stored on the drive](../concepts/file-names.md).

## Exit codes

`0` listed or emptied (or nothing to empty); `1` an error, or you answered no (*"Nothing was
deleted."*).

## Related

- [Free space on the drive](../tutorials/free-space.md) · The app's [Removed Files](../app/removed-files.md) page
