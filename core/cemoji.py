"""Custom-emoji system for AquaMark (Telegram Premium custom emoji).

Architecture (see spec):

    config (USE_CUSTOM_EMOJIS)
      -> CUSTOM_EMOJIS definitions (this module — paste real IDs here)
        -> prepare()/expand()/icon helpers (this module)
          -> handlers/common.py send/edit/button wrappers
            -> bot handlers

How it works
------------
Message templates keep human-readable tokens like ``[[water]]``. At send
time the token is replaced by the *fallback Unicode emoji* (e.g. 💧) which
stays in the text for everyone. When custom emojis are active, a
``custom_emoji`` MessageEntity wrapping EXACTLY that one emoji character is
attached alongside, carrying the ``custom_emoji_id``. Premium clients render
the custom emoji; everyone else sees the normal Unicode fallback.

UTF-16 offsets
-------------
Telegram entity offsets/lengths are counted in UTF-16 code units, not Python
characters. Most emoji live outside the BMP and cost 2 UTF-16 units per
Python character. All spans in this module are computed on the final plain
text with ``_u16len`` / prefix sums, never with ``len(str)``.

Send-time fallback
------------------
Telegram only accepts custom emoji from bots that own a Fragment collectible
username; IDs may also be invalid or belong to packs the bot cannot use. The
send/edit wrappers therefore try a ladder:

    1. full message (formatting entities + custom emoji entities + icon
       buttons)
    2. formatting entities only, icon buttons stripped
    3. plain text, plain buttons

API errors are logged, never shown to the user. After repeated custom-emoji
rejections a circuit breaker disables custom emojis until restart.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import config
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, MessageEntity
from telegram.error import TelegramError

log = logging.getLogger("aquamark.cemoji")

# ---------------------------------------------------------------------------
# 1. Definitions — paste your real custom emoji IDs here.
#
#    How to get the IDs:
#      * custom emojis are created in the Telegram app (Stickers & Emoji ->
#        "Create emoji pack" — requires Premium on the creating account), or
#        grab any existing custom emoji someone sent you;
#      * send a message containing the custom emojis to the bot and reply to
#        it with /emojiids — the bot lists every custom_emoji_id it found.
#
#    Each entry needs:
#      "id":       the numeric custom_emoji_id string from Telegram
#      "fallback": the plain Unicode emoji shown when the custom one is not
#                  rendered (non-Premium clients, custom emojis disabled,
#                  or send-time fallback). The fallback is what physically
#                  stays in the message text.
# ---------------------------------------------------------------------------
PLACEHOLDER = "CUSTOM_EMOJI_ID_HERE"

CUSTOM_EMOJIS: Dict[str, Dict[str, str]] = {
    # key         custom emoji id          fallback shown otherwise
    "water":    {"id": PLACEHOLDER, "fallback": "💧"},
    "check":    {"id": PLACEHOLDER, "fallback": "✅"},
    "settings": {"id": PLACEHOLDER, "fallback": "⚙️"},
    "image":    {"id": PLACEHOLDER, "fallback": "🖼️"},
    "video":    {"id": PLACEHOLDER, "fallback": "🎥"},
    "pdf":      {"id": PLACEHOLDER, "fallback": "📄"},
    "warning":  {"id": PLACEHOLDER, "fallback": "⚠️"},
    "rocket":   {"id": PLACEHOLDER, "fallback": "🚀"},
    # --- additional keys used across AquaMark's flows -------------------
    "wave":     {"id": PLACEHOLDER, "fallback": "👋"},
    "help":     {"id": PLACEHOLDER, "fallback": "❓"},
    "anim":     {"id": PLACEHOLDER, "fallback": "🎞"},
    "palette":  {"id": PLACEHOLDER, "fallback": "🎨"},
    "tools":    {"id": PLACEHOLDER, "fallback": "🧰"},
    "search":   {"id": PLACEHOLDER, "fallback": "🔎"},
    "brush":    {"id": PLACEHOLDER, "fallback": "🖌"},
    "film":     {"id": PLACEHOLDER, "fallback": "🎬"},
    "download": {"id": PLACEHOLDER, "fallback": "⬇️"},
    "clock":    {"id": PLACEHOLDER, "fallback": "⏳"},
    "info":     {"id": PLACEHOLDER, "fallback": "ℹ️"},
    "sparkle":  {"id": PLACEHOLDER, "fallback": "✨"},
    "party":    {"id": PLACEHOLDER, "fallback": "🎉"},
    "sad":      {"id": PLACEHOLDER, "fallback": "😵"},
    "stop":     {"id": PLACEHOLDER, "fallback": "🚫"},
    "eyes":     {"id": PLACEHOLDER, "fallback": "👁"},
    "shield":   {"id": PLACEHOLDER, "fallback": "🛡"},
}

# ---------------------------------------------------------------------------
# 2. State / switches
# ---------------------------------------------------------------------------
# Runtime circuit breaker: set after repeated rejections so we stop paying
# a failed round-trip on every message. Cleared on process restart.
_tripped: bool = False
_trip_count: int = 0
_TRIP_AT: int = 3


def ids_configured() -> bool:
    """True when at least one real (non-placeholder) emoji id is set."""
    return any(e["id"] not in ("", PLACEHOLDER)
               for e in CUSTOM_EMOJIS.values())


def active() -> bool:
    """True when custom emojis should be attempted right now."""
    return (bool(getattr(config, "USE_CUSTOM_EMOJIS", False))
            and ids_configured() and not _tripped)


def icon_id(key: str) -> Optional[str]:
    """Custom emoji id for a key, or None when unusable."""
    if not active():
        return None
    entry = CUSTOM_EMOJIS.get(key)
    if not entry or entry["id"] in ("", PLACEHOLDER):
        return None
    return entry["id"]


def custom_emoji(key: str, fallback: Optional[str] = None) -> str:
    """The emoji character to physically embed in message text.

    Returns the configured fallback Unicode emoji for ``key`` (or
    ``fallback`` when the key is unknown). This is NOT the custom emoji id —
    the id travels in a MessageEntity produced by ``prepare()``.
    """
    entry = CUSTOM_EMOJIS.get(key)
    if entry:
        return entry["fallback"]
    return fallback if fallback is not None else ""


# ---------------------------------------------------------------------------
# 3. Token expansion + HTML parsing -> entities (single exact pass)
# ---------------------------------------------------------------------------
_TOKEN_RE = re.compile(r"\[\[([a-z0-9_]+)\]\]")

# HTML subset used by AquaMark's message templates -> Telegram entity types
_TAG_RE = re.compile(
    r"<(?P<close>/)?(?P<tag>b|strong|i|em|u|ins|s|strike|del|code|pre)"
    r"(?P<selfclose>\s*/)?>"
    r"|<a\s+href=\"(?P<url>[^\"]*)\"\s*>|</a>",
    re.IGNORECASE)

_TAG_TYPE = {
    "b": MessageEntity.BOLD, "strong": MessageEntity.BOLD,
    "i": MessageEntity.ITALIC, "em": MessageEntity.ITALIC,
    "u": MessageEntity.UNDERLINE, "ins": MessageEntity.UNDERLINE,
    "s": MessageEntity.STRIKETHROUGH, "strike": MessageEntity.STRIKETHROUGH,
    "del": MessageEntity.STRIKETHROUGH,
    "code": MessageEntity.CODE, "pre": MessageEntity.PRE,
}

# (kind, char_start, char_end, extra) — kind: etype str or ("ce", key)
_Span = Tuple


@dataclass
class Prepared:
    """Result of preparing a template for sending."""
    # text to actually send — tokens replaced by fallback emoji
    text: str
    # formatting entities (bold/italic/code/link) on `text`, or None to let
    # the caller use parse_mode="HTML" on the untouched template instead
    fmt_entities: Optional[List[MessageEntity]] = None
    # custom_emoji entities on `text`
    custom_entities: List[MessageEntity] = field(default_factory=list)

    @property
    def has_custom(self) -> bool:
        return bool(self.custom_entities)


def _u16len(s: str) -> int:
    """Length in UTF-16 code units (what Telegram counts), not characters.

    Emoji outside the BMP (U+10000..U+10FFFF) cost 2 UTF-16 units per Python
    character, so len(s) would under-count. Encoding to UTF-16 and dividing
    by 2 gives the exact unit count.
    """
    return len(s.encode("utf-16-le")) // 2


def _u16_prefix(text: str) -> List[int]:
    """Prefix sums: _u16_prefix(t)[i] = UTF-16 length of t[:i]."""
    out = [0] * (len(text) + 1)
    total = 0
    for i, ch in enumerate(text):
        total += 2 if ord(ch) > 0xFFFF else 1
        out[i + 1] = total
    return out


def _decode(text: str, with_custom: bool) -> Prepared:
    """Single pass over a template.

    * ``[[key]]`` tokens become the fallback emoji character; when
      ``with_custom`` a custom_emoji entity is recorded wrapping EXACTLY
      that emoji (its full UTF-16 span).
    * HTML tags are decoded into formatting entities with UTF-16 offsets
      computed on the final plain text.
    Malformed markup is dropped, never raised.
    """
    parts: List[str] = []
    spans: List[_Span] = []          # (kind, start_char, end_char, extra)
    stack: List[Tuple[int, str]] = []      # open formatting tags
    links: List[Tuple[int, str]] = []      # open <a href> (start, url)
    pos = 0

    def _emit(fragment: str) -> None:
        parts.append(fragment)

    def _charpos() -> int:
        return sum(len(p) for p in parts)

    combined = re.compile(
        _TOKEN_RE.pattern + "|" + _TAG_RE.pattern, re.IGNORECASE)

    for m in combined.finditer(text):
        _emit(text[pos:m.start()])
        pos = m.end()
        tok = m.group(1)
        if tok is not None:                       # [[key]]
            entry = CUSTOM_EMOJIS.get(tok)
            if entry is None:
                _emit(m.group(0))                 # unknown token: verbatim
                continue
            start = _charpos()
            _emit(entry["fallback"])
            if with_custom and entry["id"] not in ("", PLACEHOLDER):
                spans.append((MessageEntity.CUSTOM_EMOJI, start,
                              _charpos(), entry["id"]))
        elif m.group("tag"):
            etype = _TAG_TYPE[m.group("tag").lower()]
            if m.group("close") or m.group("selfclose"):
                for i in range(len(stack) - 1, -1, -1):
                    if stack[i][1] == etype:
                        start = stack.pop(i)[0]
                        spans.append((etype, start, _charpos(), None))
                        break
            else:
                stack.append((_charpos(), etype))
        elif m.group("url") is not None:          # <a href="...">
            links.append((_charpos(), m.group("url")))
        elif m.lastgroup is None and m.group(0) == "</a>":
            if links:
                start, url = links.pop()
                spans.append((MessageEntity.TEXT_LINK, start, _charpos(),
                              url))
        else:                                     # stray </a> etc.
            pass
    _emit(text[pos:])
    plain = "".join(parts)

    prefix = _u16_prefix(plain)
    fmt_entities: List[MessageEntity] = []
    custom_entities: List[MessageEntity] = []
    for kind, start, end, extra in spans:
        if end <= start:
            continue
        if kind == MessageEntity.CUSTOM_EMOJI:
            # wraps exactly one emoji: length = its UTF-16 unit count
            custom_entities.append(MessageEntity(
                type=MessageEntity.CUSTOM_EMOJI,
                offset=prefix[start], length=prefix[end] - prefix[start],
                custom_emoji_id=extra))
        elif kind == MessageEntity.TEXT_LINK:
            fmt_entities.append(MessageEntity(
                type=MessageEntity.TEXT_LINK,
                offset=prefix[start], length=prefix[end] - prefix[start],
                url=extra or ""))
        else:
            fmt_entities.append(MessageEntity(
                type=kind, offset=prefix[start],
                length=prefix[end] - prefix[start]))
    return Prepared(text=plain, fmt_entities=fmt_entities or None,
                    custom_entities=custom_entities)


def _expand_only(text: str) -> str:
    """Replace known ``[[key]]`` tokens, leaving everything else (including
    HTML) verbatim — used when custom emojis are inactive so callers can
    keep the classic parse_mode="HTML" send path."""
    def _sub(m):
        entry = CUSTOM_EMOJIS.get(m.group(1))
        return entry["fallback"] if entry else m.group(0)
    return _TOKEN_RE.sub(_sub, text)


def prepare(text: str) -> Prepared:
    """Turn a template (tokens + HTML) into a sendable form.

    When custom emojis are not active, returns the template with tokens
    replaced by plain emoji and ``fmt_entities=None`` — callers then send
    with parse_mode="HTML" exactly as before (zero behavior change).
    When active, returns decoded plain text plus formatting entities plus
    custom-emoji entities (offsets in UTF-16 units).
    """
    if not isinstance(text, str):
        text = str(text)
    if not active():
        # tokens only; HTML stays for the normal parse_mode path
        return Prepared(text=_expand_only(text), fmt_entities=None,
                        custom_entities=[])
    return _decode(text, with_custom=True)


def expand(text: str) -> str:
    """Replace ``[[key]]`` tokens with plain fallback emoji (no entities).

    For captions and other places that stay on the plain-text path.
    """
    return _decode(text, with_custom=False).text


# ---------------------------------------------------------------------------
# 4. Buttons with custom emoji icons
# ---------------------------------------------------------------------------
class IconInlineButton(InlineKeyboardButton):
    """InlineKeyboardButton carrying icon_custom_emoji_id.

    The vendored PTB version predates this Bot API field, so we attach it in
    a subclass and make sure it is included in the JSON payload. Telegram
    itself accepts the field (Bot API 7.2+) regardless of library version.
    """
    __slots__ = ("icon_custom_emoji_id",)

    def __init__(self, *args, icon_custom_emoji_id: Optional[str] = None,
                 **kwargs):
        super().__init__(*args, **kwargs)
        object.__setattr__(self, "icon_custom_emoji_id",
                           icon_custom_emoji_id or None)

    def to_dict(self):
        d = super().to_dict()
        if self.icon_custom_emoji_id:
            d["icon_custom_emoji_id"] = self.icon_custom_emoji_id
        return d


def icon_button(text: str, *, callback_data: Optional[str] = None,
                url: Optional[str] = None,
                icon_custom_emoji_id: Optional[str] = None) -> InlineKeyboardButton:
    """Build a button with a custom emoji icon (or a plain one as fallback)."""
    if icon_custom_emoji_id and active():
        kw = {"text": text}
        if callback_data is not None:
            kw["callback_data"] = callback_data
        if url is not None:
            kw["url"] = url
        return IconInlineButton(icon_custom_emoji_id=icon_custom_emoji_id,
                                **kw)
    return InlineKeyboardButton(text, callback_data=callback_data, url=url)


def markup_has_icons(markup: Optional[InlineKeyboardMarkup]) -> bool:
    if markup is None:
        return False
    return any(isinstance(b, IconInlineButton) and b.icon_custom_emoji_id
               for row in markup.inline_keyboard for b in row)


def strip_icons(markup: Optional[InlineKeyboardMarkup]
                ) -> Optional[InlineKeyboardMarkup]:
    """Rebuild a keyboard without custom-emoji icons (fallback level 2)."""
    if not markup_has_icons(markup):
        return markup
    rows = []
    for row in markup.inline_keyboard:
        new_row = []
        for b in row:
            new_row.append(InlineKeyboardButton(
                text=b.text, callback_data=b.callback_data, url=b.url))
        rows.append(new_row)
    return InlineKeyboardMarkup(rows)


# ---------------------------------------------------------------------------
# 5. Send/edit wrappers with the fallback ladder
# ---------------------------------------------------------------------------
_BENIGNS = ("message is not modified", "message to edit not found",
           "query is too old")


def _benign(exc: Exception) -> bool:
    """Errors that are not about custom emojis and must not trigger a retry."""
    return any(b in str(exc).lower() for b in _BENIGNS)


def note_rejection():
    """Count a custom-emoji rejection; trip the breaker after repeated ones."""
    global _tripped, _trip_count
    _trip_count += 1
    if _trip_count >= _TRIP_AT and not _tripped:
        _tripped = True
        log.warning(
            "custom emojis disabled for this session after %d rejections "
            "(bot likely lacks a Fragment collectible username or the IDs "
            "are invalid); falling back to Unicode emoji", _trip_count)


async def reply_text(message, text: str, **kw):
    """message.reply_text with custom-emoji support and graceful fallback.

    Ladder: (1) custom entities + icon buttons, (2) formatting only with
    icon buttons stripped, (3) plain text. Technical errors are logged,
    never surfaced; only a failure of the plain attempt is re-raised (a
    genuine transport problem the caller already handles).
    """
    prepared = prepare(text)
    markup = kw.get("reply_markup")
    rest = {k: v for k, v in kw.items() if k != "reply_markup"}
    icons = markup_has_icons(markup)

    if not prepared.has_custom and not icons:
        # fast path — identical to the classic send (parse_mode kept)
        return await message.reply_text(prepared.text, **kw)

    # ---- level 1: custom emoji entities and/or icon buttons -------------
    if prepared.has_custom:
        entities = (prepared.fmt_entities or []) + prepared.custom_entities
        try:
            return await message.reply_text(
                prepared.text, entities=entities or None,
                reply_markup=markup, **rest)
        except TelegramError as exc:
            if _benign(exc):
                raise
            log.info("custom-emoji send rejected (%s); demoting", exc)
    elif icons and prepared.fmt_entities is None:
        # no text entities needed — keep the HTML parse_mode path + icons
        try:
            return await message.reply_text(prepared.text,
                                            reply_markup=markup, **rest)
        except TelegramError as exc:
            if _benign(exc):
                raise
            log.info("icon-button send rejected (%s); demoting", exc)

    # ---- level 2: formatting only, icons stripped -----------------------
    markup2 = strip_icons(markup)
    rest2 = {k: v for k, v in rest.items() if k != "parse_mode"}
    try:
        if prepared.fmt_entities:
            res = await message.reply_text(
                prepared.text, entities=prepared.fmt_entities,
                reply_markup=markup2, **rest2)
        else:
            res = await message.reply_text(prepared.text,
                                           reply_markup=markup2, **rest2)
        # the demotion worked -> the rejection was custom-emoji related
        if prepared.has_custom or icons:
            note_rejection()
        return res
    except TelegramError as exc:
        if _benign(exc):
            raise
        log.warning("send failed without custom emojis too (%s); "
                    "trying plain text", exc)

    # ---- level 3: plain text --------------------------------------------
    if prepared.has_custom or icons:
        note_rejection()
    return await message.reply_text(prepared.text, reply_markup=markup2,
                                    **rest2)


async def edit_message(msg, text: str, **kw):
    """msg.edit_text with the same custom-emoji fallback ladder."""
    prepared = prepare(text)
    markup = kw.get("reply_markup")
    rest = {k: v for k, v in kw.items() if k != "reply_markup"}
    icons = markup_has_icons(markup)

    if not prepared.has_custom and not icons:
        return await msg.edit_text(prepared.text, **kw)

    if prepared.has_custom:
        entities = (prepared.fmt_entities or []) + prepared.custom_entities
        try:
            return await msg.edit_text(prepared.text,
                                       entities=entities or None,
                                       reply_markup=markup, **rest)
        except TelegramError as exc:
            if _benign(exc):
                raise
            log.info("custom-emoji edit rejected (%s); demoting", exc)
    elif icons and prepared.fmt_entities is None:
        try:
            return await msg.edit_text(prepared.text, reply_markup=markup,
                                       **rest)
        except TelegramError as exc:
            if _benign(exc):
                raise
            log.info("icon-button edit rejected (%s); demoting", exc)

    markup2 = strip_icons(markup)
    rest2 = {k: v for k, v in rest.items() if k != "parse_mode"}
    try:
        if prepared.fmt_entities:
            res = await msg.edit_text(prepared.text,
                                      entities=prepared.fmt_entities,
                                      reply_markup=markup2, **rest2)
        else:
            res = await msg.edit_text(prepared.text, reply_markup=markup2,
                                      **rest2)
        if prepared.has_custom or icons:
            note_rejection()
        return res
    except TelegramError as exc:
        if _benign(exc):
            raise
        log.warning("edit failed without custom emojis too (%s); "
                    "trying plain text", exc)

    if prepared.has_custom or icons:
        note_rejection()
    return await msg.edit_text(prepared.text, reply_markup=markup2, **rest2)
