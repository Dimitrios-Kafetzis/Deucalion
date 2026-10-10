"""Restore: browse the backup (original names), pick files/folders, restore them."""

from __future__ import annotations

import threading
from pathlib import Path

from ..common import (Adw, Gio, GLib, Gtk, alert, button, clamp, clear, hbox, label, on_main, open_folder,
                      page_with_header, run_async, scrolled, toast, vbox)
from ...manifest import Entry
from ...restore import Restorer
from ...util import human_duration, human_size, plural

MAX_ROWS = 600


class RestorePage:
    def __init__(self, win):
        self.win = win
        self.state = win.state
        self.manifest = None
        self.manifest_target = None
        self.path = ""                 # current logical folder ('' = top)
        self.selected: set[str] = set()
        self.to_folder: str | None = None
        self.cancel = threading.Event()

        # Browser
        self.crumbs = hbox(4)
        self.search = Gtk.SearchEntry(placeholder_text="Search the backup", hexpand=True)
        self.search.connect("search-changed", lambda *_: self._refresh_list())
        top = vbox(8, children=[self.crumbs, self.search])
        self.listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.listbox.add_css_class("boxed-list")
        self.listbox.connect("row-activated", self._on_row)
        self.note = label("", ("dim-label", "caption"))
        browser = vbox(12, margin=18, children=[top, self.listbox, self.note])

        self.sel_label = label("Nothing selected", ("dim-label",), wrap=False)
        self.dest = Gtk.DropDown.new_from_strings(["To their original place", "To another folder…"])
        self.dest.connect("notify::selected", self._on_dest)
        self.restore_btn = button("Restore…", self._preview, ("suggested-action", "pill"))
        bottom = hbox(12, [self.sel_label, Gtk.Box(hexpand=True), self.dest, self.restore_btn])
        for side in ("top", "bottom", "start", "end"):
            getattr(bottom, f"set_margin_{side}")(10)

        browse_tv = Adw.ToolbarView()
        browse_tv.set_content(scrolled(clamp(browser, 900)))
        browse_tv.add_bottom_bar(bottom)

        self.empty = Adw.StatusPage(icon_name="document-revert-symbolic", title="Nothing to restore yet",
                                    description="Connect (and unlock) your backup drive to browse your backup.")
        # Progress / done
        self.bar = Gtk.ProgressBar()
        self.prog_text = label("", ("dim-label",), xalign=0.5)
        stop = button("Stop", lambda: self.cancel.set(), ("pill", "destructive-action"))
        stop.set_halign(Gtk.Align.CENTER)
        running = clamp(vbox(14, margin=48, children=[label("Restoring…", ("title-1",), xalign=0.5), self.bar,
                                                      self.prog_text, stop]), 640)
        running.set_valign(Gtk.Align.CENTER)
        self.done = Adw.StatusPage()
        self.done_box = vbox(12)
        self.done.set_child(self.done_box)

        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.stack.add_named(browse_tv, "browse")
        self.stack.add_named(self.empty, "empty")
        self.stack.add_named(running, "running")
        self.stack.add_named(scrolled(self.done), "done")
        rebuild = button("Rebuild This Machine…", lambda: win.show_page("rebuild"), ("flat",),
                         icon="system-software-install-symbolic")
        self.widget = page_with_header("Restore", self.stack, header_end=[rebuild])
        self.state.connect("changed", lambda *_: self._on_state())

    # -- state ------------------------------------------------------------------------------------------
    def _on_state(self):
        if self.stack.get_visible_child_name() in ("running", "done"):
            return
        self.on_show()

    def on_show(self):
        if self.stack.get_visible_child_name() in ("running", "done"):
            return
        t = self.state.target
        if t is None:
            self._close_manifest()
            if self.state.status == "locked":
                self.empty.set_child(button("Unlock", lambda: self.win.unlock_drive(), ("pill", "suggested-action")))
            else:
                self.empty.set_child(None)
            self.stack.set_visible_child_name("empty")
            return
        if str(self.manifest_target) != str(t.root):
            self._close_manifest()
            self.manifest = t.manifest()
            self.manifest_target = t.root
            self.path = ""
            self.selected.clear()
        self.stack.set_visible_child_name("browse")
        self._refresh_list()

    def _close_manifest(self):
        if self.manifest is not None:
            self.manifest.close()
        self.manifest = None
        self.manifest_target = None

    # -- browsing -------------------------------------------------------------------------------------
    def _refresh_list(self):
        if self.manifest is None:
            return
        clear(self.listbox)
        clear(self.crumbs)
        text = self.search.get_text().strip()
        if text:
            entries = self.manifest.search(text, MAX_ROWS)
            self.crumbs.append(label(f"Results for “{text}”", ("heading",)))
            self.note.set_label("" if entries else "Nothing found.")
            for e in entries:
                self.listbox.append(self._row(e, show_path=True))
            return
        # breadcrumbs
        parts = [""] + ([p for p in self.path.split("/")] if self.path else [])
        acc = []
        for i, part in enumerate(parts):
            if part:
                acc.append(part)
            target = "/".join(acc)
            b = button("Backup" if not part else part, lambda t=target: self._go(t), ("flat",))
            self.crumbs.append(b)
            if i < len(parts) - 1:
                self.crumbs.append(label("›", ("dim-label",), wrap=False))
        if self.path == "":
            entries = []
            for name, (origin, kind) in self.manifest.sources().items():
                e = self.manifest.get(name)
                if e is not None:
                    entries.append(e)
            self.note.set_label("“home” is your home folder; “system” holds your system settings "
                                "(used by Rebuild).")
        else:
            children = self.manifest.children(self.path)
            entries = sorted(children.values(), key=lambda e: (e.kind != "d", e.name.lower()))
            self.note.set_label("" if len(entries) <= MAX_ROWS else
                                f"Showing {MAX_ROWS:,} of {len(entries):,} items. Use search to find others.")
        for e in entries[:MAX_ROWS]:
            self.listbox.append(self._row(e))
        self._update_selection()

    def _row(self, e: Entry, show_path: bool = False) -> Gtk.Widget:
        if e.kind == "d":
            size, files = self.manifest.tree_totals(e.path)
            sub, icon = f"{plural(files, 'file')} · {human_size(size)}", "folder-symbolic"
        elif e.kind == "l":
            sub, icon = f"link to {e.link}", "emblem-symbolic-link-symbolic"
        else:
            sub, icon = human_size(e.size), "text-x-generic-symbolic"
        if show_path:
            sub = f"{e.parent} · {sub}"
        title = {"home": "Home folder", "system": "System settings"}.get(e.path, e.name)
        r = Adw.ActionRow(title=GLib.markup_escape_text(title), subtitle=GLib.markup_escape_text(sub))
        check = Gtk.CheckButton(active=e.path in self.selected or self._inside_selected(e.path),
                                valign=Gtk.Align.CENTER)
        check.connect("toggled", lambda c, p=e.path: self._toggle(p, c.get_active()))
        r.add_prefix(check)
        r.add_prefix(Gtk.Image(icon_name=icon))
        if e.kind == "d":
            r.add_suffix(Gtk.Image(icon_name="go-next-symbolic"))
            r.set_activatable(True)
        r.logical = e.path
        r.kind = e.kind
        return r

    def _inside_selected(self, path: str) -> bool:
        return any(path.startswith(s + "/") for s in self.selected)

    def _on_row(self, _lb, r):
        if getattr(r, "kind", "") == "d":
            self.search.set_text("")
            self._go(r.logical)

    def _go(self, path: str):
        self.path = path
        self._refresh_list()

    def _toggle(self, path: str, on: bool):
        if on:
            self.selected = {s for s in self.selected if not s.startswith(path + "/")}
            self.selected.add(path)
        else:
            self.selected.discard(path)
        self._update_selection()

    def _update_selection(self):
        n = len(self.selected)
        self.sel_label.set_label("Nothing selected" if not n else f"{n} item{'s' if n > 1 else ''} selected")
        self.restore_btn.set_sensitive(n > 0 and not self.state.busy)

    def _on_dest(self, *_):
        if self.dest.get_selected() != 1:
            self.to_folder = None
            return
        dialog = Gtk.FileDialog(title="Restore into which folder?", modal=True)

        def done(d, res):
            try:
                f = d.select_folder_finish(res)
                self.to_folder = f.get_path()
                toast(self.widget, f"Restoring into {self.to_folder}")
            except GLib.Error:
                self.dest.set_selected(0)

        dialog.select_folder(self.win, None, done)

    # -- restoring ----------------------------------------------------------------------------------------
    def _preview(self):
        items = sorted(self.selected)
        if "system" in items or any(i.startswith("system/") for i in items):
            if self.to_folder is None:
                alert(self.win, "Choose a folder", "System settings are not restored in place. Use Rebuild, or "
                                                   "choose “To another folder…” to look at them.")
                return
        cfg, target = self.state.cfg, self.state.target
        to = Path(self.to_folder) if self.to_folder else None
        restorer = Restorer(cfg, target, self.manifest)
        run_async(lambda: restorer.plan(items, to), lambda plan: self._confirm(restorer, plan))

    def _confirm(self, restorer, plan):
        dest_lines = "\n".join(f"• {d}" for _, d in plan.roots[:5])
        body = (f"{plan.copy_files:,} files ({human_size(plan.copy_bytes)}) will be restored to:\n{dest_lines}\n\n"
                f"New: {plan.count('create') + plan.count('mkdir'):,} · Already the same: {plan.count('same'):,}")
        extra = None
        if plan.count("overwrite"):
            body += (f"\n\n{plan.count('overwrite'):,} files here are different and will be replaced. "
                     "The current versions are kept in “Deucalion-before-restore” in your home folder.")
            lb = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
            lb.add_css_class("boxed-list")
            for it in plan.of("overwrite")[:200]:
                lb.append(Adw.ActionRow(title=GLib.markup_escape_text(str(it.dest))))
            extra = Gtk.ScrolledWindow(min_content_height=160, max_content_height=260, child=lb)
        if plan.count("missing"):
            body += f"\n\n{plan.count('missing'):,} files are missing on the drive and can't be restored."
        if not plan.copy_files and not plan.count("overwrite") and not plan.count("mkdir") and not plan.count("create"):
            alert(self.win, "Nothing to restore", "Everything you selected is already the same here.")
            return
        alert(self.win, "Restore these files?", body, (("cancel", "Cancel"), ("restore", "Restore")),
              suggested="restore", extra=extra, callback=lambda r: self._run(restorer, plan) if r == "restore" else None)

    def _run(self, restorer, plan):
        self.cancel = threading.Event()
        restorer.cancel = self.cancel

        def progress(p):
            frac = p.bytes_done / p.bytes_total if p.bytes_total else 1.0
            text = (f"{human_size(p.bytes_done)} of {human_size(p.bytes_total)}"
                    + (f" · {human_size(p.rate)}/s" if p.rate else "")
                    + (f" · about {human_duration(p.eta)} left" if p.eta else ""))
            on_main(lambda: (self.bar.set_fraction(min(frac, 1)), self.prog_text.set_label(text)))

        restorer.on_progress = progress
        self.state.set_busy(True)
        self.stack.set_visible_child_name("running")
        run_async(lambda: restorer.execute(plan), self._done, self._failed)

    def _failed(self, msg):
        self.state.set_busy(False)
        self.stack.set_visible_child_name("browse")
        alert(self.win, "Restore failed", msg)

    def _done(self, res):
        self.state.set_busy(False)
        ok = res.status == "completed"
        self.done.set_icon_name("emblem-ok-symbolic" if ok else "dialog-warning-symbolic")
        self.done.set_title("Restored" if res.status != "cancelled" else "Restore stopped")
        desc = f"{plural(res.restored_files, 'file')} ({human_size(res.restored_bytes)}) restored."
        if res.undo_dir:
            desc += f"\nThe files that were replaced are kept in {res.undo_dir}."
        self.done.set_description(desc)
        clear(self.done_box)
        buttons = [button("Done", self._back, ("pill", "suggested-action"))]
        if res.undo_dir:
            buttons.insert(0, button("Open Replaced Files", lambda: open_folder(res.undo_dir), ("pill",)))
        self.done_box.append(hbox(12, buttons, halign=Gtk.Align.CENTER))
        if res.warnings:
            g = Adw.PreferencesGroup(title="Warnings")
            for w in res.warnings[:50]:
                g.add(Adw.ActionRow(title=GLib.markup_escape_text(w)))
            self.done_box.append(clamp(g, 700))
        self.stack.set_visible_child_name("done")

    def _back(self):
        self.selected.clear()
        self.stack.set_visible_child_name("browse")
        self._refresh_list()
