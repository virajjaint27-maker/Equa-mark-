"""Interactive settings panels (inline keyboards) for every watermark option."""
import logging

from telegram import Update
from telegram.ext import CallbackContext, ContextTypes

import config
from core import colors
from core import fonts as F
from core import styles as ST
from core.animations import REGISTRY as ANIMS
from core.animations import get as get_anim
from core.settings import DEFAULTS
from handlers import common as H
from handlers import anim_ui

log = logging.getLogger("aquamark.settings")

# param -> (title, icon, kind, meta)
PARAMS = {
    "text":       ("Watermark text", "✏️", "action", {}),
    "color":      ("Text color", "🎨", "color", {}),
    "color2":     ("Gradient 2nd color", "🌈", "color", {"optional": True}),
    "style":      ("Style preset", "✨", "choice", {}),
    "font":       ("Font", "🔤", "choice", {}),
    "size_pct":   ("Size", "🅰️", "step", {"min": 1, "max": 40, "step": 1,
                                          "big": 5, "unit": "%"}),
    "opacity":    ("Opacity", "💧", "step", {"min": 0.05, "max": 1.0,
                                             "step": 0.05, "big": 0.25,
                                             "unit": ""}),
    "stroke_w":   ("Outline width", "🔲", "step", {"min": 0, "max": 15,
                                                   "step": 0.5, "big": 3,
                                                   "unit": "%"}),
    "stroke_color": ("Outline color", "▪️", "color", {}),
    "shadow":     ("Shadow strength", "🌙", "step", {"min": 0, "max": 100,
                                                     "step": 5, "big": 20,
                                                     "unit": ""}),
    "shadow_color": ("Shadow color", "🌑", "color", {}),
    "glow":       ("Glow strength", "💡", "step", {"min": 0, "max": 100,
                                                   "step": 5, "big": 20,
                                                   "unit": ""}),
    "glow_color": ("Glow color", "🔆", "color", {"optional": True}),
    "position":   ("Position", "📍", "choice", {}),
    "margin":     ("Margin", "📐", "step", {"min": 0, "max": 25, "step": 1,
                                            "big": 5, "unit": "%"}),
    "rotation":   ("Rotation", "🔄", "step", {"min": -180, "max": 180,
                                              "step": 5, "big": 45,
                                              "unit": "°"}),
    "animation":  ("Animation", "🎞", "action", {}),
    "anim_speed": ("Animation speed", "⏩", "step", {"min": 0.25, "max": 4.0,
                                                     "step": 0.25, "big": 1.0,
                                                     "unit": "×"}),
    "loop_secs":  ("Photo loop length", "⏱", "step", {"min": 2, "max": 15,
                                                       "step": 1, "big": 2,
                                                       "unit": "s"}),
    "out_format": ("Output format", "📁", "choice", {}),
    "quality":    ("Render quality", "⚙️", "choice", {}),
    "keep_audio": ("Keep audio", "🔊", "toggle", {}),
    "send_as":    ("Send result as", "📤", "choice", {}),
    "auto_mode":  ("Auto-process media", "🤖", "toggle", {}),
}

MAIN_ROWS = [
    ("text", "wm_type", "color"),
    ("color2", "style", "font"),
    ("size_pct", "opacity", "stroke_w"),
    ("shadow", "glow", "position"),
    ("margin", "rotation", "animation"),
    ("anim_speed", "loop_secs", "out_format"),
    ("quality", "keep_audio", "send_as"),
    ("auto_mode", None, None),
]


def _choices(param):
    if param == "style":
        return [(sid, "%s %s" % (e[1], e[0])) for sid, e in ST.STYLES.items()]
    if param == "font":
        return [(fid, e[1]) for fid, e in F.FONTS.items()
                if fid != "emoji"]
    if param == "position":
        return [(p, config.POSITION_NAMES[p]) for p in config.POSITIONS]
    if param == "out_format":
        return [("auto", "Auto (recommended)"), ("mp4", "MP4 video"),
                ("gif", "GIF")]
    if param == "quality":
        return [("low", "Fast (smaller)"), ("medium", "Balanced"),
                ("high", "High (recommended)"), ("ultra", "Ultra (slow)")]
    if param == "send_as":
        return [("auto", "Auto"), ("video", "Video"),
                ("document", "File / document")]
    if param == "wm_type":
        return [("text", "Text watermark"), ("logo", "Logo image")]
    return []


def _fmt_value(param, s):
    v = s.get(param)
    if param in ("color", "color2", "stroke_color", "shadow_color",
                 "glow_color", "box_color"):
        return str(v) if v else "auto"
    if param == "animation":
        a = get_anim(v)
        return "%s %s" % (a.icon, a.name)
    if param == "text":
        return '"%s"' % (v[:40] if v else "— not set —")
    if param in ("keep_audio", "auto_mode", "tile", "box"):
        return "on" if v else "off"
    if param == "style":
        e = ST.STYLES.get(v)
        return "%s %s" % (e[1], e[0]) if e else str(v)
    if param == "font":
        e = F.FONTS.get(v)
        return e[1] if e else str(v)
    if param == "position":
        return config.POSITION_NAMES.get(v, str(v))
    if isinstance(v, float):
        return ("%g" % v) + PARAMS.get(param, (None, None, None, {}))[3].get(
            "unit", "")
    return str(v)


def _summary(s):
    lines = []
    anim = get_anim(s["animation"])
    lines.append("✏️ Text: %s" % _fmt_value("text", s))
    lines.append("🎨 Color: %s%s" % (
        s["color"], " → %s" % s["color2"] if s["color2"] else ""))
    lines.append("🔤 Font: %s · 🅰 %g%%" % (F.FONTS.get(
        s["font"], ("?",))[0], s["size_pct"]))
    lines.append("📍 %s · 🎞 %s %s" % (
        config.POSITION_NAMES.get(s["position"], s["position"]),
        anim.icon, "static" if anim.id == "static" else anim.name))
    if s["tile"]:
        lines.append("🧩 Tiled watermark (anti-crop)")
    lines.append("🤖 Auto-process: %s" % ("on" if s["auto_mode"] else "off"))
    return "\n".join(lines)


# ------------------------------------------------------------- panels

def main_menu(s):
    rows = []
    for row in MAIN_ROWS:
        r = []
        for param in row:
            if param is None:
                continue
            spec = PARAMS.get(param)
            if not spec:
                continue
            label = "%s %s" % (spec[1], _short(spec[0], s, param))
            r.append(H.btn(label, "st:go:%s" % param))
        rows.append(r)
    rows.append([
        H.btn("Box & Tiling", "st:go:boxpanel", ce="settings"),
        H.btn("Profiles", "pf:menu", ce="eyes"),
    ])
    rows.append([H.btn("Reset all", "st:reset", ce="warning")])
    text = ("[[settings]] <b>Watermark Settings</b>\n\n%s\n\n"
            "[[info]] Tip: send me any photo, video or PDF and I'll "
            "watermark it with these exact settings." % _summary(s))
    return text, H.kb(rows)


def _short(title, s, param):
    v = _fmt_value(param, s)
    if len(v) > 14:
        v = v[:13] + "…"
    return v


def param_panel(param, s):
    spec = PARAMS.get(param)
    if not spec:
        return main_menu(s)
    title, icon, kind, meta = spec
    cur = _fmt_value(param, s)
    head = "%s <b>%s</b>\n\nCurrent: <b>%s</b>" % (icon, title, cur)

    if param == "animation":
        return anim_ui.menu_keyboard(s)

    if kind == "step":
        lo, hi, st_, big = meta["min"], meta["max"], meta["step"], meta["big"]
        rows = [[H.btn("−%g" % big, "st:adj:%s:-%g" % (param, big)),
                 H.btn("−%g" % st_, "st:adj:%s:-%g" % (param, st_)),
                 H.btn("+%g" % st_, "st:adj:%s:%g" % (param, st_)),
                 H.btn("+%g" % big, "st:adj:%s:%g" % (param, big))]]
        rows.append([H.btn("✏️ Type a value", "st:txt:%s" % param)])
        return head + "\n\nRange: %g … %g%s" % (lo, hi, meta["unit"]), H.kb(
            rows + _back_row())

    if kind == "choice":
        rows = []
        pair = []
        for val, label in _choices(param):
            mark = "● " if str(s.get(param)) == str(val) else "○ "
            pair.append(H.btn(mark + label, "st:chc:%s:%s" % (param, val)))
            if len(pair) == 2:
                rows.append(pair)
                pair = []
        if pair:
            rows.append(pair)
        return head, H.kb(rows + _back_row())

    if kind == "toggle":
        on = bool(s.get(param))
        rows = [[H.btn("✅ On" if not on else "🔘 On",
                       "st:tgl:%s" % param),
                 H.btn("❌ Off" if on else "🔘 Off",
                       "st:tgl:%s" % param)]]
        return head, H.kb(rows + _back_row())

    if kind == "color":
        rows = [[H.btn("🎨 Send a color", "st:clr:%s" % param)]]
        if meta.get("optional") and s.get(param):
            rows.append([H.btn("🚫 Remove", "st:clroff:%s" % param)])
        text = (head + "\n\nAccepted: <code>#RRGGBB</code>, "
                "<code>rgb(255,0,0)</code>, or names like <code>gold</code>, "
                "<code>deep pink</code>.\nGradients: send two colors like "
                "<code>#fff&gt;#f00</code> (text color only).")
        return text, H.kb(rows + _back_row())

    if param == "text":
        rows = [[H.btn("✏️ Send new text", "st:txt:text")]]
        if s.get("wm_type") != "text":
            rows.insert(0, [H.btn("➡️ Use text watermark",
                                  "st:chc:wm_type:text")])
        text = (head + "\n\nMulti-line? Send several lines at once.\n"
                "Dynamic values: {date} {time} {year} {user} {username} "
                "{chat} {count}")
        return text, H.kb(rows + _back_row())

    return head, H.kb(_back_row())


def box_panel(s):
    head = ("📦 <b>Background box & Tiling</b>\n\n"
            "Box: <b>%s</b>%s\n"
            "Box color: <b>%s</b> · opacity <b>%g</b> · pad <b>%g%%</b> · "
            "radius <b>%g%%</b>\n"
            "Tiling: <b>%s</b> · gap <b>%g%%</b> · angle <b>%g°</b>"
            % ("on" if s["box"] else "off",
               "" if s["box"] else " (disabled)",
               s["box_color"], s["box_opacity"], s["box_pad"], s["box_radius"],
               "on" if s["tile"] else "off", s["tile_gap"], s["tile_angle"]))
    rows = [
        [H.btn("🔘 Box: %s" % ("on" if s["box"] else "off"), "st:tgl:box"),
         H.btn("🔘 Tile: %s" % ("on" if s["tile"] else "off"), "st:tgl:tile")],
        [H.btn("🎨 Box color", "st:clr:box_color"),
         H.btn("💧 Box opacity %g" % s["box_opacity"], "st:go:box_opacity")],
        [H.btn("📐 Box pad %g%%" % s["box_pad"], "st:go:box_pad"),
         H.btn("⭕ Box radius %g%%" % s["box_radius"], "st:go:box_radius")],
        [H.btn("↔️ Tile gap %g%%" % s["tile_gap"], "st:go:tile_gap"),
         H.btn("📐 Tile angle %g°" % s["tile_angle"], "st:go:tile_angle")],
    ]
    if s["tile"]:
        head += "\n\nℹ️ Tiling repeats your watermark across the whole frame " \
                "(anti-crop). Motion is limited to a gentle drift while tiled."
    return head, H.kb(rows + _back_row())


def reset_panel():
    return ("♻️ <b>Reset all settings?</b>\n\n"
            "This restores every option to its default. Your saved profiles "
            "are kept."), H.kb([
        [H.btn("✅ Yes, reset", "st:rst:yes"), H.btn("❌ Cancel", "st:main")]])


def _back_row():
    return [[H.btn("◀️ Settings", "st:main")]]


# ------------------------------------------------------------- callbacks

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data or ""
    uid = H.user_id_of(update)
    await H.answer_safely(query)
    s = H.settings_of(context, uid)
    parts = data.split(":")

    # st:go:<param>
    if parts[1] == "go":
        param = parts[2]
        if param == "boxpanel":
            text, markup = box_panel(s)
        elif param in PARAMS:
            text, markup = param_panel(param, s)
        else:
            text, markup = main_menu(s)
        return await H.safe_edit(query, text, markup, parse_mode="HTML")

    if parts[1] == "main":
        text, markup = main_menu(s)
        return await H.safe_edit(query, text, markup, parse_mode="HTML")

    if parts[1] == "adj":
        param, amount = parts[2], float(parts[3])
        meta = PARAMS[param][3]
        newv = max(meta["min"], min(meta["max"],
                                    round(float(s[param]) + amount, 2)))
        s[param] = newv
        s = H.save_settings(context, uid, s)
        text, markup = param_panel(param, s)
        return await H.safe_edit(query, text, markup, parse_mode="HTML")

    if parts[1] == "chc":
        param, val = parts[2], parts[3]
        if param == "wm_type":
            s["wm_type"] = val
        else:
            s[param] = val
        s = H.save_settings(context, uid, s)
        text, markup = param_panel(param, s)
        return await H.safe_edit(query, text, markup, parse_mode="HTML")

    if parts[1] == "tgl":
        param = parts[2]
        if param == "box":
            s["box"] = not s["box"]
        elif param == "tile":
            s["tile"] = not s["tile"]
        else:
            s[param] = not bool(s[param])
        s = H.save_settings(context, uid, s)
        if param in ("box", "tile"):
            text, markup = box_panel(s)
        else:
            text, markup = param_panel(param, s)
        return await H.safe_edit(query, text, markup, parse_mode="HTML")

    if parts[1] == "clr":
        H.set_await(context, "color", {"param": parts[2]})
        await H.reply(query.message, 
            "🎨 Send me the new color for <b>%s</b>:\n"
            "<code>#FF6600</code> · <code>rgb(30,144,255)</code> · "
            "<code>gold</code> — or /cancel" % PARAMS[parts[2]][0],
            parse_mode="HTML")
        return

    if parts[1] == "clroff":
        param = parts[2]
        s[param] = ""
        s = H.save_settings(context, uid, s)
        text, markup = param_panel(param, s)
        return await H.safe_edit(query, text, markup, parse_mode="HTML")

    if parts[1] == "txt":
        param = parts[2]
        H.set_await(context, "value", {"param": param})
        await H.reply(query.message, 
            "✏️ Send me the new value for <b>%s</b> — or /cancel" %
            PARAMS[param][0], parse_mode="HTML")
        return

    if parts[1] == "reset":
        text, markup = reset_panel()
        return await H.safe_edit(query, text, markup, parse_mode="HTML")

    if parts[1] == "rst" and parts[2] == "yes":
        s = H.save_settings(context, uid, dict(DEFAULTS))
        text, markup = main_menu(s)
        return await H.safe_edit(query, "♻️ Settings reset to defaults.\n\n" +
                                 text, markup, parse_mode="HTML")


# ------------------------------------------------------------- text input

async def handle_await(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process a plain-text message when the bot is awaiting input."""
    msg = update.message
    uid = H.user_id_of(update)
    state = H.pop_await(context)
    if not state:
        return False
    s = H.settings_of(context, uid)
    raw = (msg.text or "").strip()
    if raw.lower() in ("/cancel", "cancel"):
        await H.reply(msg, "👌 Cancelled.")
        return True

    kind = state.get("kind")
    if kind == "color":
        param = state["extra"]["param"]
        try:
            if param == "color" and ">" in raw:
                c1, c2 = colors.parse_gradient(raw)
                s["color"] = colors.to_hex(c1)
                s["color2"] = colors.to_hex(c2)
            else:
                c = colors.parse_color(raw)
                s[param] = colors.to_hex(c)
        except colors.ColorError as exc:
            H.set_await(context, kind, state["extra"])  # keep waiting
            await H.reply(msg, "❌ %s\nTry again or send /cancel." % exc)
            return True
        s = H.save_settings(context, uid, s)
        from core import cemoji
        await cemoji.reply_photo(
            msg, __import__("io").BytesIO(
                __import__("core.renderer", fromlist=["swatch"]).swatch(
                    colors.parse_color(s[param]), s[param]).tobytes()
            ) if False else _swatch_bytes(colors.parse_color(s[param]),
                                          s[param]),
            caption="✅ %s set to <b>%s</b>" %
                    (PARAMS[param][0], s[param]),
            parse_mode="HTML")
        return True

    if kind == "value":
        param = state["extra"]["param"]
        if param == "text":
            s["text"] = raw[:200]
            s["wm_type"] = "text"
        else:
            meta = PARAMS[param][3]
            try:
                v = float(raw.replace(",", "."))
            except ValueError:
                H.set_await(context, kind, state["extra"])
                await H.reply(msg, "❌ That's not a number. Try again or "
                                     "/cancel")
                return True
            s[param] = max(meta["min"], min(meta["max"], v))
        s = H.save_settings(context, uid, s)
        text, markup = param_panel(param, s)
        await H.reply(msg, "✅ Updated:\n\n" + text, reply_markup=markup,
                             parse_mode="HTML")
        return True

    if kind == "anim_search":
        query = raw[:40]
        return await anim_ui.send_search(update, context, query)

    if kind == "profile_name":
        import db
        db_ok = db.save_profile(uid, raw[:40], s)
        await H.reply(msg, "💾 Profile <b>%s</b> saved!" % H.esc(raw[:40])
                             if db_ok else "❌ Could not save profile.",
                             parse_mode="HTML")
        return True

    return False


def _swatch_bytes(rgba, label):
    import io
    from core import renderer
    buf = io.BytesIO()
    renderer.swatch(rgba, label).save(buf, format="PNG")
    buf.seek(0)
    return buf


async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = H.user_id_of(update)
    s = H.settings_of(context, uid)
    text, markup = main_menu(s)
    await H.branded_photo(update.message, config.SETTINGS_IMG, text,
                          reply_markup=markup, parse_mode="HTML")


# ------------------------------------------------------------- quick cmds

QUICK = {
    "style": ("style", "choice"),
    "font": ("font", "choice"),
    "size": ("size_pct", "step"),
    "opacity": ("opacity", "step"),
    "position": ("position", "choice"),
    "rotation": ("rotation", "step"),
    "speed": ("anim_speed", "step"),
}


async def cmd_quick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Quick setters: /size 12 · /position br · /style neon · /font bebas"""
    cmd = update.message.text.split()[0].lstrip("/").split("@")[0].lower()
    spec = QUICK.get(cmd)
    if not spec:
        return
    param, kind = spec
    uid = H.user_id_of(update)
    s = H.settings_of(context, uid)
    arg = " ".join(context.args or []).strip()

    if arg:
        if kind == "choice":
            val = None
            if param == "style":
                arg_l = arg.lower().replace(" ", "-")
                for cand in (arg_l, arg_l.replace("-", "")):
                    if cand in ST.STYLES:
                        val = cand
                        break
            elif param == "font":
                arg_l = arg.lower().replace(" ", "-")
                for cand in (arg_l, arg_l.replace("-", "")):
                    if cand in F.FONTS:
                        val = cand
                        break
            elif param == "position":
                val = arg.lower() if arg.lower() in config.POSITIONS else None
            if val is None:
                await H.reply(update.message, 
                    "❌ Unknown %s “%s”. Send /%s without arguments to see "
                    "options." % (param, arg, cmd))
                return
            s[param] = val
        else:
            meta = PARAMS[param][3]
            try:
                v = float(arg.replace(",", ".").replace("x", "")
                          .replace("%", "").replace("°", ""))
            except ValueError:
                await H.reply(update.message, "❌ Send a number, e.g. "
                                                "/%s 12" % cmd)
                return
            s[param] = max(meta["min"], min(meta["max"], v))
        s = H.save_settings(context, uid, s)
        await H.reply(update.message, 
            "✅ %s set to <b>%s</b>" % (PARAMS[param][0],
                                        _fmt_value(param, s)),
            parse_mode="HTML")
        return

    text, markup = param_panel(param, s)
    await H.reply(update.message, text, reply_markup=markup,
                                    parse_mode="HTML")


def register(app):
    from telegram.ext import CommandHandler, CallbackQueryHandler
    app.add_handler(CommandHandler(["settings", "set"], cmd_settings))
    for cmdname in QUICK:
        app.add_handler(CommandHandler(cmdname, cmd_quick))
    app.add_handler(CallbackQueryHandler(on_callback, pattern=r"^st:"))
