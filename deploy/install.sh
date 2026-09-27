#!/usr/bin/env bash
# ============================================================
#  AquaMark — install as a systemd service on a Linux server.
#
#  Usage (from inside the aquamark-bot folder):
#      sudo bash deploy/install.sh
#
#  What it does:
#    1. runs the preflight check (aborts if anything is broken)
#    2. installs deploy/aquamark.service with the correct paths
#    3. enables + starts the service (auto-start on boot,
#       auto-restart on crash)
#
#  Manage it with:
#      systemctl status aquamark
#      systemctl restart aquamark
#      journalctl -u aquamark -f          (live logs)
# ============================================================
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Please run as root:  sudo bash deploy/install.sh"
  exit 1
fi

cd "$(dirname "$0")/.."
AQM_DIR="$(pwd)"
PYTHON="$(command -v python3 || true)"

if [ -z "$PYTHON" ]; then
  echo "ERROR: python3 not found. Install Python 3.8+ first."
  exit 1
fi

echo "=== AquaMark systemd installer ==========================="
echo "  folder : $AQM_DIR"
echo "  python : $PYTHON"
echo

echo "--- preflight check ---"
if ! "$PYTHON" bot.py --check; then
  echo
  echo "Preflight failed — fix the problems above, then re-run."
  exit 1
fi
echo

echo "--- installing service ---"
sed -e "s|__AQM_DIR__|$AQM_DIR|g" \
    -e "s|__PYTHON__|$PYTHON|g" \
    deploy/aquamark.service > /etc/systemd/system/aquamark.service
systemctl daemon-reload
systemctl enable aquamark >/dev/null
systemctl restart aquamark
sleep 3

if systemctl is-active --quiet aquamark; then
  echo "✓ Service installed and running."
  echo
  echo "  live logs   : journalctl -u aquamark -f"
  echo "  status      : systemctl status aquamark"
  echo "  stop/start  : systemctl stop aquamark / systemctl start aquamark"
  echo "  after edit  : systemctl restart aquamark"
  echo "  remove      : systemctl disable --now aquamark && rm /etc/systemd/system/aquamark.service"
else
  echo "✗ Service did not start. Recent logs:"
  journalctl -u aquamark -n 20 --no-pager || true
  exit 1
fi
