#!/usr/bin/env python3
"""
Context Builder for Autonomous Agent
=====================================
Builds contextual briefings and summaries.

Provides morning briefings, evening summaries, and meeting context
by aggregating information from system state, task queue, and
calendar sources.
"""

import os
import json
import subprocess
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import logging

logger = logging.getLogger("autonomous-agent.context")


class ContextBuilder:
    """
    Builds contextual information for briefings, meetings, and summaries.

    Configure with a config dict containing:
        - live_state_file: path to system state JSON (optional)
        - queue_db: path to task queue database
        - calendar_command: command to fetch calendar events (optional)
    """

    def __init__(self, config: Dict):
        self.config = config
        self.live_state_file = config.get("live_state_file", "")
        self.calendar_command = config.get("calendar_command", "")

    # ==========================================
    # MORNING BRIEFING
    # ==========================================

    async def build_morning_briefing(self) -> str:
        """Build the morning briefing."""
        sections = []
        now = datetime.now()

        # Greeting
        sections.append(f"Good morning! It's {now.strftime('%A, %B %d')}.")

        # Today's calendar (if calendar command is configured)
        if self.calendar_command:
            try:
                calendar = await self._get_today_calendar()
                if calendar:
                    sections.append(f"\nToday's Schedule:\n{calendar}")
                else:
                    sections.append("\nNo meetings scheduled today.")
            except Exception as e:
                logger.error(f"Calendar error: {e}")

        # Pending tasks
        try:
            tasks = await self._get_pending_tasks()
            if tasks:
                sections.append(f"\nPending Tasks:\n{tasks}")
        except Exception as e:
            logger.error(f"Tasks error: {e}")

        # System status (if live state file is configured)
        if self.live_state_file:
            try:
                system = self._get_system_status()
                if system:
                    sections.append(f"\nSystem:\n{system}")
            except Exception as e:
                logger.error(f"System error: {e}")

        return "\n".join(sections)

    # ==========================================
    # EVENING SUMMARY
    # ==========================================

    async def build_evening_summary(self, actions_taken: List[Dict]) -> str:
        """Build the evening summary."""
        sections = []

        # Summary header
        sections.append("Here's your daily summary:")

        # Actions taken today
        today = datetime.now().date().isoformat()
        today_actions = [a for a in actions_taken if a.get("timestamp", "").startswith(today)]

        if today_actions:
            sections.append("\nAgent Activity:")
            sections.append(f"  {len(today_actions)} actions taken today")

            # Categorize
            notifications = len([a for a in today_actions if a.get("type") == "notification"])
            tasks_done = len([a for a in today_actions if a.get("type") == "task_completed"])

            if notifications:
                sections.append(f"  {notifications} notifications sent")
            if tasks_done:
                sections.append(f"  {tasks_done} background tasks completed")
        else:
            sections.append("\nNo significant agent activity today.")

        # Tomorrow's first event (if calendar is configured)
        if self.calendar_command:
            try:
                tomorrow = await self._get_tomorrow_first_event()
                if tomorrow:
                    sections.append(f"\nTomorrow:\n{tomorrow}")
            except Exception as e:
                logger.error(f"Tomorrow calendar error: {e}")

        # System health
        if self.live_state_file:
            system = self._get_system_status()
            if system:
                sections.append(f"\nSystem Health:\n{system}")

        sections.append("\nHave a good evening!")

        return "\n".join(sections)

    # ==========================================
    # MEETING CONTEXT
    # ==========================================

    async def build_meeting_context(self, meeting_title: str, attendees: List[str]) -> str:
        """Build context for an upcoming meeting."""
        sections = []

        sections.append(f"Meeting: {meeting_title}")

        if attendees:
            sections.append(f"\nAttendees: {', '.join(attendees[:5])}")

        return "\n".join(sections)

    # ==========================================
    # HELPERS
    # ==========================================

    async def _get_today_calendar(self) -> Optional[str]:
        """Get today's calendar events using the configured command."""
        if not self.calendar_command:
            return None

        try:
            parts = self.calendar_command.split()
            result = subprocess.run(
                parts + ["today"],
                capture_output=True,
                timeout=30
            )

            if result.returncode == 0:
                output = result.stdout.decode().strip()
                if output and "No events" not in output:
                    lines = output.split("\n")[:5]  # Max 5 events
                    return "\n".join(f"  {line}" for line in lines if line.strip())

        except Exception as e:
            logger.error(f"Calendar fetch error: {e}")

        return None

    async def _get_tomorrow_first_event(self) -> Optional[str]:
        """Get tomorrow's first event."""
        if not self.calendar_command:
            return None

        try:
            parts = self.calendar_command.split()
            result = subprocess.run(
                parts + ["upcoming", "5"],
                capture_output=True,
                timeout=30
            )

            if result.returncode == 0:
                output = result.stdout.decode().strip()
                tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
                for line in output.split("\n"):
                    if tomorrow in line:
                        return f"First event: {line}"

        except Exception as e:
            logger.error(f"Tomorrow calendar error: {e}")

        return None

    def _get_email_status(self) -> Optional[str]:
        """Get email status from live state."""
        try:
            if self.live_state_file and os.path.exists(self.live_state_file):
                with open(self.live_state_file) as f:
                    state = json.load(f)

                email = state.get("email", {})
                unread = email.get("unread_count", 0)
                needs_response = email.get("needs_response_count", 0)
                alerts = email.get("alerts", [])

                parts = []
                if unread:
                    parts.append(f"  {unread} unread")
                if needs_response:
                    parts.append(f"  {needs_response} need response")

                if alerts:
                    for a in alerts[:2]:
                        subj = a.get("subject", "")[:30]
                        frm = a.get("from", "").split("<")[0][:15]
                        parts.append(f"  {frm}: {subj}")

                return "\n".join(parts) if parts else None

        except Exception as e:
            logger.error(f"Email status error: {e}")

        return None

    async def _get_pending_tasks(self) -> Optional[str]:
        """Get pending background tasks."""
        try:
            from core.task_queue import TaskQueue
            queue = TaskQueue(self.config.get("queue_db", ""))

            pending = queue.get_all_pending()
            if pending:
                lines = []
                for task in pending[:5]:
                    lines.append(f"  {task.title}")
                return "\n".join(lines)

        except Exception as e:
            logger.error(f"Task queue error: {e}")

        return None

    def _get_system_status(self) -> Optional[str]:
        """Get brief system status from live state file."""
        try:
            if self.live_state_file and os.path.exists(self.live_state_file):
                with open(self.live_state_file) as f:
                    state = json.load(f)

                system = state.get("system", {})
                mem = system.get("memory_percent", 0)

                apps = state.get("applications", [])

                parts = []
                parts.append(f"  Memory: {mem}%")
                parts.append(f"  Apps: {len(apps)} open")

                return "\n".join(parts)

        except Exception as e:
            logger.error(f"System status error: {e}")

        return None
