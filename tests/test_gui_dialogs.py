"""The app's dialogs, run for real with GTK's Broadway backend (nothing appears on screen).

Skipped where GTK 4 / libadwaita or gtk4-broadwayd are not installed."""

import os
import shutil
import socket
import subprocess
import sys
import textwrap
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
# Some sandboxed terminals (e.g. the VS Code snap) inject GTK settings that break GTK 4.
SNAP_VARS = ("GSETTINGS_SCHEMA_DIR", "GTK_PATH", "GTK_EXE_PREFIX", "GIO_MODULE_DIR", "GTK_IM_MODULE_FILE",
             "GDK_PIXBUF_MODULE_FILE", "GDK_PIXBUF_MODULEDIR", "LOCPATH")


def _env(display: str) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in SNAP_VARS}
    env.pop("DISPLAY", None)
    env.pop("WAYLAND_DISPLAY", None)
    env.update(GDK_BACKEND="broadway", BROADWAY_DISPLAY=f":{display}", NO_AT_BRIDGE="1",
               XDG_DATA_DIRS="/usr/local/share:/usr/share", PYTHONPATH=str(REPO))
    return env


def _free_display() -> str:
    for n in range(40, 90):  # Broadway display :n listens on TCP port 8080 + n
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", 8080 + n)) != 0:
                return str(n)
    raise unittest.SkipTest("no free Broadway display")


def _gtk_available() -> bool:
    if not shutil.which("gtk4-broadwayd"):
        return False
    probe = "import gi; gi.require_version('Gtk', '4.0'); gi.require_version('Adw', '1')"
    env = {k: v for k, v in os.environ.items() if k not in SNAP_VARS}
    return subprocess.run([sys.executable, "-c", probe], env=env, capture_output=True).returncode == 0


@unittest.skipUnless(_gtk_available(), "GTK 4 / libadwaita / gtk4-broadwayd not available")
class PasswordDialog(unittest.TestCase):
    def test_unlock_dialog_opens(self):
        """Regression: the Unlock dialog crashed (PasswordEntry has no set_placeholder_text), so no
        encrypted drive could be unlocked from the app."""
        display = _free_display()
        broadway = subprocess.Popen(["gtk4-broadwayd", f":{display}"], stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL, env=_env(display))
        self.addCleanup(broadway.wait)
        self.addCleanup(broadway.terminate)
        time.sleep(1)
        script = textwrap.dedent("""
            import sys
            from deucalion.gui.common import Adw, GLib, Gtk, ask_password
            result = {}
            app = Adw.Application(application_id="io.github.DimitriosKafetzis.DeucalionTest")

            def check(win):
                dialog = win.get_visible_dialog()
                entry = dialog.get_extra_child() if dialog else None
                result["ok"] = isinstance(entry, Gtk.PasswordEntry) and \\
                    entry.get_property("placeholder-text") == "Password"
                app.quit()

            def activate(app):
                win = Adw.ApplicationWindow(application=app)
                win.present()
                try:
                    ask_password(win, "Unlock", "Enter the password.", lambda pw: None)
                except Exception as e:
                    result["error"] = repr(e)
                    app.quit()
                    return
                GLib.timeout_add(300, lambda: check(win) and False)

            app.connect("activate", activate)
            app.run([])
            print(result)
            sys.exit(0 if result.get("ok") else 1)
        """)
        r = subprocess.run([sys.executable, "-c", script], env=_env(display), capture_output=True, text=True,
                           timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
