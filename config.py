
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Telegram Credentials
# Cast API_ID to int as required by Telethon
API_ID = int(os.getenv("API_ID", "38659771"))
API_HASH = os.getenv("API_HASH", "6178147a40a23ade99f8b3a45f00e436")
BOT_TOKEN = os.getenv("BOT_TOKEN", "7970306481:AAFDDUbfhRejpeZnxKnDggJTmLqM7FZaIdU")

# Instagram Credentials
INSTAGRAM_USERNAME = os.getenv("INSTAGRAM_USERNAME", "shaktipurvaj")
INSTAGRAM_PASSWORD = os.getenv("INSTAGRAM_PASSWORD", "Shubham@9984")

# Session File Path
SESSION_FILE = "session.json"

# Update Control
# The Group ID allowed to trigger /update
ALLOWED_UPDATE_GROUP_ID = -1003830607616
