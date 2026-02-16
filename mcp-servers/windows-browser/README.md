# Windows Browser MCP Server

Browser automation from WSL/Windows via PowerShell, CDP, and AutoHotkey. Take screenshots, click, type, scroll, and navigate -- all from Claude Code.

## Requirements

- Windows 10/11 with WSL
- Google Chrome or Microsoft Edge
- [AutoHotkey v2](https://www.autohotkey.com/) (for click/scroll/keyboard)
- Python 3.8+ (Windows Python recommended)

## Setup

```bash
pip install -r requirements.txt
```

Install AutoHotkey v2 on Windows (for reliable mouse/keyboard input).

## Tools

| Tool | Description |
|------|-------------|
| `browser_open` | Launch browser on a specific monitor |
| `browser_navigate` | Navigate to a URL |
| `browser_screenshot` | Take a screenshot of a monitor |
| `browser_click` | Click at coordinates from a screenshot |
| `browser_type` | Type text |
| `browser_send_keys` | Send keyboard shortcuts (Ctrl+C, etc.) |
| `browser_scroll` | Scroll up/down at a position |
| `browser_search` | Google search with screenshot |
| `window_move` | Move a window to a specific monitor |
| `get_monitors` | Detect connected monitors |

## Configuration

Add to your `settings.local.json`:

```json
{
  "mcpServers": {
    "windows-browser": {
      "command": "powershell.exe",
      "args": [
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-Command", "cd 'C:\\path\\to\\windows-browser'; python src/server.py"
      ],
      "disabled": false
    }
  }
}
```

## How It Works

1. **Screenshots**: Uses PowerShell `System.Drawing` to capture monitors
2. **Clicking**: Uses AutoHotkey for reliable cross-monitor mouse input
3. **Keyboard**: AutoHotkey for shortcuts, PowerShell SendKeys for text
4. **Browser**: Chrome/Edge launched with CDP (Chrome DevTools Protocol)
5. **Monitors**: Auto-detects multi-monitor layout including DPI scaling

## Multi-Monitor Support

Automatically detects monitor positions and handles:
- Negative coordinates (left-side monitors)
- DPI scaling (virtual vs physical coordinates)
- Up to 3 monitors (left/center/right)

## Notes

- Must run with Windows Python (not WSL Python) for COM access
- AutoHotkey handles DPI scaling natively
- Screenshots use virtual coordinates (DPI-scaled) for consistency
- Browser CDP runs on port 9222 by default
