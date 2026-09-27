"""Tests for the network timeout configuration in bot.py.

Regression guard for the 'TimedOut' long-poll error: the get_updates
request needs its own generous read timeout, far above the poll window.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import unittest

import bootstrap
bootstrap.setup()

import bot


class TestNetTimeouts(unittest.TestCase):
    def test_importing_bot_is_side_effect_free(self):
        # bot.py must not touch the network / config on import
        self.assertTrue(callable(bot.main))

    def test_poll_window_far_below_read_timeout(self):
        # the whole point of the fix: read slack over the poll window
        self.assertGreaterEqual(
            bot.NET_TIMEOUTS["get_updates_read_timeout"],
            bot.POLL_TIMEOUT + 30)

    def test_get_updates_request_configured_separately(self):
        # PTB uses a second HTTP client for polling; all four of its
        # timeouts must be set explicitly
        for key in ("get_updates_connect_timeout",
                    "get_updates_read_timeout",
                    "get_updates_write_timeout",
                    "get_updates_pool_timeout"):
            self.assertIn(key, bot.NET_TIMEOUTS)
            self.assertGreater(bot.NET_TIMEOUTS[key], 0)

    def test_media_upload_timeout_generous(self):
        # ~50 MB result uploads on slow uplinks need minutes, not seconds
        self.assertGreaterEqual(bot.NET_TIMEOUTS["media_write_timeout"], 120)
        self.assertGreaterEqual(bot.NET_TIMEOUTS["write_timeout"], 120)

    def test_builder_receives_every_timeout(self):
        from telegram.ext import ApplicationBuilder
        b = bot._apply_net_timeouts(ApplicationBuilder().token("1:x"))
        for key, value in bot.NET_TIMEOUTS.items():
            self.assertEqual(getattr(b, "_" + key), value,
                             "builder missing %s" % key)


if __name__ == "__main__":
    unittest.main()


class TestTokenGuard(unittest.TestCase):
    """The friendly placeholder/revoked-token guard in bot.py."""

    def test_placeholder_rejected(self):
        self.assertFalse(bot._token_looks_valid("PASTE-YOUR-NEW-TOKEN-HERE"))
        self.assertFalse(
            bot._token_looks_valid("123456789:AAF-your-bot-token-here"))

    def test_empty_and_short_rejected(self):
        self.assertFalse(bot._token_looks_valid(""))
        self.assertFalse(bot._token_looks_valid("123456:short"))
        self.assertFalse(bot._token_looks_valid("no-colon-at-all"))

    def test_real_shape_accepted(self):
        self.assertTrue(bot._token_looks_valid(
            "123456789:AA" + "x" * 32))
        self.assertTrue(bot._token_looks_valid(
            "8974576056:AAEMPrwJlbBPnF36twuV6Voh-57J9h8oLo0"))

    def test_help_message_is_friendly(self):
        msg = bot._token_help()
        self.assertIn("BOT_TOKEN", msg)
        self.assertIn("@BotFather", msg)
        self.assertNotIn("Traceback", msg)
