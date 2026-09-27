"""Start, help, features, onboarding, logo, text, auto-mode commands."""
import logging
import os
import time

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes, MessageHandler, filters

import config
import db
from core.animations import count as anim_count
from handlers import common as H
from handlers import settings_ui

log = logging.getLogger("aquamark.start")

_STARTED_AT = time.time()

WELCOME = (
    "[[wave]] <b>Welcome to AquaMark!</b>\n\n"
    "Your personal media watermarking assistant.\n\n"
    "Send me an image, video or PDF — forwarded works too — and I'll help "
    "you watermark it quickly.\n\n"
    "<b>Features</b>\n"
    "[[image]] Images & Photos\n"
    "[[video]] Videos, GIFs & video notes\n"
    "[[pdf]] PDF files\n"
    "[[anim]] %d animations — DVD bounce, glitch, typewriter…\n"
    "[[palette]] Colors, gradients, 17 styles, 9 fonts\n"
    "[[settings]] Custom watermark options — position, opacity, rotation, "
    "tiling\n\n"
    "<b>Send your first file to get started!</b> [[rocket]]\n\n"
    "[[help]] Guide: /help · Feature tour: /features"
)

HELP = (
    "[[info]] <b>AquaMark — Guide</b>\n\n"
    "<b>Watermarking</b>\n"
    "• Send/forward any photo, video, GIF or video note — I watermark it "
    "with your saved look\n"
    "• /wm &lt;text&gt; — set watermark text\n"
    "• /setlogo — reply to a PNG to use a logo watermark\n"
    "• /auto — toggle instant processing (no confirm button)\n\n"
    "[[settings]] <b>Customize</b>\n"
    "• /settings — the full control panel\n"
    "• /color &lt;color&gt; — e.g. /color #FF6600 or /color gold\n"
    "• /gradient &lt;c1&gt;&gt;&lt;c2&gt; — e.g. /gradient #fff&gt;#f00\n"
    "• /animation — browse %d animations with live demos\n"
    "• /style, /font, /size, /opacity, /position, /rotation …\n"
    "• /profiles — save &amp; switch named looks\n\n"
    "[[tools]] <b>Media tools</b> (reply to media, or caption it)\n"
    "/stickerize /circle /resize /compress /convert /trim /tomp3 /speed "
    "/reverse /mute /ss /meta /gray /sepia /blurbg\n\n"
    "[[sparkle]] <b>Other</b>\n"
    "/features · /about · /ping · /stats (yours) · /reset\n\n"
    "💡 Tips: albums are batch-processed; videos up to 20 MB (Telegram Bot "
    "API limit); watermark text supports {date} {user} {count} variables."
)

FEATURES = [
    ("[[water]] Core watermarking", [
        "Text watermarks on photos", "Text watermarks on videos", "PDF watermarking (text stamp)",
        "Logo / image watermarks (PNG)",
        "Round video notes", "GIFs & animations (→ MP4)",
        "Static stickers & image documents",
        "Forwarded media", "Album batch processing (up to 10)",
        "Auto mode — instant processing",
        "Animated watermark on photos (looping MP4/GIF)",
    ]),
    ("🎞 Motion — %d animations" % anim_count(), [
        "DVD bounce + 9 more bounce modes",
        "Marquees, slides & diagonal sweeps",
        "Orbits, figure-8, lissajous, pendulum",
        "Pulse, heartbeat, breathe, zoom loops",
        "Spin, wobble, tumble, metronome",
        "Blink, strobe, flicker, ghost, double flash",
        "Edge patrol & corner hops",
        "Teleports, shuffle, earthquake, matrix rain",
        "Pro combos (DVD+spin, orbit+pulse, cinematic…)",
        "Typewriter, glitch, karaoke, shimmer, color-cycle",
        "Animation speed control (0.25×–4×)",
        "Live in-chat demo for every animation",
    ]),
    ("[[palette]] Design control", [
        "Custom colors — hex, rgb(), 148 names",
        "Two-color gradient text",
        "17 style presets (neon, gold, sticker, glass…)",
        "9 bundled fonts incl. Devanagari (हिन्दी) & Arabic",
        "Size control + smart auto-fit",
        "Opacity, outline, drop shadow, neon glow",
        "Background box/pill (color, opacity, pad, radius)",
        "Rotation (−180°…180°)",
        "9-point position grid + margins",
        "Tiled anti-crop watermarks (angle + gap)",
        "Multi-line text & emoji",
        "Dynamic variables {date} {time} {user} {chat} {count}",
    ]),
    ("[[settings]] Workflow", [
        "Interactive settings panels",
        "Quick 2.6s preview renders",
        "Live progress bar + cancel button",
        "Unlimited named profiles",
        "Persistent per-user settings",
        "Color swatch confirmations",
        "Fair-use rate limiting",
        "Personal stats",
    ]),
    ("[[tools]] Media tools (15)", [
        "/stickerize /circle /resize /compress /convert",
        "/trim /tomp3 /speed /reverse /mute",
        "/ss /meta /gray /sepia /blurbg",
    ]),
    ("[[shield]] Engineering", [
        "Zero-install bundle — vendored deps + static ffmpeg",
        "Offline Pillow bootstrap for Python 3.8–3.14 (x86_64)",
        "Auto audio handling (copy → AAC fallback)",
        "Oversize auto-compression under Telegram's 50 MB cap",
        "Owner admin: /broadcast /users /ban /unban",
        "Rotating file logs + graceful shutdown",
        "python3 bot.py --check preflight",
    ]),
]


# standalone sign-off sent right after the welcome text — a single
# emoji, nothing else in the message (owner's request)
SIGNOFF_EMOJI = "😎"


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = H.user_id_of(update)
    db.ensure_user(uid, update.effective_user.first_name,
                   update.effective_user.username)
    # branded banner first (graceful fallback to text-only if missing)
    await H.branded_photo(update.message, config.BRAND_IMG,
                          config.WELCOME_CAPTION)
    await H.reply(update.message, WELCOME % anim_count(),
              parse_mode="HTML")
    # finally: the sign-off emoji as its own message
    try:
        await H.reply(update.message, SIGNOFF_EMOJI)
    except Exception:
        log.warning("could not send sign-off emoji", exc_info=True)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await H.branded_photo(update.message, config.HELP_IMG,
                          HELP % anim_count(), parse_mode="HTML")


async def cmd_features(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parts = ["⭐ <b>AquaMark feature tour</b>\n"]
    n = 0
    for title, items in FEATURES:
        parts.append("\n<b>%s</b>" % title)
        for it in items:
            parts.append("• %s" % it)
            n += 1
    parts.append("\n\n<b>Total: %d+ features</b> — and everything is "
                 "configurable per user." % n)
    await H.reply(update.message, "\n".join(parts), parse_mode="HTML")


async def cmd_about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await H.reply(update.message, 
        "🤖 <b>AquaMark</b> v%s\nProfessional watermark studio for "
        "Telegram.\n\n🎞 %d animations · 🎨 full design control · 🧰 media "
        "tools\n\nBuilt with python-telegram-bot + Pillow + ffmpeg. "
        "Self-contained: no server dependencies." %
        (config.VERSION, anim_count()), parse_mode="HTML")


async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    up = int(time.time() - _STARTED_AT)
    h, rem = divmod(up, 3600)
    m, s = divmod(rem, 60)
    up_str = ("%dh %02dm" % (h, m)) if h else ("%dm %02ds" % (m, s))
    g = db.global_stats()
    await H.reply(update.message, 
        "🏓 Pong!\n\n⏱ Uptime: %s\n🎬 Animations: %d\n👥 Users: %d\n💧 "
        "Renders: %d" % (up_str, anim_count(), g["users"], g["processed"]))


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = H.user_id_of(update)
    st = db.user_stats(uid)
    await H.reply(update.message, 
        "📊 <b>Your stats</b>\n\n💧 Media watermarked: <b>%d</b>" %
        st["processed"], parse_mode="HTML")


# ---------------------------------------------------------------- text / wm

async def cmd_wm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = H.user_id_of(update)
    s = H.settings_of(context, uid)
    text = " ".join(context.args or []).strip()
    if not text:
        H.set_await(context, "wm_text")
        await H.reply(update.message, 
            "✏️ Send me the watermark text — or /cancel\n\n💡 Multi-line is "
            "supported (send several lines), and variables like {date} "
            "{user} {count} work too.")
        return
    s["text"] = text[:200]
    s["wm_type"] = "text"
    s = H.save_settings(context, uid, s)
    await H.reply(update.message, 
        "✅ Watermark set to:\n<b>%s</b>\n\nSend me any photo or video!" %
        H.esc(s["text"]), parse_mode="HTML")


async def cmd_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await cmd_wm(update, context)


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Route plain text: awaiting-input states, onboarding, hints."""
    msg = update.message
    if msg is None or not msg.text:
        return
    uid = H.user_id_of(update)
    db.ensure_user(uid, update.effective_user.first_name,
                   update.effective_user.username)
    if db.is_banned(uid):
        return
    if msg.text.startswith("/"):
        return  # unknown command -> handled elsewhere

    if context.user_data.get("await"):
        handled = await settings_ui.handle_await(update, context)
        if handled:
            return

    state = context.user_data.get("await")
    if state:
        return

    s = H.settings_of(context, uid)
    if s.get("wm_type") == "text" and not s.get("text"):
        s["text"] = msg.text[:200]
        s = H.save_settings(context, uid, s)
        await H.reply(msg, 
            "✅ Watermark set to <b>%s</b>\n\nNow send me any photo or "
            "video — or fine-tune everything in /settings 🎨" %
            H.esc(s["text"]), parse_mode="HTML")
        return

    if context.user_data.get("await"):
        return
    await H.reply(msg, 
        "🫧 I watermark media! Send me a photo or video (forwarded is "
        "fine).\n\nChange my text with /wm, or explore /settings and "
        "/animation 🎞")


# ---------------------------------------------------------------- quick cmds

async def cmd_color(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from core import colors
    from core import renderer
    uid = H.user_id_of(update)
    s = H.settings_of(context, uid)
    raw = " ".join(context.args or []).strip()
    if not raw:
        await H.reply(update.message, 
            "🎨 Usage: /color #FF6600 · /color rgb(30,144,255) · /color "
            "gold — names, hex and rgb() all work. 148 named colors!")
        return
    try:
        if ">" in raw:
            c1, c2 = colors.parse_gradient(raw)
            s["color"] = colors.to_hex(c1)
            s["color2"] = colors.to_hex(c2)
            label = "Gradient %s → %s" % (s["color"], s["color2"])
            sw = renderer.swatch(c1, label)
        else:
            c = colors.parse_color(raw)
            s["color"] = colors.to_hex(c)
            s["color2"] = ""
            sw = renderer.swatch(c, s["color"])
    except colors.ColorError as exc:
        await H.reply(update.message, "❌ %s" % exc)
        return
    s = H.save_settings(context, uid, s)
    import io
    buf = io.BytesIO()
    sw.save(buf, format="PNG")
    buf.seek(0)
    from core import cemoji
    await cemoji.reply_photo(
        update.message, buf, "✅ Text color updated!", parse_mode="HTML")


async def cmd_gradient(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_color(update, context)


async def cmd_auto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = H.user_id_of(update)
    s = H.settings_of(context, uid)
    s["auto_mode"] = not s["auto_mode"]
    s = H.save_settings(context, uid, s)
    state_txt = "ON — I watermark media the moment you send it" \
        if s["auto_mode"] else "OFF — I'll ask before watermarking"
    await H.reply(update.message, 
        "🤖 Auto-process is now <b>%s</b>" % state_txt, parse_mode="HTML")


async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from core.settings import DEFAULTS
    uid = H.user_id_of(update)
    H.save_settings(context, uid, dict(DEFAULTS))
    await H.reply(update.message, 
        "♻️ Settings reset to defaults. Your profiles are safe.")


# ---------------------------------------------------------------- logo

async def cmd_setlogo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = H.user_id_of(update)
    msg = update.message
    src_msg = msg.reply_to_message or msg
    info = __import__("core.media", fromlist=["classify"]).classify(src_msg)
    if info is None or not info.is_image_like:
        await H.reply(msg, 
            "🖼 Reply to a PNG/image with /setlogo (or send the image with "
            "caption /setlogo). Transparent PNGs work best!")
        return
    status = await H.reply(msg, "⬇️ Saving logo…")
    import tempfile, shutil
    d = tempfile.mkdtemp(prefix="logo_", dir=config.TMP_DIR)
    try:
        from core import media as M
        src = await M.download(context, info, d)
        from PIL import Image
        im = Image.open(src)
        if im.mode not in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
        else:
            im = im.convert("RGBA")
        # clear old logos
        for ext in (".png", ".webp", ".jpg", ".jpeg"):
            p = os.path.join(config.LOGO_DIR, "%d%s" % (uid, ext))
            if os.path.isfile(p):
                os.remove(p)
        out = os.path.join(config.LOGO_DIR, "%d.png" % uid)
        im.thumbnail((1024, 1024), Image.LANCZOS)
        im.save(out, "PNG")
        s = H.settings_of(context, uid)
        s["wm_type"] = "logo"
        H.save_settings(context, uid, s)
        await H.edit_msg(status, 
            "✅ Logo saved and logo-mode enabled! Send any media to stamp "
            "it. (Size/opacity/position still apply — /settings)")
    finally:
        shutil.rmtree(d, ignore_errors=True)


async def cmd_clearlogo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = H.user_id_of(update)
    removed = False
    for ext in (".png", ".webp", ".jpg", ".jpeg"):
        p = os.path.join(config.LOGO_DIR, "%d%s" % (uid, ext))
        if os.path.isfile(p):
            os.remove(p)
            removed = True
    s = H.settings_of(context, uid)
    s["wm_type"] = "text"
    H.save_settings(context, uid, s)
    await H.reply(update.message, 
        "🗑 Logo removed — back to text watermarking." if removed else
        "You had no logo saved. Set one with /setlogo!")


async def cmd_logo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_setlogo(update, context)


def _u16_slice(text: str, offset: int, length: int) -> str:
    """Extract the entity span from text using UTF-16 offsets."""
    data = text.encode("utf-16-le")
    return data[offset * 2:(offset + length) * 2].decode("utf-16-le",
                                                         errors="replace")


async def cmd_emojiids(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/emojiids — list custom_emoji_ids from a (replied-to) message.

    Makes configuring CUSTOM_EMOJIS in core/cemoji.py trivial: send any
    custom emoji to the bot, reply to it with /emojiids, copy the IDs.
    """
    msg = update.effective_message
    target = msg.reply_to_message or msg
    ents = [e for e in (target.entities or target.caption_entities or [])
            if e.type == "custom_emoji"]
    if not ents:
        await H.reply(
            msg,
            "ℹ️ <b>Custom emoji ID lookup</b>\\n\\n"
            "Send me a message that contains custom emojis (or reply to "
            "one) and I'll list their IDs.\\n\\n"
            "How to create your own set:\\n"
            "1. In Telegram: <b>Settings → Stickers & Emoji → Create "
            "emoji pack</b> (needs Premium on the creating account)\\n"
            "2. Send the finished emojis to me here\\n"
            "3. Reply to that message with /emojiids\\n"
            "4. Paste the IDs into <code>CUSTOM_EMOJIS</code> in "
            "<code>core/cemoji.py</code>",
            parse_mode="HTML")
        return
    body = target.text or target.caption or ""
    lines = ["🎯 <b>Custom emoji IDs found:</b>\\n"]
    for i, e in enumerate(ents, 1):
        glyph = _u16_slice(body, e.offset, e.length)
        lines.append("%d. %s → <code>%s</code>"
                     % (i, H.esc(glyph), H.esc(e.custom_emoji_id or "")))
    lines.append("\\nPaste them into <code>CUSTOM_EMOJIS</code> in "
                 "<code>core/cemoji.py</code>, then restart the bot.")
    await H.reply(msg, "\\n".join(lines), parse_mode="HTML")


def register(app):
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("features", cmd_features))
    app.add_handler(CommandHandler("about", cmd_about))
    app.add_handler(CommandHandler("ping", cmd_ping))
    app.add_handler(CommandHandler("mystats", cmd_stats))
    app.add_handler(CommandHandler("emojiids", cmd_emojiids))
    app.add_handler(CommandHandler(["wm", "text"], cmd_wm))
    app.add_handler(CommandHandler("color", cmd_color))
    app.add_handler(CommandHandler("gradient", cmd_gradient))
    app.add_handler(CommandHandler("auto", cmd_auto))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CommandHandler("setlogo", cmd_setlogo))
    app.add_handler(CommandHandler("clearlogo", cmd_clearlogo))
    app.add_handler(CommandHandler("logo", cmd_logo))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, on_text))
