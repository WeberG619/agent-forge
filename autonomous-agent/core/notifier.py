#!/usr/bin/env python3
"""
Notifier for Autonomous Agent
=============================
Sends notifications via configurable channels (Telegram, console, voice, etc.).

Configure via environment variables:
    TELEGRAM_BOT_TOKEN - Your Telegram bot token (from @BotFather)
    TELEGRAM_CHAT_ID   - Your Telegram user/chat ID

If no Telegram credentials are set, notifications are logged to console only.
"""

import os
import sys
import asyncio
import logging
from typing import Optional
from datetime import datetime

logger = logging.getLogger("autonomous-agent.notifier")

# ============================================
# CONFIGURATION (from environment variables)
# ============================================

# Telegram - set these env vars to enable Telegram notifications
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Preferences
MAX_MESSAGE_LENGTH = 4000


class Notifier:
    """
    Sends notifications through multiple channels.

    By default, notifications are logged to console. Configure Telegram
    by setting TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID environment variables.

    You can extend this class with additional notification channels
    (Slack, Discord, email, etc.) by adding new send methods.
    """

    def __init__(self):
        self.telegram_enabled = bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)
        self.notification_history = []

        if self.telegram_enabled:
            logger.info("Telegram notifications enabled")
        else:
            logger.info("Telegram not configured - notifications will be logged to console only")
            logger.info("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID env vars to enable Telegram")

    async def send(self, title: str, message: str, priority: str = "medium") -> bool:
        """
        Send notification via best available channel.

        Args:
            title: Notification title
            message: Notification body
            priority: "critical", "high", "medium", "low"

        Returns:
            True if notification was sent successfully
        """
        full_message = f"*{title}*\n\n{message}"

        # Truncate if too long
        if len(full_message) > MAX_MESSAGE_LENGTH:
            full_message = full_message[:MAX_MESSAGE_LENGTH - 20] + "\n\n...(truncated)"

        # Log all notifications
        self._log_notification(title, message, priority)

        # Try Telegram first
        if self.telegram_enabled:
            success = await self._send_telegram(full_message)
            if success:
                return True

        # Console fallback - always works
        logger.info(f"[NOTIFICATION] [{priority.upper()}] {title}: {message[:200]}")
        return True

    async def _send_telegram(self, message: str) -> bool:
        """Send message via Telegram Bot API."""
        try:
            import aiohttp
        except ImportError:
            logger.warning("aiohttp not installed - Telegram notifications disabled")
            logger.warning("Install with: pip install aiohttp")
            return False

        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

            # Try with Markdown first
            payload = {
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "Markdown"
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=30) as resp:
                    if resp.status == 200:
                        logger.info("Telegram notification sent")
                        return True
                    else:
                        # Markdown failed, try plain text
                        logger.debug("Markdown failed, trying plain text")
                        plain_message = message.replace("*", "").replace("_", "").replace("`", "")
                        payload["text"] = plain_message
                        del payload["parse_mode"]

                        async with session.post(url, json=payload, timeout=30) as resp2:
                            if resp2.status == 200:
                                logger.info("Telegram notification sent (plain text)")
                                return True
                            else:
                                body = await resp2.text()
                                logger.error(f"Telegram error: {resp2.status} - {body}")
                                return False

        except Exception as e:
            logger.error(f"Telegram send error: {e}")
            return False

    def _log_notification(self, title: str, message: str, priority: str):
        """Log notification to history."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "title": title,
            "message": message[:200],
            "priority": priority
        }
        self.notification_history.append(entry)

        # Keep last 100
        if len(self.notification_history) > 100:
            self.notification_history = self.notification_history[-100:]

        logger.info(f"[{priority.upper()}] {title}: {message[:50]}...")

    def get_history(self, limit: int = 20) -> list:
        """Get recent notification history."""
        return self.notification_history[-limit:]


# ============================================
# QUICK TEST
# ============================================

async def test():
    notifier = Notifier()
    print(f"Telegram enabled: {notifier.telegram_enabled}")

    await notifier.send(
        "Agent Test",
        "This is a test notification from the Autonomous Agent.",
        "medium"
    )

if __name__ == "__main__":
    asyncio.run(test())
