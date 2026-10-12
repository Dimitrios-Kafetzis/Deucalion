# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Dimitrios Kafetzis

import json
import os
import unittest
from pathlib import Path

from deucalion import aptsources, rebuild
from deucalion.backup import ALL, BackupJob, Source
from deucalion.config import Excluder
from deucalion.util import DeucalionError

from helpers import BackupTestCase


class FakePrivileged:
    """Records administrator operations instead of running them."""

    def __init__(self):
        self.calls = []

    def start(self):
        pass

    def call(self, op, on_progress=None, **args):
        self.calls.append((op, args))
        return {"code": 0, "imported": [], "added": args.get("groups", [])}

    def close(self):
        pass


class AptSourcesTest(unittest.TestCase):
    def test_one_line_format_merges_suites_and_components(self):
        text = ("deb http://dell.archive.canonical.com/ noble somerville\n"
                "deb http://dell.archive.canonical.com/ noble somerville-torracat\n"
                "# deb-src ignored\n"
                "deb [arch=amd64 signed-by=/usr/share/keyrings/x.gpg] https://ppa.launchpadcontent.net/a/b/ubuntu noble main\n"
                "deb https://ppa.launchpadcontent.net/a/b/ubuntu noble-updates main\n")
        repos = aptsources.parse(text, "x.list")
        self.assertEqual(len(repos), 3)  # signed-by differs between the two PPA lines
        dell = repos[0]
        self.assertEqual(dell.kind, "oem")
        self.assertEqual(dell.components, ["somerville", "somerville-torracat"])
        self.assertEqual(repos[1].signed_by, "/usr/share/keyrings/x.gpg")
        self.assertEqual(repos[1].options, {"arch": "amd64"})
        self.assertEqual(repos[1].label, "PPA a/b")

    def test_deb822(self):
        text = ("X-Repolib-Name: Google Chrome\nTypes: deb\nURIs: https://dl.google.com/linux/chrome-stable/deb/\n"
                "Suites: stable\nComponents: main\nArchitectures: amd64\nSigned-By: /usr/share/keyrings/google-chrome.gpg\n")
        [r] = aptsources.parse(text, "google-chrome.sources")
        self.assertEqual((r.label, r.suites, r.signed_by, r.kind), ("Google Chrome", ["stable"],
                         "/usr/share/keyrings/google-chrome.gpg", "third-party"))
        again = aptsources.parse(aptsources.render(r, r.suites), "google-chrome.sources")[0]
        self.assertEqual((again.uris, again.suites, again.components, again.signed_by),
                         (r.uris, r.suites, r.components, r.signed_by))

    def test_suite_mapping(self):
        self.assertEqual(aptsources.map_suite("noble", "noble", "resolute"), "resolute")
        self.assertEqual(aptsources.map_suite("noble-security", "noble", "resolute"), "resolute-security")
        self.assertEqual(aptsources.map_suite("stable", "noble", "resolute"), "stable")
        self.assertEqual(aptsources.map_suite("noblex", "noble", "resolute"), "noblex")

    def test_render_list(self):
        [r] = aptsources.parse("deb [signed-by=/k.gpg] https://example.org/apt jammy main contrib\n", "e.list")
        self.assertEqual(aptsources.render(r, ["noble"]), "deb [signed-by=/k.gpg] https://example.org/apt noble main contrib\n")


class RebuildTest(BackupTestCase):
    def backup_with_recipe(self, files: dict[str, str | bytes]):
        recipe = self.tmp / "recipe"
        for rel, data in files.items():
            p = recipe / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data.encode() if isinstance(data, str) else data)
        job = BackupJob(self.cfg, self.target)
        job.sources.append(Source("system", recipe, "recipe", Excluder([])))
        job.scope["system"] = ALL
        try:
            job.execute(job.scan())
        finally:
            job.close()

    def context(self):
        m = self.target.manifest()
        self.addCleanup(m.close)
        self.priv = FakePrivileged()
        return rebuild.Context(self.cfg, self.target, m, privileged=self.priv)

    def info(self, **user):
        return json.dumps({"format": 1, "os": {"codename": "noble", "pretty": "Ubuntu 24.04"},
                           "machine": {"hostname": "old", "arch": os.uname().machine},
                           "user": {"name": "alice", "home": str(self.home), "groups": user.get("groups", [])}})

    def test_paths_step_rewrites_old_home(self):
        self.write(".config/app/settings.json", f'{{"dir": "{self.home}/Projects"}}')
        self.write(".gitconfig", "[user]\n name = A\n")
        self.write("Documents/note.txt", f"{self.home} is mentioned but not a settings file")
        os.symlink(f"{self.home}/Documents", self.home / ".docs-link")
        self.backup_with_recipe({"info.json": self.info()})
        # move to a new machine with another username
        new_home = self.tmp / "home" / "bob"
        new_home.mkdir()
        self.cfg["home_path"] = str(new_home)
        ctx = self.context()
        rebuild.HomeStep().apply(ctx, rebuild.HomeStep().plan(ctx).actionable, out=lambda s: None)
        plan = rebuild.PathsStep().plan(ctx)
        self.assertEqual({i.key for i in plan.items}, {".config/app/settings.json", ".docs-link"})
        rebuild.PathsStep().apply(ctx, plan.items, out=lambda s: None)
        self.assertEqual((new_home / ".config/app/settings.json").read_text(), f'{{"dir": "{new_home}/Projects"}}')
        self.assertEqual(os.readlink(new_home / ".docs-link"), f"{new_home}/Documents")
        self.assertIn(str(self.home), (new_home / "Documents/note.txt").read_text())  # not touched

    def test_system_config_step(self):
        missing = "/etc/udev/rules.d/99-deucalion-test-does-not-exist.rules"
        changed = [
            {"path": missing, "status": "added", "package": "", "mode": 0o644},
            {"path": "/etc/hostname", "status": "installer", "package": "", "mode": 0o644},
            {"path": "/etc/apt/sources.list.d/x.list", "status": "added", "package": "", "mode": 0o644},
            {"path": "/etc/deucalion-test-other.conf", "status": "added", "package": "", "mode": 0o600},
        ]
        self.backup_with_recipe({
            "info.json": self.info(),
            "etc/changed.json": json.dumps(changed),
            f"etc/files{missing}": 'SUBSYSTEM=="tty", MODE="0666"\n',
            "etc/files/etc/hostname": "old\n",
            "etc/files/etc/deucalion-test-other.conf": "x=1\n",
        })
        ctx = self.context()
        plan = rebuild.SystemConfigStep().plan(ctx)
        by_key = {i.key: i for i in plan.items}
        self.assertEqual(set(by_key), {missing, "/etc/deucalion-test-other.conf"})
        self.assertTrue(by_key[missing].selected)                    # safe place, new file
        self.assertFalse(by_key["/etc/deucalion-test-other.conf"].selected)
        self.assertIn("+SUBSYSTEM", rebuild.SystemConfigStep.diff(by_key[missing]))
        rebuild.SystemConfigStep().apply(ctx, [by_key[missing]], out=lambda s: None)
        ops = [c[0] for c in self.priv.calls]
        self.assertEqual(ops, ["put_etc_file", "reload"])
        self.assertEqual(self.priv.calls[0][1]["dest"], missing)
        self.assertEqual(self.priv.calls[1][1]["what"], ["udev"])

    def test_repos_step(self):
        self.backup_with_recipe({
            "info.json": self.info(),
            "packages/apt/sources.list.d/example.sources":
                "Types: deb\nURIs: https://deucalion-test.invalid/apt\nSuites: noble\nComponents: main\n"
                "Signed-By: /usr/share/keyrings/deucalion-test.gpg\n",
            "packages/apt/keys/usr/share/keyrings/deucalion-test.gpg": b"\x99binarykey",
        })
        ctx = self.context()
        ctx.new_codename = "resolute"
        plan = rebuild.ReposStep().plan(ctx)
        [item] = plan.items
        self.assertIn("could not check", item.detail)
        self.assertIn("Suites: resolute", item.data["content"])
        self.assertEqual(item.data["keys"][0]["path"], "/usr/share/keyrings/deucalion-test.gpg")
        rebuild.ReposStep().apply(ctx, [item], out=lambda s: None)
        self.assertEqual([c[0] for c in self.priv.calls], ["apt_add_source", "apt_update"])

    def test_packages_step_reports_unavailable_and_local_debs(self):
        self.write("Downloads/tool_1.0_amd64.deb", b"!<arch>\n")
        self.backup_with_recipe({
            "info.json": self.info(),
            "packages/apt-manual.txt": "deucalion-no-such-package\nlinux-image-generic\n",
            "packages/apt-local.json": json.dumps([
                {"package": "deucalion-test-tool", "version": "1.0", "deb_files": ["Downloads/tool_1.0_amd64.deb"]},
                {"package": "deucalion-test-gone", "version": "2.0", "deb_files": []}]),
            "packages/snaps.json": json.dumps([{"name": "core22", "dependency": True}]),
        })
        ctx = self.context()
        plan = rebuild.PackagesStep().plan(ctx)
        by_key = {i.key: i for i in plan.items}
        self.assertIn("deucalion-no-such-package", by_key["apt:unavailable"].detail)
        self.assertTrue(by_key["deb:deucalion-test-tool"].selectable)
        self.assertFalse(by_key["deb:deucalion-test-gone"].selectable)
        self.assertNotIn("snap:core22", by_key)
        self.assertTrue(any("linux-image-generic" in n for n in plan.notes))

    def test_services_step_groups(self):
        self.backup_with_recipe({"info.json": self.info(groups=["deucalion-no-such-group", "root"])})
        ctx = self.context()
        plan = rebuild.ServicesStep().plan(ctx)
        keys = {i.key for i in plan.items}
        self.assertNotIn("group:deucalion-no-such-group", keys)
        if os.getuid() != 0:
            self.assertIn("group:root", keys)

    def test_state_is_per_backup(self):
        self.backup_with_recipe({"info.json": self.info()})
        state = rebuild.load_state(self.target)
        rebuild.save_state(state, "home", "done", [])
        self.assertEqual(rebuild.load_state(self.target)["steps"]["home"]["status"], "done")


class HelperOpsTest(unittest.TestCase):
    def test_argument_checks(self):
        from deucalion import helper
        with self.assertRaises(helper.OpError):
            helper.op_apt_install(print, packages=["ok", "rm -rf /"])
        with self.assertRaises(helper.OpError):
            helper.op_put_etc_file(print, src="/etc/hostname", dest="/etc/../root/x", mode=0o644,
                                   undo_dir="/var/backups/deucalion/x")
        with self.assertRaises(helper.OpError):
            helper.op_put_etc_file(print, src="/etc/hostname", dest="/etc/shadow", mode=0o644,
                                   undo_dir="/var/backups/deucalion/x")
        with self.assertRaises(helper.OpError):
            helper.op_apt_add_source(print, filename="../evil.list", content="", keys=[])
        with self.assertRaises(helper.OpError):
            helper.op_apt_add_source(print, filename="ok.list", content="", keys=[{"path": "/etc/passwd", "data": ""}])


if __name__ == "__main__":
    unittest.main()
