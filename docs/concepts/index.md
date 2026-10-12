# Understanding Deucalion

You don't need to read this section to use Deucalion, but it explains what happens behind the
buttons, in plain language. Each page is short.

| Page | In one sentence |
|---|---|
| [One copy, and Removed Files](mirror-and-removed.md) | The drive holds one up-to-date copy of your files; old versions go to Removed Files, which only you empty. |
| [The manifest](manifest.md) | A small database on the drive remembers what Linux-only details a plain drive can't store. |
| [File names on exFAT](file-names.md) | Why some names look slightly different on the drive, and why they come back exactly right. |
| [Full and partial backups](full-and-partial.md) | Back up everything, or quickly update a few folders. |
| [The system recipe](system-recipe.md) | A readable description of your apps and settings, saved with every full backup. |
| [What a rebuild restores](rebuild.md) | What Deucalion puts back on a new computer, and what it deliberately leaves alone. |
| [Administrator access](administrator-access.md) | When Deucalion asks for your password, and why that part is kept small. |
| [How your data is protected](safety.md) | The promises Deucalion makes, and how they were tested. |

## The words used on this site

The same words are used everywhere for the same things. The [glossary](../reference/glossary.md)
has the full list. The most important ones:

- **Backup drive**: the external drive (or the part or folder of it) where Deucalion keeps your
  backup.
- **Backup**: the copy of your files on the backup drive, in a folder called `Deucalion-Backup`.
- **Removed Files**: old versions of changed files and files deleted from your computer, kept on the
  drive in a folder called `_removed`.
- **System recipe**: the description of your apps, software sources and settings, saved with full
  backups. The app calls it **system settings**.
- **Undo folder**: `Deucalion-before-restore` in your home folder, where Deucalion keeps anything a
  restore replaced.
- **Lock** and **unlock**: close or open an encrypted backup drive with its password. In the
  terminal, these are `deucalion close` and `deucalion open`.
