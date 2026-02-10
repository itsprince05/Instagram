import os
import sys
import logging
import subprocess
import time
import shutil
import asyncio
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import instaloader

# --- CONFIGURATION ---
TOKEN = "7970306481:AAFDDUbfhRejpeZnxKnDggJTmLqM7FZaIdU"
# API_ID and API_HASH are generally used for userbots (Pyrogram/Telethon). 
# Since we are using python-telegram-bot (standard Bot API), we only strictly need the TOKEN.
# I will keep them here if you decide to switch libraries later, but they aren't used in this specific implementation.
API_ID = "38659771"
API_HASH = "6178147a40a23ade99f8b3a45f00e436"

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize Instaloader
L = instaloader.Instaloader()

# --- INSTAGRAM LOGIN ---
# To fix 401 errors, we must login.
INSTA_USER = os.getenv("INSTA_USER") 
INSTA_PASS = os.getenv("INSTA_PASS")

def instagram_login():
    if not INSTA_USER or not INSTA_PASS:
        logger.warning("Instagram credentials not found in environment variables. Running anonymously (might fail).")
        return

    try:
        logger.info(f"Attempting login for {INSTA_USER}...")
        # Check if session file exists
        session_file = f"session-{INSTA_USER}"
        if os.path.exists(session_file):
             try:
                L.load_session_from_file(INSTA_USER, filename=session_file)
                logger.info("Session loaded successfully.")
                return 
             except Exception as e:
                logger.warning(f"Failed to load session: {e}. Trying fresh login.")

        # Login if no session or session failed
        L.login(INSTA_USER, INSTA_PASS)
        L.save_session_to_file(filename=session_file)
        logger.info("Logged in and session saved.")
            
    except Exception as e:
        logger.error(f"Instagram Login Failed: {e}")

# Perform login on startup
try:
    instagram_login()
except Exception as e:
    logger.error(f"Login routine failed: {e}")

# File to store chat_id for post-update notification
UPDATE_STATUS_FILE = "update_status.txt"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Hello! I can download Instagram content and tell you your Chat ID.\n"
        "Commands:\n"
    )

async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    # Send ID in code format so it's clickable/copyable
    await update.message.reply_text(f"<code>{chat_id}</code>", parse_mode=ParseMode.HTML)

async def update_bot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    
    # Only allow update in specific group
    if chat_id != -1003830607616:
        await update.message.reply_text("This command is not allowed here.")
        return

    await update.message.reply_text("Pulling changes from GitHub...")
    
    try:
        # Run git pull
        process = subprocess.Popen(["git", "pull"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output, error = process.communicate()
        
        if process.returncode == 0:
            await update.message.reply_text(f"Git Pull Successful.\nOutput:\n{output.decode()}\nRestarting...")
            
            # Save the chat ID to notify after restart
            with open(UPDATE_STATUS_FILE, "w") as f:
                f.write(str(chat_id))
            
            # Restart the script
            # Use sys.executable for the program argument to ensure correct path resolution
            os.execv(sys.executable, [sys.executable] + sys.argv)
        else:
            await update.message.reply_text(f"Git Pull Failed.\nError:\n{error.decode()}")
            
    except Exception as e:
        await update.message.reply_text(f"Update failed: {e}")

async def download_instagram_content(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    url = update.message.text
    chat_id = update.effective_chat.id
    
    if "instagram.com" not in url:
        return # Ignore non-links

    status_message = await update.message.reply_text("Processing... Please wait.")

    try:
        # Extract shortcode
        shortcode = None
        if "p/" in url: shortcode = url.split("instagram.com/p/")[1].split("/")[0]
        elif "reel/" in url: shortcode = url.split("instagram.com/reel/")[1].split("/")[0]
        elif "tv/" in url: shortcode = url.split("instagram.com/tv/")[1].split("/")[0]

        if not shortcode:
            await status_message.edit_text("Could not extract shortcode.")
            return

        target_dir = f"temp_{shortcode}_{int(time.time())}"
        
        # Download
        # Using a loop to run blocking instaloader call in a separate thread to not block the bot
        await asyncio.to_thread(download_post, shortcode, target_dir)

        # Check and send files
        files_sent = False
        media_group = [] 
        # Note: Sending media group (album) is better for multiple files, 
        # but for simplicity let's send individually or strictly what we find.
        
        for root, dirs, files in os.walk(target_dir):
            for file in files:
                file_path = os.path.join(root, file)
                if file.endswith(".mp4"):
                    await context.bot.send_video(chat_id=chat_id, video=open(file_path, 'rb'))
                    files_sent = True
                elif file.endswith(".jpg"):
                    await context.bot.send_photo(chat_id=chat_id, photo=open(file_path, 'rb'))
                    files_sent = True
        
        if not files_sent:
             await status_message.edit_text("Could not find media. The post might be private.")
        else:
             await status_message.delete()

    except Exception as e:
        await status_message.edit_text(f"Error: {str(e)}")
    finally:
        if 'target_dir' in locals() and os.path.exists(target_dir):
            shutil.rmtree(target_dir)

def download_post(shortcode, target_dir):
    try:
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        L.download_post(post, target=target_dir)
    except Exception as e:
        print(f"Instaloader Error: {e}")
        raise e

async def check_for_update_success(application: Application):
    if os.path.exists(UPDATE_STATUS_FILE):
        try:
            with open(UPDATE_STATUS_FILE, "r") as f:
                chat_id = int(f.read().strip())
            
            # Send the "Updated" message
            await application.bot.send_message(chat_id=chat_id, text="Bot Updated Successfully! 🚀")
            
            os.remove(UPDATE_STATUS_FILE)
        except Exception as e:
            logger.error(f"Failed to send update notification: {e}")

def main() -> None:
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("id", get_id))
    application.add_handler(CommandHandler("update", update_bot))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_instagram_content))

    # Add the post-init callback to check for update status
    # application.post_init = check_for_update_success # post_init doesn't accept coroutines easily in all versions, 
    # let's just run it once the loop starts or use a job queue if available, 
    # or simpler: just check in the main loop before polling if possible.
    # Actually, post_init IS designed for this in v20+.
    application.post_init = check_for_update_success

    application.run_polling()

if __name__ == '__main__':
    main()
