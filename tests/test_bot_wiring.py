import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bootstrap
bootstrap.setup()
import unittest

import config

config.BOT_TOKEN = "123456:dummy-for-tests"


class TestBotWiring(unittest.TestCase):
    def test_imports(self):
        import bot  # noqa: F401  (must not trigger run)
        import db
        from handlers import (admin, anim_ui, pipeline, profiles, start,  # noqa: F401
                              settings_ui, tools)
        from core import (animations, colors, fonts, media, renderer,  # noqa: F401
                          settings, styles, textvars, video_engine)

    def test_application_builds_and_registers(self):
        from telegram.ext import ApplicationBuilder
        from handlers import (admin, anim_ui, pipeline, profiles, start,
                              settings_ui, tools)
        app = ApplicationBuilder().token("123456:dummy").build()
        start.register(app)
        settings_ui.register(app)
        anim_ui.register(app)
        profiles.register(app)
        tools.register(app)
        admin.register(app)
        pipeline.register(app)
        total = sum(len(v) for v in app.handlers.values())
        self.assertGreaterEqual(total, 45)

    def test_command_menu(self):
        from bot import COMMANDS
        self.assertLessEqual(len(COMMANDS), 100)
        names = [c for c, _ in COMMANDS]
        self.assertEqual(len(names), len(set(names)))
        for c, desc in COMMANDS:
            self.assertTrue(1 <= len(c) <= 32)
            self.assertTrue(c.islower())
            self.assertTrue(desc)

    def test_callback_data_fits_64_bytes(self):
        from core.animations import REGISTRY
        from handlers.settings_ui import PARAMS, _choices
        samples = ["st:main", "st:go:size_pct", "st:adj:anim_speed:-1.0",
                   "st:tgl:box", "st:clr:stroke_color", "st:chc:position:br",
                   "st:rst:yes", "an:menu", "an:search", "pf:menu",
                   "pf:save", "act:wm", "act:prev", "cnl"]
        for a in REGISTRY.values():
            samples += ["an:cat:%s:99" % a.cat, "an:sel:%s" % a.id,
                        "an:demo:%s" % a.id, "an:use:%s" % a.id]
        for p in PARAMS:
            samples.append("st:go:%s" % p)
            samples.append("st:adj:%s:-0.05" % p)
            for val, _ in _choices(p):
                samples.append("st:chc:%s:%s" % (p, val))
        for s in samples:
            self.assertLessEqual(len(s.encode("utf-8")), 64,
                                 "callback too long: %s" % s)

    def test_feature_count_50_plus(self):
        from handlers.start import FEATURES
        total = sum(len(items) for _, items in FEATURES)
        self.assertGreaterEqual(total, 50)

    def test_animation_count_100_plus(self):
        from core.animations import REGISTRY
        self.assertGreaterEqual(len(REGISTRY), 100)

    def test_help_texts_exist(self):
        from handlers.start import WELCOME, HELP
        self.assertIn("AquaMark", WELCOME)
        self.assertIn("settings", HELP)

    def test_tools_usage_docs(self):
        from handlers.tools import USAGE, _TOOLS
        self.assertEqual(set(USAGE.keys()), set(_TOOLS.keys()))
        self.assertGreaterEqual(len(USAGE), 15)

    def test_preflight_runs(self):
        import subprocess
        r = subprocess.run(
            [sys.executable, "bot.py", "--check"],
            capture_output=True, text=True, timeout=120,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        # BOT_TOKEN missing in test env is the only acceptable failure
        self.assertIn("preflight", r.stdout)
        self.assertIn("Animations", r.stdout)

    def test_version_flag(self):
        import subprocess
        r = subprocess.run(
            [sys.executable, "bot.py", "--version"],
            capture_output=True, text=True, timeout=60,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.assertIn("AquaMark", r.stdout)



    def test_welcome_banner(self):
        """The /start banner image ships with the bot and is wired in."""
        import os
        import config
        from handlers import start
        self.assertTrue(os.path.isfile(config.BRAND_IMG),
                        "assets/branding/welcome.png missing")
        self.assertLess(os.path.getsize(config.BRAND_IMG), 8 * 1048576,
                        "banner too large for Telegram photo upload")
        self.assertIn("reply_photo", open(
            os.path.join(os.path.dirname(start.__file__), "start.py"),
            encoding="utf-8").read(), "start.py must send the banner")


if __name__ == "__main__":
    unittest.main()
