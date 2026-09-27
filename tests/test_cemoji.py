"""Tests for the custom-emoji system (core/cemoji.py) — UTF-16 offsets,
token expansion, HTML decoding, button icons, and the send fallback ladder."""
import asyncio
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import unittest

import bootstrap
bootstrap.setup()

import config
from core import cemoji as CE
from core import uifont
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, MessageEntity
from telegram.error import TelegramError
from handlers import common as H


def u16(s):
    return len(s.encode("utf-16-le")) // 2


class CEBase(unittest.TestCase):
    """Inject a real ID for one key; restore module state after each test."""

    def setUp(self):
        self._saved = (dict(CE.CUSTOM_EMOJIS), CE._tripped, CE._trip_count)
        CE.CUSTOM_EMOJIS["water"]["id"] = "5312345678901234567"
        CE.CUSTOM_EMOJIS["settings"]["id"] = "999000111222333444"
        CE._tripped = False
        CE._trip_count = 0

    def tearDown(self):
        emojis, tripped, count = self._saved
        CE.CUSTOM_EMOJIS.clear()
        CE.CUSTOM_EMOJIS.update(emojis)
        CE._tripped = tripped
        CE._trip_count = count


class TestPrepare(CEBase):
    def test_inactive_keeps_html_and_expands_tokens(self):
        CE._tripped = True  # force inactive without touching config
        p = CE.prepare("[[water]] <b>Hi</b> [[check]]")
        self.assertEqual(p.text, uifont.stylize("💧 <b>Hi</b> ✅"))
        self.assertIsNone(p.fmt_entities)
        self.assertFalse(p.has_custom)

    def test_active_offsets_are_utf16(self):
        p = CE.prepare("[[water]] <b>Aqua</b>Mark [[rocket]] [[nope]]")
        self.assertEqual(p.text, uifont.stylize("💧 AquaMark 🚀 [[nope]]"))
        b = p.fmt_entities[0]
        self.assertEqual((b.type, b.offset, b.length),
                     ("bold", 3, u16(uifont.stylize("Aqua"))))
        c = p.custom_entities[0]
        self.assertEqual(c.type, "custom_emoji")
        self.assertEqual(c.custom_emoji_id, "5312345678901234567")
        # 💧 is one Python char but TWO UTF-16 units
        self.assertEqual((c.offset, c.length), (0, 2))

    def test_entity_wraps_exactly_one_emoji(self):
        for key, expect in (("water", "💧"), ("settings", "⚙️")):
            p = CE.prepare("abc [[%s]] xyz" % key)
            e = p.custom_entities[0]
            seg = p.text.encode("utf-16-le")[
                e.offset * 2:(e.offset + e.length) * 2].decode("utf-16-le")
            self.assertEqual(seg, expect)
            self.assertEqual(e.length, u16(expect))

    def test_unknown_token_left_verbatim(self):
        p = CE.prepare("[[notakey]] stays")
        self.assertEqual(p.text, uifont.stylize("[[notakey]] stays"))
        self.assertFalse(p.has_custom)

    def test_placeholder_id_never_produces_entity(self):
        p = CE.prepare("[[check]] x")  # check still has PLACEHOLDER id
        self.assertIn("✅", p.text)
        self.assertFalse(p.has_custom)

    def test_nested_link_code_entities(self):
        p = CE.prepare(
            '🎬 <code>x[[check]]y</code> <a href="https://t.me">L[[water]]</a>'
            " <b>bo<i>ld</i></b>")
        kinds = sorted(e.type for e in p.fmt_entities)
        self.assertEqual(kinds, ["bold", "code", "italic", "text_link"])
        for e in p.fmt_entities:
            seg = p.text.encode("utf-16-le")[
                e.offset * 2:(e.offset + e.length) * 2].decode("utf-16-le")
            self.assertTrue(seg)  # non-empty span on the final text

    def test_malformed_html_tolerated(self):
        p = CE.prepare("</b> oops <b>unclosed [[water]]")
        self.assertIn("💧", p.text)

    def test_expand_for_captions(self):
        self.assertEqual(CE.expand("a [[water]] b"), uifont.stylize("a 💧 b"))


class TestButtons(CEBase):
    def test_icon_button_payload(self):
        b = CE.icon_button("Settings", callback_data="st:main",
                           icon_custom_emoji_id=CE.icon_id("water"))
        d = b.to_dict()
        self.assertEqual(d["icon_custom_emoji_id"], "5312345678901234567")
        self.assertEqual(d["text"], "Settings")
        self.assertEqual(d["callback_data"], "st:main")

    def test_markup_has_icons_and_strip(self):
        from handlers import common as H
        b = H.btn("Settings", "st:main", ce="water")
        self.assertTrue(CE.markup_has_icons(H.kb([[b]])))
        stripped = CE.strip_icons(H.kb([[b]]))
        self.assertFalse(CE.markup_has_icons(stripped))
        flat = stripped.inline_keyboard[0][0]
        self.assertEqual(flat.text, uifont.stylize("Settings"))

    def test_inactive_btn_prefixes_unicode_emoji(self):
        CE._tripped = True
        from handlers import common as H
        b = H.btn("Settings", "st:main", ce="water")
        self.assertEqual(b.text, uifont.stylize("💧 Settings"))
        self.assertNotIsInstance(b, CE.IconInlineButton)

    def test_active_btn_is_icon_button(self):
        from handlers import common as H
        b = H.btn("Settings", "st:main", ce="water")
        self.assertIsInstance(b, CE.IconInlineButton)


class FakeMessage:
    """Records reply_text calls; fails attempts that carry custom-emoji
    entities or icon buttons (like Telegram would for a non-Fragment bot)."""

    def __init__(self, fail_custom=True, fail_icons=True):
        self.calls = []
        self.fail_custom = fail_custom
        self.fail_icons = fail_icons

    @staticmethod
    def _has_custom(ents):
        return any(e.type == "custom_emoji" for e in (ents or []))

    async def reply_text(self, text, **kw):
        ents = kw.get("entities")
        markup = kw.get("reply_markup")
        icons = CE.markup_has_icons(markup)
        self.calls.append((text, ents, icons))
        if self.fail_custom and self._has_custom(ents):
            raise TelegramError("Bad Request: CUSTOM_EMOJI_INVALID")
        if self.fail_icons and icons:
            raise TelegramError("Bad Request: button icon not allowed")
        return self


class TestFallbackLadder(CEBase):
    def setUp(self):
        super().setUp()
        self.loop = asyncio.new_event_loop()

    def tearDown(self):
        self.loop.close()
        super().tearDown()

    def test_level1_success(self):
        m = FakeMessage(fail_custom=False, fail_icons=False)
        self.loop.run_until_complete(CE.reply_text(
            m, "[[water]] <b>Go</b>"))
        self.assertEqual(len(m.calls), 1)
        text, ents, icons = m.calls[0]
        self.assertEqual(text, uifont.stylize("💧 Go"))
        self.assertEqual(len(ents), 2)  # bold + custom_emoji

    def test_demotes_to_formatting_only(self):
        m = FakeMessage(fail_custom=True, fail_icons=False)
        self.loop.run_until_complete(CE.reply_text(
            m, "[[water]] <b>Go</b>"))
        self.assertEqual(len(m.calls), 2)
        (t1, e1, _), (t2, e2, _) = m.calls
        self.assertEqual(t1, t2)
        self.assertEqual(len(e1), 2)
        self.assertEqual([e.type for e in e2], ["bold"])  # custom dropped
        # a successful demotion counts toward the circuit breaker
        self.assertEqual(CE._trip_count, 1)

    def test_demotes_all_the_way_to_plain(self):
        class FailAllEntities(FakeMessage):
            async def reply_text(self, text, **kw):
                if kw.get("entities"):
                    self.calls.append(
                        (text, kw.get("entities"),
                         CE.markup_has_icons(kw.get("reply_markup"))))
                    raise TelegramError("Bad Request: entity not allowed")
                return await FakeMessage.reply_text(self, text, **kw)
        m = FailAllEntities(fail_custom=True, fail_icons=True)
        self.loop.run_until_complete(CE.reply_text(
            m, "[[water]] <b>Go</b>",
            reply_markup=H.kb([[H.btn("Settings", "st:main", ce="water")]])))
        self.assertEqual(len(m.calls), 3)  # full -> fmt -> plain
        text, ents, icons = m.calls[-1]
        self.assertEqual(text, uifont.stylize("💧 Go"))
        self.assertIsNone(ents)
        self.assertFalse(icons)

    def test_icons_only_message_demotes(self):
        markup = H.kb([[H.btn("Settings", "st:main", ce="water")]])
        m = FakeMessage(fail_custom=True, fail_icons=True)
        self.loop.run_until_complete(CE.reply_text(
            m, "plain text", reply_markup=markup))
        self.assertEqual(len(m.calls), 2)
        self.assertTrue(m.calls[0][2])    # first attempt had icons
        self.assertFalse(m.calls[1][2])   # retry without

    def test_benign_error_not_demoted(self):
        class Benign(FakeMessage):
            async def reply_text(self, text, **kw):
                self.calls.append((text, kw.get("entities"), False))
                raise TelegramError("Bad Request: message is not modified")
        m = Benign()
        with self.assertRaises(TelegramError):
            self.loop.run_until_complete(CE.reply_text(m, "[[water]] x"))
        self.assertEqual(len(m.calls), 1)  # no retry

    def test_inactive_path_untouched(self):
        CE._tripped = True
        m = FakeMessage()
        self.loop.run_until_complete(CE.reply_text(
            m, "[[water]] <b>Hi</b>", parse_mode="HTML"))
        self.assertEqual(len(m.calls), 1)
        text, ents, icons = m.calls[0]
        self.assertEqual(text, uifont.stylize("💧 <b>Hi</b>"))  # HTML kept

    def test_circuit_breaker_trips(self):
        CE._trip_count = CE._TRIP_AT - 1
        CE.note_rejection()
        self.assertTrue(CE._tripped)
        self.assertFalse(CE.active())


class TestArchitecture(unittest.TestCase):
    def test_no_emoji_ids_outside_module(self):
        """Raw custom emoji ID literals must live only in core/cemoji.py."""
        import glob
        import re
        offenders = []
        for path in glob.glob("handlers/*.py") + glob.glob("core/*.py"):
            if path.replace(os.sep, "/").endswith("cemoji.py"):
                continue
            with open(path, encoding="utf-8") as fh:
                src = fh.read()
            if CE.PLACEHOLDER in src or re.search(r'"\d{15,}"', src):
                offenders.append(path)
        self.assertEqual(offenders, [])

    def test_tokens_defined_for_all_used_keys(self):
        import re
        used = set()
        for f in ("handlers/start.py", "handlers/pipeline.py",
                  "handlers/settings_ui.py", "handlers/common.py"):
            with open(f, encoding="utf-8") as fh:
                src = fh.read()
            used |= set(re.findall(r"\[\[([a-z0-9_]+)\]\]", src))
        missing = used - set(CE.CUSTOM_EMOJIS)
        self.assertEqual(missing, set(),
                         "tokens without a CUSTOM_EMOJIS entry: %s" % missing)


if __name__ == "__main__":
    unittest.main()
