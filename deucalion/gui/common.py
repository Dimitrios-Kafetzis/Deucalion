"""Shared GUI helpers: background work, dialogs, small widget builders, app state."""

from __future__ import annotations

import datetime as _dt
import threading
import traceback
from pathlib import Path
from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk, Pango  # noqa: E402

from ..config import Config  # noqa: E402
from ..target import Target  # noqa: E402
from ..util import DeucalionError, human_size  # noqa: E402

APP_ID = "io.github.DimitriosKafetzis.Deucalion"


# ------------------------------------------------------------------------------------------------
# Background work


def run_async(func: Callable, on_done: Callable | None = None, on_error: Callable | None = None) -> threading.Thread:
    """Run func() in a thread; call on_done(result) or on_error(message) on the main loop."""

    def worker():
        try:
            result = func()
        except DeucalionError as e:
            msg = str(e)
            GLib.idle_add(lambda: (on_error or _default_error)(msg) and False)
            return
        except Exception as e:  # unexpected: show it, keep the app alive
            traceback.print_exc()
            msg = f"Unexpected error: {type(e).__name__}: {e}"
            GLib.idle_add(lambda: (on_error or _default_error)(msg) and False)
            return
        if on_done:
            GLib.idle_add(lambda: on_done(result) and False)

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    return t


def _default_error(msg: str) -> None:
    app = Gtk.Application.get_default()
    win = app.get_active_window() if app else None
    alert(win, "Something went wrong", msg)


def on_main(func: Callable, *args) -> None:
    """Call func(*args) on the GTK main loop (from any thread)."""
    GLib.idle_add(lambda: func(*args) and False)


# ------------------------------------------------------------------------------------------------
# Dialogs


def alert(parent, heading: str, body: str = "", responses=(("ok", "OK"),), default: str | None = None,
          destructive: str | None = None, suggested: str | None = None, callback: Callable | None = None,
          extra: Gtk.Widget | None = None) -> Adw.AlertDialog:
    d = Adw.AlertDialog(heading=heading, body=body)
    for rid, label in responses:
        d.add_response(rid, label)
    if destructive:
        d.set_response_appearance(destructive, Adw.ResponseAppearance.DESTRUCTIVE)
    if suggested:
        d.set_response_appearance(suggested, Adw.ResponseAppearance.SUGGESTED)
    d.set_default_response(default or responses[-1][0])
    d.set_close_response(responses[0][0])
    if extra is not None:
        d.set_extra_child(extra)
    if callback:
        d.connect("response", lambda _d, r: callback(r))
    d.present(parent)
    return d


def ask_password(parent, heading: str, body: str, callback: Callable[[str | None], None]) -> None:
    entry = Gtk.PasswordEntry(show_peek_icon=True, activates_default=True)
    entry.set_placeholder_text("Password")

    def done(response):
        callback(entry.get_text() if response == "unlock" else None)

    d = alert(parent, heading, body, (("cancel", "Cancel"), ("unlock", "Unlock")), default="unlock",
              suggested="unlock", callback=done, extra=entry)
    d.set_focus(entry)


def toast(widget: Gtk.Widget, text: str) -> None:
    root = widget.get_root()
    overlay = getattr(root, "toast_overlay", None)
    if overlay is not None:
        overlay.add_toast(Adw.Toast(title=text, timeout=4))


def open_folder(path: Path) -> None:
    Gio.AppInfo.launch_default_for_uri(Path(path).as_uri(), None)


# ------------------------------------------------------------------------------------------------
# Widgets


def label(text: str = "", css: tuple[str, ...] = (), wrap: bool = True, xalign: float = 0.0,
          selectable: bool = False) -> Gtk.Label:
    lab = Gtk.Label(label=text, xalign=xalign, wrap=wrap, selectable=selectable)
    if wrap:
        lab.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
    for c in css:
        lab.add_css_class(c)
    return lab


def button(text: str, on_click: Callable | None = None, css: tuple[str, ...] = (), icon: str | None = None,
           tooltip: str | None = None) -> Gtk.Button:
    if icon and text:
        content = Adw.ButtonContent(label=text, icon_name=icon)
        b = Gtk.Button(child=content)
    elif icon:
        b = Gtk.Button(icon_name=icon)
    else:
        b = Gtk.Button(label=text)
    for c in css:
        b.add_css_class(c)
    if tooltip:
        b.set_tooltip_text(tooltip)
    if on_click:
        b.connect("clicked", lambda *_: on_click())
    return b


def row(title: str, subtitle: str = "", icon: str | None = None, suffix: Gtk.Widget | None = None,
        activatable: bool = False) -> Adw.ActionRow:
    r = Adw.ActionRow(title=GLib.markup_escape_text(title), subtitle=GLib.markup_escape_text(subtitle))
    r.set_subtitle_lines(3)
    if icon:
        r.add_prefix(Gtk.Image(icon_name=icon))
    if suffix is not None:
        r.add_suffix(suffix)
    r.set_activatable(activatable)
    return r


def clear(container) -> None:
    """Remove every child of a box / list box / preferences group."""
    if isinstance(container, Adw.PreferencesGroup):
        for w in list(getattr(container, "_rows", [])):
            container.remove(w)
        container._rows = []
        return
    child = container.get_first_child()
    while child is not None:
        nxt = child.get_next_sibling()
        container.remove(child)
        child = nxt


def group_add(group: Adw.PreferencesGroup, widget: Gtk.Widget) -> Gtk.Widget:
    """PreferencesGroup.add that remembers rows, so clear() can remove them later."""
    group.add(widget)
    if not hasattr(group, "_rows"):
        group._rows = []
    group._rows.append(widget)
    return widget


def page_with_header(title: str, content: Gtk.Widget, header_end: list[Gtk.Widget] = (),
                     bottom: Gtk.Widget | None = None) -> Adw.ToolbarView:
    tv = Adw.ToolbarView()
    hb = Adw.HeaderBar()
    hb.set_title_widget(Adw.WindowTitle(title=title))
    for w in header_end:
        hb.pack_end(w)
    tv.add_top_bar(hb)
    tv.set_content(content)
    if bottom is not None:
        tv.add_bottom_bar(bottom)
    return tv


def scrolled(child: Gtk.Widget) -> Gtk.ScrolledWindow:
    sw = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
    sw.set_child(child)
    return sw


def clamp(child: Gtk.Widget, size: int = 760) -> Adw.Clamp:
    c = Adw.Clamp(maximum_size=size, tightening_threshold=size - 100)
    c.set_child(child)
    return c


def vbox(spacing: int = 12, margin: int = 0, children=()) -> Gtk.Box:
    b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=spacing)
    if margin:
        for side in ("top", "bottom", "start", "end"):
            getattr(b, f"set_margin_{side}")(margin)
    for c in children:
        b.append(c)
    return b


def hbox(spacing: int = 12, children=(), halign=Gtk.Align.FILL) -> Gtk.Box:
    b = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=spacing, halign=halign)
    for c in children:
        b.append(c)
    return b


def when(iso: str | None) -> str:
    """'Today at 14:02', 'Yesterday at 09:10', '3 days ago', or a date."""
    if not iso:
        return "Never"
    try:
        t = _dt.datetime.fromisoformat(iso)
    except ValueError:
        return iso
    now = _dt.datetime.now(t.tzinfo)
    days = (now.date() - t.date()).days
    if days == 0:
        return f"Today at {t:%H:%M}"
    if days == 1:
        return f"Yesterday at {t:%H:%M}"
    if days < 7:
        return f"{days} days ago"
    return f"{t:%d %B %Y}"


def stamp_to_text(stamp: str) -> str:
    """'2026-10-10_143005' -> '10 October 2026, 14:30'."""
    try:
        return f"{_dt.datetime.strptime(stamp, '%Y-%m-%d_%H%M%S'):%d %B %Y, %H:%M}"
    except ValueError:
        return stamp


# ------------------------------------------------------------------------------------------------
# App state


class AppState(GObject.Object):
    """The configuration and the backup drive's state, shared by all pages.
    Emits 'changed' whenever the drive status may have changed."""

    __gsignals__ = {"changed": (GObject.SignalFlags.RUN_FIRST, None, ())}

    def __init__(self):
        super().__init__()
        self.cfg = Config.load()
        self.target: Target | None = None
        self.status = "none"       # none | disconnected | locked | ready
        self.busy = False          # a backup/restore/rebuild is running
        self.monitor = Gio.VolumeMonitor.get()
        for sig in ("mount-added", "mount-removed", "volume-added", "volume-removed"):
            self.monitor.connect(sig, lambda *_: GLib.timeout_add(800, self._refresh_once))

    def _refresh_once(self) -> bool:
        self.refresh()
        return False

    @property
    def access(self) -> dict:
        try:
            tid = Target.select(self.cfg)
        except DeucalionError:
            return {}
        return self.cfg["targets"][tid].get("access") or {}

    @property
    def target_name(self) -> str:
        try:
            return self.cfg["targets"][Target.select(self.cfg)]["name"]
        except DeucalionError:
            return ""

    def refresh(self) -> None:
        self.cfg = Config.load()
        self.target = None
        if not self.cfg.get("targets"):
            self.status = "none"
        else:
            try:
                self.target = Target.find(self.cfg)
                self.status = "ready"
            except DeucalionError:
                self.status = "disconnected"
                access = self.access
                if access.get("method", "none") != "none":
                    try:
                        from ..drivesetup import DriveSetup
                        DriveSetup(self.cfg, out=lambda s: None).locate(access)
                        self.status = "locked"
                    except DeucalionError:
                        pass
        self.emit("changed")

    def set_busy(self, busy: bool) -> None:
        self.busy = busy
        self.emit("changed")

    def free_text(self) -> str:
        if self.target is None:
            return ""
        return f"{human_size(self.target.free_bytes())} free"
