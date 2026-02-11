
import os
import re
import logging
import subprocess
import asyncio
from telethon import TelegramClient, events
from instagrapi import Client
from instagrapi.exceptions import (
    ChallengeRequired,
    TwoFactorRequired,
    LoginRequired,
    MediaNotFound
)
import config

# Configure Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize Telegram Client
bot = TelegramClient('bot_session', config.API_ID, config.API_HASH).start(bot_token=config.BOT_TOKEN)

# Initialize Instagram Client
cl = Client()

def login_instagram():
    """
    Handles Instagram Login with Session Management.
    """
    logger.info("Attempting to login to Instagram...")
    
    # Check if session file exists
    if os.path.exists(config.SESSION_FILE):
        logger.info("Found session file. Loading...")
        try:
            cl.load_settings(config.SESSION_FILE)
            cl.login(config.INSTAGRAM_USERNAME, config.INSTAGRAM_PASSWORD)
            logger.info("Logged in using session settings!")
            return True
        except (ChallengeRequired, TwoFactorRequired) as e:
            logger.error(f"Session Login Failed (Challenge/2FA): {e}")
            logger.warning("Please delete the session file and login manually if this persists.")
            return False
        except Exception as e:
            logger.error(f"Session Login Failed: {e}")
            return False

    # If no session file, try fresh login
    try:
        logger.info("Attempting fresh login...")
        cl.login(config.INSTAGRAM_USERNAME, config.INSTAGRAM_PASSWORD)
        cl.dump_settings(config.SESSION_FILE)
        logger.info("Fresh login successful. Session saved.")
        return True
    
    except ChallengeRequired:
        logger.critical("Login Failed: Challenge Required. Please login manually locally to generate a session file.")
        return False
    except TwoFactorRequired:
        logger.critical("Login Failed: 2FA Required.")
        return False
    except Exception as e:
        logger.error(f"Login Failed: {e}")
        return False

# Attempt Login on Startup
if not login_instagram():
    logger.warning("Instagram login failed. Bot may not operate correctly for private content.")

# -----------------
# Utility Commands
# -----------------

@bot.on(events.NewMessage(pattern='/id'))
async def handle_id_command(event):
    """
    Returns the chat ID of the current chat/group,
    formatted as monospaced text for easy copying.
    """
    # Simply reply with the chat ID in backticks
    await event.reply(f"`{event.chat_id}`")

@bot.on(events.NewMessage(pattern='/update'))
async def handle_update_command(event):
    """
    Updates the bot repository via git pull if sent from the allowed group.
    """
    # Check if the command is from the allowed group
    if event.chat_id != config.ALLOWED_UPDATE_GROUP_ID:
        # Ignore silently if unauthorized group
        return

    msg = await event.reply("🔄 Checking for updates...")

    try:
        # Run 'git pull'
        process = await asyncio.create_subprocess_exec(
            "git", "pull",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        output = stdout.decode().strip()
        error = stderr.decode().strip()

        if process.returncode == 0:
            if "Already up to date." in output:
                await msg.edit(f"✅ Bot is already up to date.\n\n`{output}`")
            else:
                await msg.edit(f"✅ Bot Updated Successfully!\n\nOutput:\n`{output}`\n\n_Restart might be required for changes to take effect._")
        else:
            await msg.edit(f"❌ Update Failed:\n\nError:\n`{error}`")
            
    except Exception as e:
        await msg.edit(f"❌ Error during update: {str(e)}")


# -----------------
# Instagram Handler
# -----------------

@bot.on(events.NewMessage(pattern=re.compile(r'.*instagram\.com.*', re.IGNORECASE)))
async def handle_instagram_link(event):
    # If the message starts with a command like /id or /update, ignore it here
    # (Though pattern matching usually handles this, regex .*instagram.com.* might catch text with commands if not careful)
    if event.text.startswith('/'):
        return

    if event.is_private:
         # Log user interaction or restricts
         pass

    text = event.message.text
    
    # Extract URL using Regex
    match = re.search(r'(https?://(?:www\.)?instagram\.com/[^\s]+)', text)
    if not match:
        return
    
    insta_url = match.group(0) # The extracted URL
    
    # Send "Date fetching..." message
    msg = await event.reply("⏳ Fetching media info...")

    file_path = None
    try:
        # 1. Get Media PK
        pk = cl.media_pk_from_url(insta_url)
        
        # 2. Get Media Info
        # Using handle_exception isn't needed if we catch specific ones below, but cl methods raise them.
        media_info = cl.media_info(pk)
        
        media_type = media_info.media_type # 1=Photo, 2=Video, 8=Album
        
        # 3. Handle Media Types
        if media_type == 1: # Photo
            await msg.edit("📸 Downloading Photo...")
            path = cl.photo_download(pk, folder=".")
            file_path = str(path)
            
            await msg.edit("📤 Uploading Photo...")
            await bot.send_file(
                event.chat_id, 
                file_path, 
                caption=f"{media_info.caption_text[:1000]}..." if media_info.caption_text else ""
            )
            
        elif media_type == 2: # Video/Reel/IGTV
            await msg.edit("🎥 Downloading Video...")
            path = cl.video_download(pk, folder=".")
            file_path = str(path)
            
            await msg.edit("📤 Uploading Video...")
            await bot.send_file(
                event.chat_id, 
                file_path, 
                caption=f"{media_info.caption_text[:1000]}..." if media_info.caption_text else ""
            )
            
        elif media_type == 8: # Album
            # As requested: Simple message for now
            await msg.edit("⚠️ Carousel downloading not supported yet.")
            return

        else:
             await msg.edit("❌ Unknown media type.")
             return

        # 4. Clean up
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Deleted local file: {file_path}")
        
        await msg.delete() # Remove status message

    except ChallengeRequired:
        await msg.edit("⚠️ Error: Instagram Challenge Required. Admin verification needed.")
        logger.error("Challenge Required.")
    
    except LoginRequired:
        await msg.edit("⚠️ Error: Login Required. Session invalid.")
    
    except MediaNotFound:
         await msg.edit("❌ Error: Media not found (Private or Invalid).")
    
    except Exception as e:
        logger.error(f"Error processing link: {e}")
        await msg.edit(f"❌ Error: {str(e)}")
        # Cleanup if failed
        if file_path and os.path.exists(file_path):
             os.remove(file_path)

if __name__ == '__main__':
    print("Bot is running...")
    bot.run_until_disconnected()
