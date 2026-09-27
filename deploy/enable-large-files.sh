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
    if docker ps -a --format '{{.Names}}' 2>/dev/null \
        | grep -qx telegram-bot-api; then
      note "Docker container exists — starting it"
      run docker start telegram-bot-api
    else
      note "Docker found — running the official server as a container"
      run docker run -d --name telegram-bot-api --restart always \
        -p "127.0.0.1:$PORT:8081" \
        -v /opt/telegram-bot-api:/var/lib/telegram-bot-api \
        aiogram/telegram-bot-api:latest \
        --api-id "$API_ID" --api-hash "$API_HASH" --local
    fi
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
  say "Waiting for the local server + bot login"
  note "(after the cloud logOut below, Telegram can take ~10 minutes"
  note " to let the bot into the local server — this may take a while)"
  ok=""
  for i in $(seq 1 180); do   # up to 15 minutes
    body="$(curl -s --max-time 3 "$BASE/bot$TOKEN/getMe" || true)"
    if printf '%s' "$body" | grep -q '"ok"[ ]*:[ ]*true'; then ok=1; break; fi
    if [ $((i % 24)) = 0 ]; then note "still waiting... ($((i * 5 / 60)) min)"; fi
    sleep 5
  done
  if [ -z "$ok" ]; then
    echo "ERROR: local server not answering on $BASE"
    echo "Docker:   docker logs telegram-bot-api"
    echo "Built:    journalctl -u telegram-bot-api -e"
    exit 1
  fi
  note "server is up and the bot is logged in"
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
restarted=""
if systemctl list-unit-files 2>/dev/null | grep -q '^aquamark'; then
  UNIT_DIR="$(systemctl show -p WorkingDirectory --value aquamark 2>/dev/null || true)"
  if [ -n "$UNIT_DIR" ] && [ "$UNIT_DIR" != "$BOT_DIR" ]; then
    say "WARNING — the 'aquamark' service runs from a DIFFERENT folder"
    note "service folder : $UNIT_DIR"
    note "this folder    : $BOT_DIR"
    note "restarting it would NOT use the .env updated by this script!"
    note ""
    note "Fix (point the service at this folder):"
    note "    cd $BOT_DIR && bash deploy/install.sh"
    note "Then: systemctl restart aquamark"
  else
    run systemctl restart aquamark
    note "restarted — check: journalctl -u aquamark -f"
    restarted=1
  fi
fi
if [ -z "$restarted" ]; then
  note "If the bot is running in a terminal (python3 bot.py): stop it"
  note "with Ctrl+C and start it again from THIS folder:"
  note "    cd $BOT_DIR && python3 bot.py"
fi

# ------------------------------------------------- final proof
if [ "$DRY" != 1 ] && [ -f "$BOT_DIR/bot.py" ]; then
  say "Final verification (bot.py --check)"
  ( cd "$BOT_DIR" && python3 bot.py --check ) || true
fi

say "DONE — maximum file sizes enabled"
note "receive: up to 2000 MB   send: up to 1900 MB (safe margin)"
note "for the absolute 2000 MB send ceiling add to .env:"
note "    AQM_MAX_OUT_MB=2000"
note "revert anytime: remove AQM_API_BASE from .env, restart, then"
note "    curl $BASE/bot\$TOKEN/logOut"
