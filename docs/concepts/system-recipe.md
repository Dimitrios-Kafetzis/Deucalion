# The system recipe

Your files are only part of what makes a computer yours. The rest is how it is set up: the apps you
installed, where they come from, your desktop settings, your Wi-Fi networks. The **system recipe**
describes all of this as readable text files. Every full backup saves it, in the `system` folder of
the backup. The app calls it **system settings**.

The recipe is *a description*, not a copy of system files. That is what makes it possible to replay
it on a **newer** Ubuntu version, where copying old system files over new ones would break things.

## What it contains

| In the recipe | File(s) in `system/` | Used by rebuild step |
|---|---|---|
| Ubuntu version, computer name, model, your user name, groups, shell | `info.json` | 1 Check, 8 Groups |
| apt packages you installed | `packages/apt-manual.txt` (+ `apt-installed.tsv`, the full list, for reference) | 3 Packages |
| Packages installed from downloaded `.deb` files, and where those files are in your home folder | `packages/apt-local.json` | 3 Packages |
| Software sources (apt repositories, PPAs) and their signing keys | `packages/apt/` | 2 Software sources |
| Snaps, with their channel and whether they are "classic" | `packages/snaps.json` | 3 Packages |
| Flatpak apps and remotes | `packages/flatpaks.json` | 3 Packages (listed only) |
| npm and pipx tools; VS Code extensions | `packages/other.json` | 3 Packages lists the npm and pipx tools; the VS Code list is kept for reference |
| All desktop settings (GNOME: wallpaper, dock, shortcuts, app settings…) | `desktop/dconf.ini` | 6 Desktop |
| GNOME extensions that were enabled | `desktop/gnome-extensions.json` | 6 Desktop |
| Your scheduled tasks (crontab), enabled services | `services/` | 8 Services |
| Files in `/etc` that you (or programs) changed or added | `etc/changed.json`, `etc/files/` | 7 System settings |
| Saved Wi-Fi and VPN connections, **with their passwords** | `network/` (and `/etc/netplan/90-NM-…` files on Ubuntu 23.10 and newer) | 8 Network |
| The administrator's crontab | `services/root-crontab.txt` | 8 Services |
| Software installed by hand in `/opt` and `/usr/local` | `software/manual-installs.json` | 3 Packages (listed only) |
| Names of Docker images and volumes, and of virtual machines (not their contents) | `software/containers-and-vms.json` | kept for reference |

Here is the `system` folder of the demo backup:

```text
--8<-- "snippets/cli/system-recipe.txt"
```

## Protected settings

Some of these settings can only be read by the administrator: saved Wi-Fi and VPN connections,
some `/etc` files and the administrator's crontab. Deucalion saves them only when **Include
protected settings** is on (it is on by default). Ubuntu then asks for your administrator password
at the start of the backup. See [Include protected settings](../tutorials/protected-settings.md).

Without the password, everything else is still saved. A copy of protected settings from an earlier
backup is kept, not deleted.

!!! warning "Wi-Fi passwords on an unencrypted drive"
    Saved connections contain their passwords. On a drive without encryption, anyone who has the
    drive can read them. Deucalion warns you when an unencrypted drive would get SSH keys, GnuPG
    keys or browser sessions from your home folder, but it does not warn about Wi-Fi passwords
    separately. If that matters to you, use an [encrypted drive](../choosing-a-drive.md) or turn
    **Include protected settings** off.

## How `/etc` changes are found

Deucalion compares every file in `/etc` with what Ubuntu's packages put there (using the package
system's checksums). It keeps:

- **modified** files: a package's file that you (or a program) changed;
- **added** files: files no package owns, created after Ubuntu was installed;
- **installer** files: files no package owns that haven't changed since Ubuntu was installed. A
  rebuild keeps these for reference only.

Files that are identical to Ubuntu's defaults are left out, and so are a few that must never be
copied: password hashes (`/etc/shadow`), the computer's identity (`/etc/machine-id`), private TLS
keys, SSH host keys and generated files. Files larger than 2 MB are skipped.

## The recipe is updated only when something changes

The recipe is first written to `~/.local/state/deucalion/system` on your computer, then backed up
like any other folder. Each file is rewritten only when its content changes, so an unchanged recipe
costs nothing on the next backup.

## Related

- [What a rebuild restores](rebuild.md)
- [Rebuild your computer](../tutorials/rebuild.md)
