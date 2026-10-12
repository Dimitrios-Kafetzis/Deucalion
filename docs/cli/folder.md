# `deucalion folder`

Manages **extra folders**: folders outside your home folder that full backups include too, such as
`/srv/shared`, or a second disk mounted at `/data`.

```text
--8<-- "snippets/cli/help-folder.txt"
```

| Command | What it does |
|---|---|
| `deucalion folder` (or `folder list`) | Show your home folder (always included) and the extra folders. |
| `deucalion folder add PATH [--name NAME]` | Add a folder. |
| `deucalion folder remove NAME` | Remove the extra folder called `NAME` (its name, not its path). What was already backed up from it stays in the backup. |

```text
--8<-- "snippets/cli/folder-add.txt"
```

Each extra folder has a short **name** (the last part of its path by default, here `shared`), which
is where it is stored in the backup: `extras/shared/`. Choose another with `--name` (letters, digits,
`.`, `_` and `-` only).

Refused:

| Message | Why |
|---|---|
| `… is not a folder.` | The path doesn't exist or isn't a folder. |
| `That folder is inside your home folder, which is already backed up.` | |
| `There is already an extra folder called '…'.` | Use `--name` to give it another name. |
| `Use only letters, digits, '.', '_' and '-' in the name (--name).` | |
| `No extra folder called '…'.` | (`remove`) Use the name shown by `deucalion folder`. |

!!! note "Reading the folder"
    Deucalion reads extra folders as you. Files you can't read are skipped with a warning; it
    doesn't use administrator rights for them.

If an extra folder is **empty** when you back up (for example because the disk it lives on isn't
mounted) but the backup has files from it, Deucalion skips it to keep the backup safe: *"… is empty,
but the backup has files from it. Skipped, to keep the backup safe (is its drive connected?)."*

## Exit codes

`0` done; `1` refused (see above).

## Related

- [Back up a folder outside your home](../tutorials/outside-home.md)
- The app's [Settings](../app/settings.md#extra-folders) page
