# `deucalion config`

Shows or edits Deucalion's [configuration file](../reference/configuration.md),
`~/.config/deucalion/config.json`.

```text
--8<-- "snippets/cli/help-config.txt"
```

| Command | What it does |
|---|---|
| `deucalion config` (or `config show`) | Print the configuration, with the default values filled in. |
| `deucalion config path` | Print where the file is. |
| `deucalion config edit` | Open the file in your text editor (`$VISUAL`, then `$EDITOR`, then `nano`). When you close the editor, Deucalion checks that the file can still be read. |

```text
--8<-- "snippets/cli/config-path.txt"
```

```text
--8<-- "snippets/cli/config-show.txt"
```

Most settings have their own command or app page; edit the file directly only for what has none
(for example a [list of exclusions for an extra folder](../reference/configuration.md#extra_folders)).
A file that can't be read stops every command with *"Configuration file is damaged: …"*.

## Exit codes

`0` done; `1` the file is damaged.

## Related

- [The configuration file](../reference/configuration.md)
