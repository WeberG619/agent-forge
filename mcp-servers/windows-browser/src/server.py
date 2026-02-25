#!/usr/bin/env python3
"""
Windows Browser MCP Server
Controls Windows browsers from WSL via PowerShell and CDP
"""

import asyncio
import json
import subprocess
import sys
import os
import base64
import tempfile
import time
from datetime import datetime
from typing import Dict, Any, List
import urllib.request
import urllib.error

# PowerShell Bridge — faster than subprocess.run(powershell.exe...)
# Set POWERSHELL_BRIDGE_PATH env var if you have a persistent PS bridge
_BRIDGE_PATH = os.environ.get("POWERSHELL_BRIDGE_PATH", "")
if _BRIDGE_PATH:
    sys.path.insert(0, _BRIDGE_PATH)
try:
    from client import run_powershell as _ps_bridge
    _HAS_BRIDGE = True
except ImportError:
    _HAS_BRIDGE = False

# MCP SDK imports
try:
    from mcp.server import Server
    from mcp.types import (
        Tool,
        TextContent,
        ImageContent,
    )
    from mcp.server.stdio import stdio_server
except ImportError:
    print("MCP SDK not installed. Run: pip install mcp", file=sys.stderr)
    sys.exit(1)

# Configuration
DEFAULT_MONITOR = "center"  # left, center, right, or primary
CDP_PORT = 9222
SCREENSHOT_DIR = os.environ.get("BROWSER_SCREENSHOT_DIR", os.path.join(tempfile.gettempdir(), "browser-mcp-screenshots"))
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

# Monitor positions (will be detected dynamically)
MONITORS = {
    "left": {"x": -5120, "y": 0, "width": 2560, "height": 1440},
    "center": {"x": -2560, "y": 0, "width": 2560, "height": 1440},
    "right": {"x": 0, "y": 0, "width": 2560, "height": 1440},
    "primary": {"x": 0, "y": 0, "width": 2560, "height": 1440},
}

server = Server("windows-browser")

def run_powershell(script: str, capture_output: bool = True) -> tuple[str, str, int]:
    """Execute PowerShell script and return stdout, stderr, returncode.
    Uses the persistent bridge (~5ms) with subprocess fallback (~590ms)."""
    if _HAS_BRIDGE:
        result = _ps_bridge(script)
        return result.stdout, result.stderr, result.returncode
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-WindowStyle", "Hidden", "-Command", script],
        capture_output=capture_output,
        text=True
    )
    return result.stdout, result.stderr, result.returncode

_monitor_cache: Dict[str, Any] = {"data": None, "time": 0.0}

def detect_monitors() -> Dict[str, Dict]:
    """Detect monitor configuration from Windows (cached for 60s).

    Returns VIRTUAL (DPI-scaled) coordinates - NOT physical pixels.
    E.g., a 3840x2160 monitor at 150% DPI returns 2560x1440.
    This matches the coordinate space used by take_screenshot() and click_at().
    """
    now = time.time()
    if _monitor_cache["data"] and (now - _monitor_cache["time"]) < 60:
        return _monitor_cache["data"]

    script = """
    # NO SetProcessDPIAware - returns virtual coordinates
    Add-Type -AssemblyName System.Windows.Forms
    $screens = [System.Windows.Forms.Screen]::AllScreens
    $result = @()
    foreach ($screen in $screens) {
        $result += @{
            Name = $screen.DeviceName
            X = $screen.Bounds.X
            Y = $screen.Bounds.Y
            Width = $screen.Bounds.Width
            Height = $screen.Bounds.Height
            Primary = $screen.Primary
        }
    }
    $result | ConvertTo-Json -Compress
    """
    stdout, _, _ = run_powershell(script)
    try:
        screens = json.loads(stdout.strip())
        if not isinstance(screens, list):
            screens = [screens]

        # Sort by X position to determine left/center/right
        screens.sort(key=lambda s: s['X'])

        monitors = {}
        for i, screen in enumerate(screens):
            if screen.get('Primary'):
                monitors['primary'] = screen
            if len(screens) == 3:
                if i == 0:
                    monitors['left'] = screen
                elif i == 1:
                    monitors['center'] = screen
                else:
                    monitors['right'] = screen
            elif len(screens) == 2:
                if i == 0:
                    monitors['left'] = screen
                else:
                    monitors['right'] = screen

        _monitor_cache["data"] = monitors
        _monitor_cache["time"] = now
        return monitors
    except Exception:
        return MONITORS

def launch_browser_with_cdp(url: str = "about:blank", monitor: str = "center", browser: str = "chrome") -> bool:
    """Launch browser with CDP enabled on specified monitor

    Args:
        url: URL to navigate to
        monitor: Which monitor (left, center, right, primary)
        browser: Browser to use (chrome, edge)
    """
    monitors = detect_monitors()
    mon = monitors.get(monitor, monitors.get('primary', MONITORS['center']))

    # Calculate window position with margins
    x = mon['X'] + 50
    y = mon['Y'] + 50
    width = mon['Width'] - 100
    height = mon['Height'] - 100

    # Browser paths and process names
    browser_config = {
        "chrome": {
            "paths": [
                "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
                "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe"
            ],
            "profile_dir": "$env:TEMP\\chrome-cdp-profile",
            "process_name": "chrome"
        },
        "edge": {
            "paths": [
                "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
                "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe"
            ],
            "profile_dir": "$env:TEMP\\edge-cdp-profile",
            "process_name": "msedge"
        }
    }

    config = browser_config.get(browser.lower(), browser_config["chrome"])

    script = f"""
    # Find browser executable
    $browserPath = $null
    $paths = @({', '.join([f'"{p}"' for p in config["paths"]])})
    foreach ($p in $paths) {{
        if (Test-Path $p) {{
            $browserPath = $p
            break
        }}
    }}

    if (-not $browserPath) {{
        Write-Error "{browser} not found"
        exit 1
    }}

    Start-Process $browserPath -ArgumentList @(
        "--remote-debugging-port={CDP_PORT}",
        "--user-data-dir={config['profile_dir']}",
        "--window-position={x},{y}",
        "--window-size={width},{height}",
        "{url}"
    )

    Start-Sleep -Seconds 2

    # Bring window to front
    Add-Type @'
using System;
using System.Runtime.InteropServices;
public class Win32Launch {{
    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")]
    public static extern bool BringWindowToTop(IntPtr hWnd);
}}
'@

    $proc = Get-Process {config['process_name']} -ErrorAction SilentlyContinue | Where-Object {{ $_.MainWindowHandle -ne 0 }} | Select-Object -First 1
    if ($proc) {{
        [Win32Launch]::ShowWindow($proc.MainWindowHandle, 9)
        [Win32Launch]::BringWindowToTop($proc.MainWindowHandle)
        [Win32Launch]::SetForegroundWindow($proc.MainWindowHandle)
    }}

    Write-Output "{browser} launched with CDP on port {CDP_PORT}"
    """

    stdout, stderr, code = run_powershell(script)
    return code == 0

# Backward compatibility alias
def launch_chrome_with_cdp(url: str = "about:blank", monitor: str = "center") -> bool:
    """Launch Chrome with CDP enabled on specified monitor (legacy function)"""
    return launch_browser_with_cdp(url, monitor, "chrome")

def cdp_request(method: str, params: dict = None) -> dict:
    """Send a CDP request to Chrome"""
    try:
        # First get the list of targets
        targets_url = f"http://localhost:{CDP_PORT}/json"
        with urllib.request.urlopen(targets_url, timeout=5) as response:
            targets = json.loads(response.read().decode())

        if not targets:
            return {"error": "No browser targets found"}

        # Find a page target
        page_target = None
        for target in targets:
            if target.get('type') == 'page':
                page_target = target
                break

        if not page_target:
            return {"error": "No page target found"}

        return {"success": True, "target": page_target}
    except Exception as e:
        return {"error": str(e)}

def navigate_browser(url: str) -> dict:
    """Navigate the browser to a URL using CDP"""
    # First check if Chrome with CDP is running
    result = cdp_request("check")

    if "error" in result:
        # Need to launch Chrome
        launch_chrome_with_cdp(url)
        return {"success": True, "message": f"Launched Chrome and navigated to {url}"}

    # Use PowerShell to navigate existing window
    script = f"""
    Add-Type -AssemblyName System.Windows.Forms

    # Find Chrome window and send keys to navigate
    $chrome = Get-Process chrome -ErrorAction SilentlyContinue | Where-Object {{ $_.MainWindowHandle -ne 0 }} | Select-Object -First 1
    if ($chrome) {{
        # Activate window
        Add-Type @'
using System;
using System.Runtime.InteropServices;
public class Win32 {{
    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);
}}
'@
        [Win32]::SetForegroundWindow($chrome.MainWindowHandle)
        Start-Sleep -Milliseconds 200

        # Send Ctrl+L to focus address bar, then type URL and Enter
        [System.Windows.Forms.SendKeys]::SendWait("^l")
        Start-Sleep -Milliseconds 100
        [System.Windows.Forms.SendKeys]::SendWait("{url}")
        Start-Sleep -Milliseconds 100
        [System.Windows.Forms.SendKeys]::SendWait("{{ENTER}}")

        Write-Output "Navigated to {url}"
    }} else {{
        Write-Output "Chrome not found, launching..."
    }}
    """

    stdout, stderr, code = run_powershell(script)
    if "Chrome not found" in stdout:
        launch_chrome_with_cdp(url)

    return {"success": True, "url": url}

def take_screenshot(monitor: str = "center", filename: str = None) -> tuple:
    """Take a screenshot of specified monitor.

    IMPORTANT: Does NOT call SetProcessDPIAware(). This keeps the screenshot
    in virtual coordinate space (e.g., 2560x1440 at 150% DPI), which matches
    the coordinates returned by detect_monitors() and used by click_at().
    All three functions must use the same coordinate space.

    Returns (filepath, width, height) or (None, 0, 0) on failure.
    """
    monitors = detect_monitors()
    mon = monitors.get(monitor, monitors.get('primary', MONITORS['center']))

    if not filename:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"screenshot_{monitor}_{timestamp}.jpg"

    filepath = os.path.join(SCREENSHOT_DIR, filename)
    # Convert WSL path to Windows path generically
    import re
    win_path = re.sub(r'^/mnt/([a-z])/', lambda m: m.group(1).upper() + ':\\\\', filepath).replace('/', '\\')

    script = f"""
    # NO SetProcessDPIAware - keep virtual coordinates to match click_at()
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing

    $x = {mon['X']}
    $y = {mon['Y']}
    $width = {mon['Width']}
    $height = {mon['Height']}

    $bitmap = New-Object System.Drawing.Bitmap($width, $height)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $graphics.CopyFromScreen($x, $y, 0, 0, [System.Drawing.Size]::new($width, $height))
    $bitmap.Save('{win_path}', [System.Drawing.Imaging.ImageFormat]::Jpeg)
    $graphics.Dispose()
    $bitmap.Dispose()

    Write-Output "${{width}}x${{height}}"
    """

    stdout, stderr, code = run_powershell(script)

    if code == 0:
        # Parse dimensions from output
        try:
            w, h = stdout.strip().split('x')
            return filepath, int(w), int(h)
        except Exception:
            return filepath, mon['Width'], mon['Height']
    else:
        return None, 0, 0

AHK_EXE = r"C:\Program Files\AutoHotkey\v2\AutoHotkey64.exe"

def _wsl_to_win(path):
    """Convert WSL path to Windows path generically."""
    import re
    return re.sub(r'^/mnt/([a-z])/', lambda m: m.group(1).upper() + ':\\\\', path).replace('/', '\\')

AHK_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "click.ahk")
AHK_SCRIPT_WIN = _wsl_to_win(AHK_SCRIPT)
AHK_SENDKEYS_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sendkeys.ahk")
AHK_SENDKEYS_SCRIPT_WIN = _wsl_to_win(AHK_SENDKEYS_SCRIPT)
AHK_SCROLL_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scroll.ahk")
AHK_SCROLL_SCRIPT_WIN = _wsl_to_win(AHK_SCROLL_SCRIPT)

def click_at(x: int, y: int, monitor: str = None, action: str = "click") -> dict:
    """Click at coordinates relative to a monitor's screenshot using AutoHotkey.

    AutoHotkey handles DPI scaling, multi-monitor negative coordinates, and
    window focus natively - far more reliable than PowerShell SendInput/mouse_event
    which get swallowed by the foreground process (VS Code/terminal).

    Args:
        x, y: Pixel coordinates from the screenshot image
        monitor: Which monitor the coordinates are from (offsets by monitor position)
        action: click, rightclick, doubleclick, or move

    Returns dict with: success, target_x, target_y, actual_x, actual_y, active_window
    """
    monitors = detect_monitors()

    # If monitor specified, offset coordinates by monitor's virtual position
    abs_x, abs_y = x, y
    if monitor and monitor in monitors:
        mon = monitors[monitor]
        abs_x = mon['X'] + x
        abs_y = mon['Y'] + y

    ahk_cmd = f'& "{AHK_EXE}" "{AHK_SCRIPT_WIN}" {abs_x} {abs_y} {action}'
    stdout, _, code = run_powershell(ahk_cmd)
    stdout = stdout.strip()

    # Parse diagnostic output from AHK: target=X,Y|actual=X,Y|action=...|activewin=...
    result = {"success": code == 0, "target_x": abs_x, "target_y": abs_y}
    try:
        parts = stdout.split('|')
        for part in parts:
            key, val = part.split('=', 1)
            if key == 'actual':
                ax, ay = val.split(',')
                result['actual_x'] = int(ax)
                result['actual_y'] = int(ay)
            elif key == 'activewin':
                result['active_window'] = val
            elif key == 'action':
                result['action'] = val
    except Exception:
        pass

    return result

def type_text(text: str) -> bool:
    """Type text using SendKeys"""
    # Escape special characters for SendKeys
    escaped = text.replace('{', '{{').replace('}', '}}').replace('+', '{+}').replace('^', '{^}').replace('%', '{%}')

    script = f"""
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.SendKeys]::SendWait("{escaped}")
    Write-Output "Typed text"
    """

    stdout, stderr, code = run_powershell(script)
    return code == 0

def send_keys(keys: str) -> dict:
    """Send keyboard input using AutoHotkey's native Send command.

    Supports full AHK key syntax:
      Modifiers: ^ (Ctrl), ! (Alt), + (Shift), # (Win)
      Special keys: {Enter}, {Tab}, {Escape}, {PgDn}, {PgUp}, etc.
      Combos: ^a (Ctrl+A), ^l (Ctrl+L), !{F4} (Alt+F4)

    Returns dict with: success, keys, window_before, window_after
    """
    ahk_cmd = f'& "{AHK_EXE}" "{AHK_SENDKEYS_SCRIPT_WIN}" {keys}'
    stdout, _, code = run_powershell(ahk_cmd)
    stdout = stdout.strip()

    result = {"success": code == 0, "keys": keys}
    try:
        parts = stdout.split('|')
        for part in parts:
            key, val = part.split('=', 1)
            result[key] = val
    except Exception:
        pass

    return result

def scroll_at(x: int, y: int, monitor: str = None, direction: str = "down", clicks: int = 3) -> dict:
    """Scroll at coordinates using AutoHotkey.

    Args:
        x, y: Pixel coordinates from the screenshot image
        monitor: Which monitor the coordinates are from
        direction: 'up' or 'down'
        clicks: Number of scroll steps (default 3)

    Returns dict with: success, target_x, target_y, direction, clicks, active_window
    """
    monitors = detect_monitors()

    abs_x, abs_y = x, y
    if monitor and monitor in monitors:
        mon = monitors[monitor]
        abs_x = mon['X'] + x
        abs_y = mon['Y'] + y

    ahk_cmd = f'& "{AHK_EXE}" "{AHK_SCROLL_SCRIPT_WIN}" {abs_x} {abs_y} {direction} {clicks}'
    stdout, _, code = run_powershell(ahk_cmd)
    stdout = stdout.strip()

    result = {"success": code == 0, "target_x": abs_x, "target_y": abs_y, "direction": direction, "clicks": clicks}
    try:
        parts = stdout.split('|')
        for part in parts:
            key, val = part.split('=', 1)
            if key == 'actual':
                ax, ay = val.split(',')
                result['actual_x'] = int(ax)
                result['actual_y'] = int(ay)
            elif key == 'activewin':
                result['active_window'] = val
    except Exception:
        pass

    return result

def bring_window_to_front(process_name: str) -> bool:
    """Bring a window to the foreground"""
    script = f"""
    Add-Type @'
using System;
using System.Runtime.InteropServices;
public class Win32Front {{
    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")]
    public static extern bool BringWindowToTop(IntPtr hWnd);
}}
'@

    $proc = Get-Process {process_name} -ErrorAction SilentlyContinue | Where-Object {{ $_.MainWindowHandle -ne 0 }} | Select-Object -First 1
    if ($proc) {{
        [Win32Front]::ShowWindow($proc.MainWindowHandle, 9)  # SW_RESTORE
        [Win32Front]::BringWindowToTop($proc.MainWindowHandle)
        [Win32Front]::SetForegroundWindow($proc.MainWindowHandle)
        Write-Output "Window brought to front"
    }} else {{
        Write-Output "Process {process_name} not found"
    }}
    """

    stdout, stderr, code = run_powershell(script)
    return "brought to front" in stdout.lower()

def move_window_to_monitor(process_name: str, monitor: str = "center") -> bool:
    """Move a window to specified monitor"""
    monitors = detect_monitors()
    mon = monitors.get(monitor, monitors.get('primary', MONITORS['center']))

    x = mon['X'] + 50
    y = mon['Y'] + 50
    width = mon['Width'] - 100
    height = mon['Height'] - 100

    script = f"""
    Add-Type @'
using System;
using System.Runtime.InteropServices;
public class Win32 {{
    [DllImport("user32.dll")]
    public static extern bool SetWindowPos(IntPtr hWnd, IntPtr hWndInsertAfter, int X, int Y, int cx, int cy, uint uFlags);
}}
'@

    $proc = Get-Process {process_name} -ErrorAction SilentlyContinue | Where-Object {{ $_.MainWindowHandle -ne 0 }} | Select-Object -First 1
    if ($proc) {{
        [Win32]::SetWindowPos($proc.MainWindowHandle, [IntPtr]::Zero, {x}, {y}, {width}, {height}, 0x0040)
        Write-Output "Window moved to {monitor} monitor"
    }} else {{
        Write-Output "Process {process_name} not found"
    }}
    """

    stdout, stderr, code = run_powershell(script)
    return "moved" in stdout.lower()

# MCP Tool Definitions
@server.list_tools()
async def list_tools() -> List[Tool]:
    return [
        Tool(
            name="browser_open",
            description="Open a web browser (Chrome or Edge) on a specific monitor and navigate to a URL",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL to navigate to"
                    },
                    "monitor": {
                        "type": "string",
                        "enum": ["left", "center", "right", "primary"],
                        "description": "Which monitor to open the browser on",
                        "default": "center"
                    },
                    "browser": {
                        "type": "string",
                        "enum": ["chrome", "edge"],
                        "description": "Which browser to use (chrome or edge)",
                        "default": "chrome"
                    }
                },
                "required": ["url"]
            }
        ),
        Tool(
            name="browser_navigate",
            description="Navigate the browser to a new URL",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL to navigate to"
                    }
                },
                "required": ["url"]
            }
        ),
        Tool(
            name="browser_screenshot",
            description="Take a screenshot of a monitor to see what's displayed",
            inputSchema={
                "type": "object",
                "properties": {
                    "monitor": {
                        "type": "string",
                        "enum": ["left", "center", "right", "primary"],
                        "description": "Which monitor to screenshot",
                        "default": "center"
                    }
                }
            }
        ),
        Tool(
            name="browser_click",
            description="Click at coordinates from a screenshot using AutoHotkey. Pass the monitor name to correctly map screenshot pixel positions to screen coordinates. Works reliably on all monitors including negative-coordinate multi-monitor setups.",
            inputSchema={
                "type": "object",
                "properties": {
                    "x": {
                        "type": "integer",
                        "description": "X pixel coordinate from the screenshot"
                    },
                    "y": {
                        "type": "integer",
                        "description": "Y pixel coordinate from the screenshot"
                    },
                    "monitor": {
                        "type": "string",
                        "enum": ["left", "center", "right", "primary"],
                        "description": "Which monitor the coordinates are from (must match the monitor used in browser_screenshot)",
                        "default": "primary"
                    },
                    "action": {
                        "type": "string",
                        "enum": ["click", "rightclick", "doubleclick", "move"],
                        "description": "Type of mouse action",
                        "default": "click"
                    }
                },
                "required": ["x", "y"]
            }
        ),
        Tool(
            name="browser_type",
            description="Type text using keyboard",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Text to type"
                    }
                },
                "required": ["text"]
            }
        ),
        Tool(
            name="browser_send_keys",
            description="Send keyboard shortcuts and special keys using AutoHotkey. Supports Ctrl/Alt/Shift combos and special keys like Enter, Tab, PgDn, arrows, F-keys. Use AHK syntax: ^ for Ctrl, ! for Alt, + for Shift, # for Win. Examples: '^l' (Ctrl+L), '^a' (Ctrl+A), '{PgDn}' (Page Down), '{Enter}' (Enter), '^c' (Ctrl+C), '!{Tab}' (Alt+Tab), '{F5}' (F5 key).",
            inputSchema={
                "type": "object",
                "properties": {
                    "keys": {
                        "type": "string",
                        "description": "Keys to send in AutoHotkey syntax. Modifiers: ^ (Ctrl), ! (Alt), + (Shift), # (Win). Special keys: {Enter}, {Tab}, {Escape}, {PgDn}, {PgUp}, {Home}, {End}, {Up}, {Down}, {Left}, {Right}, {F1}-{F12}, {Backspace}, {Delete}, {Space}. Combos: ^a (Ctrl+A), ^l (Ctrl+L). Repeat: {PgDn 3} sends PgDn 3 times."
                    }
                },
                "required": ["keys"]
            }
        ),
        Tool(
            name="browser_scroll",
            description="Scroll up or down at a specific position on a monitor. Moves the mouse to the coordinates first, then sends scroll wheel events. Use with monitor parameter to target the correct screen.",
            inputSchema={
                "type": "object",
                "properties": {
                    "x": {
                        "type": "integer",
                        "description": "X pixel coordinate from screenshot (where to scroll)"
                    },
                    "y": {
                        "type": "integer",
                        "description": "Y pixel coordinate from screenshot (where to scroll)"
                    },
                    "monitor": {
                        "type": "string",
                        "enum": ["left", "center", "right", "primary"],
                        "description": "Which monitor the coordinates are from",
                        "default": "primary"
                    },
                    "direction": {
                        "type": "string",
                        "enum": ["up", "down"],
                        "description": "Scroll direction",
                        "default": "down"
                    },
                    "clicks": {
                        "type": "integer",
                        "description": "Number of scroll steps (default 3, increase for faster scrolling)",
                        "default": 3
                    }
                },
                "required": ["x", "y"]
            }
        ),
        Tool(
            name="browser_search",
            description="Open browser and perform a Google search",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query"
                    },
                    "monitor": {
                        "type": "string",
                        "enum": ["left", "center", "right", "primary"],
                        "default": "center"
                    },
                    "browser": {
                        "type": "string",
                        "enum": ["chrome", "edge"],
                        "description": "Which browser to use",
                        "default": "chrome"
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="window_move",
            description="Move an application window to a specific monitor",
            inputSchema={
                "type": "object",
                "properties": {
                    "process_name": {
                        "type": "string",
                        "description": "Name of the process (e.g., 'chrome', 'msedge', 'notepad')"
                    },
                    "monitor": {
                        "type": "string",
                        "enum": ["left", "center", "right", "primary"],
                        "default": "center"
                    }
                },
                "required": ["process_name"]
            }
        ),
        Tool(
            name="get_monitors",
            description="Get information about connected monitors",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list:
    """Handle tool calls - returns list of content items for MCP SDK 1.12.x compatibility"""
    try:
        if name == "browser_open":
            url = arguments.get("url", "https://google.com")
            monitor = arguments.get("monitor", "center")
            browser = arguments.get("browser", "chrome")

            success = launch_browser_with_cdp(url, monitor, browser)

            # Take a screenshot to show result
            await asyncio.sleep(2)
            screenshot_path, _, _ = take_screenshot(monitor)

            if screenshot_path and os.path.exists(screenshot_path):
                with open(screenshot_path, 'rb') as f:
                    image_data = base64.b64encode(f.read()).decode()

                return [
                    TextContent(type="text", text=f"{browser.capitalize()} opened on {monitor} monitor, navigated to {url}"),
                    ImageContent(type="image", data=image_data, mimeType="image/jpeg")
                ]
            else:
                return [TextContent(type="text", text=f"{browser.capitalize()} opened on {monitor} monitor, navigated to {url}")]

        elif name == "browser_navigate":
            url = arguments.get("url")
            result = navigate_browser(url)

            await asyncio.sleep(1)
            screenshot_path, _, _ = take_screenshot("center")

            if screenshot_path and os.path.exists(screenshot_path):
                with open(screenshot_path, 'rb') as f:
                    image_data = base64.b64encode(f.read()).decode()

                return [
                    TextContent(type="text", text=f"Navigated to {url}"),
                    ImageContent(type="image", data=image_data, mimeType="image/jpeg")
                ]
            else:
                return [TextContent(type="text", text=f"Navigated to {url}")]

        elif name == "browser_screenshot":
            monitor = arguments.get("monitor", "center")
            screenshot_path, img_w, img_h = take_screenshot(monitor)

            if screenshot_path and os.path.exists(screenshot_path):
                with open(screenshot_path, 'rb') as f:
                    image_data = base64.b64encode(f.read()).decode()

                return [
                    TextContent(type="text", text=f"Screenshot of {monitor} monitor ({img_w}x{img_h} pixels). Use browser_click with monitor=\"{monitor}\" and pixel coordinates from this image."),
                    ImageContent(type="image", data=image_data, mimeType="image/jpeg")
                ]
            else:
                raise Exception("Failed to take screenshot")

        elif name == "browser_click":
            x = arguments.get("x")
            y = arguments.get("y")
            monitor = arguments.get("monitor", "primary")
            action = arguments.get("action", "click")
            result = click_at(x, y, monitor=monitor, action=action)

            diag = f"{action.capitalize()} at ({x}, {y}) on {monitor} monitor"
            diag += f" -> absolute ({result.get('target_x')}, {result.get('target_y')})"
            if 'actual_x' in result:
                diag += f", cursor landed at ({result['actual_x']}, {result['actual_y']})"
            if 'active_window' in result:
                diag += f", active_window={result['active_window']}"
            if not result.get('success'):
                diag = "Click failed: " + diag

            return [TextContent(type="text", text=diag)]

        elif name == "browser_type":
            text = arguments.get("text")
            success = type_text(text)

            return [TextContent(type="text", text=f"Typed: {text}" if success else "Type failed")]

        elif name == "browser_send_keys":
            keys = arguments.get("keys")
            result = send_keys(keys)

            diag = f"Sent keys: {keys}"
            if result.get('window_before'):
                diag += f", window: {result['window_before']}"
            if result.get('window_after') and result.get('window_after') != result.get('window_before'):
                diag += f" -> {result['window_after']}"
            if not result.get('success'):
                diag = "Send keys failed: " + diag

            return [TextContent(type="text", text=diag)]

        elif name == "browser_scroll":
            x = arguments.get("x")
            y = arguments.get("y")
            monitor = arguments.get("monitor", "primary")
            direction = arguments.get("direction", "down")
            clicks = arguments.get("clicks", 3)
            result = scroll_at(x, y, monitor=monitor, direction=direction, clicks=clicks)

            diag = f"Scrolled {direction} {clicks}x at ({x}, {y}) on {monitor} monitor"
            diag += f" -> absolute ({result.get('target_x')}, {result.get('target_y')})"
            if 'active_window' in result:
                diag += f", active_window={result['active_window']}"
            if not result.get('success'):
                diag = "Scroll failed: " + diag

            return [TextContent(type="text", text=diag)]

        elif name == "browser_search":
            query = arguments.get("query")
            monitor = arguments.get("monitor", "center")
            browser = arguments.get("browser", "chrome")

            search_url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
            launch_browser_with_cdp(search_url, monitor, browser)

            await asyncio.sleep(2)
            screenshot_path, _, _ = take_screenshot(monitor)

            if screenshot_path and os.path.exists(screenshot_path):
                with open(screenshot_path, 'rb') as f:
                    image_data = base64.b64encode(f.read()).decode()

                return [
                    TextContent(type="text", text=f"Searched for: {query}"),
                    ImageContent(type="image", data=image_data, mimeType="image/jpeg")
                ]
            else:
                return [TextContent(type="text", text=f"Searched for: {query}")]

        elif name == "window_move":
            process_name = arguments.get("process_name")
            monitor = arguments.get("monitor", "center")

            success = move_window_to_monitor(process_name, monitor)

            return [TextContent(type="text", text=f"Moved {process_name} to {monitor} monitor" if success else f"Failed to move {process_name}")]

        elif name == "get_monitors":
            monitors = detect_monitors()

            # Add DPI info for diagnostics
            dpi_script = """
            Add-Type @'
using System;
using System.Runtime.InteropServices;
public class DpiInfo {
    [DllImport("user32.dll")]
    public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")]
    public static extern int GetSystemMetrics(int nIndex);
    [DllImport("gdi32.dll")]
    public static extern int GetDeviceCaps(IntPtr hdc, int nIndex);
    [DllImport("user32.dll")]
    public static extern IntPtr GetDC(IntPtr hWnd);
}
'@
            # Get virtual metrics first (before DPI aware)
            $vw = [DpiInfo]::GetSystemMetrics(0)
            $vh = [DpiInfo]::GetSystemMetrics(1)

            # Now get physical metrics
            $null = [DpiInfo]::SetProcessDPIAware()
            $pw = [DpiInfo]::GetSystemMetrics(0)
            $ph = [DpiInfo]::GetSystemMetrics(1)

            # Get DPI
            $hdc = [DpiInfo]::GetDC([IntPtr]::Zero)
            $dpi = [DpiInfo]::GetDeviceCaps($hdc, 88)

            Write-Output "${vw}x${vh}|${pw}x${ph}|${dpi}"
            """
            dpi_out, _, _ = run_powershell(dpi_script)
            dpi_info = {}
            try:
                parts = dpi_out.strip().split('|')
                dpi_info = {
                    "virtual_resolution": parts[0],
                    "physical_resolution": parts[1],
                    "dpi": int(parts[2]),
                    "scale_factor": round(int(parts[2]) / 96.0, 2),
                    "coordinate_space": "virtual (all screenshot/click coords use this)"
                }
            except Exception:
                pass

            info = {"monitors": monitors, "dpi_info": dpi_info}
            return [TextContent(type="text", text=json.dumps(info, indent=2))]

        else:
            raise Exception(f"Unknown tool: {name}")

    except Exception as e:
        raise Exception(f"Error: {str(e)}")

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())

if __name__ == "__main__":
    import urllib.parse
    asyncio.run(main())
