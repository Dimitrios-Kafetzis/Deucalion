$ cat "/media/alex/Alex Backup1/READ-ME-FIRST.txt"
DEUCALION BACKUP DRIVE
======================

This drive holds a backup made with Deucalion 0.2.0
(https://github.com/Dimitrios-Kafetzis/Deucalion).

Your backup is on the encrypted second part (partition) of this drive.
This normal part only holds this file and the Deucalion tool.

Opening the backup
------------------
Linux (Ubuntu):
  Run:  Deucalion-Tool/bin/deucalion open
  or use VeraCrypt: Select Device → the drive's second partition → Mount.

macOS:
  Install VeraCrypt (and macFUSE) from https://www.veracrypt.fr/en/Downloads.html,
  then Select Device → the drive's second partition → Mount.

Windows:
  Install VeraCrypt from https://www.veracrypt.fr/en/Downloads.html,
  then Select Device → the drive's second partition → Mount.
  If Windows says a drive needs formatting, choose Cancel: never format it.

Restoring files or rebuilding a machine (Ubuntu)
------------------------------------------------
  1. Run Deucalion-Tool/bin/deucalion open and enter the backup password.
  2. Open a terminal in the Deucalion-Tool folder on this drive and run:
       bin/deucalion register <the backup folder>   (only the first time on a new machine)
       bin/deucalion rebuild                        rebuild a whole machine, step by step
       bin/deucalion restore ~/Documents            restore single folders or files

Notes
-----
- Never format this drive or rename the Deucalion-Backup folder.
- Deucalion-Backup/_removed holds older versions and deleted files; empty it with
  'deucalion removed empty' when you need space.
