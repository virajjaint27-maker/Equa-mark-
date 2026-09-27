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
