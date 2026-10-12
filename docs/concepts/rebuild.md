# What a rebuild restores

A **rebuild** sets up a computer again from a full backup: a new computer, or your own computer after
a fresh install of a newer Ubuntu version. It works even if your user name on the new computer is
different. It runs in eight steps. Each step first shows what it would do and changes nothing until
you click **Apply** (or press ++enter++ in the terminal). You can skip any step, stop at any time,
and continue later.

## The eight steps

| Step | What it does | Needs your administrator password |
|---|---|---|
| 1. **Check the backup and this machine** | Shows where the backup comes from and compares it with this computer: Ubuntu version, user name, free space, processor type. | no |
| 2. **Software sources (apt repositories)** | Adds the extra software sources you had (for example Google Chrome's, or a PPA), adapted to this Ubuntu version, with their keys. Each one is checked online first; one that doesn't exist for this version is shown as **NOT available** and is not selected. | yes |
| 3. **Applications and packages** | Installs the apt packages you had installed, your snaps, and packages from `.deb` files that are still in your backed-up home folder. Packages that don't exist here are listed but not installed. | yes |
| 4. **Your home folder** | Restores your files, folder by folder. You choose which folders. | no |
| 5. **Update paths in your settings** | If your home folder path changed (for example `/home/alex` → `/home/alexk`), updates settings files and links that still point to the old path. | no |
| 6. **Desktop settings (GNOME)** | Loads your desktop settings: wallpaper, dock, keyboard shortcuts, app settings. | no |
| 7. **System settings (/etc)** | Puts back the system files you had changed, one by one. **Show Changes** shows the difference for each. | yes |
| 8. **Groups, scheduled tasks, services and network connections** | Adds you to the groups you were in, restores your crontab, enables services, and imports Wi-Fi and VPN connections. | yes |

## What it deliberately leaves alone

A rebuild is careful by design. It does **not**:

- **remove anything**: no package is ever removed (apt runs with `--no-remove`);
- **touch Ubuntu's own software sources** (`ubuntu.sources`, `sources.list`): the new Ubuntu
  version's own sources are always kept. Extra sources are added as new files;
- **install kernels, drivers, firmware or hardware-specific packages**: packages whose names start
  with `linux-image`, `linux-headers`, `linux-modules`, `linux-generic`, `linux-oem`,
  `linux-firmware`, `oem-`, `nvidia-driver`, `grub-` or `shim-signed` are left to the Ubuntu
  installer, which picks the right ones for the new hardware. Hardware-specific (OEM) software
  sources are pre-selected only if the new computer is the same model;
- **copy the old computer's identity**: `/etc/passwd`, `/etc/group`, `/etc/hostname`,
  `/etc/machine-id`, `/etc/fstab` (the disk layout), `/etc/crypttab`, the time zone and locale
  files are kept in the backup **for reference only**, as are `/etc` files the installer created;
- **restore apt, netplan, NetworkManager, PAM, cloud-init, initramfs or GRUB files from `/etc`**:
  these are handled by their own steps or by the installer;
- **overwrite without keeping the original**: every file it replaces is kept first (see below).

/etc files are **pre-selected** only in well-understood places (udev rules, kernel module and
`sysctl` settings, X11 settings, printers, `/etc/environment`, security limits and `sudoers.d`), only
when nothing would be overwritten or the file is a package's configuration file you had changed, and
only when the program that uses it is installed. Everything else is listed, unticked, for you to
review with **Show Changes**.

## Where the originals go

| What was replaced | Where the original is kept |
|---|---|
| Files in your home folder (steps 4 and 5) | `~/Deucalion-before-restore/…` (the undo folder) |
| Your desktop settings (step 6) | `~/Deucalion-before-restore/<date>-desktop/dconf-before.ini` |
| Your crontab (step 8) | `~/Deucalion-before-restore/<date>-crontab/crontab-before.txt` |
| `/etc` files and the administrator's crontab (steps 7 and 8) | `/var/backups/deucalion/<date>/…` |

## Running it again is safe

Each step remembers when it was done (in `~/.local/state/deucalion/rebuild.json`). Running the
rebuild again skips the finished steps; you can run any step again on purpose. A second run changes
nothing that is already right: files that are the same are not copied, sources that exist are not
added again, packages that are installed are not offered again.

## After a rebuild

Log out and back in: new group memberships and some desktop settings take effect only then.

## Related

- [Rebuild your computer](../tutorials/rebuild.md) (the full walk-through)
- [The system recipe](system-recipe.md)
- [The Rebuild page](../app/rebuild.md) and [`deucalion rebuild`](../cli/rebuild.md)
