# Documentation and screenshots

This site is built with [MkDocs](https://www.mkdocs.org) and
[Material for MkDocs](https://squidfunk.github.io/mkdocs-material/). Its source is in `docs/`, and its
configuration is `mkdocs.yml`.

## Preview and build

```bash
python3 -m venv ~/.venvs/deucalion-docs
~/.venvs/deucalion-docs/bin/pip install -r docs/requirements.txt
~/.venvs/deucalion-docs/bin/mkdocs serve           # preview at http://127.0.0.1:8000
~/.venvs/deucalion-docs/bin/mkdocs build --strict  # fails on any warning, such as a broken link
```

## Real output only

Every screenshot and every piece of terminal output on this site comes from a real run; nothing is
typed by hand. Terminal output is in `docs/snippets/cli/<name>.txt` and is included in pages like this:

````markdown
```text
--8<-- "snippets/cli/status.txt"
```
````

Screenshots are in `docs/assets/screenshots/<section>/<name>.png`.

## Making them again

After changing the app or what a command prints, run:

```bash
python3 docs/tools/screenshots.py                  # everything, from scratch (about an hour)
python3 docs/tools/screenshots.py --stage layouts  # or one stage: old, layouts, new
```

It never touches this computer's drives or system: everything runs in throwaway Ubuntu virtual
machines (QEMU/KVM), and the "drives" are image files that the VM sees as USB drives.

| Stage | What it does |
|---|---|
| `base` | Downloads Ubuntu 24.04 and 26.04 cloud images (checked against Ubuntu's signed `SHA256SUMS`) and prepares two VM disks with what an Ubuntu Desktop has (GTK, UDisks, fonts…). Cached in `~/.cache/deucalion-docs/`. |
| `old` | "Alex's laptop" (24.04, user `alex`): a fictional home folder (`demo_home.py`) and system (`old_machine.sh`), the drive wizard, backups, restores, Removed Files, Settings, locking, error messages, and the command line. |
| `layouts` | Every drive layout, in the app and in a terminal; opening backups without Deucalion. |
| `new` | "Alex's new laptop" (26.04, user `alexk`): Deucalion run from the drive, the rebuild in the app, how Deucalion behaves without a desktop, and the rebuild in a terminal. Needs a previous `old` run (it uses that run's backup drive). |

It needs `qemu-system-x86`, `qemu-utils`, `gpgv`, `ssh` and KVM, about 40 GB of free disk space while it
runs (the demo drives are deleted at the end), and an internet connection (for VeraCrypt, apt and snap
inside the VMs). `pngquant`, if installed, makes the images smaller.

### How the screenshots are taken

The app has a **screenshot mode**, active only when `DEUCALION_SCREENSHOT_DIR` is set. It draws the
window with GTK's Broadway backend, so no window appears on any screen, and saves a PNG after each entry
of `DEUCALION_SCREENSHOT_PAGES`:

```text
[name=]page[:action[(argument)]][@milliseconds]
```

- `page`: a sidebar page (`overview`, `backup`, `restore`, `rebuild`, `drives`, `removed`,
  `settings`), or `win` for the window itself.
- `action`: calls `screenshot_<action>(argument)` on that page and does what a click would do, for
  example `drives:pick(encrypt-part)`, `restore:select(home/Documents/Notes.txt)` or `win:close`.
  Actions that wait for something (`backup:finished`, `drives:finished`, `rebuild:applied`) are
  repeated every second until it is done.
- `name`: the PNG's name; `_` takes no picture. `@ms`: how long to wait before the picture.

The tools in `docs/tools/`:

| File | Role |
|---|---|
| `screenshots.py` | The entry point: the stages; copies the results into `docs/`. |
| `vm.py` | Cloud images and VMs (cloud-init over HTTP, QEMU/KVM, SSH), and USB drives through QEMU's control interface. |
| `scenario_old.py`, `scenario_layouts.py`, `scenario_new.py`, `scenario_common.py` | The scenarios. Each step is a function; with `--keep`, the VM stays up, and `scenario_old.py --attach DIR --from STEP` runs steps again on it. |
| `capture.py` | Runs inside the VM: runs commands in a terminal and saves what they print (answering their questions; passwords are never echoed), and takes app screenshots. |
| `demo_home.py`, `old_machine.sh` | The fictional demo home folder and system. |

!!! note "Demo machines only"
    In the VMs, a polkit rule lets the demo user do administrator tasks without a password window,
    because there is no screen to show it on. Otherwise they are ordinary Ubuntu installations.

## Publishing

The site is published with GitHub Pages.
