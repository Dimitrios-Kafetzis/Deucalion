# `deucalion status`

Shows the state of your backup: where it is, what it holds, how much space is left, and the last
backups.

```text
--8<-- "snippets/cli/help-status.txt"
```

```text
--8<-- "snippets/cli/status.txt"
```

| Line | Meaning |
|---|---|
| **Folder** | The backup folder on the drive. |
| **Filesystem**, **Encrypted** | The drive's format, and whether it is encrypted. |
| **Backed up** | Number of files and size in the backup (without Removed Files). |
| **Free space** | Free space on the drive. |
| **\_removed/** | Size of [Removed Files](../concepts/mirror-and-removed.md), and in how many groups (batches). |
| **From machine** | Which computer and user the backup comes from, and its Ubuntu version. |
| **Last full** | When the last full backup finished. |
| **Recent runs** | The last five backups: when they started, full or partial (with what was backed up), how they ended (`completed`, `completed_with_warnings`, `cancelled`, `failed`, or `running` if it was interrupted), and how much they copied. |

If the drive is locked, `status` asks for its password first.

| Option | What it does |
|---|---|
| `--target NAME` | Which backup drive. |

## Exit codes

`0` shown; `1` the drive isn't available (for example *"Backup drive 'Alex Backup' is not connected (or
not unlocked). Plug it in and try again."*).

## Related

- The app's [Overview](../app/overview.md) page
