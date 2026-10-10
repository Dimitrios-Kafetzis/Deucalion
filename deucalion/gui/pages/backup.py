"""Back Up: choose what, review the plan, watch the progress."""

from __future__ import annotations

import threading
from contextlib import ExitStack
from pathlib import Path

from ..common import (Adw, Gio, GLib, Gtk, alert, button, clamp, clear, group_add, hbox, label, on_main,
                      open_folder, page_with_header, row, run_async, scrolled, toast, vbox)
from ...backup import BackupJob
from ...logs import close_run_log, open_run_log
from ...util import human_duration, human_size, plural


class BackupPage:
    def __init__(self, win):
        self.win = win
        self.state = win.state
        self.folders: list[str] = []
        self.job: BackupJob | None = None
        self.plan = None
        self.stack_ctx: ExitStack | None = None
        self.cancel = threading.Event()
        self.log = None
        self.log_paths = []

        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.stack.add_named(self._build_choose(), "choose")
        self.stack.add_named(self._build_scanning(), "scanning")
        self.stack.add_named(self._build_review(), "review")
        self.stack.add_named(self._build_running(), "running")
        self.stack.add_named(self._build_done(), "done")
        self.widget = page_with_header("Back Up", self.stack)

    # -- choose -------------------------------------------------------------------------------------
    def _build_choose(self):
        page = Adw.PreferencesPage()
        what = Adw.PreferencesGroup(title="What to back up")
        self.everything = Gtk.CheckButton(active=True)
        self.some = Gtk.CheckButton(group=self.everything)
        r1 = row("Everything", "Your whole home folder and your system settings (apps, repositories, "
                               "desktop, network…) so this machine can be rebuilt.", activatable=True)
        r1.add_prefix(self.everything)
        r1.set_activatable_widget(self.everything)
        r2 = row("Only some folders", "Quickly update just the folders you choose.", activatable=True)
        r2.add_prefix(self.some)
        r2.set_activatable_widget(self.some)
        what.add(r1)
        what.add(r2)
        page.add(what)

        self.folders_group = Adw.PreferencesGroup(title="Folders")
        self.folders_group.set_header_suffix(button("Add Folder…", self._add_folders, ("flat",), icon="list-add-symbolic"))
        page.add(self.folders_group)

        opts = Adw.PreferencesGroup(title="Options")
        self.sys_switch = Adw.SwitchRow(title="Save system settings",
                                        subtitle="Apps, repositories, desktop settings, services")
        self.admin_switch = Adw.SwitchRow(title="Include protected settings",
                                          subtitle="Wi-Fi passwords and settings only the administrator can read. "
                                                   "You will be asked for your password.")
        opts.add(self.sys_switch)
        opts.add(self.admin_switch)
        page.add(opts)
        self.opts_group = opts

        start = button("Check What Will Be Copied", self.start_scan, ("suggested-action", "pill", "pill-big"))
        start.set_halign(Gtk.Align.CENTER)
        start.set_margin_top(12)
        self.start_button = start
        g = Adw.PreferencesGroup()
        g.add(start)
        page.add(g)
        self.everything.connect("toggled", lambda *_: self._update_choose())
        self._update_choose()
        return page

    def _update_choose(self):
        partial = not self.everything.get_active()
        self.folders_group.set_visible(partial)
        self.opts_group.set_visible(not partial)
        cfg = self.state.cfg
        self.sys_switch.set_active(cfg.get("system_recipe", True))
        self.admin_switch.set_active(cfg.get("system_admin", True))
        clear(self.folders_group)
        if not self.folders:
            group_add(self.folders_group, row("No folders yet", "Use “Add Folder…” to choose some."))
        for f in self.folders:
            rm = button("", lambda f=f: (self.folders.remove(f), self._update_choose()), ("flat",),
                        icon="user-trash-symbolic", tooltip="Remove")
            group_add(self.folders_group, row(f.replace(str(Path.home()), "~", 1), "", "folder-symbolic", rm))
        self.start_button.set_sensitive(self.state.status == "ready" and (not partial or bool(self.folders)))

    def _add_folders(self):
        dialog = Gtk.FileDialog(title="Choose folders to back up", modal=True)
        dialog.set_initial_folder(Gio.File.new_for_path(str(self.state.cfg.home)))

        def done(d, res):
            try:
                files = d.select_multiple_folders_finish(res)
            except GLib.Error:
                return
            for i in range(files.get_n_items()):
                p = files.get_item(i).get_path()
                if p and p not in self.folders:
                    self.folders.append(p)
            self._update_choose()

        dialog.select_multiple_folders(self.win, None, done)

    def on_show(self):
        if self.stack.get_visible_child_name() == "choose":
            self._update_choose()

    def start_full(self):
        """From the Overview's 'Back Up Now'."""
        self.win.show_page("backup")
        if self.stack.get_visible_child_name() != "choose":
            return
        self.everything.set_active(True)
        self.start_scan()

    def screenshot_review(self):
        self.start_full()

    def screenshot_done(self):
        self._auto_copy = True
        self.start_full()

    # -- scanning -------------------------------------------------------------------------------------
    def _build_scanning(self):
        self.scan_spinner = Gtk.Spinner(width_request=48, height_request=48, halign=Gtk.Align.CENTER)
        self.scan_status = Adw.StatusPage(title="Looking at your files…", child=vbox(12, children=[
            self.scan_spinner, button("Cancel", self._cancel_scan, ("pill",))]))
        self.scan_status.get_child().set_halign(Gtk.Align.CENTER)
        return self.scan_status

    def start_scan(self):
        s = self.state
        if s.status == "locked":
            self.win.unlock_drive(self.start_scan)
            return
        if s.status != "ready" or s.busy:
            return
        partial = not self.everything.get_active()
        only = list(self.folders) if partial else []
        cfg = s.cfg
        cfg["system_recipe"] = self.sys_switch.get_active()
        cfg["system_admin"] = self.admin_switch.get_active()
        cfg.save()
        self.cancel = threading.Event()
        target = s.target
        self.stack_ctx = ExitStack()
        try:
            self.stack_ctx.enter_context(target.lock())
        except Exception as e:
            self.stack_ctx = None
            alert(self.win, "Can't start", str(e))
            return
        self.log, self.log_paths = open_run_log(target, "backup")
        self.job = BackupJob(cfg, target, only, on_progress=self._scan_progress, cancel=self.cancel, log=self.log)
        s.set_busy(True)
        self.scan_spinner.start()
        self.scan_status.set_description("")
        self.stack.set_visible_child_name("scanning")
        with_system = not partial and cfg.get("system_recipe", True)
        use_admin = with_system and cfg.get("system_admin", True)

        def work():
            if with_system:
                on_main(self.scan_status.set_description,
                        "Saving your system settings…" + (" You may be asked for your administrator password."
                                                         if use_admin else ""))
                priv = None
                if use_admin:
                    from ...privileged import Privileged
                    priv = Privileged(method="pkexec")
                try:
                    self.job.prepare_system(priv)
                finally:
                    if priv:
                        priv.close()
            return self.job.scan()

        run_async(work, self._scan_done, self._scan_failed)

    def _scan_progress(self, p):
        on_main(self.scan_status.set_description, f"{p.files_total:,} files checked\n{p.current[-80:]}")

    def _cancel_scan(self):
        self.cancel.set()

    def _scan_failed(self, msg):
        self._finish_job()
        self.stack.set_visible_child_name("choose")
        if not self.cancel.is_set():
            alert(self.win, "Could not check your files", msg)

    def _scan_done(self, plan):
        self.scan_spinner.stop()
        if self.cancel.is_set():
            self._scan_failed("")
            return
        self.plan = plan
        self._fill_review()
        self.stack.set_visible_child_name("review")
        if getattr(self, "_auto_copy", False):
            self._auto_copy = False
            self._start_copy()

    # -- review -------------------------------------------------------------------------------------
    def _build_review(self):
        self.review_page = Adw.PreferencesPage()
        self.review_banner = Adw.Banner(revealed=False)
        self.review_summary = Adw.PreferencesGroup(title="This backup")
        self.review_folders = Adw.PreferencesGroup(title="Largest folders",
                                                   description="Exclude big folders you don't need in Settings.")
        self.review_warn = Adw.PreferencesGroup(title="Worth knowing")
        for g in (self.review_summary, self.review_folders, self.review_warn):
            self.review_page.add(g)
        self.start_copy = button("Start Backup", self._start_copy, ("suggested-action", "pill", "pill-big"))
        back = button("Back", self._back_from_review, ("pill",))
        bar = hbox(12, [back, self.start_copy], halign=Gtk.Align.CENTER)
        bar.set_margin_top(12)
        bar.set_margin_bottom(12)
        tv = Adw.ToolbarView()
        tv.add_top_bar(self.review_banner)
        tv.set_content(self.review_page)
        tv.add_bottom_bar(bar)
        return tv

    def _fill_review(self):
        p = self.plan
        for g in (self.review_summary, self.review_folders, self.review_warn):
            clear(g)
        rows = [
            ("New files", f"{p.new_files:,}", human_size(p.new_bytes), "list-add-symbolic"),
            ("Changed files", f"{p.changed_files:,}", f"{human_size(p.changed_bytes)} · old versions are kept in Removed Files",
             "document-edit-symbolic"),
            ("Gone from this computer", f"{p.removed_items:,}", f"{human_size(p.removed_bytes)} · moved to Removed Files",
             "user-trash-symbolic"),
            ("Unchanged", f"{p.unchanged_files:,}", human_size(p.unchanged_bytes), "emblem-ok-symbolic"),
        ]
        for title, n, sub, icon in rows:
            group_add(self.review_summary, row(title, sub, icon, label(n, ("title-3",), wrap=False)))
        free = self.state.target.free_bytes()
        group_add(self.review_summary, row("To copy now", f"{human_size(free)} free on the drive",
                                           "document-save-symbolic", label(human_size(p.copy_bytes), ("title-3",), wrap=False)))
        folders = p.largest_folders(8)
        self.review_folders.set_visible(bool(folders) and p.kind == "full")
        for folder, files, size in folders:
            group_add(self.review_folders, row(folder.replace("home/", "~/", 1), f"{files:,} files",
                                               "folder-symbolic", label(human_size(size), ("dim-label",), wrap=False)))
        notes = list(p.warnings) + [f"{path}: {why}" for path, why in p.skipped[:20]]
        found = self.job.sensitive_found() if p.kind == "full" else []
        from ...util import is_encrypted
        if found and not is_encrypted(self.state.target.root):
            notes.insert(0, "This drive is not encrypted, and the backup includes keys or logged-in sessions ("
                         + ", ".join(found[:4]) + ").")
        self.review_warn.set_visible(bool(notes))
        for n in notes[:40]:
            group_add(self.review_warn, row(n, "", "dialog-information-symbolic"))
        identity = self.job.identity_problem()
        problem = self.job.space_problem(p)
        self.review_banner.set_revealed(bool(identity or problem))
        self.review_banner.set_title(problem or identity or "")
        self.start_copy.set_sensitive(problem is None)
        self.start_copy.set_label("Start Backup" if not p.nothing_to_do else "Finish (nothing to copy)")

    def _back_from_review(self):
        self._finish_job()
        self.stack.set_visible_child_name("choose")
        self._update_choose()

    # -- running ------------------------------------------------------------------------------------
    def _build_running(self):
        self.bar = Gtk.ProgressBar(show_text=False)
        self.pct = label("0%", ("big-number",), xalign=0.5)
        self.amount = label("", ("title-4",), xalign=0.5)
        self.speed = label("", ("dim-label",), xalign=0.5)
        self.current = label("", ("dim-label", "caption"), xalign=0.5, wrap=False)
        self.current.set_ellipsize(3)
        stop = button("Stop", self._ask_stop, ("pill", "destructive-action"))
        stop.set_halign(Gtk.Align.CENTER)
        box = vbox(14, margin=48, children=[label("Backing up…", ("title-1",), xalign=0.5), self.pct, self.bar,
                                            self.amount, self.speed, self.current, stop])
        box.set_valign(Gtk.Align.CENTER)
        return clamp(box, 640)

    def _start_copy(self):
        self.stack.set_visible_child_name("running")
        self.bar.set_fraction(0)
        self.pct.set_label("0%")
        self.job.on_progress = self._copy_progress
        plan = self.plan
        run_async(lambda: self.job.execute(plan), self._copy_done, self._copy_failed)

    def _copy_progress(self, p):
        frac = p.bytes_done / p.bytes_total if p.bytes_total else 1.0
        amount = f"{human_size(p.bytes_done)} of {human_size(p.bytes_total)} · {p.files_done:,} of {p.files_total:,} files"
        speed = (f"{human_size(p.rate)}/s" if p.rate else "") + (f" · about {human_duration(p.eta)} left" if p.eta else "")
        current = p.current

        def apply():
            self.bar.set_fraction(min(frac, 1.0))
            self.pct.set_label(f"{min(frac, 1.0) * 100:.0f}%")
            self.amount.set_label(amount)
            self.speed.set_label(speed)
            self.current.set_label(current)

        on_main(apply)

    def _ask_stop(self):
        alert(self.win, "Stop the backup?", "Files copied so far are kept. The next backup continues from here.",
              (("cont", "Keep Going"), ("stop", "Stop")), destructive="stop",
              callback=lambda r: self.cancel.set() if r == "stop" else None)

    def _copy_failed(self, msg):
        self._finish_job()
        self._show_done("failed", "The backup failed", msg, [])

    def _copy_done(self, result):
        self._finish_job()
        if result.status == "failed":
            self._show_done("failed", "The backup failed", result.error or "", result.warnings)
        elif result.status == "cancelled":
            self._show_done("cancelled", "Backup stopped",
                            f"{result.copied_files:,} files were copied. The next backup continues from here.", [])
        else:
            text = (f"Copied {plural(result.copied_files, 'file')} ({human_size(result.copied_bytes)}) in "
                    f"{human_duration(result.duration)}. {plural(result.removed_items, 'item')} moved to Removed Files.")
            title = "Backup complete" if result.status == "completed" else "Backup complete, with warnings"
            self._show_done(result.status, title, text, result.warnings)
            if self.state.target is not None:
                from ...cli import _refresh_tool_copy
                run_async(lambda: _refresh_tool_copy(self.state.cfg, self.state.target))

    def _finish_job(self):
        if self.job is not None:
            self.job.close()
            self.job = None
        if self.log is not None:
            close_run_log(self.log)
            self.log = None
        if self.stack_ctx is not None:
            self.stack_ctx.close()
            self.stack_ctx = None
        self.state.set_busy(False)

    # -- done -------------------------------------------------------------------------------------------
    def _build_done(self):
        self.done_status = Adw.StatusPage()
        self.done_warn = Adw.PreferencesGroup(title="Warnings")
        log_btn = button("Open Log", lambda: open_folder(self.log_paths[0]) if self.log_paths else None, ("pill",))
        ok = button("Done", lambda: (self.stack.set_visible_child_name("choose"), self.state.refresh()),
                    ("pill", "suggested-action"))
        self.done_status.set_child(vbox(18, children=[hbox(12, [log_btn, ok], halign=Gtk.Align.CENTER),
                                                      clamp(self.done_warn, 700)]))
        return scrolled(self.done_status)

    def _show_done(self, status, title, text, warnings):
        icon = {"completed": "emblem-ok-symbolic", "completed_with_warnings": "dialog-warning-symbolic",
                "cancelled": "media-playback-stop-symbolic"}.get(status, "dialog-error-symbolic")
        self.done_status.set_icon_name(icon)
        self.done_status.set_title(title)
        self.done_status.set_description(text)
        clear(self.done_warn)
        self.done_warn.set_visible(bool(warnings))
        for w in warnings[:60]:
            group_add(self.done_warn, row(w))
        self.stack.set_visible_child_name("done")
        toast(self.widget, title)
