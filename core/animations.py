"""AquaMark animation registry — 106 motion & text-effect presets.

Two render modes, both validated against real ffmpeg renders:
  * "expr"    — single PNG sprite + overlay x/y (+scale/rotate/fade/enable) expressions
  * "seq"/"seqexpr" — PIL-rendered frame sequence (-stream_loop) with optional motion exprs

Expression variables (ffmpeg overlay eval): W,H main size, w,h overlay size, t seconds.
Template placeholders filled at build time: {v} speed, {bx},{by} anchored base position,
{ax},{ay},{m},{cx},{cy} safe-motion helpers, {dur} media duration.
"""
import math


class Anim(object):
    __slots__ = ("id", "name", "icon", "cat", "mode", "x", "y", "pre", "enable",
                 "seq", "seq_params", "roams", "once", "probe")

    def __init__(self, aid, name, icon, cat, mode="expr", x=None, y=None,
                 pre=None, enable=None, seq=None, seq_params=None,
                 roams=False, once=False, probe=None):
        self.id = aid
        self.name = name
        self.icon = icon
        self.cat = cat
        self.mode = mode
        self.x = x
        self.y = y
        self.pre = pre
        self.enable = enable
        self.seq = seq
        self.seq_params = seq_params or {}
        self.roams = roams
        self.once = once
        # test probe: ("motion", t1, t2) | ("gate", t_on, t_off)
        self.probe = probe or ("motion", 0.30, 0.85)

    @property
    def is_sequence(self):
        return self.mode in ("seq", "seqexpr")


CATS = [
    ("bounce", "Bounce", "📀"),
    ("slide", "Slide & Marquee", "↔️"),
    ("wave", "Waves & Orbits", "〰️"),
    ("zoom", "Zoom & Pulse", "🔍"),
    ("rotate", "Rotation", "🔄"),
    ("blink", "Blink & Strobe", "⚡"),
    ("fade", "Fade", "🌗"),
    ("edge", "Edge Patrol", "🛡"),
    ("jump", "Jumps & Teleports", "🌀"),
    ("fun", "Fun & FX", "🎉"),
    ("combo", "Pro Combos", "💎"),
    ("textfx", "Text Effects", "✍️"),
]


def _A(**kw):
    return kw


# Order matters for catalog display.
_SPECS = [
    # ---------------- BOUNCE (10) ----------------
    _A(aid="dvd", name="DVD Bounce", icon="📀", cat="bounce", roams=True,
       x="{ax}-abs(mod(t*{v}*0.50*{ax},2*{ax})-{ax})",
       y="{ay}-abs(mod(t*{v}*0.34*{ay},2*{ay})-{ay})"),
    _A(aid="dvd-slow", name="DVD Bounce Slow", icon="🐌", cat="bounce", roams=True,
       x="{ax}-abs(mod(t*{v}*0.20*{ax},2*{ax})-{ax})",
       y="{ay}-abs(mod(t*{v}*0.13*{ay},2*{ay})-{ay})",
       probe=("motion", 0.5, 1.7)),
    _A(aid="bounce-bottom", name="Bounce (bottom)", icon="🏀", cat="bounce",
       x="{bx}", y="{ay}-{ay}*abs(sin(2*PI*{v}*0.45*t))"),
    _A(aid="bounce-top", name="Bounce (top)", icon="🎈", cat="bounce",
       x="{bx}", y="{ay}*(1-abs(sin(2*PI*{v}*0.45*t)))"),
    _A(aid="bounce-left", name="Bounce (left)", icon="🏓", cat="bounce",
       x="{ax}*(1-abs(sin(2*PI*{v}*0.45*t)))", y="{by}"),
    _A(aid="bounce-right", name="Bounce (right)", icon="🎾", cat="bounce",
       x="{ax}*abs(sin(2*PI*{v}*0.45*t))", y="{by}"),
    _A(aid="bounce-diag", name="Diagonal Bounce", icon="↗️", cat="bounce", roams=True,
       x="{ax}*abs(sin(2*PI*{v}*0.35*t))",
       y="{ay}*abs(sin(2*PI*{v}*0.27*t))"),
    _A(aid="pingpong-x", name="Ping-Pong ↔", icon="↔️", cat="bounce", roams=True,
       x="{ax}-abs(mod(t*{v}*0.45*{ax},2*{ax})-{ax})", y="{by}"),
    _A(aid="pingpong-y", name="Ping-Pong ↕️", icon="↕️", cat="bounce", roams=True,
       x="{bx}", y="{ay}-abs(mod(t*{v}*0.45*{ay},2*{ay})-{ay})"),
    _A(aid="bounce-squash", name="Squash Bounce", icon="🤸", cat="bounce",
       pre="scale=w='iw*(1+0.18*pow(abs(cos(2*PI*{v}*0.45*t)),6))'"
           ":h='ih*(1-0.22*pow(abs(cos(2*PI*{v}*0.45*t)),6))':eval=frame",
       x="{bx}", y="{ay}-{ay}*abs(sin(2*PI*{v}*0.45*t))"),

    # ---------------- SLIDE & MARQUEE (12) ----------------
    _A(aid="marquee-lr", name="Marquee →", icon="➡️", cat="slide", roams=True,
       x="W-mod(t*{v}*0.30*(W+w),W+w)", y="{by}"),
    _A(aid="marquee-rl", name="Marquee ←", icon="⬅️", cat="slide", roams=True,
       x="-w+mod(t*{v}*0.30*(W+w),W+w)", y="{by}"),
    _A(aid="marquee-tb", name="Marquee ↓", icon="⬇️", cat="slide", roams=True,
       x="{bx}", y="H-mod(t*{v}*0.30*(H+h),H+h)"),
    _A(aid="marquee-bt", name="Marquee ↑", icon="⬆️", cat="slide", roams=True,
       x="{bx}", y="-h+mod(t*{v}*0.30*(H+h),H+h)"),
    _A(aid="diag-dr", name="Diagonal ↘", icon="↘️", cat="slide", roams=True,
       x="W-mod(t*{v}*0.30*(W+w),W+w)", y="H-mod(t*{v}*0.30*(H+h),H+h)"),
    _A(aid="diag-ur", name="Diagonal ↗", icon="↗️", cat="slide", roams=True,
       x="W-mod(t*{v}*0.30*(W+w),W+w)", y="-h+mod(t*{v}*0.30*(H+h),H+h)"),
    _A(aid="diag-ul", name="Diagonal ↖", icon="↖️", cat="slide", roams=True,
       x="-w+mod(t*{v}*0.30*(W+w),W+w)", y="-h+mod(t*{v}*0.30*(H+h),H+h)"),
    _A(aid="diag-dl", name="Diagonal ↙", icon="↙️", cat="slide", roams=True,
       x="-w+mod(t*{v}*0.30*(W+w),W+w)", y="H-mod(t*{v}*0.30*(H+h),H+h)"),
    _A(aid="slide-lr", name="Slide In →", icon="oplay", cat="slide", once=True,
       x="-w+({bx}+w)*(1-pow(1-min(1,t*{v}*0.8),2))", y="{by}",
       probe=("motion", 0.15, 0.7)),
    _A(aid="slide-rl", name="Slide In ←", icon="◀️", cat="slide", once=True,
       x="W+({bx}-W)*(1-pow(1-min(1,t*{v}*0.8),2))", y="{by}",
       probe=("motion", 0.15, 0.7)),
    _A(aid="slide-tb", name="Slide In ↓", icon="⬇️", cat="slide", once=True,
       x="{bx}", y="-h+({by}+h)*(1-pow(1-min(1,t*{v}*0.8),2))",
       probe=("motion", 0.15, 0.7)),
    _A(aid="slide-bt", name="Slide In ↑", icon="⬆️", cat="slide", once=True,
       x="{bx}", y="H+({by}-H)*(1-pow(1-min(1,t*{v}*0.8),2))",
       probe=("motion", 0.15, 0.7)),

    # ---------------- WAVES & ORBITS (12) ----------------
    _A(aid="wave-h", name="Wave 〰", icon="🌊", cat="wave",
       x="{bx}", y="{by}+{ay}*0.10*sin(2*PI*{v}*t)"),
    _A(aid="wave-v", name="Wave (sideways)", icon=" Sin", cat="wave",
       x="{bx}+{ax}*0.10*sin(2*PI*{v}*t)", y="{by}"),
    _A(aid="float", name="Float", icon="☁️", cat="wave",
       x="{bx}+{ax}*0.08*sin(2*PI*{v}*0.35*t+0.5)",
       y="{by}+{ay}*0.10*sin(2*PI*{v}*0.27*t+1.2)"),
    _A(aid="figure8", name="Figure 8", icon="8️⃣", cat="wave", roams=True,
       x="{cx}+{ax}*0.35*sin(2*PI*{v}*0.40*t)",
       y="{cy}+{ay}*0.35*sin(2*PI*{v}*0.80*t)"),
    _A(aid="lissajous-13", name="Lissajous 1:3", icon="➰", cat="wave", roams=True,
       x="{cx}+{ax}*0.35*sin(2*PI*{v}*0.33*t)",
       y="{cy}+{ay}*0.35*sin(2*PI*{v}*0.99*t)"),
    _A(aid="lissajous-32", name="Lissajous 3:2", icon="🌀", cat="wave", roams=True,
       x="{cx}+{ax}*0.35*sin(2*PI*{v}*0.66*t)",
       y="{cy}+{ay}*0.35*sin(2*PI*{v}*0.44*t)"),
    _A(aid="orbit-cw", name="Orbit ↻", icon="🪐", cat="wave", roams=True,
       x="{cx}+0.32*min({ax},{ay})*cos(2*PI*{v}*0.5*t)",
       y="{cy}+0.32*min({ax},{ay})*sin(2*PI*{v}*0.5*t)"),
    _A(aid="orbit-ccw", name="Orbit ↺", icon="🌑", cat="wave", roams=True,
       x="{cx}+0.32*min({ax},{ay})*cos(2*PI*{v}*0.5*t)",
       y="{cy}-0.32*min({ax},{ay})*sin(2*PI*{v}*0.5*t)"),
    _A(aid="orbit-wide", name="Wide Orbit", icon="🛰", cat="wave", roams=True,
       x="{cx}+{ax}*0.45*cos(2*PI*{v}*0.4*t)",
       y="{cy}+{ay}*0.15*sin(2*PI*{v}*0.4*t)"),
    _A(aid="spiral", name="Spiral", icon="🌸", cat="wave", roams=True,
       x="{cx}+(0.36*min({ax},{ay}))*(0.45+0.55*abs(sin(2*PI*{v}*0.15*t)))"
       "*cos(2*PI*{v}*0.6*t)",
       y="{cy}+(0.36*min({ax},{ay}))*(0.45+0.55*abs(sin(2*PI*{v}*0.15*t)))"
       "*sin(2*PI*{v}*0.6*t)"),
    _A(aid="pendulum", name="Pendulum", icon="🕰", cat="wave",
       pre="format=rgba,rotate=a='0.55*sin(2*PI*{v}*0.5*t)':c=0x00000000:ow=iw:oh=ih",
       x="{bx}+{ax}*0.15*sin(2*PI*{v}*0.5*t)", y="{by}"),
    _A(aid="metronome", name="Metronome", icon="⏱", cat="wave",
       pre="format=rgba,rotate=a='-0.5*sin(2*PI*{v}*t)':c=0x00000000:ow=iw:oh=ih",
       x="{bx}", y="{by}"),

    # ---------------- ZOOM & PULSE (6) ----------------
    _A(aid="pulse", name="Pulse", icon="💓", cat="zoom",
       pre="scale=w='iw*(1+0.18*abs(sin(2*PI*{v}*t)))':h=-1:eval=frame",
       x="{bx}", y="{by}"),
    _A(aid="breathe", name="Breathe", icon="🫁", cat="zoom",
       pre="scale=w='iw*(1+0.10*(0.5+0.5*sin(2*PI*{v}*0.35*t)))':h=-1:eval=frame",
       x="{bx}", y="{by}", probe=("motion", 0.3, 1.2)),
    _A(aid="heartbeat", name="Heartbeat", icon="❤️", cat="zoom",
       pre="scale=w='iw*(1+0.16*(pow(abs(sin(2*PI*{v}*t)),6)"
           "+0.6*pow(abs(sin(2*PI*{v}*t+0.9)),24)))':h=-1:eval=frame",
       x="{bx}", y="{by}"),
    _A(aid="zoom-in", name="Zoom In Loop", icon="🔎", cat="zoom",
       pre="scale=w='iw*(0.5+mod(t*{v}*0.25,1))':h=-1:eval=frame",
       x="{cx}", y="{cy}"),
    _A(aid="zoom-out", name="Zoom Out Loop", icon="🔭", cat="zoom",
       pre="scale=w='iw*(1.5-mod(t*{v}*0.25,1))':h=-1:eval=frame",
       x="{cx}", y="{cy}"),
    _A(aid="zoom-bounce", name="Zoom Bounce", icon="🏀", cat="zoom",
       pre="scale=w='iw*(1+0.25*abs(sin(2*PI*{v}*0.45*t)))':h=-1:eval=frame",
       x="{bx}", y="{ay}-{ay}*abs(sin(2*PI*{v}*0.45*t))"),

    # ---------------- ROTATION (6) ----------------
    _A(aid="spin-cw", name="Spin ↻", icon="🎡", cat="rotate",
       pre="format=rgba,rotate=a='2*PI*{v}*0.8*t':c=0x00000000:ow=iw:oh=ih",
       x="{bx}", y="{by}"),
    _A(aid="spin-ccw", name="Spin ↺", icon="🎠", cat="rotate",
       pre="format=rgba,rotate=a='-2*PI*{v}*0.8*t':c=0x00000000:ow=iw:oh=ih",
       x="{bx}", y="{by}"),
    _A(aid="wobble", name="Wobble", icon="🥴", cat="rotate",
       pre="format=rgba,rotate=a='0.35*sin(2*PI*{v}*2*t)':c=0x00000000:ow=iw:oh=ih",
       x="{bx}", y="{by}"),
    _A(aid="tilt", name="Slow Tilt", icon="🫨", cat="rotate",
       pre="format=rgba,rotate=a='0.5*sin(2*PI*{v}*0.3*t)':c=0x00000000:ow=iw:oh=ih",
       x="{bx}", y="{by}", probe=("motion", 0.3, 1.2)),
    _A(aid="tumble", name="Tumble", icon="🤸", cat="rotate", roams=True,
       pre="format=rgba,rotate=a='2*PI*{v}*1.2*t':c=0x00000000:ow=iw:oh=ih",
       x="W-mod(t*{v}*0.30*(W+w),W+w)", y="{by}"),
    _A(aid="orbit-spin", name="Orbit + Spin", icon="💫", cat="rotate", roams=True,
       pre="format=rgba,rotate=a='2*PI*{v}*0.6*t':c=0x00000000:ow=iw:oh=ih",
       x="{cx}+0.32*min({ax},{ay})*cos(2*PI*{v}*0.5*t)",
       y="{cy}+0.32*min({ax},{ay})*sin(2*PI*{v}*0.5*t)"),

    # ---------------- BLINK & STROBE (6) ----------------
    _A(aid="blink", name="Blink", icon="👁", cat="blink",
       enable="lt(mod(t*{v},1),0.55)",
       probe=("gate", 0.20, 0.80)),
    _A(aid="blink-fast", name="Blink Fast", icon="⚡", cat="blink",
       enable="lt(mod(t*{v}*2,1),0.5)",
       probe=("gate", 0.10, 0.35)),
    _A(aid="strobe", name="Strobe", icon="📸", cat="blink",
       enable="lt(mod(t*{v}*4,1),0.4)",
       probe=("gate", 0.02, 0.15)),
    _A(aid="flicker", name="Flicker", icon="🕯", cat="blink",
       enable="lt(mod(t*{v},1),0.5+0.45*sin(13*t))",
       probe=("gate", 0.05, 0.30)),
    _A(aid="ghost", name="Ghost", icon="👻", cat="blink",
       enable="lt(mod(t*{v}*0.5,1),0.85)",
       probe=("gate", 0.50, 1.90)),
    _A(aid="flash2", name="Double Flash", icon="✨", cat="blink",
       enable="lt(mod(t*{v}*1.2,1.2),0.12)+between(mod(t*{v}*1.2,1.2),0.2,0.32)",
       probe=("gate", 0.05, 0.70)),

    # ---------------- FADE (3) ----------------
    _A(aid="fade-once", name="Fade In & Out", icon="🌗", cat="fade", once=True,
       pre="format=rgba,fade=t=in:st=0:d=0.5:alpha=1,"
           "fade=t=out:st={fadeout}:d=0.5:alpha=1",
       x="{bx}", y="{by}", probe=("motion", 0.15, 0.60)),
    _A(aid="fade-in-once", name="Fade In", icon="🌅", cat="fade", once=True,
       pre="format=rgba,fade=t=in:st=0:d=0.6:alpha=1",
       x="{bx}", y="{by}", probe=("motion", 0.10, 0.90)),
    _A(aid="fade-out-once", name="Fade Out", icon="🌇", cat="fade", once=True,
       pre="format=rgba,fade=t=out:st={fadeout}:d=0.6:alpha=1",
       x="{bx}", y="{by}", probe=("motion", 0.15, 2.0)),

    # ---------------- EDGE PATROL (4) ----------------
    _A(aid="edge-follow", name="Edge Follow", icon="🛡", cat="edge", roams=True,
       x="if(lt({S},{ax}),{S},if(lt({S},{ax}+{ay}),{ax},"
         "if(lt({S},2*{ax}+{ay}),2*{ax}+{ay}-{S},0)))",
       y="if(lt({S},{ax}),0,if(lt({S},{ax}+{ay}),{S}-{ax},"
         "if(lt({S},2*{ax}+{ay}),{ay},2*{ax}+2*{ay}-{S})))",
       _s="mod(t*{v}*0.35*({ax}+{ay}),2*({ax}+{ay}))"),
    _A(aid="border-patrol", name="Border Patrol", icon="🚓", cat="edge", roams=True,
       x="if(lt({S},{ax}),{S},if(lt({S},{ax}+{ay}),{ax},"
         "if(lt({S},2*{ax}+{ay}),2*{ax}+{ay}-{S},0)))",
       y="if(lt({S},{ax}),0,if(lt({S},{ax}+{ay}),{S}-{ax},"
         "if(lt({S},2*{ax}+{ay}),{ay},2*{ax}+2*{ay}-{S})))",
       _s="mod(t*{v}*0.15*({ax}+{ay}),2*({ax}+{ay}))",
       probe=("motion", 0.3, 1.5)),
    _A(aid="corners", name="Corner Hops", icon="📐", cat="edge", roams=True,
       probe=("motion", 0.5, 2.1),
       x="if(eq(floor(mod(t*{v}*0.6,4)),0),0,if(eq(floor(mod(t*{v}*0.6,4)),1),{ax},"
         "if(eq(floor(mod(t*{v}*0.6,4)),2),{ax},0)))",
       y="if(eq(floor(mod(t*{v}*0.6,4)),0),0,if(eq(floor(mod(t*{v}*0.6,4)),1),0,"
         "if(eq(floor(mod(t*{v}*0.6,4)),2),{ay},{ay})))"),
    _A(aid="corner-hop-fast", name="Corner Hops Fast", icon="🔀", cat="edge", roams=True,
       probe=("motion", 0.5, 2.1),
       x="if(eq(floor(mod(t*{v}*1.2,4)),0),0,if(eq(floor(mod(t*{v}*1.2,4)),1),{ax},"
         "if(eq(floor(mod(t*{v}*1.2,4)),2),{ax},0)))",
       y="if(eq(floor(mod(t*{v}*1.2,4)),0),0,if(eq(floor(mod(t*{v}*1.2,4)),1),0,"
         "if(eq(floor(mod(t*{v}*1.2,4)),2),{ay},{ay})))"),

    # ---------------- JUMPS & TELEPORTS (4) ----------------
    _A(aid="teleport", name="Teleport", icon="🌀", cat="jump", roams=True,
       probe=("motion", 0.5, 1.5),
       x="{ax}*mod(abs(sin(floor(t*{v}*0.7)*12.9898)*43758.5453),1)",
       y="{ay}*mod(abs(sin(floor(t*{v}*0.7)*78.233)*43758.5453),1)"),
    _A(aid="jumpy-grid", name="Grid Jumps", icon="🔲", cat="jump", roams=True,
       probe=("motion", 0.5, 1.5),
       x="{ax}*floor(mod(abs(sin(floor(t*{v}*0.8)*12.9898)*43758.5453),1)*4)/3",
       y="{ay}*floor(mod(abs(sin(floor(t*{v}*0.8)*78.233)*43758.5453),1)*4)/3"),
    _A(aid="shuffle", name="Shuffle", icon="🃏", cat="jump", roams=True,
       probe=("motion", 0.5, 1.2),
       x="{ax}*floor(mod(abs(sin(floor(t*{v}*1.5)*12.9898)*43758.5453),1)*6)/5",
       y="{ay}*floor(mod(abs(sin(floor(t*{v}*1.5)*78.233)*43758.5453),1)*6)/5"),
    _A(aid="hop", name="Hop", icon="🐇", cat="jump", probe=("motion", 0.3, 0.6),
       x="{bx}+{ax}*0.05*sin(2*PI*{v}*4*t)",
       y="{by}-{ay}*0.20*abs(sin(2*PI*{v}*2*t))"),

    # ---------------- FUN & FX (12) ----------------
    _A(aid="shake", name="Shake", icon="🫨", cat="fun",
       x="{bx}+{m}*0.012*sin(2*PI*{v}*11*t)",
       y="{by}+{m}*0.010*cos(2*PI*{v}*13*t)"),
    _A(aid="vibrate", name="Vibrate", icon="📳", cat="fun",
       x="{bx}+{m}*0.006*sin(2*PI*{v}*28*t)",
       y="{by}+{m}*0.006*cos(2*PI*{v}*31*t)"),
    _A(aid="earthquake", name="Earthquake", icon="🌋", cat="fun",
       x="{bx}+{m}*0.025*sin(2*PI*{v}*9*t+1)",
       y="{by}+{m}*0.020*sin(2*PI*{v}*7*t)"),
    _A(aid="matrix-fall", name="Matrix Fall", icon="🟩", cat="fun", roams=True,
       x="{bx}", y="mod(t*{v}*0.8*(H+h),H+h)-h"),
    _A(aid="rain", name="Rain", icon="🌧", cat="fun", roams=True,
       x="{bx}", y="mod(t*{v}*0.35*(H+h),H+h)-h"),
    _A(aid="rocket", name="Rocket", icon="🚀", cat="fun", roams=True,
       x="{bx}", y="H-mod(t*{v}*0.5*(H+h),H+h)"),
    _A(aid="falling", name="Falling", icon="🍂", cat="fun", roams=True,
       x="{bx}", y="mod(t*{v}*0.5*(H+h),H+h)-h"),
    _A(aid="drift", name="Slow Drift", icon="🛶", cat="fun",
       x="{bx}+{ax}*0.30*sin(2*PI*{v}*t/10)",
       y="{by}+{ay}*0.25*sin(2*PI*{v}*t/13)", probe=("motion", 0.3, 1.6)),
    _A(aid="sway", name="Sway", icon="🌾", cat="fun", probe=("motion", 0.3, 1.6),
       pre="format=rgba,rotate=a='0.25*sin(2*PI*{v}*0.5*t)':c=0x00000000:ow=iw:oh=ih",
       x="{bx}+{ax}*0.08*sin(2*PI*{v}*0.5*t)", y="{by}"),
    _A(aid="nod", name="Nod", icon="🙂", cat="fun", probe=("motion", 0.3, 0.6),
       x="{bx}", y="{by}+{ay}*0.08*abs(sin(2*PI*{v}*0.8*t))"),
    _A(aid="wobble-drop", name="Maple Fall", icon="🍁", cat="fun", roams=True,
       pre="format=rgba,rotate=a='0.4*sin(2*PI*{v}*3*t)':c=0x00000000:ow=iw:oh=ih",
       x="{bx}+{ax}*0.15*sin(2*PI*{v}*0.7*t)",
       y="mod(t*{v}*0.4*(H+h),H+h)-h"),
    _A(aid="butterfly", name="Butterfly", icon="🦋", cat="fun", roams=True,
       pre="scale=w='iw*(1+0.12*(0.5+0.5*sin(2*PI*{v}*2*t)))':h=-1:eval=frame",
       x="{cx}+{ax}*0.30*sin(2*PI*{v}*0.4*t)",
       y="{cy}+{ay}*0.30*sin(2*PI*{v}*0.8*t)"),

    # ---------------- PRO COMBOS (8) ----------------
    _A(aid="dvd-spin", name="DVD Bounce + Spin", icon="💿", cat="combo", roams=True,
       pre="format=rgba,rotate=a='2*PI*{v}*0.4*t':c=0x00000000:ow=iw:oh=ih",
       x="{ax}-abs(mod(t*{v}*0.50*{ax},2*{ax})-{ax})",
       y="{ay}-abs(mod(t*{v}*0.34*{ay},2*{ay})-{ay})"),
    _A(aid="orbit-pulse", name="Orbit + Pulse", icon="🎆", cat="combo", roams=True,
       pre="scale=w='iw*(1+0.15*abs(sin(2*PI*{v}*t)))':h=-1:eval=frame",
       x="{cx}+0.32*min({ax},{ay})*cos(2*PI*{v}*0.5*t)",
       y="{cy}+0.32*min({ax},{ay})*sin(2*PI*{v}*0.5*t)"),
    _A(aid="pulse-drift", name="Pulse + Drift", icon="🎈", cat="combo",
       pre="scale=w='iw*(1+0.15*abs(sin(2*PI*{v}*t)))':h=-1:eval=frame",
       x="{bx}+{ax}*0.25*sin(2*PI*{v}*t/9)",
       y="{by}+{ay}*0.20*sin(2*PI*{v}*t/12)", probe=("motion", 0.3, 1.6)),
    _A(aid="cinematic", name="Cinematic Drift", icon="🎬", cat="combo",
       pre="scale=w='iw*(1+0.15*mod(t*{v}*0.05,1))':h=-1:eval=frame",
       x="{bx}+{ax}*0.18*sin(2*PI*{v}*t/14)",
       y="{by}+{ay}*0.14*sin(2*PI*{v}*t/17)",
       probe=("motion", 0.3, 1.8)),
    _A(aid="marquee-pulse", name="Marquee + Pulse", icon="🎛", cat="combo", roams=True,
       pre="scale=w='iw*(1+0.15*abs(sin(2*PI*{v}*t)))':h=-1:eval=frame",
       x="W-mod(t*{v}*0.30*(W+w),W+w)", y="{by}"),
    _A(aid="spin-pulse", name="Spin + Pulse", icon="⚡", cat="combo",
       pre="format=rgba,rotate=a='2*PI*{v}*0.5*t':c=0x00000000:ow=iw:oh=ih,"
           "scale=w='iw*(1+0.12*abs(sin(2*PI*{v}*t)))':h=-1:eval=frame",
       x="{bx}", y="{by}"),
    _A(aid="shake-pulse", name="Shake + Pulse", icon="💥", cat="combo",
       pre="scale=w='iw*(1+0.10*abs(sin(2*PI*{v}*t)))':h=-1:eval=frame",
       x="{bx}+{m}*0.012*sin(2*PI*{v}*11*t)",
       y="{by}+{m}*0.010*cos(2*PI*{v}*13*t)"),
    _A(aid="glide-fade", name="Glide + Fade", icon="🛸", cat="combo",
       mode="seqexpr", seq="alpha_breathe", seq_params={"lo": 0.35, "hi": 1.0},
       x="{bx}+{ax}*0.20*sin(2*PI*{v}*t/6)",
       y="{by}+{ay}*0.15*sin(2*PI*{v}*t/8)", probe=("motion", 0.3, 1.6)),

    # ---------------- TEXT EFFECTS — frame sequences (23) ----------------
    _A(aid="typewriter", name="Typewriter", icon="⌨️", cat="textfx", mode="seq",
       seq="typewriter", seq_params={"cursor": True}, probe=("motion", 0.25, 0.75)),
    _A(aid="typewriter-fast", name="Typewriter Fast", icon="🏃", cat="textfx",
       mode="seq", seq="typewriter", seq_params={"cursor": True, "period": 1.2},
       probe=("motion", 0.15, 0.45)),
    _A(aid="type-loop", name="Type & Restart", icon="🔁", cat="textfx", mode="seq",
       seq="typewriter", seq_params={"cursor": True, "hold_end": 0.35},
       probe=("motion", 0.25, 0.75)),
    _A(aid="reveal-left", name="Reveal →", icon="▶️", cat="textfx", mode="seq",
       seq="wipe", seq_params={"dir": "lr"}, probe=("motion", 0.2, 0.7)),
    _A(aid="reveal-center", name="Reveal ◀▶", icon="↔️", cat="textfx", mode="seq",
       seq="wipe", seq_params={"dir": "c"}, probe=("motion", 0.2, 0.7)),
    _A(aid="wipe-up", name="Wipe ↑", icon="⬆️", cat="textfx", mode="seq",
       seq="wipe", seq_params={"dir": "bt"}, probe=("motion", 0.6, 0.95)),
    _A(aid="curtain", name="Curtain Fade", icon="🎭", cat="textfx", mode="seq",
       seq="alpha_ramp", seq_params={"lo": 0.05, "hi": 1.0},
       probe=("motion", 0.2, 0.8)),
    _A(aid="pop-in", name="Pop In", icon="🫧", cat="textfx", mode="seq",
       seq="pop_in", probe=("motion", 0.15, 0.8)),
    _A(aid="drop-in", name="Drop In", icon="🪂", cat="textfx", mode="seq",
       seq="drop_in", probe=("motion", 0.15, 0.8)),
    _A(aid="bounce-in", name="Bounce In", icon="🤑", cat="textfx", mode="seq",
       seq="bounce_in", probe=("motion", 0.15, 0.8)),
    _A(aid="slide-in-fade", name="Slide + Fade In", icon="🎯", cat="textfx",
       mode="seq", seq="slide_in_fade", probe=("motion", 0.15, 0.8)),
    _A(aid="elastic", name="Elastic", icon="🦎", cat="textfx", mode="seq",
       seq="elastic", probe=("motion", 0.1, 0.3)),
    _A(aid="jelly", name="Jelly", icon="🍮", cat="textfx", mode="seq",
       seq="jelly", probe=("motion", 0.2, 0.7)),
    _A(aid="color-cycle", name="Color Cycle", icon="🌈", cat="textfx", mode="seq",
       seq="hue_cycle", seq_params={"shift": 360}, probe=("motion", 0.2, 0.7)),
    _A(aid="rainbow", name="Rainbow", icon="🏳️‍🌈", cat="textfx", mode="seq",
       seq="hue_cycle", seq_params={"shift": 360, "period": 1.2},
       probe=("motion", 0.1, 0.4)),
    _A(aid="color-swap", name="Color Swap", icon="🔁", cat="textfx", mode="seq",
       seq="color_swap", seq_params={"period": 1.6},
       probe=("motion", 0.2, 0.8)),
    _A(aid="shimmer", name="Shimmer", icon="✨", cat="textfx", mode="seq",
       seq="shimmer", probe=("motion", 0.2, 0.6)),
    _A(aid="karaoke", name="Karaoke", icon="🎤", cat="textfx", mode="seq",
       seq="karaoke", seq_params={"accent": "#FFD700"},
       probe=("motion", 0.2, 0.7)),
    _A(aid="glow-pulse", name="Glow Pulse", icon="🔮", cat="textfx", mode="seq",
       seq="glow_pulse", seq_params={"amount": 0.6},
       probe=("motion", 0.5, 1.5)),
    _A(aid="neon-flicker", name="Neon Flicker", icon="💡", cat="textfx", mode="seq",
       seq="alpha_flicker", seq_params={"seed": 7},
       probe=("motion", 0.1, 0.5)),
    _A(aid="glitch", name="Glitch", icon="📺", cat="textfx", mode="seq",
       seq="glitch", seq_params={"soft": False}, probe=("motion", 0.75, 1.17)),
    _A(aid="glitch-soft", name="Glitch Soft", icon="🖥", cat="textfx", mode="seq",
       seq="glitch", seq_params={"soft": True}, probe=("motion", 0.75, 1.17)),
    _A(aid="pulse-fade", name="Pulse Fade", icon="🫀", cat="textfx", mode="seq",
       seq="pulse_fade", probe=("motion", 0.25, 0.5)),
]

REGISTRY = {}
for _spec in _SPECS:
    _spec.pop("_s", None)  # internal helper exprs live in _EDGE_S
    REGISTRY[_spec["aid"]] = Anim(**_spec)

# the default "no animation" preset — selectable, but not shown in category lists
REGISTRY["static"] = Anim("static", "Static (no motion)", "📌", "basic",
                          x="{bx}", y="{by}")

# motion helper expressions used by the edge-patrol family
_EDGE_S = {
    "edge-follow": "mod(t*{v}*0.35*({ax}+{ay}),2*({ax}+{ay}))",
    "border-patrol": "mod(t*{v}*0.15*({ax}+{ay}),2*({ax}+{ay}))",
}


def get(aid):
    return REGISTRY.get(aid) or REGISTRY["static"]


def count():
    return len(REGISTRY)


def by_category():
    out = []
    for cat_id, cat_name, cat_icon in CATS:
        items = [a for a in REGISTRY.values() if a.cat == cat_id]
        if items:
            out.append((cat_id, cat_name, cat_icon, items))
    return out


def search(query):
    q = query.strip().lower()
    if not q:
        return []
    return [a for a in REGISTRY.values()
            if q in a.id or q in a.name.lower() or q in a.cat]


def _fmt(template, ctx):
    out = template
    for k, v in ctx.items():
        out = out.replace("{%s}" % k, str(v))
    return out


def build_overlay(anim, s, W, H, wm_w, wm_h, duration, base_xy):
    """Build final overlay options dict for one animation.

    base_xy: (bx, by) anchored position numbers (already computed by caller).
    Returns {"x": str, "y": str, "pre": str|None, "enable": str|None}
    """
    v = float(s.get("anim_speed", 1.0))
    bx, by = base_xy
    fadeout = max(0.2, (duration or 5.0) - 0.55)
    ctx = {
        "v": ("%g" % v),
        "bx": int(round(bx)), "by": int(round(by)),
        "ax": "max(W-w,1)", "ay": "max(H-h,1)",
        "m": "min(W,H)", "cx": "(W-w)/2", "cy": "(H-h)/2",
        "fadeout": ("%.2f" % fadeout),
    }

    x = _fmt(anim.x, ctx) if anim.x else None
    y = _fmt(anim.y, ctx) if anim.y else None
    if anim.id in _EDGE_S:
        s_expr = _fmt(_EDGE_S[anim.id], ctx)
        ctx["S"] = s_expr
        x = _fmt(anim.x, ctx) if anim.x else None
        y = _fmt(anim.y, ctx) if anim.y else None
    pre = _fmt(anim.pre, ctx) if anim.pre else None
    enable = _fmt(anim.enable, ctx) if anim.enable else None
    return {"x": x, "y": y, "pre": pre, "enable": enable}
