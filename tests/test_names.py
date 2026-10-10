import unittest

from deucalion.config import Excluder
from deucalion.names import NamePolicy, exfat_safe, fit, utf16_units


class NamesTest(unittest.TestCase):
    def test_illegal_characters_replaced_with_lookalikes(self):
        self.assertEqual(exfat_safe("a:b"), "a：b")
        self.assertEqual(exfat_safe('x*?"<>|\\y'), "x＊？＂＜＞｜＼y")
        self.assertEqual(exfat_safe("tab\there"), "tab␉here")

    def test_trailing_dots_and_spaces(self):
        self.assertEqual(exfat_safe("trail."), "trail．")
        self.assertEqual(exfat_safe("trail. "), "trail．␠")
        self.assertEqual(exfat_safe("..."), "．．．")
        self.assertEqual(exfat_safe(".hidden"), ".hidden")

    def test_windows_reserved(self):
        self.assertEqual(exfat_safe("CON"), "CON＿")
        self.assertEqual(exfat_safe("nul.txt"), "nul＿.txt")
        self.assertEqual(exfat_safe("CONSOLE"), "CONSOLE")

    def test_invalid_utf8_bytes(self):
        name = b"bad\xff".decode("utf-8", "surrogateescape")
        self.assertEqual(exfat_safe(name), "bad%FF")

    def test_long_names_fit(self):
        name = "😀" * 127 + ".txt"
        out = fit(name)
        self.assertLessEqual(utf16_units(out), 255)
        self.assertTrue(out.endswith(".txt"))
        self.assertNotEqual(fit("a" * 300), fit("a" * 299 + "b"))

    def test_choose_avoids_case_collisions(self):
        pol = NamePolicy("exfat")
        used = set()
        a = pol.choose("Notes", used)
        b = pol.choose("notes", used)
        c = pol.choose("NOTES", used)
        self.assertEqual(a, "Notes")
        self.assertEqual(b, "notes (2)")
        self.assertEqual(c, "NOTES (3)")

    def test_posix_policy_is_identity(self):
        pol = NamePolicy("posix")
        used = set()
        self.assertEqual(pol.choose("a:b", used), "a:b")
        self.assertEqual(pol.choose("A:B", used), "A:B")


class ExcluderTest(unittest.TestCase):
    def setUp(self):
        self.ex = Excluder([".cache/", "node_modules/", ".local/share/Trash/", ".config/**/Cache/",
                            "*.tmp", "snap/*/*/.cache/"])

    def test_name_anywhere(self):
        self.assertTrue(self.ex.excluded("proj/node_modules", "node_modules", True))
        self.assertFalse(self.ex.excluded("proj/node_modules", "node_modules", False))  # dir-only
        self.assertTrue(self.ex.excluded("a/b/x.tmp", "x.tmp", False))

    def test_path_patterns(self):
        self.assertTrue(self.ex.excluded(".local/share/Trash", "Trash", True))
        self.assertFalse(self.ex.excluded("Documents/.local/share/Trash", "Trash", True))
        self.assertTrue(self.ex.excluded(".config/google-chrome/Default/Cache", "Cache", True))
        self.assertTrue(self.ex.excluded(".config/Code/Cache", "Cache", True))
        self.assertFalse(self.ex.excluded("Documents/Cache", "Cache", True))

    def test_single_star_stays_in_one_folder(self):
        self.assertTrue(self.ex.excluded(".cache", ".cache", True))
        ex = Excluder(["snap/*/common/"])
        self.assertTrue(ex.excluded("snap/firefox/common", "common", True))
        self.assertFalse(ex.excluded("snap/firefox/x/common", "common", True))


if __name__ == "__main__":
    unittest.main()
