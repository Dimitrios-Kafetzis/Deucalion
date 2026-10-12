# Glossary

The words used on this site, each with one meaning.

Administrator helper
:   The small program that does the few tasks needing administrator rights, after you give your
    password. See [Administrator access](../concepts/administrator-access.md).

Administrator password
:   The password Ubuntu asks for administrator tasks: usually your own login password, if your account
    is an administrator.

Backup
:   The copy of your files and system recipe on the backup drive, in the `Deucalion-Backup` folder.

Backup drive
:   The external drive (or the encrypted part, or the encrypted folder on it) where Deucalion keeps your
    backup. In the command line also called a *target*.

Backup password
:   The password of an encrypted backup drive. It can't be recovered.

Batch
:   One dated folder in Removed Files: what one backup moved there.

Default drive
:   The backup drive backups go to when you don't choose one (★ on the **Drives** page).

Dry run
:   A run that shows what would happen and changes nothing (`--dry-run`).

Encrypted folder
:   A layout where the backup lives in one encrypted file on a drive that keeps its other files.

Encrypted part, normal part
:   The two partitions of the *encrypted part + normal part* layout.

Encryption
:   Scrambling data so that it can only be read with the password. Deucalion uses VeraCrypt or LUKS.

exFAT
:   A drive format readable and writable on Linux, Windows and macOS. Deucalion's default for
    unencrypted drives and inside VeraCrypt.

Exclusion, pattern
:   A rule that leaves files or folders out of the backup. See [Exclusion patterns](exclusion-patterns.md).

Extra folder
:   A folder outside your home folder that full backups include.

Full backup
:   A backup of everything: home folder, extra folders and system recipe.

Home folder
:   Your personal folder, `/home/<your name>` (`~` for short).

Layout
:   How a drive is prepared: whole drive encrypted, encrypted part + normal part, encrypted folder,
    plain exFAT, or as it is. See [Choosing a drive](../choosing-a-drive.md).

Lock, unlock
:   Close or open an encrypted backup drive. In the terminal: `deucalion close`, `deucalion open`.

LUKS
:   The disk encryption built into Linux. Readable only on Linux.

Manifest
:   The small database on the drive that records original names, permissions, links and checksums. See
    [The manifest](../concepts/manifest.md).

Mirror
:   One up-to-date copy of your files. The backup is a mirror; older versions go to Removed Files.

Mount, unmount
:   Make a drive's files available in a folder (such as `/media/<you>/<name>`), or stop that before
    unplugging.

Partial backup
:   A backup of only the folders or files you choose. See [Full and partial backups](../concepts/full-and-partial.md).

Profile
:   A saved list of folders for partial backups (command line only).

Protected settings
:   Settings only the administrator can read: Wi-Fi/VPN connections, some `/etc` files, root's crontab.

Rebuild
:   Setting up a computer from a full backup, in eight steps. See [What a rebuild restores](../concepts/rebuild.md).

Register
:   Tell Deucalion to use a drive (or folder) for backups.

Removed Files
:   Old versions of changed files and files deleted from your computer, kept on the drive in
    `Deucalion-Backup/_removed` until you empty them.

Restore
:   Copy files or folders from the backup back to your computer.

System recipe
:   A readable description of your apps, software sources and settings, saved with each full backup and
    used by a rebuild. The app calls it **system settings**. See [The system recipe](../concepts/system-recipe.md).

Terminal
:   A window where you type commands. Open one with ++ctrl+alt+t++.

Undo folder
:   `~/Deucalion-before-restore`, where Deucalion keeps what a restore or rebuild replaced.

VeraCrypt
:   Free encryption software for Linux, Windows and macOS. Deucalion can create VeraCrypt drives and open
    them on Ubuntu without the VeraCrypt app.
