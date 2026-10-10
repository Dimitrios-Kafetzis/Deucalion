"""File names that are safe to store on exFAT (and readable on Windows/macOS).

The original name is always kept in the manifest, so encoding is only about
what you see when browsing the drive. Characters exFAT rejects are replaced by
look-alike full-width characters, so names stay readable:  a:b  ->  a：b
"""

from __future__ import annotations

import hashlib
import re

# Characters exFAT refuses (verified on the Linux exfat driver).
_SUBSTITUTES = {
    '"': "＂",  # ＂
    "*": "＊",  # ＊
    ":": "：",  # ：
    "<": "＜",  # ＜
    ">": "＞",  # ＞
    "?": "？",  # ？
    "\\": "＼",  # ＼
    "|": "｜",  # ｜
}
_TRAILING = {".": "．", " ": "␠"}  # Linux exFAT silently drops trailing dots
_WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(10)} | {f"LPT{i}" for i in range(10)}

MAX_UNITS = 255  # exFAT limit, counted in UTF-16 code units


def utf16_units(name: str) -> int:
    return len(name.encode("utf-16-le", "surrogatepass")) // 2


def _encode_char(c: str) -> str:
    o = ord(c)
    if c in _SUBSTITUTES:
        return _SUBSTITUTES[c]
    if o < 0x20:
        return chr(0x2400 + o)  # ␀ … ␟ control-picture symbols
    if 0xDC80 <= o <= 0xDCFF:
        return f"%{o - 0xDC00:02X}"  # byte that is not valid UTF-8
    if 0xD800 <= o <= 0xDFFF:
        return "%3F"
    return c


_NEEDS_ENCODING = re.compile(r'[\x00-\x1f"*:<>?\\|\ud800-\udfff]|[. ]\Z')


def exfat_safe(name: str) -> str:
    if _NEEDS_ENCODING.search(name) is None:  # the common case: nothing to change
        out = name
    else:
        out = "".join(_encode_char(c) for c in name)
    # Trailing dots/spaces
    stripped = out.rstrip(". ")
    if stripped != out:
        out = stripped + "".join(_TRAILING[c] for c in out[len(stripped):])
    stem = out.split(".", 1)[0]
    if stem.upper() in _WINDOWS_RESERVED:
        out = stem + "＿" + out[len(stem):]  # CON.txt -> CON＿.txt
    return fit(out)


def fit(name: str, max_units: int = MAX_UNITS) -> str:
    """Shorten a name that is too long, keeping its extension and making it unique."""
    if utf16_units(name) <= max_units:
        return name
    digest = hashlib.sha1(name.encode("utf-8", "surrogatepass")).hexdigest()[:8]
    stem, dot, ext = name.rpartition(".")
    if not dot or not stem or utf16_units(ext) > 20:
        stem, ext = name, ""
    tail = f"~{digest}" + (f".{ext}" if ext else "")
    budget = max_units - utf16_units(tail)
    while utf16_units(stem) > budget:
        stem = stem[:-1]
    return stem + tail


def with_counter(name: str, n: int) -> str:
    """'report.pdf', 2 -> 'report (2).pdf'"""
    stem, dot, ext = name.rpartition(".")
    if not dot or not stem:
        return fit(f"{name} ({n})")
    return fit(f"{stem} ({n}).{ext}")


def fold_exfat(name: str) -> str:
    """Key under which exFAT considers two names equal (it is case-insensitive)."""
    return name.upper()


class NamePolicy:
    """How original names map to names on the drive."""

    def __init__(self, kind: str):
        if kind not in ("exfat", "posix"):
            raise ValueError(kind)
        self.kind = kind

    def encode(self, name: str) -> str:
        return exfat_safe(name) if self.kind == "exfat" else name

    def fold(self, name: str) -> str:
        return fold_exfat(name) if self.kind == "exfat" else name

    def choose(self, name: str, used: set[str]) -> str:
        """Pick a drive name for `name` that does not clash with `used` (folded keys).
        Adds the chosen key to `used`."""
        candidate = self.encode(name)
        n = 2
        while self.fold(candidate) in used:
            candidate = with_counter(self.encode(name), n)
            n += 1
        used.add(self.fold(candidate))
        return candidate
