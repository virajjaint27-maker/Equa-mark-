"""Watermark sprite renderer (Pillow).

Builds tight RGBA sprites with a composable effect stack:
  box -> shadow -> glow -> stroke -> fill(solid|gradient) -> opacity -> rotation

Also renders frame sequences for the 24 text-effect animations and composite
helpers for photos. Pillow >= 10.4 compatible (also 11.x/12.x).
"""
import colorsys
import math
import os
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

try:
    RESAMPLE = Image.Resampling.LANCZOS        # for resize()
    ROT_RESAMPLE = Image.Resampling.BICUBIC    # rotate() rejects LANCZOS
except AttributeError:  # Pillow < 9.1
    RESAMPLE = Image.LANCZOS
    ROT_RESAMPLE = Image.BICUBIC

from . import colors as C
from . import fonts as F

PAD_FRAC = 0.55  # sprite padding around text, fraction of font size


def _hex_to_rgb01(rgba):
    return (rgba[0] / 255.0, rgba[1] / 255.0, rgba[2] / 255.0)


def hue_shift(rgba, deg):
    r, g, b = _hex_to_rgb01(rgba)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    h = (h + deg / 360.0) % 1.0
    r2, g2, b2 = colorsys.hsv_to_rgb(h, s, v)
    return (int(r2 * 255), int(g2 * 255), int(b2 * 255), rgba[3])


def lerp_color(c1, c2, k):
    return tuple(int(a + (b - a) * k) for a, b in zip(c1[:3], c2[:3])) + (c1[3],)


def _ease_out_bounce(t):
    if t < 1 / 2.75:
        return 7.5625 * t * t
    if t < 2 / 2.75:
        t -= 1.5 / 2.75
        return 7.5625 * t * t + 0.75
    if t < 2.5 / 2.75:
        t -= 2.25 / 2.75
        return 7.5625 * t * t + 0.9375
    t -= 2.625 / 2.75
    return 7.5625 * t * t + 0.984375


def _ease_out_back(t):
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * pow(t - 1, 3) + c1 * pow(t - 1, 2)


class SpriteFactory(object):
    """Renders the watermark sprite for given settings + target media size.

    render() supports cheap variations used by sequence generators:
    text override, color override, gradient shift, glow factor.
    """

    def __init__(self, settings, W, H, logo_path=None):
        self.s = settings
        self.W = int(W)
        self.H = int(H)
        self.logo_path = logo_path
        self.text = settings.get("text") or ""
        self.font_px = max(12, int(round(
            float(settings.get("size_pct", 8)) / 100.0 * min(self.W, self.H))))
        self._cache = {}
        self._fit_attempts = 0
        sprite = self.render()
        # auto-fit: shrink font if sprite spills past 92% of media width
        max_w = 0.92 * self.W
        if sprite.width > max_w and self.font_px > 12 and self._fit_attempts < 3:
            self._fit_attempts += 1
            self.font_px = max(12, int(self.font_px * max_w / sprite.width))
            self._cache = {}
            sprite = self.render()
        self.sprite = sprite

    # ------------- layout -------------

    def _lines(self):
        return [ln for ln in str(self.text).split("\n")] or [""]

    def _line_runs(self, line):
        return F.segments(line, self.s.get("font", F.DEFAULT_FONT_ID))

    def _line_width(self, draw, line, font_px):
        total = 0.0
        for fid, run in self._line_runs(line):
            font = F.get_font(fid, font_px)
            total += font.getlength(run)
        return total

    def _text_block_size(self):
        lines = self._lines()
        line_h = int(self.font_px * 1.30)
        widths = []
        dummy = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
        for ln in lines:
            widths.append(self._line_width(dummy, ln, self.font_px))
        return lines, line_h, max(widths) if widths else 1

    # ------------- core render -------------

    def render(self, text=None, color=None, color2=None, glow_factor=1.0):
        s = self.s
        if s.get("wm_type") == "logo" and self.logo_path:
            return self._render_logo()
        use_text = text if text is not None else self.text
        if not use_text:
            use_text = " "

        saved = self.text
        try:
            self.text = use_text
            lines, line_h, block_w = self._text_block_size()
            stroke_px = int(round(self.font_px * float(s.get("stroke_w", 0)) / 100.0))
            glow_amt = float(s.get("glow", 0)) * glow_factor
            shadow_amt = float(s.get("shadow", 0))
            box_on = bool(s.get("box"))
            box_pad_px = int(round(self.font_px * float(s.get("box_pad", 35)) / 100.0))

            pad = int(math.ceil(self.font_px * PAD_FRAC)) + stroke_px + \
                (box_pad_px if box_on else 0)
            glow_pad = int(self.font_px * 0.5) if glow_amt > 0 else 0
            shadow_pad = int(self.font_px * 0.35) if shadow_amt > 0 else 0
            pad += max(glow_pad, shadow_pad)

            w = int(math.ceil(block_w)) + pad * 2
            h = len(lines) * line_h + pad * 2

            img = Image.new("RGBA", (w, h), (0, 0, 0, 0))

            # --- text masks ---
            mask_full = Image.new("L", (w, h), 0)     # glyphs + stroke
            mask_fill = Image.new("L", (w, h), 0)     # glyphs only
            md = ImageDraw.Draw(mask_full)
            fd = ImageDraw.Draw(mask_fill)
            y = pad
            for ln in lines:
                x = pad
                for fid, run in F.segments(ln, s.get("font", F.DEFAULT_FONT_ID)):
                    font = F.get_font(fid, self.font_px)
                    if stroke_px > 0:
                        md.text((x, y), run, font=font, fill=255,
                                stroke_width=stroke_px, stroke_fill=255)
                    else:
                        md.text((x, y), run, font=font, fill=255)
                    fd.text((x, y), run, font=font, fill=255)
                    x += font.getlength(run)
                y += line_h

            # --- box ---
            if box_on:
                bx0 = pad - box_pad_px
                by0 = pad - int(box_pad_px * 0.6)
                bx1 = w - pad + box_pad_px
                by1 = h - pad + int(box_pad_px * 0.6)
                radius = int(self.font_px * float(s.get("box_radius", 50)) / 100.0)
                radius = max(0, min(radius, int((by1 - by0) / 2)))
                bc = C.parse_color(s.get("box_color", "#000000"))
                alpha = int(255 * float(s.get("box_opacity", 0.45)))
                layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
                ld = ImageDraw.Draw(layer)
                ld.rounded_rectangle([bx0, by0, bx1, by1], radius=radius,
                                     fill=bc[:3] + (alpha,))
                img.alpha_composite(layer)

            # --- shadow ---
            if shadow_amt > 0:
                sc = C.parse_color(s.get("shadow_color", "#000000"))
                off = max(2, int(self.font_px * 0.07))
                blur = max(2, int(self.font_px * 0.10))
                sh = Image.new("RGBA", (w, h), (0, 0, 0, 0))
                sh.paste(sc[:3] + (255,), (off, off + int(self.font_px * 0.03)),
                         mask_full)
                sh = sh.filter(ImageFilter.GaussianBlur(blur))
                a = sh.getchannel("A").point(
                    lambda v: int(v * min(1.0, shadow_amt / 100.0 * 0.85)))
                sh.putalpha(a)
                img.alpha_composite(sh)

            # --- glow ---
            if glow_amt > 0:
                gc = C.parse_color(s.get("glow_color") or s.get("color", "#FFFFFF"))
                blur = max(2, int(self.font_px * 0.16))
                gl = Image.new("RGBA", (w, h), (0, 0, 0, 0))
                gl.paste(gc[:3] + (255,), (0, 0), mask_full)
                gl = gl.filter(ImageFilter.GaussianBlur(blur))
                k = min(2.5, glow_amt / 100.0 * 1.8)
                a = gl.getchannel("A").point(lambda v: min(255, int(v * k)))
                gl.putalpha(a)
                img.alpha_composite(gl)

            # --- stroke + fill ---
            stroke_color = C.parse_color(s.get("stroke_color", "#000000"))
            if stroke_px > 0:
                sl = Image.new("RGBA", (w, h), (0, 0, 0, 0))
                sl.paste(stroke_color[:3] + (255,), (0, 0), mask_full)
                img.alpha_composite(sl)

            fill_c1 = C.parse_color(color or s.get("color", "#FFFFFF"))
            c2_spec = color2 if color2 is not None else s.get("color2", "")
            fill_c2 = None
            if str(c2_spec or "").strip():
                try:
                    fill_c2 = C.parse_color(c2_spec)
                except C.ColorError:
                    fill_c2 = None

            fill_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            if fill_c2 is not None:
                grad = Image.new("RGBA", (w, h), (0, 0, 0, 0))
                gd = ImageDraw.Draw(grad)
                gh = max(1, len(lines) * line_h)
                top = pad
                for i in range(gh):
                    k = i / float(gh)
                    gd.line([(0, top + i), (w, top + i)],
                            fill=lerp_color(fill_c1, fill_c2, k)[:3] + (255,))
                fill_layer.paste(grad, (0, 0), mask_fill)
            else:
                fill_layer.paste(fill_c1[:3] + (255,), (0, 0), mask_fill)
            img.alpha_composite(fill_layer)

            # --- global opacity ---
            op = float(s.get("opacity", 1.0))
            if op < 1.0:
                a = img.getchannel("A").point(lambda v: int(v * op))
                img.putalpha(a)

            # --- rotation ---
            rot = float(s.get("rotation", 0) or 0)
            if abs(rot) > 0.5:
                img = img.rotate(-rot, resample=ROT_RESAMPLE, expand=True)
            return img
        finally:
            self.text = saved

    def _render_logo(self):
        try:
            logo = Image.open(self.logo_path).convert("RGBA")
        except Exception:
            return self.render(text="?")
        bbox = logo.getbbox()
        if bbox:
            logo = logo.crop(bbox)
        target_h = max(16, int(round(
            float(self.s.get("size_pct", 8)) / 100.0 * min(self.W, self.H))))
        if logo.height > target_h:
            nw = int(logo.width * target_h / logo.height)
            logo = logo.resize((max(1, nw), target_h), RESAMPLE)
        elif logo.height < target_h // 2:
            nw = int(logo.width * target_h / logo.height)
            logo = logo.resize((max(1, nw), target_h), RESAMPLE)
        pad = int(logo.height * 0.25)
        canvas = Image.new("RGBA",
                           (logo.width + pad * 2, logo.height + pad * 2),
                           (0, 0, 0, 0))
        canvas.alpha_composite(logo, (pad, pad))
        op = float(self.s.get("opacity", 1.0))
        if op < 1.0:
            a = canvas.getchannel("A").point(lambda v: int(v * op))
            canvas.putalpha(a)
        rot = float(self.s.get("rotation", 0) or 0)
        if abs(rot) > 0.5:
            canvas = canvas.rotate(-rot, resample=ROT_RESAMPLE, expand=True)
        return canvas


# ------------- positioning -------------

def pad_diagonal(sprite):
    """Pad a sprite to a diagonal square so ffmpeg rotate() never clips it.

    Returns (padded, pad_x, pad_y) — pad offsets let the engine keep the
    text anchored at its intended position.
    """
    d = int(math.ceil(math.hypot(sprite.width, sprite.height))) + 4
    out = Image.new("RGBA", (d, d), (0, 0, 0, 0))
    px = (d - sprite.width) // 2
    py = (d - sprite.height) // 2
    out.alpha_composite(sprite, (px, py))
    return out, px, py


def position_xy(s, W, H, w, h):
    """9-grid anchor position for a sprite of size (w,h) on media (W,H)."""
    m = float(s.get("margin", 4)) / 100.0 * min(W, H)
    pos = s.get("position", "br")
    x = m if pos[1] == "l" else (W - w - m if pos[1] == "r" else (W - w) / 2.0)
    y = m if pos[0] == "t" else (H - h - m if pos[0] == "b" else (H - h) / 2.0)
    return int(max(-w, min(W, x))), int(max(-h, min(H, y)))


def build_tile_canvas(sprite, s, W, H):
    """Anti-crop tiled watermark covering the frame (plus overflow)."""
    gap_x = int(sprite.width * (1.0 + float(s.get("tile_gap", 30)) / 100.0))
    gap_y = int(sprite.height * (1.0 + float(s.get("tile_gap", 30)) / 100.0))
    angle = float(s.get("tile_angle", -30))
    tile = sprite.rotate(-angle, resample=ROT_RESAMPLE, expand=True) \
        if abs(angle) > 0.5 else sprite.copy()
    tw, th = tile.size
    cw = W + tw * 2
    ch = H + th * 2
    canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    step_x = max(tw + gap_x - sprite.width + sprite.width, 1)
    step_y = max(th + gap_y - sprite.height + sprite.height, 1)
    step_x = int(sprite.width * (1 + float(s.get("tile_gap", 30)) / 100.0)) or 1
    step_y = int(sprite.height * (1 + float(s.get("tile_gap", 30)) / 100.0)) or 1
    y = 0
    while y < ch:
        x = 0
        while x < cw:
            canvas.alpha_composite(tile, (x, y))
            x += step_x
        y += step_y
    return canvas, tw, th


# ------------- photo compositing -------------

def composite_photo(photo_path, sprite, s, out_path, keep_format=True):
    photo = Image.open(photo_path)
    if photo.mode != "RGBA":
        photo = photo.convert("RGBA")
    W, H = photo.size
    if bool(s.get("tile")):
        canvas, _, _ = build_tile_canvas(sprite, s, W, H)
        photo.paste(canvas, ((W - canvas.width) // 2,
                             (H - canvas.height) // 2), canvas)
    else:
        x, y = position_xy(s, W, H, sprite.width, sprite.height)
        photo.alpha_composite(sprite, (int(x), int(y)))
    ext = os.path.splitext(str(photo_path))[1].lower().lstrip(".") \
        if keep_format else "png"
    if ext in ("", "jpg", "jpeg"):
        ext = "jpg"
        photo = photo.convert("RGB")
    elif ext not in ("png", "webp", "bmp"):
        ext = "png"
    final = os.path.splitext(out_path)[0] + "." + ext
    save_kw = {}
    if ext == "jpg":
        save_kw["quality"] = 93
    photo.save(final, **save_kw)
    return final


# ------------- color swatch (UI helper) -------------

def swatch(rgba, label=None):
    img = Image.new("RGBA", (260, 96), (24, 26, 32, 255))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([10, 10, 250, 86], radius=18, fill=rgba)
    txt = label or C.to_hex(rgba)
    lum = 0.299 * rgba[0] + 0.587 * rgba[1] + 0.114 * rgba[2]
    fg = (17, 17, 17, 255) if lum > 140 else (255, 255, 255, 255)
    font = F.get_font("dejavu-bold", 34)
    tw = d.textlength(txt, font=font)
    d.text(((260 - tw) / 2, 30), txt, font=font, fill=fg)
    return img


# ------------- frame sequences -------------

def render_sequence(factory, anim, out_dir, seq_fps=12, min_frames=None):
    """Render frame PNGs for a sequence animation.

    Returns dict(dir, fps, n, w, h, pad_x, pad_y, inner_w, inner_h).
    Frames are anchored so the inner sprite keeps its intended grid position;
    the engine subtracts pad when computing overlay coordinates.
    min_frames extends the sequence by repeating its cycle (used for GIF
    renders, where the frame source is not looped by ffmpeg).
    """
    base = factory.sprite
    params = dict(anim.seq_params or {})
    period = float(params.pop("period", 2.0))
    n = max(2, int(round(period * seq_fps)))
    total = n
    if min_frames:
        total = max(n, int(min_frames))
    gen = _GENERATORS.get(anim.seq)
    if gen is None:
        gen = _GENERATORS["alpha_breathe"]

    pad_x = int(base.width * 0.5)
    pad_y = int(base.height * 0.5)
    cw = base.width + pad_x * 2
    ch = base.height + pad_y * 2

    os.makedirs(out_dir, exist_ok=True)
    for i in range(total):
        p = (i % n) / float(n)
        frame = gen(factory, base, i % n, n, p, params, cw, ch, pad_x, pad_y)
        if frame.size != (cw, ch):
            frame = frame.resize((cw, ch), RESAMPLE)
        frame.save(os.path.join(out_dir, "%04d.png" % i))
    return {"dir": os.path.abspath(out_dir), "fps": seq_fps, "n": total,
            "w": cw, "h": ch, "pad_x": pad_x, "pad_y": pad_y,
            "inner_w": base.width, "inner_h": base.height}


def _canvas(base, cw, ch, pad_x, pad_y):
    c = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    c.alpha_composite(base, (pad_x, pad_y))
    return c


def _scale_about_center(img, kx, ky):
    if abs(kx - 1) < 0.01 and abs(ky - 1) < 0.01:
        return img
    nw = max(2, int(img.width * kx))
    nh = max(2, int(img.height * ky))
    r = img.resize((nw, nh), RESAMPLE)
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.alpha_composite(r, ((img.width - nw) // 2, (img.height - nh) // 2))
    return out


def _shifted(img, dx, dy):
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.alpha_composite(img, (int(dx), int(dy)))
    return out


def _set_alpha(img, factor):
    a = img.getchannel("A").point(lambda v: max(0, min(255, int(v * factor))))
    out = img.copy()
    out.putalpha(a)
    return out


# --- generators: (factory, base, i, n, p, params, cw, ch, pad_x, pad_y) -> Image

def _g_typewriter(factory, base, i, n, p, params, cw, ch, pad_x, pad_y):
    text = factory.text
    k = max(1, int(math.ceil(p * len(text)))) if p < 1 else len(text)
    partial = factory.render(text=text[:k])
    canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    canvas.alpha_composite(partial, (pad_x, pad_y))
    if params.get("cursor", True) and k < len(text):
        d = ImageDraw.Draw(canvas)
        font = F.get_font(factory.s.get("font", F.DEFAULT_FONT_ID),
                          factory.font_px)
        x = pad_x + partial.width - factory.font_px * 0.1
        d.rectangle([x, pad_y + factory.font_px * 0.15,
                     x + factory.font_px * 0.16,
                     pad_y + factory.font_px * 1.05],
                    fill=C.parse_color(factory.s.get("color", "#FFFFFF")))
    return canvas


def _g_wipe(factory, base, i, n, p, params, cw, ch, pad_x, pad_y):
    direction = params.get("dir", "lr")
    canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    w, h = base.size
    if direction == "lr":
        part = base.crop((0, 0, max(1, int(w * p)), h))
        canvas.alpha_composite(part, (pad_x, pad_y))
    elif direction == "bt":
        part = base.crop((0, h - max(1, int(h * p)), w, h))
        canvas.alpha_composite(part, (pad_x, pad_y))
    else:  # center out
        k = p / 2.0
        part = base.crop((int(w * (0.5 - k)), 0, int(w * (0.5 + k)) or w, h))
        canvas.alpha_composite(part, (pad_x + (w - part.width) // 2, pad_y))
    return canvas


def _g_alpha_ramp(factory, base, i, n, p, params, cw, ch, pad_x, pad_y):
    lo = params.get("lo", 0.05)
    hi = params.get("hi", 1.0)
    return _set_alpha(_canvas(base, cw, ch, pad_x, pad_y), lo + (hi - lo) * p)


def _g_alpha_breathe(factory, base, i, n, p, params, cw, ch, pad_x, pad_y):
    lo = params.get("lo", 0.35)
    hi = params.get("hi", 1.0)
    k = lo + (hi - lo) * (0.5 + 0.5 * math.sin(2 * math.pi * p))
    return _set_alpha(_canvas(base, cw, ch, pad_x, pad_y), k)


def _g_alpha_flicker(factory, base, i, n, p, params, cw, ch, pad_x, pad_y):
    rng = random.Random(int(params.get("seed", 7)) * 1000 + i)
    k = rng.uniform(0.15, 1.0)
    if rng.random() < 0.12:
        k = 0.05
    return _set_alpha(_canvas(base, cw, ch, pad_x, pad_y), k)


def _g_hue_cycle(factory, base, i, n, p, params, cw, ch, pad_x, pad_y):
    shift = float(params.get("shift", 360)) * p
    c1 = hue_shift(C.parse_color(factory.s.get("color", "#FFFFFF")), shift)
    c2 = None
    if str(factory.s.get("color2", "")).strip():
        c2 = hue_shift(C.parse_color(factory.s.get("color2")), shift)
    img = factory.render(color=C.to_hex(c1),
                         color2=C.to_hex(c2) if c2 else "")
    return _canvas(img, cw, ch, pad_x, pad_y)


def _g_color_swap(factory, base, i, n, p, params, cw, ch, pad_x, pad_y):
    c1 = C.parse_color(factory.s.get("color", "#FFFFFF"))
    c2s = str(factory.s.get("color2", "")).strip()
    c2 = C.parse_color(c2s) if c2s else (255 - c1[0], 255 - c1[1],
                                         255 - c1[2], 255)
    k = 0.5 - 0.5 * math.cos(2 * math.pi * p)
    mid = lerp_color(c1, c2, k)
    img = factory.render(color=C.to_hex(mid))
    return _canvas(img, cw, ch, pad_x, pad_y)


def _g_shimmer(factory, base, i, n, p, params, cw, ch, pad_x, pad_y):
    canvas = _canvas(base, cw, ch, pad_x, pad_y)
    band_w = max(8, int(base.width * 0.28))
    x = int((base.width + band_w) * (p * 2 - 0.5)) + pad_x
    mask = Image.new("L", canvas.size, 0)
    md = ImageDraw.Draw(mask)
    md.rectangle([x, 0, x + band_w // 2, ch], fill=255)
    band = Image.new("RGBA", canvas.size, (255, 255, 255, 235))
    highlight = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    highlight.paste(band, (0, 0), mask)
    hl = highlight.filter(ImageFilter.GaussianBlur(3))
    out = canvas.copy()
    out.alpha_composite(hl)
    return out


def _g_karaoke(factory, base, i, n, p, params, cw, ch, pad_x, pad_y):
    canvas = _canvas(base, cw, ch, pad_x, pad_y)
    accent = C.parse_color(params.get("accent", "#FFD700"))
    acc = factory.render(color=C.to_hex(accent))
    w = max(1, int(acc.width * min(1.0, p * 1.15)))
    part = acc.crop((0, 0, w, acc.height))
    canvas.alpha_composite(part, (pad_x, pad_y))
    return canvas


def _g_glow_pulse(factory, base, i, n, p, params, cw, ch, pad_x, pad_y):
    amount = float(params.get("amount", 0.6))
    k = 1.0 - amount + amount * (0.5 + 0.5 * math.sin(2 * math.pi * p))
    # the pulse must be visible even when the user's glow setting is 0:
    # force a base glow while rendering this sequence
    s = factory.s
    forced = float(s.get("glow", 0) or 0) <= 0
    if forced:
        s["glow"] = 30.0  # glow is on a 0..100 scale
    try:
        img = factory.render(glow_factor=max(0.05, k))
    finally:
        if forced:
            s["glow"] = 0
    # gentle size breath synced with the glow pulse
    return _scale_about_center(_canvas(img, cw, ch, pad_x, pad_y),
                               1 + 0.05 * k, 1 + 0.05 * k)


def _g_pulse_fade(factory, base, i, n, p, params, cw, ch, pad_x, pad_y):
    k = 0.5 + 0.5 * abs(math.sin(2 * math.pi * p))
    img = _set_alpha(_canvas(base, cw, ch, pad_x, pad_y), 0.45 + 0.55 * k)
    return _scale_about_center(img, 1 + 0.12 * k, 1 + 0.12 * k)


def _g_pop_in(factory, base, i, n, p, params, cw, ch, pad_x, pad_y):
    if p < 0.30:
        k = p / 0.30
        scale = 0.2 + 0.8 * _ease_out_back(k)
    else:
        scale = 1.0
    img = _scale_about_center(_canvas(base, cw, ch, pad_x, pad_y),
                              max(0.05, scale), max(0.05, scale))
    if p < 0.08:
        img = _set_alpha(img, p / 0.08)
    return img


def _g_drop_in(factory, base, i, n, p, params, cw, ch, pad_x, pad_y):
    if p < 0.45:
        k = p / 0.45
        dy = -(1 - _ease_out_bounce(k)) * ch * 0.5
    else:
        dy = 0
    return _shifted(_canvas(base, cw, ch, pad_x, pad_y), 0, dy)


def _g_bounce_in(factory, base, i, n, p, params, cw, ch, pad_x, pad_y):
    if p < 0.5:
        k = p / 0.5
        scale = 0.3 + 0.7 * _ease_out_bounce(k)
    else:
        scale = 1.0
    return _scale_about_center(_canvas(base, cw, ch, pad_x, pad_y),
                               max(0.05, scale), max(0.05, scale))


def _g_slide_in_fade(factory, base, i, n, p, params, cw, ch, pad_x, pad_y):
    if p < 0.35:
        k = p / 0.35
        dx = -(1 - k * k) * base.width * 0.45
        alpha = k
    else:
        dx, alpha = 0, 1.0
    return _set_alpha(_shifted(_canvas(base, cw, ch, pad_x, pad_y), dx, 0), alpha)


def _g_elastic(factory, base, i, n, p, params, cw, ch, pad_x, pad_y):
    decay = math.exp(-4.0 * p)
    scale = 1.0 + 0.35 * decay * math.sin(2 * math.pi * 2.5 * p)
    return _scale_about_center(_canvas(base, cw, ch, pad_x, pad_y), scale,
                               1.0 + 0.12 * decay * math.sin(2 * math.pi * 2.5 * p))


def _g_jelly(factory, base, i, n, p, params, cw, ch, pad_x, pad_y):
    k = math.sin(2 * math.pi * 2 * p)
    return _scale_about_center(_canvas(base, cw, ch, pad_x, pad_y),
                               1 + 0.15 * k, 1 - 0.15 * k)


def _g_glitch(factory, base, i, n, p, params, cw, ch, pad_x, pad_y):
    soft = bool(params.get("soft", True))
    rng = random.Random(99 + i)
    amp = base.height * 0.10 if soft else base.height * 0.25
    canvas = _canvas(base, cw, ch, pad_x, pad_y)
    if rng.random() < (0.50 if soft else 0.55):
        out = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        slices = 8 if soft else 12
        sh = max(1, ch // slices)
        for sy in range(0, ch, sh):
            dx = int(rng.uniform(-amp, amp)) if rng.random() < 0.6 else 0
            dy = int(rng.uniform(-amp, amp) * 0.4) if not soft and rng.random() < 0.3 else 0
            part = canvas.crop((0, sy, cw, min(ch, sy + sh)))
            out.alpha_composite(part, (dx, sy + dy))
        canvas = out
        if not soft and rng.random() < 0.6:
            r = _shifted(canvas, 3, 0)
            r.putalpha(r.getchannel("A").point(lambda v: int(v * 0.45)))
            b = _shifted(canvas, -3, 0)
            b.putalpha(b.getchannel("A").point(lambda v: int(v * 0.45)))
            canvas.alpha_composite(r)
            canvas.alpha_composite(b)
    return canvas


_GENERATORS = {
    "typewriter": _g_typewriter,
    "wipe": _g_wipe,
    "alpha_ramp": _g_alpha_ramp,
    "alpha_breathe": _g_alpha_breathe,
    "alpha_flicker": _g_alpha_flicker,
    "hue_cycle": _g_hue_cycle,
    "color_swap": _g_color_swap,
    "shimmer": _g_shimmer,
    "karaoke": _g_karaoke,
    "glow_pulse": _g_glow_pulse,
    "pulse_fade": _g_pulse_fade,
    "pop_in": _g_pop_in,
    "drop_in": _g_drop_in,
    "bounce_in": _g_bounce_in,
    "slide_in_fade": _g_slide_in_fade,
    "elastic": _g_elastic,
    "jelly": _g_jelly,
    "glitch": _g_glitch,
}
