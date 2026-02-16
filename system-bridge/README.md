# System Bridge

The System Bridge is a background daemon that monitors your desktop and writes a `live_state.json` file every 10 seconds. Claude Code reads this file to understand what applications you have open, your monitor setup, clipboard contents, and recent files.

Beyond basic monitoring, the System Bridge includes a workflow learning engine, proactive notification system, project intelligence engine, and a watchdog for reliability.

## Architecture

```
watchdog.py ──────────> daemon.py ──────────> live_state.json
(restarts if crashed)   (core monitor)         (read by Claude)
                              │
                              ├── workflow_engine.py
                              │   (learns action patterns, predicts next steps)
                              │
                              ├── notification_system.py
                              │   (toast alerts, reminders, anomaly warnings)
                              │
                              └── project_intelligence.py
                                  (correlates apps to projects, detects mismatches)
```

## Components

### daemon.py — Core Monitor
The main background daemon. Polls open applications, active window, system resources, clipboard, and recent files. Writes `live_state.json` and logs events to `events.ndjson`.

### watchdog.py — Daemon Watchdog
Monitors the daemon process and restarts it if it crashes or becomes unhealthy. Checks health based on PID file, state freshness, and health.json status. Rate-limits restarts to prevent loops (max 5 restarts per 5-minute window).

```bash
# Run the watchdog (foreground)
python3 watchdog.py --console

# Check daemon status
python3 watchdog.py --status
```

### workflow_engine.py — Workflow Learning Engine
Tracks user actions (app switches, file opens, commands), learns sequential patterns, and predicts likely next actions. Uses SQLite for persistent storage and supports anomaly detection.

```bash
# Record an action
python3 workflow_engine.py record app_switch '{"app": "Chrome", "from": "VSCode", "to": "Chrome"}'

# Get predictions
python3 workflow_engine.py predict

# View action history
python3 workflow_engine.py history 20

# Analyze learned patterns
python3 workflow_engine.py analyze

# Backfill from events.ndjson
python3 workflow_engine.py backfill
```

### notification_system.py — Proactive Notifications
Generates and delivers notifications via Windows toast, sound alerts, and log files. Monitors for application mismatches, unfinished work reminders, and time-based alerts. Deduplicates notifications automatically.

```bash
# Run all checks
python3 notification_system.py check

# Send a test toast notification
python3 notification_system.py toast "Hello from Claude"
```

### project_intelligence.py — Project Intelligence
Correlates open applications and window titles to known projects using configurable regex patterns. Detects project mismatches, loads relevant memories, predicts user intent, and generates intelligence briefings.

```bash
# Analyze current state
python3 project_intelligence.py analyze

# Get a human-readable briefing
python3 project_intelligence.py briefing

# Detect the current project
python3 project_intelligence.py project

# Check for mismatches
python3 project_intelligence.py mismatches
```

To configure project detection, create a `project_patterns.json` file in the system-bridge directory:

```json
{
  "my_project": {
    "patterns": ["my.?project", "mp[_\\-\\s]"],
    "aliases": ["My Project", "MP"],
    "path": "/path/to/project"
  }
}
```

## Starting the Daemon

### Windows (WSL)
```bash
# Foreground (for testing)
python3 daemon.py --console

# Background
powershell.exe -Command "Start-Process pythonw -ArgumentList 'daemon.py' -WindowStyle Hidden"
```

### macOS / Linux
```bash
python3 daemon.py &
```

## Checking Status

```bash
python3 daemon.py --status
cat health.json
```

## Stopping

```bash
python3 daemon.py --stop
```

## Platform Support

| Feature | Windows/WSL | macOS | Linux |
|---------|-------------|-------|-------|
| Open applications | Full | Basic | Requires wmctrl |
| Active window | Full | No | No |
| System resources | Full | No | No |
| Clipboard | Full | No | No |
| Recent files | Full | No | No |
| Toast notifications | Full | No | No |

## Files

### Runtime Files
- `live_state.json` — Current system state (updated every 10s)
- `health.json` — Daemon health status
- `events.ndjson` — Event log (app open/close, focus changes)
- `daemon.pid` — Process ID file
- `daemon.log` — Daemon log file
- `watchdog.log` — Watchdog log file

### Data Files
- `workflows.db` — SQLite database of learned workflow patterns
- `learned_patterns.json` — Exported workflow pattern analysis
- `intelligence.json` — Latest project intelligence output
- `notifications.jsonl` — Notification delivery log
- `project_patterns.json` — (Optional) Custom project detection patterns
