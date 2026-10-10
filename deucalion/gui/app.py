"""The Deucalion app: main window with a sidebar of pages."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from .common import (APP_ID, Adw, AppState, Gdk, Gio, GLib, Gtk, alert, ask_password, run_async,  # noqa: F401
                     toast)

CSS = b"""
.hero-icon { color: @accent_color; }
.hero-title { font-size: 1.6em; font-weight: 800; }
.big-number { font-size: 2.2em; font-weight: 800; font-feature-settings: "tnum"; }
.stat-card { padding: 18px; border-radius: 12px; }
.stat-title { font-weight: 600; opacity: 0.7; }
.mono { font-family: monospace; font-size: 0.9em; }
.pill-big { padding: 10px 32px; font-size: 1.1em; }
.status-ok { color: @success_color; }
.status-warn { color: @warning_color; }
.status-error { color: @error_color; }
.sidebar-badge { font-size: 0.8em; padding: 0 6px; border-radius: 9px; background: alpha(@accent_bg_color, 0.2); }
.step-number { font-weight: 800; opacity: 0.6; min-width: 24px; }
"""

PAGES = [
    ("overview", "Overview", "go-home-symbolic"),
    ("backup", "Back Up", "document-save-symbolic"),
    ("restore", "Restore", "document-revert-symbolic"),
    ("rebuild", "Rebuild", "system-software-install-symbolic"),
    ("drives", "Drives", "drive-harddisk-symbolic"),
    ("removed", "Removed Files", "user-trash-symbolic"),
    ("settings", "Settings", "emblem-system-symbolic"),
]


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application, state: AppState):
        super().__init__(application=app, title="Deucalion", default_width=1100, default_height=760)
        self.set_size_request(360, 500)
        self.state = state
        self.toast_overlay = Adw.ToastOverlay()
        self.split = Adw.NavigationSplitView(min_sidebar_width=210, max_sidebar_width=260)
        self.toast_overlay.set_child(self.split)
        self.set_content(self.toast_overlay)

        # Narrow windows: show one pane at a time
        bp = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 680sp"))
        bp.add_setter(self.split, "collapsed", True)
        self.add_breakpoint(bp)

        # Sidebar
        self.sidebar_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.sidebar_list.add_css_class("navigation-sidebar")
        self.sidebar_rows = {}
        for key, title, icon in PAGES:
            box = Gtk.Box(spacing=12, margin_top=6, margin_bottom=6, margin_start=6, margin_end=6)
            box.append(Gtk.Image(icon_name=icon))
            box.append(Gtk.Label(label=title, xalign=0, hexpand=True))
            r = Gtk.ListBoxRow(child=box)
            r.key = key
            self.sidebar_list.append(r)
            self.sidebar_rows[key] = r
        self.sidebar_list.connect("row-activated", lambda _l, r: self.show_page(r.key))

        side_tv = Adw.ToolbarView()
        hb = Adw.HeaderBar()
        hb.set_title_widget(Adw.WindowTitle(title="Deucalion"))
        menu = Gio.Menu()
        menu.append("About Deucalion", "app.about")
        hb.pack_end(Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu, primary=True,
                                   tooltip_text="Main menu"))
        side_tv.add_top_bar(hb)
        side_scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        side_scroll.set_child(self.sidebar_list)
        side_tv.set_content(side_scroll)
        self.drive_chip = Gtk.Label(xalign=0, wrap=True, margin_start=18, margin_end=12, margin_bottom=12)
        self.drive_chip.add_css_class("dim-label")
        self.drive_chip.add_css_class("caption")
        side_tv.add_bottom_bar(self.drive_chip)
        self.split.set_sidebar(Adw.NavigationPage(title="Deucalion", child=side_tv))

        # Pages (built lazily)
        self.pages: dict[str, object] = {}
        state.connect("changed", lambda *_: self._on_state())
        self.show_page("overview")

    def _on_state(self) -> None:
        s = self.state
        text = {"none": "No backup drive yet",
                "disconnected": f"“{s.target_name}” is not connected",
                "locked": f"“{s.target_name}” is locked",
                "ready": f"“{s.target_name}” · {s.free_text()}"}[s.status]
        self.drive_chip.set_label(text)

    def page(self, key: str):
        if key not in self.pages:
            from . import pages
            cls = getattr(pages, {"overview": "OverviewPage", "backup": "BackupPage", "restore": "RestorePage",
                                  "rebuild": "RebuildPage", "drives": "DrivesPage", "removed": "RemovedPage",
                                  "settings": "SettingsPage"}[key])
            self.pages[key] = cls(self)
        return self.pages[key]

    def show_page(self, key: str) -> None:
        page = self.page(key)
        self.sidebar_list.select_row(self.sidebar_rows[key])
        if not hasattr(page, "nav_page"):
            title = next(t for k, t, _ in PAGES if k == key)
            page.nav_page = Adw.NavigationPage(title=title, child=page.widget)
        if self.split.get_content() is not page.nav_page:
            self.content_page = page.nav_page
            self.split.set_content(self.content_page)
        self.split.set_show_content(True)
        if hasattr(page, "on_show"):
            page.on_show()

    # -- shared actions -------------------------------------------------------------------------
    def unlock_drive(self, on_done=None) -> None:
        access = self.state.access
        name = self.state.target_name

        def got(pw):
            if not pw:
                return
            from ..drivesetup import DriveSetup
            toast(self, "Unlocking…" + (" You may be asked for your administrator password."
                                        if access.get("method") == "veracrypt" else ""))

            def work():
                ds = DriveSetup(self.state.cfg, out=lambda s: None)
                try:
                    return ds.open(access, pw)
                finally:
                    ds.close()

            def done(_mp):
                self.state.refresh()
                toast(self, f"“{name}” is unlocked")
                if on_done:
                    on_done()

            run_async(work, done, lambda msg: alert(self, "Could not unlock the drive", msg))

        ask_password(self, f"Unlock “{name}”", "Enter the password of your backup drive.", got)

    def lock_drive(self) -> None:
        from ..drivesetup import DriveSetup
        access = self.state.access
        cfg = self.state.cfg

        def work():
            ds = DriveSetup(cfg, out=lambda s: None)
            try:
                if access.get("method", "none") == "none":
                    from ..util import run
                    root = self.state.target.root if self.state.target else None
                    if root is not None:
                        src = run(["findmnt", "-rno", "SOURCE", "--target", str(root)]).stdout.strip()
                        ds.u.unmount(ds.u.resolve(src))
                else:
                    ds.close_access(access)
            finally:
                ds.close()

        run_async(work, lambda _r: (self.state.refresh(), toast(self, "You can unplug the drive now")),
                  lambda msg: alert(self, "Could not close the drive", msg))


class DeucalionApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.state: AppState | None = None
        self.window: MainWindow | None = None
        about = Gio.SimpleAction.new("about", None)
        about.connect("activate", lambda *_: self._about())
        self.add_action(about)

    def do_startup(self):
        Adw.Application.do_startup(self)
        icons = Path(__file__).resolve().parent.parent.parent / "data" / "icons"
        display = Gdk.Display.get_default()
        if icons.is_dir():
            Gtk.IconTheme.get_for_display(display).add_search_path(str(icons))
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS, len(CSS))
        Gtk.StyleContext.add_provider_for_display(display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        Gtk.Window.set_default_icon_name(APP_ID)
        if os.environ.get("DEUCALION_SCREENSHOT_DIR"):  # headless rendering reports no font DPI
            settings = Gtk.Settings.get_default()
            settings.set_property("gtk-xft-dpi", 96 * 1024)
            settings.set_property("gtk-font-name", "Ubuntu Sans 11")

    def do_activate(self):
        if self.window is None:
            self.state = AppState()
            self.window = MainWindow(self, self.state)
            self.state.refresh()
        self.window.present()
        shots = os.environ.get("DEUCALION_SCREENSHOT_DIR")
        if shots:
            GLib.timeout_add(1500, lambda: _screenshots(self.window, Path(shots)) and False)

    def _about(self):
        from .. import __version__
        about = Adw.AboutDialog(application_name="Deucalion", application_icon=APP_ID, version=__version__,
                                developer_name="Dimitrios Kafetzis",
                                website="https://github.com/Dimitrios-Kafetzis/Deucalion",
                                comments="Back up your Ubuntu machine to an external drive, and rebuild it later.",
                                license_type=Gtk.License.CUSTOM)
        about.present(self.window)


def _screenshots(win: MainWindow, folder: Path) -> None:
    """Developer aid: render each page to a PNG, then quit (DEUCALION_SCREENSHOT_DIR)."""
    from gi.repository import Graphene
    folder.mkdir(parents=True, exist_ok=True)
    keys = os.environ.get("DEUCALION_SCREENSHOT_PAGES", ",".join(k for k, _, _ in PAGES)).split(",")

    def snap(name: str) -> None:
        w, h = win.get_width(), win.get_height()
        shot = Gtk.Snapshot()
        Gtk.WidgetPaintable.new(win).snapshot(shot, w, h)
        node = shot.to_node()
        if node is not None:
            tex = win.get_native().get_renderer().render_texture(node, Graphene.Rect().init(0, 0, w, h))
            tex.save_to_png(str(folder / f"{name}.png"))

    def step(i: int) -> bool:
        if i > 0:
            snap(keys[i - 1])
        if i >= len(keys):
            win.get_application().quit()
            return False
        key = keys[i]
        if ":" in key:  # page:action, e.g. "drives:setup"
            page, action = key.split(":", 1)
            win.show_page(page)
            getattr(win.page(page), f"screenshot_{action}")()
        else:
            win.show_page(key)
        GLib.timeout_add(int(os.environ.get("DEUCALION_SCREENSHOT_WAIT", "1200")), lambda: step(i + 1))
        return False

    step(0)


def run_gui(argv: list[str] | None = None) -> int:
    app = DeucalionApp()
    return app.run(argv if argv is not None else sys.argv[:1])
