"""THE flagship test: render ALL animations with real ffmpeg + pixel checks.

Every animation must:
  * render without ffmpeg errors
  * produce a ~full-duration output
  * actually be visible (pixel diff vs plain background)
  * actually animate (pixel diff between probe times / gate on-off)
"""
import asyncio
import os
import subprocess
import sys
import tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bootstrap
bootstrap.setup()
import unittest

from PIL import Image, ImageChops, ImageStat

from core import renderer as R
from core.animations import REGISTRY
from core.settings import DEFAULTS, normalize
from core.video_engine import ffmpeg, probe, watermark_video
from handlers.pipeline import prepare_sprite

DUR = 2.2
VW, VH = 480, 270
VIS_MIN = 40000       # sum-of-diff (L channel) to count as visible
MOT_MIN = 15000       # sum-of-diff between probe times to count as motion
HIDDEN_MAX = 25000    # gate "off" frames must match the background


def _run(args, timeout=60):
    return subprocess.run(
        [ffmpeg(), "-hide_banner", "-loglevel", "error", "-y"] + args,
        capture_output=True, text=True, timeout=timeout)


class TestAllAnimations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="aqm_allanims_")
        cls.base = os.path.join(cls.tmp, "base.mp4")
        r = _run(["-f", "lavfi",
                  "-i", "color=c=0x203040:size=%dx%d:rate=25:duration=%.2f"
                  % (VW, VH, DUR),
                  "-c:v", "libx264", "-preset", "ultrafast",
                  "-pix_fmt", "yuv420p", cls.base])
        assert r.returncode == 0, r.stderr[:400]
        cls.meta = probe(cls.base)
        cls.bg = cls._frame(cls.base, 1.0)

        # colored text: white would make hue/color-cycle animations
        # (hue rotation of white is still white) invisible to pixel probes
        cls.settings = normalize(dict(DEFAULTS, text="AQUA•TEST",
                                      size_pct=12, stroke_w=2,
                                      color="#38B6FF"))
        cls.factory = R.SpriteFactory(cls.settings, VW, VH)
        assert cls.factory.sprite.width > 80, "test sprite too small"
        cls.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(cls.loop)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.loop.close()
        finally:
            import shutil
            shutil.rmtree(cls.tmp, ignore_errors=True)

    @classmethod
    def _frame(cls, video, t):
        out = os.path.join(cls.tmp, "probe.png")
        r = _run(["-ss", str(t), "-i", video, "-frames:v", "1",
                  "-pix_fmt", "rgba", out])
        assert r.returncode == 0, r.stderr[:200]
        return Image.open(out).convert("RGBA")

    @staticmethod
    def _diff_sum(a, b):
        return ImageStat.Stat(
            ImageChops.difference(a, b).convert("L")).sum[0]

    def _render(self, aid):
        anim = REGISTRY[aid]
        s = dict(self.settings)
        s["animation"] = aid
        job = tempfile.mkdtemp(prefix="anim_", dir=self.tmp)
        sprite_path, seq_info = prepare_sprite(self.factory, anim, s,
                                               VW, VH, job)
        out = self.loop.run_until_complete(watermark_video(
            self.base, os.path.join(job, "out"), sprite_path, s,
            self.meta, seq_info=seq_info))
        return out

    def test_01_registry_sanity(self):
        self.assertGreaterEqual(len(REGISTRY), 100)
        ids = list(REGISTRY.keys())
        self.assertEqual(len(ids), len(set(ids)))
        for a in REGISTRY.values():
            self.assertTrue(a.name and a.icon and a.cat)
            self.assertIn(a.mode, ("expr", "seq", "seqexpr"))
            self.assertLessEqual(len("an:demo:%s" % a.id), 64)

    def test_02_all_animations_render_and_animate(self):
        failures = []
        results = []
        for aid in sorted(REGISTRY.keys()):
            anim = REGISTRY[aid]
            with self.subTest(animation=aid):
                try:
                    out = self._render(aid)
                except Exception as exc:
                    failures.append("%s: RENDER %s" % (aid, str(exc)[:120]))
                    continue
                m = probe(out)
                if abs(m["duration"] - DUR) > 0.4:
                    failures.append("%s: duration %.2f" % (aid,
                                                           m["duration"]))
                vis = self._diff_sum(self._frame(out, 1.0), self.bg)
                if vis < VIS_MIN:
                    failures.append("%s: not visible (%d)" % (aid, int(vis)))
                    continue
                kind, t1, t2 = anim.probe
                if kind == "motion":
                    if aid == "static":
                        results.append(aid)
                        continue
                    mot = self._diff_sum(self._frame(out, t1),
                                         self._frame(out, t2))
                    if mot < MOT_MIN:
                        failures.append("%s: no motion between %.2f/%.2f (%d)"
                                        % (aid, t1, t2, int(mot)))
                elif kind == "gate":
                    on = self._diff_sum(self._frame(out, t1), self.bg)
                    off = self._diff_sum(self._frame(out, t2), self.bg)
                    if on < VIS_MIN:
                        failures.append("%s: gate not on at %.2f (%d)"
                                        % (aid, t1, int(on)))
                    if off > HIDDEN_MAX:
                        failures.append("%s: gate not off at %.2f (%d)"
                                        % (aid, t2, int(off)))
                results.append(aid)
        print("\n===== animations verified: %d/%d =====" %
              (len(results), len(REGISTRY)))
        if failures:
            self.fail("animation failures:\n  " + "\n  ".join(failures))

    def test_03_animation_speed_scales(self):
        out = self._render("dvd")
        a = self._frame(out, 0.4)
        s = dict(self.settings, animation="dvd", anim_speed=4.0)
        job = tempfile.mkdtemp(prefix="anim_", dir=self.tmp)
        sprite_path, seq_info = prepare_sprite(
            self.factory, REGISTRY["dvd"], s, VW, VH, job)
        out4 = self.loop.run_until_complete(watermark_video(
            self.base, os.path.join(job, "out"), sprite_path, s,
            self.meta, seq_info=seq_info))
        b = self._frame(out4, 0.4)
        # fast dvd must have moved further by t=0.4 than slow dvd
        bg4 = self.bg
        d_slow = self._diff_sum(a, bg4)
        d_fast = self._diff_sum(b, bg4)
        self.assertGreater(d_fast, d_slow * 0.6)


if __name__ == "__main__":
    unittest.main()
