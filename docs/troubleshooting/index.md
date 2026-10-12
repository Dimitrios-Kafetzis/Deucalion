# Troubleshooting

Something didn't work? Start here.

1. **Read the message.** Deucalion's messages say what happened and, usually, what to do. Look it up in
   [Messages and what to do](messages.md): each entry explains what it means, why it happens, and the
   exact steps to fix it.
2. **Check the [FAQ](faq.md)** for questions that aren't error messages: odd file names on the drive,
   a slow check, a power cut, a forgotten password.
3. **Look at the log.** Every backup, restore and rebuild writes a log, both on the drive
   (`Deucalion-Backup/.deucalion/logs/`) and on your computer (`~/.local/state/deucalion/logs/`). The
   app's **Open Log** button (after a backup) opens it.
4. **Unexpected error?** If Deucalion says *"Unexpected error: …"*, run the same command again with
   `DEUCALION_DEBUG=1` in front (for example `DEUCALION_DEBUG=1 deucalion backup`) to see the
   details, and [report it](https://github.com/Dimitrios-Kafetzis/Deucalion/issues). A backup never
   changes anything on your computer, even when it fails.

!!! tip "Nothing is lost by trying again"
    Backups only read your computer and never delete anything on the drive; restores keep what they
    replace. Running the same command again after fixing a problem is always safe.
