#!/usr/bin/env python3
"""
Email Monitor - Pushes email alerts via notification channels.

Reads an email alerts JSON file (written by an external email watcher)
and sends notifications for priority and urgent items.

Three notification tiers:
  1. Priority contacts (configurable domains/addresses) -> all channels + voice
  2. urgent_response category -> all channels + voice
  3. needs_response category -> silent notification only (no voice)

Configuration:
    PROACTIVE_ALERTS_FILE       - Path to email alerts JSON
    PROACTIVE_PRIORITY_DOMAINS  - Comma-separated list of priority email domains
    PROACTIVE_PRIORITY_EMAILS   - Comma-separated list of priority email addresses
"""

import json
import logging
import os
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger("email_monitor")

# Configurable via environment
ALERTS_FILE = Path(
    os.getenv("PROACTIVE_ALERTS_FILE", str(Path(__file__).parent / "email_alerts.json"))
)

# Priority domains and addresses (configurable via env vars)
_domains_env = os.getenv("PROACTIVE_PRIORITY_DOMAINS", "")
PRIORITY_DOMAINS: List[str] = [d.strip() for d in _domains_env.split(",") if d.strip()]

_emails_env = os.getenv("PROACTIVE_PRIORITY_EMAILS", "")
PRIORITY_EMAILS: List[str] = [e.strip() for e in _emails_env.split(",") if e.strip()]


def _is_priority_sender(sender: str) -> bool:
    """Check if sender is from a priority domain or address."""
    sender_lower = sender.lower()
    # Check specific addresses
    for addr in PRIORITY_EMAILS:
        if addr.lower() in sender_lower:
            return True
    # Check domains
    for domain in PRIORITY_DOMAINS:
        if domain.lower() in sender_lower:
            return True
    return False


def _extract_sender_name(from_field: str) -> str:
    """Extract readable name from email From field."""
    # "John Doe <john@example.com>" -> "John Doe"
    if "<" in from_field:
        name = from_field.split("<")[0].strip().strip('"')
        if name:
            return name
    return from_field


class EmailMonitor:
    """Monitors email alerts and pushes notifications."""

    def __init__(self, tracker_state, alerts_file: Path = None):
        self.tracker = tracker_state
        self.alerts_file = alerts_file or ALERTS_FILE

    def check(self):
        """Main check method - called periodically by the scheduler."""
        alerts = self._load_alerts()
        if not alerts:
            return

        alert_list = alerts.get("alerts", [])
        if not alert_list:
            return

        for alert in alert_list:
            email_id = alert.get("id", "")
            if not email_id:
                continue

            # Skip already notified
            if self.tracker.is_email_notified(email_id):
                continue

            category = alert.get("category", "")
            sender = alert.get("from", "")

            # Determine notification tier
            is_priority = _is_priority_sender(sender)
            is_urgent = category == "urgent_response"
            is_needs_response = category == "needs_response"

            if is_priority or is_urgent:
                # Tier 1 & 2: all channels + voice
                self._notify_priority(alert, is_priority)
                self.tracker.mark_email_notified(email_id)
            elif is_needs_response:
                # Tier 3: silent notification only
                self._notify_standard(alert)
                self.tracker.mark_email_notified(email_id)

        # Clean old tracked emails periodically
        self.tracker.clean_old_emails(max_age_hours=48.0)

    def _load_alerts(self) -> Dict:
        """Load email alerts from JSON file."""
        try:
            if self.alerts_file.exists():
                with open(self.alerts_file, "r") as f:
                    return json.load(f)
        except json.JSONDecodeError:
            # File may be mid-write by the email watcher
            logger.debug("Email alerts JSON parse error (likely mid-write)")
        except IOError as e:
            logger.error(f"Failed to read email alerts: {e}")
        return {}

    def _notify_priority(self, alert: Dict, is_priority_contact: bool):
        """Send priority notification (all channels + voice)."""
        sender = _extract_sender_name(alert.get("from", "Unknown"))
        subject = alert.get("subject", "(No subject)")
        account = alert.get("account", "")

        label = "Priority email" if is_priority_contact else "Urgent email"
        message = f"{label} from {sender}: {subject}"
        if account:
            message += f"\n({account})"

        logger.info(f"Priority email alert: {message}")

        try:
            from notify_channels import notify_all

            notify_all(message, voice=True)
        except ImportError:
            print(f"PRIORITY EMAIL: {message}")
        except Exception as e:
            logger.error(f"Failed to send priority email alert: {e}")

    def _notify_standard(self, alert: Dict):
        """Send standard notification (silent, no voice)."""
        sender = _extract_sender_name(alert.get("from", "Unknown"))
        subject = alert.get("subject", "(No subject)")

        message = f"Email needs response from {sender}: {subject}"

        logger.info(f"Standard email alert: {message}")

        try:
            from notify_channels import notify_telegram_only

            notify_telegram_only(message)
        except ImportError:
            print(f"EMAIL ALERT: {message}")
        except Exception as e:
            logger.error(f"Failed to send standard email alert: {e}")


if __name__ == "__main__":
    # Manual test
    from tracker_state import TrackerState

    logging.basicConfig(level=logging.INFO)

    state = TrackerState()
    monitor = EmailMonitor(state)

    print(f"Alerts file: {monitor.alerts_file}")
    print(f"File exists: {monitor.alerts_file.exists()}")
    print(f"Priority domains: {PRIORITY_DOMAINS or '(none configured)'}")
    print(f"Priority emails: {PRIORITY_EMAILS or '(none configured)'}")

    if monitor.alerts_file.exists():
        alerts = monitor._load_alerts()
        print(f"Total alerts: {len(alerts.get('alerts', []))}")
        print(f"Urgent: {alerts.get('urgent_count', 0)}")
        print(f"Needs response: {alerts.get('needs_response_count', 0)}")
        for a in alerts.get("alerts", []):
            print(f"  [{a.get('category')}] {a.get('from', '')[:40]} - {a.get('subject', '')[:50]}")
            print(f"    Priority: {_is_priority_sender(a.get('from', ''))}")

    print("\nRunning check...")
    monitor.check()
    state.save()
    print("Done.")
