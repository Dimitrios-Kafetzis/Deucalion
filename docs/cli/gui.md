# `deucalion gui`

Opens the [app](../app/index.md). Typing just `deucalion` does the same when you are on a desktop.

```text
--8<-- "snippets/cli/help-gui.txt"
```

Without a desktop (for example over SSH), plain `deucalion` prints the list of commands instead:

```text
--8<-- "snippets/cli/headless-gui.txt"
```

If the app's libraries are missing: *"The app can't start (…). The python3-gi, gir1.2-gtk-4.0 and
gir1.2-adw-1 packages are needed."* Install them with [`deucalion deps --install`](deps.md).

## Exit codes

`0` when the app is closed; `1` if it can't start.
