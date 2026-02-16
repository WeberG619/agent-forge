#!/usr/bin/env python3
"""
System Bridge Watchdog
Monitors the daemon and restarts it if it crashes or becomes unhealthy.

Run as: pythonw watchdog.py (background)
Or: python watchdog.py --console (foreground for testing)
"""

import json
import subprocess
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
import logging
from logging.handlers import RotatingFileHandler

# Configuration
BASE_DIR = Path(__file__).parent
PID_FILE = BASE_DIR / "daemon.pid"
HEALTH_FILE = BASE_DIR / "health.json"
STATE_FILE = BASE_DIR / "live_state.json"
WATCHDOG_LOG = BASE_DIR / "watchdog.log"
DAEMON_SCRIPT = BASE_DIR / "daemon.py"

CHECK_INTERVAL = 30  # seconds between health checks
MAX_STALE_SECONDS = 60  # consider daemon dead if state not updated for this long
MAX_RESTART_ATTEMPTS = 5  # max restarts within restart window
RESTART_WINDOW = 300  # seconds (5 minutes)

# Setup logging
def setup_logging():
    logger = logging.getLogger('watchdog')
    logger.setLevel(logging.INFO)

    handler = RotatingFileHandler(
        WATCHDOG_LOG,
        maxBytes=1024 * 1024,  # 1MB
        backupCount=2
    )
    handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s'
    ))
    logger.addHandler(handler)

    if '--console' in sys.argv:
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'
        ))
        logger.addHandler(console)

    return logger

logger = setup_logging()


class DaemonWatchdog:
    """Monitors and restarts the daemon as needed."""

    def __init__(self):
        self.restart_times = []
        self.running = True

    def is_daemon_running(self) -> bool:
        """Check if daemon process is running."""
        if not PID_FILE.exists():
            return False

        try:
            with open(PID_FILE) as f:
                pid = int(f.read().strip())

            if sys.platform == 'win32':
                # Use tasklist on Windows to avoid os.kill WinError 6
                result = subprocess.run(
                    ['tasklist', '/FI', f'PID eq {pid}', '/NH'],
                    capture_output=True, text=True, timeout=5
                )
                return str(pid) in result.stdout
            else:
                os.kill(pid, 0)
                return True
        except (ProcessLookupError, ValueError, FileNotFoundError, OSError):
            return False
        except PermissionError:
            # Process exists but we can't signal it
            return True

    def is_daemon_healthy(self) -> tuple[bool, str]:
        """Check if daemon is healthy based on health file and state freshness."""
        # Check state file freshness
        if STATE_FILE.exists():
            try:
                with open(STATE_FILE) as f:
                    state = json.load(f)
                last_update = datetime.fromisoformat(state.get("timestamp", "2000-01-01"))
                age = (datetime.now() - last_update).total_seconds()
                if age > MAX_STALE_SECONDS:
                    return False, f"State is stale ({age:.0f}s old)"
            except Exception as e:
                return False, f"Cannot read state file: {e}"
        else:
            return False, "State file missing"

        # Check health file
        if HEALTH_FILE.exists():
            try:
                with open(HEALTH_FILE) as f:
                    health = json.load(f)
                status = health.get("status", "unknown")
                if status == "critical":
                    return False, f"Health status: critical - {health.get('issue', 'unknown')}"
                if status == "degraded":
                    logger.warning(f"Daemon degraded: {health.get('issue', 'unknown')}")
            except Exception as e:
                return False, f"Cannot read health file: {e}"

        return True, "OK"

    def can_restart(self) -> bool:
        """Check if we can restart (haven't exceeded restart limit)."""
        now = datetime.now()
        # Remove old restart times
        self.restart_times = [t for t in self.restart_times
                             if (now - t).total_seconds() < RESTART_WINDOW]

        if len(self.restart_times) >= MAX_RESTART_ATTEMPTS:
            logger.error(f"Too many restarts ({len(self.restart_times)}) in {RESTART_WINDOW}s window")
            return False
        return True

    def start_daemon(self) -> bool:
        """Start the daemon process."""
        try:
            # Platform-specific process creation
            if sys.platform == 'win32':
                try:
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo.wShowWindow = 0  # SW_HIDE

                    subprocess.Popen(
                        ['pythonw', str(DAEMON_SCRIPT)],
                        cwd=str(BASE_DIR),
                        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
                        startupinfo=startupinfo
                    )
                except (AttributeError, OSError):
                    # Fallback if STARTUPINFO fails
                    subprocess.Popen(
                        ['pythonw', str(DAEMON_SCRIPT)],
                        cwd=str(BASE_DIR),
                        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
                    )
            else:
                # Linux/WSL/macOS
                subprocess.Popen(
                    ['python3', str(DAEMON_SCRIPT)],
                    cwd=str(BASE_DIR)
                )

            self.restart_times.append(datetime.now())
            logger.info("Daemon started")

            # Wait a bit and verify it started
            time.sleep(3)
            return self.is_daemon_running()

        except Exception as e:
            logger.error(f"Failed to start daemon: {e}")
            return False

    def run(self):
        """Main watchdog loop."""
        logger.info("Watchdog starting...")

        while self.running:
            try:
                running = self.is_daemon_running()

                if not running:
                    logger.warning("Daemon not running")
                    if self.can_restart():
                        logger.info("Attempting to start daemon...")
                        if self.start_daemon():
                            logger.info("Daemon started successfully")
                        else:
                            logger.error("Failed to start daemon")
                else:
                    healthy, reason = self.is_daemon_healthy()
                    if not healthy:
                        logger.warning(f"Daemon unhealthy: {reason}")
                        # Try to kill and restart
                        if self.can_restart():
                            logger.info("Killing unhealthy daemon...")
                            try:
                                with open(PID_FILE) as f:
                                    pid = int(f.read().strip())
                                os.kill(pid, 9)  # SIGKILL
                                time.sleep(2)
                            except Exception as e:
                                logger.error(f"Could not kill daemon: {e}")

                            logger.info("Attempting restart...")
                            if self.start_daemon():
                                logger.info("Daemon restarted successfully")
                            else:
                                logger.error("Failed to restart daemon")

                time.sleep(CHECK_INTERVAL)

            except KeyboardInterrupt:
                logger.info("Watchdog stopping...")
                self.running = False
            except Exception as e:
                logger.error(f"Watchdog error: {e}")
                time.sleep(60)

        logger.info("Watchdog stopped")


def main():
    if '--status' in sys.argv:
        watchdog = DaemonWatchdog()
        running = watchdog.is_daemon_running()
        healthy, reason = watchdog.is_daemon_healthy()
        print(f"Daemon running: {running}")
        print(f"Daemon healthy: {healthy} ({reason})")
    else:
        watchdog = DaemonWatchdog()
        watchdog.run()


if __name__ == "__main__":
    main()
