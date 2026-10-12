# `deucalion ls`

Lists what is in the backup, with the **original** file names (even those
[stored differently on exFAT](../concepts/file-names.md)).

```text
--8<-- "snippets/cli/help-ls.txt"
```

Without a path, it lists the parts of the backup: your home folder, the system recipe and any extra
folders, with where each came from:

```text
--8<-- "snippets/cli/ls-after-folder.txt"
```

With a path, the contents of that folder (folders end with `/` and show their number of files and
size; links show where they point):

```text
--8<-- "snippets/cli/ls-documents.txt"
```

The path can be a path on your computer (`~/Documents`, `/home/alex/Documents`, `/srv/shared`) or a
path in the backup (`home/Documents`, `system/packages`, `extras/shared`). A path that isn't in the
backup gives *"… is not in the backup."* or *"… is not part of the backup."* (exit code 1).

| Option | What it does |
|---|---|
| `path` | A folder or file to list. |
| `--target NAME` | Which backup drive. |

## Exit codes

`0` listed; `1` not found or drive not available.

## Related

- [Find and restore a file](../tutorials/restore-file.md)
- [`restore`](restore.md)
