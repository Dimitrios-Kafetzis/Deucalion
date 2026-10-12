# Files on your computer

What Deucalion creates on your computer (not on the backup drive).

## Your settings: `~/.config/deucalion/`

| File | What it is |
|---|---|
| `config.json` | Your [configuration](configuration.md): backup drives, exclusions, extra folders, profiles, options. |

Kept by `./install.sh --uninstall`. (Moved by `XDG_CONFIG_HOME` or `DEUCALION_CONFIG_DIR`.)

## Working files: `~/.local/state/deucalion/`

| File or folder | What it is |
|---|---|
| `system/` | The [system recipe](../concepts/system-recipe.md), generated before each full backup, then backed up to the drive's `system/`. |
| `logs/` | A copy of every backup, restore and rebuild log (`<date>_<time>-backup.log`…). |
| `rebuild.json` | Which [rebuild](../concepts/rebuild.md) steps are done, for which backup drive. |
| `open-drives.json` | VeraCrypt drives Deucalion unlocked, so it can lock them again. |
| `tmp/` | The backup plan while a backup runs (deleted afterwards). |

This folder is never backed up. (Moved by `XDG_STATE_HOME` or `DEUCALION_STATE_DIR`.)

## The undo folder: `~/Deucalion-before-restore/`

Everything a restore or a rebuild replaced in your home folder, in one dated folder per run (see
[Undo a restore](../tutorials/undo-restore.md)):

| Folder | Made by |
|---|---|
| `<date>_<time>/home/<you>/…` | A restore (also the rebuild's home step). |
| `<date>_<time>-paths/…` | The rebuild's paths step. |
| `<date>_<time>-desktop/dconf-before.ini` | The rebuild's desktop step (your desktop settings before). |
| `<date>_<time>-crontab/crontab-before.txt` | The rebuild's services step (your crontab before). |

Deucalion never deletes it, and never backs it up. Delete old folders yourself when you no longer need
them.

## System files replaced by a rebuild: `/var/backups/deucalion/`

`/etc` files and the administrator's crontab that a [rebuild](../concepts/rebuild.md) replaced, in one
dated folder per run, with their full path (for example
`/var/backups/deucalion/<date>_<time>/etc/hosts`). Owned by root; read them with `sudo`.

## Added by a rebuild

- Software sources: new files in `/etc/apt/sources.list.d/` (named as on the old computer), and their
  keys in `/etc/apt/keyrings/` or `/etc/apt/trusted.gpg.d/`. Existing files are never replaced.
- Network connections: in `/etc/NetworkManager/system-connections/` or `/etc/netplan/90-NM-….yaml`.

## The program (when installed with `./install.sh`)

| Where | What |
|---|---|
| `~/.local/share/deucalion/` | The program. |
| `~/.local/bin/deucalion` | The `deucalion` command (a link to the program). |
| `~/.local/share/applications/io.github.DimitriosKafetzis.Deucalion.desktop` | The app menu entry. |
| `~/.local/share/icons/hicolor/…/io.github.DimitriosKafetzis.Deucalion*.svg` | The app's icons. |
| `/usr/local/libexec/deucalion/helper.py` | The [administrator helper](../concepts/administrator-access.md) (with `--system-helper`), owned by root. |
| `/usr/share/polkit-1/actions/io.github.DimitriosKafetzis.Deucalion.policy` | Its password prompt (with `--system-helper`). |

`./install.sh --uninstall` removes all of these, and keeps your settings and backups.

## Temporary

During a full backup with protected settings, the administrator helper collects them in a new folder
`/tmp/deucalion-admin-…` that only it can reach, hands it over, and Deucalion deletes it right away.
VeraCrypt installs download into `/tmp/deucalion-veracrypt-…`, deleted afterwards.
