#!/usr/bin/env python3
"""
Autonomous Agent - Core Agent Loop
====================================
A persistent background agent that watches, thinks, acts, and reports.

This is the brain that makes the system proactive rather than reactive.
It monitors system state, processes background tasks, and sends
notifications based on configurable triggers.
"""

import asyncio
import json
import os
import sys
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import subprocess
import traceback

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.task_queue import TaskQueue, Task, TaskStatus
from core.decision_engine import DecisionEngine, Decision
from core.notifier import Notifier
from core.context_builder import ContextBuilder
from core.autonomous_triggers import AutonomousTriggers
from core.task_executor import TaskExecutor

# ============================================
# CONFIGURATION
# ============================================

# All paths are relative to the autonomous-agent directory
BASE_DIR = Path(__file__).parent.parent

CONFIG = {
    # Paths (relative to BASE_DIR)
    "live_state_file": os.getenv("AGENT_STATE_FILE", ""),
    "log_dir": str(BASE_DIR / "logs"),
    "queue_db": str(BASE_DIR / "queues" / "tasks.db"),

    # Calendar command (optional - set to your calendar CLI tool)
    # Example: "python3 /path/to/calendar_client.py"
    "calendar_command": os.getenv("AGENT_CALENDAR_COMMAND", ""),

    # Timing (seconds)
    "watch_interval": 30,           # How often to check system state
    "calendar_check_interval": 300,  # Check calendar every 5 min
    "task_process_interval": 60,     # Check task queue every minute

    # Notification settings
    "quiet_hours_start": 22,  # 10 PM
    "quiet_hours_end": 7,     # 7 AM
    "min_notification_gap": 300,  # At least 5 min between notifications

    # Thresholds
    "memory_warning_threshold": 85,  # Warn at 85% memory
    "urgent_email_keywords": ["urgent", "asap", "emergency", "deadline"],

    # Meeting prep
    "meeting_prep_minutes": 15,  # Prepare context 15 min before meetings
}

# ============================================
# LOGGING
# ============================================

log_dir = Path(CONFIG["log_dir"])
log_dir.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(log_dir / "agent.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("autonomous-agent")

# ============================================
# MAIN AGENT CLASS
# ============================================

class AutonomousAgent:
    """The persistent background agent that watches, thinks, acts, and reports."""

    def __init__(self):
        self.running = False
        self.paused = False
        self.last_notification_time = None
        self.last_state_hash = None
        self.session_start = datetime.now()

        # Initialize components
        self.task_queue = TaskQueue(CONFIG["queue_db"])
        self.decision_engine = DecisionEngine(CONFIG)
        self.notifier = Notifier()
        self.context_builder = ContextBuilder(CONFIG)

        # State tracking
        self.state_history: List[Dict] = []
        self.actions_taken: List[Dict] = []
        self.pending_briefings: List[Dict] = []

        # Autonomous triggers - makes the agent self-acting
        self.autonomous_triggers = AutonomousTriggers(self)

        # Task executor - processes task queue
        self.task_executor = TaskExecutor(notifier=self.notifier)

        logger.info("Autonomous Agent initialized")

    # ==========================================
    # STATE WATCHING
    # ==========================================

    def read_live_state(self) -> Dict:
        """Read current system state from state file."""
        try:
            state_file = CONFIG["live_state_file"]
            if state_file and os.path.exists(state_file):
                with open(state_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error reading live state: {e}")
        return {}

    def get_state_hash(self, state: Dict) -> str:
        """Get a hash of relevant state changes."""
        relevant = {
            "active_window": state.get("active_window", ""),
            "app_count": len(state.get("applications", [])),
            "memory_percent": state.get("system", {}).get("memory_percent", 0),
        }
        return json.dumps(relevant, sort_keys=True)

    async def watch_system(self):
        """Watch system state for significant changes."""
        while self.running:
            if self.paused:
                await asyncio.sleep(5)
                continue

            try:
                state = self.read_live_state()
                if not state:
                    await asyncio.sleep(CONFIG["watch_interval"])
                    continue

                current_hash = self.get_state_hash(state)

                # Detect significant changes
                if current_hash != self.last_state_hash:
                    await self.handle_state_change(state)
                    self.last_state_hash = current_hash

                # Check thresholds
                await self.check_system_thresholds(state)

                # Track history (keep last 100)
                self.state_history.append({
                    "timestamp": datetime.now().isoformat(),
                    "state": state
                })
                if len(self.state_history) > 100:
                    self.state_history = self.state_history[-100:]

            except Exception as e:
                logger.error(f"Watch error: {e}")

            await asyncio.sleep(CONFIG["watch_interval"])

    async def handle_state_change(self, state: Dict):
        """Handle significant state changes."""
        # Detect focus changes that might need context
        active = state.get("active_window", "")
        if "meeting" in active.lower() or "teams" in active.lower():
            logger.info(f"Meeting context detected: {active[:50]}")

    async def check_system_thresholds(self, state: Dict):
        """Check if any thresholds are exceeded."""
        system = state.get("system", {})
        memory = system.get("memory_percent", 0)

        if memory > CONFIG["memory_warning_threshold"]:
            await self.maybe_notify(
                "High Memory Usage",
                f"System memory is at {memory}%. Consider closing unused apps.",
                priority="medium"
            )

    # ==========================================
    # CALENDAR WATCHING
    # ==========================================

    async def watch_calendar(self):
        """Watch calendar for upcoming meetings."""
        while self.running:
            if self.paused:
                await asyncio.sleep(5)
                continue

            try:
                if CONFIG.get("calendar_command"):
                    events = await self.get_upcoming_events()

                    for event in events:
                        minutes_until = event.get("minutes_until", 999)

                        # Prepare context before meeting
                        if CONFIG["meeting_prep_minutes"] - 2 <= minutes_until <= CONFIG["meeting_prep_minutes"] + 2:
                            await self.prepare_meeting_context(event)

            except Exception as e:
                logger.error(f"Calendar watch error: {e}")

            await asyncio.sleep(CONFIG["calendar_check_interval"])

    async def get_upcoming_events(self) -> List[Dict]:
        """Get upcoming calendar events using configured command."""
        calendar_cmd = CONFIG.get("calendar_command", "")
        if not calendar_cmd:
            return []

        try:
            parts = calendar_cmd.split()
            result = subprocess.run(
                parts + ["upcoming", "5"],
                capture_output=True,
                timeout=30
            )

            if result.returncode == 0:
                output = result.stdout.decode()
                events = []
                # Parse output - adjust based on your calendar tool's format
                return events

        except Exception as e:
            logger.error(f"Calendar error: {e}")
        return []

    async def prepare_meeting_context(self, event: Dict):
        """Prepare contextual briefing before a meeting."""
        title = event.get("summary", "Meeting")
        attendees = event.get("attendees", [])

        # Build context
        context = await self.context_builder.build_meeting_context(title, attendees)

        await self.maybe_notify(
            f"{title} in {CONFIG['meeting_prep_minutes']} min",
            context,
            priority="high"
        )

    # ==========================================
    # TASK PROCESSING
    # ==========================================

    async def process_task_queue(self):
        """Process background tasks using PARALLEL TaskExecutor."""
        logger.info(f"Parallel task queue processor starting (max workers: {self.task_executor.max_workers})")

        while self.running:
            if self.paused:
                await asyncio.sleep(5)
                continue

            try:
                # Calculate available slots
                available_slots = self.task_executor.max_workers - self.task_executor.active_count

                if available_slots > 0:
                    # Get multiple tasks (up to available slots)
                    tasks = self.task_executor.get_next_tasks(limit=available_slots)

                    if tasks:
                        logger.info(f"Launching {len(tasks)} task(s) in parallel (slots: {available_slots}/{self.task_executor.max_workers})")

                        # Launch all tasks concurrently
                        for task in tasks:
                            logger.info(f"Processing task: #{task['id']} - {task['title']}")
                            asyncio.create_task(
                                self._execute_task_wrapper(task),
                                name=f"task-{task['id']}"
                            )

                        # Brief delay to let tasks start
                        await asyncio.sleep(2)
                    else:
                        # No pending tasks, wait before checking again
                        await asyncio.sleep(CONFIG["task_process_interval"])
                else:
                    # All slots busy, wait a bit before checking again
                    await asyncio.sleep(10)

            except Exception as e:
                logger.error(f"Task processing error: {e}")
                await asyncio.sleep(CONFIG["task_process_interval"])

    async def _execute_task_wrapper(self, task: dict):
        """Wrapper for parallel task execution with error handling."""
        task_id = task['id']
        try:
            await self.task_executor.execute_task(task)
            logger.info(f"Task #{task_id} completed successfully")
        except Exception as e:
            logger.error(f"Task #{task_id} execution error: {e}")

    async def execute_task(self, task: Task):
        """Execute a background task using Claude."""
        self.task_queue.update_status(task.id, TaskStatus.IN_PROGRESS)

        try:
            # Execute via Claude Code CLI
            result = await self.run_claude_task(task.prompt)

            # Update task with result
            self.task_queue.complete_task(task.id, result)

            # Notify user
            await self.maybe_notify(
                f"Task Complete: {task.title}",
                f"{result[:500]}..." if len(result) > 500 else result,
                priority="medium"
            )

        except Exception as e:
            error_msg = str(e)
            self.task_queue.fail_task(task.id, error_msg)

            await self.maybe_notify(
                f"Task Failed: {task.title}",
                error_msg,
                priority="high"
            )

    async def run_claude_task(self, prompt: str) -> str:
        """Run a task through Claude Code CLI."""
        try:
            # --dangerously-skip-permissions is required for non-interactive execution
            proc = await asyncio.create_subprocess_exec(
                'claude', '-p', prompt,
                '--output-format', 'text',
                '--dangerously-skip-permissions',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=300  # 5 minute timeout for background tasks
            )

            return stdout.decode().strip() or "Task completed (no output)"

        except asyncio.TimeoutError:
            return "Task timed out after 5 minutes"
        except Exception as e:
            raise Exception(f"Claude execution error: {e}")

    # ==========================================
    # PROACTIVE ACTIONS
    # ==========================================

    async def run_proactive_checks(self):
        """Run periodic proactive checks."""
        while self.running:
            if self.paused:
                await asyncio.sleep(5)
                continue

            try:
                now = datetime.now()

                # Morning briefing (configurable - default 7:00 AM)
                briefing_hour = int(os.getenv("AGENT_BRIEFING_HOUR", "7"))
                if now.hour == briefing_hour and now.minute < 5:
                    await self.send_morning_briefing()

                # Evening summary (configurable - default 6:00 PM)
                summary_hour = int(os.getenv("AGENT_SUMMARY_HOUR", "18"))
                if now.hour == summary_hour and now.minute < 5:
                    await self.send_evening_summary()

            except Exception as e:
                logger.error(f"Proactive check error: {e}")

            await asyncio.sleep(60)  # Check every minute

    async def send_morning_briefing(self):
        """Send morning briefing."""
        if self.in_quiet_hours():
            return

        briefing = await self.context_builder.build_morning_briefing()

        await self.maybe_notify(
            "Good Morning",
            briefing,
            priority="high",
            force=True  # Always send morning briefing
        )

    async def send_evening_summary(self):
        """Send evening summary."""
        summary = await self.context_builder.build_evening_summary(self.actions_taken)

        await self.maybe_notify(
            "Daily Summary",
            summary,
            priority="medium"
        )

    # ==========================================
    # NOTIFICATION MANAGEMENT
    # ==========================================

    def in_quiet_hours(self) -> bool:
        """Check if we're in quiet hours."""
        hour = datetime.now().hour
        start = CONFIG["quiet_hours_start"]
        end = CONFIG["quiet_hours_end"]

        if start > end:  # Crosses midnight
            return hour >= start or hour < end
        else:
            return start <= hour < end

    async def maybe_notify(self, title: str, message: str, priority: str = "low", force: bool = False):
        """Send notification if appropriate."""

        # Check quiet hours (unless forced)
        if not force and self.in_quiet_hours() and priority != "high":
            logger.info(f"Skipping notification (quiet hours): {title}")
            return

        # Check notification gap (unless forced or high priority)
        if not force and priority != "high" and self.last_notification_time:
            gap = (datetime.now() - self.last_notification_time).seconds
            if gap < CONFIG["min_notification_gap"]:
                logger.info(f"Skipping notification (too soon): {title}")
                return

        # Send notification
        await self.notifier.send(title, message, priority)
        self.last_notification_time = datetime.now()

        # Log action
        self.actions_taken.append({
            "timestamp": datetime.now().isoformat(),
            "type": "notification",
            "title": title,
            "priority": priority
        })

    # ==========================================
    # CONTROL METHODS
    # ==========================================

    def pause(self):
        """Pause the agent."""
        self.paused = True
        logger.info("Agent paused")

    def resume(self):
        """Resume the agent."""
        self.paused = False
        logger.info("Agent resumed")

    def add_task(self, title: str, prompt: str, priority: int = 5) -> int:
        """Add a task to the queue."""
        task_id = self.task_queue.add_task(title, prompt, priority)
        logger.info(f"Task added: {title} (ID: {task_id})")
        return task_id

    def get_status(self) -> Dict:
        """Get agent status."""
        return {
            "running": self.running,
            "paused": self.paused,
            "uptime": str(datetime.now() - self.session_start),
            "pending_tasks": self.task_queue.count_pending(),
            "actions_taken": len(self.actions_taken),
            "last_notification": self.last_notification_time.isoformat() if self.last_notification_time else None
        }

    # ==========================================
    # MAIN LOOP
    # ==========================================

    async def run(self):
        """Main agent loop."""
        self.running = True
        logger.info("=" * 60)
        logger.info("AUTONOMOUS AGENT STARTING")
        logger.info("=" * 60)

        # Start all watchers
        tasks = [
            asyncio.create_task(self.watch_system()),
            asyncio.create_task(self.watch_calendar()),
            asyncio.create_task(self.process_task_queue()),
            asyncio.create_task(self.run_proactive_checks()),
            asyncio.create_task(self.autonomous_triggers.run()),
        ]

        logger.info("All watchers started (including autonomous triggers)")

        # Send startup notification
        await self.notifier.send(
            "Autonomous Agent Online",
            "Agent started with autonomous triggers.\n\n"
            "- Folder watching\n"
            "- Priority email alerts\n"
            "- Pattern learning\n\n"
            "Control via: python agent_control.py",
            "low"
        )

        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            logger.info("Agent shutting down...")
        finally:
            self.running = False

    def stop(self):
        """Stop the agent."""
        self.running = False
        self.autonomous_triggers.stop()
        logger.info("Agent stopped")


# ============================================
# ENTRY POINT
# ============================================

async def main():
    agent = AutonomousAgent()

    try:
        await agent.run()
    except KeyboardInterrupt:
        agent.stop()
        print("\nAgent stopped.")

if __name__ == "__main__":
    asyncio.run(main())
