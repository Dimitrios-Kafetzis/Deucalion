# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Dimitrios Kafetzis

"""Check that the backup on the drive is complete and undamaged."""

from __future__ import annotations

import hashlib
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from .backup import CHUNK, Cancelled, Progress
from .manifest import Manifest
from .target import Target


@dataclass
class VerifyResult:
    checked_files: int = 0
    checked_bytes: int = 0
    missing: list[str] = field(default_factory=list)
    wrong_size: list[str] = field(default_factory=list)
    damaged: list[str] = field(default_factory=list)
    cancelled: bool = False

    @property
    def ok(self) -> bool:
        return not (self.missing or self.wrong_size or self.damaged)


def verify(target: Target, manifest: Manifest, full: bool = False,
           on_progress: Callable[[Progress], None] | None = None,
           cancel: threading.Event | None = None) -> VerifyResult:
    """Quick mode checks every file exists with the right size.
    Full mode also re-reads every file and compares its checksum."""
    cancel = cancel or threading.Event()
    total_bytes, total_files = manifest.tree_totals()
    progress = Progress(phase="verify", files_total=total_files, bytes_total=total_bytes if full else 0)
    res = VerifyResult()
    last = 0.0
    try:
        for e in manifest.iter_tree(""):
            if e.kind != "f":
                continue
            if cancel.is_set():
                raise Cancelled()
            path = target.root / e.stored
            progress.current = e.path
            try:
                st = os.stat(path)
            except OSError:
                res.missing.append(e.path)
                continue
            if st.st_size != e.size:
                res.wrong_size.append(e.path)
                continue
            if full and e.sha256:
                h = hashlib.sha256()
                with open(path, "rb") as f:
                    while buf := f.read(CHUNK):
                        if cancel.is_set():
                            raise Cancelled()
                        h.update(buf)
                        progress.bytes_done += len(buf)
                        if on_progress and time.monotonic() - last > 0.1:
                            last = time.monotonic()
                            on_progress(progress)
                if h.hexdigest() != e.sha256:
                    res.damaged.append(e.path)
            res.checked_files += 1
            res.checked_bytes += e.size
            progress.files_done += 1
            if on_progress and time.monotonic() - last > 0.1:
                last = time.monotonic()
                on_progress(progress)
    except Cancelled:
        res.cancelled = True
    # The next backup copies these again.
    for path in res.missing + res.wrong_size + res.damaged:
        manifest.mark_for_recopy(path)
    manifest.commit()
    progress.phase = "done"
    if on_progress:
        on_progress(progress)
    return res
