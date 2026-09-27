"""PDF watermarking for AquaMark.

Pure-Python via the vendored pypdf + fpdf2 packages (no system deps).
Stamps the user's watermark text (or logo) on every page, honouring the
shared settings: text, color, opacity, size_pct, rotation, position and
font. Runs synchronously — call it through ``asyncio.to_thread`` from the
async pipeline.
"""
from __future__ import annotations

import io
import logging
import os
from typing import Optional

import config
from core.colors import parse_color

log = logging.getLogger("aquamark.pdf")

# margins around the page, as a fraction of the smaller page side
_MARGIN_FRAC = 0.05
# font size floor in points
_MIN_SIZE = 8.0


class PDFError(Exception):
    pass


def _font(s: dict):
    """Return (family, style, path) for the user's font, or a built-in."""
    family = (s.get("font") or "dejavu").split(":")[0]
    try:
        from core.fonts import FONTS
        entry = FONTS.get(family) or FONTS.get("dejavu")
    except Exception:
        entry = None
    if entry:
        path = os.path.join(config.FONT_DIR, entry[0])
        if os.path.isfile(path):
            return "AQM", "", path
    # fpdf2 core font — always available, no file needed
    return "helvetica", "B", None


def _anchor(position: str, w: float, h: float, tw: float, th: float):
    """Map the shared 9-point position grid onto page coordinates.

    fpdf2's origin is the page's TOP-left corner (image-like), not the
    PDF-native bottom-left, so "t" is a small y and "b" a large one.
    """
    m = min(w, h) * _MARGIN_FRAC
    x = {"l": m, "c": (w - tw) / 2.0, "r": w - m - tw}
    y = {"t": m, "c": (h - th) / 2.0, "b": h - m - th}
    pos = position if position in ("tl", "tc", "tr", "cl", "cc", "cr",
                                   "bl", "bc", "br") else "cc"
    return x[pos[1]], y[pos[0]]


def _stamp_pdf(w: float, h: float, s: dict, lines, r: int, g: int, b: int,
               opacity: float, rotation: float, position: str,
               logo_path: Optional[str]) -> bytes:
    """Render one watermark stamp page as a standalone PDF (in memory)."""
    from fpdf import FPDF

    # unit="pt" so sizes are in PDF points. NOTE: no orientation argument —
    # fpdf2 treats an explicit format as PORTRAIT dims and would swap a
    # landscape (w>h) tuple; passing the tuple alone keeps it verbatim.
    pdf = FPDF(unit="pt", format=(w, h))
    pdf.set_auto_page_break(False)
    pdf.add_page(format=(w, h))
    pdf.set_text_color(r, g, b)

    if logo_path is not None:  # ---- logo mode ---------------------------
        from PIL import Image as PILImage
        with PILImage.open(logo_path) as im:
            iw, ih = im.size
        lw = w * max(4.0, float(s.get("size_pct", 12))) / 100.0
        lh = lw * (ih / max(1.0, iw))
        x0, y0 = (w - lw) / 2.0, (h - lh) / 2.0
        cx, cy = x0 + lw / 2.0, y0 + lh / 2.0
        with pdf.local_context(fill_opacity=opacity):
            with pdf.rotation(rotation, cx, cy):
                pdf.image(logo_path, x=x0, y=y0, w=lw, h=lh)
    else:  # ---- text mode ------------------------------------------------
        family, style, path = _font(s)
        if path:
            pdf.add_font(family, style, path)
        pdf.set_font(family, style, 24.0)  # width probe size (set again below)
        size = max(_MIN_SIZE, w * float(s.get("size_pct", 8)) / 100.0)
        pdf.set_font(family, style, size)
        try:
            widths = [pdf.get_string_width(ln) for ln in lines]
        except Exception:
            widths = [size * 0.6 * len(ln) for ln in lines]
        line_h = size * 1.25
        block_w = max(widths)
        block_h = line_h * len(lines)
        x0, y0 = _anchor(position, w, h, block_w, block_h)
        # rotation pivots around the block's centre so it stays in place
        cx, cy = x0 + block_w / 2.0, y0 + block_h / 2.0
        with pdf.local_context(fill_opacity=opacity):
            with pdf.rotation(rotation, cx, cy):
                for i, ln in enumerate(lines):
                    bx = x0 + (block_w - widths[i]) / 2.0
                    by = y0 + line_h * i + size * 0.8  # baseline
                    pdf.text(bx, by, ln)
    return bytes(pdf.output())


def watermark_pdf(src: str, out: str, s: dict,
                  logo_path: Optional[str] = None) -> str:
    """Stamp every page of ``src``; write to ``out`` (a .pdf path)."""
    from pypdf import PdfReader, PdfWriter, Transformation

    try:
        reader = PdfReader(src)
        if reader.is_encrypted:
            from pypdf import PasswordType
            # empty owner-password PDFs open with ""; a user password
            # does not — decrypt() returns NOT_DECRYPTED instead of raising
            if reader.decrypt("") == PasswordType.NOT_DECRYPTED:
                raise PDFError("That PDF is password-protected, so I can't "
                               "watermark it.")
    except PDFError:
        raise
    except Exception as exc:
        raise PDFError("That PDF could not be read — it may be corrupt or "
                       "password-protected.") from exc
    try:
        n_pages = len(reader.pages)
    except Exception as exc:
        raise PDFError("That PDF could not be read.") from exc
    if not n_pages:
        raise PDFError("That PDF has no readable pages.")
    writer = PdfWriter()

    text = (s.get("text") or "AquaMark").strip()
    opacity = max(0.05, min(1.0, float(s.get("opacity", 0.9))))
    rotation = float(s.get("rotation", 0) or 0)
    position = s.get("position", "cc")
    lines = [ln for ln in text.split("\n") if ln.strip()][:5] or [text]

    try:
        r, g, b, _a = parse_color(s.get("color") or "#FFFFFF",
                                  default=(255, 255, 255, 255))
    except Exception:
        r = g = b = 255

    logo = None
    if s.get("wm_type") == "logo" and logo_path and os.path.isfile(logo_path):
        logo = logo_path

    for page in reader.pages:
        try:
            w = float(page.mediabox.width)
            h = float(page.mediabox.height)
            ox = float(page.mediabox.left)
            oy = float(page.mediabox.bottom)
        except Exception:
            w, h, ox, oy = 595.0, 842.0, 0.0, 0.0  # A4 portrait fallback

        try:
            stamp_bytes = _stamp_pdf(w, h, s, lines, r, g, b, opacity,
                                     rotation, position, logo)
            stamp = PdfReader(io.BytesIO(stamp_bytes)).pages[0]
            if ox or oy:
                # page's origin is not (0,0) — shift the stamp to match
                page.merge_transformed_page(
                    stamp, Transformation().translate(ox, oy))
            else:
                page.merge_page(stamp)
        except PDFError:
            raise
        except Exception:
            log.exception("stamp render failed on %s", src)
            raise PDFError("Failed to stamp one of the PDF pages.")
        writer.add_page(page)

    with open(out, "wb") as fh:
        writer.write(fh)
    return out
