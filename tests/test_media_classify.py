"""Regression tests for core.media.classify — must never crash on any
Telegram message shape (bug seen live: 'Sticker' object has no file_name)."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import unittest
from types import SimpleNamespace as NS

from core import media as M


def _msg(**media):
    """A message-like object: every category None except the ones given."""
    base = dict(photo=None, video=None, animation=None, video_note=None,
                sticker=None, document=None, voice=None, audio=None)
    base.update(media)
    return NS(**base)


PHOTO = NS(width=800, height=600, file_id="p1", file_size=1000)
VIDEO = NS(file_id="v1", width=1920, height=1080, duration=12.5,
           file_size=9_000_000, file_name="clip.MOV")
ANIM = NS(file_id="a1", width=480, height=270, duration=4.0,
          file_size=2_000_000, file_name="funny.gif")
VNOTE = NS(file_id="n1", length=360, duration=8.0, file_size=5_000_000)
# Sticker built EXACTLY like PTB 21.11: no file_name attribute
STICKER_STATIC = NS(file_id="s1", width=512, height=512, file_size=20_000,
                    is_animated=False, is_video=False)
STICKER_ANIM = NS(file_id="s2", width=512, height=512, file_size=50_000,
                  is_animated=True, is_video=False, duration=3.0)
STICKER_VIDEO = NS(file_id="s3", width=512, height=512, file_size=80_000,
                   is_animated=False, is_video=True, duration=5.0)
DOC_IMAGE = NS(file_id="d1", file_size=3_000_000, file_name="pic.png",
               mime_type="image/png")
DOC_UNKNOWN = NS(file_id="d2", file_size=1_000, file_name="data.xyz",
                 mime_type="application/octet-stream")
VOICE = NS(file_id="vo1", file_size=500_000)


class TestClassify(unittest.TestCase):
    def test_photo(self):
        info = M.classify(_msg(photo=[PHOTO]))
        self.assertEqual(info.kind, M.KIND_PHOTO)
        self.assertEqual(info.ext, ".jpg")

    def test_video(self):
        info = M.classify(_msg(video=VIDEO))
        self.assertEqual(info.kind, M.KIND_VIDEO)
        self.assertEqual(info.ext, ".mov")
        self.assertTrue(info.is_video_like)

    def test_video_without_filename(self):
        v = NS(file_id="v2", width=640, height=360, duration=2.0,
               file_size=1_000, file_name=None)
        info = M.classify(_msg(video=v))
        self.assertEqual(info.kind, M.KIND_VIDEO)
        self.assertEqual(info.ext, ".mp4")

    def test_animation(self):
        info = M.classify(_msg(animation=ANIM))
        self.assertEqual(info.kind, M.KIND_ANIMATION)
        self.assertEqual(info.ext, ".gif")

    def test_video_note(self):
        info = M.classify(_msg(video_note=VNOTE))
        self.assertEqual(info.kind, M.KIND_VIDEO_NOTE)

    def test_static_sticker(self):
        # regression: 'Sticker' object has no attribute 'file_name'
        info = M.classify(_msg(sticker=STICKER_STATIC))
        self.assertEqual(info.kind, M.KIND_IMAGE_DOC)
        self.assertEqual(info.ext, ".webp")
        self.assertEqual(info.filename, "sticker.webp")
        self.assertTrue(info.is_image_like)

    def test_animated_sticker(self):
        info = M.classify(_msg(sticker=STICKER_ANIM))
        self.assertEqual(info.kind, M.KIND_UNSUPPORTED)

    def test_video_sticker(self):
        info = M.classify(_msg(sticker=STICKER_VIDEO))
        self.assertEqual(info.kind, M.KIND_UNSUPPORTED)

    def test_document_image(self):
        info = M.classify(_msg(document=DOC_IMAGE))
        self.assertEqual(info.kind, M.KIND_IMAGE_DOC)
        self.assertEqual(info.ext, ".png")

    def test_document_unknown(self):
        info = M.classify(_msg(document=DOC_UNKNOWN))
        self.assertEqual(info.kind, M.KIND_UNSUPPORTED)

    def test_document_pdf(self):
        d = NS(file_id="d9", file_size=2_000_000, file_name="report.pdf",
               mime_type="application/pdf")
        info = M.classify(_msg(document=d))
        self.assertEqual(info.kind, M.KIND_PDF)
        self.assertEqual(info.ext, ".pdf")
        self.assertFalse(info.is_video_like)
        self.assertFalse(info.is_image_like)

    def test_document_pdf_by_ext_only(self):
        d = NS(file_id="d10", file_size=1, file_name="doc.pdf",
               mime_type="")
        info = M.classify(_msg(document=d))
        self.assertEqual(info.kind, M.KIND_PDF)

    def test_document_video_by_mime(self):
        d = NS(file_id="d3", file_size=1, file_name="",
               mime_type="video/mp4")
        info = M.classify(_msg(document=d))
        self.assertEqual(info.kind, M.KIND_VIDEO)

    def test_voice(self):
        info = M.classify(_msg(voice=VOICE))
        self.assertEqual(info.kind, M.KIND_AUDIO)

    def test_plain_text_message(self):
        self.assertIsNone(M.classify(_msg()))

    def test_none(self):
        self.assertIsNone(M.classify(None))

    def test_mediainfo_helpers(self):
        info = M.classify(_msg(video=VIDEO))
        self.assertIn("1920x1080", info.summary())
        self.assertIn("12s", info.summary())


class FakeReplyMessage:
    def __init__(self):
        self.calls = []

    async def _record(self, name, *a, **kw):
        self.calls.append((name, a, kw))
        return None

    def __getattr__(self, name):
        if name.startswith("reply_"):
            async def _call(*a, **kw):
                return await self._record(name, *a, **kw)
            return _call
        raise AttributeError(name)


class TestSendRouting(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp(prefix="aqm_send_")

    def _file(self, name, size=1024, content=b"%PDF-1.4 fake"):
        p = os.path.join(self.tmp, name)
        with open(p, "wb") as fh:
            fh.write(content)
            fh.write(b"\x00" * max(0, size - len(content)))
        return p

    def test_pdf_always_sent_as_document(self):
        import asyncio
        fake = FakeReplyMessage()
        pdf = self._file("out.pdf")
        res = asyncio.run(M.send_watermarked(fake, pdf, "pdf", None, {}))
        self.assertIsNone(res)
        self.assertEqual(len(fake.calls), 1)
        name, args, kw = fake.calls[0]
        self.assertEqual(name, "reply_document")
        self.assertTrue(kw.get("force_document"))
        self.assertEqual(kw.get("filename"), "out.pdf")

    def test_pdf_by_extension_even_if_kind_wrong(self):
        import asyncio
        fake = FakeReplyMessage()
        pdf = self._file("renamed.pdf")
        asyncio.run(M.send_watermarked(fake, pdf, "photo", None, {}))
        name, _a, _kw = fake.calls[0]
        self.assertEqual(name, "reply_document")

    def test_small_photo_sent_as_photo(self):
        import asyncio
        fake = FakeReplyMessage()
        jpg = self._file("out.jpg", content=b"\xff\xd8fakejpg")
        asyncio.run(M.send_watermarked(fake, jpg, "photo", None, {}))
        name, _a, _kw = fake.calls[0]
        self.assertEqual(name, "reply_photo")

    def test_gif_preferred(self):
        import asyncio
        fake = FakeReplyMessage()
        gif = self._file("out.gif", content=b"GIF89a")
        asyncio.run(M.send_watermarked(fake, gif, "video", None, {}))
        name, _a, _kw = fake.calls[0]
        self.assertEqual(name, "reply_animation")

    def test_oversize_forced_to_document(self):
        import asyncio
        import config as _config
        fake = FakeReplyMessage()
        big = self._file("big.mp4", size=_config.MAX_OUT_SIZE + 1,
                         content=b"\x00mp4data")
        asyncio.run(M.send_watermarked(fake, big, "video", None, {}))
        name, _a, _kw = fake.calls[0]
        self.assertEqual(name, "reply_document")


if __name__ == "__main__":
    unittest.main()
