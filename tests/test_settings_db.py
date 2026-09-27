import os
import sys
import tempfile
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import unittest

import config
import db
from core.settings import DEFAULTS, normalize


class TestSettings(unittest.TestCase):
    def test_defaults_complete(self):
        s = normalize({})
        self.assertEqual(s["color"], "#FFFFFF")
        self.assertEqual(s["position"], "br")
        self.assertEqual(s["animation"], "static")
        self.assertTrue(s["auto_mode"])

    def test_clamps(self):
        s = normalize({"size_pct": 500, "opacity": -3, "anim_speed": 99,
                       "rotation": 400, "margin": -10})
        self.assertEqual(s["size_pct"], 40.0)
        self.assertEqual(s["opacity"], 0.05)
        self.assertEqual(s["anim_speed"], 4.0)
        self.assertEqual(s["rotation"], 180.0)
        self.assertEqual(s["margin"], 0.0)

    def test_bad_values_fall_back(self):
        s = normalize({"color": "notacolor", "animation": "nope",
                       "font": "nope", "position": "xx", "quality": "???"})
        self.assertEqual(s["color"], DEFAULTS["color"])
        self.assertEqual(s["animation"], "static")
        self.assertEqual(s["font"], DEFAULTS["font"])
        self.assertEqual(s["position"], DEFAULTS["position"])
        self.assertEqual(s["quality"], DEFAULTS["quality"])

    def test_text_length(self):
        s = normalize({"text": "x" * 500})
        self.assertLessEqual(len(s["text"]), 200)

    def test_types(self):
        s = normalize({"opacity": "0.5", "tile": "true", "box": "1"})
        self.assertAlmostEqual(s["opacity"], 0.5)
        self.assertTrue(s["tile"])
        self.assertTrue(s["box"])


class TestDB(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="aqm_db_")
        self._old = config.DB_PATH
        config.DB_PATH = os.path.join(self.tmp, "test.db")
        db.init_db()

    def tearDown(self):
        config.DB_PATH = self._old

    def test_user_lifecycle(self):
        db.ensure_user(1, "Alice", "alice")
        self.assertFalse(db.is_banned(1))
        db.set_banned(1, True)
        self.assertTrue(db.is_banned(1))
        db.set_banned(1, False)
        self.assertFalse(db.is_banned(1))
        db.bump_processed(1)
        db.bump_processed(1)
        self.assertEqual(db.user_stats(1)["processed"], 2)

    def test_settings_roundtrip(self):
        db.save_settings(2, normalize({"color": "#123456", "size_pct": 20}))
        s = db.get_settings(2)
        self.assertEqual(s["color"], "#123456")
        self.assertEqual(s["size_pct"], 20.0)
        # unknown keys from an older version are dropped gracefully
        import json
        with db._conn() as c:
            c.execute("INSERT OR REPLACE INTO settings VALUES (2, ?)",
                      (json.dumps({"color": "#ABCDEF", "legacy_key": 1}),))
        s = db.get_settings(2)
        self.assertEqual(s["color"], "#ABCDEF")
        self.assertNotIn("legacy_key", s)

    def test_profiles(self):
        db.save_settings(3, {"color": "#111111"})
        self.assertTrue(db.save_profile(3, "insta", {"color": "#222222"}))
        profs = db.list_profiles(3)
        self.assertEqual(len(profs), 1)
        self.assertEqual(profs[0]["name"], "insta")
        loaded = db.load_profile(3, "insta")
        self.assertEqual(loaded["color"], "#222222")
        # overwrite same name
        self.assertTrue(db.save_profile(3, "insta", {"color": "#333333"}))
        self.assertEqual(len(db.list_profiles(3)), 1)
        self.assertTrue(db.delete_profile(3, "insta"))
        self.assertEqual(db.list_profiles(3), [])

    def test_rate_limit(self):
        self.assertTrue(db.rate_allow(9, limit=2))
        self.assertTrue(db.rate_allow(9, limit=2))
        self.assertFalse(db.rate_allow(9, limit=2))
        # simulate window expiry
        with db._conn() as c:
            c.execute("UPDATE users SET rate_ts=? WHERE user_id=?",
                      (time.time() - 3601, 9))
        self.assertTrue(db.rate_allow(9, limit=2))

    def test_global_stats(self):
        db.ensure_user(10, "A")
        db.bump_processed(10)
        g = db.global_stats()
        self.assertGreaterEqual(g["users"], 1)
        self.assertGreaterEqual(g["processed"], 1)


if __name__ == "__main__":
    unittest.main()
