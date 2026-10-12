$ cat "/media/alex/Spare/READ-ME-FIRST.txt"
DEUCALION BACKUP DRIVE
======================

This drive holds a backup made with Deucalion 0.2.0
(https://github.com/Dimitrios-Kafetzis/Deucalion).

Your backup is the folder Deucalion-Backup. Your files are in Deucalion-Backup/home as
normal files and folders: you can open and copy them directly.

Opening the backup
------------------
Linux (Ubuntu):
  Just open the drive in the Files app.

macOS:
  Just open the drive in Finder (exFAT and NTFS drives are readable on macOS).

Windows:
  Just open the drive in File Explorer.

Restoring files or rebuilding a machine (Ubuntu)
------------------------------------------------
  1. Plug in the drive.
  2. Open a terminal in the Deucalion-Tool folder on this drive and run:
       bin/deucalion register <the backup folder>   (only the first time on a new machine)
       bin/deucalion rebuild                        rebuild a whole machine, step by step
       bin/deucalion restore ~/Documents            restore single folders or files

Notes
-----
- Never format this drive or rename the Deucalion-Backup folder.
- Deucalion-Backup/_removed holds older versions and deleted files; empty it with
  'deucalion removed empty' when you need space.
