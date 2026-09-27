"""Font registry + script-aware routing (Latin / Cyrillic / Greek / Devanagari /
Arabic / emoji). Stdlib + Pillow only — no fontTools dependency."""
import os
import unicodedata

try:
    from PIL import ImageFont
except ImportError:  # tests import bootstrap first; direct import fallback
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "vendor"))
    from PIL import ImageFont

_FONT_CACHE = {}

# id -> (file, display name, default variable-axis weight or None, label)
FONTS = {
    "dejavu":        ("DejaVuSans.ttf", "DejaVu Sans", None, "Clean • wide Unicode"),
    "dejavu-bold":   ("DejaVuSans-Bold.ttf", "DejaVu Sans Bold", None, "Bold • wide Unicode"),
    "noto":          ("NotoSans.ttf", "Noto Sans", 500, "Modern sans"),
    "montserrat":    ("Montserrat.ttf", "Montserrat", 700, "Brand • bold geometric"),
    "bebas":         ("BebasNeue-Regular.ttf", "Bebas Neue", None, "Impact • condensed"),
    "playfair":      ("PlayfairDisplay.ttf", "Playfair Display", 700, "Elegant serif"),
    "devanagari":    ("NotoSansDevanagari.ttf", "Noto Devanagari", 700, "हिन्दी + Latin"),
    "arabic":        ("NotoNaskhArabic.ttf", "Noto Naskh Arabic", 400, "العربية + Latin"),
    "emoji":         ("NotoEmoji.ttf", "Noto Emoji", 400, "Emoji & symbols"),
}

# fonts usable for plain Latin text
_LATIN_OK = {"dejavu", "dejavu-bold", "noto", "montserrat", "bebas", "playfair",
             "devanagari", "arabic"}
DEFAULT_FONT_ID = "dejavu-bold"


def font_path(font_id):
    entry = FONTS.get(font_id)
    if entry is None:
        return None
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "assets", "fonts", entry[0])
    return p if os.path.isfile(p) else None


def get_font(font_id, px, weight=None):
    """Load a font at a pixel size (cached). Applies variable weight if any."""
    px = max(8, int(round(px)))
    key = (font_id, px, weight)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    entry = FONTS.get(font_id) or FONTS[DEFAULT_FONT_ID]
    path = font_path(font_id) or font_path(DEFAULT_FONT_ID)
    font = ImageFont.truetype(path, px)
    axis_weight = weight if weight is not None else entry[2]
    if axis_weight is not None:
        try:
            font.set_variation_by_axes([axis_weight])
        except Exception:
            pass
    _FONT_CACHE[key] = font
    return font


def _classify(ch):
    """Route a character to a script family."""
    cp = ord(ch)
    if cp < 128:
        return "latin"                      # ASCII covers itself
    if 0x1F000 <= cp <= 0x1FAFF or cp in (0x2600, 0x2764) or \
       0x2190 <= cp <= 0x27BF or 0xFE0F == cp or 0x1F1E6 <= cp <= 0x1F1FF:
        return "emoji"                      # emoji, dingbats, symbols, flags
    try:
        name = unicodedata.name(ch, "")
    except ValueError:
        name = ""
    upper = name.upper()
    if "DEVANAGARI" in upper:
        return "devanagari"
    if "ARABIC" in upper:
        return "arabic"
    if "CYRILLIC" in upper or "GREEK" in upper:
        return "cyrillic"                   # dejavu covers both
    if "EMOJI" in upper or "SYMBOL" in upper or "DINGBAT" in upper:
        return "emoji"
    return "latin"                          # letters/ext by default


def resolve_font_id(font_id, ch):
    """Best font id for a character given the user's chosen font."""
    fam = _classify(ch)
    if fam == "emoji":
        return "emoji" if font_id != "emoji" else "emoji"
    if fam == "devanagari":
        return font_id if font_id == "devanagari" else "devanagari"
    if fam == "arabic":
        return font_id if font_id == "arabic" else "arabic"
    if fam == "cyrillic":
        return font_id if font_id in ("dejavu", "dejavu-bold") else "dejavu-bold"
    # latin-ish: user's choice if it can do latin, else dejavu
    return font_id if font_id in _LATIN_OK else "dejavu-bold"


def segments(text, font_id):
    """Split text into (font_id, substring) runs, grouping same-font chars.

    Pure single-font texts come back as one segment so Pillow (and libraqm,
    when present) can shape the whole string properly.
    """
    if not text:
        return [(font_id, text)]
    runs = []
    cur_fid, buf = None, ""
    for ch in text:
        fid = resolve_font_id(font_id, ch)
        if fid == cur_fid or cur_fid is None:
            buf += ch
            cur_fid = fid
        else:
            runs.append((cur_fid, buf))
            buf, cur_fid = ch, fid
    if buf:
        runs.append((cur_fid, buf))
    return runs


def font_choices():
    """(id, label) list for UI."""
    return [(fid, "%s — %s" % (e[1], e[3])) for fid, e in FONTS.items()]
