---
description: Check live system state - open apps, monitors, clipboard, recent files
---

# System Bridge - Live System State

You are checking the live system state to understand what the user is currently working on.

## Live State File

The system bridge daemon writes to `{{INSTALL_DIR}}/system-bridge/live_state.json`

This file is updated every 10 seconds and contains:

## Information Available

### Open Applications
```json
{
  "open_apps": [
    {"name": "Code", "process": "Code.exe", "window_title": "project - VS Code"},
    {"name": "Chrome", "process": "chrome.exe", "window_title": "GitHub"}
  ]
}
```

### Monitor Configuration
```json
{
  "monitors": {
    "count": 2,
    "primary": "main"
  }
}
```

### Recent Activity
```json
{
  "clipboard": "Last copied text",
  "recent_files": ["file1.py", "file2.ts"],
  "active_window": "Current focused application"
}
```

## Usage

### Read Current State
```bash
cat {{INSTALL_DIR}}/system-bridge/live_state.json 2>/dev/null || echo "System bridge not running"
```

### Check Daemon Health
```bash
cat {{INSTALL_DIR}}/system-bridge/health.json 2>/dev/null
```

## Integration

This information helps Claude:
1. **Proactively understand context** without asking
2. **See what applications are open** for automation
3. **Know the monitor setup** for window management
4. **Access clipboard content** for quick operations
