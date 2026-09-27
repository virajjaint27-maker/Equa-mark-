"""Central configuration for AquaMark. Environment first, .env as fallback."""
import logging
import logging.handlers
import os

ROOT = os.path.dirname(os.path.abspath(__file__))


def _load_dotenv(path):
    """Tiny .env loader (no dependency). Existing env vars always win."""
    if not os.path.isfile(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except OSError:
        pass


_load_dotenv(os.path.join(ROOT, ".env"))

VERSION = "1.2.4"
BRAND = "AquaMark"
TAGLINE = "Professional Watermark Studio"

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()

# --- Telegram app credentials (optional; from my.telegram.org) ---
# The Bot API only needs BOT_TOKEN. API_ID/API_HASH are MTProto-app
# credentials kept here for optional advanced integrations.
API_ID = None
_api_id_raw = os.environ.get("API_ID", "").strip()
if _api_id_raw:
    try:
        API_ID = int(_api_id_raw)
    except ValueError:
        API_ID = None
API_HASH = os.environ.get("API_HASH", "").strip()

OWNER_ID = None
_owner_raw = os.environ.get("OWNER_ID", "").strip()
if _owner_raw:
    try:
        OWNER_ID = int(_owner_raw)
    except ValueError:
        OWNER_ID = None

LOG_LEVEL = os.environ.get("AQM_LOG_LEVEL", "INFO").upper()

# --- Telegram Premium custom emojis ---------------------------------------
# Master switch. When True (and real emoji IDs are configured in
# core/cemoji.py), messages use custom_emoji entities with automatic
# fallback to the plain Unicode emoji for everyone else. When False or
# before IDs are pasted, only the normal Unicode emoji are used.
USE_CUSTOM_EMOJIS = os.environ.get(
    "AQM_USE_CUSTOM_EMOJIS", "1").strip().lower() in ("1", "true", "yes", "on")

# --- optional local Bot API server (raises file size caps dramatically) ---
# Cloud Bot API hard limits: 20 MB download / 50 MB upload per file.
# A self-hosted local Bot API server (see LARGE-FILES.md) raises both to
# 2000 MB. Point the bot at it with AQM_API_BASE, e.g.:
#   AQM_API_BASE=http://127.0.0.1:8081
# File-download URLs default to the same host automatically.
BOT_API_BASE = os.environ.get("AQM_API_BASE", "").strip().rstrip("/")
BOT_API_FILE_BASE = os.environ.get("AQM_API_FILE_BASE", "").strip().rstrip("/")

# --- limits (MB, env-tunable; defaults auto-raise with a local server) ---
def _int_env(name, default):
    try:
        return int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default

_DEFAULT_IN_MB = 2000 if BOT_API_BASE else 20
_DEFAULT_OUT_MB = 1900 if BOT_API_BASE else 47

# --- paths ---
DATA_DIR = os.path.join(ROOT, "data")
TMP_DIR = os.path.join(DATA_DIR, "tmp")
LOG_DIR = os.path.join(ROOT, "logs")
LOG_FILE = os.path.join(LOG_DIR, "bot.log")
DB_PATH = os.path.join(DATA_DIR, "aquamark.db")
FONT_DIR = os.path.join(ROOT, "assets", "fonts")
LOGO_DIR = os.path.join(DATA_DIR, "logos")
BRAND_IMG = os.path.join(ROOT, "assets", "branding", "welcome.png")
PROCESS_IMG = os.path.join(ROOT, "assets", "branding", "process.jpg")
SETTINGS_IMG = os.path.join(ROOT, "assets", "branding", "settings.jpg")
HELP_IMG = os.path.join(ROOT, "assets", "branding", "help.jpg")

# small-caps UI font ("Travel vote" style) on all bot text; AQM_UI_FONT=0
# restores the plain alphabet
USE_UI_FONT = os.environ.get(
    "AQM_UI_FONT", "1").strip().lower() in ("1", "true", "yes", "on")
WELCOME_CAPTION = "💧 %s — %s" % (BRAND, TAGLINE)
for _d in (DATA_DIR, TMP_DIR, LOG_DIR, LOGO_DIR):
    os.makedirs(_d, exist_ok=True)

# --- limits ---
MAX_IN_SIZE = _int_env("AQM_MAX_IN_MB", _DEFAULT_IN_MB) * 1024 * 1024
MAX_OUT_SIZE = _int_env("AQM_MAX_OUT_MB", _DEFAULT_OUT_MB) * 1024 * 1024
MAX_BATCH = 10                          # media group items processed per album
MAX_VIDEO_WARN_SECONDS = 900            # longer than this -> warn about time
RATE_JOBS_PER_HOUR = 15                 # per-user watermark jobs
PREVIEW_SECONDS = 2.6                   # live demo / preview render length
SEQ_FPS = 12                            # frame-sequence animation fps
MAX_FONT_PCT = 40.0                     # font size ceiling (% of min dimension)

# --- encode quality presets: name -> (crf, preset) ---
QUALITY = {
    "low": (30, "veryfast"),
    "medium": (26, "veryfast"),
    "high": (22, "medium"),
    "ultra": (18, "slow"),
}

POSITIONS = ["tl", "tc", "tr", "cl", "cc", "cr", "bl", "bc", "br"]
POSITION_NAMES = {
    "tl": "top left", "tc": "top center", "tr": "top right",
    "cl": "center left", "cc": "center", "cr": "center right",
    "bl": "bottom left", "bc": "bottom center", "br": "bottom right",
}


def setup_logging():
    handlers = [logging.StreamHandler()]
    try:
        handlers.append(logging.handlers.RotatingFileHandler(
            LOG_FILE, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"))
    except OSError:
        pass
    logging.basicConfig(
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        handlers=handlers,
    )
    for noisy in ("httpx", "httpcore", "apscheduler", "hpack"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
