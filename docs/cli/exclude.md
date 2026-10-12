# `deucalion exclude`

Manages the list of what is left out of your **home folder**'s backup. Each entry is a
[pattern](../reference/exclusion-patterns.md), such as `Videos/` or `*.iso`.

```text
--8<-- "snippets/cli/help-exclude.txt"
```

| Command | What it does |
|---|---|
| `deucalion exclude` (or `exclude list`) | Show the list. |
| `deucalion exclude add PATTERN …` | Add patterns (one already there is ignored). |
| `deucalion exclude remove PATTERN …` | Remove patterns. One that isn't in the list stops it: *"Not in the exclusion list: …"*. |
| `deucalion exclude reset` | Put back the [default list](../reference/exclusion-patterns.md#default-exclusions); your own patterns are removed. |

Every command prints the list afterwards. Put patterns in quotes, so the terminal doesn't expand
`*` itself:

```text
--8<-- "snippets/cli/exclude-add.txt"
```

!!! note "Leaving out something that is already backed up"
    The next full backup moves it from the backup to Removed Files (*Gone/excluded* in the plan):

    ```text
    --8<-- "snippets/cli/backup-after-exclude-dry-run.txt"
    ```

In a [partial backup](backup.md), a folder you name with `--only` that is excluded is skipped with a
warning: *"…: excluded by your exclusion rules; skipped."*

Some folders are always left out and aren't in the list: Deucalion's own working folder
(`~/.local/state/deucalion/`) and the undo folder (`~/Deucalion-before-restore/`).

The patterns apply to your home folder only. Extra folders have their own list, which can only be
changed in the [configuration file](../reference/configuration.md) (`excludes` of each folder).

## Exit codes

`0` done; `1` a pattern to remove wasn't in the list.

## Related

- [Leave folders out](../tutorials/leave-out.md) · [Exclusion patterns](../reference/exclusion-patterns.md)
- The app's [Settings](../app/settings.md#leave-out-of-backups) page
