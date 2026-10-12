# `deucalion register`

Uses a drive **as it is** for backups: creates a `Deucalion-Backup` folder on it (or reuses the one
that is there) and adds it to your backup drives. Nothing on the drive is erased or changed.

Use it to:

- back up to a drive you formatted yourself (NTFS, exFAT, ext4…), without a copy of Deucalion on it
  (for that, use [`setup-drive --layout as-is`](setup-drive.md));
- add a backup drive you already have, for example on a new computer;
- make an existing backup drive the default one.

```text
--8<-- "snippets/cli/help-register.txt"
```

| Option | What it does |
|---|---|
| `path` | Where the drive is mounted (`/media/alex/MyDrive`), a folder on it, or an existing `Deucalion-Backup` folder. |
| `--name NAME` | A name for this backup drive. Default: the folder's name. Only used when a new backup folder is created. |
| `--default` | Make it the default drive. The first drive you register is always the default. |

## How the path is used

- If `path` **is** a backup folder (it has `.deucalion/drive-id` inside), that backup is registered.
- If `path` **contains** a `Deucalion-Backup` backup folder, that one is registered.
- Otherwise a new `Deucalion-Backup` folder is created inside `path`.

Then it prints what it found:

```text
--8<-- "snippets/cli/register-default.txt"
```

- **Filesystem** and how names are stored: as they are on Linux filesystems (ext4, Btrfs, XFS…),
  [exFAT-safe](../concepts/file-names.md) on others (exFAT, NTFS, FAT).
- **Encrypted**: whether the drive is encrypted (VeraCrypt or LUKS, once unlocked).

A folder on the disk your system runs from is refused:

```text
--8<-- "snippets/cli/register-system-disk.txt"
```

## Changing the default drive

Register the backup folder again with `--default`. Use the exact path that
[`deucalion targets`](drives.md#targets-your-backup-drives) shows for that drive, so you don't create
a new backup folder somewhere else by mistake:

```bash
deucalion targets
deucalion register "/media/alex/Alex Backup2/Deucalion-Backup" --default
```

Registering a drive again keeps everything Deucalion knows about it, such as how to unlock it.

!!! tip "Encrypted drives"
    To add an *encrypted* backup drive on a new computer, use [`deucalion open`](open-close.md): it
    finds the encrypted backup, unlocks it, and registers it, remembering how to unlock it next time.
    `register` only sees a drive that is already unlocked.

## Exit codes

`0` registered; `1` an error (for example *"… is not a folder."*).

## Related

- [Use a drive as it is](../tutorials/drive-as-is.md)
- [Move your backups to a bigger drive](../tutorials/bigger-drive.md)
