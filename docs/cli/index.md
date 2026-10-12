# Using the command line

Everything the app does can also be done by typing commands in a terminal. Commands start with
`deucalion`, followed by what you want to do:

```bash
deucalion backup
deucalion restore ~/Documents/report.pdf
```

New to the terminal? See [Opening a terminal](../getting-started/index.md#opening-a-terminal-only-needed-for-the-command-line).

## All commands

```text
--8<-- "snippets/cli/help.txt"
```

| Command | What it does | Page |
|---|---|---|
| `deucalion` | Opens the app (on a desktop); prints the list of commands otherwise. | [gui](gui.md) |
| `gui` | Opens the app. | [gui](gui.md) |
| `deps` | Checks (and installs) what Deucalion needs, including VeraCrypt. | [deps](deps.md) |
| `drives` | Lists the drives plugged into this computer. | [drives and targets](drives.md) |
| `targets` | Lists your registered backup drives. | [drives and targets](drives.md) |
| `setup-drive` | Prepares a drive for backups: format and/or encrypt it. | [setup-drive](setup-drive.md) |
| `register` | Uses a drive (or a folder on it) as it is, for backups. | [register](register.md) |
| `open`, `close` | Unlock or lock an encrypted backup drive; close any backup drive before unplugging it. | [open and close](open-close.md) |
| `backup` | Backs up everything, or only some folders. | [backup](backup.md) |
| `status` | Shows the state of the backup. | [status](status.md) |
| `ls` | Lists what is in the backup, with the original names. | [ls](ls.md) |
| `restore` | Restores files or folders. | [restore](restore.md) |
| `rebuild` | Rebuilds this computer from a backup, step by step. | [rebuild](rebuild.md) |
| `verify` | Checks that the backup on the drive is complete and undamaged. | [verify](verify.md) |
| `removed` | Lists or empties Removed Files (`_removed/`). | [removed](removed.md) |
| `exclude` | Manages what is left out of your home folder's backup. | [exclude](exclude.md) |
| `folder` | Manages extra folders outside your home folder. | [folder](folder.md) |
| `profile` | Manages saved selections for partial backups. | [profile](profile.md) |
| `config` | Shows or edits the configuration file. | [config](config.md) |

## Things that work the same everywhere

**Help.** Add `--help` (or `-h`) to any command to see its options: `deucalion backup --help`.
`deucalion --version` prints the version.

**Which drive.** Commands that use a backup drive take `--target NAME`, where `NAME` is the drive's
name (as `deucalion targets` shows it) or its id. Without it, Deucalion uses your **default** drive;
if you have several drives and no default, it asks you to choose one with `--target`.

**Locked drives.** If the backup drive is encrypted and locked, commands that need it ask for its
password and unlock it first:

```text
--8<-- "snippets/cli/status-locked.txt"
```

**Paths.** Files and folders can be given as you see them on your computer
(`~/Documents/report.pdf`, `/home/alex/Documents`) or as they are named in the backup
(`home/Documents`). Put names with spaces or special characters in quotes:
`"~/Documents/Budget 2026.ods"`.

**Questions.** When a command needs a yes or no, it asks: `Restore now? [y/N]`. Type `y` and press
++enter++ for yes; anything else (or just ++enter++) means no. `-y` or `--yes` answers yes in advance.
Without a terminal to ask in (for example in a script), a question counts as **no** unless you give
`--yes`.

**Stopping.** Press ++ctrl+c++ once to stop a backup, restore, rebuild or verify **safely**: Deucalion
prints *Stopping safely… (press Ctrl+C again to abort immediately)* and stops at the next safe point.
A half-copied file is thrown away, never left behind; a file a restore was replacing is put back.
Press it a second time to stop immediately. Either way, the next run continues where it stopped.
Package installations and `/etc` changes during a rebuild are never cut off half way.

**Colours.** Deucalion colours its output in a terminal (green for success, yellow for warnings, red
for errors). Set `NO_COLOR=1` to turn colours off.

**Administrator password.** Deucalion never needs `sudo` in front of it, and refuses to run as root.
When a step needs administrator rights, it asks: `[Deucalion] administrator password for alex:`. See
[Administrator access](../concepts/administrator-access.md).

## Exit codes

Every command ends with a number that scripts can check (`echo $?` shows it):

| Code | Meaning |
|---|---|
| `0` | Done. (For `verify`: the backup is intact.) |
| `1` | Something went wrong, or you answered **no** to a question. The message says what. (For `verify`: problems were found.) |
| `2` | The command was typed wrong (unknown command or option); the usage is printed. |
| `130` | Stopped with ++ctrl+c++ (or stopped safely). |

## Unexpected errors

If something unexpected happens, Deucalion prints:

```text
Unexpected error: <the error>
Nothing on your machine was changed by a backup. Run again with DEUCALION_DEBUG=1 for details, and please report it.
```

Run the command again as `DEUCALION_DEBUG=1 deucalion …` to see the full details, and
[report it](https://github.com/Dimitrios-Kafetzis/Deucalion/issues).
