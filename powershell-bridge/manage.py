"""
PowerShell Bridge — Lifecycle Management

Usage:
    python3 manage.py start    # Start the bridge
    python3 manage.py stop     # Stop the bridge
    python3 manage.py status   # Check bridge status
    python3 manage.py restart  # Restart the bridge
"""

import json
import os
import signal
import subprocess
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PID_FILE = os.path.join(SCRIPT_DIR, "bridge.pid")
HEALTH_FILE = os.path.join(SCRIPT_DIR, "health.json")


def _read_pid() -> int | None:
    if not os.path.exists(PID_FILE):
        return None
    try:
        with open(PID_FILE) as f:
            return int(f.read().strip())
    except (ValueError, IOError):
        return None


def _read_health() -> dict | None:
    if not os.path.exists(HEALTH_FILE):
        return None
    try:
        with open(HEALTH_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def _is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _ping_bridge() -> float | None:
    """Ping via client. Returns ms or None."""
    try:
        sys.path.insert(0, SCRIPT_DIR)
        from client import ping

        return ping()
    except Exception:
        return None


def cmd_start():
    pid = _read_pid()
    if pid and _is_alive(pid):
        print(f"Bridge already running (PID {pid})")
        return

    print("Starting PowerShell Bridge...")
    proc = subprocess.Popen(
        [sys.executable, os.path.join(SCRIPT_DIR, "bridge.py"), "--daemon"],
        cwd=SCRIPT_DIR,
    )
    proc.wait()  # The daemon forks, so this returns immediately

    # Wait for it to be ready
    for _ in range(30):
        time.sleep(0.2)
        latency = _ping_bridge()
        if latency is not None:
            pid = _read_pid()
            print(f"Bridge started (PID {pid}, {latency:.0f}ms ping)")
            return

    print("Bridge may have failed to start. Check bridge.log")


def cmd_stop():
    pid = _read_pid()
    if pid is None:
        print("Bridge not running (no PID file)")
        return

    print(f"Stopping bridge (PID {pid})...")
    try:
        os.kill(pid, signal.SIGTERM)
        for _ in range(10):
            time.sleep(0.2)
            if not _is_alive(pid):
                break
        if _is_alive(pid):
            os.kill(pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        pass

    try:
        os.remove(PID_FILE)
    except OSError:
        pass

    print("Bridge stopped")


def cmd_status():
    pid = _read_pid()
    health = _read_health()

    print("PowerShell Bridge Status")
    print("=" * 40)

    if pid and _is_alive(pid):
        latency = _ping_bridge()
        if latency is not None:
            print("  Status:   RUNNING")
            print(f"  PID:      {pid}")
            if health:
                print(f"  PS PID:   {health.get('ps_pid', '?')}")
                print(f"  Port:     {health.get('port', 15776)}")
                print(f"  Uptime:   {health.get('uptime_s', '?')}s")
                print(f"  Requests: {health.get('requests', '?')}")
            print(f"  Latency:  {latency:.0f}ms")
        else:
            print(f"  Status:   UNHEALTHY (PID {pid} alive but not responding)")
    elif pid:
        print(f"  Status:   DEAD (stale PID {pid})")
    else:
        print("  Status:   STOPPED")


def cmd_restart():
    cmd_stop()
    time.sleep(1)
    cmd_start()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    {"start": cmd_start, "stop": cmd_stop, "status": cmd_status, "restart": cmd_restart}.get(
        cmd, lambda: (print("Usage: python3 manage.py {start|stop|status|restart}"), sys.exit(1))
    )()
