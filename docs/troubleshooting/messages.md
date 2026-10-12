# Messages and what to do

The messages Deucalion shows, in its own words, grouped by topic. Use your browser's search
(++ctrl+f++) to find yours.

## The backup drive

### "Backup drive '…' is not connected (or not unlocked). Plug it in and try again."

Also: **"The backup drive is not connected."** (encrypted drives), and in the app *"“Alex Backup” is not
connected"*.

```text
--8<-- "snippets/cli/backup-not-connected.txt"
```

- **Means:** Deucalion can't find the registered backup drive.
- **Why:** it isn't plugged in; it is encrypted and locked; or its part isn't mounted (for example on
  a computer without a desktop, or on Ubuntu 26.04 a drive that hasn't been opened yet).
- **Fix:** plug it in. Open it in the Files app once (this mounts it). If it is encrypted, unlock it
  (**Unlock** in the app, or `deucalion open`). Then try again.

### "The backup drive '…' is locked." / "… is locked"

- **Means:** the drive is plugged in but encrypted and locked.
- **Fix:** commands ask for the password themselves. In the app, click **Unlock**.

### "Another Deucalion task is already using this drive."

```text
--8<-- "snippets/cli/another-task.txt"
```

- **Means:** a backup, restore, rebuild or check is already running on this drive (in the app, or in
  another terminal).
- **Why:** two tasks on one drive at once could get in each other's way, so Deucalion allows only one.
- **Fix:** wait for the other task to finish (or stop it), then try again. The drive is free again as
  soon as the other task ends, even if it crashed. Check for an open Deucalion window or a terminal
  still running a command.

### "No backup drive registered yet. Run: deucalion setup-drive (or deucalion register <drive folder>)"

- **Means:** Deucalion doesn't know a backup drive on this computer yet.
- **Fix:** [set one up](../choosing-a-drive.md); for a drive that already has a backup:
  `deucalion open` (encrypted) or `deucalion register <drive folder>`.

### "Several backup drives are registered; choose one with --target NAME."

- **Fix:** add `--target "Name"` (names from `deucalion targets`), or make one the default (the star button on the
  **Drives** page, or `deucalion register <its backup folder> --default`).

### "No registered backup drive called '…'."

- **Fix:** check the name with `deucalion targets` (names are case-sensitive; use quotes for names with
  spaces).

### "… is on the same disk as your system. A backup there would be lost together with the system. Choose an external drive."

- **Means:** you tried to register a folder on your computer's own disk.
- **Why:** if that disk fails, you would lose the backup too.
- **Fix:** use an external drive.

### "The drive is in use. Close any window or program that shows its files, then try again."

- **Means:** the drive couldn't be unmounted or locked.
- **Fix:** close Files windows and programs that use files on the drive (also a terminal whose current
  folder is on the drive: `cd ~`), then try again.

## Passwords and encryption

### "Wrong password." / "wrong password, or this is not a VeraCrypt volume"

- **Fix:** type it again carefully. Check ++caps-lock++ and that the keyboard layout is the one you
  used when you chose the password. If you have forgotten it, see
  [FAQ: I forgot my password](faq.md#i-forgot-my-backup-password).

### "Administrator access was not granted."

- **Means:** the administrator password window was cancelled, or the password was wrong.
- **Fix:** try again and type your administrator (login) password. If your account isn't an
  administrator, ask the computer's administrator. For backups, you can avoid the password: turn off
  **Include protected settings** (see [Include protected settings](../tutorials/protected-settings.md)).

### "The installed administrator helper does not match this version of Deucalion. Update it with: ./install.sh --system-helper (from the Deucalion folder)"

- **Means:** the system-wide administrator helper is from another version of Deucalion.
- **Why:** after updating Deucalion, the helper in `/usr/local/libexec/deucalion/` wasn't updated.
  Deucalion refuses to use a helper that isn't exactly its own.
- **Fix:** in the folder where you downloaded Deucalion: `./install.sh --system-helper`.

### "VeraCrypt is needed to create a VeraCrypt volume. Install it from https://www.veracrypt.fr/en/Downloads.html (Ubuntu .deb), then run this again."

- **Fix:** `deucalion deps --install --veracrypt`, or the **Install** button in the app's drive wizard,
  or install it yourself. Only *creating* a VeraCrypt drive needs it; opening one works without it.

### "… libSM.so.6: cannot open shared object file …"

- **Means:** VeraCrypt can't start.
- **Why:** VeraCrypt's package needs the `libsm6` library without declaring it; a computer without a
  desktop may not have it.
- **Fix:** `sudo apt install libsm6`.

### "The VeraCrypt download could not be verified (bad, expired or revoked signature). Nothing was installed."

Also *"…could not be verified (bad or missing signature)…"*, *"Could not download VeraCrypt's signing
key…"*, *"Unexpected VeraCrypt download location…"*, *"The VeraCrypt release offered … is older than
expected…"*.

- **Means:** the VeraCrypt download didn't pass Deucalion's checks, so it wasn't installed.
- **Fix:** try again later (a download may have been cut). If it keeps failing, install VeraCrypt from
  [veracrypt.fr](https://www.veracrypt.fr/en/Downloads.html) yourself.

### "A password is needed but there is no terminal to ask for it."

- **Means:** a command needed the backup's password but runs without a terminal (a script, a cron job).
- **Fix:** unlock the drive first in a terminal, or see [Use Deucalion without a desktop](../tutorials/headless.md).

## Backing up

### "Not enough space on the drive: this backup needs about … but only … is free. You can free space by emptying _removed/ (deucalion removed empty) or excluding large folders."

- **Means:** the backup wouldn't fit, so nothing was copied.
- **Fix:** see [Free space on the drive](../tutorials/free-space.md): empty old groups in Removed Files,
  leave out large folders, or use a bigger drive.

### "The backup drive is full. Free some space (for example empty _removed/ with: deucalion removed empty, or leave out large folders) and run again."

- **Means:** the drive filled up *during* the backup (for example because files grew meanwhile).
- **Fix:** free some space (as above) and run the backup again. Nothing is damaged; it continues where
  it stopped.

### "This drive holds the backup of …@… (home folder …), but this is …@… (home folder …). …" { #this-drive-holds-the-backup-of }

- **Means:** the drive's backup comes from another computer or user (or a different home folder).
- **Why it matters:** backing up makes the drive mirror *this* computer: everything that is only in the
  old backup moves to Removed Files.
- **Fix:** on a new computer, [rebuild](../tutorials/rebuild.md) or restore first. If you really want
  this drive to follow this computer from now on, answer **y** (or click **Start Backup** in the app).
  Nothing is deleted: the old files stay in Removed Files until you empty them.

### "Note: this drive is not encrypted, and your backup includes keys or logged-in sessions (…)."

- **Means:** your backup holds SSH keys, GnuPG keys, keyrings or browser sessions, on a drive anyone
  can read.
- **Fix:** nothing is required, but keep the drive safe, or use an [encrypted drive](../choosing-a-drive.md).

### "…: changed while it was being copied; it will be copied again next time."

- **Means:** a program changed that file while Deucalion copied it, so the copy may not be consistent.
- **Fix:** nothing to do now; the next backup copies it again. For files that change all the time (a
  running virtual machine, a database), close the program before backing up.

### "…: could not be copied (…)." / "…: cannot be read (…); keeping what is already backed up"

- **Means:** Deucalion couldn't read that file or folder (for example permissions). The previous backup
  of it, if any, is kept.
- **Fix:** if you need it backed up, fix its permissions (it must be readable by you). Files only the
  administrator can read in your home folder are unusual; check who owns them.

### "…: special file (socket, pipe or device)"

- **Means:** these aren't real files and can't be backed up. Nothing to do.

### "…: another filesystem is mounted here; not followed"

- **Means:** a folder in your home folder is a mount point of another disk (or a network share). It is
  not backed up as part of the home folder.
- **Fix:** if you want it backed up, add it as an [extra folder](../tutorials/outside-home.md).

### "… is empty, but the backup has files from it. Skipped, to keep the backup safe (is its drive connected?)."

- **Means:** a folder you back up (often an extra folder on another disk) is empty now, but wasn't
  before. Rather than moving its whole backup to Removed Files, Deucalion skips it.
- **Fix:** mount its disk and back up again. If you really emptied it, remove it from your extra folders.

### "…: sparse file; it uses … on this machine but will take … on the drive."

- **Means:** a large file that takes little space on your disk (for example a virtual machine disk)
  takes its full size on the drive.
- **Fix:** nothing, or leave it out if you don't need it backed up.

### "System settings (/etc, network) were not updated because administrator access was not used; the copy from an earlier backup is kept."

- **Means:** this backup ran without the administrator password (a dry run, `--no-admin`, or the
  option off), so the protected settings weren't read again. Those from an earlier backup stay.
- **Fix:** nothing, unless you want them updated: run a full backup and give the password.

### "N system files (and network connections) can only be saved with administrator access."

- **Means:** a backup without administrator access couldn't read some system files, and no earlier
  backup had them.
- **Fix:** turn **Include protected settings** on and back up again.

### "…: not found on this machine; skipped." / "…: excluded by your exclusion rules; skipped." / "…: is not a folder any more; skipped."

- **Means:** in a partial backup, one of the paths you named doesn't exist, is left out by your
  exclusions, or changed from a folder to a file.

### "… is not inside your home folder or a configured extra folder."

- **Fix:** partial backups can only cover your home folder and extra folders. To back up another folder,
  [add it as an extra folder](../tutorials/outside-home.md).

### "This backup was created on a Linux filesystem but the drive is now a different filesystem (e.g. exFAT). Register a new backup folder instead."

- **Means:** the backup folder was made on a Linux-formatted drive, which was later reformatted or
  copied to exFAT/NTFS.
- **Fix:** register a new backup folder on that drive and make a full backup.

### "…/_removed should be a folder but is not. Rename it, then run the backup again."

- **Fix:** something replaced the `_removed` folder on the drive with a file. Rename that file, then
  back up again.

## Restoring

### "… is not part of the backup." / "… is not in the backup."

- **Fix:** check the path with `deucalion ls` (or browse it in the app). Paths of extra folders are their
  original paths (`/srv/shared/…`).

### "“…” and “…” would be restored to the same place (…). Restore them separately, or into different folders."

- **Means:** with **To another folder…** (`--to`), two items with the same name would land in the same
  place.

### "…: not restored (…); the version that was there has been kept (see above)."

- **Means:** one file couldn't be restored; your own version is untouched (or put back).

### "…: restored, but its content does not match the checksum recorded at backup time. The copy on the drive may be damaged."

- **Fix:** check the drive with `deucalion verify --full`; see [Check that a backup is intact](../tutorials/verify.md).

### "Some files could not go to the undo folder and were kept next to their original place instead: …"

- **Means:** a file to be replaced couldn't be moved into `~/Deucalion-before-restore` (for example it is
  on another disk), so it was renamed next to itself: `name.before-restore-<date>`.

### "System settings are not restored in place. Use Rebuild, or choose “To another folder…” to look at them."

- **Means:** (app) the system recipe can't be restored into the system directly.

## Setting up drives

See the table of messages in [`setup-drive`](../cli/setup-drive.md#what-it-needs). The most important:

### "Could not tell which disk holds your system, so no drive will be changed (this protects your system disk)."

- **Means:** Deucalion couldn't work out which disk your system runs from (for example with a ZFS root),
  so it refuses to change any drive.
- **Fix:** prepare the drive yourself (for example as exFAT with the Disks app) and use
  [`deucalion register`](../cli/register.md).

### "/dev/… holds your system. Deucalion never changes it."

- **Means:** you named your system disk. It is always refused.

## Rebuilding

### "apt update reported problems; some repositories may not work."

- **Means:** after adding software sources, refreshing the package lists showed errors (shown in the log
  above it), for example a source that is temporarily unreachable.
- **Fix:** read the log lines starting with `E:` or `W:`. Remove a source that doesn't work from
  `/etc/apt/sources.list.d/` (the files Deucalion added keep their original names), then run
  `sudo apt update`.

### "apt package … could not be installed." / "snap … could not be installed."

- **Fix:** install it later yourself (`sudo apt install …`), or run the step again
  (`deucalion rebuild --step packages`) once its software source works.

### "rebuild needs a terminal to ask you questions (or use --dry-run / --yes)."

- **Fix:** run it in a terminal, or with `--dry-run` / `--yes`.

### "Desktop settings could not be loaded: …" / "This machine has no GNOME settings tool (dconf)…"

- **Fix:** install `dconf-cli` (and a GNOME desktop) and run the desktop step again.

### "Your scheduled tasks (crontab) are in the backup, but cron is not installed here. …"

- **Fix:** `sudo apt install cron`, then `deucalion rebuild --step services`.

## Running Deucalion

### "Please run Deucalion as your normal user (not with sudo). It asks for the admin password itself when a step needs it."

- **Fix:** run it without `sudo`.

### "The app can't start (…). The python3-gi, gir1.2-gtk-4.0 and gir1.2-adw-1 packages are needed."

- **Fix:** `deucalion deps --install`.

### "The app needs Ubuntu 24.04 or newer (libadwaita 1.5; this computer has 1.1). Everything also works from the terminal: run 'deucalion --help' to see the commands."

- **Means:** this Ubuntu version (for example 22.04) is too old for the app.
- **Fix:** use the [command line](../cli/index.md), or upgrade Ubuntu.

### "deucalion: command not found"

- **Fix:** right after the first installation, log out and back in once; or use `~/.local/bin/deucalion`.
  From a drive's `Deucalion-Tool` folder, use `bin/deucalion`.

### "Configuration file is damaged: …"

- **Fix:** open the file (`deucalion config path` shows where) in a text editor and fix it, or rename it
  to start again with the defaults (you then need to register your drives again).
