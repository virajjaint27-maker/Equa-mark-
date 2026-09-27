"""Media intake -> watermark -> deliver. Auto mode, albums, previews, cancel."""
import asyncio
import logging
import os
import shutil
import tempfile

from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

import config
import db
from core import animations as ANIM
from core import media as M
from core import pdf_engine
from core import renderer as R
from core import textvars
from core import video_engine
from core.video_engine import FFmpegError, JobCancelled
from handlers import common as H
from handlers import tools as TOOLS

log = logging.getLogger("aquamark.pipeline")

_group_state = {}            # media_group_id -> {chat, items, task}
_job_semaphore = asyncio.Semaphore(2)
_user_busy = set()


def register(app):
    media_filter = (filters.PHOTO | filters.VIDEO | filters.ANIMATION |
                    filters.VIDEO_NOTE | filters.Document.ALL |
                    filters.Sticker.ALL)
    app.add_handler(MessageHandler(media_filter, on_media), group=10)
    from telegram.ext import CallbackQueryHandler
    app.add_handler(CallbackQueryHandler(on_action, pattern=r"^act:"))
    app.add_handler(CallbackQueryHandler(on_cancel, pattern=r"^cnl:"))


# ---------------------------------------------------------------- intake

async def on_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if msg is None:
        return
    uid = H.user_id_of(update)
    db.ensure_user(uid, update.effective_user.first_name,
                   update.effective_user.username)
    if db.is_banned(uid):
        return

    # media captioned with a command routes to the tools module
    caption = (msg.caption or "").strip()
    if caption.startswith("/"):
        return await TOOLS.dispatch_caption_tool(update, context)

    info = M.classify(msg)
    if info is None:
        return
    if info.kind == M.KIND_UNSUPPORTED:
        await H.reply(msg, M.UNSUPPORTED_TEXT)
        return
    if info.kind == M.KIND_AUDIO:
        await H.reply(
            msg,
            "🎵 Audio has no pixels to watermark — but you can use "
            "/tomp3 (reply it to a video) or /meta to inspect a file.")
        return

    # albums: collect with a debounce, then batch
    if msg.media_group_id:
        key = msg.media_group_id
        state = _group_state.setdefault(
            key, {"chat": msg.chat_id, "items": []})
        state["items"].append(info)
        task = state.get("task")
        if task:
            task.cancel()
        loop = asyncio.get_event_loop()
        state["task"] = loop.call_later(
            1.6, lambda: asyncio.ensure_future(_flush_group(key, context)))
        return

    s = H.settings_of(context, uid)
    if s.get("auto_mode"):
        await run_job(update, context, [info], preview=False)
    else:
        await _offer_actions(update, context, [info])


async def _flush_group(key, context):
    state = _group_state.pop(key, None)
    if not state or not state["items"]:
        return
    items = state["items"][:config.MAX_BATCH]
    first = items[0].message
    if first is None:
        return
    fake = _FakeUpdate(first)
    uid = first.from_user.id if first.from_user else 0
    s = H.settings_of(context, uid)
    if len(state["items"]) > config.MAX_BATCH:
        await H.reply(
            first,
            "📦 Albums are capped at %d items — processing the first %d."
            % (config.MAX_BATCH, config.MAX_BATCH))
    if s.get("auto_mode"):
        await run_job(fake, context, items, preview=False)
    else:
        await _offer_actions(fake, context, items)


class _FakeUpdate(object):
    """Duck-typed Update so shared code paths can use effective_message."""

    def __init__(self, message):
        self.effective_message = message
        self.effective_user = message.from_user
        self.effective_chat = message.chat
        self.callback_query = None


def _look_summary(s):
    a = ANIM.get(s["animation"])
    return " • ".join([s["text"][:30] if s["text"] else "(no text)",
                       s["color"], "%s %s" % (a.icon, a.name)])


async def _offer_actions(update, context, infos):
    n = len(infos)
    s = H.settings_of(context, H.user_id_of(update))
    plural = "this media" if n == 1 else "this album (%d items)" % n
    rows = [[H.btn("Watermark it!", "act:wm", ce="water")]]
    if infos[0].is_video_like:
        rows[0].append(H.btn("Quick preview", "act:prev", ce="eyes"))
    rows.append([H.btn("Settings", "st:main", ce="settings"),
                 H.btn("Animation", "an:menu", ce="anim")])
    await H.reply(update.effective_message,
                  "🫧 Got %s!\n\nCurrent look: <b>%s</b>\n\nWhat should "
                  "I do?" % (plural, H.esc(_look_summary(s))),
                  reply_markup=H.kb(rows), parse_mode="HTML")


async def on_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await H.answer_safely(query)
    action = (query.data or "").split(":")[1]
    msg = query.message
    src = msg.reply_to_message if msg.reply_to_message else None
    if src is None:
        return await H.safe_edit(
            query, "🤔 I couldn't find the media for this button — please "
                   "send it again.")
    info = M.classify(src)
    if info is None or info.kind in (M.KIND_UNSUPPORTED, M.KIND_AUDIO):
        return await H.safe_edit(query, M.UNSUPPORTED_TEXT)
    try:
        await query.message.delete()
    except Exception:
        pass
    if action == "wm":
        await run_job(update, context, [info], preview=False)
    elif action == "prev":
        await run_job(update, context, [info], preview=True)


async def on_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await H.answer_safely(query, "Stopping…")
    context.user_data.get("cancel_event", asyncio.Event()).set()


def prepare_sprite(factory, anim, s, W, H, job_dir, duration=None):
    """Build the sprite/sequence inputs for a video render.

    Returns (sprite_path_or_None, seq_info_or_None). seq_info with dir=None
    means "single PNG with anchor compensation" (rotation padding).
    """
    if anim.is_sequence and not s.get("tile"):
        min_frames = None
        if s.get("out_format") == "gif" and duration:
            # GIF frame sources are not ffmpeg-looped (memory bug workaround)
            min_frames = int(round(duration * 12)) + 2
        return None, R.render_sequence(
            factory, anim, os.path.join(job_dir, "seq"),
            min_frames=min_frames)
    sprite_path = os.path.join(job_dir, "wm.png")
    if s.get("tile"):
        canvas, _, _ = R.build_tile_canvas(factory.sprite, s, W, H)
        canvas.save(sprite_path)
        return sprite_path, None
    if anim.pre and "rotate" in anim.pre:
        padded, px, py = R.pad_diagonal(factory.sprite)
        padded.save(sprite_path)
        return sprite_path, {
            "dir": None, "fps": 25, "w": padded.width, "h": padded.height,
            "pad_x": px, "pad_y": py,
            "inner_w": factory.sprite.width,
            "inner_h": factory.sprite.height}
    factory.sprite.save(sprite_path)
    return sprite_path, None


# ---------------------------------------------------------------- jobs

async def run_job(update, context, media_items, preview=False):
    first_msg = update.effective_message
    uid = H.user_id_of(update)
    user = update.effective_user
    chat = update.effective_chat

    if uid in _user_busy:
        await first_H.reply(msg, H.busy_note())
        return
    _user_busy.add(uid)
    cancel_event = asyncio.Event()
    context.user_data["cancel_event"] = cancel_event
    try:
        if not db.rate_allow(uid):
            await H.reply(
                first_msg,
                "🚦 Easy there! You've hit the hourly limit of %d renders — "
                "try again a little later." % config.RATE_JOBS_PER_HOUR)
            return
        s = H.settings_of(context, uid)
        if s.get("wm_type") == "text" and not s.get("text"):
            await H.reply(
                first_msg,
                "✏️ First tell me what the watermark should say — send your "
                "text (e.g. <code>@yourbrand</code>) or use "
                "<code>/wm your text</code>.", parse_mode="HTML")
            return
        if s.get("wm_type") == "logo" and not _logo_path(uid):
            await H.reply(
                first_msg,
                "🖼 Logo mode is on but there's no logo yet. Send /setlogo "
                "with a PNG, or switch to text in /settings.")
            return

        async with _job_semaphore:
            for idx, info in enumerate(media_items):
                await _process_one(update, context, info, s, uid, user,
                                   chat, preview, idx, len(media_items),
                                   cancel_event)
    except JobCancelled:
        _st = context.user_data.pop("job_status", None)
        if _st:
            try:
                await _st.delete()
            except Exception:
                pass
        await H.reply(first_msg, "[[stop]] Render cancelled.")
    except M.TooLarge as exc:
        await H.reply(first_msg, "📦 %s" % exc)
    except FFmpegError as exc:
        log.error("ffmpeg error: %s", exc)
        await H.reply(first_msg,
            "[[sad]] The renderer hit an error — it's been logged. Please try "
            "again, maybe with different settings (/settings).\n"
            "<code>%s</code>" % H.esc(str(exc)[-200:]), parse_mode="HTML")
    except Exception:
        log.exception("job failed")
        await H.reply(first_msg,
                      "[[sad]] Something went wrong on my side. The error "
                      "is logged — please try again.")
    finally:
        _user_busy.discard(uid)
        context.user_data.pop("cancel_event", None)
        context.user_data.pop("job_status", None)


def _logo_path(uid):
    for ext in (".png", ".webp", ".jpg", ".jpeg"):
        p = os.path.join(config.LOGO_DIR, "%d%s" % (uid, ext))
        if os.path.isfile(p):
            return p
    return None


async def _process_one(update, context, info, s, uid, user, chat, preview,
                       index, total, cancel_event):
    msg = update.effective_message
    job_dir = tempfile.mkdtemp(prefix="job_", dir=config.TMP_DIR)
    status = None
    try:
        label = "Preview" if preview else "Watermarking"
        if total > 1:
            label += " (%d/%d)" % (index + 1, total)
        cancel_kb = H.kb([[H.btn("Cancel", "cnl", ce="stop")]])
        status = await H.branded_photo(
            msg, config.PROCESS_IMG, "[[clock]] %s…" % label,
            reply_markup=cancel_kb)
        context.user_data["job_status"] = status

        async def note(text):
            try:
                await H.edit_msg(status, text, reply_markup=cancel_kb)
            except Exception:
                pass

        await note("[[download]] %s — downloading…" % label)
        src = await M.download(context, info, job_dir)

        await note("[[search]] %s — analyzing…" % label)
        meta = dict(info.tg or {})
        if info.is_video_like:
            probed = video_engine.probe(src)
            meta["duration"] = meta.get("duration") or probed["duration"]
            meta["width"] = meta.get("width") or probed["width"]
            meta["height"] = meta.get("height") or probed["height"]
            meta["has_audio"] = probed["has_audio"]
            if not (meta.get("duration") and meta.get("width")):
                raise FFmpegError("couldn't read video properties")
        elif info.kind == M.KIND_IMAGE_DOC:
            from PIL import Image
            with Image.open(src) as im:
                meta["width"], meta["height"] = im.size
        else:
            meta.setdefault("width", 0)
            meta.setdefault("height", 0)

        if preview and info.is_video_like:
            src = await _make_preview_clip(src, job_dir)
            meta["duration"] = min(config.PREVIEW_SECONDS,
                                   meta.get("duration") or
                                   config.PREVIEW_SECONDS)

        s_job = dict(s)
        if preview:
            s_job["quality"] = "low"
            s_job["keep_audio"] = False
            s_job["tile"] = False
        if s_job.get("template_vars"):
            s_job["text"] = textvars.resolve(
                s_job.get("text", ""), user=user, chat=chat,
                count=db.user_stats(uid)["processed"] + 1)

        await note("[[brush]] %s — drawing watermark…" % label)
        anim = ANIM.get(s_job.get("animation", "static"))
        logo = _logo_path(uid) if s_job.get("wm_type") == "logo" else None
        factory = R.SpriteFactory(s_job, meta.get("width") or 1280,
                                  meta.get("height") or 720, logo_path=logo)

        if info.kind == M.KIND_PDF:
            await note("[[pdf]] %s — stamping pages…" % label)
            logo = _logo_path(uid) if s_job.get("wm_type") == "logo" else None
            out = await asyncio.to_thread(
                pdf_engine.watermark_pdf, src,
                os.path.join(job_dir, "out.pdf"), s_job, logo)
            kind_for_send = "pdf"
        elif info.is_video_like:
            sprite_path, seq_info = prepare_sprite(
                factory, anim, s_job, meta["width"], meta["height"], job_dir,
                duration=meta.get("duration"))
            await note("[[film]] %s — rendering… %s" % (label, H.bar(0)))
            out = await video_engine.watermark_video(
                src, os.path.join(job_dir, "out"), sprite_path, s_job, meta,
                seq_info=seq_info,
                progress_cb=lambda f, L=label: note(
                    "[[film]] %s — rendering… %s" % (L, H.bar(f))),
                cancel_event=cancel_event)
            kind_for_send = "video"
        else:
            animated = (anim.id != "static" or
                        s_job.get("out_format") == "gif")
            if animated and not s_job.get("tile"):
                await note("[[film]] %s — rendering loop… %s" % (label, H.bar(0)))
                sprite_path, seq_info = prepare_sprite(
                    factory, anim, s_job, meta.get("width") or 1280,
                    meta.get("height") or 720, job_dir,
                    duration=s_job.get("loop_secs", 4))
                out = await video_engine.render_photo_loop(
                    src, os.path.join(job_dir, "out"), sprite_path, s_job,
                    seq_info=seq_info,
                    progress_cb=lambda f: note(
                        "[[film]] %s — rendering… %s" % (label, H.bar(f))),
                    cancel_event=cancel_event)
                kind_for_send = "video"
            else:
                out = R.composite_photo(src, factory.sprite, s_job,
                                        os.path.join(job_dir, "out"))
                kind_for_send = "photo"

        try:
            await status.delete()
        except Exception:
            pass
        context.user_data.pop("job_status", None)

        out_meta = video_engine.probe(out) if kind_for_send == "video" else {}
        caption = _result_caption(s_job, anim, preview)
        await M.send_watermarked(msg, out, kind_for_send, out_meta, s_job,
                                 caption=caption)
        db.bump_processed(uid)
    finally:
        if status is not None:
            try:
                await status.delete()
            except Exception:
                pass
        shutil.rmtree(job_dir, ignore_errors=True)


async def _make_preview_clip(src, job_dir):
    out = os.path.join(job_dir, "preview_src.mp4")
    args = ["-i", src, "-t", "%.2f" % config.PREVIEW_SECONDS, "-an",
            "-vf", "scale='min(480,iw)':-2", "-c:v", "libx264",
            "-preset", "ultrafast", "-crf", "30", "-pix_fmt", "yuv420p",
            "-map_metadata", "-1", out]
    await video_engine.tool_render(args, duration=config.PREVIEW_SECONDS,
                                   timeout=120)
    return out


def _result_caption(s, anim, preview):
    if preview:
        return "[[eyes]] Preview render — tweak /settings then send the media " \
               "again for the full-quality version."
    a_txt = "" if anim.id == "static" else " · %s %s" % (anim.icon, anim.name)
    first = "[[water]] %s%s" % (s["text"][:60] if s.get("text") else "Logo", a_txt)
    if s.get("tile"):
        first += " · 🧩 tiled"
    return first
