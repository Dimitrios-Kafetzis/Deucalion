# Administrator access

Deucalion runs as you, never as the administrator ("root"). Do not start it with `sudo`; it refuses:

```text
Please run Deucalion as your normal user (not with sudo). It asks for the admin password itself when a step needs it.
```

A few tasks do need administrator rights. For those, and only for those, Deucalion asks for your
password.

## When it asks

| Task | Why |
|---|---|
| A full backup with **Include protected settings** on (the default) | to read saved Wi-Fi/VPN connections, some `/etc` files and the administrator's crontab |
| Creating, unlocking or locking a **VeraCrypt** drive | Ubuntu only lets the administrator do this |
| Rebuild steps 2, 3, 7 and 8 | to add software sources, install packages, write `/etc` files, add you to groups, enable services, import network connections |
| Installing missing packages or VeraCrypt (`deucalion deps --install`, the installer) | to install software |

Everything else needs **no** password: backups without protected settings, restoring your files,
and preparing, unlocking and mounting **exFAT and LUKS** drives. These go through Ubuntu's disk
service (UDisks), which lets the person sitting at the computer manage external drives.

## How the password is asked

- **In the app**, Ubuntu shows its password window. With the [system helper installed](../getting-started/install.md#recommended-install-the-administrator-helper),
  it says *"Deucalion needs administrator access to save or restore protected system settings, or to
  use an encrypted VeraCrypt drive"* and remembers your password for a few minutes.
- **In a terminal**, `sudo` asks: `[Deucalion] administrator password for alex:`.
- **On a computer without a desktop** (for example over SSH), if `sudo` works without a password
  (`sudo -n`), Deucalion uses that and asks nothing. See [Use Deucalion without a desktop](../tutorials/headless.md).

The password is asked **once per task**: Deucalion starts one helper process and sends all the
administrator work of that task through it.

## The administrator helper

All administrator work goes through one small program, the **administrator helper**
(`deucalion/helper.py`). It is deliberately narrow:

- It accepts only a **fixed list of operations** (16 in version 0.2), and checks every argument:
  package names must look like package names, files written to `/etc` must be inside `/etc`, and so
  on. Anything else is refused.
- It **refuses to touch the disk your system runs from**, whatever it is asked.
- It runs with `python3 -I` and uses nothing but Python's standard library, so other Python files
  can't change what it does.
- **Ctrl+C doesn't interrupt it**, so a package installation or a write to `/etc` is never cut off
  half way.
- The app checks that the installed helper is **exactly the same file** as its own copy, and refuses
  to use a different one: *"The installed administrator helper does not match this version of
  Deucalion. Update it with: ./install.sh --system-helper (from the Deucalion folder)"*.

When you install it with `./install.sh --system-helper`, it is placed in
`/usr/local/libexec/deucalion/helper.py`, owned by root and not writable by anyone else. Without
it, Deucalion runs the helper from its own folder, which works the same but is a file you (and any
program you run) could change.

## Related

- [How your data is protected](safety.md)
- [Include protected settings](../tutorials/protected-settings.md)
