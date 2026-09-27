"""Media utility tools: stickerize, circle, trim, speed, tomp3, meta, ..."""
import io
import logging
import os
import re
import shutil
import tempfile

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

import config
from core import media as M
from core import video_engine
from core.video_engine import FFmpegError, ffmpeg
from handlers import common as H

log = logging.getLogger("aquamark.tools")

NEEDS_MEDIA = "🧰 Send this command while replying to a photo/video, or send " \
              "media with the command as caption (e.g. photo + “/circle”)."
BAD_ARGS = "❌ Usage: %s"


def register(app):
    for name in ("stickerize", "circle", "resize", "compress", "convert",
                 "trim", "tomp3", "speed", "reverse", "mute", "ss", "meta",
                 "gray", "sepia", "blurbg"):
        app.add_handler(CommandHandler(name, _make_entry(name)))


def _make_entry(name):
    async def _cmd(update, context):
        await run_tool(update, context, name, list(context.args or []))
    _cmd.__name__ = "cmd_%s" % name
    return _cmd


async def dispatch_caption_tool(update, context):
    msg = update.effective_message
    caption = (msg.caption or "").strip()
    parts = caption.split(None, 1)
    if not parts:
        return
    name = parts[0].lstrip("/").split("@")[0].lower()
    args = parts[1].split() if len(parts) > 1 else []
    if name in ("stickerize", "circle", "resize", "compress", "convert",
                "trim", "tomp3", "speed", "reverse", "mute", "ss", "meta",
                "gray", "sepia", "blurbg"):
        await run_tool(update, context, name, args, media_msg=msg)


# ---------------------------------------------------------------- plumbing

async def run_tool(update, context, name, args, media_msg=None):
    msg = update.effective_message
    uid = H.user_id_of(update)
    db_user = __import__("db")
    db_user.ensure_user(uid, update.effective_user.first_name,
                        update.effective_user.username)
    if db_user.is_banned(uid):
        return

    src_msg = media_msg or msg.reply_to_message
    info = M.classify(src_msg) if src_msg is not None else None
    if info is None or info.kind in (M.KIND_UNSUPPORTED, M.KIND_AUDIO) or \
            not (info.is_image_like or info.is_video_like):
        await H.reply(msg, NEEDS_MEDIA)
        return

    status = await H.reply(msg, "🧰 Working…")
    job_dir = tempfile.mkdtemp(prefix="tool_", dir=config.TMP_DIR)
    try:
        src = await M.download(context, info, job_dir)
        handler = _TOOLS[name]
        out = await handler(update, context, info, src, args, job_dir)
        try:
            await status.delete()
        except Exception:
            pass
        if out is None:
            return
        await _send_result(msg, out)
    except M.TooLarge as exc:
        await H.reply(msg, "📦 %s" % exc)
    except FFmpegError as exc:
        await H.reply(msg, "😵 Tool failed: <code>%s</code>" %
                             H.esc(str(exc)[-200:]), parse_mode="HTML")
    except _UsageError as exc:
        await H.reply(msg, "❌ %s" % exc)
    except Exception:
        log.exception("tool %s failed", name)
        await H.reply(msg, "😵 The tool hit an error — it's been logged.")
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)


class _UsageError(Exception):
    pass


async def _send_result(msg, out):
    size = os.path.getsize(out)
    with open(out, "rb") as fh:
        if out.endswith((".jpg", ".jpeg", ".png")) and size < 9 * 1024 * 1024:
            await msg.reply_photo(photo=fh, write_timeout=120)
        elif out.endswith(".mp3"):
            await msg.reply_audio(audio=fh, write_timeout=120,
                                  filename=os.path.basename(out))
        elif out.endswith(".webp"):
            await msg.reply_document(document=fh, write_timeout=120,
                                     filename=os.path.basename(out))
        elif out.endswith(".gif"):
            await msg.reply_animation(animation=fh, write_timeout=120)
        else:
            kw = {"write_timeout": 180, "supports_streaming": True}
            meta = video_engine.probe(out)
            if meta.get("width"):
                kw["width"] = meta["width"]
                kw["height"] = meta["height"]
            if meta.get("duration"):
                kw["duration"] = int(meta["duration"])
            await msg.reply_video(video=fh, **kw)


def _pil():
    from PIL import Image, ImageDraw, ImageFilter, ImageOps
    return Image, ImageDraw, ImageFilter, ImageOps


# ---------------------------------------------------------------- tools

async def t_stickerize(update, context, info, src, args, job_dir):
    Image, ImageDraw, ImageFilter, ImageOps = _pil()
    im = Image.open(src).convert("RGBA")
    im.thumbnail((512, 512), Image.LANCZOS)
    alpha = im.getchannel("A")
    border = max(4, int(max(im.size) * 0.045))
    if border % 2 == 0:
        border += 1
    silhouette = alpha.filter(ImageFilter.MaxFilter(border))
    white = Image.new("RGBA", im.size, (255, 255, 255, 255))
    white.putalpha(silhouette)
    out_im = Image.alpha_composite(white, im)
    out = os.path.join(job_dir, "sticker.webp")
    out_im.save(out, "WEBP")
    return out


async def t_circle(update, context, info, src, args, job_dir):
    Image, ImageDraw, _, _ = _pil()
    im = Image.open(src).convert("RGBA")
    side = min(im.size)
    left = (im.width - side) // 2
    top = (im.height - side) // 2
    im = im.crop((left, top, left + side, top + side))
    mask = Image.new("L", (side, side), 0)
    d = ImageDraw.Draw(mask)
    d.ellipse([0, 0, side - 1, side - 1], fill=255)
    im.putalpha(mask)
    out = os.path.join(job_dir, "circle.png")
    im.save(out, "PNG")
    return out


async def t_resize(update, context, info, src, args, job_dir):
    Image, _, _, _ = _pil()
    m = re.match(r"^(\d{1,5})(?:[xX](\d{1,5}))?$", args[0]) if args else None
    if not m:
        raise _UsageError("/resize <WxH> — e.g. /resize 1080x1080 or "
                          "/resize 800 (keeps ratio)")
    im = Image.open(src)
    w = int(m.group(1))
    h = int(m.group(2)) if m.group(2) else None
    if h:
        if w > 4000 or h > 4000:
            raise _UsageError("Max dimension is 4000px.")
        im = im.resize((w, h), Image.LANCZOS)
    else:
        if w > 4000:
            raise _UsageError("Max dimension is 4000px.")
        im.thumbnail((w, w), Image.LANCZOS)
    out = os.path.join(job_dir, "resized.png")
    im.save(out, "PNG")
    return out


async def t_compress(update, context, info, src, args, job_dir):
    q = 70
    if args:
        try:
            q = max(10, min(95, int(args[0])))
        except ValueError:
            raise _UsageError("/compress [10-95] — quality, default 70")
    if info.is_video_like:
        out = os.path.join(job_dir, "compressed.mp4")
        await video_engine.tool_render(
            ["-i", src, "-c:v", "libx264", "-preset", "veryfast", "-crf",
             "28", "-vf", "scale='min(1280,iw)':-2", "-c:a", "aac", "-b:a",
             "96k", "-map_metadata", "-1", out])
        return out
    Image, _, _, _ = _pil()
    im = Image.open(src).convert("RGB")
    out = os.path.join(job_dir, "compressed.jpg")
    im.save(out, "JPEG", quality=q, optimize=True)
    return out


async def t_convert(update, context, info, src, args, job_dir):
    if not args:
        raise _UsageError("/convert <jpg|png|webp|mp4|gif>")
    fmt = args[0].lower().lstrip(".")
    if fmt in ("jpg", "jpeg", "png", "webp") and info.is_image_like:
        Image, _, _, _ = _pil()
        im = Image.open(src)
        out = os.path.join(job_dir, "out." + ("jpg" if fmt == "jpeg" else fmt))
        if fmt in ("jpg", "jpeg"):
            im = im.convert("RGB")
            im.save(out, "JPEG", quality=93)
        else:
            im.save(out, fmt.upper())
        return out
    if fmt == "mp4" and info.is_video_like:
        out = os.path.join(job_dir, "out.mp4")
        await video_engine.tool_render(
            ["-i", src, "-c:v", "libx264", "-preset", "veryfast", "-crf",
             "23", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
             "-movflags", "+faststart", "-map_metadata", "-1", out])
        return out
    if fmt == "gif":
        out = os.path.join(job_dir, "out.gif")
        if info.is_video_like:
            meta = video_engine.probe(src)
            if (meta.get("duration") or 0) > 30:
                raise _UsageError("GIF conversion is capped at 30s of video.")
            fc = ("[0:v]fps=12,scale='min(480,iw)':-1:flags=lanczos,split"
                  "[a][b];[a]palettegen=stats_mode=diff[p];"
                  "[b][p]paletteuse=dither=bayer:bayer_scale=4[v]")
            await video_engine.tool_render(
                ["-i", src, "-filter_complex", fc, "-map", "[v]",
                 "-loop", "0", out])
        else:
            Image, _, _, _ = _pil()
            im = Image.open(src).convert("RGB")
            im.thumbnail((640, 640), Image.LANCZOS)
            im.save(out, "GIF")
        return out
    raise _UsageError("Can't convert that %s to %s — try /convert jpg|png|"
                      "webp|mp4|gif" % ("image" if info.is_image_like else
                                        "video", fmt))


def _parse_time(tok):
    m = re.match(r"^(\d+):(\d{1,2})(?:\.(\d+))?$", tok)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2)) + \
            (float("0." + m.group(3)) if m.group(3) else 0.0)
    m = re.match(r"^(\d+(?:\.\d+)?)$", tok)
    if m:
        return float(m.group(1))
    return None


async def t_trim(update, context, info, src, args, job_dir):
    if not args or "-" not in args[0]:
        raise _UsageError("/trim <start>-<end> — e.g. /trim 3-12 or "
                          "/trim 1:20-1:45")
    a, b = args[0].split("-", 1)
    t0, t1 = _parse_time(a), _parse_time(b)
    if t0 is None or t1 is None or t1 <= t0:
        raise _UsageError("Couldn't read those times — e.g. /trim 3-12")
    out = os.path.join(job_dir, "trimmed.mp4")
    await video_engine.tool_render(
        ["-ss", "%.2f" % t0, "-i", src, "-t", "%.2f" % (t1 - t0),
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
         "-movflags", "+faststart", "-map_metadata", "-1", out],
        duration=(t1 - t0))
    return out


async def t_tomp3(update, context, info, src, args, job_dir):
    out = os.path.join(job_dir, "audio.mp3")
    await video_engine.tool_render(
        ["-i", src, "-vn", "-c:a", "libmp3lame", "-b:a", "192k", out])
    return out


async def t_speed(update, context, info, src, args, job_dir):
    if not args:
        raise _UsageError("/speed <0.5-4> — e.g. /speed 1.5")
    try:
        factor = float(args[0].replace("x", "").replace("X", ""))
    except ValueError:
        raise _UsageError("/speed <0.5-4>")
    if not (0.5 <= factor <= 4.0):
        raise _UsageError("Speed must be between 0.5 and 4.")
    atempo = "atempo=%.3f" % factor
    if factor > 2.0:
        atempo = "atempo=2.0,atempo=%.3f" % (factor / 2.0)
    elif factor < 0.5:
        atempo = "atempo=0.5,atempo=%.3f" % (factor / 0.5)
    out = os.path.join(job_dir, "sped.mp4")
    vf = "setpts=%.5f*PTS" % (1.0 / factor)
    has_audio = video_engine.probe(src).get("has_audio")
    if has_audio:
        await video_engine.tool_render(
            ["-i", src, "-filter_complex",
             "[0:v]%s[v];[0:a]%s[a]" % (vf, atempo), "-map", "[v]",
             "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast", "-crf",
             "23", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
             "-map_metadata", "-1", out])
    else:  # audioless input: [0:a] would match no streams
        await video_engine.tool_render(
            ["-i", src, "-vf", vf, "-an", "-c:v", "libx264", "-preset",
             "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
             "-map_metadata", "-1", out])
    return out


async def t_reverse(update, context, info, src, args, job_dir):
    meta = video_engine.probe(src)
    if (meta.get("duration") or 0) > 60:
        raise _UsageError("Reverse is capped at 60s videos (memory limits).")
    out = os.path.join(job_dir, "reversed.mp4")
    await video_engine.tool_render(
        ["-i", src, "-vf", "reverse", "-an", "-c:v", "libx264", "-preset",
         "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
         "-map_metadata", "-1", out], duration=meta.get("duration"))
    return out


async def t_mute(update, context, info, src, args, job_dir):
    out = os.path.join(job_dir, "muted.mp4")
    await video_engine.tool_render(
        ["-i", src, "-an", "-c:v", "copy", "-map_metadata", "-1", out])
    return out


async def t_ss(update, context, info, src, args, job_dir):
    t = _parse_time(args[0]) if args else None
    if t is None:
        t = 0.0
    out = os.path.join(job_dir, "frame.jpg")
    await video_engine.tool_render(
        ["-ss", "%.2f" % max(0.0, t), "-i", src, "-frames:v", "1", "-q:v",
         "2", out])
    return out


async def t_meta(update, context, info, src, args, job_dir):
    import subprocess
    r = subprocess.run([ffmpeg(), "-hide_banner", "-i", src],
                       capture_output=True, text=True, timeout=30)
    lines = [ln for ln in (r.stderr or "").splitlines()
             if ("Stream" in ln or "Duration" in ln or "Input" in ln)]
    text = "📋 <b>Media info</b>\n<code>%s</code>" % H.esc(
        "\n".join(lines[:12]) or "no info")
    await H.reply(update.effective_message, text, parse_mode="HTML")
    return None


async def t_gray(update, context, info, src, args, job_dir):
    Image, _, _, _ = _pil()
    im = Image.open(src).convert("RGB")
    out = os.path.join(job_dir, "gray.jpg")
    im.convert("L").convert("RGB").save(out, "JPEG", quality=93)
    return out


async def t_sepia(update, context, info, src, args, job_dir):
    Image, _, _, _ = _pil()
    im = Image.open(src).convert("RGB")
    r, g, b = im.split()
    rr = r.point(lambda i: min(255, int(i * 0.393 + g.getextrema()[0] * 0)))
    # proper sepia matrix
    Image_ = Image
    sepia = Image_.merge("RGB", (
        r.point(lambda i: min(255, int(i * 0.393 + 76 * 0.769 + 149 * 0.189))),
        g.point(lambda i: min(255, int(i * 0.349 + 76 * 0.686 + 149 * 0.168))),
        b.point(lambda i: min(255, int(i * 0.272 + 76 * 0.534 + 149 * 0.131)))))
    out = os.path.join(job_dir, "sepia.jpg")
    sepia.save(out, "JPEG", quality=93)
    return out


async def t_blurbg(update, context, info, src, args, job_dir):
    Image, ImageDraw, ImageFilter, ImageOps = _pil()
    im = Image.open(src).convert("RGB")
    W, H = 1080, 1920
    bg = ImageOps.fit(im, (W, H), Image.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(28))
    fg = im.copy()
    fg.thumbnail((W, int(W * 3.2)), Image.LANCZOS)
    if fg.height > H - 120:
        fg.thumbnail((int((H - 120) * 4), H - 120), Image.LANCZOS)
    bg.paste(fg, ((W - fg.width) // 2, (H - fg.height) // 2))
    out = os.path.join(job_dir, "story.jpg")
    bg.save(out, "JPEG", quality=92)
    return out


_TOOLS = {
    "stickerize": t_stickerize,
    "circle": t_circle,
    "resize": t_resize,
    "compress": t_compress,
    "convert": t_convert,
    "trim": t_trim,
    "tomp3": t_tomp3,
    "speed": t_speed,
    "reverse": t_reverse,
    "mute": t_mute,
    "ss": t_ss,
    "meta": t_meta,
    "gray": t_gray,
    "sepia": t_sepia,
    "blurbg": t_blurbg,
}

USAGE = {
    "stickerize": "Cut out a photo into a sticker (white outline, "
                  "transparent bg)",
    "circle": "Crop a photo into a circle",
    "resize": "/resize 1080x1080",
    "compress": "/compress [10-95]",
    "convert": "/convert jpg|png|webp|mp4|gif",
    "trim": "/trim 3-12",
    "tomp3": "Extract MP3 audio from a video",
    "speed": "/speed 1.5",
    "reverse": "Reverse a short video (≤60s)",
    "mute": "Remove audio from a video",
    "ss": "/ss 12 — screenshot frame at second 12",
    "meta": "Show detailed media info",
    "gray": "Grayscale a photo",
    "sepia": "Sepia tone a photo",
    "blurbg": "9:16 story canvas with blurred background",
}
