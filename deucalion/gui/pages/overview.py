"""Overview: the backup drive at a glance and a big 'Back Up Now' button."""

from __future__ import annotations

import datetime as _dt
import json

from ..common import (Adw, Gtk, button, clamp, clear, group_add, hbox, label, page_with_header, row, run_async,
                      scrolled, vbox, when)
from ...util import human_size

STATUS_ICON = {"completed": ("emblem-ok-symbolic", "status-ok"),
               "completed_with_warnings": ("dialog-warning-symbolic", "status-warn"),
               "cancelled": ("media-playback-stop-symbolic", "status-warn"),
               "failed": ("dialog-error-symbolic", "status-error"),
               "running": ("content-loading-symbolic", "status-warn")}
STATUS_TEXT = {"completed": "Completed", "completed_with_warnings": "Completed with warnings",
               "cancelled": "Stopped", "failed": "Failed", "running": "Interrupted"}


class OverviewPage:
    def __init__(self, win):
        self.win = win
        self.state = win.state

        self.banner = Adw.Banner(button_label="Back Up Now")
        self.banner.connect("button-clicked", lambda *_: win.show_page("backup"))

        # Hero
        self.hero_icon = Gtk.Image(pixel_size=96)
        self.hero_icon.add_css_class("hero-icon")
        self.hero_title = label("", ("hero-title",), xalign=0.5)
        self.hero_sub = label("", ("dim-label",), xalign=0.5)
        self.hero_buttons = hbox(12, halign=Gtk.Align.CENTER)
        hero = vbox(10, children=[self.hero_icon, self.hero_title, self.hero_sub, self.hero_buttons])
        hero.set_margin_top(24)
        hero.set_margin_bottom(12)

        # Stat cards
        self.cards = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=3,
                                 min_children_per_line=1, column_spacing=12, row_spacing=12, homogeneous=True)

        self.recent = Adw.PreferencesGroup(title="Recent activity")
        body = vbox(24, margin=24, children=[hero, self.cards, self.recent])
        content = vbox(0, children=[self.banner, scrolled(clamp(body, 860))])
        self.widget = page_with_header("Overview", content, header_end=[
            button("", lambda: self.state.refresh(), icon="view-refresh-symbolic", tooltip="Check the drive again")])
        self.state.connect("changed", lambda *_: self.update())

    def on_show(self):
        self.update()

    def _card(self, title: str, value: str, detail: str) -> Gtk.Widget:
        box = vbox(4, children=[label(title, ("stat-title",)), label(value, ("big-number",)),
                                label(detail, ("dim-label", "caption"))])
        box.add_css_class("card")
        box.add_css_class("stat-card")
        return box

    def update(self):
        s = self.state
        clear(self.hero_buttons)
        clear(self.cards)
        clear(self.recent)
        self.banner.set_revealed(False)
        name = s.target_name
        if s.status == "none":
            self.hero_icon.set_from_icon_name("drive-harddisk-symbolic")
            self.hero_title.set_label("Welcome to Deucalion")
            self.hero_sub.set_label("Back up everything on this computer to an external drive, and rebuild "
                                    "it later on a new machine or a new Ubuntu version.\nStart by choosing a drive.")
            self.hero_buttons.append(button("Set Up a Backup Drive", lambda: self.win.page("drives").start_setup(),
                                            ("suggested-action", "pill", "pill-big")))
            self.recent.set_visible(False)
            return
        if s.status == "disconnected":
            self.hero_icon.set_from_icon_name("drive-harddisk-symbolic")
            self.hero_title.set_label(f"“{name}” is not connected")
            self.hero_sub.set_label("Plug in your backup drive to back up or restore.")
            self.hero_buttons.append(button("Choose Another Drive", lambda: self.win.show_page("drives"), ("pill",)))
        elif s.status == "locked":
            self.hero_icon.set_from_icon_name("changes-prevent-symbolic")
            self.hero_title.set_label(f"“{name}” is locked")
            self.hero_sub.set_label("Your backup drive is encrypted. Unlock it with its password.")
            self.hero_buttons.append(button("Unlock", lambda: self.win.unlock_drive(),
                                            ("suggested-action", "pill", "pill-big")))
        else:
            self.hero_icon.set_from_icon_name("drive-harddisk-symbolic")
            self.hero_title.set_label(name)
            self.hero_sub.set_label(f"Ready · {s.free_text()}")
            self.hero_buttons.append(button("Back Up Now", lambda: self.win.page("backup").start_full(),
                                            ("suggested-action", "pill", "pill-big"), icon="document-save-symbolic"))
            self.hero_buttons.append(button("Restore…", lambda: self.win.show_page("restore"), ("pill", "pill-big")))
        self.recent.set_visible(s.target is not None)
        if s.target is None:
            return
        target = s.target
        run_async(lambda: self._load(target), self._show_stats)

    @staticmethod
    def _load(target):
        summary = target.read_summary()
        m = target.manifest()
        try:
            size, files = m.tree_totals()
            runs = m.last_runs(6)
        finally:
            m.close()
        removed = sum(b[1] for b in target.removed_batches())
        return summary, size, files, runs, removed

    def _show_stats(self, data):
        summary, size, files, runs, removed = data
        last = summary.get("last_run") or {}
        last_full = summary.get("last_full_backup")
        self.cards.append(self._card("Last backup", when(last.get("finished")),
                                     STATUS_TEXT.get(last.get("status"), "No backup yet")))
        self.cards.append(self._card("In the backup", human_size(size), f"{files:,} files"))
        self.cards.append(self._card("Removed files", human_size(removed),
                                     "old versions & deleted files kept on the drive"))
        if not last_full:
            self.banner.set_title("This drive has no full backup yet.")
            self.banner.set_revealed(True)
        else:
            age = (_dt.datetime.now().astimezone() - _dt.datetime.fromisoformat(last_full)).days
            if age >= 7:
                self.banner.set_title(f"Your last full backup was {age} days ago.")
                self.banner.set_revealed(True)
        if not runs:
            group_add(self.recent, row("No backups yet", "Your backups will be listed here."))
        for rid, kind, started, finished, status, scope, stats in runs:
            st = json.loads(stats) if stats else {}
            icon, css = STATUS_ICON.get(status, ("dialog-question-symbolic", ""))
            img = Gtk.Image(icon_name=icon)
            if css:
                img.add_css_class(css)
            title = f"{'Full' if kind == 'full' else 'Partial'} backup · {when(started)}"
            sub = f"{STATUS_TEXT.get(status, status)} · copied {st.get('copied_files', 0):,} files " \
                  f"({human_size(st.get('copied_bytes', 0))})"
            if kind == "partial" and scope:
                sub += f" · {scope}"
            r = row(title, sub)
            r.add_prefix(img)
            group_add(self.recent, r)
