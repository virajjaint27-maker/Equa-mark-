"""Unicode UI font for AquaMark — the "𝐓ʀᴀᴠᴇʟ ᴠᴏᴛᴇ" look.

Every outgoing bot message and button label is rendered in a small-caps
styled alphabet: uppercase letters become bold mathematical capitals
(𝐀…𝐙) and lowercase letters become small caps (ᴀʙᴄ…ᴢ), matching the
owner's requested style.

Safety rules (what stylize() never touches):
  * ``[[tokens]]``           — decoded later by core.cemoji
  * HTML tags (<b>, </i>…)   — needed for parse_mode="HTML"
  * <code>/<pre> content     — values users copy (hex colors…)
  * /commands, @usernames, #tags — must stay tappable ASCII
  * URLs, digits, emoji, non-Latin scripts (हिन्दी, العربية…)

The whole feature is behind ``AQM_UI_FONT`` (default on).
"""
from __future__ import annotations

import re

# lowercase -> small caps (x has no small-cap form; q uses the ogonek form)
_SMALL = {
    "a": "ᴀ", "b": "ʙ", "c": "ᴄ", "d": "ᴅ", "e": "ᴇ", "f": "ꜰ",
    "g": "ɢ", "h": "ʜ", "i": "ɪ", "j": "ᴊ", "k": "ᴋ", "l": "ʟ",
    "m": "ᴍ", "n": "ɴ", "o": "ᴏ", "p": "ᴘ", "q": "ǫ", "r": "ʀ",
    "s": "ꜱ", "t": "ᴛ", "u": "ᴜ", "v": "ᴠ", "w": "ᴡ", "x": "x",
    "y": "ʏ", "z": "ᴢ",
}
# uppercase -> mathematical bold capitals (U+1D400..U+1D419)
_BOLD = {chr(c): chr(0x1D400 + (c - ord("A"))) for c in range(ord("A"),
                                                             ord("Z") + 1)}

_TABLE = {ord(k): v for k, v in {**_SMALL, **_BOLD}.items()}

# spans that must survive untouched, in priority order
_PROTECT = re.compile(
    r"\[\[[a-z_]+\]\]"                      # [[emoji tokens]]
    r"|</?[a-zA-Z][^<>]*>"                  # HTML tags
    r"|<code>.*?</code>|<pre>.*?</pre>"     # verbatim blocks
    r"|(?<!\w)/[A-Za-z0-9_]+"               # /commands
    r"|@[A-Za-z0-9_]+"                      # @usernames
    r"|#[A-Za-z0-9_]+"                      # #tags / hex shown inline
    r"|(?:https?://|t\.me/)\S+"             # URLs
    , re.IGNORECASE | re.DOTALL)


def active() -> bool:
    """Is the UI font enabled? (AQM_UI_FONT, default on)"""
    import config
    return bool(getattr(config, "USE_UI_FONT", True))


def _stylize_span(text: str) -> str:
    return text.translate(_TABLE)


def stylize(text: str) -> str:
    """Render ``text`` in the small-caps UI font, protecting tokens,
    markup, commands, mentions, tags and URLs."""
    if not text:
        return text
    if not active():
        return text
    out = []
    pos = 0
    for m in _PROTECT.finditer(text):
        out.append(_stylize_span(text[pos:m.start()]))
        out.append(m.group(0))            # protected — verbatim
        pos = m.end()
    out.append(_stylize_span(text[pos:]))
    return "".join(out)
