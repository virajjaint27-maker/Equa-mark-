# 💧 AquaMark — Professional Telegram Watermark Bot

Watermark photos and videos straight from Telegram, with **107 animations**,
full color control, 15 media tools and a **zero-install bundle**: everything
the bot needs travels inside this folder. On a fresh Linux VPS the only step
is pasting your bot token — no `apt install`, no `pip install`.

```
cp .env.example .env    # paste your BotFather token
python3 bot.py
```

That's it. First start self-checks everything (`python3 bot.py --check` runs
the same preflight manually).

---

## Run it on a Linux server (24/7, recommended)

The bundle targets Linux x86_64 — **no installs at all** (ffmpeg, Pillow and
the Telegram library all ship inside the folder). Only Python 3.8+ is needed,
which every distro has.

```bash
# 1. upload the folder to the server (from your machine):
scp -r aquamark-bot user@your-server:/opt/

# 2. on the server — verify:
cd /opt/aquamark-bot
python3 bot.py --check          # everything should be ✓

# 3. install as a service (auto-start on boot, auto-restart on crash):
sudo bash deploy/install.sh

# 4. watch it work:
journalctl -u aquamark -f
```

No systemd (some OpenVZ/LXC containers)? Any of these work too:

```bash
tmux new -s aqua 'python3 bot.py'          # detach: Ctrl+B then D
# or
nohup python3 bot.py > /dev/null 2>&1 &
```

**Updating:** replace the folder contents, then `systemctl restart aquamark`.
**Windows/RDP instead?** See `WINDOWS-RDP.md` (needs Python + ffmpeg installs).

---

## Requirements

| What | Details |
|---|---|
| OS | Linux x86_64 (any mainstream distro; Ubuntu/Debian/CentOS/Alpine all fine) |
| Python | **3.8 – 3.14** (only the interpreter — nothing else installed system-wide) |
| Internet | outbound HTTPS to Telegram API (api.telegram.org) |
| Disk | ~200 MB free for this folder + job temp files |
| Everything else | bundled: python-telegram-bot, pypdf + fpdf2 (PDF engine), Pillow (wheels for py3.8–3.14), static ffmpeg 7.0.2, 9 fonts |

> **Not x86_64?** (e.g. ARM) The bot still runs — it will prefer a system
> `ffmpeg` if one exists, and as a last resort installs Pillow online once.
> See *Troubleshooting*.

---

## What it does

**Core:** send or forward any photo, video, GIF, sticker, round video note,
image document **or PDF** — the bot returns it watermarked. Albums are processed as a
batch. `/auto` flips instant-fire mode (no confirm button).

**Watermark design:** custom text or a PNG logo, colors by hex / `rgb()` /
148 named colors, two-color gradients, 17 style presets (neon, gold, sticker,
glass…), 9 bundled fonts — including **Devanagari (हिन्दी)**, **Arabic** and
emoji — opacity, outline, shadow, glow, background box/pill, rotation
(−180°…180°), 9-point position grid, tiled anti-crop mode, and dynamic text
variables like `{date} {time} {user} {chat} {count}`.

**PDF watermarking:** every page of a PDF document is stamped with the same
text/logo settings — any page size and orientation, portrait or landscape,
with correct rotation pivots and transparency. The result comes back as a
file, preserving document quality. Password-protected PDFs are rejected with
a friendly message.

**107 animations** (every one pixel-verified by the test suite): DVD bounce
(the classic) + 9 more bounce modes, marquees & sweeps, orbits, figure-8,
lissajous, pendulum, pulse, heartbeat, breathe, zoom, spin, wobble, tumble,
metronome, blink, strobe, flicker, ghost, edge patrol, corner hops, teleports,
shuffle, earthquake, matrix rain, typewriter, glitch, karaoke, shimmer,
color-cycle, pro combos (DVD+spin, orbit+pulse, cinematic…). Speed is
adjustable 0.25×–4×, and `/animation` renders a **live in-chat demo** of each
one before you commit.

**Photos come alive too:** any animation can be burned into a photo as a
looping MP4 (or GIF for ≤20s clips).

**15 media tools** — reply to any media with:
`/stickerize /circle /resize /compress /convert /trim /tomp3 /speed /reverse
/mute /ss /meta /gray /sepia /blurbg`

**Workflow:** interactive settings panels, 2.6s quick previews, live progress
bar with a cancel button, unlimited named profiles, persistent per-user
settings, color swatch confirmations, fair-use rate limiting, personal stats.

**Engineering:** auto audio handling (stream-copy, AAC fallback on exotic
codecs), automatic re-compression when output would exceed Telegram's 50 MB
cap, optional **Telegram Premium custom emojis** (three-level graceful
fallback — see below), rotating file logs, graceful shutdown, and an owner
admin suite (`/broadcast /users /ban /unban`).

---

## Commands

| Command | Purpose |
|---|---|
| `/start` | welcome + feature tour |
| `/help` | quick usage guide |
| `/features` | the full feature list |
| `/animation` | browse all 107 animations with live demos |
| `/color <value>` | set watermark color (hex, `rgb()`, name) |
| `/gradient <c1> <c2>` | two-color gradient text |
| `/logo` / `/setlogo` / `/clearlogo` | use your PNG as the watermark |
| `/set` | interactive settings panels |
| `/reset` | restore defaults |
| `/auto` | toggle instant processing (no confirm step) |
| `/mystats` | your usage stats |
| `/emojiids` | list the custom-emoji IDs the bot can use |
| `/ping` `/about` | health + about |
| *owner only* | `/broadcast /users /ban /unban` |
| *reply to media* | the 15 media tools listed above |

Most settings are also reachable through inline buttons — send anything to
the bot and tap **⚙️ Settings**.

---

## Testing (already run — rerun anytime)

```bash
./run_tests.sh
```

124 tests: unit suites (colors, fonts, text variables, settings, database,
renderer), the PDF engine (stamp-every-page, rotation/opacity internals,
landscape pages, encrypted-PDF rejection), the custom-emoji layer (UTF-16
offsets, button icons, fallback ladder, architecture guards), the video/image
engines (audio copy, WebM re-encode, mute, GIF,
cancel, oversize guard, photo loops, quality presets, tiling), **all 107
animations rendered end-to-end with pixel-level checks** (visibility, motion,
gating, duration), and bot wiring (imports, 45+ handlers, command registry,
callback data limits, `--check`/`--version`).

---

## Project layout

```
bot.py                 entry point (+ --check / --version)
bootstrap.py           zero-install magic: vendored deps, Pillow wheel, ffmpeg
config.py              env/.env configuration
db.py                  SQLite: users, settings, profiles, rate limits
core/
  animations.py        the 107 animation presets (x/y/pre expressions)
  video_engine.py      ffmpeg runner, watermark graphs, progress, cancel
  renderer.py          sprite factory + sequence frame generators (PIL)
  colors.py fonts.py   color parsing / font routing (multi-script + emoji)
  pdf_engine.py        PDF watermarking (pypdf + fpdf2, every page)
  cemoji.py            custom Premium emojis: config, entities, fallbacks
  media.py             media classification + send helpers
  settings.py styles.py textvars.py
handlers/
  pipeline.py          the watermarking pipeline (photo, video, loops, GIF)
  settings_ui.py anim_ui.py tools.py profiles.py admin.py start.py common.py
vendor/                vendored python-telegram-bot + pypdf + fpdf2 (as-is)
wheels/                offline Pillow wheels (cp38–cp314, x86_64)
bin/ffmpeg.xz          static ffmpeg 7.0.2 (extracted once at first start)
assets/fonts/          9 bundled fonts
tests/                 the suite described above
data/                  runtime: settings db, job temp files, logs
```

---

## Custom Premium emojis (optional)

The bot can use **custom Telegram Premium emojis** in its messages and inline
buttons — the animated collectible kind. Because bots may only *send* custom
emojis when they have a **Fragment collectible username** (e.g. `yourbot.t.me`),
the whole feature is wrapped in a fallback ladder and is safe to enable
anywhere:

1. **Level 1** — messages carry `custom_emoji` entities and buttons carry
   icon IDs (full premium look).
2. **Level 2** — if Telegram rejects those (no collectible username, invalid
   IDs), the bot automatically resends the same message with regular
   formatting and no icon buttons.
3. **Level 3** — plain text with Unicode emoji, always works.

The switch lives in `.env` (`AQM_USE_CUSTOM_EMOJIS=1`, default on). Nothing
technical is ever shown to the user — failures are logged to
`data/aquamark.log` and after 3 rejections the bot disables custom emojis for
the session.

**To use your own set:**

1. Make sure the bot's username is a Fragment collectible (auctioned on
   [fragment.com](https://fragment.com)); a regular BotFather username is
   **not** enough — Telegram rejects custom-emoji entities otherwise.
2. Forward any custom emoji to `@missiles_info_bot` (or use your own client)
   to see its ID, then paste real IDs into `CUSTOM_EMOJIS` in
   `core/cemoji.py`, replacing the `CUSTOM_EMOJI_ID_HERE` placeholders.
   ~28 keys cover the whole bot (welcome, tools, processing, buttons…).
3. Restart the bot. `/emojiids` lists what is currently configured.

If you never touch the placeholders the bot simply keeps using the normal
Unicode emoji it already ships with — everything else works unchanged.

---

## Troubleshooting

- **`BOT_TOKEN missing`** — copy `.env.example` to `.env` and paste the token,
  or `export BOT_TOKEN=...` before starting.
- **`ffmpeg` problems on non-x86_64** — install any system ffmpeg
  (`apt install ffmpeg`); the bot prefers it automatically.
- **Pillow on exotic Python/ARM** — first start tries the bundled wheel, then
  a one-time online `pip install --target vendor Pillow`. It never touches
  system packages.
- **Bot can't connect** — check outbound HTTPS to `api.telegram.org:443`
  (some VPS providers block it by default).
- **Logs** — `data/aquamark.log` (rotates at 5 MB).

---

*All media processing happens locally in this folder. Nothing is uploaded
anywhere except the processed result back to Telegram.*
