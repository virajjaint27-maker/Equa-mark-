#!/usr/bin/env python3
"""AquaMark — professional Telegram watermark studio.

Usage:
    python3 bot.py              run the bot (BOT_TOKEN in .env or environment)
    python3 bot.py --check      preflight: verify the environment
    python3 bot.py --version    print version info
"""
import os
import sys


def _version():
    import config
    return "AquaMark %s" % config.VERSION


def _preflight():
    """Zero-side-effect environment check with a friendly report."""
    checks = []

    def ok(label, detail=""):
        checks.append((True, label, detail))

    def bad(label, detail=""):
        checks.append((False, label, detail))

    v = sys.version_info
    if v >= (3, 8):
        ok("Python %d.%d.%d" % (v.major, v.minor, v.micro),
           "3.8+ required")
    else:
        bad("Python %d.%d.%d" % (v.major, v.minor, v.micro),
            "3.8+ required")

    try:
        import bootstrap
        bootstrap.setup()
        ok("Vendored packages", "telegram library ready")
    except SystemExit as exc:
        bad("Vendored packages", str(exc)[:80])
        _report(checks)
        return 1
    except Exception as exc:
        bad("Vendored packages", repr(exc)[:80])
        _report(checks)
        return 1

    try:
        import telegram
        ok("python-telegram-bot", telegram.__version__)
    except Exception as exc:
        bad("python-telegram-bot", repr(exc)[:80])

    try:
        from PIL import Image, ImageFont
        import PIL
        ok("Pillow", PIL.__version__)
    except Exception as exc:
        bad("Pillow", repr(exc)[:80])

    try:
        import pypdf
        import fpdf
        ok("PDF engine", "pypdf %s + fpdf2 %s"
           % (pypdf.__version__, fpdf.__version__))
    except Exception as exc:
        bad("PDF engine", repr(exc)[:80])

    try:
        import config as _config
        from core import cemoji
        if not getattr(_config, "USE_CUSTOM_EMOJIS", False):
            ok("Custom emojis", "off (USE_CUSTOM_EMOJIS=0)")
        elif not cemoji.ids_configured():
            ok("Custom emojis",
               "enabled, IDs not set yet (paste into core/cemoji.py)")
        else:
            ok("Custom emojis", "%d ids configured"
               % sum(1 for e in cemoji.CUSTOM_EMOJIS.values()
                     if e["id"] not in ("", cemoji.PLACEHOLDER)))
    except Exception as exc:
        bad("Custom emojis", repr(exc)[:80])

    try:
        import bootstrap
        ff = bootstrap.ffmpeg_path()
        import subprocess
        out = subprocess.run([ff, "-version"], capture_output=True,
                             text=True, timeout=20).stdout.splitlines()
        ok("ffmpeg", out[0].split("version")[1].strip()[:40] if
           "version" in out[0] else "ready")
    except SystemExit as exc:
        bad("ffmpeg", str(exc).splitlines()[0][:80])
    except Exception as exc:
        bad("ffmpeg", repr(exc)[:80])

    try:
        from core import fonts as F
        from PIL import ImageFont
        n = 0
        for fid, entry in F.FONTS.items():
            p = F.font_path(fid)
            if p and os.path.isfile(p):
                ImageFont.truetype(p, 20)
                n += 1
        if n == len(F.FONTS):
            ok("Fonts", "%d bundled fonts" % n)
        else:
            bad("Fonts", "only %d/%d load" % (n, len(F.FONTS)))
    except Exception as exc:
        bad("Fonts", repr(exc)[:80])

    try:
        from core.animations import count
        n = count()
        if n >= 100:
            ok("Animations", "%d presets" % n)
        else:
            bad("Animations", "only %d registered" % n)
    except Exception as exc:
        bad("Animations", repr(exc)[:80])

    import config
    if config.BOT_TOKEN:
        ok("BOT_TOKEN", "configured")
    else:
        bad("BOT_TOKEN", "missing — put it in .env or export BOT_TOKEN")

    for d in (config.DATA_DIR, config.TMP_DIR, config.LOG_DIR):
        try:
            probe = os.path.join(d, ".write_test")
            with open(probe, "w") as fh:
                fh.write("x")
            os.remove(probe)
        except Exception as exc:
            bad("Writable dir %s" % d, repr(exc)[:60])
    ok("Data dirs", "writable")

    return _report(checks)


def _report(checks):
    print("\nAquaMark preflight check")
    print("=" * 52)
    fails = 0
    for good, label, detail in checks:
        mark = "✓" if good else "✗"
        print(" %s  %-22s %s" % (mark, label, detail))
        if not good:
            fails += 1
    print("=" * 52)
    if fails:
        print(" %d problem(s) found — fix them, then run: python3 bot.py"
              % fails)
        return 1
    print(" All good — run: python3 bot.py")
    return 0


# --- network timeouts ---------------------------------------------------
# Telegram holds long-polls open BY DESIGN (no updates = the server waits
# out the whole window). If the read timeout sits at or below the poll
# window, every quiet poll aborts with TimedOut + a full traceback in the
# log — the classic scary-but-harmless error. The get_updates request is a
# SEPARATE HTTP client in python-telegram-bot and must be configured on
# its own; the regular request timeouts alone are NOT enough.
POLL_TIMEOUT = 15  # seconds each long-poll stays open

NET_TIMEOUTS = {
    # regular API calls (sending messages, media, edits)
    "connect_timeout": 30,
    "read_timeout": 60,
    "write_timeout": 240,
    "pool_timeout": 30,
    "media_write_timeout": 300,          # ~50 MB uploads on slow uplinks
    # the long-poll get_updates request
    "get_updates_connect_timeout": 30,
    "get_updates_read_timeout": POLL_TIMEOUT + 45,   # poll + wide slack
    "get_updates_write_timeout": 15,
    "get_updates_pool_timeout": 30,
}


def _apply_net_timeouts(builder):
    """Apply NET_TIMEOUTS to an ApplicationBuilder (each method returns
    the builder, so a simple chain-in-a-loop works)."""
    for name, value in NET_TIMEOUTS.items():
        builder = getattr(builder, name)(value)
    return builder


def main():
    if "--version" in sys.argv:
        print(_version())
        return 0
    if "--check" in sys.argv:
        return _preflight()

    import bootstrap
    bootstrap.setup()

    import config
    config.setup_logging()
    import logging
    log = logging.getLogger("aquamark")

    if not config.BOT_TOKEN:
        print("=" * 60)
        print("ERROR: BOT_TOKEN is not set.")
        print("")
        print("Create a file named .env next to bot.py containing:")
        print("    BOT_TOKEN=123456789:AA_your_token_from_BotFather")
        print("")
        print("Get a token from @BotFather in Telegram (/newbot).")
        print("You can also export BOT_TOKEN as an environment variable.")
        print("=" * 60)
        return 1

    import db
    db.init_db()
    db.cleanup_tmp()

    from telegram import BotCommand, Update
    from telegram.constants import ParseMode
    from telegram.error import TelegramError
    from telegram.ext import (ApplicationBuilder, CallbackQueryHandler,
                              CommandHandler, ContextTypes, MessageHandler,
                              filters)

    from handlers import admin, anim_ui, pipeline, profiles, start, \
        settings_ui, tools

    builder = _apply_net_timeouts(
        ApplicationBuilder().token(config.BOT_TOKEN))
    if config.BOT_API_BASE:  # optional local Bot API server (LARGE-FILES.md)
        base = config.BOT_API_BASE
        builder = (builder
                   .base_url(base + "/bot")
                   .base_file_url((config.BOT_API_FILE_BASE or base)
                                  + "/file/bot"))
        log.info("Using local Bot API server: %s "
                 "(file caps: in %d MB / out %d MB)",
                 base, config.MAX_IN_SIZE // 1048576,
                 config.MAX_OUT_SIZE // 1048576)
    app = (builder
           .post_init(_post_init)
           .build())

    # register everything
    start.register(app)
    settings_ui.register(app)
    anim_ui.register(app)
    profiles.register(app)
    tools.register(app)
    admin.register(app)
    pipeline.register(app)

    async def _error_handler(update: object,
                             context: ContextTypes.DEFAULT_TYPE):
        from telegram.error import NetworkError
        if isinstance(context.error, NetworkError):
            # TimedOut / connection reset etc. — the updater retries
            # polling on its own; one calm line is all this needs
            log.warning("transient network error (auto-retried): %s",
                        context.error)
            return
        log.error("unhandled exception", exc_info=context.error)
        try:
            if isinstance(update, Update) and update.effective_message:
                await update.effective_message.reply_text(
                    "😵 Something unexpected happened — the error is logged "
                    "with ID <code>%s</code>. Please try again." %
                    str(abs(id(context.error)) % 100000),
                    parse_mode=ParseMode.HTML)
        except TelegramError:
            pass

    app.add_error_handler(_error_handler)

    log.info("AquaMark %s starting (animations=%d)",
             config.VERSION, __import__("core.animations",
                                        fromlist=["count"]).count())
    app.run_polling(drop_pending_updates=True, timeout=POLL_TIMEOUT,
                    allowed_updates=["message", "callback_query"])
    return 0


COMMANDS = [
    ("start", "Start & quick tips"),
    ("help", "Full guide"),
    ("wm", "Set watermark text"),
    ("settings", "Control panel"),
    ("animation", "106 animations"),
    ("color", "Set text color"),
    ("gradient", "Gradient text"),
    ("style", "Style presets"),
    ("font", "Choose font"),
    ("size", "Watermark size"),
    ("opacity", "Opacity"),
    ("position", "Position"),
    ("rotation", "Rotation"),
    ("speed", "Animation speed"),
    ("profiles", "Saved looks"),
    ("setlogo", "Use a logo watermark"),
    ("clearlogo", "Remove logo"),
    ("auto", "Instant processing on/off"),
    ("features", "Feature tour"),
    ("about", "About this bot"),
    ("ping", "Status & uptime"),
    ("mystats", "Your stats"),
    ("reset", "Reset settings"),
    ("stickerize", "Photo → sticker"),
    ("circle", "Circle crop"),
    ("resize", "Resize photo"),
    ("compress", "Compress media"),
    ("convert", "Convert format"),
    ("trim", "Trim video"),
    ("tomp3", "Video → MP3"),
    ("reverse", "Reverse video"),
    ("mute", "Mute video"),
    ("ss", "Frame screenshot"),
    ("meta", "Media info"),
    ("gray", "Grayscale"),
    ("sepia", "Sepia tone"),
    ("blurbg", "9:16 story canvas"),
    ("broadcast", "Owner: broadcast"),
    ("users", "Owner: user list"),
    ("ban", "Owner: ban"),
    ("unban", "Owner: unban"),
]


async def _post_init(app):
    from telegram import BotCommand
    import logging
    try:
        cmds = [BotCommand(c, d) for c, d in COMMANDS if d != "placeholder"]
        await app.bot.set_my_commands(cmds)
    except Exception:
        logging.getLogger("aquamark").warning("could not set command menu",
                                              exc_info=True)
    me = await app.bot.get_me()
    logging.getLogger("aquamark").info("Bot @%s is live!", me.username)


if __name__ == "__main__":
    sys.exit(main())
