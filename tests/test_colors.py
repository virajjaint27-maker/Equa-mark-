import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import unittest

from core import colors


class TestColors(unittest.TestCase):
    def test_hex_formats(self):
        self.assertEqual(colors.parse_color("#FF8000"), (255, 128, 0, 255))
        self.assertEqual(colors.parse_color("ff8000"), (255, 128, 0, 255))
        self.assertEqual(colors.parse_color("#f80"), (255, 136, 0, 255))
        self.assertEqual(colors.parse_color("#f80a"), (255, 136, 0, 170))
        self.assertEqual(colors.parse_color("#FF800080"), (255, 128, 0, 128))

    def test_rgb_formats(self):
        self.assertEqual(colors.parse_color("rgb(1,2,3)"), (1, 2, 3, 255))
        self.assertEqual(colors.parse_color("rgba(1,2,3,0.5)"), (1, 2, 3, 128))
        self.assertEqual(colors.parse_color("10, 20, 30"), (10, 20, 30, 255))

    def test_named(self):
        self.assertEqual(colors.parse_color("gold"), (255, 215, 0, 255))
        self.assertEqual(colors.parse_color("GOLD"), (255, 215, 0, 255))
        self.assertEqual(colors.parse_color("deep sky blue"), (0, 191, 255, 255))
        self.assertEqual(colors.parse_color("DeepSkyBlue"), (0, 191, 255, 255))
        self.assertGreater(len(colors.NAMED), 140)

    def test_clamping(self):
        r, g, b, a = colors.parse_color("rgb(300,-5,999)")
        self.assertEqual((r, g, b), (255, 0, 255))

    def test_invalid(self):
        with self.assertRaises(colors.ColorError):
            colors.parse_color("notacolor")
        with self.assertRaises(colors.ColorError):
            colors.parse_color("")
        self.assertEqual(colors.parse_color("notacolor", default=(1, 2, 3, 4)),
                         (1, 2, 3, 4))

    def test_gradient(self):
        c1, c2 = colors.parse_gradient("#fff>#000")
        self.assertEqual(c1, (255, 255, 255, 255))
        self.assertEqual(c2, (0, 0, 0, 255))
        c1, c2 = colors.parse_gradient("gold")
        self.assertIsNone(c2)
        with self.assertRaises(colors.ColorError):
            colors.parse_gradient("a>b>c")

    def test_to_hex(self):
        self.assertEqual(colors.to_hex((255, 0, 16, 255)), "#FF0010")


if __name__ == "__main__":
    unittest.main()
