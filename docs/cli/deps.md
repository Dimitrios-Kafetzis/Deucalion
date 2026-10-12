# `deucalion deps`

Checks what Deucalion needs, and installs what is missing. The installer (`./install.sh`) runs
`deucalion deps --install` first.

```text
--8<-- "snippets/cli/help-deps.txt"
```

```text
--8<-- "snippets/cli/deps.txt"
```

| Option | What it does |
|---|---|
| *(none)* | Show what is installed (✓) and what is missing (✗). |
| `--install` | Install what is missing with apt (asks first, then for your administrator password), and offer to install VeraCrypt. |
| `--veracrypt` | With `--install`: install VeraCrypt without asking. |
| `--no-veracrypt` | With `--install`: don't install VeraCrypt and don't ask. |
| `-y`, `--yes` | Don't ask before installing packages (and VeraCrypt). |

For what each package is for, and how VeraCrypt is downloaded and checked, see
[Install](../getting-started/install.md#what-the-installer-checks-deucalion-deps).

!!! note "VeraCrypt on a computer without a desktop"
    VeraCrypt's official package needs the `libsm6` library but doesn't say so. Every Ubuntu Desktop
    has it; a minimal or server installation may not. There, VeraCrypt is reported as installed but
    fails with *"libSM.so.6: cannot open shared object file"*. Install it with `sudo apt install
    libsm6`. See [Use Deucalion without a desktop](../tutorials/headless.md).

## Exit codes

| Code | Without `--install` | With `--install` |
|---|---|---|
| `0` | Everything needed is installed (VeraCrypt doesn't count). | Everything needed is installed now. |
| `1` | Something needed is missing. | Still missing: … |
