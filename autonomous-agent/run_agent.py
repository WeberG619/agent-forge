#!/usr/bin/env python3
"""
Autonomous Agent - Main Entry Point
====================================
Run this to start the background agent.

Usage:
    python run_agent.py              # Run in foreground
    python run_agent.py --daemon     # Run as daemon (background)
    python run_agent.py --status     # Check if running
    python run_agent.py --stop       # Stop the daemon
"""

import os
import sys
import argparse
import asyncio
import signal
import json
from pathlib import Path
from datetime import datetime

# Add core to path
sys.path.insert(0, str(Path(__file__).parent))

from core.agent import AutonomousAgent

# Paths relative to this file
BASE_DIR = Path(__file__).parent
PID_FILE = str(BASE_DIR / "agent.pid")
LOG_FILE = str(BASE_DIR / "logs" / "agent.log")


def save_pid():
    """Save current PID to file."""
    with open(PID_FILE, 'w') as f:
        f.write(str(os.getpid()))


def read_pid() -> int:
    """Read PID from file."""
    try:
        if os.path.exists(PID_FILE):
            with open(PID_FILE) as f:
                return int(f.read().strip())
    except Exception:
        pass
    return 0


def remove_pid():
    """Remove PID file."""
    try:
        os.remove(PID_FILE)
    except Exception:
        pass


def is_running() -> bool:
    """Check if agent is already running."""
    pid = read_pid()
    if pid:
        try:
            os.kill(pid, 0)  # Check if process exists
            return True
        except OSError:
            remove_pid()
    return False


def stop_daemon():
    """Stop the running daemon."""
    pid = read_pid()
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
            print(f"Sent stop signal to agent (PID: {pid})")
            remove_pid()
            return True
        except OSError as e:
            print(f"Could not stop agent: {e}")
            remove_pid()
    else:
        print("Agent is not running")
    return False


def show_status():
    """Show agent status."""
    if is_running():
        pid = read_pid()
        print(f"Agent is RUNNING (PID: {pid})")

        # Read recent log entries
        try:
            with open(LOG_FILE) as f:
                lines = f.readlines()[-10:]
                print("\nRecent log entries:")
                for line in lines:
                    print(f"  {line.rstrip()}")
        except Exception:
            pass
    else:
        print("Agent is NOT running")
        print(f"\nStart with: python {__file__}")


async def main_loop():
    """Main async loop."""
    agent = AutonomousAgent()

    # Handle shutdown signals
    def shutdown(sig, frame):
        print("\nShutdown signal received...")
        agent.stop()
        remove_pid()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Save PID
    save_pid()

    try:
        await agent.run()
    finally:
        remove_pid()


def run_daemon():
    """Run as a daemon process."""
    # Fork to background
    pid = os.fork()
    if pid > 0:
        print(f"Agent started in background (PID: {pid})")
        sys.exit(0)

    # Detach from terminal
    os.setsid()

    # Second fork
    pid = os.fork()
    if pid > 0:
        sys.exit(0)

    # Redirect standard file descriptors
    sys.stdout.flush()
    sys.stderr.flush()

    with open('/dev/null', 'r') as devnull:
        os.dup2(devnull.fileno(), sys.stdin.fileno())

    # Ensure log directory exists
    Path(LOG_FILE).parent.mkdir(parents=True, exist_ok=True)

    log_fd = open(LOG_FILE, 'a')
    os.dup2(log_fd.fileno(), sys.stdout.fileno())
    os.dup2(log_fd.fileno(), sys.stderr.fileno())

    # Run the agent
    asyncio.run(main_loop())


def main():
    parser = argparse.ArgumentParser(description="Autonomous Agent for Claude Code")
    parser.add_argument("--daemon", "-d", action="store_true", help="Run as daemon")
    parser.add_argument("--status", "-s", action="store_true", help="Show status")
    parser.add_argument("--stop", action="store_true", help="Stop the daemon")

    args = parser.parse_args()

    if args.status:
        show_status()
    elif args.stop:
        stop_daemon()
    elif args.daemon:
        if is_running():
            print("Agent is already running!")
            sys.exit(1)
        run_daemon()
    else:
        # Run in foreground
        if is_running():
            print("Agent is already running in background!")
            print("Use --stop to stop it first, or --status to check")
            sys.exit(1)

        print("=" * 60)
        print("AUTONOMOUS AGENT")
        print("=" * 60)
        print("Running in foreground. Press Ctrl+C to stop.")
        print()

        asyncio.run(main_loop())


if __name__ == "__main__":
    main()
