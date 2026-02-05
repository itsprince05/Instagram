import asyncio
import logging
import re
import os
import requests
import time
import sys
import random
import subprocess
import json
from concurrent.futures import ThreadPoolExecutor
from telethon import TelegramClient, events


# --- Logging Configuration ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Configuration ---
API_ID = 38659771
API_HASH = '6178147a40a23ade99f8b3a45f00e436'
BOT_TOKEN = "8533327762:AAHR1D4CyFpMQQ4NztXhET6OL4wL1kHNkQ4"



# Groups
GROUP_MEDIA = -1003759432523
GROUP_ERROR = -1003650307144


# Valid headers for requests mostly for download if needed, though instaloader handles its own metadata
# API_URL = "https://princeapps.com/insta.php" # Removed





# --- Client Initialization ---
bot = TelegramClient('controller_bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# --- State Management ---
QUEUE = asyncio.Queue()
IS_PROCESSING = False

# Stats tracking
STATS = {
    'total': 0,
    'completed': 0,
    'failed': 0,
    'remaining': 0,
    'status_msg': None,
    'chat_id': None
}

# Executor for blocking IO
executor = ThreadPoolExecutor(max_workers=5)

def clean_instagram_url(url):
    """Removes query parameters to get the clean Instagram link."""
    return url.split('?')[0]

async def update_status_message():
    """Updates the status message in the chat."""
    if not STATS['status_msg']:
        return

    try:
        text = (
            "Bulk Processing Status\n\n"
            f"Total Tasks: {STATS['total']}\n"
            f"Completed: {STATS['completed']}\n"
            f"Failed: {STATS['failed']}\n"
            f"Remaining: {STATS['remaining']}\n\n"
            "Processing..."
        )
        
        if STATS['remaining'] == 0 and STATS['total'] > 0:
            text += "\n\nAll tasks completed!"

        await STATS['status_msg'].edit(text)
    except Exception as e:
        logger.error(f"Failed to update status message: {e}")

    except Exception as e:
        logger.error(f"Failed to update status message: {e}")



def fetch_media_task(url):
    """Fetch media using Direct Instagram GraphQL/JSON API."""
    try:
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Instagram 243.1.0.14.111',
            'Accept': '*/*'
        })
        
        # Clean URL
        clean_link = url.split('?')[0]
        # Append parameters for JSON
        api_url = f"{clean_link}?__a=1&__d=dis"
        
        response = session.get(api_url, timeout=10)
        
        if response.status_code != 200:
             if response.status_code == 401:
                 return {'error': "HTTP 401 - Login Required (Server Blocked)"}
             return {'error': f"HTTP {response.status_code}"}
             
        try:
            data = response.json()
        except:
            return {'error': "Invalid JSON Response"}
            
        items = []
        
        # Locate the media node
        # Structure varies: sometimes ['items'][0], sometimes ['graphql']['shortcode_media']
        node = None
        if 'items' in data and len(data['items']) > 0:
            node = data['items'][0]
        elif 'graphql' in data and 'shortcode_media' in data['graphql']:
            node = data['graphql']['shortcode_media']
            
        if not node:
            return {'error': "No Media Node Found"}
            
        media_list = []
        msgs = []
        
        # Helper to process a single node
        def process_node(n):
            # Check for Video
            if 'video_versions' in n:
                # Get best quality video
                videos = sorted(n['video_versions'], key=lambda x: x['width']*x['height'], reverse=True)
                if videos:
                    media_list.append({'url': videos[0]['url'], 'is_video': True})
            elif 'image_versions2' in n:
                # Get best quality image
                images = sorted(n['image_versions2']['candidates'], key=lambda x: x['width']*x['height'], reverse=True)
                if images:
                    media_list.append({'url': images[0]['url'], 'is_video': False})
            
            # Check Audio flag if available (usually has_audio)
            if n.get('has_audio') is False and n.get('video_versions'):
                msgs.append(f"Error - No Audio\n{url}")

        # Check for Sidecar
        if 'carousel_media' in node:
            msgs.append(f"Multiple Sidecar\n{url}")
            for child in node['carousel_media']:
                process_node(child)
        else:
            process_node(node)
            
        if not media_list:
             return {'error': "Invalid / No Media Found"}

        msgs = list(set(msgs))
        return {'media': media_list, 'msgs': msgs}

    except Exception as e:
        return {'error': f"Exception: {str(e)}"}

def download_media_task(media_url, is_video=False):
    """Synchronous function to download media to temp file."""
    try:
        # Determine extension based on type, fail-safe
        ext = 'mp4' if is_video else 'jpg'
            
        filename = f"temp_{int(time.time() * 1000000)}.{ext}"
        
        
        with requests.get(media_url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(filename, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        return filename
    except Exception as e:
        logger.error(f"Download failed: {e}")
        if os.path.exists(filename):
            try:
                os.remove(filename)
            except:
                pass
        return None

async def process_queue():
    """Main worker loop."""
    global IS_PROCESSING
    IS_PROCESSING = True
    loop = asyncio.get_event_loop()
    
    while not QUEUE.empty():
        url = await QUEUE.get()
        clean_url = clean_instagram_url(url)
        logger.info(f"Processing: {url}")
        
        try:
            # 1. Fetch Metadata (Run in Thread)
            result = await loop.run_in_executor(executor, fetch_media_task, url)
            
            if 'media' in result:
                media_items = result['media']
                # 2. Process Media
                for item in media_items:
                    media_link = item['url']
                    is_video = item['is_video']
                    
                    # Download (Run in Thread)
                    file_path = await loop.run_in_executor(executor, download_media_task, media_link, is_video)
                    
                    if file_path:
                        try:
                            # Upload (Telethon send_file is async)
                            await bot.send_file(
                                GROUP_MEDIA,
                                file_path,
                                caption=clean_url,
                                force_document=False,
                                supports_streaming=is_video
                            )
                        except Exception as e_up:
                            logger.error(f"Upload failed: {e_up}")
                        finally:
                            # Cleanup
                            if os.path.exists(file_path):
                                os.remove(file_path)
                            
                        await asyncio.sleep(1) # Rate limit
                
                # Send Side Channel Messages (No Audio, Multiple Sidecar)
                if 'msgs' in result:
                    for msg in result['msgs']:
                        try:
                            await bot.send_message(GROUP_ERROR, msg, link_preview=False)
                        except:
                            pass

                STATS['completed'] += 1
            else:
                # Error
                error_reason = result.get('error', 'Unknown')
                
                # Check for "Invalid" specific error
                if "Invalid" in error_reason:
                     await bot.send_message(GROUP_ERROR, f"Error - Invalid\n{url}", link_preview=False)
                else:
                     raise Exception(error_reason) # Trigger standard error handler

        except Exception as e:
            STATS['failed'] += 1
            # Standard error handler for exceptions
            try:
                await bot.send_message(
                    GROUP_ERROR, 
                    f"Error: {e}\n{url}", 
                    link_preview=False
                )
            except:
                pass
        
        # DEBUG: Send Dump if exists
        if os.path.exists('debug_dump.json'):
            try:
                await bot.send_file(
                    GROUP_ERROR,
                    'debug_dump.json',
                    caption=f"Debug Data for: {url}",
                    force_document=True
                )
            except Exception as e_dump:
                logger.error(f"Failed to send debug dump: {e_dump}")
            finally:
                os.remove('debug_dump.json')
        
        STATS['remaining'] = QUEUE.qsize()
        STATS['remaining'] = QUEUE.qsize()
        await update_status_message()
        await asyncio.sleep(5) # 5 Second Delay (User Request)
            
    IS_PROCESSING = False
    await update_status_message()

@bot.on(events.NewMessage(pattern='/update'))
async def update_handler(event):
    if event.chat_id == GROUP_MEDIA or event.is_private:
        msg = await event.respond("Update Requested\nPulling latest code...")
        try:
            proc = await asyncio.create_subprocess_shell(
                "git pull",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            
            if proc.returncode == 0:
                await msg.edit(f"Git Pull Success\n{stdout.decode().strip()}\n\nRestarting System...")
                subprocess.Popen(["sudo", "systemctl", "restart", "extracter"])
                sys.exit(0)
            else:
                await msg.edit(f"Git Pull Failed\n{stderr.decode()}")
        except Exception as e:
            await msg.edit(f"Error: {e}")



@bot.on(events.NewMessage)
async def message_handler(event):
    if not event.is_private:
        return
    
    chat_id = event.chat_id
    text = event.message.text or ""

    if text.startswith('/'):
        return

    # --- Normal Link Processing ---
    urls = re.findall(r'(https?://(?:www\.)?instagram\.com/\S+)', text)
    
    if urls:
        added = 0
        for url in urls:
            await QUEUE.put(url)
            added += 1
            
        if added > 0:
            STATS['chat_id'] = event.chat_id
            
            if not IS_PROCESSING and STATS['remaining'] == 0:
                STATS['total'] = added
                STATS['completed'] = 0
                STATS['failed'] = 0
                STATS['remaining'] = QUEUE.qsize()
                STATS['status_msg'] = await event.respond(
                    f"Derived Queue ({added} links)..."
                )
            else:
                STATS['total'] += added
                STATS['remaining'] = QUEUE.qsize()
                if STATS['status_msg']:
                    try:
                        await STATS['status_msg'].delete()
                    except:
                        pass
                STATS['status_msg'] = await event.respond(
                    f"Queue Updated (+{added})..."
                )
            
            await update_status_message()
            
            if not IS_PROCESSING:
                asyncio.create_task(process_queue())

@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    await event.respond("👋 Send Instagram links to extract.")

if __name__ == '__main__':
    bot.run_until_disconnected()