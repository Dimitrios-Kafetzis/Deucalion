# Environment variables

Deucalion works without any of these. They are for special cases, scripts and development.

| Variable | Effect |
|---|---|
| `NO_COLOR` | Any value: no colours in the terminal output. |
| `DEUCALION_DEBUG` | Any value: on an unexpected error, show the full Python error instead of a short message. |
| `DEUCALION_CONFIG_DIR` | Folder for `config.json` instead of `~/.config/deucalion`. |
| `DEUCALION_STATE_DIR` | Folder for working files instead of `~/.local/state/deucalion`. |
| `XDG_CONFIG_HOME`, `XDG_STATE_HOME` | Standard locations; used when the two above aren't set. |
| `DEUCALION_PASSWORD_STDIN` | Any value: read backup passwords from standard input (one line each) instead of asking in the terminal. See [Use Deucalion without a desktop](../tutorials/headless.md). |
| `VISUAL`, `EDITOR` | The editor `deucalion config edit` opens (default `nano`). |
| `DEUCALION_ALLOW_ROOT` | Any value: allow running as root. Not recommended; Deucalion asks for administrator rights itself. |

## For tests

| Variable | Effect |
|---|---|
| `DEUCALION_TEST_EXFAT` | A mounted exFAT folder: also run the test suite on a real exFAT volume. |
| `DEUCALION_TEST_UDISKS` | Any value: also run the LUKS drive-setup test on a disk image (needs a desktop session). |

## For the documentation's screenshots

These are only read when `DEUCALION_SCREENSHOT_DIR` is set; see [Documentation and screenshots](../developers/documentation.md).

| Variable | Effect |
|---|---|
| `DEUCALION_SCREENSHOT_DIR` | Folder to save screenshots in. Turns screenshot mode on. |
| `DEUCALION_SCREENSHOT_PAGES` | What to show and photograph, as a list of entries. |
| `DEUCALION_SCREENSHOT_WAIT` | Default wait before each picture, in milliseconds (1200). |
| `DEUCALION_SCREENSHOT_SIZE` | Window size, e.g. `1024x760`. |
| `DEUCALION_SCREENSHOT_THEME` | `light` or `dark`. |
| `DEUCALION_SCREENSHOT_FONT` | Font (default `Ubuntu Sans 11`). |
