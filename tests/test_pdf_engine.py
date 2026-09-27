"""Tests for core/pdf_engine.py — real PDFs stamped and verified."""
import io
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import unittest

import bootstrap
bootstrap.setup()

from core.pdf_engine import PDFError, watermark_pdf
from core.settings import DEFAULTS, normalize


def _make_pdf(pages=1, size=(595, 842), text="Page %d"):
    """Build a small source PDF with fpdf2 (no reportlab needed)."""
    from fpdf import FPDF
    from pypdf import PdfReader
    # no orientation arg: fpdf2 would swap explicit landscape formats
    pdf = FPDF(unit="pt", format=size)
    pdf.set_auto_page_break(False)
    pdf.set_font("helvetica", "", 24)
    for i in range(pages):
        pdf.add_page(format=size)
        if text:
            pdf.text(100, 100, text % (i + 1))
    return PdfReader(io.BytesIO(bytes(pdf.output())))


def _write(path, reader):
    w = _writer_for(reader)
    with open(path, "wb") as fh:
        w.write(fh)
    return path


def _writer_for(reader):
    from pypdf import PdfWriter
    w = PdfWriter()
    for p in reader.pages:
        w.add_page(p)
    return w


class TestPDFEngine(unittest.TestCase):
    def setUp(self):
        self.tmp = "/home/user/.cache/tmp/pdf_tests"
        os.makedirs(self.tmp, exist_ok=True)

    def test_stamp_every_page(self):
        src = _write(os.path.join(self.tmp, "src.pdf"), _make_pdf(pages=3))
        s = normalize(dict(DEFAULTS, text="AQUAMARK", color="#38B6FF",
                           size_pct=10, opacity=70, rotation=30,
                           position="cc"))
        out = os.path.join(self.tmp, "out.pdf")
        watermark_pdf(src, out, s)
        self.assertTrue(os.path.isfile(out) and os.path.getsize(out) > 500)

        from pypdf import PdfReader
        r = PdfReader(out)
        self.assertEqual(len(r.pages), 3)
        for i, page in enumerate(r.pages):
            txt = page.extract_text() or ""
            self.assertIn("AQUAMARK", txt, "page %d not stamped" % (i + 1))
            self.assertIn("Page %d" % (i + 1), txt, "page %d lost content"
                          % (i + 1))

    def test_rotation_and_opacity_in_content(self):
        """The stamp must carry a rotate matrix and a fill-alpha ExtGState."""
        src = _write(os.path.join(self.tmp, "src_rot.pdf"), _make_pdf())
        s = normalize(dict(DEFAULTS, text="TILT", rotation=30, opacity=0.7))
        out = os.path.join(self.tmp, "out_rot.pdf")
        watermark_pdf(src, out, s)

        from pypdf import PdfReader
        page = PdfReader(out).pages[0]
        # text roundtrips via the ToUnicode map of the subset TTF
        self.assertIn("TILT", page.extract_text() or "")
        data = page.get_contents().get_data().decode("latin-1", "replace")
        # 30deg rotation matrix inside the content stream
        self.assertIn("0.866 0.5 -0.5 0.866", data)
        # fill-opacity ExtGState was applied...
        self.assertRegex(data, r"/GS\d+ gs")
        # ...and actually carries /ca 0.7
        xg = page["/Resources"].get("/ExtGState")
        cas = [round(float(v.get_object().get("/ca", 1)), 2)
               for v in (xg or {}).values()]
        self.assertIn(0.7, cas)

    def test_landscape_page_keeps_size(self):
        src = _write(os.path.join(self.tmp, "src_ls.pdf"),
                     _make_pdf(size=(842, 595)))
        s = normalize(dict(DEFAULTS, text="WIDE"))
        out = os.path.join(self.tmp, "out_ls.pdf")
        watermark_pdf(src, out, s)
        from pypdf import PdfReader
        page = PdfReader(out).pages[0]
        self.assertAlmostEqual(float(page.mediabox.width), 842.0, delta=1.0)
        self.assertAlmostEqual(float(page.mediabox.height), 595.0, delta=1.0)
        self.assertIn("WIDE", page.extract_text() or "")

    def test_position_and_multiline(self):
        src = _write(os.path.join(self.tmp, "src2.pdf"), _make_pdf())
        s = normalize(dict(DEFAULTS, text="LINE ONE\nLINE TWO",
                           position="br", rotation=0, size_pct=8))
        out = os.path.join(self.tmp, "out2.pdf")
        watermark_pdf(src, out, s)
        from pypdf import PdfReader
        txt = PdfReader(out).pages[0].extract_text() or ""
        self.assertIn("LINE ONE", txt)
        self.assertIn("LINE TWO", txt)

    def test_custom_font_used(self):
        src = _write(os.path.join(self.tmp, "src3.pdf"), _make_pdf())
        s = normalize(dict(DEFAULTS, text="हिन्दी STAMP", font="devanagari"))
        out = os.path.join(self.tmp, "out3.pdf")
        watermark_pdf(src, out, s)  # must not raise on font registration
        self.assertTrue(os.path.getsize(out) > 500)

    def test_logo_mode(self):
        from PIL import Image, ImageDraw
        logo = os.path.join(self.tmp, "logo.png")
        im = Image.new("RGBA", (400, 160), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rectangle((10, 10, 390, 150), fill=(56, 182, 255, 255))
        im.save(logo)
        src = _write(os.path.join(self.tmp, "src4.pdf"), _make_pdf())
        s = normalize(dict(DEFAULTS, wm_type="logo", size_pct=20))
        out = os.path.join(self.tmp, "out4.pdf")
        watermark_pdf(src, out, s, logo_path=logo)
        self.assertTrue(os.path.getsize(out) > 1000)  # image embedded

    def test_encrypted_pdf_friendly_error(self):
        from pypdf import PdfWriter
        w = PdfWriter()
        w.add_blank_page(595, 842)
        w.encrypt("pypdf-riddle")  # user password
        enc = os.path.join(self.tmp, "enc.pdf")
        with open(enc, "wb") as fh:
            w.write(fh)
        s = normalize(dict(DEFAULTS, text="x"))
        with self.assertRaises(PDFError):
            watermark_pdf(enc, os.path.join(self.tmp, "outenc.pdf"), s)

    def test_corrupt_pdf_raises_friendly(self):
        bad = os.path.join(self.tmp, "bad.pdf")
        with open(bad, "wb") as fh:
            fh.write(b"this is not a pdf at all")
        s = normalize(dict(DEFAULTS, text="x"))
        with self.assertRaises(PDFError):
            watermark_pdf(bad, os.path.join(self.tmp, "outbad.pdf"), s)


if __name__ == "__main__":
    unittest.main()
