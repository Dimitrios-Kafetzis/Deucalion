# `deucalion open` and `deucalion close`

## `open`: unlock an encrypted backup drive

Asks for the backup's password, unlocks the encrypted drive (or part, or folder), and mounts it.

```text
--8<-- "snippets/cli/help-open.txt"
```

```text
--8<-- "snippets/cli/open.txt"
```

You rarely need `open` on its own: any command that needs a locked drive (`backup`, `status`,
`restore`…) asks for the password and unlocks it first.

**On a new computer** (or after you [forgot](../app/drives.md#backup-drives) the drive), `open` finds
the encrypted backup by itself, if the drive has a normal part: it reads
`Deucalion-Tool/drive.json` on every mounted drive. It then unlocks the backup and **registers** it,
remembering how to unlock it next time:

```text
--8<-- "snippets/cli/new-open.txt"
```

If it can't find it, give the encrypted part or file the first time (only needed once):

```bash
deucalion open /dev/sdb2                             # an encrypted part, or a whole encrypted drive's part
deucalion open /media/alex/Photos/Deucalion-Backup.hc   # an encrypted folder (VeraCrypt)
deucalion open /media/alex/Photos/Deucalion-Backup.luks # an encrypted folder (LUKS)
```

A part is opened as LUKS if it is a LUKS volume, as VeraCrypt otherwise; a file ending in `.luks` as
LUKS, any other file as VeraCrypt.

| Option | What it does |
|---|---|
| `source` | The encrypted part (`/dev/sdb2`) or file; only needed when Deucalion can't find it. |
| `--target NAME` | Which registered drive to unlock. |

VeraCrypt needs your administrator password to unlock (*"Unlocking (you will be asked for your
administrator password)…"*) and can take up to a minute. **Opening a VeraCrypt drive doesn't need the
VeraCrypt app**: Deucalion uses Ubuntu's own `cryptsetup`. LUKS needs no administrator password.

Messages:

| Message | Meaning |
|---|---|
| `Wrong password.` (LUKS) / `wrong password, or this is not a VeraCrypt volume` (VeraCrypt) | Try again; check ++caps-lock++ and the keyboard layout. |
| `No encrypted Deucalion backup found. Plug in the drive, or give the encrypted partition or file: deucalion open /dev/sdb2` | The drive isn't plugged in, its normal part isn't mounted, or it has no normal part (whole-drive encryption). |
| `Unlocked at …, but there is no Deucalion backup in it.` | The password was right, but this encrypted volume has no backup. |
| `The backup drive is not connected.` | The registered drive isn't plugged in. |

## `close`: lock (or unmount) before unplugging

Locks an encrypted backup drive, or unmounts a normal one, so you can unplug it safely.

```text
--8<-- "snippets/cli/help-close.txt"
```

```text
--8<-- "snippets/cli/close.txt"
```

For a drive that isn't encrypted it unmounts the drive's part that holds the backup (if it isn't
mounted: *"The backup drive is not mounted."*). For an encrypted folder it also detaches the file,
so the drive can be unplugged.

If a window or program still uses the drive: *"The drive is in use. Close any window or program that
shows its files, then try again."*

!!! tip "Always close before unplugging"
    Unplugging a drive without closing it may lose the last changes written to it. Deucalion's
    backup survives this (the next backup repairs it), but other files on the drive may not.

## Exit codes

`0` done; `1` an error (wrong password, drive not found…); `130` stopped.

## Related

- [Unlock and lock an encrypted drive](../tutorials/unlock-lock.md)
- [Open your backup without Deucalion](../tutorials/open-without-deucalion.md)
