#!/usr/bin/env python3
"""
Autonomous Triggers for Self-Acting Agent
==========================================
These triggers make the agent act on its own based on context,
not just when commanded.

THE WATCHER - Detects events and spawns workflows automatically.

Configure watched folders and priority senders in config.json or
by modifying the WATCH_FOLDERS and PRIORITY_SENDERS lists below.
"""

import os
import json
import asyncio
import logging
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field

# Import the agent dispatcher
from core.agent_dispatcher import AgentDispatcher, DispatchEvent

logger = logging.getLogger("autonomous-agent.triggers")

# ============================================
# CONFIGURATION
# ============================================
# Customize these for your workflow.
# You can also load from a config file.

WATCH_FOLDERS = [
    # Example: Watch Downloads for new PDFs
    # {
    #     "path": "/path/to/Downloads",
    #     "patterns": ["*.pdf"],
    #     "action": "process_pdf",
    #     "description": "Process new PDFs in Downloads"
    # },
    # {
    #     "path": "/path/to/client/folder",
    #     "patterns": ["*.pdf", "*.xlsx", "*.docx"],
    #     "action": "notify_new_client_file",
    #     "description": "Alert on new client files"
    # }
]

PRIORITY_SENDERS = [
    # Example: Add your priority contacts
    # {"email": "boss@company.com", "name": "Boss", "priority": "critical"},
    # {"email": "client@example.com", "name": "Client", "priority": "high"},
]


@dataclass
class TriggerEvent:
    """An event that can trigger autonomous action."""

    trigger_type: str
    timestamp: datetime
    data: Dict
    handled: bool = False


@dataclass
class WatchedFolder:
    """A folder being watched for changes."""

    path: str
    patterns: List[str]
    action: str
    known_files: Set[str] = field(default_factory=set)
    last_scan: Optional[datetime] = None


# ============================================
# AUTONOMOUS TRIGGER SYSTEM
# ============================================


class AutonomousTriggers:
    """
    Watches for context changes and triggers autonomous actions.
    This is what makes the agent truly self-acting.

    To add custom triggers, subclass this and override the run() method,
    or add watched folders and priority senders to the configuration lists.
    """

    def __init__(self, agent):
        self.agent = agent
        self.running = False

        # State tracking
        self.last_active_window: Optional[str] = None
        self.watched_folders: List[WatchedFolder] = []
        self.pending_events: List[TriggerEvent] = []
        self.action_cooldowns: Dict[str, datetime] = {}

        # Pattern learning
        self.activity_log: List[Dict] = []
        self.learned_patterns: List[Dict] = []

        # Agent Dispatcher for autonomous execution
        self.dispatcher = AgentDispatcher(notifier=agent.notifier)

        # Load config from file if available
        self._load_config()

        # Initialize watched folders
        self._init_watched_folders()

        logger.info("Autonomous Triggers initialized")

    def _load_config(self):
        """Load trigger configuration from config file if available."""
        config_file = Path(__file__).parent.parent / "config.json"
        if config_file.exists():
            try:
                with open(config_file) as f:
                    config = json.load(f)

                # Override defaults with config file values
                global WATCH_FOLDERS, PRIORITY_SENDERS
                if "watch_folders" in config:
                    WATCH_FOLDERS.extend(config["watch_folders"])
                if "priority_senders" in config:
                    PRIORITY_SENDERS.extend(config["priority_senders"])

                logger.info(f"Loaded trigger config from {config_file}")
            except Exception as e:
                logger.error(f"Error loading config: {e}")

    def _init_watched_folders(self):
        """Initialize folder watchers."""
        for config in WATCH_FOLDERS:
            path = config["path"]
            if os.path.exists(path):
                wf = WatchedFolder(path=path, patterns=config["patterns"], action=config["action"])
                # Initial scan to know existing files
                wf.known_files = self._scan_folder(path, config["patterns"])
                wf.last_scan = datetime.now()
                self.watched_folders.append(wf)
                logger.info(f"Watching folder: {path}")
            else:
                logger.warning(f"Watch folder not found: {path}")

    def _scan_folder(self, path: str, patterns: List[str]) -> Set[str]:
        """Scan folder for files matching patterns."""
        files = set()
        try:
            folder = Path(path)
            for pattern in patterns:
                for f in folder.glob(pattern):
                    if f.is_file():
                        # Use path + mtime as unique identifier
                        stat = f.stat()
                        file_id = f"{f.name}:{stat.st_mtime}"
                        files.add(file_id)
        except Exception as e:
            logger.error(f"Error scanning {path}: {e}")
        return files

    def _check_cooldown(self, action_key: str, cooldown_minutes: int = 15) -> bool:
        """Check if action is in cooldown period."""
        if action_key in self.action_cooldowns:
            elapsed = datetime.now() - self.action_cooldowns[action_key]
            if elapsed < timedelta(minutes=cooldown_minutes):
                return False
        return True

    def _set_cooldown(self, action_key: str):
        """Set cooldown for an action."""
        self.action_cooldowns[action_key] = datetime.now()

    # ==========================================
    # TRIGGER: FOLDER WATCHER
    # ==========================================

    async def check_watched_folders(self):
        """
        Monitor folders for new files and process them automatically.
        """
        for wf in self.watched_folders:
            try:
                current_files = self._scan_folder(wf.path, wf.patterns)
                new_files = current_files - wf.known_files

                if new_files:
                    for file_id in new_files:
                        filename = file_id.split(":")[0]
                        filepath = os.path.join(wf.path, filename)

                        logger.info(f"New file detected: {filepath}")

                        # Execute action
                        await self._execute_folder_action(wf.action, filepath, filename)

                    # Update known files
                    wf.known_files = current_files

                wf.last_scan = datetime.now()

            except Exception as e:
                logger.error(f"Error checking folder {wf.path}: {e}")

    async def _execute_folder_action(self, action: str, filepath: str, filename: str):
        """Execute action for a new file."""

        if action == "process_pdf":
            # Check if it might be a floor plan
            is_floor_plan = self._quick_floor_plan_check(filename)

            if is_floor_plan:
                logger.info(f"Dispatching floor-plan-processor for: {filename}")
                event = DispatchEvent(
                    trigger_type="new_pdf_floor_plan",
                    data={"filepath": filepath, "filename": filename, "source": "folder watch"},
                    priority="high",
                )
                await self.dispatcher.dispatch(event)
            else:
                # Notify for non-floor-plan PDFs
                await self.agent.notifier.send(
                    "New PDF Detected", f"{filename}\n\nPath: {filepath}", "low"
                )

            self._log_activity(
                "pdf_detected", {"filename": filename, "is_floor_plan": is_floor_plan}
            )

        elif action == "notify_new_client_file":
            logger.info(f"New client file: {filename}")
            file_ext = Path(filename).suffix.lower()

            event = DispatchEvent(
                trigger_type="new_client_file",
                data={
                    "filepath": filepath,
                    "filename": filename,
                    "event_type": "client file",
                    "contact_name": "Client",
                    "subject": f"New file: {filename}",
                },
                priority="medium",
            )
            await self.dispatcher.dispatch(event)

            self._log_activity(
                "client_file_detected", {"filename": filename, "file_type": file_ext}
            )

        else:
            # Unknown action - just notify
            await self.agent.notifier.send(
                "New File Detected", f"Folder: {os.path.dirname(filepath)}\nFile: {filename}", "low"
            )

    def _quick_floor_plan_check(self, filename: str) -> bool:
        """Quick heuristic check if a file might be a floor plan."""
        floor_plan_keywords = ["floor", "plan", "layout", "architectural", "level", "l1", "l2"]
        filename_lower = filename.lower()
        return any(kw in filename_lower for kw in floor_plan_keywords)

    # ==========================================
    # TRIGGER: PRIORITY EMAIL WATCHER
    # ==========================================

    async def check_priority_emails(self, state: Dict):
        """
        Watch for emails from priority senders and dispatch agents to handle them.
        """
        if not PRIORITY_SENDERS:
            return

        email_state = state.get("email", {})
        alerts = email_state.get("alerts", [])

        for alert in alerts:
            from_addr = alert.get("from", "").lower()
            subject = alert.get("subject", "")
            preview = alert.get("preview", "")
            alert_id = alert.get("id", hashlib.md5(f"{from_addr}{subject}".encode()).hexdigest())

            # Check cooldown (don't process same email twice)
            cooldown_key = f"email_alert:{alert_id}"
            if not self._check_cooldown(cooldown_key, 60):  # 1 hour cooldown per email
                continue

            # Check if from priority sender
            for sender in PRIORITY_SENDERS:
                if sender["email"].lower() in from_addr:
                    self._set_cooldown(cooldown_key)

                    priority = sender["priority"]
                    name = sender["name"]

                    # Dispatch client-liaison for priority emails
                    logger.info(f"Priority email from {name}: {subject[:50]}")
                    event = DispatchEvent(
                        trigger_type=f"priority_email_{priority}",
                        data={
                            "event_type": "priority email",
                            "contact_name": name,
                            "subject": subject,
                            "preview": preview[:500],
                        },
                        priority=priority,
                    )
                    await self.dispatcher.dispatch(event)

                    self._log_activity(
                        "priority_email_detected", {"from": name, "subject": subject}
                    )
                    break

    # ==========================================
    # TRIGGER: WORK SESSION DETECTOR
    # ==========================================

    async def check_work_session(self, state: Dict):
        """
        Detect when a work session starts/ends and offer assistance.
        Configure work_apps list to match your development tools.
        """
        active_window = state.get("active_window", "")
        apps = state.get("applications", [])

        # Detect work apps - customize this list
        work_apps = ["Code", "Cursor", "PyCharm", "IntelliJ", "WebStorm", "Terminal"]
        active_work_apps = [
            a for a in apps if any(w in a.get("ProcessName", "") for w in work_apps)
        ]

        if active_work_apps and not self.last_active_window:
            # Work session starting
            cooldown_key = "work_session_start"
            if self._check_cooldown(cooldown_key, 120):  # 2 hour cooldown
                self._set_cooldown(cooldown_key)

                app_names = [a.get("ProcessName") for a in active_work_apps]
                await self.agent.notifier.send(
                    "Work Session Started",
                    f"Detected: {', '.join(app_names)}\n\nUse agent_control.py task to queue background work.",
                    "low",
                )

        self.last_active_window = active_window

    # ==========================================
    # PATTERN LEARNING
    # ==========================================

    def _log_activity(self, activity_type: str, data: Dict):
        """Log activity for pattern learning."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "hour": datetime.now().hour,
            "day_of_week": datetime.now().strftime("%A"),
            "type": activity_type,
            "data": data,
        }
        self.activity_log.append(entry)

        # Keep last 1000 entries
        if len(self.activity_log) > 1000:
            self.activity_log = self.activity_log[-1000:]

        # Periodically analyze patterns
        if len(self.activity_log) % 50 == 0:
            self._analyze_patterns()

    def _analyze_patterns(self):
        """Analyze activity log to find patterns."""
        if len(self.activity_log) < 20:
            return

        # Simple pattern detection - count activities by hour
        hour_counts = {}
        for entry in self.activity_log:
            hour = entry.get("hour", 0)
            activity = entry.get("type", "unknown")
            key = f"{hour}:{activity}"
            hour_counts[key] = hour_counts.get(key, 0) + 1

        # Find frequent patterns
        patterns = []
        for key, count in hour_counts.items():
            if count >= 3:  # At least 3 occurrences
                hour, activity = key.split(":", 1)
                patterns.append({"hour": int(hour), "activity": activity, "frequency": count})

        self.learned_patterns = patterns
        logger.info(f"Learned {len(patterns)} patterns from activity")

    async def apply_learned_patterns(self):
        """Apply learned patterns proactively."""
        if not self.learned_patterns:
            return

        current_hour = datetime.now().hour

        for pattern in self.learned_patterns:
            if pattern["hour"] == current_hour:
                activity = pattern["activity"]

                # Check cooldown
                cooldown_key = f"pattern:{activity}:{current_hour}"
                if not self._check_cooldown(cooldown_key, 60):
                    continue

                # Log pattern detection (could auto-execute for high frequency patterns)
                if pattern["frequency"] >= 5:
                    logger.info(f"Pattern detected: frequent {activity} at {current_hour}:00")

    # ==========================================
    # MAIN LOOP
    # ==========================================

    async def run(self):
        """Main trigger checking loop."""
        self.running = True
        logger.info("Autonomous triggers active")

        while self.running:
            try:
                # Read current state
                state = self.agent.read_live_state()

                # Run all trigger checks
                if state:
                    await self.check_priority_emails(state)
                    await self.check_work_session(state)

                # Folder watching (less frequent)
                if datetime.now().second < 10:  # Once per minute
                    await self.check_watched_folders()

                # Pattern application (less frequent)
                if datetime.now().minute % 15 == 0 and datetime.now().second < 10:
                    await self.apply_learned_patterns()

            except Exception as e:
                logger.error(f"Trigger loop error: {e}")

            await asyncio.sleep(10)  # Check every 10 seconds

    def stop(self):
        """Stop the trigger system."""
        self.running = False
