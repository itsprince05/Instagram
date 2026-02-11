
import json
import os
import sys
from instagrapi import Client
from instagrapi.exceptions import (
    ChallengeRequired,
    TwoFactorRequired,
    LoginRequired,
    FeedbackRequired
)
import config

# Helper to input code
def code_handler(text, choice=None):
    print(f"\n[Instagram Challenge] {text}")
    return input(">> Enter Code: ").strip()

def create_session():
    if os.path.exists(config.SESSION_FILE):
        print(f"Removing old session file: {config.SESSION_FILE}")
        os.remove(config.SESSION_FILE)

    cl = Client()
    # Set the interactive handler
    cl.challenge_code_handler = code_handler

    print(f"Attempting to login as: {config.INSTAGRAM_USERNAME}")
    print("Please check your Email/SMS if prompted for a code.")

    try:
        # Try login with basic credentials
        # verification_code arg is mostly for 2FA, but instagrapi uses handlers for challenges
        cl.login(config.INSTAGRAM_USERNAME, config.INSTAGRAM_PASSWORD)
        
        # If successful
        cl.dump_settings(config.SESSION_FILE)
        print(f"\n[SUCCESS] Login successful! Session saved to '{config.SESSION_FILE}'")
        print("You can now restart your bot: python bot.py")

    except TwoFactorRequired:
        print("\n[AUTH] 2FA is enabled.")
        code = input(">> Enter 2FA Code (SMS/Auth App): ").strip()
        try:
            cl.login(config.INSTAGRAM_USERNAME, config.INSTAGRAM_PASSWORD, verification_code=code)
            cl.dump_settings(config.SESSION_FILE)
            print(f"\n[SUCCESS] 2FA Login successful! Session saved.")
            print("You can now restart your bot: python bot.py")
        except Exception as e:
             print(f"\n[ERROR] 2FA Failed: {e}")

    except ChallengeRequired as e:
        print("\n[CHALLENGE] Instagram requires verification.")
        # Sometimes the handler above catches it, sometimes we fall here.
        # If we fall here, we might need to manually trigger the resolution steps if library didn't.
        # However, cl.login() usually triggers the handler if set.
        
        # If we are here, automatic handling might have failed or not triggered.
        # Manual attempt logic:
        try:
             # Basic attempt to resolve if possible
             # (This part is complex as it depends on what 'e' contains, 
             # but often just running login with handler SET is enough).
             print(f"Challenge Details: {e}")
             print("The script tried to handle it automatically but failed.")
             print("Try logging into Instagram.com on this computer's browser first to trust the IP.")
        except Exception as e2:
             print(f"Resolution failed: {e2}")

    except FeedbackRequired as e:
        print(f"\n[BLOCK] Action Blocked (Feedback Required): {e}")
        print("Your IP might be temporarily blocked or you are posting too fast.")
        print("Try logging in later or change your IP/VPN.")

    except Exception as e:
        print(f"\n[ERROR] Login Failed: {e}")
        if "blacklist" in str(e).lower():
            print("\n!!! IP BLACKLISTED !!!")
            print("Instagram has flagged your IP address.")
            print("Suggestions:")
            print("1. Turn off your Wi-Fi router for 5 mins (to get new IP).")
            print("2. Connect to a different network (Mobile Hotspot).")
            print("3. Use a Proxy/VPN in the script.")

if __name__ == "__main__":
    create_session()
