
import sys
import os
import re
import logging
import subprocess
import asyncio

# Force immediate flushing of stdout to see logs in real-time
sys.stdout.reconfigure(encoding='utf-8')

print("Initializing Bot Libraries...")

try:
    from telethon import TelegramClient, events
    print("Telethon imported successfully.")
    from instagrapi import Client
    from instagrapi.exceptions import (
        ChallengeRequired,
        TwoFactorRequired,
        LoginRequired,
        MediaNotFound
    )
    print("Instagrapi imported successfully.")
except ImportError as e:
    print(f"CRITICAL ERROR: Missing libraries. Did you run 'pip install -r requirements.txt'?\nError: {e}")
    input("Press Enter to exit...")
    sys.exit(1)

import config

# Configure Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

print(f"Connecting to Telegram with Bot Token: {config.BOT_TOKEN[:10]}...")
# Initialize Telegram Client
bot = TelegramClient('bot_session', config.API_ID, config.API_HASH).start(bot_token=config.BOT_TOKEN)
print("Telegram Client Started!")

# Initialize Instagram Client
cl = Client()

def login_instagram():
    """
    Handles Instagram Login with Session Management.
    """
    print("\n--- INSTAGRAM LOGIN START ---")
    logger.info("Attempting to login to Instagram...")
    
    # Check if session file exists
    if os.path.exists(config.SESSION_FILE):
        print(f"Found session file: {config.SESSION_FILE}")
        logger.info("Found session file. Loading...")
        try:
            cl.load_settings(config.SESSION_FILE)
            cl.login(config.INSTAGRAM_USERNAME, config.INSTAGRAM_PASSWORD)
            print("Login Successful using Session!")
            logger.info("Logged in using session settings!")
            return True
        except (ChallengeRequired, TwoFactorRequired) as e:
            print(f"Session Failed: {e}")
            logger.error(f"Session Login Failed (Challenge/2FA): {e}")
            logger.warning("Please delete the session file and login manually if this persists.")
            return False
        except Exception as e:
            print(f"Session Login Error: {e}")
            logger.error(f"Session Login Failed: {e}")
            return False

    # If no session file, try fresh login
    try:
        print(f"Attempting Fresh Login for user: {config.INSTAGRAM_USERNAME}...")
        logger.info("Attempting fresh login...")
        cl.login(config.INSTAGRAM_USERNAME, config.INSTAGRAM_PASSWORD)
        cl.dump_settings(config.SESSION_FILE)
        print("Fresh Login Successful! Session saved.")
        logger.info("Fresh login successful. Session saved.")
        return True
    
    except ChallengeRequired:
        print("CRITICAL: Instagram Challenge Required. Login Failed.")
        logger.critical("Login Failed: Challenge Required. Please login manually locally to generate a session file.")
        return False
    except TwoFactorRequired:
        print("CRITICAL: 2FA Required. Login Failed.")
        logger.critical("Login Failed: 2FA Required.")
        return False
    except Exception as e:
        print(f"Login Error: {e}")
        logger.error(f"Login Failed: {e}")
        return False

# -----------------
# Utility Commands
# -----------------

@bot.on(events.NewMessage(pattern='/start'))
async def handle_start(event):
    """
    Sanity check to see if bot is online.
    """
    print(f"Received /start from {event.chat_id}")
    await event.reply("✅ Bot is Online!\n\nSend me an Instagram link to download.\nOptions:\n/id - Get Chat ID\n/update - Update Bot (Admin only)")

@bot.on(events.NewMessage(pattern='/id'))
async def handle_id_command(event):
    """
    Returns the chat ID of the current chat/group.
    """
    print(f"Received /id from {event.chat_id}")
    await event.reply(f"`{event.chat_id}`")

@bot.on(events.NewMessage(pattern='/update'))
async def handle_update_command(event):
    """
    Updates the bot repository via git pull if sent from the allowed group.
    Attempts to preserve local changes using stash.
    """
    print(f"Received /update from {event.chat_id}")
    # Check if the command is from the allowed group
    if event.chat_id != config.ALLOWED_UPDATE_GROUP_ID:
        return

    msg = await event.reply("🔄 Stashing local changes and checking for updates...")

    try:
        # 1. Git Stash (Save local changes)
        p_stash = await asyncio.create_subprocess_exec(
            "git", "stash",
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        await p_stash.communicate()

        # 2. Git Pull
        process = await asyncio.create_subprocess_exec(
            "git", "pull",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        output = stdout.decode().strip()
        error = stderr.decode().strip()

        # 3. Git Stash Pop (Restore local changes)
        # We do this regardless of pull success to ensure we don't lose work, 
        # unless pull was fatal in a way that left repo weird.
        p_pop = await asyncio.create_subprocess_exec(
            "git", "stash", "pop",
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        await p_pop.communicate()

        if process.returncode == 0:
            if "Already up to date." in output:
                await msg.edit(f"✅ Bot is already up to date.\n\n`{output}`\n\n_Restored local changes._")
            else:
                await msg.edit(f"✅ Bot Updated Successfully!\n\nOutput:\n`{output}`\n\n_Restored local changes._\n🔄 Restarting bot...")
                # Restart the bot process
                os.execl(sys.executable, sys.executable, *sys.argv)
        else:
            await msg.edit(f"❌ Update Failed:\n\nError:\n`{error}`\n\n_Restored local changes._")
            
    except Exception as e:
        await msg.edit(f"❌ Error during update: {str(e)}")


# -----------------
# Instagram Handler
# -----------------

@bot.on(events.NewMessage)
async def handle_all_messages(event):
    """
    Global message handler to route instagram links.
    """
    if not event.text:
        return

    # Regex for Instagram
    if re.search(r'instagram\.com', event.text, re.IGNORECASE):
        # Avoid processing /update or /id if they somehow contain instagram.com
        if event.text.strip().startswith('/'):
            return

        print(f"Processing Instagram Link from {event.chat_id}...")
        
        # Extract URL
        match = re.search(r'(https?://(?:www\.)?instagram\.com/[^\s]+)', event.text)
        if not match:
            # Fallback for links without http/https (if user copy-pastes weirdly)
            match = re.search(r'(www\.instagram\.com/[^\s]+)', event.text)
            if not match:
                return
            insta_url = "https://" + match.group(0)
        else:
            insta_url = match.group(0)

        # Send "Fetching..." message
        msg = await event.reply("⏳ Fetching media info...")

        file_path = None
        try:
            # 1. Get Media PK
            pk = cl.media_pk_from_url(insta_url)
            
            # 2. Get Media Info
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
                await msg.edit("⚠️ Carousel downloading not supported yet.")
                print("Carousel detected - skipping.")
                return

            else:
                await msg.edit("❌ Unknown media type.")
                return

            # 4. Clean up
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
                print(f"Deleted local file: {file_path}")
            
            await msg.delete()

        except ChallengeRequired:
            await msg.edit("⚠️ Error: Instagram Challenge Required. Admin verification needed.")
            print("Error: Challenge Required.")
        
        except LoginRequired:
            print("Error: Login Required. Attempting to re-login...")
            try:
                # Attempt to re-login using credentials
                cl.login(config.INSTAGRAM_USERNAME, config.INSTAGRAM_PASSWORD)
                cl.dump_settings(config.SESSION_FILE)
                print("Re-login successful. Retrying fetch...")
                
                # Retry fetching media info after re-login
                media_info = cl.media_info(pk)
                # We need to duplicate the logic or use a loop, but for quick fix:
                # We will process it here or jump back. 
                # Since we can't jump back easily in this structure without refactoring into a function,
                # let's just ask the user to try again for now, but confirm login is fixed.
                await msg.edit("⚠️ Session expired but Re-login was successful! \n\nPlease send the link again.")
                return

            except Exception as e:
                print(f"Re-login failed: {e}")
                # If re-login fails, the session file is likely bad. Delete it.
                if os.path.exists(config.SESSION_FILE):
                    os.remove(config.SESSION_FILE)
                    print("Deleted corrupted session file.")
                
                await msg.edit("⚠️ Error: Login Required and Re-login failed. \n\nPlease wait a minute and try again (Server restarting session).")
        
        except MediaNotFound:
            await msg.edit("❌ Error: Media not found (Private or Invalid).")
            print("Error: Media Not Found.")
        
        except Exception as e:
            print(f"Exception processing link: {e}")
            await msg.edit(f"❌ Error: {str(e)}")
            if file_path and os.path.exists(file_path):
                os.remove(file_path)

if __name__ == '__main__':
    print("\n-----------------------------------")
    print("       BOT STARTUP SEQUENCE        ")
    print("-----------------------------------")
    
    # Attempt Login on Startup
    if not login_instagram():
        print("WARNING: Instagram login failed. Bot may not operate correctly for private content.")
    else:
        print("Instagram Login: OK")
        
    print("\nBot is now running and waiting for messages...")
    print("Send /start to your bot in Telegram to verify connectivity.")
    
    try:
        bot.run_until_disconnected()
    except Exception as e:
        print(f"Bot Crashed: {e}")
        input("Press Enter to exit...")
