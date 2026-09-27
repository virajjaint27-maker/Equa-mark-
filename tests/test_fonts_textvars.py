import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import unittest

from core import fonts, textvars


class TestFonts(unittest.TestCase):
    def test_registry_loads(self):
        self.assertGreaterEqual(len(fonts.FONTS), 9)
        for fid in fonts.FONTS:
            path = fonts.font_path(fid)
            self.assertTrue(path and os.path.isfile(path),
                            "missing font file for %s" % fid)
            f = fonts.get_font(fid, 40)
            self.assertIsNotNone(f.getbbox("Ag"))

    def test_default_font(self):
        self.assertIn(fonts.DEFAULT_FONT_ID, fonts.FONTS)

    def test_script_routing(self):
        # latin stays with chosen font
        self.assertEqual(fonts.resolve_font_id("montserrat", "H"),
                         "montserrat")
        # devanagari routed
        self.assertEqual(fonts.resolve_font_id("montserrat", "म"), "devanagari")
        # arabic routed
        self.assertEqual(fonts.resolve_font_id("montserrat", "م"), "arabic")
        # emoji routed
        self.assertEqual(fonts.resolve_font_id("montserrat", "🔥"), "emoji")
        # cyrillic only dejavu
        self.assertEqual(fonts.resolve_font_id("bebas", "Ж"), "dejavu-bold")

    def test_segments(self):
        segs = fonts.segments("Hello", "montserrat")
        self.assertEqual(segs, [("montserrat", "Hello")])
        segs = fonts.segments("Hi म", "montserrat")
        self.assertEqual(len(segs), 2)
        self.assertEqual(segs[0], ("montserrat", "Hi "))
        self.assertEqual(segs[1], ("devanagari", "म"))

    def test_variable_weight(self):
        f = fonts.get_font("montserrat", 40)  # axis default 700
        self.assertIsNotNone(f)


class FakeUser(object):
    first_name = "Rahul"
    username = "rahul_x"


class FakeChat(object):
    title = "Designers Hub"


class TestTextVars(unittest.TestCase):
    def test_no_braces(self):
        self.assertEqual(textvars.resolve("plain text"), "plain text")

    def test_date_vars(self):
        out = textvars.resolve("{year}", None, None, None)
        self.assertRegex(out, r"^\d{4}$")
        self.assertIn(textvars.resolve("{month}"), 
                      ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul",
                       "Aug", "Sep", "Oct", "Nov", "Dec"])

    def test_user_vars(self):
        self.assertEqual(textvars.resolve("{user}", FakeUser(), None), "Rahul")
        self.assertEqual(textvars.resolve("{username}", FakeUser(), None),
                         "@rahul_x")
        self.assertEqual(textvars.resolve("{chat}", FakeUser(), FakeChat()),
                         "Designers Hub")

    def test_count_rand(self):
        self.assertEqual(textvars.resolve("{count}", None, None, 7), "7")
        self.assertRegex(textvars.resolve("{rand}", None, None),
                         r"^\d{6}$")
        self.assertRegex(textvars.resolve("{rand100}", None, None),
                         r"^\d{1,2}$")

    def test_unknown_left_alone(self):
        self.assertEqual(textvars.resolve("{nope}", None, None), "{nope}")


if __name__ == "__main__":
    unittest.main()
