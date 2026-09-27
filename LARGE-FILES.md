# Handling large files (up to 2000 MB)

## Why the 20 MB wall exists

Every Telegram bot using the **cloud** Bot API is hard-limited by Telegram
itself — no code can work around it:

| Direction | Cloud Bot API | Local Bot API server |
|---|---|---|
| Bot **downloads** (files sent *to* the bot) | **20 MB** | **2000 MB** |
| Bot **uploads** (results sent back) | **50 MB** | **2000 MB** |

The fix for big files is Telegram's official, self-hosted **local Bot API
server**. It runs next to the bot on the same machine; the bot talks to it
instead of api.telegram.org, and the 20/50 MB caps disappear.

It needs the **api_id / api_hash** from <https://my.telegram.org> → "API
development tools" — AquaMark's `.env` already has a place for them.

---

## Setup (Linux server, ~5 minutes)

### 1. Run the local Bot API server

With Docker (easiest):

```bash
docker run -d --name telegram-bot-api --restart always \
  -p 127.0.0.1:8081:8081 \
  -v /opt/telegram-bot-api:/var/lib/telegram-bot-api \
  aiogram/telegram-bot-api:latest \
  --api-id <YOUR_API_ID> --api-hash <YOUR_API_HASH> --local
```

(Use the `API_ID` / `API_HASH` values from your `.env`.)

Without Docker: build from <https://github.com/tdlib/telegram-bot-api>
(instructions in its README) and run
`telegram-bot-api --api-id ... --api-hash ... --local`.

### 2. Point AquaMark at it

Add one line to `.env`:

```env
AQM_API_BASE=http://127.0.0.1:8081
```

That's all — AquaMark automatically raises its receive/send caps to
2000 MB / 1900 MB and routes everything through the local server.

### 3. Migrate the bot session (one-time)

A bot can't be logged into the cloud and the local server at the same time.
Once the local server is running and AquaMark is configured:

```bash
# 1. log the bot out of the CLOUD API (one-time; takes effect after ~10 min):
curl "https://api.telegram.org/bot<TOKEN>/logOut"

# 2. restart the bot (systemd shown; otherwise just re-run it):
sudo systemctl restart aquamark
```

The order matters: `logOut` first, then start the bot against the local
server (it logs in automatically on first request).

> To go back to the cloud API later: remove the `AQM_API_BASE` line, then
> call `curl "http://127.0.0.1:8081/bot<TOKEN>/close"` … and
> `curl "http://127.0.0.1:8081/bot<TOKEN>/logOut"` — after ~10 minutes the
> bot works on api.telegram.org again.

---

## Fine-tuning

| `.env` variable | Default | Meaning |
|---|---|---|
| `AQM_API_BASE` | *(empty = cloud)* | Local Bot API server URL |
| `AQM_API_FILE_BASE` | same as base | Override for file-download URL |
| `AQM_MAX_IN_MB` | 20 (2000 with local) | Max input file size |
| `AQM_MAX_OUT_MB` | 47 (1900 with local) | Max output file size |

The bot still compresses oversized *outputs* automatically — with the local
server, a 300 MB 4K video comes back watermarked and, if needed, re-encoded
to fit under the cap.

## Notes

- The local server needs **~2 GB RAM** free and disk space for its cache
  (`/opt/telegram-bot-api` above). On small VPS instances, watch memory.
- Everything stays on your machine — the local server proxies to Telegram's
  data centers directly, no third party involved.
- RDP/Windows: the Docker command works in Docker Desktop for Windows too;
  use `AQM_API_BASE=http://127.0.0.1:8081` the same way.
