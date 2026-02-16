#!/usr/bin/env python3
"""
Persistent Task Queue for Autonomous Agent
==========================================
SQLite-backed task queue for background work.
"""

import sqlite3
import json
from datetime import datetime
from enum import Enum
from dataclasses import dataclass
from typing import Optional, List
from pathlib import Path


class TaskStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Task:
    id: int
    title: str
    prompt: str
    priority: int  # 1 = highest, 10 = lowest
    status: TaskStatus
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    result: Optional[str] = None
    error: Optional[str] = None


class TaskQueue:
    """Persistent task queue backed by SQLite."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize the database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    priority INTEGER DEFAULT 5,
                    status TEXT DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    result TEXT,
                    error TEXT
                )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority)
            """)

    def add_task(self, title: str, prompt: str, priority: int = 5) -> int:
        """Add a new task to the queue. Returns task ID."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                INSERT INTO tasks (title, prompt, priority, status, created_at)
                VALUES (?, ?, ?, 'pending', ?)
            """, (title, prompt, priority, datetime.now().isoformat()))

            return cursor.lastrowid

    def get_task(self, task_id: int) -> Optional[Task]:
        """Get a task by ID."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM tasks WHERE id = ?",
                (task_id,)
            ).fetchone()

            if row:
                return Task(
                    id=row["id"],
                    title=row["title"],
                    prompt=row["prompt"],
                    priority=row["priority"],
                    status=TaskStatus(row["status"]),
                    created_at=row["created_at"],
                    started_at=row["started_at"],
                    completed_at=row["completed_at"],
                    result=row["result"],
                    error=row["error"]
                )
        return None

    def get_next_pending(self) -> Optional[Task]:
        """Get the next pending task (highest priority first)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("""
                SELECT * FROM tasks
                WHERE status = 'pending'
                ORDER BY priority ASC, created_at ASC
                LIMIT 1
            """).fetchone()

            if row:
                return Task(
                    id=row["id"],
                    title=row["title"],
                    prompt=row["prompt"],
                    priority=row["priority"],
                    status=TaskStatus(row["status"]),
                    created_at=row["created_at"],
                    started_at=row["started_at"],
                    completed_at=row["completed_at"],
                    result=row["result"],
                    error=row["error"]
                )
        return None

    def get_all_pending(self) -> List[Task]:
        """Get all pending tasks."""
        tasks = []
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT * FROM tasks
                WHERE status = 'pending'
                ORDER BY priority ASC, created_at ASC
            """).fetchall()

            for row in rows:
                tasks.append(Task(
                    id=row["id"],
                    title=row["title"],
                    prompt=row["prompt"],
                    priority=row["priority"],
                    status=TaskStatus(row["status"]),
                    created_at=row["created_at"],
                    started_at=row["started_at"],
                    completed_at=row["completed_at"],
                    result=row["result"],
                    error=row["error"]
                ))
        return tasks

    def update_status(self, task_id: int, status: TaskStatus):
        """Update task status."""
        with sqlite3.connect(self.db_path) as conn:
            if status == TaskStatus.IN_PROGRESS:
                conn.execute("""
                    UPDATE tasks SET status = ?, started_at = ?
                    WHERE id = ?
                """, (status.value, datetime.now().isoformat(), task_id))
            else:
                conn.execute("""
                    UPDATE tasks SET status = ?
                    WHERE id = ?
                """, (status.value, task_id))

    def complete_task(self, task_id: int, result: str):
        """Mark task as completed with result."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE tasks
                SET status = 'completed', completed_at = ?, result = ?
                WHERE id = ?
            """, (datetime.now().isoformat(), result, task_id))

    def fail_task(self, task_id: int, error: str):
        """Mark task as failed with error."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE tasks
                SET status = 'failed', completed_at = ?, error = ?
                WHERE id = ?
            """, (datetime.now().isoformat(), error, task_id))

    def cancel_task(self, task_id: int):
        """Cancel a pending task."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE tasks
                SET status = 'cancelled', completed_at = ?
                WHERE id = ? AND status = 'pending'
            """, (datetime.now().isoformat(), task_id))

    def count_pending(self) -> int:
        """Count pending tasks."""
        with sqlite3.connect(self.db_path) as conn:
            result = conn.execute(
                "SELECT COUNT(*) FROM tasks WHERE status = 'pending'"
            ).fetchone()
            return result[0] if result else 0

    def count_by_status(self) -> dict:
        """Count tasks by status."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("""
                SELECT status, COUNT(*) as count
                FROM tasks
                GROUP BY status
            """).fetchall()

            return {row[0]: row[1] for row in rows}

    def get_recent_completed(self, limit: int = 10) -> List[Task]:
        """Get recently completed tasks."""
        tasks = []
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT * FROM tasks
                WHERE status = 'completed'
                ORDER BY completed_at DESC
                LIMIT ?
            """, (limit,)).fetchall()

            for row in rows:
                tasks.append(Task(
                    id=row["id"],
                    title=row["title"],
                    prompt=row["prompt"],
                    priority=row["priority"],
                    status=TaskStatus(row["status"]),
                    created_at=row["created_at"],
                    started_at=row["started_at"],
                    completed_at=row["completed_at"],
                    result=row["result"],
                    error=row["error"]
                ))
        return tasks

    def cleanup_old(self, days: int = 30):
        """Remove completed/failed tasks older than N days."""
        with sqlite3.connect(self.db_path) as conn:
            cutoff = datetime.now().isoformat()[:10]  # Simple date comparison
            conn.execute("""
                DELETE FROM tasks
                WHERE status IN ('completed', 'failed', 'cancelled')
                AND completed_at < date(?, '-' || ? || ' days')
            """, (cutoff, days))
