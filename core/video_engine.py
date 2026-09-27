"""Async ffmpeg engine: video watermarking, photo loops, probing, helpers."""
import asyncio
import inspect
import os
import re
import subprocess

from . import animations as ANIM
from . import renderer as R

FF = None


def ffmpeg():
    global FF
    if FF is None:
        import bootstrap
        FF = bootstrap.ffmpeg_path()
    return FF


class FFmpegError(Exception):
    pass


class JobCancelled(Exception):
    pass


PROGRESS_THROTTLE = 0.6   # seconds between progress callbacks (test-patchable)


# ---------------------------------------------------------------- probing

_DUR_RE = re.compile(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)")
_DIM_RE = re.compile(r"Stream #\d+:\d+.*?: Video: .*?(\d{2,5})x(\d{2,5})")


def probe(path):
    """Return {duration, width, height, has_audio} parsed from ffmpeg output."""
    try:
        r = subprocess.run(
            [ffmpeg(), "-hide_banner", "-i", str(path)],
            capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        raise FFmpegError("probe timeout on %s" % path)
    err = r.stderr or ""
    duration = 0.0
    m = _DUR_RE.search(err)
    if m:
        h, mi, s = m.groups()
        duration = int(h) * 3600 + int(mi) * 60 + float(s)
    width = height = 0
    m = _DIM_RE.search(err)
    if m:
        width, height = int(m.group(1)), int(m.group(2))
    return {"duration": duration, "width": width, "height": height,
            "has_audio": "Audio:" in err}


# ---------------------------------------------------------------- runner

async def run_ffmpeg(args, duration=None, progress_cb=None, cancel_event=None,
                     timeout=None):
    """Run ffmpeg; parse -progress lines; support cancel + timeout."""
    cmd = [ffmpeg(), "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
           "-progress", "pipe:1", "-nostats"] + [str(a) for a in args]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)

    async def _work():
        last = 0.0
        last_frac = None
        loop = asyncio.get_event_loop()

        async def _emit(frac):
            nonlocal last, last_frac
            now = loop.time()
            if now - last >= PROGRESS_THROTTLE or frac >= 1.0:
                last = now
                last_frac = frac
                res = progress_cb(frac)
                if inspect.isawaitable(res):
                    await res

        while True:
            if cancel_event is not None and cancel_event.is_set():
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
                raise JobCancelled()
            line = await proc.stdout.readline()
            if not line:
                break
            if line.startswith(b"out_time_us=") and progress_cb and duration \
                    and duration > 0:
                try:
                    us = int(line.split(b"=", 1)[1])
                except ValueError:
                    continue
                frac = max(0.0, min(1.0, us / 1e6 / duration))
                await _emit(frac)
        # always finish at 100% on success so the UI never stalls below it
        if progress_cb and duration and duration > 0 \
                and (last_frac is None or last_frac < 1.0):
            await _emit(1.0)
        stderr = await proc.stderr.read()
        if cancel_event is not None and cancel_event.is_set():
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            raise JobCancelled()
        await proc.wait()
        if proc.returncode != 0:
            if proc.returncode == -9:
                # SIGKILL with no stderr = the OS OOM-killer almost always
                raise FFmpegError(
                    "The server ran out of memory while rendering (ffmpeg "
                    "was killed). Try a smaller/shorter video, the /settings "
                    "'low' quality preset, or add more RAM/swap to this "
                    "machine.")
            raise FFmpegError(stderr.decode("utf-8", "replace")[-900:] or
                              "ffmpeg exited with %s" % proc.returncode)
        return stderr.decode("utf-8", "replace")

    try:
        if timeout:
            return await asyncio.wait_for(_work(), timeout)
        return await _work()
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        raise FFmpegError("render timed out")
    except JobCancelled:
        raise
    finally:
        if proc.returncode is None:
            try:
                proc.kill()
            except ProcessLookupError:
                pass



def build_graph(s, W, H, sprite_w, sprite_h, duration, seq_info=None,
                force_scale=None, gif=False):
    """Build the complete filtergraph ending in [even]."""
    anim = ANIM.get(s.get("animation", "static"))
    tile = bool(s.get("tile"))
    v = float(s.get("anim_speed", 1.0))

    pre = None
    enable = None
    if tile:
        if anim.id == "static" or not anim.x:
            x = "%d" % int((W - sprite_w) / 2)
            y = "%d" % int((H - sprite_h) / 2)
        else:  # tiled canvases get a gentle drift
            x = "(W-w)/2+W*0.04*sin(2*PI*%g*t/9)" % v
            y = "(H-h)/2+H*0.04*sin(2*PI*%g*t/12)" % v
    else:
        inner_w = seq_info["inner_w"] if seq_info else sprite_w
        inner_h = seq_info["inner_h"] if seq_info else sprite_h
        bx, by = R.position_xy(s, W, H, inner_w, inner_h)
        if seq_info:
            bx -= seq_info["pad_x"]
            by -= seq_info["pad_y"]
        ov = ANIM.build_overlay(anim, s, W, H, sprite_w, sprite_h,
                                duration, (bx, by))
        x, y, pre = ov["x"], ov["y"], ov["pre"]
        if not anim.is_sequence:
            enable = ov["enable"]

    opts = []
    if x is not None:
        opts.append("x='%s'" % x)
    if y is not None:
        opts.append("y='%s'" % y)
    if enable:
        opts.append("enable='%s'" % enable)

    parts = []
    base_label = "[0:v]"
    if force_scale:
        parts.append("[0:v]scale=%s[base]" % force_scale)
        base_label = "[base]"
    wm_label = "[1:v]"
    if pre:
        parts.append("[1:v]%s[wm]" % pre)
        wm_label = "[wm]"
    parts.append("%s%soverlay=%s[wmout]" %
                 (base_label, wm_label, ":".join(opts) if opts else "0:0"))

    if gif:
        parts.append("[wmout]split[a0][b0];[a0]palettegen=stats_mode=diff[p];"
                     "[b0][p]paletteuse=dither=bayer:bayer_scale=4[even]")
    else:
        parts.append("[wmout]scale=trunc(iw/2)*2:trunc(ih/2)*2,"
                     "format=yuv420p[even]")
    return ";".join(parts)


def _wm_input_args(sprite_path, seq_info, gif=False, duration=None):
    """Watermark source inputs.

    Single PNG: a FINITE loop (`-loop 1 -t duration`) so time-based pre
    filters (scale/rotate/fade expressions with t) re-evaluate per frame.
    A finite loop is required: infinite looped image inputs combined with
    the palettegen/paletteuse GIF graph make ffmpeg 7.x consume unbounded
    memory, and single (non-looped) frames freeze t-dependent filters.
    Sequence: -stream_loop for video; GIF renders use pre-extended frames
    (no loop) for the same reason.
    """
    if seq_info and seq_info.get("dir"):
        args = ["-framerate", str(seq_info["fps"]),
                "-i", os.path.join(seq_info["dir"], "%04d.png")]
        if not gif:
            args = ["-stream_loop", "-1"] + args
        return args
    args = ["-loop", "1", "-framerate", "25"]
    if duration:
        args += ["-t", "%.3f" % (float(duration) + 0.5)]
    args += ["-i", str(sprite_path)]
    return args


async def _render(inputs, graph, out, duration, s, audio_mode, crf, preset,
                  gif, progress_cb, cancel_event, timeout):
    args = list(inputs) + ["-filter_complex", graph, "-map", "[even]",
                           "-t", "%.3f" % max(0.2, duration)]
    if not gif and audio_mode != "none":
        args += ["-map", "0:a?"]
    if gif:
        args += ["-loop", "0"]
    else:
        args += ["-c:v", "libx264", "-preset", preset, "-crf", str(crf),
                 "-movflags", "+faststart", "-pix_fmt", "yuv420p"]
        if audio_mode == "copy":
            args += ["-c:a", "copy"]
        elif audio_mode == "encode":
            args += ["-c:a", "aac", "-b:a", "128k"]
    args += ["-map_metadata", "-1", str(out)]
    return await run_ffmpeg(args, duration=duration, progress_cb=progress_cb,
                            cancel_event=cancel_event, timeout=timeout)


# ---------------------------------------------------------------- public API

async def watermark_video(src, out_base, sprite_path, s, meta, seq_info=None,
                          progress_cb=None, cancel_event=None):
    """Watermark a video -> mp4 (or gif). Returns the output path."""
    import config

    duration = meta.get("duration") or 0.0
    if duration <= 0:
        raise FFmpegError("could not determine video duration")
    W, H = meta.get("width") or 0, meta.get("height") or 0
    if W <= 0 or H <= 0:
        raise FFmpegError("could not determine video dimensions")

    gif = s.get("out_format") == "gif" and duration <= 20.0
    out = out_base + (".gif" if gif else ".mp4")

    src_lower = str(src).lower()
    force_encode_audio = any(x in src_lower for x in (".webm", ".mkv"))
    if not s.get("keep_audio", True) or not meta.get("has_audio") or gif:
        audio_mode = "none"
    elif force_encode_audio:
        audio_mode = "encode"
    else:
        audio_mode = "copy"

    crf, preset = config.QUALITY.get(s.get("quality", "high"), (22, "medium"))
    timeout = max(120.0, duration * 8.0)
    sprite_w, sprite_h = _sprite_dims(sprite_path, seq_info)

    def graph_for(scale=None):
        return build_graph(s, W, H, sprite_w, sprite_h, duration,
                           seq_info=seq_info, force_scale=scale, gif=gif)

    inputs = ["-i", str(src)] + _wm_input_args(sprite_path, seq_info, gif,
                                               duration)

    async def attempt(audio_mode_, scale=None):
        return await _render(inputs, graph_for(scale), out, duration, s,
                             audio_mode_, crf, preset, gif, progress_cb,
                             cancel_event, timeout)

    try:
        await attempt(audio_mode)
    except FFmpegError:
        if audio_mode == "copy":
            await attempt("encode")   # container/codec mismatch fallback
        else:
            raise

    tries = 0
    while os.path.getsize(out) > config.MAX_OUT_SIZE and tries < 2:
        tries += 1
        scale = "min(1280,iw):-2" if tries == 1 else "min(854,iw):-2"
        crf = min(32, crf + 4)
        await attempt(audio_mode, scale)

    if os.path.getsize(out) > config.MAX_OUT_SIZE:
        raise FFmpegError("output still exceeds the 50 MB Telegram limit "
                          "after compression retries")
    return out


async def render_photo_loop(photo_path, out_base, sprite_path, s,
                            seq_info=None, progress_cb=None,
                            cancel_event=None):
    """Animated watermark over a still photo -> looping mp4 (or gif)."""
    import config

    loop_secs = float(s.get("loop_secs", 4))
    from PIL import Image
    with Image.open(photo_path) as im:
        W, H = im.size
    if W * H > 2600000:  # keep loop renders snappy on huge photos
        ratio = (2600000.0 / (W * H)) ** 0.5
        W, H = int(W * ratio), int(H * ratio)
        photo_path = _downscale_photo(photo_path, W, H)

    gif = s.get("out_format") == "gif"
    out = out_base + (".gif" if gif else ".mp4")
    crf, preset = config.QUALITY.get(s.get("quality", "high"), (22, "medium"))
    sprite_w, sprite_h = _sprite_dims(sprite_path, seq_info)

    graph = build_graph(s, W, H, sprite_w, sprite_h, loop_secs,
                        seq_info=seq_info, gif=gif)
    inputs = (["-loop", "1", "-framerate", "25", "-t", "%.3f" % loop_secs,
               "-i", str(photo_path)] + _wm_input_args(sprite_path, seq_info,
                                                       gif, loop_secs))
    await _render(inputs, graph, out, loop_secs, s, "none", crf, preset, gif,
                  progress_cb, cancel_event, max(90.0, loop_secs * 12))
    return out


def _sprite_dims(sprite_path, seq_info):
    if seq_info:
        return seq_info["w"], seq_info["h"]
    from PIL import Image
    with Image.open(sprite_path) as im:
        return im.size


def _downscale_photo(photo_path, W, H):
    from PIL import Image
    out = str(photo_path) + ".scaled.png"
    with Image.open(photo_path) as im:
        im = im.convert("RGB").resize((W, H), R.RESAMPLE)
        im.save(out, "PNG")
    return out


# ---------------------------------------------------------------- tools API

async def tool_render(args, duration=None, progress_cb=None, cancel_event=None,
                      timeout=900):
    return await run_ffmpeg(args, duration=duration, progress_cb=progress_cb,
                            cancel_event=cancel_event, timeout=timeout)
