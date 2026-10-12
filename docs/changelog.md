# Changelog

## Unreleased

Found while following this documentation step by step on Ubuntu 24.04 and 26.04:

- **The app's Unlock dialog works again.** It failed to open, so an encrypted drive couldn't be unlocked
  from the app (only with `deucalion open`).
- **Drive names with spaces** (such as "Alex Backup") work everywhere: `deucalion open` without
  arguments now finds an encrypted backup on such a drive (the first step of a rebuild), `deucalion close`
  unmounts it, and the copy of Deucalion on its normal part is refreshed after backups.
- **`deucalion register <drive> --default`** keeps how to unlock an encrypted drive (it was lost, so
  Deucalion then treated the drive as unencrypted).
- **Rebuild:** PPAs added on Ubuntu 24.04 and newer keep their signing key. Before, the restored PPA was
  refused by apt ("… is not signed").
- The copy of Deucalion on backup drives (`Deucalion-Tool`) and `./install.sh` no longer copy the `docs/`
  folder, which now holds this website and its screenshots.
- New documentation website, with tutorials for the app and the command line; the app's screenshot
  mode was extended for it.

## 0.2.0 (10 October 2026)

From a third independent review:

- Ubuntu mirrors are recognised only by the archive's layout (a path ending in `/ubuntu` with
  `-updates`/`-security` suites, or the archive key); Wine, ROS, MongoDB, Microsoft and similar
  repositories are offered again during a rebuild.
- Restored apt sources keep their original names and never overwrite anything; the system's own source
  files are refused.
- The administrator helper ignores Ctrl+C, so apt/dpkg and `/etc` writes are never cut off; its
  temporary `/etc` file is removed on failure.
- No endless loops when `_removed` or the undo folder is a file or a broken link.
- VeraCrypt installs require a good signature (GOODSIG), reject revoked or expired keys, and require a
  minimum version.
- Restoring over a folder that became a link restores its files.
- macOS/Windows clutter on the drive is left alone; leftovers are logged by path.
- Files to be replaced are marked for re-copy in one transaction (fast on USB drives).
- `install.sh` refreshes an outdated system helper automatically.

From a real-data test (about 700,000 files, 49 GB):

- exFAT drives are formatted with 8 KB clusters: with the 128 KB default, 36 GB of real files filled an
  80 GB drive.
- The space check counts whole clusters per file and new folders.
- A drive that fills up while writing the manifest, the run history or `backup.json` ends with the
  normal "drive is full" message; the manifest stays intact.

Documentation: how Deucalion protects your data, and how it was tested.

## 0.1.0

The first version, built in five milestones and a safety campaign.

**Backup, restore, verify (command line).** A scan-plan-copy engine with a SQLite manifest on the drive
(permissions, owners, links, original names, checksums); exFAT-safe names; a single mirror where changed
and deleted files move to `_removed/`; partial backups, profiles, exclusions and extra folders; restores
with a preview and an undo folder, also to a new user name; `verify` (sizes or checksums); low memory
for millions of files; safety checks (registered drives only, never the system disk, another machine's
backup, space, one task at a time, safe Ctrl+C).

**System recipe and rebuild (command line).** Every full backup saves the system recipe: apt packages
(also from downloaded `.deb` files), repositories and keys, snaps, flatpaks, desktop settings, GNOME
extensions, crontabs, services, groups, software in `/opt` and `/usr/local`, changed `/etc` files, network
connections. `deucalion rebuild` replays it in eight resumable steps with `--dry-run` and `--step`. An
administrator helper with a fixed, checked list of operations.

**Drive setup and encryption.** `deucalion setup-drive`: whole-drive encryption, encrypted part + normal
part, encrypted folder, plain exFAT, or as it is; VeraCrypt or LUKS. Drives are prepared through UDisks
without administrator rights where possible. `deucalion open` and `close`. A READ-ME and a copy of
Deucalion on the drive's normal part.

**The app (GTK 4 + libadwaita).** Overview, Back Up, Restore, Rebuild, Drives (with a setup wizard),
Removed Files and Settings; adapts to narrow windows.

**Installer.** `install.sh` installs for the current user, with `--system-helper` (a root-owned helper
and a clear password prompt) and `--uninstall`; `deucalion deps` checks and installs what is needed,
including a signature-checked VeraCrypt.

**Safety campaign.** Detection of edits that keep size and date; restores that rename (never copy and
delete) and put the original back on failure; rebuilds that keep everything they replace, never remove
packages, never change Ubuntu's own sources, and are repeatable; a randomized torture test; manual
administrator and VeraCrypt checks; a full rebuild of a fresh Ubuntu 26.04 VM from a 24.04 backup.
