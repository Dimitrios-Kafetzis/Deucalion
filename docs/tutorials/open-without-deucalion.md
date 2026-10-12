# Open your backup without Deucalion

**What you'll do:** get at your backed-up files on any computer: Linux without Deucalion, Windows or
macOS.<br>
**What you need:** the backup drive and its password (if encrypted); for VeraCrypt on Windows or
macOS, the free VeraCrypt app.<br>
**How long it takes:** 5–15 minutes (plus installing VeraCrypt if needed).

Your backup is made of normal files. Your home folder is in `Deucalion-Backup/home`, and extra folders
in `Deucalion-Backup/extras`. You can open and copy them directly. Two things to know:

- On an exFAT or NTFS drive, a few names look slightly different (`report： final？.txt`); see
  [File names on exFAT](../concepts/file-names.md).
- Permissions and links come back only when Deucalion restores the files. Copying them by hand gives
  you the content.

The drive's `READ-ME-FIRST.txt` (on its normal part) explains the same for that drive.

## No encryption

=== "Linux"

    Plug in the drive; open it in the Files app; open `Deucalion-Backup` → `home`.

=== "Windows"

    Plug in the drive; open it in File Explorer; open `Deucalion-Backup` → `home`. exFAT and NTFS
    drives can be read by Windows.

=== "macOS"

    Plug in the drive; open it in Finder; open `Deucalion-Backup` → `home`. exFAT drives can be read
    and written; NTFS drives can only be read.

## VeraCrypt

=== "Linux"

    **With the VeraCrypt app:** open VeraCrypt; for an encrypted *folder* click **Select File** and
    choose `Deucalion-Backup.hc` on the drive; for an encrypted *part* or *whole drive* click
    **Select Device** and choose the drive's encrypted partition. Choose a free slot, click **Mount**,
    type the password. The backup appears as a drive.

    **Without VeraCrypt**, with `cryptsetup`, which every Ubuntu has (for a whole drive or part, use
    the partition, for example `/dev/sdb2`, instead of the file):

    ```text
    --8<-- "snippets/cli/cryptsetup-open.txt"
    ```

    ```text
    --8<-- "snippets/cli/cryptsetup-mount.txt"
    ```

    When you are done:

    ```text
    --8<-- "snippets/cli/cryptsetup-close.txt"
    ```

=== "Windows"

    1. Install VeraCrypt from [veracrypt.fr](https://www.veracrypt.fr/en/Downloads.html).
    2. Open VeraCrypt. Choose a free drive letter in the list.
    3. Encrypted **folder**: click **Select File…** and choose `Deucalion-Backup.hc` on the drive.
       Encrypted **part** or **whole drive**: click **Select Device…** and choose the drive's encrypted
       partition.
    4. Click **Mount** and type the backup password. The backup appears as a new drive in File Explorer.
    5. When done, select it in VeraCrypt and click **Dismount**.

    !!! danger "Never format"
        Windows may say that a drive (the encrypted part) needs to be formatted. Choose **Cancel**.
        Formatting would erase your backup.

=== "macOS"

    1. Install [macFUSE](https://osxfuse.github.io/) and VeraCrypt (from
       [veracrypt.fr](https://www.veracrypt.fr/en/Downloads.html)), as VeraCrypt's instructions
       describe.
    2. Open VeraCrypt, choose a slot, then **Select File…** (`Deucalion-Backup.hc`, for an encrypted
       folder) or **Select Device…** (the encrypted partition), and click **Mount**.
    3. Type the backup password. The backup appears in Finder.
    4. When done, click **Dismount** in VeraCrypt.

## LUKS

LUKS is built into Linux and can't be opened on Windows or macOS.

=== "Linux"

    **On a desktop:** plug in the drive. Ubuntu asks for the password and opens it in the Files app.

    **In a terminal**, with Ubuntu's disk tools (for an encrypted folder, first attach the file with
    `udisksctl loop-setup -f /media/<you>/<drive>/Deucalion-Backup.luks` and use the device it names):

    ```text
    --8<-- "snippets/cli/udisks-unlock.txt"
    ```

    ```text
    --8<-- "snippets/cli/udisks-mount.txt"
    ```

    ```text
    --8<-- "snippets/cli/udisks-ls.txt"
    ```

    When done: `udisksctl unmount -b /dev/dm-…` then `udisksctl lock -b /dev/sd…` (the devices shown
    above).

=== "Windows, macOS"

    Not possible: LUKS works only on Linux. Start any computer from an Ubuntu USB stick ("Try Ubuntu")
    to read it.

## Restoring with Deucalion later

To put files back with their original names and permissions, use Deucalion on Ubuntu: from the drive's
`Deucalion-Tool` folder (`bin/deucalion open`, then `bin/deucalion restore …`), or after
[installing it](../getting-started/install.md).

**What you have now:** access to your files from any computer.
