$ cat "/media/alex/Photos/READ-ME-FIRST.txt"
DEUCALION BACKUP DRIVE
======================

This drive holds a backup made with Deucalion 0.2.0
(https://github.com/Dimitrios-Kafetzis/Deucalion).

Your backup is inside the encrypted file Deucalion-Backup.hc on this drive.
It opens as a normal folder after you enter its password.

Opening the backup
------------------
Linux (Ubuntu):
  Run:  Deucalion-Tool/bin/deucalion open
  or use VeraCrypt: Select File → Deucalion-Backup.hc → Mount.

macOS:
  Install VeraCrypt (and macFUSE) from https://www.veracrypt.fr/en/Downloads.html,
  then Select File → Deucalion-Backup.hc → Mount.

Windows:
  Install VeraCrypt from https://www.veracrypt.fr/en/Downloads.html,
  then Select File → Deucalion-Backup.hc → Mount.

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
