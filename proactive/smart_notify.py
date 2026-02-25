#!/usr/bin/env python3
"""
Smart Notification System

Monitors system state and sends proactive notifications
based on configurable rules.

Rules are defined as NotificationRule objects with:
- A trigger type (system_status, app_opened, etc.)
- A condition function
- An action (notify_all, notify_local, notify_telegram, log_only)
- A cooldown to prevent spam

The system reads from a JSON state file (configurable via
PROACTIVE_STATE_FILE env var) and detects changes between cycles.
"""

import json
import logging
import os
import time
from pathlib import Path
from datetime import datetime
from typing import Callable, Dict, List, Optional

logger = logging.getLogger("smart_notify")

# Default state file location (override with PROACTIVE_STATE_FILE env var)
DEFAULT_STATE_FILE = Path(__file__).parent / "system_state.json"


class NotificationRule:
    """A rule for triggering notifications."""

    def __init__(
        self,
        name: str,
        trigger: str,
        condition: Callable,
        action: str,
        message_template: str,
        cooldown_minutes: int = 5,
    ):
        self.name = name
        self.trigger = trigger
        self.condition = condition
        self.action = action
        self.message_template = message_template
        self.cooldown_minutes = cooldown_minutes

    def format_message(self, event: Dict) -> str:
        """Format the notification message."""
        return self.message_template.format(**event)


class SmartNotifier:
    """Smart notification manager for system-level events."""

    def __init__(self, tracker_state=None, state_file: Optional[Path] = None):
        self.tracker = tracker_state
        self.rules: List[NotificationRule] = []
        self.state_file = state_file or Path(
            os.getenv("PROACTIVE_STATE_FILE", str(DEFAULT_STATE_FILE))
        )
        self.last_state = {}
        self._setup_default_rules()

    def _setup_default_rules(self):
        """Set up default notification rules.

        Override or extend this by subclassing or calling add_rule().
        """
        # High memory warning
        self.rules.append(
            NotificationRule(
                name="high_memory",
                trigger="system_status",
                condition=lambda e: e.get("memory_percent", 0) > 85,
                action="notify_local",
                message_template="High memory usage: {memory_percent}%. Consider closing some apps.",
                cooldown_minutes=30,
            )
        )

    def add_rule(self, rule: NotificationRule):
        """Add a custom notification rule."""
        self.rules.append(rule)

    def _check_cooldown(self, rule_name: str, minutes: float) -> bool:
        """Check cooldown using TrackerState if available, else always allow."""
        if self.tracker:
            return self.tracker.check_cooldown(f"smart_{rule_name}", minutes)
        return True  # No tracker = always allow

    def _record_cooldown(self, rule_name: str):
        """Record cooldown."""
        if self.tracker:
            self.tracker.record_cooldown(f"smart_{rule_name}")

    def get_current_state(self) -> Dict:
        """Read current system state from the state file."""
        try:
            if self.state_file.exists():
                return json.loads(self.state_file.read_text())
        except Exception:
            pass
        return {}

    def detect_events(self, old_state: Dict, new_state: Dict) -> List[Dict]:
        """Detect events by comparing old and new states.

        Override this to add custom event detection logic.
        """
        events = []

        # Check system status
        system = new_state.get("system", {})
        if system.get("memory_percent", 0) > 85:
            events.append(
                {"type": "system_status", "memory_percent": system.get("memory_percent", 0)}
            )

        # Check app changes (generic - any new app)
        old_apps = {a.get("name", "") for a in old_state.get("applications", [])}
        for app in new_state.get("applications", []):
            name = app.get("name", "")
            if name and name not in old_apps:
                events.append({"type": "app_opened", "app": name, "title": app.get("title", "")})

        return events

    def send_notification(self, message: str, action: str):
        """Send notification via the specified action channel."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted = f"[{timestamp}] {message}"

        try:
            from .notify_channels import (
                notify_all,
                notify_voice_only,
                notify_telegram_only,
                send_console,
            )
        except ImportError:
            try:
                from notify_channels import (
                    notify_all,
                    notify_voice_only,
                    notify_telegram_only,
                    send_console,
                )
            except ImportError:
                # Ultimate fallback
                print(f"NOTIFY: {formatted}")
                return

        if action == "notify_all":
            logger.info(f"NOTIFY ALL: {formatted}")
            notify_all(message, voice=True)
        elif action == "notify_local":
            logger.info(f"LOCAL: {formatted}")
            notify_voice_only(message)
        elif action == "notify_telegram":
            logger.info(f"TELEGRAM: {formatted}")
            notify_telegram_only(message)
        elif action == "log_only":
            logger.info(f"LOG: {formatted}")
        else:
            logger.info(f"CONSOLE: {formatted}")
            send_console(message)

    def process_events(self, events: List[Dict]):
        """Process detected events against all rules."""
        for event in events:
            for rule in self.rules:
                if rule.condition(event) and self._check_cooldown(rule.name, rule.cooldown_minutes):
                    message = rule.format_message(event)
                    self.send_notification(message, rule.action)
                    self._record_cooldown(rule.name)

    def run_once(self):
        """Run one monitoring cycle."""
        new_state = self.get_current_state()
        events = self.detect_events(self.last_state, new_state)
        self.process_events(events)
        self.last_state = new_state

    def run_continuous(self, interval_seconds: int = 30):
        """Run continuous monitoring."""
        logger.info("=" * 60)
        logger.info("SMART NOTIFICATION SYSTEM ACTIVE")
        logger.info(f"Monitoring every {interval_seconds} seconds...")
        logger.info(f"State file: {self.state_file}")
        logger.info("=" * 60)

        while True:
            try:
                self.run_once()
                time.sleep(interval_seconds)
            except KeyboardInterrupt:
                logger.info("Stopping smart notifications...")
                break
            except Exception as e:
                logger.error(f"Error: {e}")
                time.sleep(interval_seconds)


def main():
    """Main entry point."""
    import sys

    logging.basicConfig(level=logging.INFO)

    notifier = SmartNotifier()

    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        notifier.run_once()
    else:
        notifier.run_continuous()


if __name__ == "__main__":
    main()
