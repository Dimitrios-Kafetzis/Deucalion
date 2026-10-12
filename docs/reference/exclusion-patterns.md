# Exclusion patterns

Patterns decide what is left out of a backup. They are matched against paths **inside your home
folder** (or inside an extra folder, for its own list).

## Rules

| Pattern | Matches |
|---|---|
| A name without `/` | A file or folder with that name **anywhere**. `notes.tmp` leaves out every `notes.tmp`. |
| A path with `/` | That path from the top of your home folder. `.local/share/Trash` leaves out only `~/.local/share/Trash`. |
| Ending with `/` | **Folders** only. `build/` leaves out folders called `build`, but not a file called `build`. |
| `*` | Any characters within one name (not `/`). `*.iso` matches `ubuntu.iso` anywhere. |
| `**` | Any number of folders (including none). `.config/**/Cache/` matches `.config/Code/Cache` and `.config/a/b/Cache`. |
| `?` | Exactly one character (not `/`). `IMG_????.jpg` matches `IMG_0001.jpg`. |
| Starting with `#` | A comment; ignored. |

Matching is case-sensitive: `Videos/` doesn't match `videos`.

!!! note "A single name always matches anywhere"
    A leading `/` is removed before matching, so `/Videos/` is the same as `Videos/`: every folder
    called `Videos`, at any depth. A pattern with a `/` *inside* is anchored to the top of your home
    folder: `Documents/Videos/` leaves out only `~/Documents/Videos`. There is no way to say "only the
    `Videos` folder at the top" with a single name; usually that makes no difference.

## Examples

| You want to leave out | Pattern |
|---|---|
| Your `Videos` folder (and any folder called `Videos`) | `Videos/` |
| Only `~/Downloads/iso` | `Downloads/iso/` |
| All disk images | `*.iso` |
| Every `node_modules` folder | `node_modules/` |
| Virtual machine disks | `*.qcow2`, `*.vdi`, `*.vmdk` |
| Every folder called `cache` (lower case) under `.config` | `.config/**/cache/` |
| A big log file in one place | `Projects/server/app.log` |

## Default exclusions

Deucalion leaves these out by default. You can remove any of them in **Settings** or with
`deucalion exclude remove`, and get them back with **Restore Defaults** or `deucalion exclude reset`:

```text
--8<-- "snippets/cli/exclude-list.txt"
```

| Pattern | What it is |
|---|---|
| `.cache/` | Caches of every program. |
| `.thumbnails/` | Old location of picture thumbnails. |
| `.local/share/Trash/` | The Trash. |
| `.local/share/recently-used.xbel` | The list of recently used files. |
| `.local/share/containers/` | Podman container storage. |
| `.var/app/*/cache/` | Caches of Flatpak apps. |
| `.npm/_cacache/` | npm's download cache. |
| `.config/**/Cache/`, `Code Cache/`, `GPUCache/`, `DawnCache/`, `DawnGraphiteCache/`, `DawnWebGPUCache/`, `GrShaderCache/`, `ShaderCache/`, `CacheStorage/`, `CachedData/`, `CachedExtensionVSIXs/` | Caches of browsers and Electron apps (Chrome, VS Code, Slack…). |

**Always left out** (not in the list, can't be changed): `~/.local/state/deucalion/` (Deucalion's own
working folder) and `~/Deucalion-before-restore/` (the undo folder).

**Optional** (off by default; switches in **Settings → Leave out developer folders**):
`node_modules/`, `__pycache__/`, `.venv/`, `venv/`, `.tox/`, `target/debug/`.

## Related

- [Leave folders out](../tutorials/leave-out.md) · [`deucalion exclude`](../cli/exclude.md)
