#!/usr/bin/env python3
"""
Cadre - macOS Desktop Automation

AppleScript/JXA helpers for window management, screenshots, Office
automation, and Chrome CDP browser control on macOS.

Platform guard: all public functions raise RuntimeError immediately on
non-macOS hosts with a clear message — they never silently no-op so
that callers get actionable feedback.

Dependencies: stdlib only (subprocess, shutil, platform, json, base64,
              tempfile, pathlib, urllib)
"""

from __future__ import annotations

import base64
import json
import platform
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Platform guard
# ---------------------------------------------------------------------------

IS_MACOS = platform.system() == "Darwin"

_NOT_MACOS_MSG = (
    "macos_automation: this function requires macOS. "
    f"Current platform: {platform.system()}"
)


def _assert_macos() -> None:
    if not IS_MACOS:
        raise RuntimeError(_NOT_MACOS_MSG)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _run(cmd: List[str], timeout: int = 10) -> Tuple[str, str, int]:
    """Run a command and return (stdout, stderr, returncode)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except FileNotFoundError as exc:
        return "", str(exc), 127
    except subprocess.TimeoutExpired:
        return "", "Command timed out", 1


def _osascript(script: str, timeout: int = 10) -> Tuple[str, str, int]:
    """Execute an AppleScript snippet via osascript."""
    return _run(["osascript", "-e", script], timeout=timeout)


def _jxa(script: str, timeout: int = 10) -> Tuple[str, str, int]:
    """Execute a JXA (JavaScript for Automation) snippet via osascript."""
    return _run(["osascript", "-l", "JavaScript", "-e", script], timeout=timeout)


# ---------------------------------------------------------------------------
# Application management
# ---------------------------------------------------------------------------

def activate_application(app_name: str) -> bool:
    """
    Bring the named application to the foreground.

    Args:
        app_name: Display name or bundle ID (e.g. "Safari", "com.apple.Safari")

    Returns:
        True on success, False otherwise.
    """
    _assert_macos()
    script = f'tell application "{app_name}" to activate'
    stdout, stderr, rc = _osascript(script)
    return rc == 0


def open_file(file_path: str) -> bool:
    """
    Open a file with its default application via the `open` command.

    Args:
        file_path: Absolute path to the file.

    Returns:
        True on success.
    """
    _assert_macos()
    _, _, rc = _run(["open", file_path])
    return rc == 0


def open_application(app_name: str) -> bool:
    """
    Launch an application by name (searches /Applications and ~/Applications).

    Args:
        app_name: e.g. "Microsoft Excel" — no .app suffix needed.

    Returns:
        True on success.
    """
    _assert_macos()
    _, _, rc = _run(["open", "-a", app_name])
    return rc == 0


def quit_application(app_name: str) -> bool:
    """
    Gracefully quit a running application.

    Args:
        app_name: Display name of the application.

    Returns:
        True on success.
    """
    _assert_macos()
    script = f'tell application "{app_name}" to quit'
    _, _, rc = _osascript(script)
    return rc == 0


# ---------------------------------------------------------------------------
# Window geometry
# ---------------------------------------------------------------------------

def get_window_info(app_name: str) -> Optional[Dict[str, Any]]:
    """
    Return position and size of the frontmost window of the named application.

    Returns a dict with keys: x, y, width, height, title
    Returns None if the application is not running or has no windows.

    Note: Requires Accessibility permissions for the calling process.
    """
    _assert_macos()
    script = f"""
tell application "System Events"
    tell process "{app_name}"
        try
            set w to front window
            set pos to position of w
            set sz to size of w
            set ttl to name of w
            return (item 1 of pos) & "," & (item 2 of pos) & "," & ¬
                   (item 1 of sz) & "," & (item 2 of sz) & "," & ttl
        on error errMsg
            return "ERROR:" & errMsg
        end try
    end tell
end tell
"""
    stdout, _, rc = _osascript(script)
    if rc != 0 or not stdout or stdout.startswith("ERROR:"):
        return None

    parts = stdout.split(",", 4)
    if len(parts) < 5:
        return None

    try:
        return {
            "x": int(parts[0]),
            "y": int(parts[1]),
            "width": int(parts[2]),
            "height": int(parts[3]),
            "title": parts[4],
        }
    except ValueError:
        return None


def move_window(app_name: str, x: int, y: int) -> bool:
    """
    Move the frontmost window of the named application to (x, y).

    Coordinates are in macOS screen space (top-left origin).
    Requires Accessibility permissions.
    """
    _assert_macos()
    script = f"""
tell application "System Events"
    tell process "{app_name}"
        set position of front window to {{{x}, {y}}}
    end tell
end tell
"""
    _, _, rc = _osascript(script)
    return rc == 0


def resize_window(app_name: str, width: int, height: int) -> bool:
    """
    Resize the frontmost window of the named application.

    Requires Accessibility permissions.
    """
    _assert_macos()
    script = f"""
tell application "System Events"
    tell process "{app_name}"
        set size of front window to {{{width}, {height}}}
    end tell
end tell
"""
    _, _, rc = _osascript(script)
    return rc == 0


def move_and_resize_window(
    app_name: str, x: int, y: int, width: int, height: int
) -> bool:
    """
    Move and resize in a single AppleScript call (fewer round-trips).

    Requires Accessibility permissions.
    """
    _assert_macos()
    script = f"""
tell application "System Events"
    tell process "{app_name}"
        set position of front window to {{{x}, {y}}}
        set size of front window to {{{width}, {height}}}
    end tell
end tell
"""
    _, _, rc = _osascript(script)
    return rc == 0


# ---------------------------------------------------------------------------
# Screenshots
# ---------------------------------------------------------------------------

def take_screenshot(
    output_path: Optional[str] = None,
    window_only: bool = False,
    app_name: Optional[str] = None,
) -> str:
    """
    Capture a screenshot and save it as a PNG.

    Args:
        output_path: Where to save the PNG.  Defaults to a temp file.
        window_only: If True, capture only the frontmost window of app_name.
        app_name:    Application whose window to capture (only when window_only=True).
                     If omitted, captures the interactive window selection.

    Returns:
        Absolute path to the saved PNG file.

    Raises:
        RuntimeError on failure or non-macOS platform.
    """
    _assert_macos()

    if output_path is None:
        output_path = str(
            Path(tempfile.mkdtemp()) / "cadre_screenshot.png"
        )

    cmd: List[str] = ["screencapture", "-x"]  # -x = no sound

    if window_only:
        if app_name:
            # Activate the target app first so its window is front
            activate_application(app_name)
            import time as _time
            _time.sleep(0.3)
        cmd += ["-l"]
        # For -l we need the window ID (CGWindowID) — get via JXA
        if app_name:
            wid = _get_window_id(app_name)
            if wid:
                cmd += [str(wid)]
            else:
                # Fallback: capture whole screen
                cmd = ["screencapture", "-x"]
        else:
            # Interactive window grab (the user clicks the window)
            cmd += ["-W"]

    cmd.append(output_path)
    _, stderr, rc = _run(cmd, timeout=15)

    if rc != 0:
        raise RuntimeError(f"screencapture failed (rc={rc}): {stderr}")

    return output_path


def take_screenshot_base64(
    window_only: bool = False,
    app_name: Optional[str] = None,
) -> str:
    """
    Capture a screenshot and return it as a base64-encoded PNG string.

    Useful for embedding in MCP tool responses.
    """
    _assert_macos()
    path = take_screenshot(window_only=window_only, app_name=app_name)
    with open(path, "rb") as fh:
        return base64.b64encode(fh.read()).decode("ascii")


def _get_window_id(app_name: str) -> Optional[int]:
    """Return the CGWindowID of the frontmost window of app_name via JXA."""
    script = f"""
var app = Application("{app_name}");
var se = Application("System Events");
var proc = se.processes.whose({{name: "{app_name}"}})[0];
if (!proc) {{ "null" }}
else {{
    try {{
        proc.windows[0].id();
    }} catch(e) {{ "null" }}
}}
"""
    stdout, _, rc = _jxa(script)
    if rc == 0 and stdout.isdigit():
        return int(stdout)
    return None


# ---------------------------------------------------------------------------
# Office automation (AppleScript stubs for macOS Office suite)
# ---------------------------------------------------------------------------
# Microsoft Office for Mac exposes an AppleScript dictionary.
# These stubs cover the most common single-document operations.
# The Excel/Word/PowerPoint MCP servers on macOS would call these.


def excel_get_active_workbook() -> Optional[str]:
    """Return the name of the active workbook in Microsoft Excel."""
    _assert_macos()
    stdout, _, rc = _osascript(
        'tell application "Microsoft Excel" to return name of active workbook'
    )
    return stdout if rc == 0 and stdout else None


def excel_get_cell(sheet: str, cell: str) -> Optional[str]:
    """
    Return the value of a cell in the active Excel workbook.

    Args:
        sheet: Sheet name, e.g. "Sheet1"
        cell:  Cell address, e.g. "A1"
    """
    _assert_macos()
    script = f"""
tell application "Microsoft Excel"
    tell active workbook
        tell sheet "{sheet}"
            return value of range "{cell}"
        end tell
    end tell
end tell
"""
    stdout, _, rc = _osascript(script)
    return stdout if rc == 0 else None


def excel_set_cell(sheet: str, cell: str, value: str) -> bool:
    """Set the value of a cell in the active Excel workbook."""
    _assert_macos()
    script = f"""
tell application "Microsoft Excel"
    tell active workbook
        tell sheet "{sheet}"
            set value of range "{cell}" to "{value}"
        end tell
    end tell
end tell
"""
    _, _, rc = _osascript(script)
    return rc == 0


def excel_save_workbook() -> bool:
    """Save the active Excel workbook."""
    _assert_macos()
    _, _, rc = _osascript(
        'tell application "Microsoft Excel" to save active workbook'
    )
    return rc == 0


def word_get_document_name() -> Optional[str]:
    """Return the name of the active Word document."""
    _assert_macos()
    stdout, _, rc = _osascript(
        'tell application "Microsoft Word" to return name of active document'
    )
    return stdout if rc == 0 and stdout else None


def word_insert_text(text: str) -> bool:
    """
    Insert text at the current cursor position in the active Word document.

    Args:
        text: Plain text to insert (no rich formatting).
    """
    _assert_macos()
    # Escape double-quotes for AppleScript
    safe = text.replace("\\", "\\\\").replace('"', '\\"')
    script = f"""
tell application "Microsoft Word"
    set myRange to selection
    type text of myRange text: "{safe}"
end tell
"""
    _, _, rc = _osascript(script)
    return rc == 0


def powerpoint_get_presentation_name() -> Optional[str]:
    """Return the name of the active PowerPoint presentation."""
    _assert_macos()
    stdout, _, rc = _osascript(
        'tell application "Microsoft PowerPoint" to return name of active presentation'
    )
    return stdout if rc == 0 and stdout else None


def powerpoint_go_to_slide(index: int) -> bool:
    """
    Navigate to a slide by 1-based index in the active presentation.

    Args:
        index: Slide number (1-based).
    """
    _assert_macos()
    script = f"""
tell application "Microsoft PowerPoint"
    tell active presentation
        tell slide show settings
            run slide show
        end tell
        go to slide {index} of active presentation
    end tell
end tell
"""
    _, _, rc = _osascript(script)
    return rc == 0


# ---------------------------------------------------------------------------
# Chrome CDP browser automation
# ---------------------------------------------------------------------------

# macOS Chrome installs at a stable path regardless of architecture.
CHROME_MACOS_PATH = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
)
CHROME_CANARY_PATH = (
    "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary"
)
CDP_PORT = 9222
_chrome_proc: Optional[subprocess.Popen] = None  # type: ignore[type-arg]


def find_chrome_path() -> Optional[str]:
    """Return the path to the first available Chrome binary on this Mac."""
    for path in (CHROME_MACOS_PATH, CHROME_CANARY_PATH):
        if Path(path).exists():
            return path
    # Last resort: check PATH
    which = shutil.which("google-chrome") or shutil.which("chromium")
    return which


def launch_chrome_cdp(port: int = CDP_PORT, user_data_dir: Optional[str] = None) -> bool:
    """
    Launch Chrome with the remote debugging port open for CDP.

    Args:
        port:          CDP port (default 9222).
        user_data_dir: Optional custom profile directory.

    Returns:
        True if Chrome launched successfully.
    """
    _assert_macos()
    global _chrome_proc

    chrome = find_chrome_path()
    if not chrome:
        raise RuntimeError(
            "Google Chrome not found. Install it at /Applications/Google Chrome.app"
        )

    if user_data_dir is None:
        user_data_dir = str(Path(tempfile.mkdtemp()) / "cadre-chrome-profile")

    cmd = [
        chrome,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    try:
        _chrome_proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except OSError as exc:
        raise RuntimeError(f"Failed to launch Chrome: {exc}") from exc


def cdp_get_targets(port: int = CDP_PORT) -> List[Dict[str, Any]]:
    """
    Return the list of CDP targets (tabs) from a running Chrome instance.

    Args:
        port: The CDP port Chrome was started with.

    Returns:
        List of target dicts from /json/list.
    """
    _assert_macos()
    url = f"http://127.0.0.1:{port}/json/list"
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            return json.loads(resp.read().decode())
    except (urllib.error.URLError, json.JSONDecodeError):
        return []


def cdp_navigate(url: str, port: int = CDP_PORT) -> bool:
    """
    Navigate the first available Chrome tab to a URL via CDP.

    Opens a new tab if no tabs exist.

    Args:
        url:  The URL to navigate to.
        port: The CDP port.

    Returns:
        True on success.
    """
    _assert_macos()
    targets = cdp_get_targets(port)
    # Find the first "page" target
    page_target = next(
        (t for t in targets if t.get("type") == "page"),
        None,
    )

    if page_target is None:
        # Open a new tab
        try:
            new_tab_url = f"http://127.0.0.1:{port}/json/new?{url}"
            with urllib.request.urlopen(new_tab_url, timeout=3):
                pass
            return True
        except urllib.error.URLError:
            return False

    # Use the existing tab's WebSocket debugger URL isn't accessible via
    # simple HTTP — instead, POST to /json/activate then use /json/new
    try:
        activate_url = (
            f"http://127.0.0.1:{port}/json/activate/{page_target['id']}"
        )
        urllib.request.urlopen(activate_url, timeout=3)
    except urllib.error.URLError:
        pass

    # Navigate via a new Chrome tab opened to the target URL
    open_url = f"http://127.0.0.1:{port}/json/new?{url}"
    try:
        with urllib.request.urlopen(open_url, timeout=3):
            return True
    except urllib.error.URLError:
        return False


def cdp_get_page_title(port: int = CDP_PORT) -> Optional[str]:
    """Return the title of the active Chrome tab."""
    _assert_macos()
    targets = cdp_get_targets(port)
    page = next((t for t in targets if t.get("type") == "page"), None)
    return page.get("title") if page else None


def cdp_get_page_url(port: int = CDP_PORT) -> Optional[str]:
    """Return the URL of the active Chrome tab."""
    _assert_macos()
    targets = cdp_get_targets(port)
    page = next((t for t in targets if t.get("type") == "page"), None)
    return page.get("url") if page else None


# ---------------------------------------------------------------------------
# Keyboard / clipboard helpers
# ---------------------------------------------------------------------------

def type_text(text: str) -> bool:
    """
    Type text into the currently focused application via AppleScript.

    Uses keystroke which respects the active input method.
    Suitable for short strings; for long text prefer set_clipboard + paste.

    Args:
        text: Text to type (plain ASCII safest; some Unicode works).
    """
    _assert_macos()
    safe = text.replace("\\", "\\\\").replace('"', '\\"')
    script = f"""
tell application "System Events"
    keystroke "{safe}"
end tell
"""
    _, _, rc = _osascript(script)
    return rc == 0


def set_clipboard(text: str) -> bool:
    """
    Write text to the macOS clipboard via pbcopy.

    Args:
        text: Text to place on the clipboard.
    """
    _assert_macos()
    try:
        result = subprocess.run(
            ["pbcopy"],
            input=text,
            text=True,
            timeout=3,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


# ---------------------------------------------------------------------------
# CLI smoke-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if not IS_MACOS:
        print(_NOT_MACOS_MSG)
        sys.exit(1)

    print("macOS automation module loaded successfully.")
    print(f"Chrome path: {find_chrome_path() or 'not found'}")

    info = None
    try:
        # Try to get frontmost window — may fail without Accessibility perms
        from macos_bridge import get_open_applications
        apps = get_open_applications()
        print(f"Visible apps ({len(apps)}): {[a['ProcessName'] for a in apps[:5]]}")
    except Exception as exc:
        print(f"Could not query apps: {exc}")

    sys.exit(0)
