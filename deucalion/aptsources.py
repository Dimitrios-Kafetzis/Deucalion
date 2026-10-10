"""Read apt repository definitions (one-line .list and deb822 .sources files),
adapt them to a new Ubuntu release, and check that they still exist."""

from __future__ import annotations

import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field

UBUNTU_HOSTS = re.compile(r"^https?://([a-z0-9-]+\.)*(archive|security|ports|esm)\.ubuntu\.com/", re.I)
OEM_HOSTS = re.compile(r"^https?://([a-z0-9-]+\.)*archive\.canonical\.com/", re.I)
PPA_HOSTS = re.compile(r"^https?://ppa\.(launchpad|launchpadcontent)\.net/", re.I)


@dataclass
class Repo:
    file: str                   # e.g. "google-chrome.sources"
    fmt: str                    # "list" | "deb822"
    types: list[str]
    uris: list[str]
    suites: list[str]
    components: list[str]
    signed_by: str = ""         # key file path ('' if none)
    options: dict = field(default_factory=dict)
    enabled: bool = True
    name: str = ""

    @property
    def kind(self) -> str:
        uri = self.uris[0] if self.uris else ""
        if UBUNTU_HOSTS.match(uri):
            return "ubuntu"
        if OEM_HOSTS.match(uri):
            return "oem"
        if PPA_HOSTS.match(uri):
            return "ppa"
        return "third-party"

    @property
    def label(self) -> str:
        if self.name:
            return self.name
        if self.kind == "ppa":
            m = re.match(r"^https?://[^/]+/([^/]+)/([^/]+)", self.uris[0])
            if m:
                return f"PPA {m.group(1)}/{m.group(2)}"
        return self.file.rsplit(".", 1)[0]


def parse_list(text: str, file: str) -> list[Repo]:
    repos = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        tokens = line.split()
        typ = tokens[0]
        if typ not in ("deb", "deb-src"):
            continue
        rest = tokens[1:]
        opts: dict = {}
        if rest and rest[0].startswith("["):
            opt_tokens = []
            while rest:
                t = rest.pop(0)
                opt_tokens.append(t)
                if t.endswith("]"):
                    break
            for o in " ".join(opt_tokens).strip("[] ").split():
                if "=" in o:
                    k, v = o.split("=", 1)
                    opts[k.lower()] = v
        if len(rest) < 2:
            continue
        uri, suite, comps = rest[0], rest[1], rest[2:]
        signed = opts.pop("signed-by", "")
        repos.append(Repo(file, "list", [typ], [uri], [suite], comps, signed, opts))
    return _merge_list_repos(repos)


def _merge_list_repos(repos: list[Repo]) -> list[Repo]:
    """Lines that only differ in suite (noble, noble-updates…) or component count as one repository."""
    merged: dict[tuple, Repo] = {}
    for r in repos:
        key = (tuple(r.types), r.uris[0], r.signed_by, tuple(sorted(r.options.items())))
        if key in merged:
            m = merged[key]
            m.suites.extend(s for s in r.suites if s not in m.suites)
            m.components.extend(c for c in r.components if c not in m.components)
        else:
            merged[key] = r
    return list(merged.values())


def parse_deb822(text: str, file: str) -> list[Repo]:
    repos = []
    for stanza in re.split(r"\n\s*\n", text):
        fields: dict[str, str] = {}
        key = None
        for line in stanza.splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            if line[0] in " \t" and key:
                fields[key] += "\n" + line.strip()
            elif ":" in line:
                key, value = line.split(":", 1)
                key = key.strip().lower()
                fields[key] = value.strip()
        if "uris" not in fields:
            continue
        signed = fields.get("signed-by", "")
        if "\n" in signed or signed.startswith("-----BEGIN"):
            signed = "(inline key)"
        opts = {k: v for k, v in fields.items()
                if k not in ("types", "uris", "suites", "components", "signed-by", "enabled", "x-repolib-name")}
        repos.append(Repo(file, "deb822", fields.get("types", "deb").split(), fields["uris"].split(),
                          fields.get("suites", "").split(), fields.get("components", "").split(),
                          signed, opts, fields.get("enabled", "yes").lower() != "no",
                          fields.get("x-repolib-name", "")))
    return repos


def parse(text: str, file: str) -> list[Repo]:
    return parse_deb822(text, file) if file.endswith(".sources") else parse_list(text, file)


def map_suite(suite: str, old: str, new: str) -> str:
    """noble -> plucky, noble-updates -> plucky-updates; other suites (stable, main…) unchanged."""
    if old and new and (suite == old or suite.startswith(old + "-")):
        return new + suite[len(old):]
    return suite


def render(repo: Repo, suites: list[str]) -> str:
    """The repository as file content, with the given suites."""
    if repo.fmt == "deb822":
        lines = []
        if repo.name:
            lines.append(f"X-Repolib-Name: {repo.name}")
        lines += [f"Types: {' '.join(repo.types)}", f"URIs: {' '.join(repo.uris)}",
                  f"Suites: {' '.join(suites)}"]
        if repo.components:
            lines.append(f"Components: {' '.join(repo.components)}")
        for k, v in repo.options.items():
            lines.append(f"{k.title()}: {v}")
        if repo.signed_by and repo.signed_by != "(inline key)":
            lines.append(f"Signed-By: {repo.signed_by}")
        if not repo.enabled:
            lines.append("Enabled: no")
        return "\n".join(lines) + "\n"
    opts = dict(repo.options)
    if repo.signed_by:
        opts["signed-by"] = repo.signed_by
    opt_text = f"[{' '.join(f'{k}={v}' for k, v in opts.items())}] " if opts else ""
    out = []
    for typ in repo.types:
        for uri in repo.uris:
            for suite in suites:
                out.append(f"{typ} {opt_text}{uri} {suite} {' '.join(repo.components)}".rstrip())
    return "\n".join(out) + "\n"


def release_url(uri: str, suite: str) -> list[str]:
    base = uri.rstrip("/")
    if suite.endswith("/"):  # flat repository
        prefix = f"{base}/{suite}".rstrip("/")
        return [f"{prefix}/InRelease", f"{prefix}/Release"]
    return [f"{base}/dists/{suite}/InRelease", f"{base}/dists/{suite}/Release"]


def available(uri: str, suite: str, timeout: float = 10) -> bool | None:
    """True if the repository has this suite, False if it doesn't, None if we couldn't tell."""
    unsure = False
    for url in release_url(uri, suite):
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "Deucalion"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                if r.status == 200:
                    return True
        except urllib.error.HTTPError as e:
            if e.code not in (403, 404, 405, 410):
                unsure = True
        except (urllib.error.URLError, OSError, ValueError):
            unsure = True
    return None if unsure else False
