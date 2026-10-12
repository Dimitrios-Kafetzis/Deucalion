# Full and partial backups

## Full backup

A **full backup** (the app's **Everything** choice, or `deucalion backup` with no folders) copies:

- your whole **home folder**, except what is [left out](../reference/exclusion-patterns.md) (caches,
  the Trash and similar, by default);
- any **extra folders** you added outside your home folder (see
  [Back up a folder outside your home](../tutorials/outside-home.md));
- the **[system recipe](system-recipe.md)**, unless you turned it off.

Only files that are new or changed are actually copied. Files that are gone from your computer move
to [Removed Files](mirror-and-removed.md).

The date of your last full backup is shown on the **Overview** page. If it is 7 days old or more,
the app reminds you with a bar at the top of the **Overview** page.

## Partial backup

A **partial backup** (the app's **Only some folders**, or `deucalion backup --only …`) updates only
the folders or files you choose. It is quick, for example to update `~/Documents` before you leave.

- Only what you chose is compared and copied.
- **Everything else in the backup is left exactly as it was**: a partial backup never moves anything
  outside your selection to Removed Files. Inside the folders you chose, it works like a full
  backup: files you deleted there do move to Removed Files.
- The system recipe is not saved.
- You can choose folders in your home folder or in an extra folder you added. Other places are
  refused: *"… is not inside your home folder or a configured extra folder."*

If you often back up the same folders, save them as a **profile** in the terminal
(`deucalion profile add work ~/Projects ~/Documents/Work`) and use it with
`deucalion backup --profile work`. See [Save and use a profile](../tutorials/profiles.md). Profiles
are only available on the command line.

!!! tip "A rebuild needs a full backup"
    A rebuild uses the system recipe, which only full backups save. Back up **Everything** regularly,
    and always before you move to a new computer.

## Related

- [Make a full backup](../tutorials/full-backup.md)
- [Back up only some folders](../tutorials/some-folders.md)
