# The manifest

Most backup drives are formatted as **exFAT** (or NTFS), so that Windows and macOS can read them.
These filesystems can't store some details that Linux keeps for every file:

- **permissions**: who may read, change or run a file (for example, your SSH keys must be readable
  only by you);
- **owner and group**;
- **symbolic links** (shortcuts that point to another file or folder);
- **some characters in names** and the **difference between `Notes.txt` and `notes.txt`**.

Deucalion keeps all of this in a small database on the drive, the **manifest**:
`Deucalion-Backup/.deucalion/manifest.sqlite`. For every file and folder in the backup it records:

- its original name and folder;
- where it is stored on the drive (which may be a slightly different name, see
  [File names on exFAT](file-names.md));
- its permissions, owner, group, size and modification time;
- the target of a link;
- a checksum (a fingerprint of its content, SHA-256) that [`verify --full`](../tutorials/verify.md)
  uses to find damaged files.

When you restore, Deucalion reads the manifest and puts every detail back. For example, `~/.ssh`
comes back with its strict permissions, and links are recreated as links.

The manifest also records the history of your backups (shown on the **Overview** page and by
`deucalion status`).

## A copy is kept

After every completed backup, Deucalion saves a copy of the manifest as `manifest.sqlite.bak` next
to it. The manifest is written with the safest settings (every change is written to the drive
before the next one), so it survives a drive that is unplugged or a computer that loses power in the
middle of a backup.

## You don't need it to read your files

The files in the backup are normal files. You can open and copy them without Deucalion and without
the manifest (see [Open your backup without Deucalion](../tutorials/open-without-deucalion.md)). The
manifest is only needed to put back the Linux details exactly.

## Related

- [What is on the drive](../reference/drive-contents.md)
- [File names on exFAT](file-names.md)
