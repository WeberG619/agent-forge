#!/usr/bin/env python3
"""
Cadre - System Bridge Daemon
Monitors system state and writes live_state.json for Claude Code context awareness.

Supports: Windows (full), macOS (partial), Linux (partial)

Run as: python daemon.py --console (foreground for testing)
Or: pythonw daemon.py (background on Windows)
"""

import json
import os
import sys
import time
import signal
import socket
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
import logging
from logging.handlers import RotatingFileHandler
import subprocess
import platform

# Configuration
BASE_DIR = Path(os.environ.get("CADRE_DIR", str(Path.home() / ".cadre-ai"))) / "system-bridge"
STATE_FILE = BASE_DIR / "live_state.json"
PID_FILE = BASE_DIR / "daemon.pid"
HEALTH_FILE = BASE_DIR / "health.json"
LOG_FILE = BASE_DIR / "daemon.log"
EVENT_LOG = BASE_DIR / "events.ndjson"

UPDATE_INTERVAL = 10  # seconds
HEALTH_CHECK_INTERVAL = 60
MAX_LOG_SIZE = 5 * 1024 * 1024
LOG_BACKUP_COUNT = 3
IS_WINDOWS = platform.system() == "Windows" or "microsoft" in platform.release().lower()


def setup_logging():
    logger = logging.getLogger('claude_daemon')
    logger.setLevel(logging.INFO)
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(LOG_FILE, maxBytes=MAX_LOG_SIZE, backupCount=LOG_BACKUP_COUNT)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)
    if '--console' in sys.argv:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(console_handler)
    return logger


logger = setup_logging()


class SystemState:
    def __init__(self):
        self.applications: List[Dict] = []
        self.active_window: str = ""
        self.monitors: Dict = {}
        self.system_info: Dict = {}
        self.clipboard: str = ""
        self.recent_files: List[str] = []
        self.last_update: str = ""
        self.events: List[Dict] = []
        self.stats = {"started_at": datetime.now().isoformat(), "updates": 0, "errors": 0}

    def to_dict(self) -> Dict:
        return {
            "timestamp": self.last_update,
            "active_window": self.active_window,
            "monitors": self.monitors,
            "system": self.system_info,
            "clipboard_preview": self.clipboard[:100] + "..." if len(self.clipboard) > 100 else self.clipboard,
            "recent_files": self.recent_files,
            "applications": self.applications,
            "recent_events": self.events[-20:],
            "daemon_stats": self.stats,
            "hostname": socket.gethostname(),
        }


class ClaudeDaemon:
    def __init__(self):
        self.state = SystemState()
        self.previous_apps: set = set()
        self.running = True
        self.consecutive_errors = 0
        self.last_health_check = datetime.now()

        try:
            signal.signal(signal.SIGTERM, self._signal_handler)
            signal.signal(signal.SIGINT, self._signal_handler)
        except Exception:
            pass

        self._write_pid_file()

    def _signal_handler(self, signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        self.running = False

    def _write_pid_file(self):
        try:
            with open(PID_FILE, 'w') as f:
                f.write(str(os.getpid()))
        except Exception as e:
            logger.error(f"Could not write PID file: {e}")

    def _run_powershell(self, cmd: str, timeout: int = 10) -> Optional[str]:
        """Run PowerShell command (Windows/WSL only)."""
        try:
            ps_exe = "powershell.exe" if "microsoft" in platform.release().lower() else "powershell"
            result = subprocess.run(
                [ps_exe, '-NoProfile', '-NonInteractive', '-WindowStyle', 'Hidden', '-ExecutionPolicy', 'Bypass', '-Command', cmd],
                capture_output=True, text=True, timeout=timeout,
            )
            return result.stdout.strip() if result.stdout else None
        except Exception as e:
            logger.debug(f"PowerShell error: {e}")
            return None

    def get_open_applications(self) -> List[Dict]:
        """Get open applications based on platform."""
        if IS_WINDOWS:
            return self._get_apps_windows()
        elif platform.system() == "Darwin":
            return self._get_apps_macos()
        else:
            return self._get_apps_linux()

    def _get_apps_windows(self) -> List[Dict]:
        ps_cmd = '''
Get-Process | Where-Object {$_.MainWindowTitle -ne ""} | ForEach-Object {
    @{ProcessName=$_.ProcessName; MainWindowTitle=$_.MainWindowTitle; Id=$_.Id}
} | ConvertTo-Json -Compress
'''
        output = self._run_powershell(ps_cmd, timeout=15)
        if output:
            try:
                apps = json.loads(output)
                if isinstance(apps, dict):
                    apps = [apps]
                return apps
            except json.JSONDecodeError:
                pass
        return []

    def _get_apps_macos(self) -> List[Dict]:
        try:
            result = subprocess.run(
                ['osascript', '-e', 'tell application "System Events" to get name of every process whose visible is true'],
                capture_output=True, text=True, timeout=5
            )
            if result.stdout:
                names = [n.strip() for n in result.stdout.split(',')]
                return [{"ProcessName": n, "MainWindowTitle": n} for n in names]
        except Exception:
            pass
        return []

    def _get_apps_linux(self) -> List[Dict]:
        try:
            result = subprocess.run(
                ['wmctrl', '-l'], capture_output=True, text=True, timeout=5
            )
            if result.stdout:
                apps = []
                for line in result.stdout.strip().split('\n'):
                    parts = line.split(None, 3)
                    if len(parts) >= 4:
                        apps.append({"ProcessName": parts[2], "MainWindowTitle": parts[3]})
                return apps
        except Exception:
            pass
        return []

    def get_active_window(self) -> str:
        if IS_WINDOWS:
            return self._run_powershell('''
Add-Type @"
using System;using System.Runtime.InteropServices;using System.Text;
public class Win32{[DllImport("user32.dll")]public static extern IntPtr GetForegroundWindow();
[DllImport("user32.dll")]public static extern int GetWindowText(IntPtr hWnd,StringBuilder text,int count);}
"@
$h=[Win32]::GetForegroundWindow();$t=New-Object System.Text.StringBuilder 256;[Win32]::GetWindowText($h,$t,256)|Out-Null;$t.ToString()
''', timeout=5) or ""
        return ""

    def get_system_info(self) -> Dict:
        if IS_WINDOWS:
            output = self._run_powershell(r'''
$mem=Get-CimInstance Win32_OperatingSystem
$memUsed=[math]::Round(($mem.TotalVisibleMemorySize-$mem.FreePhysicalMemory)/1MB,1)
$memTotal=[math]::Round($mem.TotalVisibleMemorySize/1MB,1)
$memPct=[math]::Round((($mem.TotalVisibleMemorySize-$mem.FreePhysicalMemory)/$mem.TotalVisibleMemorySize)*100,0)
@{memory_used_gb=$memUsed;memory_total_gb=$memTotal;memory_percent=$memPct}|ConvertTo-Json -Compress
''', timeout=15)
            if output:
                try:
                    return json.loads(output)
                except Exception:
                    pass
        return {}

    def get_clipboard_text(self) -> str:
        if IS_WINDOWS:
            return self._run_powershell('''
Add-Type -AssemblyName System.Windows.Forms
$c=[System.Windows.Forms.Clipboard]::GetText()
if($c.Length -gt 500){$c=$c.Substring(0,500)+"..."}
$c
''', timeout=3) or ""
        return ""

    def get_recent_files(self) -> List[str]:
        if IS_WINDOWS:
            output = self._run_powershell(r'''
$r=[Environment]::GetFolderPath("Recent")
if(Test-Path $r){Get-ChildItem $r -Filter *.lnk -EA SilentlyContinue|Sort LastWriteTime -Desc|Select -First 10|%{$_.BaseName}}
''', timeout=5)
            if output:
                return [f.strip() for f in output.split('\n') if f.strip() and not f.startswith('$')]
        return []

    def log_event(self, event_type: str, details: str):
        event = {"ts": datetime.now().isoformat(), "type": event_type, "details": details}
        self.state.events.append(event)
        if len(self.state.events) > 100:
            self.state.events = self.state.events[-100:]
        try:
            with open(EVENT_LOG, 'a') as f:
                f.write(json.dumps(event) + '\n')
        except Exception:
            pass

    def detect_changes(self, new_apps: List[Dict]):
        current = {(a.get("ProcessName", ""), a.get("MainWindowTitle", "")) for a in new_apps}
        for app in current - self.previous_apps:
            if app[0] and app[1]:
                self.log_event("app_opened", f"{app[0]}: {app[1]}")
        for app in self.previous_apps - current:
            if app[0] and app[1]:
                self.log_event("app_closed", f"{app[0]}: {app[1]}")
        self.previous_apps = current

    def update_state(self):
        self.state.last_update = datetime.now().isoformat()
        self.state.stats["updates"] += 1

        new_apps = self.get_open_applications()
        self.detect_changes(new_apps)
        self.state.applications = new_apps

        new_active = self.get_active_window()
        if new_active and new_active != self.state.active_window:
            self.state.active_window = new_active

        # Less frequent updates
        if self.state.stats["updates"] % 6 == 0:
            self.state.system_info = self.get_system_info()
            self.state.recent_files = self.get_recent_files()

        if self.state.stats["updates"] % 3 == 0:
            self.state.clipboard = self.get_clipboard_text()

        self.save_state()

    def save_state(self):
        try:
            temp_file = STATE_FILE.with_suffix('.tmp')
            with open(temp_file, 'w') as f:
                json.dump(self.state.to_dict(), f, indent=2)
            temp_file.replace(STATE_FILE)
        except Exception as e:
            logger.error(f"Error saving state: {e}")
            self.state.stats["errors"] += 1

    def health_check(self):
        health = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "pid": os.getpid(),
            "updates": self.state.stats["updates"],
            "errors": self.state.stats["errors"],
            "tracked_apps": len(self.state.applications),
        }
        try:
            with open(HEALTH_FILE, 'w') as f:
                json.dump(health, f, indent=2)
        except Exception:
            pass
        self.last_health_check = datetime.now()

    def run(self):
        logger.info(f"System Bridge Daemon starting (PID: {os.getpid()})...")
        try:
            self.update_state()
            self.health_check()
        except Exception as e:
            logger.error(f"Initial update error: {e}")

        while self.running:
            try:
                time.sleep(UPDATE_INTERVAL)
                self.update_state()
                if (datetime.now() - self.last_health_check).total_seconds() >= HEALTH_CHECK_INTERVAL:
                    self.health_check()
            except KeyboardInterrupt:
                self.running = False
            except Exception as e:
                logger.error(f"Loop error: {e}")
                self.state.stats["errors"] += 1
                time.sleep(30)

        logger.info("Daemon stopped")
        try:
            PID_FILE.unlink(missing_ok=True)
        except Exception:
            pass


def main():
    if '--status' in sys.argv:
        if PID_FILE.exists():
            print(f"Daemon PID: {PID_FILE.read_text().strip()}")
        else:
            print("Daemon is not running")
        return

    if '--stop' in sys.argv:
        if PID_FILE.exists():
            pid = int(PID_FILE.read_text().strip())
            try:
                os.kill(pid, signal.SIGTERM)
                print(f"Sent SIGTERM to PID {pid}")
            except Exception as e:
                print(f"Could not stop: {e}")
        else:
            print("Daemon is not running")
        return

    daemon = ClaudeDaemon()
    daemon.run()


if __name__ == "__main__":
    main()
