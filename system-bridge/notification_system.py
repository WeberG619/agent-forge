#!/usr/bin/env python3
"""
Proactive Notification System
Monitors system state and generates alerts/notifications for:
1. Application mismatches
2. Unusual patterns
3. Reminders for unfinished work
4. Suggested optimizations
5. Time-based reminders

Can notify via:
- Windows toast notifications
- Sound alerts
- Log file
- Console output
"""

import json
import subprocess
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum

# Paths
BASE_DIR = Path(__file__).parent
NOTIFICATIONS_LOG = BASE_DIR / "notifications.jsonl"
STATE_FILE = BASE_DIR / "live_state.json"


class Priority(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

@dataclass
class Notification:
    """A notification to show the user."""
    title: str
    message: str
    priority: Priority
    category: str  # mismatch, reminder, suggestion, warning, info
    timestamp: str
    actions: List[Dict] = None
    auto_dismiss_seconds: int = 0

    def to_dict(self) -> Dict:
        return {
            "title": self.title,
            "message": self.message,
            "priority": self.priority.name,
            "category": self.category,
            "timestamp": self.timestamp,
            "actions": self.actions or [],
            "auto_dismiss_seconds": self.auto_dismiss_seconds
        }


class NotificationEngine:
    """Engine for generating and delivering notifications."""

    def __init__(self):
        self.delivered = set()  # Track delivered notifications to avoid duplicates

    def _get_notification_id(self, notification: Notification) -> str:
        """Generate unique ID for a notification."""
        return f"{notification.category}:{notification.title}:{notification.message[:50]}"

    def send_windows_toast(self, notification: Notification) -> bool:
        """Send Windows toast notification."""
        ps_script = f'''
        [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
        [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null

        $template = @"
        <toast>
            <visual>
                <binding template="ToastText02">
                    <text id="1">{notification.title}</text>
                    <text id="2">{notification.message[:200]}</text>
                </binding>
            </visual>
        </toast>
"@

        $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
        $xml.LoadXml($template)
        $toast = New-Object Windows.UI.Notifications.ToastNotification $xml
        [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Claude Code").Show($toast)
        '''

        try:
            subprocess.run(
                ['powershell', '-Command', ps_script],
                capture_output=True, timeout=10
            )
            return True
        except Exception as e:
            print(f"Toast notification failed: {e}")
            return False

    def send_sound_alert(self, priority: Priority):
        """Play a sound alert based on priority."""
        ps_script = '''
        $sound = New-Object System.Media.SoundPlayer
        $sound.SoundLocation = "C:\\Windows\\Media\\notify.wav"
        $sound.Play()
        '''

        try:
            subprocess.run(['powershell', '-Command', ps_script], capture_output=True, timeout=5)
        except Exception:
            pass

    def log_notification(self, notification: Notification):
        """Log notification to file."""
        with open(NOTIFICATIONS_LOG, 'a') as f:
            f.write(json.dumps(notification.to_dict()) + '\n')

    def deliver(self, notification: Notification, toast: bool = True, sound: bool = False):
        """Deliver a notification through configured channels."""
        notif_id = self._get_notification_id(notification)

        # Check for duplicate
        if notif_id in self.delivered:
            return False

        self.delivered.add(notif_id)

        # Log
        self.log_notification(notification)

        # Toast
        if toast and notification.priority.value >= Priority.MEDIUM.value:
            self.send_windows_toast(notification)

        # Sound
        if sound and notification.priority.value >= Priority.HIGH.value:
            self.send_sound_alert(notification.priority)

        return True


class ProactiveMonitor:
    """Monitors system and generates proactive notifications."""

    def __init__(self, memory_db_path: Optional[Path] = None):
        self.engine = NotificationEngine()
        self.last_check = {}
        self.memory_db_path = memory_db_path

    def check_app_mismatch(self, state: Dict) -> Optional[Notification]:
        """Check for project mismatches between open applications.

        Compares document names across all running applications and alerts
        if two apps appear to be working on different projects.
        Override this method or configure app_pairs to define which
        application pairs should be compared.
        """
        # Generic mismatch detection: compare apps that have 'document' fields
        apps_with_docs = {}
        for app_name, app_state in state.items():
            if isinstance(app_state, dict) and app_state.get("document"):
                apps_with_docs[app_name] = app_state

        if len(apps_with_docs) < 2:
            return None

        # Compare each pair of apps
        app_names = list(apps_with_docs.keys())
        for i in range(len(app_names)):
            for j in range(i + 1, len(app_names)):
                name_a = app_names[i]
                name_b = app_names[j]
                doc_a = apps_with_docs[name_a].get("document", "").lower()
                doc_b = apps_with_docs[name_b].get("document", "").lower()

                if doc_a and doc_b:
                    # Extract project-like words
                    words_a = set(doc_a.replace("-", " ").replace("_", " ").split())
                    words_b = set(doc_b.replace("-", " ").replace("_", " ").split())

                    # Check for overlap
                    common = words_a & words_b
                    significant_common = {w for w in common if len(w) > 3}

                    if len(significant_common) < 2:  # Not enough overlap
                        return Notification(
                            title="Project Mismatch Detected",
                            message=f"{name_a}: {apps_with_docs[name_a].get('document', 'Unknown')}\n"
                                    f"{name_b}: {apps_with_docs[name_b].get('document', 'Unknown')}",
                            priority=Priority.HIGH,
                            category="mismatch",
                            timestamp=datetime.now().isoformat(),
                            actions=[
                                {"label": f"Switch {name_a}", "action": f"switch_{name_a}"},
                                {"label": f"Switch {name_b}", "action": f"switch_{name_b}"},
                                {"label": "Ignore", "action": "ignore"}
                            ]
                        )

        return None

    def check_unfinished_work(self) -> List[Notification]:
        """Check for unfinished work reminders from memory database."""
        notifications = []

        if not self.memory_db_path or not self.memory_db_path.exists():
            return notifications

        conn = sqlite3.connect(self.memory_db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Find session summaries with next steps
        cursor.execute("""
            SELECT content, project, created_at FROM memories
            WHERE tags LIKE '%session-summary%'
            AND content LIKE '%### Next Steps%'
            ORDER BY created_at DESC
            LIMIT 3
        """)

        for row in cursor.fetchall():
            created = datetime.fromisoformat(row['created_at'].replace(' ', 'T'))

            # Only remind if > 1 hour old
            if datetime.now() - created > timedelta(hours=1):
                content = row['content']
                if '### Next Steps' in content:
                    steps = content.split('### Next Steps')[1].split('###')[0]
                    first_step = steps.strip().split('\n')[0] if steps else "Continue work"

                    notifications.append(Notification(
                        title=f"Unfinished: {row['project'] or 'Project'}",
                        message=first_step[:100],
                        priority=Priority.MEDIUM,
                        category="reminder",
                        timestamp=datetime.now().isoformat()
                    ))

        conn.close()
        return notifications

    def check_time_based_reminders(self) -> List[Notification]:
        """Generate time-based reminders."""
        notifications = []
        now = datetime.now()

        # End of day reminder (after 5 PM)
        if now.hour >= 17:
            notifications.append(Notification(
                title="End of Day",
                message="Consider summarizing today's work before ending session.",
                priority=Priority.LOW,
                category="reminder",
                timestamp=now.isoformat(),
                auto_dismiss_seconds=300
            ))

        # Periodic save reminder (every hour on the hour)
        if now.minute == 0:
            notifications.append(Notification(
                title="Periodic Save Reminder",
                message="Make sure your work is saved.",
                priority=Priority.LOW,
                category="reminder",
                timestamp=now.isoformat(),
                auto_dismiss_seconds=60
            ))

        return notifications

    def run_checks(self, state: Dict = None) -> List[Dict]:
        """Run all checks and return notifications."""
        if state is None:
            if STATE_FILE.exists():
                with open(STATE_FILE) as f:
                    state = json.load(f)
            else:
                state = {}

        all_notifications = []

        # App mismatch
        mismatch = self.check_app_mismatch(state)
        if mismatch:
            all_notifications.append(mismatch)

        # Unfinished work
        all_notifications.extend(self.check_unfinished_work())

        # Time-based
        all_notifications.extend(self.check_time_based_reminders())

        # Deliver all
        results = []
        for notif in all_notifications:
            delivered = self.engine.deliver(notif, toast=True, sound=False)
            results.append({
                **notif.to_dict(),
                "delivered": delivered
            })

        return results


def main():
    """CLI interface."""
    import sys

    monitor = ProactiveMonitor()

    if len(sys.argv) > 1:
        cmd = sys.argv[1]

        if cmd == "check":
            results = monitor.run_checks()
            print(json.dumps({"notifications": results}, indent=2))

        elif cmd == "toast":
            # Send a test toast
            notif = Notification(
                title="Test Notification",
                message=sys.argv[2] if len(sys.argv) > 2 else "This is a test from Claude Code",
                priority=Priority.MEDIUM,
                category="info",
                timestamp=datetime.now().isoformat()
            )
            monitor.engine.send_windows_toast(notif)
            print('{"status": "sent"}')

        else:
            print(f'{{"error": "Unknown command: {cmd}"}}')
    else:
        # Default: run all checks
        results = monitor.run_checks()
        print(json.dumps({"notifications": results}, indent=2))


if __name__ == "__main__":
    main()
