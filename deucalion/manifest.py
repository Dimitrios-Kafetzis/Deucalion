"""The manifest: a SQLite database on the drive that records, for every backed-up
item, its original name and Linux metadata (permissions, owner, symlink target,
timestamps, checksum) and where it is stored on the drive.

Paths are "logical": original names, relative to the backup root, e.g.
"home/Documents/report.pdf". They are stored as raw bytes so that any Linux
file name (even one that is not valid UTF-8) round-trips exactly.
"""

from __future__ import annotations

import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS sources (
    name   TEXT PRIMARY KEY,   -- logical prefix, e.g. 'home' or 'extras/srv'
    origin TEXT NOT NULL,      -- folder on the machine it came from
    kind   TEXT NOT NULL       -- 'home' or 'folder'
);
CREATE TABLE IF NOT EXISTS entries (
    path     BLOB PRIMARY KEY, -- logical path (original names)
    parent   BLOB NOT NULL,
    stored   BLOB NOT NULL,    -- path on the drive, relative to the backup root ('' for symlinks)
    kind     TEXT NOT NULL,    -- 'f' file, 'd' directory, 'l' symlink
    mode     INTEGER,
    uid      INTEGER,
    gid      INTEGER,
    owner    TEXT,
    grp      TEXT,
    size     INTEGER,
    mtime_ns INTEGER,
    link     BLOB,
    sha256   TEXT
);
CREATE INDEX IF NOT EXISTS entries_parent ON entries(parent);
CREATE TABLE IF NOT EXISTS runs (
    id       INTEGER PRIMARY KEY,
    kind     TEXT,
    started  TEXT,
    finished TEXT,
    status   TEXT,
    scope    TEXT,
    stats    TEXT
);
"""


def _b(s: str) -> bytes:
    return os.fsencode(s)


def _s(b: bytes | None) -> str | None:
    return None if b is None else os.fsdecode(b)


@dataclass(slots=True)
class Entry:
    path: str
    stored: str
    kind: str
    mode: int = 0
    uid: int = 0
    gid: int = 0
    owner: str = ""
    grp: str = ""
    size: int = 0
    mtime_ns: int = 0
    link: str | None = None
    sha256: str | None = None

    @property
    def name(self) -> str:
        return self.path.rsplit("/", 1)[-1]

    @property
    def parent(self) -> str:
        return self.path.rsplit("/", 1)[0] if "/" in self.path else ""


_COLS = "path, stored, kind, mode, uid, gid, owner, grp, size, mtime_ns, link, sha256"


def _row_to_entry(r) -> Entry:
    return Entry(_s(r[0]), _s(r[1]), r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], _s(r[10]), r[11])


def _subtree_bounds(path: str) -> tuple[bytes, bytes]:
    p = _b(path)
    return p + b"/", p + b"0"  # '0' is the byte after '/'


class Manifest:
    def __init__(self, path: Path):
        self.path = path
        self.db = sqlite3.connect(str(path), isolation_level="DEFERRED", check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=DELETE")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self.db.execute("PRAGMA cache_size=-131072")  # 128 MB: fewer reads from slow USB drives
        self.db.executescript(_SCHEMA)
        if self.get_meta("schema") is None:
            self.set_meta("schema", str(SCHEMA_VERSION))
        self.db.commit()
        self._last_commit = time.monotonic()
        self._pending = 0

    # -- meta / sources -------------------------------------------------------
    def get_meta(self, key: str) -> str | None:
        r = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return r[0] if r else None

    def set_meta(self, key: str, value: str) -> None:
        self.db.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (key, value))

    def set_source(self, name: str, origin: str, kind: str) -> None:
        self.db.execute("INSERT OR REPLACE INTO sources VALUES (?, ?, ?)", (name, origin, kind))

    def sources(self) -> dict[str, tuple[str, str]]:
        return {n: (o, k) for n, o, k in self.db.execute("SELECT name, origin, kind FROM sources")}

    # -- entries ----------------------------------------------------------------
    def get(self, path: str) -> Entry | None:
        r = self.db.execute(f"SELECT {_COLS} FROM entries WHERE path=?", (_b(path),)).fetchone()
        return _row_to_entry(r) if r else None

    def children(self, parent: str) -> dict[str, Entry]:
        rows = self.db.execute(f"SELECT {_COLS} FROM entries WHERE parent=?", (_b(parent),))
        out = {}
        for r in rows:
            e = _row_to_entry(r)
            out[e.name] = e
        return out

    def put(self, e: Entry) -> None:
        self.db.execute(
            f"INSERT OR REPLACE INTO entries (parent, {_COLS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (_b(e.parent), _b(e.path), _b(e.stored), e.kind, e.mode, e.uid, e.gid, e.owner, e.grp,
             e.size, e.mtime_ns, None if e.link is None else _b(e.link), e.sha256),
        )
        self._tick()

    def mark_for_recopy(self, path: str) -> None:
        """Make the next backup copy this file again (used when the drive copy is missing/damaged)."""
        self.db.execute("UPDATE entries SET mtime_ns=-1 WHERE path=?", (_b(path),))
        self._tick()

    def delete_tree(self, path: str) -> None:
        lo, hi = _subtree_bounds(path)
        self.db.execute("DELETE FROM entries WHERE path=? OR (path>=? AND path<?)", (_b(path), lo, hi))
        self._tick()

    def iter_tree(self, path: str):
        """The entry at `path` and everything below it, parents before children."""
        if path == "":
            rows = self.db.execute(f"SELECT {_COLS} FROM entries ORDER BY path")
        else:
            lo, hi = _subtree_bounds(path)
            rows = self.db.execute(
                f"SELECT {_COLS} FROM entries WHERE path=? OR (path>=? AND path<?) ORDER BY path",
                (_b(path), lo, hi))
        for r in rows:
            yield _row_to_entry(r)

    def tree_totals(self, path: str = "") -> tuple[int, int]:
        """(bytes, files) below path."""
        if path == "":
            r = self.db.execute("SELECT COALESCE(SUM(size),0), COUNT(*) FROM entries WHERE kind='f'").fetchone()
        else:
            lo, hi = _subtree_bounds(path)
            r = self.db.execute(
                "SELECT COALESCE(SUM(size),0), COUNT(*) FROM entries WHERE kind='f' AND (path=? OR (path>=? AND path<?))",
                (_b(path), lo, hi)).fetchone()
        return r[0], r[1]

    # -- runs ---------------------------------------------------------------------
    def start_run(self, kind: str, started: str, scope: str) -> int:
        cur = self.db.execute("INSERT INTO runs (kind, started, status, scope) VALUES (?,?,?,?)",
                              (kind, started, "running", scope))
        self.commit()
        return cur.lastrowid

    def finish_run(self, run_id: int, finished: str, status: str, stats: str) -> None:
        self.db.execute("UPDATE runs SET finished=?, status=?, stats=? WHERE id=?",
                        (finished, status, stats, run_id))
        self.commit()

    def last_runs(self, n: int = 10) -> list[tuple]:
        return self.db.execute(
            "SELECT id, kind, started, finished, status, scope, stats FROM runs ORDER BY id DESC LIMIT ?",
            (n,)).fetchall()

    # -- transactions -------------------------------------------------------------
    def _tick(self) -> None:
        self._pending += 1
        if self._pending >= 2000 or time.monotonic() - self._last_commit > 2:
            self.commit()

    def commit(self) -> None:
        self.db.commit()
        self._pending = 0
        self._last_commit = time.monotonic()

    def close(self) -> None:
        self.commit()
        self.db.close()
