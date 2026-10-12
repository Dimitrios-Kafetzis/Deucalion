#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Dimitrios Kafetzis
"""Runs INSIDE the documentation VM (see screenshots.py): captures real command output and app
screenshots.

  capture.py cli NAME [--answer 'REGEX=>TEXT' ...] [--show 'deucalion …'] -- COMMAND
      Runs COMMAND in a terminal (so it behaves exactly as when a person types it), answers its
      questions (each answer is typed only after its question appears, so passwords are never
      echoed), and saves the cleaned transcript to OUT/cli/NAME.txt (exit code in NAME.json).
      Answers are rules tried in order on what was printed since the last answer: REGEX=>TEXT is
      used once, REGEX=>>TEXT every time it matches.

  capture.py gui FOLDER --pages 'ENTRIES' [--size 1100x760] [--theme light]
      Renders the app with GTK's Broadway backend (no window on any screen) and saves one PNG per
      entry into OUT/shots/FOLDER/ (entry syntax: deucalion/gui/shots.py).
"""

from __future__ import annotations

import argparse
import json
import os
import pty
import re
import select
import signal
import subprocess
import sys
import time
from pathlib import Path

OUT = Path(os.environ.get("DOCS_OUT", "/var/tmp/docs-out"))  # not in the home folder: it would be backed up
REPO = Path(os.environ.get("DEUCALION_REPO", Path.home() / "Deucalion"))
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07")


def clean(raw: str) -> str:
    """What a person would see in the terminal at the end. A carriage return starts writing over
    the line again (progress lines are redrawn that way); ESC[K erases the rest of the line."""
    lines = []
    for raw_line in raw.replace("\r\n", "\n").split("\n"):
        line = ""
        for part in raw_line.split("\r"):
            text = ANSI.sub("", part)
            line = text + ("" if "\x1b[K" in part else line[len(text):])
        lines.append(line.rstrip())
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def elide(text: str, rules: list[tuple[str, str]]) -> str:
    """Replace the lines between a line matching START and the next line matching END with '…'
    (for long, uninteresting output such as apt's)."""
    lines = text.split("\n")
    for start, end in rules:
        i = next((n for n, l in enumerate(lines) if re.search(start, l)), None)
        if i is None:
            continue
        j = next((n for n in range(i + 1, len(lines)) if re.search(end, lines[n])), None)
        if j is not None and j > i + 1:
            lines[i + 1:j] = ["…"]
    return "\n".join(lines)


APT_LINE = re.compile(r"^\s*(Hit:|Get:|Ign:|Fetched |Reading |Building |Solving |Selecting |Preparing |Unpacking |"
                      r"Setting up |Processing |\(Reading database|Need to get|After this operation|The following |"
                      r"\s+[a-z0-9.+-]+( [a-z0-9.+-]+)*$|\d+ upgraded|Scanning |Running kernel|No services|No containers|"
                      r"No user sessions|No VM guests|User sessions|\* Applying |[a-z0-9_.]+ = |"
                      r"\d{4}-\d\d-\d\dT\S+ INFO |$)")


def elide_apt(text: str) -> str:
    """Replace each run of 4 or more lines of apt/dpkg (and similar tool) output with one '…' line."""
    lines, out, run, lines_after = text.split("\n"), [], [], []

    def flush():
        while run and not run[-1].strip():  # blank lines after a run belong to what follows
            lines_after.append(run.pop())
        if len(run) >= 4:
            indent = run[0][:len(run[0]) - len(run[0].lstrip())] or "    "
            out.append(indent + "…")
        else:
            out.extend(run)
        run.clear()
        out.extend(reversed(lines_after))
        lines_after.clear()

    for line in lines:
        if (line.startswith("    ") and APT_LINE.match(line)) or (run and not line.strip()):
            run.append(line)
        else:
            flush()
            out.append(line)
    flush()
    return "\n".join(out)


def run_cli(name: str, command: str, answers: list[tuple[str, str]], show: str, timeout: float,
            elisions: list[tuple[str, str]] = (), apt: bool = False) -> int:
    env = dict(os.environ, NO_COLOR="1", COLUMNS="100", LINES="40", TERM="xterm-256color", LANG="C.UTF-8")
    pid, fd = pty.fork()
    if pid == 0:
        os.execvpe("bash", ["bash", "-lc", command], env)
    # a 100-column terminal
    import fcntl
    import struct
    import termios
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 100, 0, 0))
    buf = b""
    pos = 0          # answers look only at what was printed after the last answer
    pending = list(answers)   # [(regex, text, reusable)] tried in order; a used one-time rule is dropped
    end = time.monotonic() + timeout
    while True:
        if time.monotonic() > end:
            os.kill(pid, signal.SIGKILL)
            buf += b"\n[capture: timed out]\n"
            break
        r, _, _ = select.select([fd], [], [], 0.2)
        if r:
            try:
                data = os.read(fd, 65536)
            except OSError:
                break
            if not data:
                break
            buf += data
            continue  # read everything that is ready before answering
        new_text = buf[pos:].decode("utf-8", "replace")
        for n, (rx, text, reusable) in enumerate(pending):
            if re.search(rx, new_text):
                time.sleep(0.4)  # let the program finish printing its question (and turn echo off)
                os.write(fd, text.encode() + b"\r")
                pos = len(buf)
                if not reusable:
                    pending.pop(n)
                break
    _, status = os.waitpid(pid, 0)
    code = os.waitstatus_to_exitcode(status)
    body = elide(clean(buf.decode("utf-8", "replace")), list(elisions))
    transcript = f"$ {show or command}\n" + (elide_apt(body) if apt else body)
    (OUT / "cli").mkdir(parents=True, exist_ok=True)
    (OUT / "cli" / f"{name}.txt").write_text(transcript + "\n")
    (OUT / "cli" / f"{name}.json").write_text(json.dumps({"command": show or command, "exit": code,
                                                          "unanswered": [a[0] for a in pending if not a[2]]}) + "\n")
    print(transcript)
    print(f"[exit {code}]")
    return code


def run_gui(folder: str, pages: str, size: str, theme: str, wait: int) -> int:
    out = OUT / "shots" / folder
    out.mkdir(parents=True, exist_ok=True)
    display = "7"
    broadway = subprocess.Popen(["gtk4-broadwayd", f":{display}"], stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
    time.sleep(1)
    env = dict(os.environ, GDK_BACKEND="broadway", BROADWAY_DISPLAY=f":{display}",
               DEUCALION_SCREENSHOT_DIR=str(out), DEUCALION_SCREENSHOT_PAGES=pages,
               DEUCALION_SCREENSHOT_SIZE=size, DEUCALION_SCREENSHOT_THEME=theme,
               DEUCALION_SCREENSHOT_WAIT=str(wait), NO_AT_BRIDGE="1")
    env.pop("DISPLAY", None)
    env.pop("WAYLAND_DISPLAY", None)
    try:
        r = subprocess.run([sys.executable, str(REPO / "bin" / "deucalion"), "gui"], env=env, timeout=900)
        return r.returncode
    finally:
        broadway.terminate()
        broadway.wait()


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="what", required=True)
    c = sub.add_parser("cli")
    c.add_argument("name")
    c.add_argument("--answer", action="append", default=[], help="REGEX=>TEXT")
    c.add_argument("--show", default="", help="the command as shown in the docs")
    c.add_argument("--timeout", type=float, default=1800)
    c.add_argument("--elide", action="append", default=[], help="START_REGEX=>END_REGEX")
    c.add_argument("--elide-apt", action="store_true", help="shorten apt/dpkg output to one '…' line")
    g = sub.add_parser("gui")
    g.add_argument("folder")
    g.add_argument("--pages", required=True)
    g.add_argument("--size", default="1024x760")
    g.add_argument("--theme", default="light")
    g.add_argument("--wait", type=int, default=1500)
    argv = sys.argv[1:]
    cmd = []
    if "--" in argv:  # cli NAME [options] -- COMMAND...
        i = argv.index("--")
        argv, cmd = argv[:i], argv[i + 1:]
    a = ap.parse_args(argv)
    if a.what == "cli":
        answers = []
        for x in a.answer:  # REGEX=>TEXT (once) or REGEX=>>TEXT (every time it matches)
            rx, _, text = x.partition("=>")
            answers.append((rx, text[1:], True) if text.startswith(">") else (rx, text, False))
        return run_cli(a.name, " ".join(cmd), answers, a.show, a.timeout,
                       [tuple(x.split("=>", 1)) for x in a.elide], a.elide_apt)
    return run_gui(a.folder, a.pages, a.size, a.theme, a.wait)


if __name__ == "__main__":
    sys.exit(main())
