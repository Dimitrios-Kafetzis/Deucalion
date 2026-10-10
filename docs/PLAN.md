# Deucalion — Plan for version 1

Deucalion backs up an Ubuntu machine to an external drive so that the home
folder and the system setup can be **rebuilt** on a new Ubuntu LTS or on a new
machine. It can be used from the command line (`deucalion`) or from a GNOME
app. Both use the same engine.

## 1. Goals and non-goals

**Goals (v1)**
- Full backup (home folder + "system recipe") or partial backup (selected folders/components).
- A single up-to-date copy on the drive, made of plain files you can open on Linux, macOS and Windows.
- Rebuild a new Ubuntu machine from the backup, even if the username is different.
- Restore single files or folders.
- Optional encryption: whole drive, an encrypted partition, or an encrypted folder.
- Safe by default: preview before any destructive step, nothing lost silently.

**Non-goals for v1** (planned for later versions, see §12)
- Snapshot history / retention
- Automatic or scheduled backups
- Full-disk image for disaster recovery on the same machine
- Restoring *onto* macOS/Windows (they only read and copy files from the drive)

## 2. Decisions

| Topic | Decision |
|---|---|
| Language | Python 3 (stdlib only). Runs on a fresh Ubuntu from the drive. |
| GUI | GTK4 + libadwaita (native GNOME look, preinstalled on Ubuntu 24.04+). |
| Drive filesystem | **exFAT** by default (readable on Linux, macOS and Windows). ext4 is offered for Linux-only use. |
| Linux metadata | Permissions, owners, symlinks and original file names are stored in a **manifest** on the drive and reapplied on restore. |
| Encryption | **VeraCrypt** (cross-platform) for all three modes; **LUKS** as a Linux-only alternative; or no encryption. |
| Backup model | Single mirror. Files deleted or overwritten on the machine move to `_removed/<date>/` on the drive. Only the user empties it. |
| Runs | Only when the user starts it. |
| Privileges | Runs as the normal user. Asks for the admin password only for steps that need it (§9). |

## 3. What gets backed up

### 3.1 Home folder
The whole `/home/<user>`, minus default exclusions (editable):
- `~/.cache`, `~/.local/share/Trash`, `~/snap/*/common/.cache`, browser caches,
  thumbnail caches, `~/.local/share/recently-used.xbel`
- Build/download junk patterns, off by default but available: `node_modules`, `__pycache__`, `.venv`

### 3.2 System recipe (`system/`)
Captured as data, not as system files, so it can be replayed on a newer release.

| Item | How |
|---|---|
| Ubuntu version, hostname, user, UID, hardware summary | `/etc/os-release`, `hostnamectl`, `id` |
| apt packages installed manually | `apt-mark showmanual` |
| Third-party repositories + signing keys | `/etc/apt/sources.list.d/*`, referenced keyrings |
| Snaps (with channel and confinement) | `snap list` |
| Flatpaks + remotes | `flatpak list`, `flatpak remotes` |
| Python/pipx/npm global tools | `pipx list`, `npm -g ls` (if present) |
| GNOME settings | `dconf dump /` |
| GNOME extensions | list + the extension folders (already in home) |
| Changed `/etc` files | files that differ from the package defaults (dpkg checksums) + files not owned by any package |
| Network connections (Wi-Fi, VPN) | `/etc/NetworkManager/system-connections/` (needs admin; contains passwords, so a warning is shown if the drive is not encrypted) |
| Services | enabled system services list, user systemd units, user and root crontabs |
| Fonts, `/etc/hosts`, `/etc/fstab` extra entries | included in the above |

### 3.3 Large / special data (optional components)
- **Docker:** images and volumes exported with Docker's own tools (`docker save`, volume tar export). Docker's internal storage is never copied directly.
- **Virtual machines (libvirt/virt-manager, VirtualBox):** disk images + VM definitions.
- **Any extra folder**, for example `/srv` or a data partition.
- Large files get a size estimate and a free-space check before copying. exFAT cannot store sparse files, so the tool warns when a file's on-disk size is much smaller than its apparent size.

### 3.4 Full vs partial
- **Full** = home + system recipe + any enabled large-data components.
- **Partial** = the folders/components you pick, ad hoc or saved as a named profile.
- A partial backup only updates the selected parts of the mirror. It never deletes other parts.

## 4. Layout on the drive

```
<DRIVE>/                         (plain, unencrypted area)
├── READ-ME-FIRST.txt            how to open the backup on Linux / macOS / Windows
├── Deucalion-Tool/              copy of the tool; run ./deucalion on a fresh Ubuntu
└── Deucalion-Backup/            (or inside the encrypted volume/folder)
    ├── backup.json              machine, user, Ubuntu version, date, status, tool version
    ├── home/                    mirror of /home/<user>
    ├── system/                  the recipe (§3.2), as readable text files
    ├── extras/                  Docker exports, VM images, extra folders
    ├── _removed/<date>/         files deleted/overwritten on the machine since the last run
    └── .deucalion/
        ├── manifest.sqlite      permissions, owners, symlinks, original names, sizes
        ├── drive-id             identifies this as a registered Deucalion drive
        └── logs/
```

With option (a), whole-drive encryption, there is no unencrypted area. Install VeraCrypt and Deucalion on the new machine first.

## 5. exFAT handling (manifest + safe names)
- **Permissions/owners/executable bits** → stored in the manifest and reapplied on restore. Example: `~/.ssh` comes back with 0700/0600.
- **Symlinks** → stored in the manifest, recreated on restore.
- **Names exFAT cannot store** (`: * ? " < > | \`, control characters, trailing dots/spaces) → saved under an encoded name such as `report%3A2024.txt`; the original name is recorded and restored.
- **Case collisions** (`Notes` and `notes` in the same folder) → the second one gets a suffix; the original name is recorded.
- **Timestamps** → exFAT's 10 ms precision is handled (`--modify-window`), so unchanged files aren't copied again.
- When the target is ext4 (LUKS / Linux-only), metadata is stored natively too, and the manifest is still written.

### Implementation notes (milestone 1)
- The copy engine is written in Python instead of calling rsync: rsync cannot store a file
  under a different (exFAT-safe) name, and every file has to be visited anyway to record
  its metadata. Copies go to a staging file and are renamed into place, as rsync does.
- A backup is planned first and the plan is kept in a temporary SQLite file, so memory stays
  small even for millions of files (2.3M files ≈ 50 MB RAM).
- Incremental backups trust the manifest instead of listing every folder on the drive (slow on
  USB hard disks). `deucalion verify` and `backup --check-drive` catch files missing on the drive;
  the next backup copies them again.
- Before backing up to a drive that holds another machine's/user's backup, the tool warns and asks.

### Implementation notes (milestone 2)
- The system recipe is generated into `~/.local/state/deucalion/system/` and backed up like a
  folder to `system/`; files are rewritten only when their content changes.
- `/etc` changes are found by comparing with dpkg's checksums. Files that no package owns are
  dropped when they are byte-identical to any packaged file (e.g. `/etc/profile` from
  base-files), and marked "installer" when unchanged since the OS install.
- On Ubuntu 23.10+ NetworkManager connections live in `/etc/netplan/90-NM-*.yaml`; both these
  and classic keyfiles are saved and restored.
- Administrator work goes through one helper process (`helper.py`, started once with pkexec or
  sudo) that accepts only a fixed list of operations with checked arguments.
- Still to do in v1: Docker image/volume export and VM disk images (currently only listed in
  `system/software/containers-and-vms.json`), and a polkit policy with a friendly prompt (M5).

### Implementation notes (milestone 3)
- Partitioning, exFAT formatting, LUKS creation, unlocking and mounting go through UDisks
  (D-Bus): Ubuntu allows the logged-in user to do this on non-system drives, so no
  administrator password is needed. A LUKS filesystem is created with `take-ownership`.
- VeraCrypt volumes are created with the VeraCrypt CLI (`--stdin` for the password) and
  opened with `cryptsetup --type tcrypt --veracrypt` through the administrator helper.
  Encrypted partitions get the Linux partition type, so Windows doesn't offer to format them.
- The admin helper re-checks on its own that it never touches the system disk.
- Not yet verified on real hardware: VeraCrypt create/open, and exFAT formatting
  (both need `exfatprogs`/VeraCrypt installed and the administrator password).

## 6. Encryption options

| Option | Result | Readable on |
|---|---|---|
| **a) Whole drive** | Entire drive is one VeraCrypt volume (exFAT inside) | Linux, macOS, Windows with VeraCrypt |
| **b) Encrypted partition** | Drive split into a VeraCrypt partition + a normal exFAT partition | Encrypted part: with VeraCrypt; normal part: everywhere |
| **c) Encrypted folder** | A VeraCrypt container file (e.g. `Deucalion-Backup.hc`) on the existing drive; opens as a folder | Container: with VeraCrypt; rest of drive: everywhere |
| **d) None** | Plain exFAT | Everywhere |
| **LUKS (Linux-only)** | Whole drive or partition with LUKS2 + ext4 | Ubuntu out of the box; not macOS/Windows |

Notes
- **Creating** a VeraCrypt volume needs VeraCrypt installed (the tool explains how). **Opening** one on Ubuntu works with the built-in `cryptsetup`.
- The option (c) container has a fixed size, chosen at creation. The tool suggests a size from the current backup selection plus headroom.
- Passwords are never stored by the tool.

## 7. Restore

### 7.1 Restore files
- Browse or search the backup, pick files/folders, restore to the original place or another folder.
- A preview shows what will be added and what will be overwritten.
- Overwritten files are first moved to `~/Deucalion-before-restore/<date>/`, so a restore can be undone.

### 7.2 Rebuild (new machine wizard)
Each step shows a preview, can be skipped, and can be resumed if interrupted.

1. **Check**: backup info vs this machine (Ubuntu version, username, free space).
2. **User mapping**: detect `/home/olduser` → `/home/newuser`; you confirm.
3. **Repositories**: re-add third-party repos and keys; each one is checked against the new Ubuntu release and skipped with a warning if it isn't available.
4. **Packages**: install apt packages, snaps, flatpaks. Missing ones are reported, not fatal.
5. **Home folder**: restore files + permissions + symlinks. Config files that contain the old home path are listed and fixed after you approve.
6. **Desktop**: load GNOME settings, enable extensions.
7. **System config**: each changed `/etc` file shown as a before/after diff; accept or skip one by one.
8. **Services & network**: crontabs, user services, enabled services, Wi-Fi/VPN connections.
9. **Report**: what was done, skipped and failed, saved as a log. Log out and back in.

The wizard recommends running from a fresh login with other apps closed.

## 8. Safety rules
1. **Right drive only**: backups go only to a registered drive (identified by its ID, not its name or mount point).
2. **Read-only source**: a backup never modifies or deletes anything on the machine.
3. **Nothing lost on the drive**: deleted/overwritten files go to `_removed/`, which only the user empties.
4. **Preview first**: every restore and rebuild step shows what will change before doing it.
5. **Undo for restores**: overwritten local files are kept in `~/Deucalion-before-restore/`.
6. **Destructive drive operations** (formatting, partitioning, encrypting) need you to type the drive's name to confirm. The internal system disk is never offered.
7. **Space check** before every backup. If the drive is full, the tool stops and suggests emptying `_removed/`. It never deletes anything on its own.
8. **Interrupted backups are safe**: the run is marked incomplete in `backup.json` and simply continues next time.
9. **Verify**: `deucalion verify` compares the backup against the machine (quick: sizes/dates; full: checksums).
10. **Secrets warning** when SSH keys, browser profiles or Wi-Fi passwords are being written to an unencrypted drive.
11. **Logs** of every run on the drive and in `~/.local/state/deucalion/`.

## 9. Privileges
- The app always runs as your user. The GUI never runs as root.
- Steps that need admin rights ask for your password at that moment (`pkexec` in the GUI, `sudo` in the CLI) and run through one small helper with a fixed list of allowed actions:
  - reading root-only system files (network connections, some `/etc` files)
  - formatting / partitioning / encrypting a drive
  - opening VeraCrypt/LUKS volumes
  - installing packages and writing `/etc` during rebuild

## 10. CLI

```
deucalion                         # opens the GUI
deucalion drives                  # list external drives and registered targets
deucalion setup-drive [DEVICE]    # prepare a drive: format + encryption choice (a/b/c/d/LUKS), register it
deucalion register PATH           # use an existing (already formatted) drive or folder as a target
deucalion open | close            # unlock + mount / unmount + lock the target
deucalion backup                  # full backup
deucalion backup --only ~/Documents ~/Pictures    # partial
deucalion backup --profile work   # saved partial selection
deucalion backup --dry-run        # show what would be copied, sizes, warnings
deucalion status                  # last backup, sizes, _removed size, warnings
deucalion restore PATH... [--to DIR] [--dry-run]  # restore files/folders
deucalion rebuild [--step NAME]   # new-machine wizard (interactive)
deucalion removed list | empty    # manage _removed/
deucalion verify [--full]
deucalion config show | edit      # exclusions, components, profiles
```

## 11. GUI (GTK4 + libadwaita)

- **Overview**: drive card (not connected / locked / ready), last backup and size, `_removed/` size, buttons **Back Up Now** and **Restore**.
- **Back Up**: Full or Custom; a list of components with sizes (home folders, system recipe, Docker, VMs, extra folders); exclusions; estimate → **Start** → progress (current item, speed, time left, Cancel) → summary.
- **Restore**: two cards: *Restore Files* (browser with search, pick destination, preview) and *Rebuild This Machine* (the §7.2 wizard, one page per step).
- **Drives**: list of drives; *Set Up New Drive* wizard with the encryption choices explained in plain words; unlock/lock.
- **Removed Files**: grouped by date, sizes, *Empty* (with confirmation).
- **Preferences**: exclusions, components, profiles.
- **Logs**: past runs.

Light and dark mode follow the system theme.

## 12. Later versions
- Snapshot history with retention (e.g. 7 daily / 4 weekly / 12 monthly)
- Automatic backup when the drive is plugged in, or on a schedule
- Full-disk image for same-machine disaster recovery
- Possibly: password-file integration, multiple target drives, notifications

## 13. Code structure

```
Deucalion/
├── deucalion                  launcher (CLI, or GUI when run with no arguments)
├── deucalion/
│   ├── cli.py
│   ├── config.py              ~/.config/deucalion/config.json
│   ├── drives.py              detect drives (lsblk/udisks), register, mount
│   ├── crypto.py              VeraCrypt + LUKS: create, open, close
│   ├── names.py               exFAT-safe name encoding
│   ├── manifest.py            SQLite manifest
│   ├── backup.py              scan → plan → copy engine, _removed handling, progress
│   ├── recipe.py              system recipe collectors (§3.2)
│   ├── restore.py             file restore with preview/undo
│   ├── rebuild.py             new-machine wizard steps
│   ├── verify.py
│   ├── helper.py              privileged helper (fixed action list)
│   └── gui/                   GTK4/libadwaita app and pages
├── data/                      .desktop file, icon, READ-ME-FIRST template
├── tests/                     run against loop-mounted exFAT/ext4 image files
├── install.sh                 install for the current user (~/.local)
└── docs/PLAN.md
```

## 14. Build order (milestones)

Each milestone ends with something you can try on a real drive.

1. **Core backup + file restore (CLI)**: register a plain folder/drive, full and partial backup, manifest, safe names, `_removed/`, dry-run, status, restore with preview/undo, verify.
2. **System recipe + rebuild (CLI)**: collectors, user mapping, the rebuild wizard steps.
3. **Drives + encryption**: setup-drive (a/b/c/d/LUKS), open/close, the tool copy and README on the drive.
4. **GUI**: all screens on top of the same engine.
5. **Polish**: install.sh, desktop entry and icon, docs, a full rebuild test in a VM with a different username.

Testing never touches real drives: formatting and encryption tests run on disk-image files.
