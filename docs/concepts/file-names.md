# File names on exFAT

Linux allows almost any character in a file name. exFAT, the filesystem Deucalion uses by default
so that Windows and macOS can read the drive, does not. If you look at your backup with the Files
app (or on Windows or a Mac), a few names look slightly different. **Deucalion always restores the
original names**: the [manifest](manifest.md) remembers them.

## What changes, and how

| On your computer | On an exFAT drive | Why |
|---|---|---|
| `report: final?.txt` | `report： final？.txt` | `: * ? " < > \|` and `\` are not allowed; they are replaced by look-alike characters. |
| `notes.txt` and `Notes.txt` in the same folder | `notes.txt` and `Notes (2).txt` | exFAT doesn't tell upper and lower case apart, so the second one gets a number. |
| `draft.` (ends with a dot) | `draft．` | exFAT drops dots and spaces at the end of a name. |
| `CON.txt`, `aux.log` | `CON＿.txt`, `aux＿.log` | Windows reserves these names. |
| A very long name | shortened, ending with `~` and a short code | exFAT allows at most 255 characters. |

Here is the `Documents` folder of the demo backup, as stored on the drive:

```text
--8<-- "snippets/cli/drive-names.txt"
```

And the same folder as Deucalion shows it, with the original names:

```text
--8<-- "snippets/cli/ls-documents.txt"
```

Names in other alphabets and emoji (`Συνταγές.txt`, `Ταξίδι στην Κρήτη 🌍.md`) are fine on exFAT and
stay exactly the same.

!!! note "Linux-formatted drives keep names as they are"
    On a drive formatted for Linux only (ext4, which Deucalion uses inside LUKS-encrypted drives),
    nothing is renamed. The manifest is still written.

## Related

- [The manifest](manifest.md)
- [FAQ: why do some names look odd on my drive?](../troubleshooting/faq.md#why-do-some-file-names-look-odd-on-my-drive)
