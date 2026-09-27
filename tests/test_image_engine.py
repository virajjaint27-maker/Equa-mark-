import os
import sys
import tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import unittest

from PIL import Image, ImageChops, ImageStat

from core import renderer as R
from core.settings import DEFAULTS, normalize

W, H = 800, 500


class TestImageEngine(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="aqm_img_")
        self.photo = os.path.join(self.tmp, "photo.jpg")
        im = Image.new("RGB", (W, H), (30, 60, 120))
        im.save(self.photo, quality=92)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _settings(self, **over):
        s = normalize(dict(DEFAULTS, text="©TEST", size_pct=9, **over))
        return s

    def _diff(self, a, b):
        return ImageStat.Stat(
            ImageChops.difference(a, b).convert("L")).sum[0]

    def test_static_photo_composite(self):
        s = self._settings()
        f = R.SpriteFactory(s, W, H)
        out = R.composite_photo(self.photo, f.sprite, s,
                                os.path.join(self.tmp, "out"))
        self.assertTrue(out.endswith(".jpg"))
        self.assertGreater(self._diff(Image.open(out).convert("RGB"),
                                      Image.open(self.photo).convert("RGB")),
                           30000)
        # watermark actually near bottom-right: crop that region and compare
        result = Image.open(out).convert("RGB")
        orig = Image.open(self.photo).convert("RGB")
        br_result = result.crop((W // 2, H // 2, W, H))
        br_orig = orig.crop((W // 2, H // 2, W, H))
        self.assertGreater(self._diff(br_result, br_orig), 20000)
        tl_result = result.crop((0, 0, W // 3, H // 3))
        tl_orig = orig.crop((0, 0, W // 3, H // 3))
        self.assertLess(self._diff(tl_result, tl_orig), 5000)

    def test_position_variants(self):
        for pos in ("tl", "cc", "br"):
            s = self._settings(position=pos)
            f = R.SpriteFactory(s, W, H)
            out = R.composite_photo(self.photo, f.sprite, s,
                                    os.path.join(self.tmp, "out_%s" % pos))
            self.assertTrue(os.path.isfile(out))

    def test_png_passthrough(self):
        png = os.path.join(self.tmp, "p.png")
        Image.new("RGB", (400, 300), (90, 20, 90)).save(png)
        s = self._settings()
        f = R.SpriteFactory(s, 400, 300)
        out = R.composite_photo(png, f.sprite, s,
                                os.path.join(self.tmp, "out_png"))
        self.assertTrue(out.endswith(".png"))

    def test_tiled_photo(self):
        s = self._settings(tile=True)
        f = R.SpriteFactory(s, W, H)
        out = R.composite_photo(self.photo, f.sprite, s,
                                os.path.join(self.tmp, "out_tile"))
        result = Image.open(out).convert("RGB")
        orig = Image.open(self.photo).convert("RGB")
        # watermark present in ALL four quadrants
        for qx, qy in ((0, 0), (W // 2, 0), (0, H // 2), (W // 2, H // 2)):
            quad_r = result.crop((qx, qy, qx + W // 2, qy + H // 2))
            quad_o = orig.crop((qx, qy, qx + W // 2, qy + H // 2))
            self.assertGreater(self._diff(quad_r, quad_o), 8000,
                               "quadrant %d,%d has no watermark" % (qx, qy))

    def test_opacity_reduces_signal(self):
        s_full = self._settings(opacity=1.0)
        s_soft = self._settings(opacity=0.15)
        f1 = R.SpriteFactory(s_full, W, H)
        f2 = R.SpriteFactory(s_soft, W, H)
        out1 = R.composite_photo(self.photo, f1.sprite, s_full,
                                 os.path.join(self.tmp, "o1"))
        out2 = R.composite_photo(self.photo, f2.sprite, s_soft,
                                 os.path.join(self.tmp, "o2"))
        d1 = self._diff(Image.open(out1).convert("RGB"),
                        Image.open(self.photo).convert("RGB"))
        d2 = self._diff(Image.open(out2).convert("RGB"),
                        Image.open(self.photo).convert("RGB"))
        self.assertGreater(d1, d2 * 2)


if __name__ == "__main__":
    unittest.main()
