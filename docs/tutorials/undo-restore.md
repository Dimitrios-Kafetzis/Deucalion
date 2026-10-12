# Undo a restore

**What you'll do:** get back the version of a file that a restore (or a rebuild) replaced.<br>
**What you need:** nothing: the replaced versions are on your computer.<br>
**How long it takes:** 2 minutes.

Before a restore replaces anything, Deucalion **moves** the current version into the **undo folder**,
`Deucalion-before-restore` in your home folder. Each restore gets its own folder, named after the
date and time, and inside it the **full path** of each file:

```text
--8<-- "snippets/cli/undo-folder.txt"
```

So `~/Documents/Budget 2026.ods`, replaced by a restore, is in
`~/Deucalion-before-restore/<date>_<time>/home/alex/Documents/Budget 2026.ods`.

=== "App"

    1. Right after a restore, click **Open Replaced Files**: the Files app opens that restore's undo
       folder. (Later, open your home folder in the Files app, then **Deucalion-before-restore** and the
       dated folder.)
    2. Go down to the file (`home › alex › Documents`).
    3. Drag it back to its original folder (or copy it there) and choose **Replace** when asked.

=== "Command line"

    Move the file back with `mv`, using the dated folder shown by `find` instead of `<date>_<time>`:

    ```bash
    mv ~/Deucalion-before-restore/<date>_<time>/home/alex/Documents/"Budget 2026.ods" ~/Documents/
    ```

!!! note "Other undo folders"
    A [rebuild](rebuild.md) uses the same folder: `…-paths`, `…-desktop` and `…-crontab` folders hold
    settings files, desktop settings and the crontab it replaced. `/etc` files are kept in
    `/var/backups/deucalion/` instead.

    If a file couldn't be moved into the undo folder (for example it is on another disk), it is kept
    next to the original as `name.before-restore-<date>`, and the restore says so.

Deucalion never deletes the undo folder. Delete old dated folders yourself when you no longer need
them (it is never backed up).

**What you have now:** your previous version back.
