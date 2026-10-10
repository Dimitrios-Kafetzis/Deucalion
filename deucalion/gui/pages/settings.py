"""Settings: what to leave out, extra folders, backup options."""

from __future__ import annotations

from pathlib import Path

from ..common import Adw, Gio, GLib, Gtk, alert, button, clear, group_add, row
from ...config import DEFAULT_HOME_EXCLUDES, OPTIONAL_EXCLUDES

OPTIONAL_TEXT = {
    "node_modules/": "JavaScript packages (node_modules)",
    "__pycache__/": "Python caches (__pycache__)",
    ".venv/": "Python virtual environments (.venv)",
    "venv/": "Python virtual environments (venv)",
    ".tox/": "Python test environments (.tox)",
    "target/debug/": "Rust debug builds (target/debug)",
}


class SettingsPage:
    def __init__(self, win):
        self.win = win
        self.state = win.state
        page = Adw.PreferencesPage()

        self.options = Adw.PreferencesGroup(title="Backups")
        self.keep = Adw.SwitchRow(title="Keep old versions of changed files",
                                  subtitle="They go to Removed Files instead of being replaced.")
        self.sysrec = Adw.SwitchRow(title="Save system settings with full backups",
                                    subtitle="Apps, repositories, desktop settings, services: needed to rebuild a machine.")
        self.admin = Adw.SwitchRow(title="Include protected system settings",
                                   subtitle="Wi-Fi passwords and administrator-only files. Asks for your password.")
        for w, key in ((self.keep, "keep_overwritten"), (self.sysrec, "system_recipe"), (self.admin, "system_admin")):
            w.connect("notify::active", lambda w, _p, key=key: self._set(key, w.get_active()))
            self.options.add(w)
        page.add(self.options)

        self.dev = Adw.PreferencesGroup(title="Leave out developer folders",
                                        description="They can be recreated, and often hold many small files.")
        self.dev_switches = {}
        for pat in OPTIONAL_EXCLUDES:
            sw = Adw.SwitchRow(title=OPTIONAL_TEXT.get(pat, pat))
            sw.connect("notify::active", lambda w, _p, pat=pat: self._toggle_pattern(pat, w.get_active()))
            self.dev.add(sw)
            self.dev_switches[pat] = sw
        page.add(self.dev)

        self.ex_group = Adw.PreferencesGroup(title="Leave out of backups",
                                             description="Folder/file names (anywhere) or paths from your home folder. "
                                                         "End with / for folders only; * and ** are wildcards.")
        self.ex_group.set_header_suffix(button("Restore Defaults", self._reset, ("flat",)))
        self.add_row = Adw.EntryRow(title="Add a pattern, e.g. Videos/ or *.iso", show_apply_button=True)
        self.add_row.connect("apply", self._add_pattern)
        page.add(self.ex_group)

        self.folders = Adw.PreferencesGroup(title="Extra folders",
                                            description="Folders outside your home folder to back up as well.")
        self.folders.set_header_suffix(button("Add Folder…", self._add_folder, ("flat",), icon="list-add-symbolic"))
        page.add(self.folders)

        self.widget = Adw.ToolbarView()
        hb = Adw.HeaderBar()
        hb.set_title_widget(Adw.WindowTitle(title="Settings"))
        self.widget.add_top_bar(hb)
        self.widget.set_content(page)
        self._loading = False

    def on_show(self):
        self._loading = True
        cfg = self.state.cfg
        self.keep.set_active(cfg.get("keep_overwritten", True))
        self.sysrec.set_active(cfg.get("system_recipe", True))
        self.admin.set_active(cfg.get("system_admin", True))
        ex = cfg.get("home_excludes", [])
        for pat, sw in self.dev_switches.items():
            sw.set_active(pat in ex)
        clear(self.ex_group)
        for pat in ex:
            if pat in OPTIONAL_EXCLUDES:
                continue
            group_add(self.ex_group, row(pat, "default" if pat in DEFAULT_HOME_EXCLUDES else "",
                                         suffix=button("", lambda p=pat: self._toggle_pattern(p, False, True),
                                                       ("flat",), icon="user-trash-symbolic", tooltip="Remove")))
        group_add(self.ex_group, self.add_row)
        clear(self.folders)
        group_add(self.folders, row("Home folder", str(cfg.home) + " (always included)", "user-home-symbolic"))
        for f in cfg.get("extra_folders", []):
            group_add(self.folders, row(f["name"], f["path"], "folder-symbolic",
                                        button("", lambda n=f["name"]: self._remove_folder(n), ("flat",),
                                               icon="user-trash-symbolic", tooltip="Remove")))
        self._loading = False

    def _set(self, key, value):
        if self._loading:
            return
        self.state.cfg[key] = value
        self.state.cfg.save()

    def _toggle_pattern(self, pat, on, refresh=False):
        if self._loading:
            return
        ex = self.state.cfg.setdefault("home_excludes", list(DEFAULT_HOME_EXCLUDES))
        if on and pat not in ex:
            ex.append(pat)
        elif not on and pat in ex:
            ex.remove(pat)
        self.state.cfg.save()
        if refresh:
            self.on_show()

    def _add_pattern(self, entry):
        pat = entry.get_text().strip()
        if pat:
            entry.set_text("")
            self._toggle_pattern(pat, True, refresh=True)

    def _reset(self):
        def go(r):
            if r == "reset":
                self.state.cfg["home_excludes"] = list(DEFAULT_HOME_EXCLUDES)
                self.state.cfg.save()
                self.on_show()

        alert(self.win, "Restore the default exclusions?", "Your own patterns will be removed.",
              (("cancel", "Cancel"), ("reset", "Restore Defaults")), destructive="reset", callback=go)

    def _add_folder(self):
        dialog = Gtk.FileDialog(title="Choose a folder to back up", modal=True)
        dialog.set_initial_folder(Gio.File.new_for_path("/"))

        def done(d, res):
            try:
                path = Path(d.select_folder_finish(res).get_path())
            except GLib.Error:
                return
            cfg = self.state.cfg
            if path == cfg.home or cfg.home in path.parents:
                alert(self.win, "Already included", "That folder is inside your home folder, which is always backed up.")
                return
            name = "".join(c for c in (path.name or "root") if c.isalnum() or c in "._-") or "folder"
            names = {f["name"] for f in cfg.get("extra_folders", [])}
            base, n = name, 2
            while name in names:
                name, n = f"{base}-{n}", n + 1
            cfg.setdefault("extra_folders", []).append({"name": name, "path": str(path), "excludes": []})
            cfg.save()
            self.on_show()

        dialog.select_folder(self.win, None, done)

    def _remove_folder(self, name):
        cfg = self.state.cfg
        cfg["extra_folders"] = [f for f in cfg.get("extra_folders", []) if f["name"] != name]
        cfg.save()
        self.on_show()
