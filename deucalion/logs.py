"""Per-run log files, written both on the drive and on this machine."""

from __future__ import annotations

import logging
from pathlib import Path

from .config import state_dir
from .target import Target
from .util import run_stamp


def open_run_log(target: Target, kind: str) -> tuple[logging.Logger, list[Path]]:
    stamp = run_stamp()
    logger = logging.getLogger(f"deucalion.run.{kind}.{stamp}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    paths = []
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    for d in (target.logs_dir, state_dir() / "logs"):
        try:
            d.mkdir(parents=True, exist_ok=True)
            p = d / f"{stamp}-{kind}.log"
            h = logging.FileHandler(p, encoding="utf-8", errors="backslashreplace")
            h.setFormatter(fmt)
            logger.addHandler(h)
            paths.append(p)
        except OSError:
            pass
    return logger, paths


def close_run_log(logger: logging.Logger) -> None:
    for h in list(logger.handlers):
        h.close()
        logger.removeHandler(h)
