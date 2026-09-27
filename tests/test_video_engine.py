import asyncio
import os
import subprocess
import sys
import tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import unittest

from PIL import Image

import config
from core import renderer as R
from core.settings import DEFAULTS, normalize
from core.video_engine import (FFmpegError, JobCancelled, ffmpeg, probe,
                               render_photo_loop, watermark_video)

DUR = 3.0
VW, VH = 480, 270


def _run(args, timeout=90):
    return subprocess.run(
        [ffmpeg(), "-hide_banner", "-loglevel", "error", "-y"] + args,
        capture_output=True, text=True, timeout=timeout)


class EngineBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="aqm_engine_")
        cls.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(cls.loop)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.loop.close()
        finally:
            import shutil
            shutil.rmtree(cls.tmp, ignore_errors=True)


class TestVideoEngine(EngineBase):
    @classmethod
    def setUpClass(cls):
        super(TestVideoEngine, cls).setUpClass()
        cls.base = os.path.join(cls.tmp, "base.mp4")  # mp4 + aac audio
        r = _run(["-f", "lavfi",
                  "-i", "testsrc2=size=%dx%d:rate=25:duration=%.1f"
                  % (VW, VH, DUR),
                  "-f", "lavfi", "-i", "sine=frequency=440:duration=%.1f"
                  % DUR,
                  "-c:v", "libx264", "-preset", "ultrafast",
                  "-pix_fmt", "yuv420p", "-c:a", "aac", cls.base])
        assert r.returncode == 0, r.stderr[:300]
        cls.meta = probe(cls.base)
        # webm (vp9+opus) to exercise the audio re-encode path
        cls.webm = os.path.join(cls.tmp, "base.webm")
        r = _run(["-i", cls.base, "-c:v", "libvpx", "-b:v", "400k",
                  "-c:a", "libopus", cls.webm], timeout=120)
        assert r.returncode == 0, r.stderr[:300]

    def _sprite(self, **over):
        s = normalize(dict(DEFAULTS, text="TEST", size_pct=12, **over))
        f = R.SpriteFactory(s, VW, VH)
        path = os.path.join(self.tmp, "wm_%s.png" % over.get("animation",
                                                             "static"))
        f.sprite.save(path)
        return s, path

    def test_probe(self):
        m = probe(self.base)
        self.assertAlmostEqual(m["duration"], DUR, delta=0.3)
        self.assertEqual((m["width"], m["height"]), (VW, VH))
        self.assertTrue(m["has_audio"])

    def test_probe_image(self):
        p = os.path.join(self.tmp, "img.png")
        Image.new("RGB", (100, 60), (10, 20, 30)).save(p)
        m = probe(p)
        self.assertEqual(m["duration"], 0.0)
        self.assertEqual((m["width"], m["height"]), (100, 60))
        self.assertFalse(m["has_audio"])

    def test_audio_copied(self):
        s, sp = self._sprite()
        out = self.loop.run_until_complete(watermark_video(
            self.base, os.path.join(self.tmp, "out_copy"), sp, s, self.meta))
        self.assertTrue(out.endswith(".mp4"))
        self.assertTrue(probe(out)["has_audio"])

    def test_webm_audio_reencoded(self):
        s, sp = self._sprite()
        meta = probe(self.webm)
        self.assertTrue(meta["has_audio"])
        out = self.loop.run_until_complete(watermark_video(
            self.webm, os.path.join(self.tmp, "out_webm"), sp, s, meta))
        self.assertTrue(probe(out)["has_audio"])

    def test_muted(self):
        s, sp = self._sprite(keep_audio=False)
        out = self.loop.run_until_complete(watermark_video(
            self.base, os.path.join(self.tmp, "out_mute"), sp, s, self.meta))
        self.assertFalse(probe(out)["has_audio"])

    def test_gif_output(self):
        s, sp = self._sprite(out_format="gif", animation="wave-h")
        out = self.loop.run_until_complete(watermark_video(
            self.base, os.path.join(self.tmp, "out_gif"), sp, s, self.meta))
        self.assertTrue(out.endswith(".gif"))
        self.assertGreater(os.path.getsize(out), 20000)

    def test_long_video_gif_falls_back_to_mp4(self):
        s, sp = self._sprite(out_format="gif")
        long_meta = dict(self.meta, duration=30.0)
        out = self.loop.run_until_complete(watermark_video(
            self.base, os.path.join(self.tmp, "out_giflong"), sp, s,
            long_meta))
        self.assertTrue(out.endswith(".mp4"))

    def test_progress_callback(self):
        from core import video_engine
        old_throttle = video_engine.PROGRESS_THROTTLE
        video_engine.PROGRESS_THROTTLE = 0.02   # catch every update
        try:
            s, sp = self._sprite()
            seen = []

            async def cb(frac):
                seen.append(frac)

            self.loop.run_until_complete(watermark_video(
                self.base, os.path.join(self.tmp, "out_prog"), sp, s,
                self.meta, progress_cb=cb))
        finally:
            video_engine.PROGRESS_THROTTLE = old_throttle
        # ffmpeg emits progress blocks as it encodes; a fast render may
        # emit only the final one — but it must reach ~100%
        self.assertGreaterEqual(len(seen), 1)
        self.assertGreaterEqual(max(seen), 0.9)
        self.assertLessEqual(max(seen), 1.0)
        self.assertEqual(seen, sorted(seen))

    def test_cancel(self):
        s, sp = self._sprite()
        ev = asyncio.Event()

        async def go():
            ev.set()
            return await watermark_video(
                self.base, os.path.join(self.tmp, "out_cancel"), sp, s,
                self.meta, cancel_event=ev)

        with self.assertRaises(JobCancelled):
            self.loop.run_until_complete(go())

    def test_oversize_guard_raises_after_retries(self):
        old = config.MAX_OUT_SIZE
        config.MAX_OUT_SIZE = 2048  # absurdly small on purpose
        try:
            s, sp = self._sprite()
            with self.assertRaises(FFmpegError):
                self.loop.run_until_complete(watermark_video(
                    self.base, os.path.join(self.tmp, "out_over"), sp, s,
                    self.meta))
        finally:
            config.MAX_OUT_SIZE = old

    def test_photo_loop_mp4_and_gif(self):
        photo = os.path.join(self.tmp, "photo.jpg")
        Image.new("RGB", (640, 400), (40, 90, 160)).save(photo, quality=90)
        s, sp = self._sprite(animation="dvd", loop_secs=3)
        out = self.loop.run_until_complete(render_photo_loop(
            photo, os.path.join(self.tmp, "loop"), sp, s))
        self.assertTrue(out.endswith(".mp4"))
        m = probe(out)
        self.assertAlmostEqual(m["duration"], 3.0, delta=0.4)

        s2, sp2 = self._sprite(animation="dvd", out_format="gif")
        out2 = self.loop.run_until_complete(render_photo_loop(
            photo, os.path.join(self.tmp, "loop2"), sp2, s2))
        self.assertTrue(out2.endswith(".gif"))

    def test_quality_presets_render(self):
        for q in ("low", "medium", "high"):
            s, sp = self._sprite(quality=q)
            out = self.loop.run_until_complete(watermark_video(
                self.base, os.path.join(self.tmp, "out_q_%s" % q), sp, s,
                self.meta))
            self.assertTrue(os.path.getsize(out) > 10000, q)

    def test_tiled_video(self):
        s = normalize(dict(DEFAULTS, text="©ME", tile=True, size_pct=6))
        f = R.SpriteFactory(s, VW, VH)
        sp = os.path.join(self.tmp, "tile.png")
        canvas, _, _ = R.build_tile_canvas(f.sprite, s, VW, VH)
        canvas.save(sp)
        out = self.loop.run_until_complete(watermark_video(
            self.base, os.path.join(self.tmp, "out_tile"), sp, s, self.meta))
        self.assertTrue(os.path.getsize(out) > 10000)


if __name__ == "__main__":
    unittest.main()
