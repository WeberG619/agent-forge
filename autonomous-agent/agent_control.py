#!/usr/bin/env python3
"""
Agent Control Interface
========================
Control the autonomous agent from external sources (CLI, messaging bots, etc.).

Usage:
    python agent_control.py status
    python agent_control.py task "Do something in background"
    python agent_control.py tasks
    python agent_control.py pause
    python agent_control.py resume
    python agent_control.py briefing
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from core.task_queue import TaskQueue, TaskStatus

# Paths relative to this file
BASE_DIR = Path(__file__).parent
PID_FILE = str(BASE_DIR / "agent.pid")
QUEUE_DB = str(BASE_DIR / "queues" / "tasks.db")
CONTROL_FILE = str(BASE_DIR / "control.json")


def is_agent_running() -> bool:
    """Check if agent is running."""
    try:
        if os.path.exists(PID_FILE):
            with open(PID_FILE) as f:
                pid = int(f.read().strip())
            os.kill(pid, 0)
            return True
    except Exception:
        pass
    return False


def get_status() -> str:
    """Get agent status."""
    running = is_agent_running()
    queue = TaskQueue(QUEUE_DB)

    status_parts = []

    if running:
        with open(PID_FILE) as f:
            pid = f.read().strip()
        status_parts.append(f"Agent is RUNNING (PID: {pid})")
    else:
        status_parts.append("Agent is NOT running")
        status_parts.append("Start with: python run_agent.py --daemon")

    # Task counts
    counts = queue.count_by_status()
    pending = counts.get("pending", 0)
    in_progress = counts.get("in_progress", 0)
    completed = counts.get("completed", 0)

    status_parts.append("\nTask Queue:")
    status_parts.append(f"  Pending: {pending}")
    status_parts.append(f"  In Progress: {in_progress}")
    status_parts.append(f"  Completed: {completed}")

    return "\n".join(status_parts)


def add_task(prompt: str, priority: int = 5) -> str:
    """Add a task to the queue."""
    queue = TaskQueue(QUEUE_DB)

    # Generate title from first line or first 50 chars
    title = prompt.split("\n")[0][:50]
    if len(title) < len(prompt):
        title += "..."

    task_id = queue.add_task(title, prompt, priority)

    return f"Task added (ID: {task_id})\n\nTitle: {title}\nPriority: {priority}\n\nThe agent will process this in the background."


def list_tasks() -> str:
    """List pending and recent tasks."""
    queue = TaskQueue(QUEUE_DB)

    parts = []

    # Pending
    pending = queue.get_all_pending()
    if pending:
        parts.append("Pending Tasks:")
        for task in pending[:5]:
            parts.append(f"  [{task.id}] {task.title}")
    else:
        parts.append("No pending tasks")

    # Recent completed
    completed = queue.get_recent_completed(5)
    if completed:
        parts.append("\nRecently Completed:")
        for task in completed[:3]:
            parts.append(f"  [{task.id}] {task.title}")

    return "\n".join(parts)


def send_control_signal(action: str) -> str:
    """Send control signal to agent."""
    if not is_agent_running():
        return "Agent is not running"

    # Write control signal to file (agent watches this)
    signal = {
        "action": action,
        "timestamp": datetime.now().isoformat()
    }

    with open(CONTROL_FILE, 'w') as f:
        json.dump(signal, f)

    return f"Sent '{action}' signal to agent"


def cancel_task(task_id: int) -> str:
    """Cancel a pending task."""
    queue = TaskQueue(QUEUE_DB)
    task = queue.get_task(task_id)

    if not task:
        return f"Task {task_id} not found"

    if task.status != TaskStatus.PENDING:
        return f"Task {task_id} is {task.status.value}, cannot cancel"

    queue.cancel_task(task_id)
    return f"Task {task_id} cancelled"


def main():
    parser = argparse.ArgumentParser(description="Control the Autonomous Agent")
    subparsers = parser.add_subparsers(dest="command", help="Command")

    # Status
    subparsers.add_parser("status", help="Show agent status")

    # Task
    task_parser = subparsers.add_parser("task", help="Add a background task")
    task_parser.add_argument("prompt", help="Task prompt for Claude")
    task_parser.add_argument("-p", "--priority", type=int, default=5, help="Priority 1-10 (1=highest)")

    # Tasks list
    subparsers.add_parser("tasks", help="List pending tasks")

    # Cancel
    cancel_parser = subparsers.add_parser("cancel", help="Cancel a task")
    cancel_parser.add_argument("task_id", type=int, help="Task ID to cancel")

    # Control signals
    subparsers.add_parser("pause", help="Pause the agent")
    subparsers.add_parser("resume", help="Resume the agent")
    subparsers.add_parser("briefing", help="Request a briefing now")

    args = parser.parse_args()

    if args.command == "status":
        print(get_status())
    elif args.command == "task":
        print(add_task(args.prompt, args.priority))
    elif args.command == "tasks":
        print(list_tasks())
    elif args.command == "cancel":
        print(cancel_task(args.task_id))
    elif args.command == "pause":
        print(send_control_signal("pause"))
    elif args.command == "resume":
        print(send_control_signal("resume"))
    elif args.command == "briefing":
        print(send_control_signal("briefing"))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
