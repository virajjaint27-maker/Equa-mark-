"""Telegram media classification + download/upload helpers."""
import logging
import os

import config

log = logging.getLogger("aquamark.media")

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"}
VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v", ".3gp",
              ".mpg", ".mpeg", ".ts", ".flv", ".wmv"}
AUDIO_EXTS = {".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".flac"}

KIND_PHOTO = "photo"            # compressible photo (send as photo)
KIND_IMAGE_DOC = "image_doc"    # image sent as file (keeps quality)
KIND_VIDEO = "video"
KIND_ANIMATION = "animation"    # gif / looping mp4 doc
KIND_VIDEO_NOTE = "video_note"
KIND_AUDIO = "audio"
KIND_PDF = "pdf"
KIND_UNSUPPORTED = "unsupported"


class MediaInfo(object):
    def __init__(self, kind, file_id, tg=None, filename=None, ext=None,
                 file_size=None, message=None):
        self.kind = kind
        self.file_id = file_id
        self.tg = tg or {}          # {width, height, duration}
        self.filename = filename
        self.ext = ext
        self.file_size = file_size
        self.message = message

    @property
    def is_video_like(self):
        return self.kind in (KIND_VIDEO, KIND_ANIMATION, KIND_VIDEO_NOTE)

    @property
    def is_image_like(self):
        return self.kind in (KIND_PHOTO, KIND_IMAGE_DOC)

    def summary(self):
        bits = [self.kind]
        if self.tg.get("width"):
            bits.append("%dx%d" % (self.tg.get("width", 0), self.tg.get("height", 0)))
        if self.tg.get("duration"):
            bits.append("%.0fs" % self.tg["duration"])
        if self.file_size:
            bits.append("%.1f MB" % (self.file_size / 1048576.0))
        return " · ".join(bits)


def classify(message):
    """Inspect a Telegram message and return MediaInfo (or None)."""
    if message is None:
        return None
    if message.photo:
        p = message.photo[-1]  # largest
        return MediaInfo(KIND_PHOTO, p.file_id,
                         tg={"width": p.width, "height": p.height},
                         ext=".jpg", file_size=p.file_size, message=message)
    if message.video:
        v = message.video
        fname = getattr(v, "file_name", None) or ""
        ext = os.path.splitext(fname)[1].lower() or ".mp4"
        return MediaInfo(KIND_VIDEO, v.file_id,
                         tg={"width": v.width, "height": v.height,
                             "duration": v.duration},
                         filename=fname, ext=ext,
                         file_size=v.file_size, message=message)
    if message.animation:
        a = message.animation
        fname = getattr(a, "file_name", None) or ""
        ext = os.path.splitext(fname)[1].lower() or ".mp4"
        return MediaInfo(KIND_ANIMATION, a.file_id,
                         tg={"width": a.width, "height": a.height,
                             "duration": a.duration},
                         filename=fname, ext=ext,
                         file_size=a.file_size, message=message)
    if message.video_note:
        vn = message.video_note
        return MediaInfo(KIND_VIDEO_NOTE, vn.file_id,
                         tg={"width": vn.length, "height": vn.length,
                             "duration": vn.duration},
                         ext=".mp4", file_size=vn.file_size, message=message)
    if message.sticker:
        st = message.sticker
        # NB: PTB's Sticker has NO file_name attribute (unlike Document)
        st_name = getattr(st, "file_name", None)
        if getattr(st, "is_animated", False) or getattr(st, "is_video", False):
            return MediaInfo(KIND_UNSUPPORTED, st.file_id,
                             tg={"duration": getattr(st, "duration", 3) or 3},
                             filename=st_name or "sticker.tgs", ext=".tgs",
                             file_size=st.file_size, message=message)
        return MediaInfo(KIND_IMAGE_DOC, st.file_id,
                         tg={"width": st.width, "height": st.height},
                         filename=st_name or "sticker.webp",
                         ext=".webp", file_size=st.file_size, message=message)
    if message.document:
        d = message.document
        fname = getattr(d, "file_name", None) or ""
        ext = os.path.splitext(fname)[1].lower()
        mime = (d.mime_type or "").lower()
        if ext == ".pdf" or mime == "application/pdf":
            return MediaInfo(KIND_PDF, d.file_id, filename=fname,
                             ext=".pdf", file_size=d.file_size,
                             message=message)
        if ext in VIDEO_EXTS or mime.startswith("video/"):
            return MediaInfo(KIND_VIDEO, d.file_id, filename=fname, ext=ext or ".mp4",
                             file_size=d.file_size, message=message)
        if ext in IMAGE_EXTS or mime.startswith("image/"):
            return MediaInfo(KIND_IMAGE_DOC, d.file_id,
                             tg={"width": 0, "height": 0},
                             filename=fname, ext=ext or ".bin",
                             file_size=d.file_size, message=message)
        if ext in AUDIO_EXTS or mime.startswith("audio/"):
            return MediaInfo(KIND_AUDIO, d.file_id, filename=fname, ext=ext,
                             file_size=d.file_size, message=message)
        return MediaInfo(KIND_UNSUPPORTED, d.file_id, filename=fname, ext=ext,
                         file_size=d.file_size, message=message)
    if message.voice or message.audio:
        return MediaInfo(KIND_AUDIO, (message.voice or message.audio).file_id,
                         message=message)
    return None


UNSUPPORTED_TEXT = (
    "🤔 I can't watermark that file type.\n\n"
    "I can process:\n"
    "• Photos (JPEG/PNG/WebP/BMP)\n"
    "• Videos (MP4/MKV/MOV/WEBM…)\n"
    "• GIFs & animations\n"
    "• Round video notes\n\n"
    "Animated (Lottie) stickers aren't supported — but static sticker files are!"
)


async def download(context, media, dest_dir):
    """Download a media file. Returns local path. Raises on oversize/API issues."""
    os.makedirs(dest_dir, exist_ok=True)
    cap_mb = config.MAX_IN_SIZE // 1048576
    if media.file_size and media.file_size > config.MAX_IN_SIZE:
        raise TooLarge(
            "That file is %.1f MB — this bot can receive files up to %d MB. "
            "Send a smaller/compressed version (or strip it with a "
            "compressor app first)." % (media.file_size / 1048576.0, cap_mb))
    tg_file = await context.bot.get_file(media.file_id)
    if media.ext:
        name = "media" + media.ext
    else:
        name = "media.bin"
    path = os.path.join(dest_dir, name)
    await tg_file.download_to_drive(path)
    if os.path.getsize(path) > config.MAX_IN_SIZE + 2097152:
        raise TooLarge("Downloaded file exceeds the %d MB receive limit."
                       % cap_mb)
    return path


class TooLarge(Exception):
    pass


async def send_watermarked(message, path, media_kind, meta=None, s=None,
                           caption=None):
    """Upload a produced file with the right message type."""
    s = s or {}
    if caption:
        # decode [[tokens]] + apply the UI font on the plain-caption path
        from core import cemoji
        caption = cemoji.expand(caption)
    size = os.path.getsize(path)
    send_doc = (s.get("send_as") == "document" or
                size > config.MAX_OUT_SIZE or media_kind == KIND_PDF or
                path.lower().endswith(".pdf"))
    with open(path, "rb") as fh:
        if path.endswith(".gif"):
            return await message.reply_animation(
                animation=fh, caption=caption, write_timeout=180)
        if send_doc:
            return await message.reply_document(
                document=fh, caption=caption, force_document=True,
                filename=os.path.basename(path), write_timeout=180)
        if media_kind in (KIND_PHOTO, KIND_IMAGE_DOC) and path.lower().endswith(
                (".jpg", ".jpeg", ".png", ".webp")):
            return await message.reply_photo(photo=fh, caption=caption,
                                             write_timeout=180)
        kw = {"caption": caption, "write_timeout": 180,
              "supports_streaming": True}
        if meta:
            if meta.get("width"):
                kw["width"] = int(meta["width"])
            if meta.get("height"):
                kw["height"] = int(meta["height"])
            if meta.get("duration"):
                kw["duration"] = int(meta["duration"])
        return await message.reply_video(video=fh, **kw)
