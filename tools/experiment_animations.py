#!/usr/bin/env python3
"""Validate ffmpeg animation techniques v2 — fixed mapping + frame-sequence mode."""
import os
import re
import subprocess
import sys
from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageStat

FF = "/home/user/aquamark-bot/bin/ffmpeg"
TDIR = "/tmp/animtest2"
subprocess.run(["rm", "-rf", TDIR])
os.makedirs(f"{TDIR}/seq", exist_ok=True)


def run(args):
    return subprocess.run([FF, "-hide_banner", "-loglevel", "error", "-y"] + args,
                          capture_output=True, text=True)


r = run(["-f", "lavfi", "-i", "color=c=0x224466:s=320x240:r=25:d=2",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
         "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
         "-c:a", "aac", f"{TDIR}/base.mp4"])
assert r.returncode == 0, r.stderr[:400]

img = Image.new("RGBA", (120, 40), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.text((6, 3), "TEST", font=ImageFont.load_default(size=28),
       fill=(255, 255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0, 255))
img.save(f"{TDIR}/wm.png")

# frame sequence: typewriter reveal of "TYPEWRITER!"
text = "TYPEWRITER!"
for i in range(1, 12):
    fr = Image.new("RGBA", (150, 40), (0, 0, 0, 0))
    fd = ImageDraw.Draw(fr)
    fd.text((4, 3), text[:i], font=ImageFont.load_default(size=24),
            fill=(255, 220, 80, 255), stroke_width=1, stroke_fill=(0, 0, 0, 255))
    fr.save(f"{TDIR}/seq/{i:03d}.png")


def frame(video, t, name):
    out = f"{TDIR}/{name}.png"
    r = run(["-ss", str(t), "-i", video, "-frames:v", "1", "-pix_fmt", "rgba", out])
    assert r.returncode == 0, r.stderr[:400]
    return Image.open(out).convert("RGBA")


def rms(a, b):
    return ImageStat.Stat(ImageChops.difference(a, b).convert("L")).mean[0]


def duration(path):
    r = subprocess.run([FF, "-hide_banner", "-i", path], capture_output=True, text=True)
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.?\d*)", r.stderr)
    if not m:
        return None
    h, mnt, s = m.groups()
    return int(h) * 3600 + int(mnt) * 60 + float(s)


def has_audio(path):
    r = subprocess.run([FF, "-hide_banner", "-i", path], capture_output=True, text=True)
    return "Audio:" in r.stderr


def render(name, fc, out="out.mp4", second_input=None, map_audio=True, extra_out=None):
    outp = extra_out or f"{TDIR}/{out}"
    if second_input is None:
        second_input = ["-loop", "1", "-framerate", "25", "-i", f"{TDIR}/wm.png"]
    args = ["-i", f"{TDIR}/base.mp4"] + second_input + ["-filter_complex", fc,
           "-map", "[vout]"]
    if map_audio:
        args += ["-map", "0:a?"]
    args += ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
             "-pix_fmt", "yuv420p", "-shortest"]
    if map_audio:
        args += ["-c:a", "copy"]
    args += [outp]
    r = run(args)
    if r.returncode != 0:
        print(f"[FAIL] {name}:\n{r.stderr[:700]}")
        return None
    print(f"[ok] {name}: rendered, duration={duration(outp):.2f}s")
    return outp


bg = frame(f"{TDIR}/base.mp4", 1.0, "bg")
results = []


def check(label, ok):
    results.append((label, ok))
    print(f"     -> {'PASS' if ok else 'FAIL'}: {label}")


# ---- T1: DVD bounce ----
A, B = "max(W-w,1)", "max(H-h,1)"
fc = (f"[0:v][1:v]overlay=x='{A}-abs(mod(t*200,2*{A})-{A})'"
      f":y='{B}-abs(mod(t*130,2*{B})-{B})'[vout]")
p = render("T1 dvd-bounce", fc)
if p:
    check("dvd visible", rms(frame(p, 1.0, "t1c"), bg) > 3)
    check("dvd moves", rms(frame(p, 0.4, "t1a"), frame(p, 1.4, "t1b")) > 2)

# ---- T3: scale pulse ----
fc = ("[1:v]scale=w='iw*(1+0.25*abs(sin(2*PI*t)))':h=-1:eval=frame[wm];"
      "[0:v][wm]overlay=x=(W-w)/2:y=(H-h)/2[vout]")
p = render("T3 scale-pulse", fc)
if p:
    check("scale pulse visible", rms(frame(p, 0.4, "t3a"), bg) > 3)
    check("scale pulse changes", rms(frame(p, 0.4, "t3a"), frame(p, 1.4, "t3b")) > 2)

# ---- T4: rotate with t ----
fc = ("[1:v]format=rgba,rotate=a='0.7*sin(2*PI*t)':c=0x00000000:ow=iw:oh=ih[wm];"
      "[0:v][wm]overlay=x=(W-w)/2:y=(H-h)/2[vout]")
p = render("T4 rotate", fc)
if p:
    check("rotate visible", rms(frame(p, 0.4, "t4a"), bg) > 3)
    check("rotate changes", rms(frame(p, 0.4, "t4a"), frame(p, 1.4, "t4b")) > 2)

# ---- T6: enable gate ----
fc = "[0:v][1:v]overlay=x=20:y=20:enable='lt(mod(t,1),0.5)'[vout]"
p = render("T6 blink", fc)
if p:
    check("blink visible@0.3", rms(frame(p, 0.3, "t6a"), bg) > 3)
    check("blink hidden@0.7", rms(frame(p, 0.7, "t6b"), bg) < 1)

# ---- T7: fade in/out ----
fc = ("[1:v]format=rgba,fade=t=in:st=0:d=0.8:alpha=1,"
      "fade=t=out:st=1.4:d=0.6:alpha=1[wm];[0:v][wm]overlay=x=(W-w)/2:y=(H-h)/2[vout]")
p = render("T7 fade", fc)
if p:
    check("fade visible@1.0", rms(frame(p, 1.0, "t7a"), bg) > 3)
    check("fade changes", rms(frame(p, 0.5, "t7b"), frame(p, 1.7, "t7c")) > 2)

# ---- T8: edge-follow ----
S = "mod(t*150,2*(max(W-w,1)+max(H-h,1)))"
Ax, Bx = "max(W-w,1)", "max(H-h,1)"
fc = (f"[0:v][1:v]overlay=x='if(lt({S},{Ax}),{S},if(lt({S},{Ax}+{Bx}),{Ax},"
      f"if(lt({S},2*{Ax}+{Bx}),2*{Ax}+{Bx}-{S},0)))'"
      f":y='if(lt({S},{Ax}),0,if(lt({S},{Ax}+{Bx}),{S}-{Ax},"
      f"if(lt({S},2*{Ax}+{Bx}),{Bx},2*{Ax}+2*{Bx}-{S})))'[vout]")
p = render("T8 edge-follow", fc)
if p:
    check("edge-follow visible", rms(frame(p, 0.3, "t8a"), bg) > 3)
    check("edge-follow moves", rms(frame(p, 0.3, "t8a"), frame(p, 1.3, "t8b")) > 2)

# ---- T9: GIF palette output ----
fc = ("[0:v][1:v]overlay=x='(W-w)/2+30*sin(2*PI*t)':y=(H-h)/2,split[s0][s1];"
      "[s0]palettegen[p];[s1][p]paletteuse=dither=bayer:bayer_scale=4[vout]")
p = render("T9 gif", fc, out="out.gif", extra_out=f"{TDIR}/out.gif", map_audio=False)
if p:
    check("gif animates", rms(frame(p, 0.3, "t9a"), frame(p, 1.3, "t9b")) > 2)

# ---- T10: audio preserved ----
p = render("T10 audio-copy", "[0:v][1:v]overlay=x=20:y=20[vout]")
if p:
    check("audio present", has_audio(p))
    check("duration ~2s", abs(duration(p) - 2.0) < 0.35)

# ---- T11: frame-sequence typewriter with -stream_loop ----
seq_input = ["-stream_loop", "-1", "-framerate", "11", "-i", f"{TDIR}/seq/%03d.png"]
p = render("T11 typewriter-seq", "[0:v][1:v]overlay=x=30:y=H-h-30[vout]",
           second_input=seq_input)
if p:
    check("seq visible", rms(frame(p, 0.6, "t11a"), bg) > 3)
    check("seq types", rms(frame(p, 0.3, "t11b"), frame(p, 0.8, "t11c")) > 2)
    check("seq loops (visible late)", rms(frame(p, 1.8, "t11d"), bg) > 3)

# ---- T12: frame-sequence + motion expression combined ----
fc = "[0:v][1:v]overlay=x='(W-w)/2+40*sin(2*PI*t)':y=30[vout]"
p = render("T12 seq+motion", fc, second_input=seq_input)
if p:
    check("seq+motion moves", rms(frame(p, 0.2, "t12a"), frame(p, 0.7, "t12b")) > 2)

print("\n==== SUMMARY ====")
fails = [lbl for lbl, ok in results if not ok]
print(f"{sum(1 for _, ok in results if ok)}/{len(results)} checks passed")
if fails:
    print("FAILED:", fails)
    sys.exit(1)
print("ALL TECHNIQUES VALIDATED")
