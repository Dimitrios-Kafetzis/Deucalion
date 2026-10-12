# Back up only some folders

**What you'll do:** quickly update a few folders in your backup, without a full backup.<br>
**What you need:** a backup drive with a backup on it (or not: a partial backup on an empty drive
works too).<br>
**How long it takes:** a minute or two.

A partial backup only looks at the folders you choose and leaves the rest of the backup exactly as it
was. It doesn't save the system recipe. See [Full and partial backups](../concepts/full-and-partial.md).

=== "App"

    1. Open Deucalion and go to **Back Up**.
    2. Choose **Only some folders**.
    3. Click **Add Folder…** and choose one or more folders (hold ++ctrl++ to select several). They
       must be in your home folder or in an [extra folder](outside-home.md). Repeat to add more. The
       bin button removes one from the list.

        ![The Back Up page with "Only some folders" selected and ~/Documents and ~/Pictures in the
        Folders list.](../assets/screenshots/app/backup-some.png){ .shot }

    4. Click **Check What Will Be Copied**. The plan covers only these folders:

        ![The plan of a partial backup: nothing new or changed, 45 files unchanged, and the button Finish
        (nothing to copy).](../assets/screenshots/app/backup-some-review.png){ .shot }

    5. Click **Start Backup** (it reads **Finish (nothing to copy)** when nothing changed, as here), then
       **Done** when it is finished.

=== "Command line"

    Name the folders (or files) after `--only`:

    ```text
    --8<-- "snippets/cli/backup-only.txt"
    ```

    Add `--dry-run` to only see the plan.

**What you have now:** the chosen folders are up to date in your backup. **Recent activity** (or
`deucalion status`) lists it as a *partial* backup.

**Next steps:** if you back up the same folders often, [save them as a profile](profiles.md).
