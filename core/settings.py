"""Per-user watermark settings: defaults, validation, normalization."""
from . import colors, fonts

DEFAULTS = {
    # content
    "wm_type": "text",            # text | logo
    "text": "",                   # watermark text ("" -> bot asks)
    "template_vars": True,        # resolve {date} {user} ... in text
    # look
    "color": "#FFFFFF",
    "color2": "",                 # second color -> vertical gradient ("")
    "style": "clean",
    "font": fonts.DEFAULT_FONT_ID,
    "size_pct": 8.0,              # font height as % of min(W,H) of media
    "opacity": 0.9,               # 0.05..1.0
    "stroke_w": 0.0,              # stroke width, % of font size (0=off)
    "stroke_color": "#000000",
    "shadow": 0.0,                # strength 0..100
    "shadow_color": "#000000",
    "glow": 0.0,                  # strength 0..100
    "glow_color": "",             # "" -> same as color
    "box": False,                 # background box behind text
    "box_color": "#000000",
    "box_opacity": 0.45,
    "box_pad": 35.0,              # % of font size
    "box_radius": 50.0,           # % of font size (>=50 -> pill)
    "rotation": 0.0,              # degrees -180..180
    # placement
    "position": "br",
    "margin": 4.0,                # % of min(W,H)
    "tile": False,                # repeat watermark over whole media
    "tile_gap": 30.0,             # gap between tiles, % of tile size
    "tile_angle": -30.0,          # diagonal angle for tiles
    # motion
    "animation": "static",
    "anim_speed": 1.0,            # 0.25..4.0
    "loop_secs": 4.0,             # photo->animated loop duration
    # output
    "out_format": "auto",         # auto | mp4 | gif
    "quality": "high",
    "keep_audio": True,
    "send_as": "auto",            # auto | video | document
    # behaviour
    "auto_mode": True,            # process incoming media immediately
}

_RANGES = {
    "size_pct": (1.0, 40.0),
    "opacity": (0.05, 1.0),
    "stroke_w": (0.0, 15.0),
    "shadow": (0.0, 100.0),
    "glow": (0.0, 100.0),
    "box_opacity": (0.05, 1.0),
    "box_pad": (5.0, 120.0),
    "box_radius": (0.0, 100.0),
    "rotation": (-180.0, 180.0),
    "margin": (0.0, 25.0),
    "tile_gap": (5.0, 150.0),
    "tile_angle": (-90.0, 90.0),
    "anim_speed": (0.25, 4.0),
    "loop_secs": (2.0, 15.0),
}

_ENUMS = {
    "wm_type": ["text", "logo"],
    "style": None,        # filled below from styles module (avoid cycle: checked dynamically)
    "font": None,         # filled dynamically
    "position": ["tl", "tc", "tr", "cl", "cc", "cr", "bl", "bc", "br"],
    "out_format": ["auto", "mp4", "gif"],
    "quality": ["low", "medium", "high", "ultra"],
    "send_as": ["auto", "video", "document"],
    "animation": None,    # checked dynamically against registry
}


def _clamp(name, value, lo, hi):
    try:
        v = float(value)
    except (TypeError, ValueError):
        v = DEFAULTS[name]
    return round(max(lo, min(hi, v)), 2)


def _color_field(value, default):
    try:
        return colors.to_hex(colors.parse_color(value))
    except colors.ColorError:
        return default


def normalize(s):
    """Return a safe, fully-typed settings dict (unknown keys dropped)."""
    from . import animations, styles

    out = dict(DEFAULTS)
    if not isinstance(s, dict):
        return out
    for k in DEFAULTS:
        if k in s and s[k] is not None:
            out[k] = s[k]

    # numerics
    for k, (lo, hi) in _RANGES.items():
        out[k] = _clamp(k, out[k], lo, hi)
    # booleans
    for k in ("template_vars", "box", "tile", "keep_audio", "auto_mode"):
        out[k] = bool(out[k]) if not isinstance(out[k], str) else \
            out[k].strip().lower() in ("1", "true", "yes", "on")
    # enums
    if out["font"] not in fonts.FONTS:
        out["font"] = DEFAULTS["font"]
    if out["style"] not in styles.STYLES:
        out["style"] = DEFAULTS["style"]
    if out["position"] not in _ENUMS["position"]:
        out["position"] = DEFAULTS["position"]
    if out["out_format"] not in _ENUMS["out_format"]:
        out["out_format"] = DEFAULTS["out_format"]
    if out["quality"] not in _ENUMS["quality"]:
        out["quality"] = DEFAULTS["quality"]
    if out["send_as"] not in _ENUMS["send_as"]:
        out["send_as"] = DEFAULTS["send_as"]
    if out["wm_type"] not in _ENUMS["wm_type"]:
        out["wm_type"] = DEFAULTS["wm_type"]
    if out["animation"] not in animations.REGISTRY:
        out["animation"] = DEFAULTS["animation"]
    # colors
    out["color"] = _color_field(out["color"], DEFAULTS["color"])
    out["color2"] = _color_field(out["color2"], "") if str(out["color2"]).strip() else ""
    out["stroke_color"] = _color_field(out["stroke_color"], DEFAULTS["stroke_color"])
    out["shadow_color"] = _color_field(out["shadow_color"], DEFAULTS["shadow_color"])
    out["glow_color"] = _color_field(out["glow_color"], "") if str(out["glow_color"]).strip() else ""
    out["box_color"] = _color_field(out["box_color"], DEFAULTS["box_color"])
    # text
    out["text"] = str(out["text"])[:200].strip() if out["text"] else ""
    return out


def merge(saved):
    """defaults <- stored json, then normalize."""
    return normalize(saved if isinstance(saved, dict) else {})


def describe(s):
    """Short human summary used in status lines."""
    bits = []
    if s["wm_type"] == "logo":
        bits.append("logo")
    else:
        bits.append("text" if s["text"] else "no text yet")
    bits.append(s["color"] if not s["color2"] else "%s→%s" % (s["color"], s["color2"]))
    bits.append("size %g%%" % s["size_pct"])
    if s["animation"] != "static":
        bits.append("anim: %s" % s["animation"])
    if s["tile"]:
        bits.append("tiled")
    return " • ".join(bits)
