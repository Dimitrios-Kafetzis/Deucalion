#!/usr/bin/env python3
"""Runs INSIDE the documentation VM: fills the demo user's home folder with realistic but
fictional files (including the awkward names Deucalion has to handle), and an extra folder
outside the home folder. Everything is generated; the same seed gives the same files."""

from __future__ import annotations

import os
import random
import sys
from pathlib import Path

HOME = Path.home()
rng = random.Random(2026)


def blob(path: str, size: int, mode: int | None = None) -> None:
    p = HOME / path
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "wb") as f:
        left = size
        while left > 0:
            n = min(left, 1 << 20)
            f.write(rng.randbytes(n))
            left -= n
    if mode is not None:
        os.chmod(p, mode)


def text(path: str, content: str, mode: int | None = None) -> None:
    p = HOME / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    if mode is not None:
        os.chmod(p, mode)


def main(big: bool) -> None:
    home = str(HOME)
    # Documents, with names exFAT can't store as they are
    text("Documents/report: final?.txt", "Quarterly report, final version.\n")
    text("Documents/Notes.txt", "Ideas for the garden.\n")
    text("Documents/notes.txt", "Shopping: bread, olives, feta.\n")
    text("Documents/Συνταγές.txt", "Μουσακάς, παστίτσιο, γεμιστά.\n")
    text("Documents/Ταξίδι στην Κρήτη 🌍.md", "# Trip to Crete\n\n- Chania\n- Balos\n")
    blob("Documents/Budget 2026.ods", 46_000)
    blob("Documents/CV - Alex.pdf", 182_000)
    blob("Documents/Work/Quarterly report.docx", 96_000)
    text("Documents/Work/Meeting notes 2026-09.txt", "Agenda: backups, budget, holidays.\n")
    blob("Documents/Tax/2025/receipt-0042.pdf", 61_000)
    blob("Documents/Tax/2025/receipt-0043.pdf", 58_000)
    # Pictures, music, videos: bigger files
    for i in range(1, 25):
        blob(f"Pictures/Holidays 2026/IMG_{i:04d}.jpg", rng.randint(1_800_000, 3_600_000))
    for i in range(1, 9):
        blob(f"Pictures/Family/DSC_{i:04d}.jpg", rng.randint(2_000_000, 4_000_000))
    blob("Pictures/Wallpapers/sunset.png", 1_200_000)
    for i, name in enumerate(["01 Morning.flac", "02 Harbour.flac", "03 Evening.flac"]):
        blob(f"Music/Seaside/{name}", rng.randint(18_000_000, 26_000_000))
    blob("Videos/Birthday 2026.mp4", 260_000_000 if big else 60_000_000)
    blob("Videos/Garden timelapse.mp4", 90_000_000 if big else 20_000_000)
    # Projects: code, plus folders that can be recreated
    text("Projects/website/index.html", "<!doctype html>\n<title>Alex's page</title>\n<h1>Hello</h1>\n")
    text("Projects/website/style.css", "body { font-family: sans-serif; }\n")
    text("Projects/website/package.json", '{ "name": "website", "version": "1.0.0" }\n')
    for i in range(400):
        text(f"Projects/website/node_modules/pkg{i // 20}/lib/file{i}.js", f"module.exports = {i};\n")
    text("Projects/scripts/tool.sh", "#!/bin/sh\necho 'tool'\n", 0o755)
    text("Projects/scripts/backup-photos.sh", "#!/bin/sh\ncp -r ~/Pictures /mnt/nas/\n", 0o755)
    text("Projects/notes-app/app.py", "print('notes')\n")
    for i in range(60):
        blob(f"Projects/notes-app/.venv/lib/python3.12/site-packages/mod{i}.py", 2_000)
    blob("Projects/notes-app/__pycache__/app.cpython-312.pyc", 3_000)
    text("Desktop/todo.txt", "- renew passport\n- back up the laptop\n")
    # Settings files ("dotfiles"), some mentioning the home folder's path
    text(".gitconfig", f"[user]\n\tname = Alex\n\temail = alex@example.com\n[core]\n"
                       f"\texcludesfile = {home}/.gitignore_global\n")
    text(".gitignore_global", "*.swp\n.DS_Store\n")
    text(".ssh/id_ed25519", "-----BEGIN OPENSSH PRIVATE KEY-----\n(demo key, not a real one)\n"
                            "-----END OPENSSH PRIVATE KEY-----\n", 0o600)
    text(".ssh/id_ed25519.pub", "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAdemo alex@alex-laptop\n", 0o644)
    text(".ssh/config", "Host nas\n  HostName 192.168.1.20\n  User alex\n", 0o600)
    os.chmod(HOME / ".ssh", 0o700)
    text(".config/myapp/settings.json", f'{{\n  "projects": "{home}/Projects",\n  "theme": "dark"\n}}\n')
    (HOME / ".local/bin").mkdir(parents=True, exist_ok=True)
    link = HOME / ".local/bin/tool"
    if not link.is_symlink():
        link.symlink_to(f"{home}/Projects/scripts/tool.sh")
    # Things that are left out by default
    blob(".cache/thumbnails/large/0a1b2c.png", 40_000)
    blob(".cache/pip/http/cache.bin", 900_000)
    text(".local/share/Trash/files/old draft.txt", "deleted\n")
    blob(".config/Code/Cache/data_1", 300_000)


if __name__ == "__main__":
    main(big="--big" in sys.argv)
