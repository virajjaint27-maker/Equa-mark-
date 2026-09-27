"""Shared helpers for handlers: settings access, keyboards, editing, guards."""
import html
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

import db
from core.settings import normalize

log = logging.getLogger("aquamark.handlers")


# ------------------------------------------------------------- settings

def settings_of(context, user_id):
    cached = context.user_data.get("_settings")
    if cached is None:
        cached = db.get_settings(user_id)
        context.user_data["_settings"] = cached
    return cached


def save_settings(context, user_id, settings):
    settings = normalize(settings)
    db.save_settings(user_id, settings)
    context.user_data["_settings"] = settings
    return settings


def invalidate_settings(context):
    context.user_data.pop("_settings", None)


# ------------------------------------------------------------- keyboards

def kb(rows):
    return InlineKeyboardMarkup(
        [[b for b in row] for row in rows])


def btn(text, data, ce=None):
    """Inline button; ``ce`` optionally names a custom-emoji icon key.

    The icon is only attached when custom emojis are enabled AND a real ID
    is configured (see core/cemoji.py). Otherwise a normal button is built.
    """
    from core import uifont
    text = uifont.stylize(text)
    if ce:
        from core import cemoji
        icon = cemoji.icon_id(ce)
        if icon:
            # premium: custom emoji icon + clean short text
            return cemoji.icon_button(text, callback_data=data,
                                      icon_custom_emoji_id=icon)
        # fallback: the Unicode emoji becomes part of the button text
        return InlineKeyboardButton(
            "%s %s" % (cemoji.custom_emoji(ce), text), callback_data=data)
    return InlineKeyboardButton(text, callback_data=data)


async def reply(message, text, **kw):
    """Custom-emoji-aware message.reply_text (see core/cemoji.py).

    Callers pass text with emoji tokens and HTML as before;
    the wrapper handles entities and the graceful fallback ladder.
    """
    from core import cemoji
    return await cemoji.reply_text(message, text, **kw)


async def branded_photo(message, image_path, caption, **kw):
    """Send ``image_path`` with ``caption`` (font + custom-emoji aware).

    If the image is missing or Telegram rejects it, falls back to a
    normal text message so the flow always continues.
    """
    import os
    from core import cemoji
    if image_path and os.path.isfile(image_path):
        try:
            with open(image_path, "rb") as fh:
                return await cemoji.reply_photo(message, fh, caption, **kw)
        except Exception:
            log.warning("could not send branding image %s"
                        % image_path, exc_info=True)
    return await cemoji.reply_text(message, caption, **kw)


# ------------------------------------------------------------- editing

async def edit_msg(msg, text, **kw):
    """Edit a message's text — or its caption when it carries a photo."""
    from core import cemoji
    if getattr(msg, "photo", None):
        return await cemoji.edit_caption(msg, text, **kw)
    return await cemoji.edit_message(msg, text, **kw)


async def safe_edit(query, text=None, reply_markup=None, **kw):
    """Custom-emoji-aware edit that never surfaces technical errors.

    Smart routing: when the underlying message carries a photo (banner,
    status or menu images) the text becomes the caption and is edited
    via edit_caption; text messages keep the classic edit path.
    """
    from core import cemoji
    try:
        if text is None:
            return await query.edit_message_text(
                None, reply_markup=reply_markup, **kw)
        msg = query.message
        if getattr(msg, "photo", None):
            return await cemoji.edit_caption(msg, text,
                                             reply_markup=reply_markup,
                                             **kw)
        return await cemoji.edit_message(msg, text,
                                         reply_markup=reply_markup, **kw)
    except BadRequest as exc:
        if "not modified" in str(exc).lower():
            return
        if "message to edit not found" in str(exc).lower():
            return
        raise
    except Exception:
        log.exception("edit failed")


async def answer_safely(query, text=None):
    try:
        await query.answer(text=text)
    except Exception:
        pass


# ------------------------------------------------------------- guards

def user_id_of(update):
    u = update.effective_user
    return u.id if u else 0


def chat_id_of(update):
    c = update.effective_chat
    return c.id if c else 0


def is_owner(update):
    import config
    if not config.OWNER_ID:
        return False
    return user_id_of(update) == config.OWNER_ID


# ------------------------------------------------------------- awaiting input

def set_await(context, kind, extra=None):
    context.user_data["await"] = {"kind": kind, "extra": extra or {}}


def pop_await(context):
    return context.user_data.pop("await", None)


# ------------------------------------------------------------- misc fmt

def bar(frac, width=10):
    frac = max(0.0, min(1.0, frac))
    filled = int(round(frac * width))
    return "▓" * filled + "░" * (width - filled) + " %3d%%" % int(frac * 100)


def esc(text):
    return html.escape(str(text or ""))


def busy_note():
    return ("[[clock]] You already have a job running — it'll finish in a "
            "moment. I'll ping you here.")
