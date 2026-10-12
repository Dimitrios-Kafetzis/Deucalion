# Tutorials

Step-by-step guides for every task. Each one shows the **App** and the **Command line** in tabs (choose
once; every page follows), says what you need and how long it takes, and ends with what you have now.

The screenshots and terminal output come from real runs on Ubuntu 24.04 and 26.04 computers with a
demo user, Alex, and demo drives.

## Set up a drive

Not sure which? Read [Choosing a drive](../choosing-a-drive.md) first.

| Tutorial | Erases the drive | Encrypted | Readable on |
|---|---|---|---|
| [Whole drive, VeraCrypt](drive-veracrypt.md) | yes | yes | Linux, Windows, macOS (with VeraCrypt) |
| [Whole drive, LUKS](drive-luks.md) | yes | yes | Linux |
| [Encrypted part + normal part](drive-split.md) | yes | the backup part | as above; normal part everywhere |
| [Encrypted folder on a drive you use](drive-encrypted-folder.md) | no | yes | as above |
| [Plain exFAT, no encryption](drive-exfat.md) | yes | no | everywhere |
| [Use a drive as it is](drive-as-is.md) | no | no | depends on the drive |

## Back up

- [Make a full backup](full-backup.md)
- [Back up only some folders](some-folders.md)
- [Save and use a profile](profiles.md) (command line)
- [Leave folders out](leave-out.md)
- [Back up a folder outside your home](outside-home.md)
- [Include protected settings](protected-settings.md)

## Restore

- [Find and restore a file](restore-file.md)
- [Restore a folder to another place](restore-elsewhere.md)
- [Undo a restore](undo-restore.md)

## Look after your backup

- [Unlock and lock an encrypted drive](unlock-lock.md)
- [Check that a backup is intact](verify.md) (command line)
- [Free space on the drive](free-space.md)
- [Move your backups to a bigger drive](bigger-drive.md)

## Rebuild and recover

- **[Rebuild your computer on a new Ubuntu version or a new computer](rebuild.md)**
- [Open your backup without Deucalion](open-without-deucalion.md) (Linux, Windows, macOS)
- [Use Deucalion without a desktop](headless.md) (SSH, servers)
