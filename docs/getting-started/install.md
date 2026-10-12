# Install Deucalion

**What you'll do:** download Deucalion and run its installer, which checks what your computer
needs, installs anything missing, and adds Deucalion to your app menu.<br>
**What you need:** Ubuntu 24.04 or newer (22.04 for the command line only), an internet connection, your administrator password.<br>
**How long it takes:** about 5 minutes.

The installer is a command you run once in a terminal. If you have never used a terminal, see
[Opening a terminal](index.md#opening-a-terminal-only-needed-for-the-command-line); you only need to
copy and paste.

## Step by step

1. Open a terminal: press ++ctrl+alt+t++.
2. Install `git`, the tool that downloads Deucalion. Copy this line, paste it into the terminal with
   ++ctrl+shift+v++, and press ++enter++. Type your password when asked (nothing appears while you
   type), then press ++enter++ again. If git is already installed, it says so and changes nothing.

    ```bash
    sudo apt install git
    ```

3. Download Deucalion into a folder called `Deucalion` in your home folder:

    ```bash
    git clone https://github.com/Dimitrios-Kafetzis/Deucalion.git ~/Deucalion
    ```

4. Go into the folder you just downloaded and start the installer:

    ```bash
    cd ~/Deucalion
    ./install.sh
    ```

5. The installer first lists what Deucalion needs, with a ✓ for what is already there and a ✗ for
   what is missing. If something is missing, it asks before installing it: type `y` and press
   ++enter++, then type your password when asked.

6. It then asks whether to install **VeraCrypt**. You need it only if you want an encrypted drive
   that can also be opened on Windows or macOS (see [Choosing a drive](../choosing-a-drive.md)). If
   you are not sure, answer `y`: it does no harm.

7. When it says **Done**, Deucalion is installed. You see something like this:

```text
--8<-- "snippets/cli/install.txt"
```

The `…` line stands for many lines of installation output from Ubuntu's package manager.

**What you have now:** Deucalion in your app menu (search for "Deucalion") and the `deucalion`
command in the terminal.

!!! note "On Ubuntu 22.04"
    The app needs Ubuntu 24.04 or newer. On 22.04 the installer says *"No app menu entry: The app needs
    Ubuntu 24.04 or newer …"* and installs only the `deucalion` command, which does everything the app
    does. See the [command line](../cli/index.md).

!!! note "If `deucalion` says *command not found* right after installing"
    On a computer where nothing was installed this way before, Ubuntu adds the folder that holds the
    `deucalion` command (`~/.local/bin`) to its search path only when you log in. Log out and back
    in once. Until then, you can type `~/.local/bin/deucalion` instead of `deucalion`.

## Recommended: install the administrator helper

A few things Deucalion does need administrator rights: saving your Wi-Fi passwords and protected
system settings, using a VeraCrypt drive, and installing apps during a rebuild. Deucalion does them
through a small *administrator helper* (see [Administrator access](../concepts/administrator-access.md)).

Installing the helper system-wide is recommended. Run:

```bash
cd ~/Deucalion
./install.sh --system-helper
```

```text
--8<-- "snippets/cli/install-system-helper.txt"
```

It asks for your password once. It puts a copy of the helper in `/usr/local/libexec/deucalion/`,
owned by the administrator, so other programs running as you can't change the code that runs with
administrator rights. It also gives you a clearer password prompt: *"Deucalion needs administrator
access to save or restore protected system settings, or to use an encrypted VeraCrypt drive"*, and
Ubuntu remembers your password for a few minutes so you aren't asked again and again.

Without it, Deucalion still works: it runs the helper from its own folder, and Ubuntu shows a
generic password prompt.

## What the installer checks: `deucalion deps`

The installer runs `deucalion deps --install`. You can run `deucalion deps` yourself at any time
to see what is installed:

```text
--8<-- "snippets/cli/deps.txt"
```

| Package | Needed for |
|---|---|
| `python3-gi` | talking to Ubuntu's disk service, and the app |
| `gir1.2-gtk-4.0`, `gir1.2-adw-1` | the app's window and its GNOME look |
| `udisks2` | preparing, unlocking and mounting drives |
| `cryptsetup` | opening encrypted drives |
| `exfatprogs` | creating exFAT drives (readable on Linux, macOS and Windows) |
| `pkexec` | asking for the administrator password |
| `dconf-cli` | saving desktop settings |
| `gnupg` | checking the VeraCrypt download's signature |
| `veracrypt` | VeraCrypt-encrypted drives (optional) |

On a normal Ubuntu Desktop, everything except VeraCrypt is usually already installed. See
[`deucalion deps`](../cli/deps.md) for all options.

### How VeraCrypt is installed

VeraCrypt is not in Ubuntu's own software collection. Deucalion downloads the official package from
VeraCrypt's release page on GitHub and installs it only if:

- its digital signature was made by VeraCrypt's signing key (Deucalion knows the key's fingerprint,
  `5069A233D55A0EEB174A5FC3821ACD02680D16DE`, and refuses any other key, and any revoked or expired
  one);
- it is version 1.26.29 or newer;
- it really comes from VeraCrypt's GitHub release address.

If any check fails, nothing is installed. You can also install VeraCrypt yourself from
[veracrypt.fr](https://www.veracrypt.fr/en/Downloads.html).

## Other ways to run Deucalion

You don't have to install Deucalion to use it:

- **From the downloaded folder:** run `~/Deucalion/bin/deucalion` (add a command after it, such as
  `~/Deucalion/bin/deucalion status`). With no command, it opens the app.
- **From a backup drive:** every drive Deucalion prepares (except a fully encrypted one) has a
  `Deucalion-Tool` folder with a copy of Deucalion. On a new computer, open a terminal in that
  folder and run `bin/deucalion`. This is how a [rebuild](../tutorials/rebuild.md) usually starts.

## Updating

Download the new version and run the installer again:

```bash
cd ~/Deucalion
git pull
./install.sh
```

If you installed the administrator helper and it changed, the installer updates it too (it asks for
your password). Deucalion refuses to use a helper from another version and tells you to run
`./install.sh --system-helper`.

## Uninstalling

```bash
cd ~/Deucalion
./install.sh --uninstall
```

This removes the program, the `deucalion` command, the app menu entry and icon, and the
administrator helper (asking for your password if it was installed). **Your backups and your
settings (`~/.config/deucalion`) are kept.** VeraCrypt and the Ubuntu packages Deucalion needed stay
installed; remove them with Ubuntu's software tools if you no longer need them.

## Installer options

| Option | What it does |
|---|---|
| *(none)* | Check and install what is needed (asking first), then install Deucalion for you. |
| `--system-helper` | Also install the administrator helper system-wide (asks for your password). |
| `--uninstall` | Remove Deucalion (keeps your backups and settings). |
| `--veracrypt` | Install VeraCrypt without asking. |
| `--no-veracrypt` | Don't install VeraCrypt and don't ask. |
| `--yes`, `-y` | Install missing packages without asking. |

**Next:** [Your first backup](first-backup.md).
