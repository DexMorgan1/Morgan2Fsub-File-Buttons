import os
import logging
from logging.handlers import RotatingFileHandler


TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "")
APP_ID = int(os.environ.get("APP_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "0"))
OWNER = os.environ.get("OWNER", "")
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))
PORT = int(os.environ.get("PORT", "8030"))
DB_URI = os.environ.get("DATABASE_URL", "")
DB_NAME = os.environ.get("DATABASE_NAME", "Morgan2FsubRequestJoin")

# Force-subscribe channel IDs are managed in Railway variables.
FORCE_SUB_CHANNEL = int(os.environ.get("FORCE_SUB_CHANNEL", os.environ.get("FORCE_SUB_CHANNEL_1", "0")))
FORCE_SUB_CHANNEL2 = int(os.environ.get("FORCE_SUB_CHANNEL2", os.environ.get("FORCE_SUB_CHANNEL_2", "0")))
FORCE_SUB_CHANNEL_ENABLED = os.environ.get("FORCE_SUB_CHANNEL_ENABLED", "True").lower() == "true"
FORCE_SUB_CHANNEL2_ENABLED = os.environ.get("FORCE_SUB_CHANNEL2_ENABLED", "True").lower() == "true"
AUTO_APPROVE_JOIN_REQUESTS = os.environ.get("AUTO_APPROVE_JOIN_REQUESTS", "True").lower() == "true"
TG_BOT_WORKERS = int(os.environ.get("TG_BOT_WORKERS", "4"))

# File update buttons are controlled entirely from Railway. Give each button
# a full HTTPS or Telegram URL; leaving a link empty hides only that button.
TV_SHOW_BUTTON_TEXT = os.environ.get("TV_SHOW_BUTTON_TEXT", "📺 TV SHOW").strip() or "📺 TV SHOW"
TV_SHOW_BUTTON_LINK = os.environ.get("TV_SHOW_BUTTON_LINK", "").strip()
MOVIES_BUTTON_TEXT = os.environ.get("MOVIES_BUTTON_TEXT", "🎬 MOVIES").strip() or "🎬 MOVIES"
MOVIES_BUTTON_LINK = os.environ.get("MOVIES_BUTTON_LINK", "").strip()


START_MSG = os.environ.get("START_MESSAGE", "<b>Hello {first} 🏮\n\nWelcome to SeriesAchiever. Send a file link to access your files.</b>")
FORCE_MSG = os.environ.get("FORCE_SUB_MESSAGE", "<b>Hello {first} 🏮</b>\nYou must first become a member of our channels")
CUSTOM_CAPTION = os.environ.get("CUSTOM_CAPTION", None)
PROTECT_CONTENT = os.environ.get("PROTECT_CONTENT", "False") == "True"
DISABLE_CHANNEL_BUTTON = os.environ.get("DISABLE_CHANNEL_BUTTON", "False") == "True"
BOT_STATS_TEXT = "<b>BOT UPTIME</b>\n{uptime}"
USER_REPLY_TEXT = "You need to be a SeriesAchiever bot administrator to do that."


try:
    ADMINS = [int(x) for x in os.environ.get("ADMINS", "").split()]
    if OWNER_ID:
        ADMINS.append(OWNER_ID)
    ADMINS = list(set(ADMINS))
except ValueError as error:
    raise ValueError("ADMINS must be a space-separated list of Telegram numeric IDs.") from error


LOG_FILE_NAME = "filesharingbot.txt"
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s - %(levelname)s] - %(name)s - %(message)s",
    datefmt='%d-%b-%y %H:%M:%S',
    handlers=[
        RotatingFileHandler(LOG_FILE_NAME, maxBytes=50000000, backupCount=10),
        logging.StreamHandler(),
    ],
)
logging.getLogger("pyrogram").setLevel(logging.WARNING)


def LOGGER(name: str) -> logging.Logger:
    return logging.getLogger(name)
