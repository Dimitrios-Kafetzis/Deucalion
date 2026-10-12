# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Dimitrios Kafetzis

"""Removed Files: old versions and deleted files kept on the drive, until the user empties them."""

from __future__ import annotations

from ..common import (Adw, GLib, Gtk, alert, button, clear, group_add, label, open_folder, page_with_header, row,
                      run_async, stamp_to_text, toast)
from ...util import human_size, plural


class RemovedPage:
    def __init__(self, win):
        self.win = win
        self.state = win.state
        self.checks: dict[str, Gtk.CheckButton] = {}
        self.group = Adw.PreferencesGroup(
            title="Kept on the backup drive",
            description="When a file changes or is deleted on this computer, the backup keeps the old copy here "
                        "instead of deleting it. Nothing here is removed until you empty it.")
        page = Adw.PreferencesPage()
        page.add(self.group)
        self.total = label("", ("dim-label",))
        self.open_btn = button("Open Folder", self._open, ("flat",), icon="folder-open-symbolic")
        self.delete_btn = button("Delete Selected…", self._delete, ("destructive-action",))
        self.empty = Adw.StatusPage(icon_name="user-trash-symbolic", title="Nothing here",
                                    description="Old versions and deleted files will appear here after backups.")
        self.stack = Gtk.Stack()
        self.stack.add_named(page, "list")
        self.stack.add_named(self.empty, "empty")
        self.widget = page_with_header("Removed Files", self.stack, header_end=[self.delete_btn, self.open_btn])
        self.state.connect("changed", lambda *_: self.on_show())

    def on_show(self):
        t = self.state.target
        if t is None:
            self.empty.set_title("Backup drive not available")
            self.empty.set_description("Connect (and unlock) your backup drive.")
            self.stack.set_visible_child_name("empty")
            self.delete_btn.set_visible(False)
            self.open_btn.set_visible(False)
            return
        run_async(t.removed_batches, self._fill)

    def _fill(self, batches):
        clear(self.group)
        self.checks.clear()
        has = bool(batches)
        self.delete_btn.set_visible(has)
        self.open_btn.set_visible(has)
        if not has:
            self.empty.set_title("Nothing here")
            self.empty.set_description("Old versions and deleted files will appear here after backups.")
            self.stack.set_visible_child_name("empty")
            return
        total = sum(b[1] for b in batches)
        self.group.set_title(f"Kept on the backup drive · {human_size(total)}")
        for name, size, files in reversed(batches):
            c = Gtk.CheckButton(valign=Gtk.Align.CENTER)
            c.connect("toggled", lambda *_: self._update())
            r = row(f"From the backup of {stamp_to_text(name)}", f"{plural(files, 'file')} · {human_size(size)}",
                    activatable=True)
            r.add_prefix(c)
            r.set_activatable_widget(c)
            r.add_suffix(button("", lambda n=name: open_folder(self.state.target.removed_root / n), ("flat",),
                                icon="folder-open-symbolic", tooltip="Open"))
            self.checks[name] = c
            group_add(self.group, r)
        self._update()
        self.stack.set_visible_child_name("list")

    # Screenshot mode only (the documentation). The list loads in the background each time the page is
    # shown, so these wait for it before ticking.
    def screenshot_tick(self, n: str = "1", then=None):
        """Tick the first N groups (newest first, as shown)."""
        def tick():
            for c in list(self.checks.values())[:int(n)]:
                c.set_active(True)
            if then:
                then()
            return False
        GLib.timeout_add(1500, tick)

    def screenshot_delete(self, n: str = "1"):
        self.screenshot_tick(n, then=self._delete)

    def _update(self):
        self.delete_btn.set_sensitive(any(c.get_active() for c in self.checks.values()))

    def _open(self):
        if self.state.target:
            open_folder(self.state.target.removed_root)

    def _delete(self):
        names = [n for n, c in self.checks.items() if c.get_active()]
        target = self.state.target

        def go(r):
            if r != "delete":
                return

            def work():
                with target.lock():
                    return target.empty_removed(names)

            run_async(work, lambda freed: (toast(self.widget, f"Freed {human_size(freed)}"), self.on_show()))

        alert(self.win, "Delete permanently?", f"{len(names)} group(s) of old and deleted files will be deleted from "
                                               "the backup drive. This can't be undone.",
              (("cancel", "Cancel"), ("delete", "Delete")), destructive="delete", callback=go)
