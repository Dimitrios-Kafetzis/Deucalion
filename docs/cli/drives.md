# `deucalion drives` and `deucalion targets`

## `drives`: the drives plugged in

Lists every drive plugged into the computer, **except the disk your system runs from** (it is never
listed), with its parts, their format, size, where they are mounted, and tags: *encrypted*, or
*Deucalion backup* when a part holds a backup.

```text
--8<-- "snippets/cli/help-drives.txt"
```

**Example**, with the drive prepared in [Your first backup](../getting-started/first-backup.md) and an
empty second drive:

```text
--8<-- "snippets/cli/drives-after-setup.txt"
```

- `/dev/sda` is the drive; `/dev/sda1` its normal part; `/dev/mapper/deucalion-…` the unlocked
  encrypted part (VeraCrypt).
- "external" means a USB (or other removable) drive; "internal" a second disk inside the computer.

If no drive is found: *"No external drives found. (Your system disk is never listed.)"*

## `targets`: your backup drives

Lists the drives registered for backups: name, **(default)** for the default one, whether it is
**connected**, where its backup folder is, and its id.

```text
--8<-- "snippets/cli/help-targets.txt"
```

```text
--8<-- "snippets/cli/targets.txt"
```

If none is registered: *"No backup drives registered. Use: deucalion register &lt;drive folder&gt;"*.

To make another drive the default, register its backup folder again with `--default` (see
[register](register.md#changing-the-default-drive)). To stop using a drive, use **Forget** on the
app's [Drives](../app/drives.md) page, or remove it from the [configuration file](../reference/configuration.md).

## Exit codes

Both commands end with `0`.

## Related

- [Choosing a drive](../choosing-a-drive.md) · [`setup-drive`](setup-drive.md) · [`register`](register.md)
