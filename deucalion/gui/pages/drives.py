"""Drives: the registered backup drives, connected drives, and the drive setup wizard."""

from __future__ import annotations

import os
import shutil

from ..common import (Adw, GLib, Gtk, alert, button, clamp, clear, group_add, hbox, label, on_main,
                      page_with_header, row, run_async, scrolled, toast, vbox)
from ... import drivesetup
from ...drives import list_drives
from ...target import Target
from ...util import DeucalionError, human_size

LAYOUT_TEXT = {
    "encrypt-all": ("Encrypt the whole drive", "The safest choice for a dedicated backup drive.", True),
    "encrypt-part": ("Encrypted part + normal part",
                     "Backups go in an encrypted part; the rest stays a normal drive for other files.", True),
    "encrypt-folder": ("Encrypted folder on this drive",
                       "Keeps everything already on the drive. The backup lives in one encrypted file.", False),
    "plain": ("No encryption, exFAT", "Readable on any computer without a password.", True),
    "as-is": ("No encryption, keep the drive as it is", "Keeps everything already on the drive.", False),
}


class DrivesPage:
    def __init__(self, win):
        self.win = win
        self.state = win.state
        self.backup_group = Adw.PreferencesGroup(title="Backup drives")
        self.connected_group = Adw.PreferencesGroup(title="Connected drives",
                                                    description="Your system disk is never shown here.")
        page = Adw.PreferencesPage()
        page.add(self.backup_group)
        page.add(self.connected_group)
        setup = button("Set Up a Drive…", self.start_setup, ("suggested-action",), icon="list-add-symbolic")
        self.widget = page_with_header("Drives", page, header_end=[
            setup, button("", self.refresh, icon="view-refresh-symbolic", tooltip="Look for drives again")])
        self.state.connect("changed", lambda *_: self.refresh())

    def on_show(self):
        self.refresh()

    def refresh(self):
        clear(self.backup_group)
        cfg = self.state.cfg
        targets = cfg.get("targets", {})
        if not targets:
            group_add(self.backup_group, row("No backup drive yet", "Choose “Set Up a Drive…” to prepare one."))
        for tid, t in targets.items():
            access = t.get("access") or {"method": "none"}
            enc = {"veracrypt": "VeraCrypt", "luks": "LUKS"}.get(access.get("method"), "")
            connected = (os.path.exists(os.path.join(t["path"], ".deucalion", "drive-id")))
            status = "Connected" if connected else "Not connected"
            if enc:
                status += f" · encrypted ({enc})"
            if connected:
                try:
                    status += f" · {human_size(shutil.disk_usage(t['path']).free)} free"
                except OSError:
                    pass
            r = row(t["name"] + ("  ★" if cfg.get("default_target") == tid else ""), f"{status}\n{t['path']}",
                    "drive-harddisk-symbolic")
            if connected:
                r.add_suffix(button("Lock" if enc else "Unmount", self.win.lock_drive, ("flat",),
                                    icon="media-eject-symbolic", tooltip="Close the drive so you can unplug it"))
            elif enc and self.state.status == "locked" and tid == Target.select(cfg):
                r.add_suffix(button("Unlock", self.win.unlock_drive, ("flat",)))
            if cfg.get("default_target") != tid:
                r.add_suffix(button("", lambda tid=tid: self._make_default(tid), ("flat",), icon="starred-symbolic",
                                    tooltip="Use this drive for backups"))
            r.add_suffix(button("", lambda tid=tid: self._forget(tid), ("flat",), icon="user-trash-symbolic",
                                tooltip="Forget this drive (the backup on it is kept)"))
            group_add(self.backup_group, r)

        clear(self.connected_group)
        drives = [d for d in list_drives() if not d.system]
        if not drives:
            group_add(self.connected_group, row("No external drives", "Plug in a USB drive."))
        for d in drives:
            exp = Adw.ExpanderRow(title=GLib.markup_escape_text(f"{d.model or 'Drive'} · {human_size(d.size)}"),
                                  subtitle=f"{d.path} · {'external' if d.external else 'internal'}")
            exp.add_prefix(Gtk.Image(icon_name="drive-removable-media-symbolic" if d.external else "drive-harddisk-symbolic"))
            exp.add_suffix(button("Set Up…", lambda d=d: self.start_setup(d.path), ("flat",)))
            for v in d.volumes:
                tags = []
                if v.encrypted:
                    tags.append("encrypted")
                if v.has_backup:
                    tags.append("Deucalion backup")
                sub = f"{v.fstype or 'unknown'} · {human_size(v.size)}" + (f" · {', '.join(v.mountpoints)}" if v.mountpoints else "")
                exp.add_row(row(f"{v.label or os.path.basename(v.path)}" + (f"  ({', '.join(tags)})" if tags else ""), sub))
            if not d.volumes:
                exp.add_row(row("Empty", "No filesystem"))
            group_add(self.connected_group, exp)

    def _make_default(self, tid):
        self.state.cfg["default_target"] = tid
        self.state.cfg.save()
        self.state.refresh()

    def _forget(self, tid):
        name = self.state.cfg["targets"][tid]["name"]

        def done(r):
            if r != "forget":
                return
            cfg = self.state.cfg
            cfg["targets"].pop(tid, None)
            if cfg.get("default_target") == tid:
                cfg["default_target"] = next(iter(cfg["targets"]), None)
            cfg.save()
            self.state.refresh()

        alert(self.win, f"Forget “{name}”?", "Deucalion stops using this drive. The backup on it is not deleted; "
                                            "you can add it again later.", (("cancel", "Cancel"), ("forget", "Forget")),
              destructive="forget", callback=done)

    # -- setup wizard --------------------------------------------------------------------------------
    def start_setup(self, device: str | None = None):
        self.win.show_page("drives")
        self.wizard = SetupWizard(self, device)
        self.wizard.present()

    # Screenshot mode only (the documentation): each one does what a click would do.
    def screenshot_setup(self, device: str = ""):
        """Open the wizard; with a device (e.g. /dev/sda) it starts at the storage page, as 'Set Up…' does."""
        self.start_setup(device or None)

    def screenshot_expand(self):
        """Open every connected drive's row."""
        child = self.connected_group
        for r in getattr(child, "_rows", []):
            if isinstance(r, Adw.ExpanderRow):
                r.set_expanded(True)

    def screenshot_pick(self, key: str):
        """Choose an option (a drive path, layout or encryption key) on the wizard's current page."""
        self.wizard.checks[key].set_active(True)

    def screenshot_fill(self, values: str = ""):
        """Fill the details page: 'name|password|size'."""
        w = self.wizard
        name, _, rest = values.partition("|")
        password, _, size = rest.partition("|")
        if name:
            w.name_row.set_text(name)
        if w.pw1 is not None and password:
            w.pw1.set_text(password)
            w.pw2.set_text(password)
        if w.size_row is not None and size:
            w.size_row.set_value(float(size))

    def screenshot_confirm(self):
        """Type the drive's name on the confirmation page."""
        w = self.wizard
        if w.confirm_entry is not None:
            w.confirm_entry.set_text(os.path.basename(w.drive.path))

    def screenshot_next(self):
        """Press the wizard's button at the bottom of the current page (Next, Set Up…)."""
        self.wizard.nav.get_visible_page().get_child().next_button.emit("clicked")

    def screenshot_finished(self):
        """Wait until the wizard's drive setup has finished (returns 'wait' while it runs)."""
        return "wait" if not self.wizard.dialog.get_can_close() else None

    def screenshot_forget(self, name: str = ""):
        """Ask to forget a backup drive (by name; default: the default drive)."""
        targets = self.state.cfg.get("targets", {})
        tid = next((t for t, v in targets.items() if v.get("name") == name), self.state.cfg.get("default_target"))
        if tid:
            self._forget(tid)


class SetupWizard:
    """Choose drive → layout → encryption → details → confirm → progress."""

    def __init__(self, owner: DrivesPage, device: str | None):
        self.owner = owner
        self.win = owner.win
        self.drives = [d for d in list_drives() if not d.system and d.external]
        self.drive = next((d for d in self.drives if d.path == device), None)
        self.layout = None
        self.method = None
        self.dialog = Adw.Dialog(title="Set Up a Backup Drive", content_width=620, content_height=640)
        self.nav = Adw.NavigationView()
        self.dialog.set_child(self.nav)
        if self.drive is None:
            self.nav.add(self._page_drive())
        else:
            self.nav.add(self._page_layout())

    def present(self):
        self.dialog.present(self.win)

    def _page(self, title: str, content: Gtk.Widget, next_label: str | None = None, on_next=None,
              destructive: bool = False, tag: str | None = None) -> Adw.NavigationPage:
        tv = Adw.ToolbarView()
        tv.add_top_bar(Adw.HeaderBar())
        tv.set_content(content)
        if next_label:
            b = button(next_label, on_next, ("pill", "destructive-action" if destructive else "suggested-action"))
            b.set_halign(Gtk.Align.CENTER)
            b.set_margin_top(12)
            b.set_margin_bottom(18)
            tv.add_bottom_bar(b)
            tv.next_button = b
        return Adw.NavigationPage(title=title, child=tv, tag=tag)

    def _radio_group(self, title: str, options, on_select, description: str = "") -> tuple[Adw.PreferencesGroup, list]:
        g = Adw.PreferencesGroup(title=title, description=description)
        first = None
        checks = []
        self.checks = {}
        for key, t, sub, enabled in options:
            c = Gtk.CheckButton(group=first)
            first = first or c
            c.connect("toggled", lambda c, key=key: on_select(key) if c.get_active() else None)
            r = row(t, sub, activatable=enabled)
            r.add_prefix(c)
            r.set_activatable_widget(c)
            r.set_sensitive(enabled)
            g.add(r)
            checks.append(c)
            self.checks[key] = c
        return g, checks

    # pages
    def _page_drive(self):
        page = Adw.PreferencesPage()
        if not self.drives:
            st = Adw.StatusPage(icon_name="drive-removable-media-symbolic", title="No external drive",
                                description="Plug in the USB drive you want to use, then open this again.")
            return self._page("Choose a drive", st)
        opts = [(d.path, f"{d.model or 'Drive'} · {human_size(d.size)}",
                 d.path + "".join(f" · {v.label or v.fstype}" for v in d.volumes[:3]), True) for d in self.drives]
        g, checks = self._radio_group("Which drive?", opts, lambda key: setattr(
            self, "drive", next(d for d in self.drives if d.path == key)))
        checks[0].set_active(True)
        page.add(g)
        return self._page("Choose a drive", page, "Next", lambda: self.nav.push(self._page_layout()))

    def _page_layout(self):
        page = Adw.PreferencesPage()
        d = self.drive
        mounted = [v for v in d.volumes if v.mountpoints and not v.encrypted]
        contents = Adw.PreferencesGroup(title=f"{d.model or 'Drive'} · {human_size(d.size)}")
        for v in d.volumes:
            used = ""
            if v.mountpoints:
                try:
                    used = f" · {human_size(shutil.disk_usage(v.mountpoints[0]).used)} used"
                except OSError:
                    pass
            contents.add(row(v.label or os.path.basename(v.path), f"{v.fstype or 'unknown'} · {human_size(v.size)}{used}",
                             "drive-harddisk-symbolic"))
        if not d.volumes:
            contents.add(row("Empty drive", ""))
        page.add(contents)
        opts = []
        for key, (t, sub, erases) in LAYOUT_TEXT.items():
            enabled = erases or bool(mounted)
            opts.append((key, t, sub + ("  ⚠ Erases the drive." if erases else "")
                         + ("" if enabled else "  (needs a drive with files on it)"), enabled))
        g, checks = self._radio_group("How should the backup be stored?", opts, lambda k: setattr(self, "layout", k))
        page.add(g)
        default = "encrypt-folder" if mounted else "encrypt-all"
        checks[list(LAYOUT_TEXT).index(default)].set_active(True)
        self.layout = default
        self.mounted = mounted
        return self._page("Storage", page, "Next", self._after_layout)

    def _after_layout(self):
        if self.layout.startswith("encrypt"):
            self.nav.push(self._page_method())
        else:
            self.method = ""
            self.nav.push(self._page_details())

    def _page_method(self):
        page = Adw.PreferencesPage()
        vc = drivesetup.veracrypt_binary()
        opts = [("veracrypt", "VeraCrypt", "Open your backup on Linux, macOS and Windows (with the free VeraCrypt app)."
                 + ("" if vc else "  VeraCrypt is not installed on this computer yet."), True),
                ("luks", "LUKS (Linux only)", "Built into Ubuntu, no extra software. Ubuntu asks for the password "
                                             "when you plug in the drive.", True)]
        g, checks = self._radio_group("Which encryption?", opts, lambda k: setattr(self, "method", k))
        page.add(g)
        if not vc:
            info = Adw.PreferencesGroup()
            info.add(row("VeraCrypt is not installed yet", "Deucalion can install it: the official package is "
                         "downloaded and its signature checked first. Asks for your administrator password.",
                         "dialog-information-symbolic", button("Install", self._install_veracrypt, ("suggested-action",))))
            page.add(info)
        self.method = "veracrypt" if vc else "luks"
        checks[0 if vc else 1].set_active(True)
        return self._page("Encryption", page, "Next", lambda: self.nav.push(self._page_details()))

    def _install_veracrypt(self):
        from ... import deps
        toast(self.owner.widget, "Installing VeraCrypt… you will be asked for your administrator password.")

        def done(_r):
            toast(self.owner.widget, "VeraCrypt is installed")
            self.nav.pop()
            self.nav.push(self._page_method())

        run_async(lambda: deps.install_veracrypt(out=lambda s: None), done,
                  lambda msg: alert(self.win, "Could not install VeraCrypt", msg))

    def _page_details(self):
        page = Adw.PreferencesPage()
        g = Adw.PreferencesGroup(title="Details")
        self.name_row = Adw.EntryRow(title="Name of the backup drive", text="Deucalion")
        g.add(self.name_row)
        self.size_row = None
        if self.layout in ("encrypt-part", "encrypt-folder"):
            if self.layout == "encrypt-part":
                max_gb = max(int(self.drive.size / 1024 ** 3) - 1, 1)
                title, sub = "Size of the encrypted part (GB)", "The rest of the drive stays a normal drive."
            else:
                max_gb = max(int(shutil.disk_usage(self.mounted[0].mountpoints[0]).free * 0.95 / 1024 ** 3), 1)
                title, sub = "Size of the encrypted folder (GB)", "It can't grow later, so leave room for the future."
            adj = Gtk.Adjustment(lower=1, upper=max_gb, value=int(max_gb * 0.8), step_increment=10, page_increment=100)
            self.size_row = Adw.SpinRow(title=title, subtitle=sub, adjustment=adj)
            g.add(self.size_row)
        page.add(g)
        self.pw1 = self.pw2 = None
        if self.layout.startswith("encrypt"):
            pg = Adw.PreferencesGroup(title="Password", description="It can't be recovered if you forget it. "
                                                                   "Write it down and keep it somewhere safe.")
            self.pw1 = Adw.PasswordEntryRow(title="Password")
            self.pw2 = Adw.PasswordEntryRow(title="Type it again")
            self.pw_hint = label("At least 8 characters; a few words make a strong, memorable password.",
                                 ("dim-label", "caption"))
            self.pw_hint.set_margin_top(6)
            for w in (self.pw1, self.pw2):
                w.connect("changed", lambda *_: self._check_pw())
                pg.add(w)
            pg.add(self.pw_hint)
            page.add(pg)
        p = self._page("Details", page, "Next", self._to_confirm)
        self.details_next = p.get_child().next_button
        if self.pw1 is not None:
            self.details_next.set_sensitive(False)
        return p

    def _check_pw(self):
        a, b = self.pw1.get_text(), self.pw2.get_text()
        ok = len(a) >= 8 and a == b
        if len(a) < 8:
            hint = "At least 8 characters; a few words make a strong, memorable password."
        elif a != b:
            hint = "The two passwords are different."
        elif len(a) < 12:
            hint = "OK. Tip: 12 or more characters is much safer."
        else:
            hint = "Strong password."
        self.pw_hint.set_label(hint)
        self.details_next.set_sensitive(ok)

    def _request(self) -> drivesetup.SetupRequest:
        size = int(self.size_row.get_value() * 1024 ** 3) if self.size_row else 0
        folder = self.mounted[0].mountpoints[0] if self.layout in ("encrypt-folder", "as-is") and self.mounted else ""
        return drivesetup.SetupRequest(self.layout, device=self.drive.path, folder=folder, method=self.method or "",
                                       name=self.name_row.get_text().strip() or "Deucalion", size=size,
                                       passphrase=self.pw1.get_text() if self.pw1 else "")

    def _to_confirm(self):
        req = self._request()
        page = Adw.PreferencesPage()
        missing = drivesetup.missing_requirements(req)
        g = Adw.PreferencesGroup(title="Summary")
        g.add(row("Drive", f"{self.drive.model or 'Drive'} · {human_size(self.drive.size)} · {self.drive.path}"))
        g.add(row("Storage", LAYOUT_TEXT[req.layout][0] + (f" · {req.method}" if req.method else "")))
        if req.size:
            g.add(row("Encrypted size", human_size(req.size)))
        page.add(g)
        self.confirm_entry = None
        if any(c == "exfatprogs" for c, _ in missing):
            fix = Adw.PreferencesGroup()
            fix.add(row("One more thing is needed", "The exFAT tools (exfatprogs) are not installed.",
                        "dialog-information-symbolic",
                        button("Install", lambda: self._install_exfat(), ("suggested-action",))))
            page.add(fix)
        other = [m for c, m in missing if c not in ("exfatprogs", "password")]
        for m in other:
            page.add(_group_with(row("Can't continue", m, "dialog-error-symbolic")))
        erases = req.layout in drivesetup.ERASING
        if erases:
            w = Adw.PreferencesGroup(title="Everything on this drive will be erased",
                                     description=f"To confirm, type the drive name: {os.path.basename(self.drive.path)}")
            self.confirm_entry = Adw.EntryRow(title="Drive name")
            w.add(self.confirm_entry)
            page.add(w)
        p = self._page("Confirm", page, "Erase and Set Up" if erases else "Set Up", self._run, destructive=erases)
        btn = p.get_child().next_button
        blocked = bool(other) or any(c == "exfatprogs" for c, _ in missing)
        btn.set_sensitive(not blocked and not erases)
        if self.confirm_entry is not None:
            self.confirm_entry.connect("changed", lambda e: btn.set_sensitive(
                not blocked and e.get_text().strip() == os.path.basename(self.drive.path)))
        self.confirm_button = btn
        self.nav.push(p)

    def _install_exfat(self):
        from ...privileged import Privileged

        def work():
            with Privileged(method="pkexec") as priv:
                if priv.call("apt_install", packages=["exfatprogs"]).get("code"):
                    raise DeucalionError("exfatprogs could not be installed.")

        toast(self.owner.widget, "Installing exfatprogs… you may be asked for your administrator password.")
        run_async(work, lambda _r: (self.nav.pop(), self._to_confirm()),
                  lambda msg: alert(self.win, "Could not install exfatprogs", msg))

    def _run(self):
        req = self._request()
        logv = Gtk.TextView(editable=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR, top_margin=10,
                            left_margin=10, right_margin=10, bottom_margin=10)
        logv.add_css_class("card")
        spinner = Gtk.Spinner(spinning=True, width_request=32, height_request=32)
        title = label("Setting up the drive…", ("title-2",), xalign=0.5)
        box = vbox(16, margin=24, children=[spinner, title, scrolled(logv)])
        page = Adw.NavigationPage(title="Setting up", child=box, can_pop=False)
        self.nav.push(page)
        self.dialog.set_can_close(False)

        def out(line):
            on_main(lambda: logv.get_buffer().insert(logv.get_buffer().get_end_iter(), line + "\n"))

        state = self.owner.state

        def work():
            ds = drivesetup.DriveSetup(state.cfg, out=out)
            try:
                return ds.run(req)
            finally:
                ds.close()

        def done(target):
            self.dialog.set_can_close(True)
            spinner.set_spinning(False)
            title.set_label(f"“{target.name}” is ready")
            box.append(button("Done", self.dialog.close, ("pill", "suggested-action")))
            state.refresh()

        def failed(msg):
            self.dialog.set_can_close(True)
            spinner.set_spinning(False)
            title.set_label("Setup failed")
            out(msg)
            box.append(button("Close", self.dialog.close, ("pill",)))
            state.refresh()

        run_async(work, done, failed)


def _group_with(widget):
    g = Adw.PreferencesGroup()
    g.add(widget)
    return g
