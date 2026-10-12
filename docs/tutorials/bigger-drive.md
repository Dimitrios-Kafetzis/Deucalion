# Move your backups to a bigger drive

**What you'll do:** start backing up to a new, bigger drive, and keep the old one as an extra
copy.<br>
**What you need:** the new drive; your computer with the files you back up; optionally the old
drive.<br>
**How long it takes:** 15 minutes, plus a first full backup to the new drive.

Your computer holds everything a backup needs, so you start the new drive with a fresh full backup,
and keep the old drive as long as you want its older versions.

## Step by step

1. **Set up the new drive** as described in [Choosing a drive](../choosing-a-drive.md) (for example
   [encrypted part + normal part](drive-split.md)). It becomes your **default** backup drive.
2. **Make a full backup** to it: [Make a full backup](full-backup.md). This copies everything, so it
   takes as long as a first backup.
3. **Keep the old drive** for as long as you like: as a second backup, or for the old versions in its
   Removed Files. It is still registered. To back up to it again, make it the default on the **Drives**
   page (the star button, *Use this drive for backups*), or use `--target NAME` on the command line, for example
   `deucalion backup --target "Alex Backup"`.
4. When you no longer need the old drive in Deucalion, click **Forget** next to it on the **Drives**
   page. The backup on it is not deleted.

!!! note "Copying a backup folder to another drive"
    Copying the `Deucalion-Backup` folder to another drive by hand is not supported in version 0.2.
    The copy carries the same identity as the original, so Deucalion treats both as the same backup
    drive, including how to unlock it. Use a fresh full backup instead, as above. You can still copy
    *files* out of the old backup or its Removed Files with the Files app whenever you need them.

**What you have now:** your backups on the bigger drive, and the old drive as an extra copy.
