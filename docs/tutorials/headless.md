# Use Deucalion without a desktop

**What you'll do:** back up, restore or rebuild a computer you reach over SSH, or a server without a
desktop.<br>
**What you need:** a terminal on that computer; `sudo` rights there.<br>
**How long it takes:** as on a desktop.

Everything works from the [command line](../cli/index.md). A few things behave differently when there
is no desktop session.

## What is different

**The app doesn't open.** Plain `deucalion` prints the list of commands:

```text
--8<-- "snippets/cli/headless-gui.txt"
```

**Administrator access goes through `sudo`.** Without a desktop, Deucalion uses `sudo` for the
[administrator helper](../concepts/administrator-access.md):

- if `sudo` works **without a password** for you (`sudo -n true` succeeds, as on many cloud machines),
  Deucalion uses it and asks nothing;
- otherwise it asks for your password in the terminal: `[Deucalion] administrator password for …:`.

**Mounting drives needs administrator rights.** On a desktop, Ubuntu's disk service (UDisks) lets the
person at the computer mount and unlock external drives. Over SSH it asks for an administrator
password instead: `udisksctl mount` asks for it in the terminal, and without a way to ask it refuses:

```text
--8<-- "snippets/cli/headless-udisks-mount.txt"
```

Deucalion's own disk-service calls can't ask either, so over SSH they fail with *"Not authorized to
perform operation"*.

So mount the drive (or its normal part) yourself with `sudo`, owned by you:

```text
--8<-- "snippets/cli/headless-sudo-mount.txt"
```

Then Deucalion finds the backup as usual. A **VeraCrypt** backup is unlocked through the
administrator helper, so it works the same as on a desktop:

```text
--8<-- "snippets/cli/headless-open.txt"
```

This affects **LUKS** drives and LUKS encrypted folders, and **setting up drives** (`setup-drive`):
Deucalion does these through the disk service, so over SSH they fail with *"Not authorized to perform
operation"*. Set up drives on a desktop, or unlock LUKS by hand
(`sudo cryptsetup open /dev/sdX2 backup` then `sudo mount -o uid=$(id -u) /dev/mapper/backup /mnt/x`)
and [register](../cli/register.md) the folder.

**A rebuild restores `~/.ssh`.** Your home folder's `.ssh` folder comes back from the backup,
including `authorized_keys`, which lists the keys allowed to log in over SSH. If you reach the new
computer over SSH with a key that isn't in the old computer's `authorized_keys`, you will be locked out
after step 4. Before the rebuild, add your key to the old computer's `~/.ssh/authorized_keys` and back
up, or untick `.ssh/` in step 4.

**No desktop settings.** On a server without GNOME, the desktop settings step of a rebuild says there
is nothing to do; desktop settings are not saved when `dconf` isn't installed.

**VeraCrypt may need `libsm6`.** VeraCrypt's official package needs the `libsm6` library without
declaring it; every desktop has it, a minimal server may not. Install it with `sudo apt install libsm6`
if VeraCrypt fails with *"libSM.so.6: cannot open shared object file"*.

**Questions need a terminal.** Commands that ask something need a terminal (an interactive SSH
session). In scripts, answer in advance: `--yes` for questions, `--yes-erase sdX` to erase a drive;
`rebuild` needs `--yes` (apply the pre-selected items) or `--dry-run`. Passwords can be given on
standard input with `DEUCALION_PASSWORD_STDIN=1` (one line per password asked):

```bash
printf '%s\n' "$BACKUP_PASSWORD" | DEUCALION_PASSWORD_STDIN=1 deucalion open
```

!!! warning
    Anything that stores the password in a file or in your shell history is a risk. Prefer typing it
    in an interactive session.

## A rebuild over SSH

1. Mount the drive's normal part with `sudo` (above), and `cd` into its `Deucalion-Tool` folder.
2. `bin/deucalion open` (password; administrator password if `sudo` asks).
3. `bin/deucalion rebuild`, answering each step (see [`rebuild`](../cli/rebuild.md)).
4. Log out and back in.

**What you have now:** Deucalion working on a computer without a desktop.
