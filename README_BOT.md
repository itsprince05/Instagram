# Instagram Downloader Bot

This bot downloads Instagram posts, reels, and IGTV videos and sends them to you on Telegram.

## Setup for VPS

1.  **Get a Telegram Bot Token**:
    *   Open Telegram and search for `@BotFather`.
    *   Send `/newbot` and follow the instructions.
    *   Copy the API Token.

2.  **Edit `bot.py`**:
    *   Open `bot.py` and replace `YOUR_TELEGRAM_BOT_TOKEN_HERE` with your actual token.

3.  **Upload to VPS**:
    *   Upload all files (`bot.py`, `requirements.txt`, `Procfile`, and the `instaloader` folder if you want to use the local version, otherwise `requirements.txt` will install it).

4.  **Install Dependencies on VPS**:
    ```bash
    pip install -r requirements.txt
    ```

5.  **Run the Bot**:
    ```bash
    python bot.py
    ```

## Features
*   Accepts Instagram links (Post, Reel, IGTV).
*   Downloads the content using `instaloader`.
*   Sends the video/image to the chat.
*   Deletes the downloaded files from the server after sending to save space.
