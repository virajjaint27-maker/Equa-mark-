#!/usr/bin/env bash
# enable-large-files.sh — raise AquaMark to Telegram's MAXIMUM file sizes
# (2000 MB receive / up to 2000 MB send) by installing the official local
# Bot API server next to the bot.
#
# Usage:    bash deploy/enable-large-files.sh
# Test:     DRY_RUN=1 bash deploy/enable-large-files.sh   (no changes made)
#
# Reads BOT_TOKEN, API_ID and API_HASH from the .env next to the bot.
# Safe to re-run: an already-running server is reused, .env is idempotent.

set -euo pipefail

DRY="${DRY_RUN:-0}"
BOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$BOT_DIR/.env"
PORT="${AQM_PORT:-8081}"
BASE="http://127.0.0.1:$PORT"

say()  { printf '\n== %s\n' "$*"; }
note() { printf '   %s\n' "$*"; }
run()  {
  if [ "$DRY" = 1 ]; then note "[dry-run] $*"; else "$@"; fi
}

if [ "$DRY" = 1 ]; then
  say "DRY RUN — nothing will be executed"
fi

# ---------------------------------------------------------------- .env
[ -f "$ENV_FILE" ] || { echo "ERROR: no .env at $ENV_FILE — create it first."; exit 1; }

env_get() {  # first active (uncommented) value for a key; "" when absent
  # (|| true: with pipefail a no-match grep must not abort set -e)
  grep -E "^$1=" "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '\r"' || true
}

TOKEN="$(env_get BOT_TOKEN)"
API_ID="$(env_get API_ID)"
API_HASH="$(env_get API_HASH)"

missing=0
for v in TOKEN API_ID API_HASH; do
  if [ -z "${!v}" ]; then echo "ERROR: $v is missing/empty in .env"; missing=1; fi
done
if [ "$missing" = 1 ]; then
  echo "Fill BOT_TOKEN, API_ID and API_HASH in .env (API_ID/API_HASH come"
  echo "from my.telegram.org -> API development tools), then re-run."
  exit 1
fi
note "bot dir:  $BOT_DIR"
note "api id:   ${API_ID}"
note "local url: $BASE"

# ------------------------------------------------- 1. the local server
say "Step 1/4 — local Bot API server"
if curl -sf --max-time 3 "$BASE" >/dev/null 2>&1 \
   || docker ps 2>/dev/null | grep -q telegram-bot-api; then
  note "already running — reusing it"
else
  if command -v docker >/dev/null 2>&1; then
    note "Docker found — running the official server as a container"
    run docker run -d --name telegram-bot-api --restart always \
      -p "127.0.0.1:$PORT:8081" \
      -v /opt/telegram-bot-api:/var/lib/telegram-bot-api \
      aiogram/telegram-bot-api:latest \
      --api-id "$API_ID" --api-hash "$API_HASH" --local
  else
    note "no Docker — building the official server from source (~10-20 min)"
    run apt-get update -y
    run apt-get install -y git cmake build-essential g++ zlib1g-dev libssl-dev gperf
    if [ ! -d /opt/telegram-bot-api-src ]; then
      run git clone --recursive --depth 1 \
        https://github.com/tdlib/telegram-bot-api.git /opt/telegram-bot-api-src
    fi
    run mkdir -p /opt/telegram-bot-api-src/build /var/lib/telegram-bot-api
    if [ "$DRY" = 1 ]; then
      note "[dry-run] cmake -DCMAKE_BUILD_TYPE=Release .."
      note "[dry-run] cmake --build . --target install -j2"
    else
      (
        cd /opt/telegram-bot-api-src/build
        cmake -DCMAKE_BUILD_TYPE=Release ..
        cmake --build . --target install -j2
      )
    fi
    if [ "$DRY" = 1 ]; then
      note "[dry-run] write /etc/systemd/system/telegram-bot-api.service"
    else
      cat > /etc/systemd/system/telegram-bot-api.service <<UNIT
[Unit]
Description=Telegram Bot API local server (2000 MB file caps)
After=network.target

[Service]
ExecStart=/usr/local/bin/telegram-bot-api --api-id $API_ID --api-hash $API_HASH --local --http-port $PORT
WorkingDirectory=/var/lib/telegram-bot-api
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT
      systemctl daemon-reload
      systemctl enable --now telegram-bot-api
    fi
  fi
fi

if [ "$DRY" != 1 ]; then
  say "Waiting for the local server to answer"
  ok=""
  for _ in $(seq 1 60); do
    if curl -sf --max-time 3 "$BASE/bot$TOKEN/getMe" >/dev/null 2>&1; then ok=1; break; fi
    sleep 5
  done
  if [ -z "$ok" ]; then
    echo "ERROR: local server not answering on $BASE"
    echo "Docker:   docker logs telegram-bot-api"
    echo "Built:    journalctl -u telegram-bot-api -e"
    exit 1
  fi
  note "server is up"
fi

# ------------------------------------------------- 2. point the bot at it
say "Step 2/4 — pointing AquaMark at the local server"
if grep -qE "^AQM_API_BASE=" "$ENV_FILE"; then
  run sed -i "s|^AQM_API_BASE=.*|AQM_API_BASE=$BASE|" "$ENV_FILE"
elif grep -qE "^#AQM_API_BASE=" "$ENV_FILE"; then
  run sed -i "s|^#AQM_API_BASE=.*|AQM_API_BASE=$BASE|" "$ENV_FILE"
else
  run bash -c "printf '\nAQM_API_BASE=%s\n' '$BASE' >> '$ENV_FILE'"
fi
note "caps auto-raise to 2000 MB in / 1900 MB out"

# ------------------------------------------------- 3. one-time migration
say "Step 3/4 — one-time migration off the cloud API"
note "logging the bot out of api.telegram.org (takes effect in ~10 min)"
run curl -fsS "https://api.telegram.org/bot$TOKEN/logOut" || true

# ------------------------------------------------- 4. restart the bot
say "Step 4/4 — restarting AquaMark"
if systemctl list-unit-files 2>/dev/null | grep -q '^aquamark'; then
  run systemctl restart aquamark
  note "restarted — check: journalctl -u aquamark -f"
else
  note "no 'aquamark' systemd unit found — restart the bot yourself:"
  note "    cd $BOT_DIR && python3 bot.py"
fi

say "DONE — maximum file sizes enabled"
note "receive: up to 2000 MB   send: up to 1900 MB (safe margin)"
note "for the absolute 2000 MB send ceiling add to .env:"
note "    AQM_MAX_OUT_MB=2000"
note "revert anytime: remove AQM_API_BASE from .env, restart, then"
note "    curl $BASE/bot\$TOKEN/logOut"
