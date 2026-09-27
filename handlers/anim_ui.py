"""Animation catalog: browse 106 animations by category, search, live demos."""
import asyncio
import logging
import os
import tempfile

from telegram import Update
from telegram.ext import ContextTypes

import config
from core import animations as ANIM
from core import renderer as R
from core import video_engine
from handlers import common as H

log = logging.getLogger("aquamark.anim")

PAGE_SIZE = 8
_demo_lock = asyncio.Semaphore(1)


def menu_keyboard(s):
    cur = ANIM.get(s.get("animation", "static"))
    rows = []
    pair = []
    for cat_id, cat_name, cat_icon in ANIM.CATS:
        n = sum(1 for a in ANIM.REGISTRY.values() if a.cat == cat_id)
        pair.append(H.btn("%s %s (%d)" % (cat_icon, cat_name, n),
                          "an:cat:%s:0" % cat_id))
        if len(pair) == 2:
            rows.append(pair)
            pair = []
    if pair:
        rows.append(pair)
    rows.append([H.btn("🔎 Search by name", "an:search")])
    rows.append([H.btn("🚫 No animation (static)", "an:off"),
                 H.btn("◀️ Settings", "st:main")])
    text = ("🎞 <b>Animation catalog</b> — %d presets\n\n"
            "Current: <b>%s %s</b>\n\n"
            "Pick a category, or search. Tap ▶️ on any animation to see a "
            "live demo with your current watermark!" %
            (ANIM.count(), cur.icon, cur.name))
    return text, H.kb(rows)


def _anim_row(a, selected):
    mark = "● " if selected else ""
    return [H.btn("%s%s %s" % (mark, a.icon, a.name), "an:sel:%s" % a.id),
            H.btn("▶️", "an:demo:%s" % a.id)]


def category_page(cat_id, page, s):
    cat = None
    items = [a for a in ANIM.REGISTRY.values() if a.cat == cat_id]
    for c in ANIM.CATS:
        if c[0] == cat_id:
            cat = c
            break
    if cat is None or not items:
        return menu_keyboard(s)
    items.sort(key=lambda a: a.name)
    pages = (len(items) + PAGE_SIZE - 1) // PAGE_SIZE
    page = max(0, min(pages - 1, page))
    chunk = items[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    rows = [_anim_row(a, s.get("animation") == a.id) for a in chunk]
    nav = []
    if page > 0:
        nav.append(H.btn("⏮", "an:cat:%s:%d" % (cat_id, page - 1)))
    nav.append(H.btn("%d / %d" % (page + 1, pages), "an:nope"))
    if page < pages - 1:
        nav.append(H.btn("⏭", "an:cat:%s:%d" % (cat_id, page + 1)))
    rows.append(nav)
    rows.append([H.btn("🔙 Categories", "an:menu"),
                 H.btn("◀️ Settings", "st:main")])
    text = ("%s <b>%s</b> — page %d/%d\n\n"
            "● = currently selected · ▶️ = live demo" %
            (cat[2], cat[1], page + 1, pages))
    return text, H.kb(rows)


def selected_panel(a, s):
    text = ("%s <b>%s</b>\n\n"
            "Category: %s\n\n"
            "%s" % (a.icon, a.name,
                    dict((c[0], c[1]) for c in ANIM.CATS).get(a.cat, "?"),
                    _describe(a)))
    rows = [
        [H.btn("▶️ Live demo", "an:demo:%s" % a.id),
         H.btn("✅ Use this", "an:use:%s" % a.id)],
        [H.btn("🔙 Back", "an:cat:%s:0" % a.cat),
         H.btn("◀️ Settings", "st:main")],
    ]
    return text, H.kb(rows)


def _describe(a):
    notes = {
        "bounce": "The classic screensaver bounce. Ignores position — it "
                  "roams the whole frame.",
        "slide": "Continuous wrap-around travel across the frame.",
        "textfx": "Cinematic text reveal effects (rendered frame-by-frame).",
        "combo": "Professional multi-effect combinations.",
    }
    base = notes.get(a.cat, "")
    if a.once:
        base += "\n⏳ Plays once at the start, then stays put."
    return base or "Tap ▶️ to preview it with your watermark."


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data or ""
    uid = H.user_id_of(update)
    parts = data.split(":")
    s = H.settings_of(context, uid)

    if parts[1] == "menu":
        await H.answer_safely(query)
        text, markup = menu_keyboard(s)
        return await H.safe_edit(query, text, markup, parse_mode="HTML")

    if parts[1] == "nope":
        return await H.answer_safely(query)

    if parts[1] == "cat":
        await H.answer_safely(query)
        text, markup = category_page(parts[2], int(parts[3]), s)
        return await H.safe_edit(query, text, markup, parse_mode="HTML")

    if parts[1] == "sel":
        await H.answer_safely(query)
        a = ANIM.get(parts[2])
        text, markup = selected_panel(a, s)
        return await H.safe_edit(query, text, markup, parse_mode="HTML")

    if parts[1] == "use":
        await H.answer_safely(query, "Applied!")
        s["animation"] = parts[2]
        s = H.save_settings(context, uid, s)
        a = ANIM.get(parts[2])
        text, markup = selected_panel(a, s)
        extra = "\n\n✅ <b>Applied!</b> Send me a video to see it in action."
        return await H.safe_edit(query, text + extra, markup, parse_mode="HTML")

    if parts[1] == "off":
        await H.answer_safely(query, "Animation off")
        s["animation"] = "static"
        s = H.save_settings(context, uid, s)
        text, markup = menu_keyboard(s)
        return await H.safe_edit(query, text, markup, parse_mode="HTML")

    if parts[1] == "search":
        await H.answer_safely(query)
        H.set_await(context, "anim_search")
        await query.message.reply_text(
            "🔎 Send me a search term (e.g. <code>dvd</code>, "
            "<code>glitch</code>, <code>bounce</code>) — or /cancel",
            parse_mode="HTML")
        return

    if parts[1] == "demo":
        await H.answer_safely(query, "Rendering demo…")
        return await send_demo(update, context, parts[2])


async def send_search(update: Update, context: ContextTypes.DEFAULT_TYPE,
                      query_text):
    uid = H.user_id_of(update)
    s = H.settings_of(context, uid)
    results = ANIM.search(query_text)[:PAGE_SIZE * 2]
    if not results:
        await update.message.reply_text(
            "😐 Nothing matched “%s”. Try: bounce, slide, glitch, typewriter, "
            "orbit…" % H.esc(query_text))
        return True
    rows = [_anim_row(a, s.get("animation") == a.id) for a in results]
    rows.append([H.btn("🔙 All categories", "an:menu")])
    await update.message.reply_text(
        "🔎 Results for “%s” (%d):" % (H.esc(query_text), len(results)),
        reply_markup=H.kb(rows))
    return True


async def cmd_animation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = H.user_id_of(update)
    s = H.settings_of(context, uid)
    if context.args:
        return await send_search(update, context, " ".join(context.args))
    text, markup = menu_keyboard(s)
    await update.message.reply_text(text, reply_markup=markup,
                                    parse_mode="HTML")


# ---------------------------------------------------------------- demo

async def send_demo(update: Update, context: ContextTypes.DEFAULT_TYPE,
                    anim_id):
    """Render a 2.6s demo of an animation with the user's current look."""
    a = ANIM.get(anim_id)
    uid = H.user_id_of(update)
    query = update.callback_query
    status = None
    if _demo_lock.locked():
        if query is not None:
            await query.message.reply_text(
                "🎬 One demo at a time — try again in a few seconds.")
        return
    async with _demo_lock:
        s = dict(H.settings_of(context, uid))
        s["animation"] = a.id
        s["quality"] = "low"
        s["keep_audio"] = False
        s["tile"] = False
        s["text"] = s.get("text") or "AquaMark Demo"
        s["size_pct"] = max(10, s.get("size_pct", 8))
        outdir = tempfile.mkdtemp(prefix="demo_", dir=config.TMP_DIR)
        try:
            # gradient background clip
            src = os.path.join(outdir, "bg.mp4")
            from core.video_engine import ffmpeg
            import subprocess
            bgc = subprocess.run(
                [ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
                 "-f", "lavfi", "-i",
                 "gradients=size=426x240:rate=25:duration=%.2f" %
                 config.PREVIEW_SECONDS,
                 "-c:v", "libx264", "-preset", "ultrafast",
                 "-pix_fmt", "yuv420p", src],
                capture_output=True, text=True, timeout=60)
            if bgc.returncode != 0:  # gradients filter missing -> solid
                bgc = subprocess.run(
                    [ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
                     "-f", "lavfi", "-i",
                     "color=c=0x232a3d:size=426x240:rate=25:duration=%.2f" %
                     config.PREVIEW_SECONDS,
                     "-c:v", "libx264", "-preset", "ultrafast",
                     "-pix_fmt", "yuv420p", src],
                    capture_output=True, text=True, timeout=60)
            meta = {"duration": config.PREVIEW_SECONDS, "width": 426,
                    "height": 240, "has_audio": False}
            factory = R.SpriteFactory(s, 426, 240)
            seq_info = None
            if a.is_sequence:
                seq_info = R.render_sequence(
                    factory, a, os.path.join(outdir, "seq"))
                sprite_path = None
            else:
                sprite_path = os.path.join(outdir, "wm.png")
                factory.sprite.save(sprite_path)
            out = await video_engine.watermark_video(
                src, os.path.join(outdir, "demo"), sprite_path, s, meta,
                seq_info=seq_info)
            with open(out, "rb") as fh:
                await (query.message if query else update.message).reply_animation(
                    animation=fh,
                    caption="%s <b>%s</b> — send me a video to apply it!\n"
                            "✅ Use this: tap below" % (a.icon, a.name),
                    parse_mode="HTML",
                    reply_markup=H.kb([[H.btn("✅ Use this animation",
                                              "an:use:%s" % a.id)],
                                       [H.btn("🔙 Back",
                                              "an:cat:%s:0" % a.cat)]]),
                    write_timeout=120)
        except Exception:
            log.exception("demo render failed")
            await (query.message if query else update.message).reply_text(
                "😵 Demo failed to render — please try another animation.")
        finally:
            import shutil
            shutil.rmtree(outdir, ignore_errors=True)


def register(app):
    from telegram.ext import CommandHandler, CallbackQueryHandler
    app.add_handler(CommandHandler("animation", cmd_animation))
    app.add_handler(CallbackQueryHandler(on_callback, pattern=r"^an:"))
