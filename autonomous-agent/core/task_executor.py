#!/usr/bin/env python3
"""
Task Executor - Parallel Task Processing via Claude Code
=========================================================
Picks up tasks from the queue and executes them autonomously.
Supports parallel execution - runs multiple tasks simultaneously.
"""

import asyncio
import json
import logging
import sqlite3
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Set

logger = logging.getLogger("autonomous-agent.executor")

# ============================================
# CONFIGURATION
# ============================================

# Paths relative to this file's parent (autonomous-agent/)
BASE_DIR = Path(__file__).parent.parent
TASK_DB = BASE_DIR / "queues" / "tasks.db"
RESULTS_DIR = BASE_DIR / "results"
EXECUTION_LOG = BASE_DIR / "logs" / "executions.log"

# PARALLEL EXECUTION SETTINGS
MAX_PARALLEL_TASKS = 3  # Run up to 3 tasks simultaneously
TASK_TIMEOUT = 1800     # 30 minutes per task

# Ensure directories exist
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
EXECUTION_LOG.parent.mkdir(parents=True, exist_ok=True)

# ============================================
# TASK EXECUTOR CLASS
# ============================================

class TaskExecutor:
    """Executes tasks from the queue via Claude Code CLI with parallel support."""

    def __init__(self, notifier=None, max_workers: int = MAX_PARALLEL_TASKS):
        self.notifier = notifier
        self.max_workers = max_workers
        self.current_tasks: Set[int] = set()  # Track all running task IDs
        self.execution_count = 0
        self.db_lock = threading.Lock()  # Thread-safe DB access
        self._semaphore: Optional[asyncio.Semaphore] = None

    @property
    def current_task_id(self) -> Optional[int]:
        """Backwards compatibility - returns first running task or None."""
        return next(iter(self.current_tasks), None)

    @property
    def active_count(self) -> int:
        """Number of currently running tasks."""
        return len(self.current_tasks)

    def get_next_task(self) -> Optional[Dict]:
        """Get the next pending task from the queue."""
        tasks = self.get_next_tasks(limit=1)
        return tasks[0] if tasks else None

    def get_next_tasks(self, limit: int = 1) -> List[Dict]:
        """Get multiple pending tasks from the queue (for parallel execution)."""
        with self.db_lock:
            try:
                conn = sqlite3.connect(str(TASK_DB))
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()

                # Get highest priority pending tasks, excluding any already running
                running_ids = tuple(self.current_tasks) if self.current_tasks else (0,)

                cur.execute(f"""
                    SELECT * FROM tasks
                    WHERE status = 'pending'
                    AND id NOT IN ({','.join('?' * len(running_ids))})
                    ORDER BY priority DESC, created_at ASC
                    LIMIT ?
                """, (*running_ids, limit))

                rows = cur.fetchall()
                conn.close()

                return [dict(row) for row in rows]

            except Exception as e:
                logger.error(f"Error getting next tasks: {e}")
                return []

    def mark_started(self, task_id: int):
        """Mark a task as started."""
        with self.db_lock:
            try:
                conn = sqlite3.connect(str(TASK_DB))
                cur = conn.cursor()

                now = datetime.now().isoformat()
                cur.execute("""
                    UPDATE tasks
                    SET status = 'in_progress', started_at = ?
                    WHERE id = ?
                """, (now, task_id))

                conn.commit()
                conn.close()
                self.current_tasks.add(task_id)
                logger.info(f"Task #{task_id} marked as in_progress (active: {len(self.current_tasks)})")

            except Exception as e:
                logger.error(f"Error marking task started: {e}")

    def mark_completed(self, task_id: int, result: str, execution_time: float):
        """Mark a task as completed."""
        with self.db_lock:
            try:
                conn = sqlite3.connect(str(TASK_DB))
                cur = conn.cursor()

                now = datetime.now().isoformat()
                cur.execute("""
                    UPDATE tasks
                    SET status = 'completed',
                        completed_at = ?,
                        result = ?
                    WHERE id = ?
                """, (now, result, task_id))

                conn.commit()
                conn.close()
                self.current_tasks.discard(task_id)
                logger.info(f"Task #{task_id} completed in {execution_time:.1f}s (active: {len(self.current_tasks)})")

            except Exception as e:
                logger.error(f"Error marking task completed: {e}")

    def mark_failed(self, task_id: int, error: str, execution_time: float):
        """Mark a task as failed."""
        with self.db_lock:
            try:
                conn = sqlite3.connect(str(TASK_DB))
                cur = conn.cursor()

                now = datetime.now().isoformat()
                cur.execute("""
                    UPDATE tasks
                    SET status = 'failed',
                        completed_at = ?,
                        error = ?
                    WHERE id = ?
                """, (now, error, task_id))

                conn.commit()
                conn.close()
                self.current_tasks.discard(task_id)
                logger.error(f"Task #{task_id} failed after {execution_time:.1f}s: {error} (active: {len(self.current_tasks)})")

            except Exception as e:
                logger.error(f"Error marking task failed: {e}")

    async def execute_task(self, task: Dict) -> bool:
        """Execute a single task via Claude Code CLI (parallel-safe)."""
        task_id = task["id"]
        title = task["title"]
        prompt = task["prompt"]

        logger.info(f"Starting task #{task_id}: {title}")
        self.log_execution(f"START: #{task_id} - {title} (parallel workers: {self.active_count + 1}/{self.max_workers})")

        # Notify start
        if self.notifier:
            await self.notifier.send(
                f"Task Starting: #{task_id}",
                f"{title}\n\nExecuting via Claude Code...",
                "medium"
            )

        # Mark as started
        self.mark_started(task_id)
        start_time = datetime.now()

        try:
            # Execute via Claude Code CLI
            result = await self._run_claude(prompt, timeout=TASK_TIMEOUT)

            execution_time = (datetime.now() - start_time).total_seconds()

            # Save full result to file
            result_file = RESULTS_DIR / f"task_{task_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            result_file.write_text(f"Task #{task_id}: {title}\n{'='*60}\n\n{result}")

            # Mark completed
            self.mark_completed(task_id, result, execution_time)
            self.log_execution(f"COMPLETE: #{task_id} in {execution_time:.1f}s")

            # Notify completion
            if self.notifier:
                summary = result[:800] + "..." if len(result) > 800 else result
                await self.notifier.send(
                    f"Task Complete: #{task_id}",
                    f"{title}\n\nDuration: {execution_time:.1f}s\n\n{summary}",
                    "high"
                )

            self.execution_count += 1
            return True

        except asyncio.TimeoutError:
            execution_time = (datetime.now() - start_time).total_seconds()
            error_msg = f"Task timed out after {execution_time:.0f} seconds"

            self.mark_failed(task_id, error_msg, execution_time)
            self.log_execution(f"TIMEOUT: #{task_id} after {execution_time:.1f}s")

            if self.notifier:
                await self.notifier.send(
                    f"Task Timeout: #{task_id}",
                    f"{title}\n\n{error_msg}",
                    "high"
                )

            return False

        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            error_msg = str(e)

            self.mark_failed(task_id, error_msg, execution_time)
            self.log_execution(f"FAILED: #{task_id} - {error_msg}")

            if self.notifier:
                await self.notifier.send(
                    f"Task Failed: #{task_id}",
                    f"{title}\n\nError: {error_msg}",
                    "high"
                )

            return False

    async def _run_claude(self, prompt: str, timeout: int = 1800) -> str:
        """Run a prompt through Claude Code CLI."""
        try:
            # Create a temporary prompt file for long prompts
            prompt_file = RESULTS_DIR / f"prompt_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            prompt_file.write_text(prompt)

            proc = await asyncio.create_subprocess_exec(
                'claude',
                '-p', prompt,
                '--output-format', 'text',
                '--dangerously-skip-permissions',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout
            )

            output = stdout.decode().strip()

            if proc.returncode != 0:
                stderr_text = stderr.decode().strip()
                if stderr_text and not output:
                    output = f"[Exit code {proc.returncode}]\n{stderr_text}"

            # Clean up prompt file
            prompt_file.unlink(missing_ok=True)

            return output or "Task completed (no output)"

        except asyncio.TimeoutError:
            raise
        except Exception as e:
            raise Exception(f"Claude execution error: {e}")

    def log_execution(self, message: str):
        """Log execution event."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] {message}\n"

        with open(EXECUTION_LOG, "a") as f:
            f.write(log_line)

    async def run_loop(self, check_interval: int = 10):
        """
        Continuous loop to process tasks in parallel.
        Runs up to max_workers tasks simultaneously.
        """
        logger.info(f"Parallel Task Executor starting with {self.max_workers} workers")
        self._semaphore = asyncio.Semaphore(self.max_workers)

        while True:
            try:
                # Get available tasks (up to max_workers)
                available_slots = self.max_workers - self.active_count

                if available_slots > 0:
                    tasks = self.get_next_tasks(limit=available_slots)

                    if tasks:
                        # Launch tasks in parallel
                        logger.info(f"Launching {len(tasks)} task(s) in parallel (slots: {available_slots})")

                        for task in tasks:
                            asyncio.create_task(
                                self._execute_with_logging(task),
                                name=f"task-{task['id']}"
                            )

                # Wait before checking for more tasks
                await asyncio.sleep(check_interval)

            except Exception as e:
                logger.error(f"Task executor loop error: {e}")
                await asyncio.sleep(check_interval)

    async def _execute_with_logging(self, task: Dict):
        """Wrapper to execute task and log completion."""
        task_id = task['id']
        try:
            result = await self.execute_task(task)
            logger.info(f"Task #{task_id} execution finished (success: {result})")
        except Exception as e:
            logger.error(f"Task #{task_id} execution error: {e}")

    def get_stats(self) -> Dict:
        """Get executor statistics."""
        with self.db_lock:
            try:
                conn = sqlite3.connect(str(TASK_DB))
                cur = conn.cursor()

                cur.execute("SELECT status, COUNT(*) FROM tasks GROUP BY status")
                counts = dict(cur.fetchall())

                conn.close()

                return {
                    "parallel_mode": True,
                    "max_workers": self.max_workers,
                    "active_workers": self.active_count,
                    "current_tasks": list(self.current_tasks),
                    "tasks_executed": self.execution_count,
                    "pending": counts.get("pending", 0),
                    "in_progress": counts.get("in_progress", 0),
                    "completed": counts.get("completed", 0),
                    "failed": counts.get("failed", 0),
                }

            except Exception as e:
                logger.error(f"Error getting stats: {e}")
                return {}


# ============================================
# STANDALONE EXECUTION
# ============================================

async def main():
    """Run the task executor as a standalone process."""
    import argparse

    parser = argparse.ArgumentParser(description="Parallel Task Executor")
    parser.add_argument("-w", "--workers", type=int, default=MAX_PARALLEL_TASKS,
                        help=f"Number of parallel workers (default: {MAX_PARALLEL_TASKS})")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s'
    )

    executor = TaskExecutor(max_workers=args.workers)

    print("=" * 60)
    print("Parallel Task Executor Starting")
    print("=" * 60)
    print(f"  Max parallel tasks: {args.workers}")
    print(f"  Task timeout: {TASK_TIMEOUT}s per task")
    print("=" * 60)
    print("Watching for queued tasks...")
    print("Use agent_control.py task to queue new tasks")
    print("=" * 60)

    await executor.run_loop()


if __name__ == "__main__":
    asyncio.run(main())
