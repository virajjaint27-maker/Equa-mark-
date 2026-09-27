"""Tests for core/uifont.py — the small-caps UI font."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import unittest
from unittest import mock

import bootstrap
bootstrap.setup()

import config
from core import cemoji, uifont


class TestUIFont(unittest.TestCase):
    def test_exact_requested_style(self):
        # the owner's literal example
        self.assertEqual(uifont.stylize("Travel vote"), "𝐓ʀᴀᴠᴇʟ ᴠᴏᴛᴇ")

    def test_lowercase_map(self):
        self.assertEqual(uifont.stylize("abcxyz"), "ᴀʙᴄxʏᴢ")  # x has no cap

    def test_uppercase_bold(self):
        self.assertEqual(uifont.stylize("ABC"), "𝐀𝐁𝐂")

    def test_protects_tokens_and_markup(self):
        src = "[[water]] <b>Bold</b> <code>#38B6FF</code> /start @user #tag https://t.me/x"
        out = uifont.stylize(src)
        self.assertIn("[[water]]", out)
        self.assertIn("<b>", out)
        self.assertIn("</b>", out)
        self.assertIn("<code>#38B6FF</code>", out)
        self.assertIn("/start", out)
        self.assertIn("@user", out)
        self.assertIn("#tag", out)
        self.assertIn("https://t.me/x", out)
        # non-protected words are styled
        self.assertIn("𝐁ᴏʟᴅ", out)

    def test_non_latin_untouched(self):
        src = "हिन्दी العربية 123 💧🧭 ▓░ 42%"
        self.assertEqual(uifont.stylize(src), src)

    def test_switch_off(self):
        with mock.patch.object(config, "USE_UI_FONT", False):
            self.assertEqual(uifont.stylize("Hello"), "Hello")

    def test_prepare_applies_font(self):
        p = cemoji.prepare("[[water]] Hello world")
        self.assertEqual(p.text, "💧 𝐇ᴇʟʟᴏ ᴡᴏʀʟᴅ")

    def test_expand_applies_font(self):
        self.assertEqual(cemoji.expand("[[water]] Hello"), "💧 𝐇ᴇʟʟᴏ")

    def test_entity_offsets_valid_after_font(self):
        # <b>Hi</b> <i>world</i> stylizes to "𝐇ɪ ᴡᴏʀʟᴅ"; entities must span
        # exactly the stylized substrings in UTF-16 units (𝐇 is astral = 2)
        p = cemoji.prepare("<b>Hi</b> <i>world</i>")
        text = p.text
        self.assertEqual(text, "𝐇ɪ ᴡᴏʀʟᴅ")
        ents = p.fmt_entities or []
        self.assertEqual(len(ents), 2)

        units = text.encode("utf-16-le")   # 2 bytes per UTF-16 unit

        def span(e):
            return units[e.offset * 2:(e.offset + e.length) * 2] \
                .decode("utf-16-le", "replace")

        self.assertEqual(span(ents[0]), "𝐇ɪ")     # bold — includes the
        self.assertGreater(ents[0].length, 2)     # astral 𝐇 (2 units)
        self.assertEqual(span(ents[1]), "ᴡᴏʀʟᴅ")  # italic

    def test_math_bold_chars_are_astral(self):
        # 𝐀..𝐙 live beyond the BMP: 2 UTF-16 units each
        self.assertGreater(ord("𝐓"), 0xFFFF)
        self.assertEqual(len("𝐓".encode("utf-16-le")), 4)

    def test_buttons_styled(self):
        from handlers import common as H
        b = H.btn("Watermark it!", "act:wm")
        self.assertIn("𝐖ᴀᴛᴇʀᴍᴀʀᴋ ɪᴛ!", b.text)

if __name__ == "__main__":
    unittest.main()
