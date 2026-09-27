import os
import sys
import tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import unittest

from PIL import Image, ImageStat

from core import renderer as R
from core.animations import REGISTRY as ANIMS
from core.settings import DEFAULTS, normalize
from core.styles import STYLES, apply_style

W, H = 1280, 720


def sprite_for(overrides=None):
    s = normalize(dict(DEFAULTS, **(overrides or {})))
    s["text"] = (overrides or {}).get("text", "AquaMark")
    return s, R.SpriteFactory(s, W, H)


class TestRenderer(unittest.TestCase):
    def test_all_styles_render(self):
        for sid in STYLES:
            s = apply_style(DEFAULTS, sid)
            s["text"] = "Style %s" % sid
            f = R.SpriteFactory(s, W, H)
            self.assertGreater(f.sprite.width, 10, sid)
            self.assertGreater(f.sprite.height, 10, sid)
            stat = ImageStat.Stat(f.sprite.getchannel("A"))
            self.assertGreater(stat.mean[0], 0.5, "empty sprite: %s" % sid)

    def test_gradient(self):
        s, f = sprite_for({"color": "#FFFFFF", "color2": "#000000",
                           "text": "GRADIENT"})
        sp = f.sprite
        # sample inside the text block: find alpha>128 bbox
        bbox = sp.getchannel("A").point(lambda v: 255 if v > 128 else 0
                                        ).getbbox()
        self.assertIsNotNone(bbox)
        x = (bbox[0] + bbox[2]) // 2
        top = sp.getpixel((x, bbox[1] + 2))
        bot = sp.getpixel((x, bbox[3] - 2))
        self.assertGreater(top[0], bot[0] + 40, "gradient not vertical")

    def test_stroke_and_glow_present(self):
        s, f = sprite_for({"stroke_w": 10, "glow": 80, "text": "GLOWY"})
        stat = ImageStat.Stat(f.sprite.getchannel("A"))
        self.assertGreater(stat.mean[0], 1.0)

    def test_box(self):
        s, f = sprite_for({"box": True, "box_color": "#FF0000",
                           "box_opacity": 1.0, "text": "BOXED"})
        sp = f.sprite
        # far left inside sprite should be pure-ish red box area
        found = False
        for x in range(2, 40):
            for y in range(sp.height // 3, 2 * sp.height // 3):
                px = sp.getpixel((x, y))
                if px[3] > 200:
                    self.assertGreater(px[0], 150, "box color missing")
                    self.assertLess(px[1], 110)
                    found = True
                    break
            if found:
                break
        self.assertTrue(found, "box not rendered")

    def test_rotation_expands(self):
        s0, f0 = sprite_for({"text": "LONG TEXT HERE"})
        area0 = f0.sprite.width * f0.sprite.height
        s1, f1 = sprite_for({"text": "LONG TEXT HERE", "rotation": 45})
        area1 = f1.sprite.width * f1.sprite.height
        self.assertGreater(area1, area0 * 1.5)

    def test_multiline(self):
        s0, f0 = sprite_for({"text": "one"})
        s1, f1 = sprite_for({"text": "one\ntwo"})
        self.assertGreater(f1.sprite.height, f0.sprite.height * 1.5)

    def test_auto_fit(self):
        s, f = sprite_for({
            "text": "This is an extremely long watermark line to shrink",
            "size_pct": 30})
        self.assertLessEqual(f.sprite.width, 0.95 * W)

    def test_position_grid(self):
        s = normalize(dict(DEFAULTS))
        sprite_w, sprite_h = 200, 60
        for pos in ("tl", "tc", "tr", "cl", "cc", "cr", "bl", "bc", "br"):
            s["position"] = pos
            x, y = R.position_xy(s, W, H, sprite_w, sprite_h)
            self.assertTrue(-sprite_w <= x <= W, pos)
            self.assertTrue(-sprite_h <= y <= H, pos)
        s["position"] = "tl"
        self.assertEqual(R.position_xy(s, W, H, sprite_w, sprite_h),
                         (int(0.04 * 720), int(0.04 * 720)))

    def test_tile_canvas(self):
        s, f = sprite_for({"text": "©ME"})
        canvas, tw, th = R.build_tile_canvas(f.sprite, s, W, H)
        self.assertGreaterEqual(canvas.width, W)
        self.assertGreaterEqual(canvas.height, H)
        # alpha spread across all four quadrants
        for qx, qy in ((0, 0), (canvas.width // 2, 0),
                       (0, canvas.height // 2),
                       (canvas.width // 2, canvas.height // 2)):
            quad = canvas.crop((qx, qy, qx + W // 2, qy + H // 2))
            self.assertGreater(
                ImageStat.Stat(quad.getchannel("A")).mean[0], 0.5)

    def test_pad_diagonal(self):
        s, f = sprite_for({"text": "WIDE TEXT"})
        import math
        padded, px, py = R.pad_diagonal(f.sprite)
        d = int(math.ceil(math.hypot(f.sprite.width, f.sprite.height))) + 4
        self.assertEqual(padded.size, (d, d))
        self.assertGreaterEqual(px, 0)
        self.assertGreaterEqual(py, 0)

    def test_swatch(self):
        img = R.swatch((200, 30, 30, 255), "#C81E1E")
        self.assertEqual(img.size, (260, 96))

    def test_sequences_uniform(self):
        for aid in ("typewriter", "glitch", "karaoke", "color-cycle",
                    "pop-in", "glow-pulse"):
            anim = ANIMS[aid]
            s, f = sprite_for({"text": "TESTING!"})
            d = tempfile.mkdtemp()
            info = R.render_sequence(f, anim, d)
            files = sorted(os.listdir(d))
            self.assertGreaterEqual(len(files), 8, aid)
            sizes = set(Image.open(os.path.join(d, fn)).size
                        for fn in files)
            self.assertEqual(len(sizes), 1, "non-uniform frames: %s" % aid)
            self.assertEqual(info["w"], list(sizes)[0][0])
            self.assertTrue(os.path.isabs(info["dir"]))


if __name__ == "__main__":
    unittest.main()
