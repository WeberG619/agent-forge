#!/usr/bin/env python3
"""
Notification Channels - Multi-channel message delivery.

Supports:
- Telegram (via bot API)
- Voice TTS (via configurable command)
- Console (fallback, always available)

All credentials are loaded from environment variables.
Set them before running:
    export TELEGRAM_BOT_TOKEN="your-bot-token"
    export TELEGRAM_CHAT_ID="your-chat-id"
    export VOICE_COMMAND="path/to/speak.py"  # optional
"""

import os
import json
import logging
import subprocess
from datetime import datetime

logger = logging.getLogger("notify_channels")

# --- Configuration from environment ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Optional voice TTS command (e.g., "python3 /path/to/speak.py")
VOICE_COMMAND = os.getenv("PROACTIVE_VOICE_COMMAND", "")


def send_telegram(message: str) -> bool:
    """Send a message via Telegram Bot API.

    Requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID environment variables.
    Tries Markdown formatting first, falls back to plain text.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram not configured (set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)")
        return False

    import urllib.request
    import urllib.parse
    import urllib.error

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    # Try Markdown first, fall back to plain text if special chars cause 400
    for parse_mode in ("Markdown", None):
        try:
            params = {
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
            }
            if parse_mode:
                params["parse_mode"] = parse_mode

            data = urllib.parse.urlencode(params).encode()
            req = urllib.request.Request(url, data=data, method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read())
                if result.get("ok"):
                    logger.info(f"Telegram sent: {message[:50]}...")
                    return True
                else:
                    logger.error(f"Telegram API error: {result}")
                    return False
        except urllib.error.HTTPError as e:
            if e.code == 400 and parse_mode:
                logger.debug("Markdown parse failed, retrying as plain text")
                continue
            logger.error(f"Telegram send failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return False
    return False


def send_voice(message: str, max_chars: int = 500) -> bool:
    """Speak the message using a TTS command. Truncates long messages.

    Configure via PROACTIVE_VOICE_COMMAND environment variable.
    The command receives the message text as its first argument.
    """
    if not VOICE_COMMAND:
        logger.debug("Voice not configured (set PROACTIVE_VOICE_COMMAND)")
        return False

    try:
        # Truncate long messages for voice (keep first section)
        voice_text = message
        if len(voice_text) > max_chars:
            voice_text = (
                voice_text[:max_chars].rsplit("\n", 1)[0]
                + "\n\n...and more details in notifications."
            )

        cmd_parts = VOICE_COMMAND.split()
        cmd_parts.append(voice_text)
        subprocess.run(cmd_parts, timeout=120, capture_output=True)
        return True
    except Exception as e:
        logger.error(f"Voice failed: {e}")
        return False


def send_console(message: str) -> bool:
    """Print notification to console (always available fallback)."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] NOTIFICATION: {message}")
    return True


def notify_all(message: str, voice: bool = True) -> dict:
    """Send notification to all configured channels.

    Returns a dict of channel -> success boolean.
    """
    results = {}

    # Always try Telegram
    results["telegram"] = send_telegram(message)

    # Speak locally if requested
    if voice:
        results["voice"] = send_voice(message)

    # Console fallback if nothing else worked
    if not any(results.values()):
        results["console"] = send_console(message)

    timestamp = datetime.now().strftime("%H:%M:%S")
    logger.info(f"[{timestamp}] notify_all results: {results}")
    return results


def notify_telegram_only(message: str) -> bool:
    """Send notification only to Telegram (silent, no voice)."""
    return send_telegram(message)


def notify_voice_only(message: str) -> bool:
    """Speak only, no push notification."""
    return send_voice(message)


def notify_console(message: str) -> bool:
    """Console-only notification."""
    return send_console(message)


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) > 1:
        msg = " ".join(sys.argv[1:])
        print(f"Sending: {msg}")
        results = notify_all(msg)
        print(f"Results: {results}")
    else:
        print("Usage: python notify_channels.py <message>")
        print()
        print("Environment variables:")
        print(f"  TELEGRAM_BOT_TOKEN: {'set' if TELEGRAM_BOT_TOKEN else 'not set'}")
        print(f"  TELEGRAM_CHAT_ID:   {'set' if TELEGRAM_CHAT_ID else 'not set'}")
        print(f"  PROACTIVE_VOICE_COMMAND: {VOICE_COMMAND or 'not set'}")
