# `deucalion setup-drive`

Prepares a drive for backups in one of the five [layouts](../choosing-a-drive.md): formats and/or
encrypts it, creates the backup folder, puts a copy of Deucalion and a READ-ME file on its normal
part (if it has one), and registers it as your **default** backup drive.

```text
--8<-- "snippets/cli/help-setup-drive.txt"
```

!!! danger "Three layouts erase the drive"
    `encrypt-all`, `encrypt-part` and `plain` erase **everything** on the drive. Deucalion shows the
    drive's parts and how much they hold, and asks you to type the drive's name (such as `sdb`)
    before it erases anything. Your system disk is never offered and is refused if you name it.

## Asked or given

Run it without options and it asks everything, one question at a time. Each option answers one
question in advance:

| Option | Question it answers | Values |
|---|---|---|
| `device` | **Which drive?** | the whole drive, e.g. `/dev/sdb` (not a part like `/dev/sdb1`) |
| `--layout` | **How should the backup be stored?** | `encrypt-all` (whole drive), `encrypt-part` (encrypted part + normal part), `encrypt-folder` (encrypted folder, keeps the drive's files), `plain` (exFAT, no encryption), `as-is` (keep the drive as it is) |
| `--method` | **Which encryption?** (encrypted layouts) | `veracrypt` or `luks` |
| `--size GB` | **Size of the encrypted part** / **Size of the encrypted folder** | gigabytes, e.g. `500` or `0.5` |
| `--name` | **A name for this backup drive** | e.g. `Backup` (default `Deucalion`) |
| `--yes-erase DRIVE` | **To confirm, type the drive name** | the drive's short name, e.g. `sdb` |
| `-y`, `--yes` | **Continue?** (layouts that don't erase), and **Install it now?** for `exfatprogs` | |

The menus only offer what fits the drive: on an empty drive, the two layouts that keep the drive's
files aren't offered, so **the numbers in the menu change**. Read the text, not just the number.

The password is always asked (twice, at least 8 characters; nothing appears while you type). It is
never accepted as an option, so it doesn't end up in your terminal history.

!!! warning "The password can't be recovered"
    Write it down and keep it somewhere safe. Without it, the backup can't be opened by anyone.

## Examples

**Everything asked** (encrypted part + normal part, VeraCrypt):

```text
--8<-- "snippets/cli/setup-split-cli.txt"
```

**With options** (whole drive, LUKS); only the confirmation and the password are asked:

```text
--8<-- "snippets/cli/setup-luks-whole.txt"
```

**Without any question** (plain exFAT; for scripts):

```text
--8<-- "snippets/cli/setup-small.txt"
```

The other layouts: [whole drive, VeraCrypt](../tutorials/drive-veracrypt.md) ·
[encrypted folder](../tutorials/drive-encrypted-folder.md) · [plain exFAT](../tutorials/drive-exfat.md) ·
[as it is](../tutorials/drive-as-is.md).

## What it needs

- `exfatprogs` for exFAT (plain, the normal part, and VeraCrypt's inside); it offers to install it.
- VeraCrypt for VeraCrypt layouts: *"VeraCrypt is needed to create a VeraCrypt volume. Install it from
  https://www.veracrypt.fr/en/Downloads.html (Ubuntu .deb), then run this again."* Or run
  `deucalion deps --install --veracrypt`.
- The administrator password for VeraCrypt (to create and open the volume).

Other messages you may see:

| Message | Meaning |
|---|---|
| `/dev/sdX is not an external drive (your system disk is never offered).` | The device isn't an external drive Deucalion may change. |
| `No external drive found. Plug one in and try again.` | Nothing plugged in. |
| `This drive has no usable filesystem; choose a layout that formats it.` | `encrypt-folder` or `as-is` on an empty or unmounted drive. |
| `Choose a size for the encrypted part that leaves room for the normal part.` | `--size` too small (under 64 MB) or too large. |
| `This drive is FAT32, which cannot hold files of 4 GB or more.` | Encrypted folder of 4 GB or more on a FAT32 drive. |
| `Only N GB are free on this drive.` | Encrypted folder larger than the free space. |
| `… already exists.` | An encrypted folder file is already there; Deucalion never replaces it. |
| `To erase the drive non-interactively, pass --yes-erase sdX` | No terminal to ask in, and `--yes-erase` missing. |
| `Could not tell which disk holds your system, so no drive will be changed (this protects your system disk).` | Unusual system disk setup (for example a ZFS root); nothing is changed. |

## Exit codes

`0` set up; `1` an error, or you didn't confirm (*"Nothing was changed."*); `130` stopped.

## Related

- [Choosing a drive](../choosing-a-drive.md) and the [drive setup tutorials](../tutorials/drive-veracrypt.md)
- The app's [setup wizard](../app/drives.md#the-setup-wizard)
