# `deucalion profile`

Manages **profiles**: named lists of folders (or files) for [partial backups](../concepts/full-and-partial.md#partial-backup)
that you run often. Profiles are only available on the command line.

```text
--8<-- "snippets/cli/help-profile.txt"
```

| Command | What it does |
|---|---|
| `deucalion profile` (or `profile list`) | Show your profiles. |
| `deucalion profile add NAME PATH …` | Save a profile (an existing one with the same name is replaced). |
| `deucalion profile remove NAME` | Delete a profile. |

```text
--8<-- "snippets/cli/profile-add.txt"
```

Paths are saved as full paths. Then back up with it:

```text
--8<-- "snippets/cli/backup-profile.txt"
```

`--profile` can be combined with `--only` (both lists are backed up).

Messages: *"Give the folders/files for the profile."* (no path given), *"No profile called '…'."*
(remove), and for `backup --profile`: *"No profile called '…'. See: deucalion profile list"*.

## Exit codes

`0` done; `1` an error (see above).

## Related

- [Save and use a profile](../tutorials/profiles.md)
