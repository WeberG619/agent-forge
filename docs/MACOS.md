# macOS Support

This guide covers running Cadre on macOS (Apple Silicon and Intel).

---

## What Works on macOS

| Feature | macOS | Windows/WSL | Notes |
|---------|-------|-------------|-------|
| Core framework (agents, common sense, hooks) | Yes | Yes | Platform-neutral |
| Slash commands | Yes | Yes | Platform-neutral |
| Memory system (claude-memory MCP) | Yes | Yes | Python only |
| System bridge daemon | Yes | Yes | macOS uses `macos_bridge.py` |
| Open applications list | Yes | Yes | via `lsappinfo` / `osascript` |
| Active window title | Yes (needs Accessibility) | Yes | AppleScript |
| Screen resolution / monitor count | Yes | Yes | `system_profiler` |
| Clipboard read | Yes | Yes | `pbpaste` |
| System memory / CPU | Yes | Yes | `sysctl` + `vm_stat` |
| Recent files | Yes | Yes | Finder AppleScript |
| Window move / resize | Yes (needs Accessibility) | Yes | AppleScript |
| Screenshots | Yes | Yes | `screencapture` |
| Browser automation (CDP) | Yes (Chrome) | Yes (Edge) | Same CDP protocol |
| Excel / Word automation | Partial (AppleScript) | Full (COM) | See Office section |
| Voice / TTS | No (stub) | Yes (Edge TTS) | Needs macOS impl |
| PowerShell bridge | No | Yes | Windows/WSL only |

---

## Setup

### 1. Prerequisites

```bash
# macOS ships with Python 3 via Xcode CLT
xcode-select --install

# Verify
python3 --version   # 3.9+ required
git --version
node --version      # optional, for some MCP servers
```

### 2. Run the Installer

```bash
cd /path/to/cadre-ai
chmod +x install.sh
./install.sh
```

The installer detects macOS automatically and will:
- Skip the PowerShell bridge (Windows/WSL only)
- Skip Edge CDP browser server (use Chrome CDP instead)
- Offer the System Bridge with macOS-native monitoring
- Configure Chrome at `/Applications/Google Chrome.app/...`

### 3. System Bridge (Optional)

The system bridge daemon monitors running apps, memory, and clipboard and
writes `~/.cadre-ai/system-bridge/live_state.json` every 10 seconds.

```bash
# Start in foreground (for testing)
python3 ~/.cadre-ai/system-bridge/daemon.py --console

# Start in background
nohup python3 ~/.cadre-ai/system-bridge/daemon.py &

# Check status
cat ~/.cadre-ai/system-bridge/live_state.json | python3 -m json.tool | head -40
```

### 4. Accessibility Permissions

macOS requires explicit Accessibility permission for window management
(move, resize, get active window title).

**System Settings > Privacy & Security > Accessibility**

Add your terminal emulator (Terminal.app, iTerm2, Ghostty, Warp, etc.)
and also **claude** / the Python interpreter that runs the daemon.

Without this permission:
- `get_active_window_title()` returns None
- `move_window()` / `resize_window()` fail silently and return False
- Screenshots of the full screen still work (no permission required)

### 5. Chrome CDP

The macOS browser module (`macos_automation.py`) connects to Chrome via
the same CDP protocol used by the Windows Edge server.

```bash
# Launch Chrome with debugging enabled
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
    --remote-debugging-port=9222 \
    --user-data-dir=/tmp/cadre-chrome &

# Verify CDP is reachable
curl http://127.0.0.1:9222/json/version
```

Or use the Python helper:

```python
from system_bridge.macos_automation import launch_chrome_cdp, cdp_get_targets
launch_chrome_cdp(port=9222)
targets = cdp_get_targets()
print(targets)
```

### 6. Office Automation (Microsoft Office for Mac)

Microsoft Office for Mac ships with a partial AppleScript dictionary.
The stubs in `macos_automation.py` cover the most common operations:

```python
from system_bridge.macos_automation import (
    excel_get_active_workbook,
    excel_get_cell,
    excel_set_cell,
    excel_save_workbook,
    word_insert_text,
)

wb = excel_get_active_workbook()   # "Budget 2026.xlsx"
val = excel_get_cell("Sheet1", "B2")
excel_set_cell("Sheet1", "B2", "42000")
excel_save_workbook()
```

**Limitations vs Windows COM:**
- No row/column iteration helpers (iterate in Python, call per-cell)
- No chart creation via AppleScript
- No conditional formatting via AppleScript
- Word's AppleScript dictionary is smaller than its COM equivalent

---

## Known Limitations

| Area | Limitation | Workaround |
|------|-----------|------------|
| Accessibility | Requires manual Privacy permission grant | One-time setup in System Settings |
| Window titles | Only the front window of each app | Activate the app first |
| Recent files | Reads Finder's list, not MRU per-app | App-specific lists need per-app AppleScript |
| Voice / TTS | No built-in MCP TTS server on macOS | Use `say` command or add an MCP voice server |
| Excel scripting | AppleScript dictionary is incomplete | Export to CSV for complex data, edit, re-import |
| CDP WebSocket | `macos_automation.py` uses HTTP REST only | Full WebSocket CDP needs `websockets` lib (not stdlib) |
| Retina DPI | `screencapture` captures at native resolution | Divide coords by `window.devicePixelRatio` if needed |

---

## Architecture Differences

```
Windows/WSL                          macOS
───────────────────────────────────  ────────────────────────────────────
daemon.py                            daemon.py
  └─ PowerShell via subprocess         └─ macos_bridge.py
       ├─ Get-Process                       ├─ lsappinfo / osascript
       ├─ GetForegroundWindow              ├─ System Events (AppleScript)
       └─ WMI Win32_OperatingSystem        └─ sysctl + vm_stat

powershell-bridge/                   (not applicable)
  └─ bridge.py → server.ps1

mcp-servers/windows-browser/         macos_automation.py
  └─ Edge CDP (port 9222)              └─ Chrome CDP (port 9222)

mcp-servers/excel-mcp/               macos_automation.py
  └─ COM via PowerShell                └─ AppleScript stubs
```

---

## Contributing macOS Improvements

1. **Voice/TTS** — Wrap macOS `say` command or use `AVSpeechSynthesizer`
   via a small Swift CLI shim.

2. **Full CDP WebSocket support** — Add a `websockets`-based CDP client
   (or vendor the tiny `_websocket.py` from the `websocket-client` package)
   so `cdp_evaluate()` and `cdp_click()` work without the MCP server.

3. **Better Office scripting** — JXA (JavaScript for Automation) often
   has a more complete API than AppleScript for Office 365 for Mac.

4. **Launchd daemon** — Add a `com.cadre-ai.daemon.plist` for
   `~/Library/LaunchAgents/` so the system bridge auto-starts on login.

5. **Notification Center** — Use `osascript -e 'display notification...'`
   or the `terminal-notifier` CLI for richer alerts.

PRs welcome — open against the `main` branch, tag `platform:macos`.
