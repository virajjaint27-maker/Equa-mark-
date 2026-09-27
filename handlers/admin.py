"""Owner-only admin commands: broadcast, stats, ban."""
import asyncio
import logging

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

import config
import db
from handlers import common as H

log = logging.getLogger("aquamark.admin")


def register(app):
    app.add_handler(CommandHandler("broadcast", cmd_broadcast))
    app.add_handler(CommandHandler(["stats", "astats"], cmd_stats))
    app.add_handler(CommandHandler("users", cmd_users))
    app.add_handler(CommandHandler("ban", cmd_ban))
    app.add_handler(CommandHandler("unban", cmd_unban))


def _owner_check(update):
    if not config.OWNER_ID:
        return False
    return H.user_id_of(update) == config.OWNER_ID


async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _owner_check(update):
        await update.message.reply_text(
            "🔒 Owner only. Set OWNER_ID in .env to enable admin commands.")
        return
    msg = update.message
    src = msg.reply_to_message
    text = " ".join(context.args or [])
    if src is None and not text:
        await msg.reply_text(
            "📢 Usage: reply to a message with /broadcast, or "
            "/broadcast <text>")
        return
    ids = db.all_user_ids()
    status = await msg.reply_text("📢 Broadcasting to %d users…" % len(ids))
    sent = failed = 0
    for i, uid in enumerate(ids):
        try:
            if src is not None:
                await context.bot.copy_message(
                    chat_id=uid, from_chat_id=msg.chat_id,
                    message_id=src.message_id)
            else:
                await context.bot.send_message(chat_id=uid, text=text)
            sent += 1
        except Exception:
            failed += 1
        if i % 25 == 24:
            await asyncio.sleep(1.0)
            try:
                await status.edit_text(
                    "📢 %d/%d…" % (i + 1, len(ids)))
            except Exception:
                pass
    try:
        await status.edit_text("✅ Broadcast done: %d sent, %d failed." %
                               (sent, failed))
    except Exception:
        await msg.reply_text("✅ Broadcast done: %d sent, %d failed." %
                             (sent, failed))


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _owner_check(update):
        return await _personal_stats(update, context)
    g = db.global_stats()
    await update.message.reply_text(
        "📊 <b>Global stats</b>\n\n"
        "👥 Users: <b>%d</b> (%d active)\n"
        "💧 Media watermarked: <b>%d</b>\n"
        "🎞 Animations available: <b>%d</b>" %
        (g["users"], g["active"], g["processed"],
         __import__("core.animations", fromlist=["count"]).count()),
        parse_mode="HTML")


async def _personal_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = H.user_id_of(update)
    st = db.user_stats(uid)
    await update.message.reply_text(
        "📊 <b>Your stats</b>\n\n💧 Media watermarked: <b>%d</b>" %
        st["processed"], parse_mode="HTML")


async def cmd_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _owner_check(update):
        return
    import time as _t
    rows = []
    with db._conn() as c:
        for r in c.execute(
                "SELECT user_id, first_name, username, processed, is_banned "
                "FROM users ORDER BY processed DESC LIMIT 25"):
            name = r["first_name"] or "?"
            if r["username"]:
                name += " (@%s)" % r["username"]
            rows.append("%s · %d%s" % (H.esc(name), r["processed"],
                                       " · 🚫" if r["is_banned"] else ""))
    await update.message.reply_text(
        "👥 <b>Top users</b>\n" + "\n".join(rows), parse_mode="HTML")


async def cmd_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _owner_check(update):
        return
    if not context.args or not context.args[0].lstrip("-").isdigit():
        await update.message.reply_text("Usage: /ban <user_id>")
        return
    db.set_banned(int(context.args[0]), True)
    await update.message.reply_text("🚫 Banned %s" % context.args[0])


async def cmd_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _owner_check(update):
        return
    if not context.args or not context.args[0].lstrip("-").isdigit():
        await update.message.reply_text("Usage: /unban <user_id>")
        return
    db.set_banned(int(context.args[0]), False)
    await update.message.reply_text("✅ Unbanned %s" % context.args[0])
