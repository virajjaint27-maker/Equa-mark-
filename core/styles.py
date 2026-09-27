"""Visual style presets — one-tap professional looks."""

# id -> (label, icon, overrides)
STYLES = {
    "clean": ("Clean", "⬜", {}),
    "neon": ("Neon", "💡", {"color": "#00F0FF", "glow": 80, "glow_color": "#00F0FF",
                            "stroke_w": 0}),
    "neon-pink": ("Neon Pink", "🌸", {"color": "#FF2E97", "glow": 85,
                                       "glow_color": "#FF2E97"}),
    "gold": ("Gold", "🥇", {"color": "#FFE259", "color2": "#B8860B", "shadow": 35}),
    "silver": ("Silver", "🥈", {"color": "#FFFFFF", "color2": "#9AA0A6", "shadow": 25}),
    "sticker": ("Sticker", "🏷", {"color": "#FFFFFF", "stroke_w": 12,
                                   "stroke_color": "#000000"}),
    "outline": ("Outline", "⭕", {"color": "#FFFFFF", "stroke_w": 6,
                                   "stroke_color": "#000000"}),
    "shadow": ("Shadow", "🌓", {"color": "#FFFFFF", "shadow": 55, "shadow_color": "#000000"}),
    "glass": ("Glass", "🧊", {"color": "#FFFFFF", "box": True, "box_color": "#FFFFFF",
                               "box_opacity": 0.18, "box_radius": 60, "box_pad": 45,
                               "shadow": 20}),
    "darkbar": ("Dark Bar", "⬛", {"color": "#FFFFFF", "box": True,
                                    "box_color": "#000000", "box_opacity": 0.55,
                                    "box_radius": 0, "box_pad": 60}),
    "badge": ("Badge", "🛡", {"color": "#111111", "box": True, "box_color": "#FFD700",
                               "box_opacity": 1.0, "box_radius": 50, "box_pad": 40,
                               "shadow": 30}),
    "fire": ("Fire", "🔥", {"color": "#FFB199", "color2": "#FF512F", "glow": 60,
                             "glow_color": "#FF6A00"}),
    "ice": ("Ice", "🧊", {"color": "#E0F7FF", "color2": "#8ED8F8", "glow": 55,
                           "glow_color": "#4FC3F7"}),
    "mint": ("Mint", "🌿", {"color": "#B9F8D0", "glow": 45, "glow_color": "#3EF6B0"}),
    "brand": ("Brand", "💼", {"color": "#FFFFFF", "font": "montserrat", "shadow": 30,
                               "box": True, "box_color": "#111111", "box_opacity": 0.65,
                               "box_radius": 40, "box_pad": 40}),
    "poster": ("Poster", "🎬", {"color": "#FFFFFF", "font": "bebas", "size_pct": 14,
                                 "stroke_w": 3, "shadow": 40}),
    "elegant": ("Elegant", "🎩", {"color": "#F5E9D7", "font": "playfair",
                                   "shadow": 25, "stroke_w": 1,
                                   "stroke_color": "#3A2E2A"}),
}

_DESCRIPTIONS = {
    "clean": "plain text, no effects",
    "neon": "cyan neon glow",
    "neon-pink": "hot pink neon glow",
    "gold": "golden gradient",
    "silver": "silver gradient",
    "sticker": "thick black outline",
    "outline": "thin outline",
    "shadow": "soft drop shadow",
    "glass": "frosted glass panel",
    "darkbar": "solid dark bar",
    "badge": "gold pill badge",
    "fire": "fire gradient + ember glow",
    "ice": "icy gradient + cool glow",
    "mint": "mint glow",
    "brand": "bold brand bar",
    "poster": "big condensed headline",
    "elegant": "serif luxury",
}


def apply_style(settings, style_id):
    """Return a new settings dict with the style's visual overrides applied.

    Only visual fields are touched — text, position, animation stay.
    """
    from . import settings as S

    s = dict(settings)
    entry = STYLES.get(style_id)
    if entry:
        s["style"] = style_id
        s.update(entry[2])
    return S.normalize(s)


def style_choices():
    return [(sid, "%s %s — %s" % (e[1], e[0], _DESCRIPTIONS.get(sid, "")))
            for sid, e in STYLES.items()]
