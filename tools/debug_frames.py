#!/usr/bin/env python3
"""Debug: render key cases, print real rms numbers, save frames for visual inspection."""
import os
import re
import subprocess
from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageStat

FF = "/home/user/aquamark-bot/bin/ffmpeg"
TDIR = "/tmp/animtest3"
subprocess.run(["rm", "-rf", TDIR])
os.makedirs(f"{TDIR}/seq", exist_ok=True)


def run(args):
    return subprocess.run([FF, "-hide_banner", "-loglevel", "error", "-y"] + args,
                          capture_output=True, text=True)


r = run(["-f", "lavfi", "-i", "color=c=0x224466:s=320x240:r=25:d=2",
         "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
         f"{TDIR}/base.mp4"])
assert r.returncode == 0, r.stderr

img = Image.new("RGBA", (120, 40), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.text((6, 3), "TEST", font=ImageFont.load_default(size=28),
       fill=(255, 255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0, 255))
img.save(f"{TDIR}/wm.png")

text = "TYPEWRITER!"
for i in range(0, 11):  # start at 000.png
    fr = Image.new("RGBA", (150, 40), (0, 0, 0, 0))
    fd = ImageDraw.Draw(fr)
    fd.text((4, 3), text[:i], font=ImageFont.load_default(size=24),
            fill=(255, 220, 80, 255), stroke_width=1, stroke_fill=(0, 0, 0, 255))
    fr.save(f"{TDIR}/seq/{i:03d}.png")


def frame(video, t, name):
    out = f"{TDIR}/{name}.png"
    r = run(["-ss", str(t), "-i", video, "-frames:v", "1", "-pix_fmt", "rgba", out])
    assert r.returncode == 0, r.stderr[:300]
    return Image.open(out).convert("RGBA")


def rms(a, b):
    return ImageStat.Stat(ImageChops.difference(a, b).convert("L"))


def stats(a, b):
    st = rms(a, b)
    return f"mean={st.mean[0]:.2f} sum={st.sum[0]:.0f}"


bg = frame(f"{TDIR}/base.mp4", 1.0, "bg")

CASES = {
    "static": ("[0:v][1:v]overlay=x=100:y=100[vout]",
               ["-loop", "1", "-framerate", "25", "-i", f"{TDIR}/wm.png"], None),
    "seq_type": ("[0:v][1:v]overlay=x=30:y=170[vout]",
                 ["-stream_loop", "-1", "-framerate", "11", "-i", f"{TDIR}/seq/%03d.png"], None),
    "scale_pulse": ("[1:v]scale=w='iw*(1+0.25*abs(sin(2*PI*t)))':h=-1:eval=frame[wm];"
                    "[0:v][wm]overlay=x=(W-w)/2:y=(H-h)/2[vout]",
                    ["-loop", "1", "-framerate", "25", "-i", f"{TDIR}/wm.png"], None),
    "rotate": ("[1:v]format=rgba,rotate=a='0.7*sin(2*PI*t)':c=0x00000000:ow=iw:oh=ih[wm];"
               "[0:v][wm]overlay=x=(W-w)/2:y=(H-h)/2[vout]",
               ["-loop", "1", "-framerate", "25", "-i", f"{TDIR}/wm.png"], None),
}

for name, (fc, second, _) in CASES.items():
    outp = f"{TDIR}/{name}.mp4"
    r = run(["-i", f"{TDIR}/base.mp4"] + second +
            ["-filter_complex", fc, "-map", "[vout]",
             "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
             "-pix_fmt", "yuv420p", "-shortest", outp])
    print(f"[{name}] rc={r.returncode} {r.stderr[:200]}")
    if r.returncode != 0:
        continue
    if name == "static":
        f = frame(outp, 1.0, f"{name}_f")
        print(f"   visible vs bg: {stats(f, bg)}")
    if name == "seq_type":
        f02, f05, f09, f19 = (frame(outp, t, f"{name}_{t}") for t in (0.2, 0.5, 0.9, 1.9))
        print(f"   0.2 vs bg: {stats(f02, bg)}")
        print(f"   0.2 vs 0.5 (typing): {stats(f02, f05)}")
        print(f"   0.2 vs 1.9 (loop repeat?): {stats(f02, f19)}")
        print(f"   0.9 vs bg (full text): {stats(f09, bg)}")
    if name == "scale_pulse":
        f04, f07, f10 = (frame(outp, t, f"{name}_{t}") for t in (0.4, 0.7, 1.0))
        print(f"   0.4 vs bg: {stats(f04, bg)}")
        print(f"   0.4 vs 0.7 (pulse): {stats(f04, f07)}")
        print(f"   1.0 vs bg (max size): {stats(f10, bg)}")
    if name == "rotate":
        f02, f045, f07 = (frame(outp, t, f"{name}_{t}") for t in (0.2, 0.45, 0.7))
        print(f"   0.2 vs bg: {stats(f02, bg)}")
        print(f"   0.2 vs 0.45 (rotated): {stats(f02, f045)}")
        print(f"   0.7 vs bg: {stats(f07, bg)}")

print("\nDone. Frames saved in", TDIR)
