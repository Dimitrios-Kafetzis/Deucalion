# What is on the drive

## The backup folder: `Deucalion-Backup`

```text
Deucalion-Backup/
├── backup.json          which computer and user this is, the last backup and its result
├── home/                your home folder, as normal files
├── system/              the system recipe (readable text files; see system/README.txt)
├── extras/<name>/       extra folders you added (for example extras/shared)
├── _removed/<date>/     Removed Files: old versions and deleted files, one folder per backup
└── .deucalion/          Deucalion's own records (hidden)
    ├── drive-id         the backup's identity (id, name, how names are stored)
    ├── manifest.sqlite  the manifest: original names, permissions, links, checksums
    ├── manifest.sqlite.bak   a copy, saved after every completed backup
    ├── logs/            one log per backup, restore and rebuild
    ├── lock             prevents two Deucalion tasks on the drive at once
    └── staging/         files being copied (only during a backup)
```

The demo backup, on the drive:

```text
--8<-- "snippets/cli/drive-top.txt"
```

!!! danger "Don't change these by hand"
    Don't rename or move `Deucalion-Backup`, and don't change anything in `.deucalion`. To free space,
    empty Removed Files with Deucalion. You can **open and copy** any file at any time.

### `backup.json`

A summary that any program (or person) can read:

```text
--8<-- "snippets/cli/backup-json.txt"
```

| Key | Meaning |
|---|---|
| `tool`, `tool_version`, `format` | Written by Deucalion, which version, and the format version (1). |
| `machine` | The computer's name, Ubuntu version and kernel at the last backup. |
| `user` | The user name, user id and home folder. |
| `sources` | What the backup contains (`home`, `system`, `extras/…`) and where each came from. |
| `last_run` | The last backup: full or partial, start and end, result, what it copied and moved, warnings, error. |
| `last_full_backup` | When the last full backup finished successfully. |

### `.deucalion/drive-id`

A small JSON file that makes the folder a backup: a unique `id` (how Deucalion recognises the drive,
wherever it is mounted), its `name`, when and by which version it was `created`, and `name_policy`:
`exfat` (names made [exFAT-safe](../concepts/file-names.md)) or `posix` (names kept as they are, on
Linux filesystems).

## On the normal part: `Deucalion-Tool` and `READ-ME-FIRST.txt`

Drives that Deucalion prepares (except a whole-drive encrypted one) also get, on their unencrypted
part (for the encrypted-folder layout: next to the encrypted file):

```text
--8<-- "snippets/cli/tool-folder.txt"
```

- `READ-ME-FIRST.txt`: what is on the drive and how to open the backup on Linux, macOS and Windows,
  written for the drive's layout. See an example in [Encrypted part + normal part](../tutorials/drive-split.md#what-is-on-the-drive-now).
- `Deucalion-Tool/`: a copy of Deucalion (`bin/`, `deucalion/`, `README.md`) that runs on any Ubuntu with
  `bin/deucalion`, and `drive.json`.

Both are refreshed after every backup. If a file or folder with one of these names that Deucalion
didn't create is already there, it is never replaced: Deucalion uses `READ-ME-FIRST (Deucalion).txt` or
`Deucalion-Tool (Deucalion)` instead.

### `Deucalion-Tool/drive.json`

How to open the encrypted backup, so that `deucalion open` on a new computer can find it without
being told:

```text
--8<-- "snippets/cli/drive-json.txt"
```

| Key | Meaning |
|---|---|
| `method` | `veracrypt`, `luks` or `none`. |
| `kind` | `partition` (encrypted part or whole drive) or `file` (encrypted folder). |
| `partuuid` | The encrypted partition's id (kind `partition`). |
| `file`, `plain_path` | The encrypted file's name and where the drive was mounted (kind `file`). |
| `plain_uuid` | The id of the normal part (where this file is). |
| `mount_name` | The name the unlocked backup is mounted under. |
| `version`, `target_id`, `target_name` | Deucalion's version, and the backup's id and name. |

The password is never stored anywhere.

## The encrypted folder file

The encrypted-folder layout stores the whole backup in one file: `Deucalion-Backup.hc` (VeraCrypt) or
`Deucalion-Backup.luks` (LUKS). Its size is fixed when it is created.

## How the drive is partitioned

| Layout | Partitions |
|---|---|
| Whole drive | One partition (marked as a Linux partition), encrypted; inside: exFAT (VeraCrypt) or ext4 (LUKS2). |
| Encrypted part + normal part | A normal exFAT partition first, then the encrypted partition (Linux type) at the end of the drive. |
| Plain exFAT | One exFAT partition (8 KB clusters). |
| Encrypted folder, as it is | Unchanged. |

All drives Deucalion partitions use a GPT partition table. exFAT is created with 8 KB clusters.
