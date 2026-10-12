# Configuration file

Deucalion keeps its settings in `~/.config/deucalion/config.json` (or `$XDG_CONFIG_HOME/deucalion/`, or
`$DEUCALION_CONFIG_DIR`). The app and the commands change it for you; you rarely need to edit it.
`deucalion config show` prints it with the default values filled in; `deucalion config edit` opens it in
your editor. It is a [JSON](https://www.json.org) file: keep the quotes, commas and brackets.

Missing keys take their default value. Your backup drives' passwords are never stored here.

## Keys

### `version`

The file's format version. Default: `1`. Don't change it.

### `targets`

Your registered backup drives, by id:

```json
"targets": {
  "fcf91aec-…": {
    "name": "Alex Backup",
    "path": "/media/alex/Alex Backup/Deucalion-Backup",
    "registered": "2026-10-11T23:16:38+01:00",
    "allow_internal": false,
    "access": { "method": "veracrypt", "kind": "partition", "partuuid": "…",
                "mount_name": "Alex Backup", "plain_uuid": "…" }
  }
}
```

| Key | Meaning |
|---|---|
| `name` | The drive's name. |
| `path` | Where its backup folder was last found (updated automatically when it is mounted elsewhere). |
| `registered` | When it was first registered. |
| `allow_internal` | For testing only. |
| `access` | How to unlock it: see [`drive.json`](drive-contents.md#deucalion-tooldrivejson). `{"method": "none"}` for unencrypted drives. |

Default: `{}`. Use the app's **Drives** page, `setup-drive`, `register` and `open` to change it. To stop
using a drive from the command line, remove its entry here (or use **Forget** in the app).

### `default_target`

The id of the drive backups go to. Default: `null` (the only drive, if there is one). Change it with the star button on
the **Drives** page or `deucalion register <backup folder> --default`.

### `home_path`

The home folder to back up. Default: `null` (your own home folder). Set only for special cases, for
example testing.

### `home_excludes`

What is left out of your home folder: a list of [patterns](exclusion-patterns.md). Default: the
[default exclusions](exclusion-patterns.md#default-exclusions). Changed by **Settings** and
`deucalion exclude`.

### `extra_folders`

Folders outside your home folder that full backups include:

```json
"extra_folders": [
  { "name": "shared", "path": "/srv/shared", "excludes": [] }
]
```

| Key | Meaning |
|---|---|
| `name` | Short name; the folder is stored in the backup under `extras/<name>`. |
| `path` | The folder. |
| `excludes` | Patterns left out of this folder, relative to it. **Only editable here.** |

Default: `[]`. Changed by **Settings → Extra folders** and `deucalion folder`.

### `profiles`

Named lists of paths for partial backups: `{"work": ["/home/alex/Projects", "/home/alex/Documents/Work"]}`.
Default: `{}`. Changed by `deucalion profile`.

### `keep_overwritten`

`true`: the previous version of a changed file goes to Removed Files. `false`: it is replaced directly
(files deleted from your computer still go to Removed Files). Default: `true`. Changed by **Settings →
Keep old versions of changed files**.

### `system_recipe`

`true`: full backups save the [system recipe](../concepts/system-recipe.md). Default: `true`. Changed by
**Save system settings** (Back Up page and Settings). On the command line, `--no-system` skips it once.

### `system_admin`

`true`: full backups also save the [protected settings](../tutorials/protected-settings.md) (asks for
the administrator password). Default: `true`. Changed by **Include protected settings**. On the
command line, `--no-admin` skips it once.

## A complete example

The demo configuration:

```text
--8<-- "snippets/cli/config-show.txt"
```
