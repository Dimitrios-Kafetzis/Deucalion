"""The documentation's screenshot mode: how DEUCALION_SCREENSHOT_PAGES entries are read."""

import unittest

from deucalion.gui import shots as app


class ScreenshotEntries(unittest.TestCase):
    def test_plain_pages(self):
        self.assertEqual(app.parse_screenshot_entries("overview,backup:review", 1000),
                         [("overview", "overview", "", "", 1000), ("backup-review", "backup", "review", "", 1000)])

    def test_names_arguments_and_waits(self):
        got = app.parse_screenshot_entries("first=restore:browse(home/Documents)@2500; _=win:close; drives", 900)
        self.assertEqual(got, [("first", "restore", "browse", "home/Documents", 2500),
                               ("_", "win", "close", "", 900),
                               ("drives", "drives", "", "", 900)])

    def test_argument_with_separators(self):
        got = app.parse_screenshot_entries("backup:some(Documents|Pictures)")
        self.assertEqual(got[0][1:4], ("backup", "some", "Documents|Pictures"))

if __name__ == "__main__":
    unittest.main()
