# Portability: technical reference

This page is the technical background for the [roadmap](roadmap.md): which code is portable, how each
platform will work, what can go wrong, and how it is tested. The roadmap says *what* is built and
*when*; this page says *how* and *why*.

It was written on 2026-10-13 from the code of version 0.2.1. Statements marked **To verify** were
not checked on the platform itself; check them before relying on them.

## 1. Code map { #code-map }

About 9,650 lines of Python: 7,682 in `deucalion/*.py` and `deucalion/gui/*.py`, and 1,966 in
`deucalion/gui/pages/`. There is no platform check anywhere in the code today (no `sys.platform`
or `os.name`).

### 1.1 Portable as written

| Module | Notes |
|---|---|
| `manifest.py` | SQLite. Paths are stored as bytes with `/` as separator, so they are independent of the platform. |
| `names.py` | exFAT-safe names. Already handles Windows reserved names (`CON`, `LPT1`, …), trailing dots and spaces, and the 255 UTF-16 unit limit. `fold_exfat` is only `.upper()` (see §4.4). |
| `verify.py` | Reads the manifest and the drive. Imports `backup`, which isn't portable yet (§1.2). |
| `config.py` | `Excluder` and `Config` are portable. `config_dir` and `state_dir` use XDG paths. |
| `logs.py` | Portable. |
| `backup.Scanner`, `backup.Executor`, `restore.Restorer` | The planning and copying logic is portable, except the calls in §1.2. |

### 1.2 POSIX or Linux calls inside the engine

| Where | Call | Problem elsewhere |
|---|---|---|
| `backup.py` (module top) | `import grp, pwd` | Doesn't exist on Windows: **the engine can't be imported there**. |
| `target.py` (module top) | `import fcntl` (used by `Target.lock`) | Same, on Windows. |
| `recipe.py` → `helper.py` (module top) | `import grp, pwd` | Same, on Windows. `cli.py` imports all of these, so `deucalion --help` fails on Windows. |
| `backup.Scanner.__init__` | `os.statvfs` | Missing on Windows; the `AttributeError` isn't caught by the surrounding `except OSError`. |
| `backup.Executor.run` | `os.sync()` | Missing on Windows. |
| `backup.BackupJob._write_summary` | `os.uname()` | Missing on Windows. |
| `backup._uname`, `backup._gname` | `pwd.getpwuid`, `grp.getgrgid` | Missing on Windows. |
| `restore.Restorer.__init__`, `cli.main` | `os.geteuid()` | Missing on Windows. |
| `backup._same_content` | `st_ctime` as *change* time | On Windows it is the *creation* time (deprecated there since Python 3.12). The check for "edited, then its date put back" would quietly stop working. |
| `target.Target.create` → `util.is_on_system_disk`, `util.is_posix_fs` | `findmnt`, `lsblk` through `util.run` | `util.run` doesn't catch a missing program: **registering a drive crashes on macOS**. |
| `target.Target.candidate_roots` | reads `/proc/self/mountinfo` | Linux only. It fails quietly elsewhere, so a drive mounted at another place isn't found. |
| `restore.Restorer.execute.move_aside` | `undo_root / str(path).lstrip("/")` | On Windows, `str(path)` starts with `C:\`, and joining an absolute path gives back the original path itself (§5.2). |

### 1.3 Linux-specific (works on any modern distribution)

| Module and function | Commands and interfaces |
|---|---|
| `udisks.UDisks` | UDisks2 over D-Bus (PyGObject), `udisksctl loop-setup`, `udevadm settle`, `losetup -j` |
| `drives.list_drives` | `lsblk -J -b` |
| `util.mount_info`, `mount_points`, `backing_disks`, `is_encrypted` | `findmnt -J`, `lsblk -s -J`, `/sys/block/*/loop/backing_file` |
| `drivesetup.DriveSetup` | the above, plus `/dev/disk/by-partuuid`, `/dev/disk/by-uuid`, `/media/` and `/run/media/` mount roots, `blkid` (in `cli.py`) |
| `privileged.Privileged` | `pkexec`, `sudo`, `sudo -n`, `/usr/bin/python3 -I helper.py serve` |
| `helper.op_veracrypt_create`, `op_veracrypt_open`, `op_veracrypt_close` | `veracrypt --text --create`, `cryptsetup open --type tcrypt --veracrypt`, `losetup`, `mkfs.exfat -c 8K`, `wipefs -a`, `mount`, `umount` |
| `helper.op_enable_units`, `op_add_groups`, `op_nm_import`, `op_reload` | `systemctl`, `usermod -aG`, `nmcli connection reload`, `udevadm`, `sysctl --system` |
| `recipe._services`, `rebuild.ServicesStep` | `systemctl list-unit-files`, `crontab -l`, `id -Gn` |
| `recipe._desktop`, `rebuild.DesktopStep` | `dconf dump /`, `dconf load /`, `gnome-extensions list` |
| `recipe._flatpaks` | `flatpak list`, `flatpak remotes` (the rebuild only lists Flatpaks in 0.2) |
| `gui/` | GTK 4 and libadwaita 1.5 or newer, `Gio.VolumeMonitor`, `Gio.AppInfo.launch_default_for_uri` |
| `install.sh` | XDG folders, `/usr/local/libexec/deucalion`, `/usr/share/polkit-1/actions` |

### 1.4 Debian family (Debian, Ubuntu, Mint), not only Ubuntu

| Module and function | What |
|---|---|
| `helper.scan_etc`, `_dpkg_conffiles`, `_dpkg_owned_etc`, `_packaged_md5s` | Reads `/var/lib/dpkg/status` and `/var/lib/dpkg/info/*.list`, `*.md5sums` |
| `helper.install_time` | `/var/log/installer` (Ubuntu's installer), else `/etc/machine-id` |
| `recipe._apt`, `recipe._find_debs` | `apt-mark showmanual`, `dpkg-query -W`, `apt list --installed`, `dpkg-deb -f` |
| `rebuild._installed_packages`, `_apt_candidates` | `dpkg-query -W`, `apt-cache policy` |
| `helper.op_apt_*` | `apt-get update`, `apt-get install -y --no-remove` |
| `deps._has_package`, `deps.apt_install` | `dpkg-query -W` (**not caught when missing: `deucalion deps` crashes on Fedora**), `apt-get install` |
| `helper.op_collect_admin`, `op_put_crontab` | the root crontab at `/var/spool/cron/crontabs/` (a Debian path) |

### 1.5 Ubuntu only

| Module and function | What |
|---|---|
| `aptsources.Repo.kind`, `is_ubuntu_mirror` | `UBUNTU_HOSTS`, PPA and OEM detection, the archive key name |
| `aptsources.map_suite` | Ubuntu codename mapping |
| `rebuild.DISTRO_SOURCE_FILES` | `ubuntu.sources`, `ubuntu-esm-*.sources` |
| `recipe.UBUNTU_KEYS`, `recipe.SNAP_DEPENDENCY`, `recipe._snaps`, `helper.op_snap_install` | Ubuntu keyrings, snaps |
| `helper.op_netplan_import`, `rebuild.ServicesStep` (`/etc/netplan/90-NM-*`) | Netplan, used by NetworkManager on Ubuntu 23.10 and newer |
| `deps.install_veracrypt`, `deps.choose_veracrypt_asset` | refuses unless `ID=ubuntu`; picks `veracrypt-*-Ubuntu-*.deb` |
| `cli.app_problem`, `gui/pages/drives.py` texts | "needs Ubuntu 24.04", "Built into Ubuntu" |

### 1.6 What happens today on other systems

| System | Result with 0.2.1 |
|---|---|
| Debian, Mint | Mostly works. Ubuntu's own sources are recognised only on Ubuntu, so Debian's own repository could be offered as "third-party" in a rebuild. Snaps are missing on Mint. |
| Fedora, openSUSE, Arch | `deucalion deps` crashes. Backup, restore and drives work. The recipe is nearly empty, and the `/etc` scan treats every file as unowned (they are hidden or unselected in the rebuild, so nothing is damaged). `rebuild` runs `apt-get`, which fails with code 127. |
| macOS | Imports work. `register` and `setup-drive` crash (`findmnt`). Backups could run on a registered folder, but with the Unicode risk of §4.4. |
| Windows | Nothing runs: `import grp` fails at start. |

## 2. The platform layer { #platform-layer }

The goal is that all platform-specific calls live in one place, with today's Linux code moved there
unchanged (roadmap 0.3, steps 1–3).

```text
deucalion/platform/
├── __init__.py     current() → the Platform for this computer; Distro detection
├── base.py         the interfaces (classes with the methods below)
├── linux.py        today's code, moved verbatim (0.3)
├── distro.py       per-family backends: deps, packages, sources, /etc scanner (0.3 – 0.4)
├── macos.py        (0.6)
└── windows.py      (0.8 – 0.9)
```

| Interface | Methods | Linux (from) | macOS | Windows |
|---|---|---|---|---|
| `SystemInfo` | `os_info()`, `distro()`, `user()`, `is_admin()`, `hostname()`, `machine()` | `util.os_release`, `pwd`, `os.geteuid`, `os.uname`, `/sys/class/dmi` | `sw_vers`, `sysctl hw.model` | `platform`, `ctypes` |
| `Paths` | `config_dir()`, `state_dir()`, `default_excludes()` | `config.py` (XDG) | `~/Library/Application Support/Deucalion` | `%APPDATA%`, `%LOCALAPPDATA%` |
| `Mounts` | `mount_info(path)`, `fs_type(path)`, `is_posix_fs(path)`, `mount_points()`, `candidate_roots()`, `removable_roots()`, `is_on_system_disk(path)`, `is_encrypted(path)` | `util.py`, `target.candidate_roots` | `diskutil info -plist`, `/Volumes` | `ctypes` volume APIs |
| `Drives` | `list_drives()`, `setup(request)`, `open(access)`, `close(access)` | `drives.py`, `drivesetup.py`, `udisks.py` | `diskutil`, `newfs_exfat` | PowerShell storage cmdlets (through the helper) |
| `Admin` | `start_helper()` → a connection with `call(op, **args)` | `privileged.Privileged` (pkexec, sudo) | `sudo` | UAC + named pipe |
| `FileMeta` | `capture(stat, path)`, `apply(path, entry)`, `change_time(stat)`, `lock(path)`, `sync()`, `free_space(path)`, `cluster(path)` | `os.chmod`/`chown`, `fcntl.flock`, `os.sync`, `os.statvfs` | + extended attributes, `st_flags` | attributes, `msvcrt.locking`, NTFS change time |
| `NameRules` | `drive_policy()`, `destination_fold(path)` | `names.NamePolicy` | + Unicode normalization | + Windows name rules |
| `Recipe` and rebuild backends | `collectors()`, `steps(mode)` | `recipe.py`, `rebuild.py` | Brewfile (0.7) | later |

Rules for the move:

- **Old names stay importable** (`util.mount_info`, `util.run`, `drivesetup._REMOVABLE_MOUNTS`, …) as thin
  re-exports, because tests patch them.
- **`helper.py` stays self-contained** and Linux-only (it runs as root with `python3 -I`). macOS and
  Windows get their own helpers with the same JSON protocol and the same "fixed list of checked
  operations" design.
- **Characterization tests first:** a fake `run` that records commands, fake system files, and the
  command inventory test (roadmap 0.3 step 1). The refactor is correct when these are unchanged.
- The `pwd`, `grp` and `fcntl` imports become lazy (inside the functions that need them).

## 3. Linux distributions

### 3.1 Families and detection

The family comes from `/etc/os-release`: `ID`, then `ID_LIKE`.

| Family | Distributions | `ID` / `ID_LIKE` |
|---|---|---|
| `debian` | Ubuntu, Debian, Linux Mint | `ubuntu`; `debian`; `linuxmint` with `ID_LIKE="ubuntu debian"` and `UBUNTU_CODENAME` |
| `fedora` | Fedora | `fedora` |
| `suse` | openSUSE Tumbleweed, Leap | `opensuse-tumbleweed`, `opensuse-leap`, `ID_LIKE` contains `suse` |
| `arch` | Arch | `arch` |

### 3.2 Backends per family { #distro-backends }

| | Debian family | Fedora | openSUSE | Arch |
|---|---|---|---|---|
| Packages for Deucalion | `python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 udisks2 cryptsetup exfatprogs pkexec dconf-cli gnupg` | `python3-gobject gtk4 libadwaita udisks2 cryptsetup exfatprogs polkit dconf gnupg2` | `python3-gobject typelib-1_0-Gtk-4_0 typelib-1_0-Adw-1 udisks2 cryptsetup exfatprogs polkit dconf gpg2` | `python-gobject gtk4 libadwaita udisks2 cryptsetup exfatprogs polkit dconf gnupg` |
| Installed by you | `apt-mark showmanual` | `dnf repoquery --userinstalled` | `zypper packages --userinstalled` | `pacman -Qqe` (AUR: `pacman -Qqm`) |
| Install, never removing | `apt-get install -y --no-remove` | `dnf install -y` (never `--allowerasing`) | `zypper --non-interactive install` | `pacman -Syu` first (Arch doesn't support partial upgrades), then `pacman -S --needed --noconfirm` |
| Software sources | `/etc/apt/sources.list(.d)`, keys in `/etc/apt/keyrings` | `/etc/yum.repos.d/*.repo`, `gpgkey=`; COPR; RPM Fusion release packages | `/etc/zypp/repos.d/*.repo` | extra sections in `/etc/pacman.conf` |
| New release mapping | codenames (`noble` → `resolute`, `bookworm` → `trixie`; Mint: `UBUNTU_CODENAME` for third-party) | `$releasever` (automatic) | Open Build Service URLs (`openSUSE_Leap_16.0`, …) | rolling, none |
| `/etc` changes | dpkg `status` conffiles + `info/*.md5sums` | `rpm -qa --qf '[%{FILENAMES}\t%{FILEDIGESTS}\t%{FILEFLAGS:fflags}\n]'` | same as Fedora | `/var/lib/pacman/local/*/files` (`%FILES%`, `%BACKUP%` with checksums) |
| Install time | `/var/log/installer` | `/var/log/anaconda` | `/var/log/YaST2` | first line of `/var/log/pacman.log` |
| Root crontab | `/var/spool/cron/crontabs/root` | `/var/spool/cron/root` | `/var/spool/cron/tabs/root` | `/var/spool/cron/root` |
| Administrator group | `sudo` | `wheel` | `wheel` | `wheel` |
| Desktop drive mounts | `/media/$USER` | `/run/media/$USER` | `/run/media/$USER` | `/run/media/$USER` |
| VeraCrypt | official `.deb` (Ubuntu or Debian build) | official `.rpm` + `.sig` | official `.rpm` + `.sig` | Arch's `veracrypt` package |
| SELinux | no (AppArmor) | yes, enforcing | yes on new installs | no |

**To verify** in each distribution's VM: the package names, the exact package queries (dnf 5,
zypper), the openSUSE crontab and install-time paths, what each package manager does on a conflict
with these options, and VeraCrypt's current asset names.

Other notes:

- **openSUSE's administrator password is root's password by default** (`sudo` and polkit ask for the
  root password, not yours). The documentation and the password prompts must say so.
- **Linux Mint blocks `snapd`** with `/etc/apt/preferences.d/nosnap.pref`. The rebuild then lists the
  snaps as "not available here". It never removes the block.
- **SELinux:** a file written into `/etc` must get the right label. The helper runs `restorecon` after
  `put_etc_file` where SELinux is enabled (roadmap 0.4).
- **Immutable systems** (Fedora Silverblue, openSUSE Aeon) have a read-only `/usr`. The polkit policy in
  `/usr/share/polkit-1/actions` can't be installed, and packages go through `rpm-ostree` or
  `transactional-update`. They are out of scope.

### 3.3 Rebuild modes

| Step | Same family | Another family (portable part) |
|---|---|---|
| Check | ✓ | ✓, and says which parts are not carried across |
| Software sources | ✓ | – never |
| Packages | ✓ (apt in 0.3; dnf, zypper, pacman in 0.4) | old list for reference; same-name suggestions unselected (0.4); **Flatpaks installed** |
| Home, Paths, Desktop | ✓ | ✓ |
| System settings (`/etc`) | ✓ | – never |
| Groups | ✓ | ✓ with `sudo` ↔ `wheel` |
| Crontab, your own services | ✓ | ✓ |
| System services | ✓ | shown unselected, only for units that exist here |
| Network connections | ✓ | ✓ NetworkManager keyfiles. From Ubuntu 23.10 and newer, the generated keyfiles saved from 0.3 on (`network/generated-connections/`) |

Why packages don't cross families: names differ (`build-essential` vs a dnf group, `-dev` vs
`-devel`, split or merged packages). A guessed mapping installs the wrong things or misses some, and
nobody can review a mapping table of thousands of names. Flatpaks are the same everywhere, so they
are installed.

## 4. macOS

### 4.1 Drives

- **Listing:** `diskutil list -plist` and `diskutil info -plist <disk>` (`Internal`, `Removable`,
  `Ejectable`, `BusProtocol`). Mount points are under `/Volumes`.
- **The system disk:** APFS shows "synthesized" disks (for example `disk3`), while the physical disk is
  `disk0`. The physical disk comes from the APFS container's physical stores (`diskutil apfs list
  -plist`). As on Linux, if it can't be found, no drive may be changed.
- **Formatting:** `diskutil eraseDisk ExFAT <NAME> GPT <disk>`. `diskutil` can't choose the cluster
  size, so the partition is then formatted again with `newfs_exfat` with 8 KB clusters. **To verify:**
  `newfs_exfat`'s cluster option, and whether erasing an external disk needs `sudo`.
- **CI:** `hdiutil create -size 2g -fs ExFAT -volname TEST test.dmg` and `hdiutil attach` give a real
  exFAT volume from Apple's driver. `hdiutil attach -nomount` gives a `/dev/diskN` that `diskutil` can
  erase. Drive setup can be tested this way.

### 4.2 Administrator access

- The old Authorization Services call is deprecated. The modern way (`SMAppService`, a privileged
  helper daemon) needs a signed app bundle.
- **Plan:** `sudo` from the command line, with the same JSON-over-pipe helper design and its own fixed
  list of operations. A future app could use `osascript … with administrator privileges`, which has no
  pipe, so the helper would then need a socket.
- Much less needs root on macOS than on Linux. Homebrew must **not** run as root. `/etc/hosts` and
  `/Library/LaunchDaemons` do need it.

### 4.3 Python

macOS has no usable Python out of the box. `/usr/bin/python3` is a stub that installs the Command Line
Tools, whose Python has long been 3.9, below Deucalion's 3.10 minimum (**to verify** on current macOS).
Users install Python from python.org or Homebrew. The tool copy on the drive runs with
`python3 Deucalion-Tool/bin/deucalion`.

### 4.4 How backups differ

- **Unicode spellings.** APFS treats the two spellings of `é` (NFC and NFD) as the same name. Linux
  allows both side by side. `names.fold_exfat` is only `.upper()`.
    - **On the drive:** if macOS's exFAT driver lists names in a different form than they were
      written, `backup.Scanner._walk` would see real backed-up files as unknown leftovers and **move
      them to `_removed/`**. Nothing is lost, but the backup is damaged until the next run copies
      them again. The fold must also normalize, and this must be proved on a real exFAT image in CI
      before backups are enabled on macOS.
    - **On restore:** Linux twins (by case or by Unicode form) collide on a Mac. Today
      `Restorer._decide` would mark the second one "overwrite" and move the first one into the undo
      folder. A collision pre-check is needed (it helps Windows too).
- **Extended attributes and resource forks** (Finder tags, quarantine flags, old resource forks): the
  copy loop copies only file content. Python's `os.getxattr` family is Linux-only, so macOS needs
  `ctypes` calls to libc. Store small values in a new manifest table, and report big ones.
- **Files kept only in iCloud** ("Optimize Mac Storage"): reading one downloads it. Skip files with the
  `SF_DATALESS` flag (in `st_flags`) and warn.
- **Full Disk Access:** without it, `~/Library/Mail`, `Messages`, `Safari` and the Photos library
  can't be read. The scanner already skips unreadable folders and keeps what is backed up, but a first
  backup must explain this clearly.
- **`~/Library` exclusions:** `Caches/`, `Logs/`, `Containers/*/Data/Library/Caches/`,
  `Application Support/*/Cache*`, and others, kept as a list per platform.
- **`.DS_Store` and `._*` files** written by Finder on the drive are already ignored
  (`backup.OS_CLUTTER`).

### 4.5 Recipe and rebuild

| Recipe item | How |
|---|---|
| Homebrew formulae, casks, taps, Mac App Store apps, VS Code extensions | `brew bundle dump` → `packages/Brewfile` (`mas` must be installed for App Store apps) |
| Apps installed by hand | `/Applications` (name, bundle ID, version), for reference |
| Launch agents | `~/Library/LaunchAgents` (already in the home folder) |
| Scheduled tasks | `crontab -l` |
| `/etc` | `/etc/hosts` only (macOS has no package database to compare with) |
| Wi-Fi | not saved: passwords are in the System keychain and can't be exported without a prompt per item |

A Mac-to-Mac move is already well served by Apple's Migration Assistant and Time Machine. Deucalion's
value on a Mac is a plain-file backup readable on every system, and a clean-install rebuild from the
Brewfile.

### 4.6 Encryption

- LUKS: not available on macOS.
- VeraCrypt needs a FUSE layer:
    - **macFUSE** needs a kernel extension, which on Apple silicon means lowering security in Recovery
      mode;
    - **FUSE-T** needs no kernel extension; VeraCrypt has supported it since 1.26, and Homebrew has a
      `veracrypt-fuse-t` cask that conflicts with the standard `veracrypt` cask.
- **Plan:** in 0.6, Deucalion uses volumes that the user unlocked in VeraCrypt's app. In 0.7, a CI
  spike decides whether `deucalion open` can drive VeraCrypt with FUSE-T (password through `--stdin`).

### 4.7 What GitHub's macOS runners can and can't prove

| Can | Can't |
|---|---|
| The whole suite on Apple silicon (`macos-15`, `macos-26`) | USB drives |
| Apple's exFAT driver, through disk images | Kernel extensions (macFUSE) |
| Case-sensitive and case-insensitive APFS images | Real *Full Disk Access* prompts on a user's machine |
| `diskutil` on attached images | iCloud accounts and dataless files |
| Homebrew and `brew bundle` on a fresh machine (each job is a new runner) | The look of a future app |
| A backup made on Linux, restored on macOS (artifacts between jobs) | |

## 5. Windows

### 5.1 Making the code import and run

- Lazy `pwd`, `grp` and `fcntl` imports (0.3).
- Replacements in the platform layer:
    - `os.geteuid`: `ctypes.windll.shell32.IsUserAnAdmin`;
    - `os.statvfs`: `shutil.disk_usage`, and `GetDiskFreeSpaceW` for the cluster size;
    - `os.sync`: `FlushFileBuffers` on the files written, or nothing;
    - `os.uname`: the `platform` module;
    - the lock: `msvcrt.locking`.
- A CI job imports every module except `helper`, `udisks` and `gui` on Windows (0.8, step 1).

### 5.2 Restoring onto Windows: the traps

These are real code paths in `restore.py` today, and each one needs a fix and a test before Windows
restores are allowed:

| Linux name or situation | What would happen | Fix |
|---|---|---|
| `a:b` | `dest / "a:b"` becomes a path relative to drive `A:`, **outside the restore folder**; on NTFS, `a:b` also means "stream `b` of file `a`" | destination names through a Windows name policy; every destination checked to be inside the chosen folder |
| `x\y` | becomes a sub-folder | name policy |
| `name.` or `name ` | Windows drops the trailing dot or space | name policy (look-alike characters, as on exFAT) |
| `CON`, `aux.txt` | reserved device names | name policy (`names.exfat_safe` already does this) |
| `Notes` and `notes` | the second replaces the first (moved to the undo folder) | collision pre-check |
| Paths over 260 characters | fail | `\\?\` prefix |
| `move_aside` | `undo_root / str(path).lstrip("/")` gives the original path | build the undo path from the drive letter and the rest |
| Symbolic links | need Developer Mode or administrator rights | create when allowed, otherwise list them |
| Permissions and owners | meaningless on NTFS | not applied; files inherit the folder's permissions |

### 5.3 How backups differ (0.9)

- **Locked files:** `NTUSER.DAT` is always locked, and open mailboxes and browser profiles often are.
  A consistent copy needs a Volume Shadow Copy, which needs administrator rights.
- **Change time:** `st_ctime` is the creation time. Use `GetFileInformationByHandleEx`
  (`FILE_BASIC_INFO.ChangeTime`) through `ctypes`.
- **Permissions (ACLs):** not saved. A home folder's files inherit the profile's permissions, and
  restoring explicit ACLs from another machine (other user IDs) would be wrong.
- **Placeholders:** OneDrive Files On-Demand (`FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS`,
  `FILE_ATTRIBUTE_OFFLINE`) are downloaded when read. Skip them and warn.
- **Junctions:** `os.lstat` treats them as links (Python 3.8 and newer), so they are recorded as links.
- **The registry:** not portable (user IDs, paths, program versions); never restored.

### 5.4 Administrator access

A UAC-elevated process (`ShellExecuteExW` with "runas") can't share stdin and stdout with the program
that started it. The helper talks over a named pipe whose access list allows only the user's SID. It
uses the same JSON protocol and the same "fixed list of checked operations" design as on Linux, and
needs its own security review.

### 5.5 Drives and encryption

- **Drives:**
    - formatting through PowerShell (`Get-Disk`, `Clear-Disk`, `Initialize-Disk`, `New-Partition`,
      `Format-Volume -FileSystem exFAT -AllocationUnitSize 8192`), run by the helper;
    - the system disk comes from `Get-Disk`'s `IsBoot` and `IsSystem`;
    - read-only work uses `ctypes` (`GetLogicalDrives`, `GetVolumeInformationW`).
- **VeraCrypt:**
    - On Windows its command line is `VeraCrypt.exe /v … /l X /p <password> /q /s` and
      `"VeraCrypt Format.exe" /create …`.
    - As far as is known, the password goes on the command line, where other programs can read it.
      **To verify.**
    - Plan: users unlock drives with VeraCrypt's own app, and Deucalion never handles the password on
      Windows.
- **BitLocker To Go** would be a Windows-native encrypted layout that Linux can open
  (`cryptsetup --type bitlk`). It is listed as "later".

### 5.6 Python

Windows has no Python by default (`python` opens the Microsoft Store). Users install it from
python.org or with `winget install Python.Python.3.13`. The official "embeddable" zip (about
10–15 MB, no installer) could be carried on the drive in `Deucalion-Tool`; this is decided in 0.8.

## 6. Testing infrastructure

### 6.1 Virtual machines for other distributions { #vm-images }

`docs/tools/vm.py` already does the hard parts:
- QEMU/KVM, cloud-init (NoCloud over HTTP, user `alex`);
- SSH on a forwarded port;
- USB disk images hot-plugged over QMP (`usb-bot` + `scsi-hd` on `qemu-xhci`).

Two things are Ubuntu-specific:
- the image URL and its verification (`SHA256SUMS.gpg` with the `ubuntu-cloudimage` keyring);
- `groups: [sudo, adm, plugdev]` in the user data. Drop the line: the `sudo:` rule already gives
  access.

Current images (checked 2026-10-12):

| Distribution | Image | Size | Verification |
|---|---|---|---|
| Ubuntu 24.04, 26.04 | already cached in `~/.cache/deucalion-docs` | — | signed `SHA256SUMS` (unchanged) |
| Fedora 44 | `Fedora-Cloud-Base-Generic-44-1.7.x86_64.qcow2` | not listed (about 0.5 GB) | signed `Fedora-Cloud-44-1.7-x86_64-CHECKSUM`, checked with Fedora's OpenPGP keys (`fedora.gpg`, fingerprint pinned in `vm.py`) |
| Debian 13 | `debian-13-genericcloud-amd64.qcow2` | 326 MB | `SHA512SUMS`. **No signature file** in `cloud.debian.org/images/cloud/trixie/latest/`: HTTPS only, or pin the digest in `vm.py` when the image is first approved |
| openSUSE Tumbleweed | `openSUSE-Tumbleweed-Minimal-VM.x86_64-Cloud.qcow2` | 303 MB | `.sha256` + `.sha256.asc` (openSUSE's key, pinned) |
| Arch | `Arch-Linux-x86_64-cloudimg.qcow2` | 578 MB | `.SHA256` + `.sig` (the image builders' keys, pinned) |
| Linux Mint 22 | no cloud image; ISO about 3 GB | ~3 GB | signed `sha256sum.txt`; installed once by hand, kept as a base disk |

In the VMs, administrator steps run through `Privileged`'s existing `sudo -n` path (no desktop, and the
user has passwordless `sudo`). UDisks tests need `udisks2` installed in the VM.

**This machine (checked 2026-10-12):**
- 16 cores, 30 GB RAM (about 13 GB free at the time, with most of the swap in use);
- 95 GB free on `/`;
- KVM, QEMU 8.2.2, and OVMF 2024.02 with Secure Boot and Microsoft key variables (`OVMF_CODE_4M.secboot.fd`,
  `OVMF_VARS_4M.ms.fd`);
- `swtpm` is not installed.

A Linux VM uses 2–4 GB of RAM, so about two at a time fit.

### 6.2 Containers in GitHub Actions

Containers (`debian:13`, `fedora:44`, `opensuse/tumbleweed`, `archlinux:latest`) run the unit tests with
each distribution's own Python and PyGObject. They can't mount filesystems, so the exFAT and loop-device
tests stay on the Ubuntu runner, and tests that need `findmnt`, `lsblk` or UDisks skip themselves.

### 6.3 Windows 11 under QEMU/KVM { #windows-vm }

| Item | Cost |
|---|---|
| Windows 11 Enterprise evaluation ISO (90 days, no product key) | about 6 GB (exact size read from Microsoft's page before asking) |
| Disk after installation and updates | about 30–40 GB (64 GB virtual qcow2) |
| RAM, CPUs | 6–8 GB, 4 vCPUs |
| TPM | `swtpm` and `swtpm-tools` from apt (administrator password, announced as one batch) |
| Firmware | `OVMF_CODE_4M.secboot.fd` + `OVMF_VARS_4M.ms.fd` (installed) |
| Drivers | none with emulated SATA and e1000; optionally the virtio-win ISO (~700 MB) for speed |
| Unattended setup | `autounattend.xml` on a small second disk: local account, OpenSSH server for scripted access |
| USB drives | the same QMP hot-plug as the Linux VMs |

It fits in the 95 GB free, but it is the biggest cost, so it is created only for 0.8 and 0.9.

The GitHub runner `windows-2025` (Windows Server, free for public repositories, administrator rights)
covers the engine tests, exFAT virtual disks made with `diskpart`, and shadow copies.

### 6.4 Proposed CI matrix { #ci-matrix }

`.github/workflows/tests.yml` is extended step by step: the `distros` job in 0.3, `macos` in 0.6,
`windows` in 0.8. Each change is shown to the owner before it is pushed.

```yaml
jobs:
  test:          # unchanged: ubuntu-22.04, ubuntu-24.04
  exfat:         # unchanged: the suite on a real exFAT volume

  distros:       # 0.3
    name: ${{ matrix.image }}
    runs-on: ubuntu-24.04
    container: ${{ matrix.image }}
    strategy:
      fail-fast: false
      matrix:
        image: ["debian:13", "fedora:44", "opensuse/tumbleweed", "archlinux:latest"]
    steps:
      - name: Install what Deucalion needs
        run: |
          case "${{ matrix.image }}" in
            debian*)   apt-get update -q && apt-get install -y -q git python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 gnupg dconf-cli ;;
            fedora*)   dnf install -y git python3-gobject gtk4 libadwaita gnupg2 dconf ;;
            opensuse*) zypper --non-interactive install git python3-gobject typelib-1_0-Gtk-4_0 typelib-1_0-Adw-1 gpg2 dconf ;;
            arch*)     pacman -Syu --noconfirm git python-gobject gtk4 libadwaita gnupg dconf ;;
          esac
      - uses: actions/checkout@v7
      - run: python3 -m unittest discover -s tests -v

  macos:         # 0.6
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        os: [macos-15, macos-26]
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
        with: { python-version: "3.12" }
      - run: python3 -m unittest discover -s tests -v
      - name: The suite again on Apple's exFAT driver
        run: |
          hdiutil create -size 2g -fs ExFAT -volname TEST "$RUNNER_TEMP/exfat.dmg"
          hdiutil attach "$RUNNER_TEMP/exfat.dmg"
          DEUCALION_TEST_EXFAT=/Volumes/TEST python3 -m unittest discover -s tests -v

  windows:       # 0.8
    runs-on: windows-2025
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
        with: { python-version: "3.12" }
      - run: python -m unittest discover -s tests -v
```

Cross-platform checks pass a backup between jobs as a build artifact: made on Ubuntu, then restored on
macOS (0.6) and Windows (0.8), or backed up on one macOS runner and rebuilt on another (0.7).

### 6.5 macOS testing options

Decided: GitHub's runners only (roadmap §3). The other options, for the record:

| Option | Cost (checked 2026-10-12) | Notes |
|---|---|---|
| GitHub Actions macOS runners | free for public repositories | `macos-15`, `macos-26` (Apple silicon, 3 CPUs, 7 GB); also `macos-15-intel`, `macos-26-intel`. No USB, no kernel extensions. |
| Scaleway Mac mini M4 | €0.22/hour + tax, **mandatory first 24 hours** (Apple's license), or €149/month with a monthly commitment | Screen Sharing; disk images instead of USB. |
| AWS EC2 Mac | **24-hour minimum** for the Dedicated Host; price not confirmed on AWS's page (a competitor quotes $1.23/hour for M4) | |
| MacinCloud | about $1/hour pay-as-you-go (from a competitor's page; not confirmed) | |
| A real Mac | — | The only way to test USB drives and real *Full Disk Access* prompts. |

Apple's license allows macOS virtual machines only on Apple hardware, so no macOS VM runs on the
Linux test machine.

## 7. Packaging and distribution { #packaging }

| Platform | Now and planned | Not planned, and why |
|---|---|---|
| Linux | Run from the folder (and the copy on every drive); `install.sh` for any distribution (0.3); optional Open Build Service packages (`.deb`, `.rpm`, Arch) and an AUR package (0.4, with approval) | **Flatpak:** the root helper, the recipe and the rebuild need the real system (host `apt`/`dnf`/`dconf`/`systemctl`, `pkexec`, all of `/etc` and `$HOME`). Inside Flatpak all of that goes through `flatpak-spawn --host`, which is a full sandbox escape, and Flathub's reviewers push back on it. **Snap:** the same, with classic confinement needing approval. |
| macOS | Git clone or zip, run with `python3`; optional Homebrew tap (0.6, with approval) | A signed and notarized `.app` needs the Apple Developer Program ($99 a year) and is only useful with an app. Later. |
| Windows | Zip or Git clone, `deucalion.cmd` starter (0.8); maybe the embeddable Python on the drive | Code signing: Azure Artifact Signing (about $9.99/month) is, according to DevClass, open only to organizations in the EU and UK (individuals only in the US and Canada); other options are a yearly certificate, or a free open-source signing service such as SignPath (**to verify**). Decided in 0.9. |

## 8. Facts checked on 2026-10-12 { #checked-facts }

Prices, image names and runner labels change. Check them again before relying on them.

| Fact | Source |
|---|---|
| EC2 Mac Dedicated Hosts: 24-hour minimum allocation | [AWS EC2 Mac FAQ](https://aws.amazon.com/ec2/instance-types/mac/faqs/) |
| EC2 mac-m4 at $1.23/hour (third-party claim) | [Green Mini comparison](https://www.greenmini.nl/compare/aws-ec2-mac-alternative/) |
| Scaleway Mac mini prices (M4 from €0.22/hour or €149/month) | [Scaleway Apple silicon pricing](https://scaleway.com/en/pricing/apple-silicon) |
| Scaleway: mandatory first 24 hours; monthly commitment option | [Scaleway: manage the commitment plan](https://www.scaleway.com/en/docs/apple-silicon/how-to/manage-commitment-plan/) |
| MacinCloud about $1/hour (third-party claim) | [Green Mini comparison](https://www.greenmini.nl/compare/macincloud-alternative/) |
| GitHub-hosted runner labels; free on public repositories | [GitHub-hosted runners](https://docs.github.com/en/actions/reference/runners/github-hosted-runners), [macOS 26 runners](https://github.blog/changelog/2026-02-26-macos-26-is-now-generally-available-for-github-hosted-runners/) |
| VeraCrypt with FUSE-T on macOS | [Homebrew `veracrypt-fuse-t`](https://formulae.brew.sh/cask/veracrypt-fuse-t), [VeraCrypt macOS source log](https://veracrypt.fr/code/VeraCrypt/log/src/Setup/MacOSX?showmsg=1) |
| Azure Artifact Signing eligibility and price | [DevClass, January 2026](https://devclass.com/2026/01/14/code-signing-windows-apps-may-be-easier-and-more-secure-with-new-azure-artifact-service/), [Azure pricing](https://azure.microsoft.com/pricing/details/artifact-signing/) |
| Windows 11 Enterprise evaluation (90 days) | [Microsoft Evaluation Center](https://www.microsoft.com/en-us/evalcenter/download-windows-11-enterprise) |
| `st_ctime` on Windows deprecated; `st_birthtime` | [Python discussion](https://discuss.python.org/t/st-birthtime-not-available/104350) |
| Cloud images and their checksum files | [Fedora Cloud](https://fedoraproject.org/cloud/download), [Debian 13](https://cloud.debian.org/images/cloud/trixie/latest/), [openSUSE Tumbleweed](https://download.opensuse.org/tumbleweed/appliances/), [Arch](https://geo.mirror.pkgbuild.com/images/latest/) |
