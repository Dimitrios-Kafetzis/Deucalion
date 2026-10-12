# Check that a backup is intact

**What you'll do:** check that every file in the backup is on the drive and undamaged.<br>
**What you need:** your backup drive; a terminal (this check is only on the command line).<br>
**How long it takes:** the quick check takes seconds; the full check reads the whole backup
(for example about 15 minutes per 100 GB on a USB hard disk).

Drives can fail slowly. Checking now and then (for example every few months, and before you move to a
new computer) tells you while you can still fix it.

=== "App"

    The app has no **Verify** button. Use the command line for this check (open a terminal with
    ++ctrl+alt+t++ and follow the other tab).

=== "Command line"

    1. The quick check, that every file is there with the right size:

        ```text
        --8<-- "snippets/cli/verify.txt"
        ```

    2. The full check, that every file's content is exactly what was backed up:

        ```text
        --8<-- "snippets/cli/verify-full.txt"
        ```

## If it finds problems

It lists them and marks those files, so **the next backup copies them again** from your computer:

```text
--8<-- "snippets/cli/verify-damaged.txt"
```

1. Run a backup (in the app or with `deucalion backup`). The damaged file counts as *changed* and is
   copied again; the damaged copy goes to Removed Files.

    ```text
    --8<-- "snippets/cli/backup-after-damage.txt"
    ```

2. Check again with `deucalion verify --full`:

    ```text
    --8<-- "snippets/cli/verify-again.txt"
    ```

!!! warning "If the file is no longer on your computer"
    Then the backup was the only copy, and the damaged copy can't be repaired. It may still be partly
    readable in Removed Files. If problems keep coming back, the drive is failing: move your backup to
    another drive (see [Move your backups to a bigger drive](bigger-drive.md)).

**What you have now:** confidence that your backup can be restored.

**Next steps:** [`deucalion verify`](../cli/verify.md) for all options.
