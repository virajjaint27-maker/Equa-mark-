"""Tests for the /start message sequence: banner image -> text -> compass."""
import asyncio
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import unittest
from unittest import mock

import bootstrap
bootstrap.setup()

import config
from handlers import start


class FakeUser:
    id = 4242
    first_name = "Tester"
    username = "tester"


class FakeMessage:
    def __init__(self):
        self.calls = []  # (method, args, kwargs)

    async def reply_photo(self, *a, **kw):
        self.calls.append(("reply_photo", a, kw))

    async def reply_text(self, *a, **kw):
        self.calls.append(("reply_text", a, kw))


class FakeUpdate:
    def __init__(self, message):
        self.message = message
        self.effective_user = FakeUser()


class TestStartSequence(unittest.TestCase):
    def setUp(self):
        self.msg = FakeMessage()
        self.update = FakeUpdate(self.msg)
        # don't touch the real database from a unit test
        patcher = mock.patch.object(start.db, "ensure_user")
        self.mock_ensure = patcher.start()
        self.addCleanup(patcher.stop)

    def test_start_sends_image_text_then_compass(self):
        asyncio.run(start.cmd_start(self.update, None))
        kinds = [c[0] for c in self.msg.calls]
        # exactly three sends: photo, welcome text, compass emoji
        self.assertEqual(kinds, ["reply_photo", "reply_text", "reply_text"])

        method, args, kw = self.msg.calls[0]
        from core import uifont
        self.assertEqual(kw.get("caption"),
                         uifont.stylize(config.WELCOME_CAPTION))

        method, args, kw = self.msg.calls[1]
        self.assertIn(uifont.stylize("AquaMark"), args[0])
        self.assertEqual(kw.get("parse_mode"), "HTML")

        # the final message is the compass emoji alone — nothing else
        method, args, kw = self.msg.calls[2]
        self.assertEqual(args[0], "🧭")
        self.assertEqual(args[0], start.COMPASS_SIGNOFF)

    def test_compass_is_exactly_one_grapheme(self):
        # 🧭 is a single code point (U+1F9ED) with no extra whitespace
        self.assertEqual(start.COMPASS_SIGNOFF, "\U0001F9ED")
        self.assertEqual(len(start.COMPASS_SIGNOFF), 1)


if __name__ == "__main__":
    unittest.main()
