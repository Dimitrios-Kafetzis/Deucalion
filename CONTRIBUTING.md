# Contributing to Deucalion

Thank you for helping. Deucalion looks after people's files, so every change is held to one rule
above all: **never lose or damage data**, on the computer or on the backup drive.

## Ways to help

- **Report a bug** with the [bug report form](https://github.com/Dimitrios-Kafetzis/Deucalion/issues/new/choose).
  Include `deucalion --version`, your Ubuntu version, the drive layout, and the exact message.
  Logs are in `~/.local/state/deucalion/logs/`. Remove anything private from them first.
- **Ask a question or share an idea** in [Discussions](https://github.com/Dimitrios-Kafetzis/Deucalion/discussions).
- **Improve the documentation.** It is written for people who are not technical: short sentences,
  second person, bold labels for buttons. A clearer sentence or a missing step helps a lot.
- **Fix a bug or add a feature.** For anything bigger than a small fix, open an issue or a discussion
  first so we can agree on the approach.

Security problems: please don't open a public issue; see [SECURITY.md](SECURITY.md).

## Setting up

Deucalion is Python 3.10+ with the standard library only, plus PyGObject (GTK 4 and libadwaita) for
the app and for talking to UDisks. It runs straight from the clone:

```bash
git clone https://github.com/Dimitrios-Kafetzis/Deucalion.git
cd Deucalion
bin/deucalion deps          # check what is missing (deps --install to install it)
bin/deucalion               # the app
bin/deucalion --help        # the commands
```

The [developer documentation](https://dimitrios-kafetzis.github.io/Deucalion/developers/) explains
the architecture and the design principles.

## Testing

```bash
python3 -m unittest discover -s tests
```

The tests use temporary folders as a fake home and a fake drive. They need no drive and no
administrator password. More checks (real exFAT, LUKS, the torture test, the administrator and
VeraCrypt checks, a rebuild in a VM) are described in
[Tests](https://dimitrios-kafetzis.github.io/Deucalion/developers/testing/).

> [!CAUTION]
> Never point a test, the torture test or a manual check at a drive that holds data. Use disk
> images or throwaway virtual machines.

## Making a change

1. Fork the repository and create a branch from `main`.
2. Keep the change focused. Match the surrounding code: its naming, comment style and idioms.
3. **No new dependencies.** Deucalion must run from a backup drive on a freshly installed Ubuntu, so
   it uses only the standard library and what Ubuntu ships (PyGObject, UDisks, cryptsetup).
4. **Add a test.** Every bug fix comes with a regression test that fails without the fix.
5. **Keep messages plain.** Anything a user reads says what happened and what to do next, in everyday
   words.
6. If the change affects what the app shows or what a command prints, update the documentation in
   `docs/`. Regenerate the screenshots and terminal output with `docs/tools/screenshots.py` (see
   [Documentation and screenshots](https://dimitrios-kafetzis.github.io/Deucalion/developers/documentation/)),
   and check that `mkdocs build --strict` passes.
7. Add a line to the `Unreleased` section of [CHANGELOG.md](CHANGELOG.md) (create the section if it
   isn't there).
8. Run the tests, then open a pull request and fill in the template.

### Changes to the administrator helper

`deucalion/helper.py` runs as root. Changes to it get extra review:

- Keep the list of operations fixed and check every argument.
- Never allow access to the system disk.
- Bump `HELPER_VERSION` when an operation or its arguments change.
- Add tests for the requests the helper must refuse.

### Commit messages

Write a short summary in the imperative ("Fix drive names with spaces"). Add a body when the reason
isn't obvious from the change.

## License

Deucalion is licensed under the [GNU General Public License v3.0 or later](LICENSE). By contributing,
you agree that your contributions are licensed under the same terms.

Everyone taking part is expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
