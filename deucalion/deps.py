"""Check (and install) what Deucalion needs.

Ubuntu packages are installed with apt. VeraCrypt is not in Ubuntu's repositories: its
official .deb is downloaded from VeraCrypt's GitHub releases and installed only if its
signature was made by VeraCrypt's signing key (fingerprint pinned below).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .util import DeucalionError, os_release

VERACRYPT_FINGERPRINT = "5069A233D55A0EEB174A5FC3821ACD02680D16DE"   # VeraCrypt Team, key 0x680D16DE
VERACRYPT_KEY_URLS = ["https://amcrypto.jp/VeraCrypt/VeraCrypt_PGP_public_key.asc",
                      "https://www.idrix.fr/VeraCrypt/VeraCrypt_PGP_public_key.asc"]
VERACRYPT_RELEASES = "https://api.github.com/repos/veracrypt/VeraCrypt/releases/latest"
VERACRYPT_MIN_VERSION = (1, 26, 29)   # never install an older (possibly vulnerable) release


@dataclass
class Dep:
    package: str        # apt package name
    why: str
    check: callable     # returns True when present
    required: bool = True


def _has_cmd(*names: str):
    return lambda: all(shutil.which(n) or os.path.exists(f"/usr/sbin/{n}") or os.path.exists(f"/sbin/{n}")
                       for n in names)


def _has_package(package: str):
    def check():
        r = subprocess.run(["dpkg-query", "-W", "-f", "${db:Status-Abbrev}", package], capture_output=True, text=True)
        return r.returncode == 0 and r.stdout.startswith("ii")
    return check


def _clean_env() -> dict:
    """Some sandboxed terminals (e.g. the VS Code snap) inject GTK settings that break imports."""
    env = dict(os.environ)
    for k in ("GSETTINGS_SCHEMA_DIR", "GTK_PATH", "GTK_EXE_PREFIX", "GIO_MODULE_DIR", "GTK_IM_MODULE_FILE",
              "GDK_PIXBUF_MODULE_FILE", "GDK_PIXBUF_MODULEDIR", "LOCPATH"):
        env.pop(k, None)
    return env


DEPS = [
    Dep("python3-gi", "talking to Ubuntu's disk service and the app", _has_package("python3-gi")),
    Dep("gir1.2-gtk-4.0", "the app window", _has_package("gir1.2-gtk-4.0")),
    Dep("gir1.2-adw-1", "the app's GNOME look", _has_package("gir1.2-adw-1")),
    Dep("udisks2", "preparing, unlocking and mounting drives", _has_cmd("udisksctl")),
    Dep("cryptsetup", "opening encrypted drives", _has_cmd("cryptsetup")),
    Dep("exfatprogs", "creating exFAT drives (readable on Linux, macOS and Windows)", _has_cmd("mkfs.exfat")),
    Dep("pkexec", "asking for the administrator password", _has_cmd("pkexec")),
    Dep("dconf-cli", "saving desktop settings", _has_cmd("dconf")),
    Dep("gnupg", "verifying the VeraCrypt download", _has_cmd("gpg")),
]


def missing_packages() -> list[Dep]:
    return [d for d in DEPS if not d.check()]


def veracrypt_installed() -> bool:
    return bool(shutil.which("veracrypt"))


# ------------------------------------------------------------------------------------------------
# Running privileged commands


def _as_admin(cmd: list[str]) -> list[str]:
    if os.geteuid() == 0:
        return cmd
    if sys.stdin.isatty():
        return ["sudo"] + cmd
    return ["pkexec"] + cmd


def apt_install(packages: list[str], out=print) -> None:
    if not packages:
        return
    out(f"Installing: {' '.join(packages)} (asks for your administrator password)")
    env = dict(os.environ, DEBIAN_FRONTEND="noninteractive")
    if subprocess.run(_as_admin(["apt-get", "install", "-y", "--no-remove", *packages]), env=env).returncode != 0:
        raise DeucalionError(f"Could not install {' '.join(packages)}.")


# ------------------------------------------------------------------------------------------------
# VeraCrypt


def _get(url: str, dest: Path | None = None, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Deucalion"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    if dest is not None:
        dest.write_bytes(data)
    return data


def choose_veracrypt_asset(assets: list[str], ubuntu: str, arch: str) -> str | None:
    """The .deb for this Ubuntu version, or the newest one for an older Ubuntu version."""
    pattern = re.compile(rf"^veracrypt-[\d.]+-Ubuntu-(\d+\.\d+)-{re.escape(arch)}\.deb$")
    candidates = []
    for name in assets:
        m = pattern.match(name)
        if m:
            candidates.append((tuple(int(x) for x in m.group(1).split(".")), name))
    try:
        mine = tuple(int(x) for x in ubuntu.split("."))
    except ValueError:
        return None
    usable = [c for c in candidates if c[0] <= mine]
    return max(usable)[1] if usable else None


def verify_signature(deb: Path, sig: Path, key: Path, workdir: Path) -> None:
    """Raise unless `sig` is a valid signature of `deb` by VeraCrypt's pinned key."""
    home = workdir / "gnupg"
    home.mkdir(mode=0o700)
    env = dict(os.environ, GNUPGHOME=str(home))
    subprocess.run(["gpg", "--batch", "--quiet", "--import", str(key)], env=env, capture_output=True)
    r = subprocess.run(["gpg", "--batch", "--status-fd", "1", "--verify", str(sig), str(deb)],
                       env=env, capture_output=True, text=True)
    status = {line.split()[1] for line in r.stdout.splitlines() if len(line.split()) > 1}
    if r.returncode != 0 or "GOODSIG" not in status or status & {"REVKEYSIG", "EXPKEYSIG", "EXPSIG", "KEYREVOKED",
                                                                 "BADSIG", "ERRSIG"}:
        raise DeucalionError("The VeraCrypt download could not be verified (bad, expired or revoked signature). "
                             "Nothing was installed.")
    for line in r.stdout.splitlines():
        parts = line.split()
        # [GNUPG:] VALIDSIG <sig-key-fpr> <date> <ts> <exp> <ver> <res> <pk-algo> <hash-algo> <class> <primary-fpr>
        if len(parts) >= 3 and parts[1] == "VALIDSIG":
            primary = parts[-1] if len(parts) >= 12 else parts[2]
            if primary.upper() == VERACRYPT_FINGERPRINT and r.returncode == 0:
                return
    raise DeucalionError("The VeraCrypt download could not be verified (bad or missing signature). "
                         "Nothing was installed.")


def install_veracrypt(out=print) -> None:
    osr = os_release()
    if osr.get("ID") != "ubuntu":
        raise DeucalionError(f"Install VeraCrypt yourself on this system (https://veracrypt.io).")
    arch = subprocess.run(["dpkg", "--print-architecture"], capture_output=True, text=True).stdout.strip()
    out("Looking up the latest VeraCrypt release…")
    release = json.loads(_get(VERACRYPT_RELEASES))
    assets = {a["name"]: a["browser_download_url"] for a in release.get("assets", [])}
    name = choose_veracrypt_asset(list(assets), osr.get("VERSION_ID", ""), arch)
    m = re.match(r"^veracrypt-(\d+)\.(\d+)\.(\d+)-", name or "")
    if name and (not m or tuple(int(x) for x in m.groups()) < VERACRYPT_MIN_VERSION):
        raise DeucalionError(f"The VeraCrypt release offered ({name}) is older than expected; nothing was installed.")
    if not name or name + ".sig" not in assets:
        raise DeucalionError(f"No VeraCrypt package for Ubuntu {osr.get('VERSION_ID')} ({arch}).")
    if not assets[name].startswith("https://github.com/veracrypt/VeraCrypt/releases/download/"):
        raise DeucalionError("Unexpected VeraCrypt download location; nothing was installed.")
    with tempfile.TemporaryDirectory(prefix="deucalion-veracrypt-") as tmp:
        work = Path(tmp)
        os.chmod(work, 0o755)  # apt's sandbox user must be able to read the .deb
        deb, sig, key = work / name, work / (name + ".sig"), work / "key.asc"
        out(f"Downloading {name} …")
        _get(assets[name], deb, timeout=600)
        _get(assets[name + ".sig"], sig)
        for url in VERACRYPT_KEY_URLS:
            try:
                _get(url, key)
                break
            except OSError:
                continue
        else:
            raise DeucalionError("Could not download VeraCrypt's signing key; nothing was installed.")
        out(f"Checking the signature (VeraCrypt key {VERACRYPT_FINGERPRINT[-8:]})…")
        verify_signature(deb, sig, key, work)
        os.chmod(deb, 0o644)
        out("Signature OK. Installing VeraCrypt (asks for your administrator password)…")
        env = dict(os.environ, DEBIAN_FRONTEND="noninteractive")
        if subprocess.run(_as_admin(["apt-get", "install", "-y", "--no-remove", str(deb)]), env=env).returncode != 0:
            raise DeucalionError("Installing VeraCrypt failed.")
    if not veracrypt_installed():
        raise DeucalionError("VeraCrypt still seems to be missing after installing it.")


# ------------------------------------------------------------------------------------------------


def report() -> list[tuple[str, bool, str]]:
    rows = [(d.package, d.check(), d.why) for d in DEPS]
    rows.append(("veracrypt", veracrypt_installed(), "VeraCrypt-encrypted drives (optional)"))
    return rows
