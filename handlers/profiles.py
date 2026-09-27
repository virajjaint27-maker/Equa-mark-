"""Watermark profiles: save/load named looks."""
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

import db
from handlers import common as H


def register(app):
    from telegram.ext import CallbackQueryHandler
    app.add_handler(CommandHandler(["profiles", "plist"], cmd_profiles))
    app.add_handler(CommandHandler(["profile"], cmd_profiles))
    app.add_handler(CallbackQueryHandler(on_callback, pattern=r"^pf:"))


def _menu(context, uid):
    s = H.settings_of(context, uid)
    profs = db.list_profiles(uid)
    rows = []
    for p in profs[:10]:
        rows.append([
            H.btn("📁 %s" % p["name"], "pf:load:%d" % p["id"]),
            H.btn("🗑", "pf:del:%d" % p["id"]),
        ])
    rows.append([H.btn("💾 Save current settings", "pf:save")])
    rows.append([H.btn("◀️ Settings", "st:main")])
    if profs:
        text = ("👤 <b>Profiles</b>\n\nTap a profile to apply it. 🗑 deletes."
                "\n\nCurrent look: <b>%s</b>" % H.esc(
                    s.get("text") or "(no text)"))
    else:
        text = ("👤 <b>Profiles</b>\n\nNo profiles yet. Save your current "
                "settings as a named profile — great for switching between "
                "brands!")
    return text, H.kb(rows)


async def cmd_profiles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = H.user_id_of(update)
    text, markup = _menu(context, uid)
    await H.reply(update.message, text, reply_markup=markup,
                                    parse_mode="HTML")


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = H.user_id_of(update)
    parts = (query.data or "").split(":")
    s = H.settings_of(context, uid)

    if parts[1] == "menu":
        await H.answer_safely(query)
        text, markup = _menu(context, uid)
        return await H.safe_edit(query, text, markup, parse_mode="HTML")

    if parts[1] == "save":
        await H.answer_safely(query)
        H.set_await(context, "profile_name")
        await H.reply(query.message, 
            "💾 Send me a name for this profile (e.g. <code>insta-brand</code>"
            ") — or /cancel", parse_mode="HTML")
        return

    if parts[1] == "load":
        await H.answer_safely(query, "Loading…")
        loaded = db.load_profile(uid, parts[2])
        if not loaded:
            return await H.answer_safely(query, "Profile not found")
        s = H.save_settings(context, uid, loaded)
        text, markup = _menu(context, uid)
        return await H.safe_edit(
            query, "✅ Profile applied!\n\n" + text, markup, parse_mode="HTML")

    if parts[1] == "del":
        await H.answer_safely(query)
        db.delete_profile(uid, parts[2])
        text, markup = _menu(context, uid)
        return await H.safe_edit(query, "🗑 Deleted.\n\n" + text, markup,
                                 parse_mode="HTML")
