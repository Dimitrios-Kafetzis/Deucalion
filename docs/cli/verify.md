# `deucalion verify`

Checks that the backup on the drive is complete and undamaged.

```text
--8<-- "snippets/cli/help-verify.txt"
```

| Mode | What it checks | How long |
|---|---|---|
| `deucalion verify` (quick) | Every file in the backup is on the drive, with the right size. | Seconds to minutes. |
| `deucalion verify --full` | The same, and it **reads every file** and compares its checksum (SHA-256) with the one recorded at backup time. Finds files damaged on the drive. | As long as reading the whole backup from the drive: for example, at 120 MB per second (a typical USB hard disk), about 15 minutes per 100 GB. |

```text
--8<-- "snippets/cli/verify-full.txt"
```

When something is wrong, it lists what, and **marks those files so the next backup copies them
again**:

```text
--8<-- "snippets/cli/verify-damaged.txt"
```

| Problem | Meaning |
|---|---|
| **Missing on drive** | The file isn't on the drive any more. |
| **Wrong size** | The file on the drive has a different size than recorded. |
| **Damaged (checksum mismatch)** | (`--full`) The content changed: the drive may be failing, or the file was changed outside Deucalion. |

Then run [`deucalion backup`](backup.md): the files are copied again from your computer (the damaged
copy goes to Removed Files):

```text
--8<-- "snippets/cli/backup-after-damage.txt"
```

!!! warning "If problems come back"
    Damaged files that keep appearing mean the drive itself is failing. Copy your backup to another
    drive soon (see [Move your backups to a bigger drive](../tutorials/bigger-drive.md)).

| Option | What it does |
|---|---|
| `--full` | Also read every file and compare checksums. |
| `--target NAME` | Which backup drive. |

++ctrl+c++ stops it (*"Stopped before the end."*). Problems found until then are still marked.

## Exit codes

`0` the backup is intact; `1` problems found (or the drive isn't available); `130` stopped.

## Related

- [Check that a backup is intact](../tutorials/verify.md)
