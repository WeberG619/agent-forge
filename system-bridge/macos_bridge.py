#!/usr/bin/env python3
"""
Cadre - macOS System Bridge

Provides macOS-native system state queries used by the daemon to populate
live_state.json on Apple Silicon and Intel Macs.

Platform guard: every public function returns None or an empty
collection when called on a non-macOS host.  Import this module freely
on any platform; it will simply no-op.

Dependencies: stdlib only (subprocess, shutil, platform, json, re)
"""

from __future__ import annotations

import json
import platform
import re
import shutil
import subprocess
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Platform guard
# ---------------------------------------------------------------------------

IS_MACOS = platform.system() == "Darwin"


def _require_macos(default: Any = None):
    """Decorator: return default immediately when not on macOS."""
    def decorator(fn):
        def wrapper(*args, **kwargs):
            if not IS_MACOS:
                return default() if callable(default) else default
            return fn(*args, **kwargs)
        wrapper.__name__ = fn.__name__
        wrapper.__doc__ = fn.__doc__
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _run(cmd: List[str], timeout: int = 5) -> Optional[str]:
    """Run a command and return stripped stdout, or None on failure."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout.strip() if result.stdout else None
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None


def _osascript(script: str, timeout: int = 5) -> Optional[str]:
    """Execute an AppleScript snippet and return stripped stdout."""
    return _run(["osascript", "-e", script], timeout=timeout)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@_require_macos(default=list)
def get_open_applications() -> List[Dict[str, str]]:
    """
    Return a list of visible running applications.

    Each entry has:
        ProcessName  — app bundle name (e.g. "Safari")
        MainWindowTitle — same as ProcessName (macOS doesn't expose window
                          titles this way without Accessibility permissions)
        BundleID     — com.apple.Safari (best-effort via lsappinfo)

    Falls back to a plain osascript query if lsappinfo is unavailable.
    """
    apps: List[Dict[str, str]] = []

    # Primary: lsappinfo gives us bundle IDs + names without Accessibility
    if shutil.which("lsappinfo"):
        output = _run(["lsappinfo", "list", "-only", "name"], timeout=8)
        if output:
            # lsappinfo output lines look like:
            #   ASN:0x... name="Finder" ...
            for line in output.splitlines():
                m = re.search(r'name="([^"]+)"', line)
                if m:
                    name = m.group(1)
                    apps.append({
                        "ProcessName": name,
                        "MainWindowTitle": name,
                    })
            if apps:
                return apps

    # Fallback: osascript (requires no special permissions for visible=true)
    script = (
        'tell application "System Events" '
        'to get name of every process whose visible is true'
    )
    output = _osascript(script)
    if output:
        names = [n.strip() for n in output.split(",") if n.strip()]
        apps = [{"ProcessName": n, "MainWindowTitle": n} for n in names]

    return apps


@_require_macos(default=None)
def get_active_window_title() -> Optional[str]:
    """
    Return the title of the currently focused window.

    Requires Accessibility permissions for the calling process on macOS 10.15+.
    Returns None when the permission is not granted or the call fails.
    """
    script = """
tell application "System Events"
    set frontApp to name of first application process whose frontmost is true
    try
        set winTitle to name of front window of application process frontApp
        return frontApp & ": " & winTitle
    on error
        return frontApp
    end try
end tell
"""
    return _osascript(script)


@_require_macos(default=dict)
def get_screen_info() -> Dict[str, Any]:
    """
    Return monitor count and per-display resolution via system_profiler.

    Returns a dict with keys:
        monitor_count  — int
        displays       — list of {width, height, name} dicts
        primary        — {width, height} of the main display
    """
    output = _run(
        ["system_profiler", "SPDisplaysDataType", "-json"],
        timeout=10,
    )
    if not output:
        return {"monitor_count": 0, "displays": [], "primary": {}}

    try:
        data = json.loads(output)
        raw_displays = data.get("SPDisplaysDataType", [])
    except (json.JSONDecodeError, AttributeError):
        return {"monitor_count": 0, "displays": [], "primary": {}}

    displays: List[Dict[str, Any]] = []
    for gpu in raw_displays:
        for disp in gpu.get("spdisplays_ndrvs", []):
            name = disp.get("_name", "Display")
            res_str = disp.get("_spdisplays_resolution", "")
            # "3840 x 2160 @ 60.00Hz"  or  "2560 x 1440"
            m = re.search(r"(\d+)\s*x\s*(\d+)", res_str)
            if m:
                displays.append({
                    "name": name,
                    "width": int(m.group(1)),
                    "height": int(m.group(2)),
                })

    primary = displays[0] if displays else {}
    return {
        "monitor_count": len(displays),
        "displays": displays,
        "primary": primary,
    }


@_require_macos(default=None)
def get_clipboard_text() -> Optional[str]:
    """
    Return up to 500 characters of the current clipboard text via pbpaste.
    Returns None if the clipboard is empty or contains non-text data.
    """
    output = _run(["pbpaste"], timeout=3)
    if output is None:
        return None
    if len(output) > 500:
        return output[:500] + "..."
    return output


@_require_macos(default=dict)
def get_system_info() -> Dict[str, Any]:
    """
    Return memory and CPU usage without external dependencies.

    Uses sysctl and vm_stat (both available on every macOS install).

    Returns a dict with keys:
        memory_total_gb  — float
        memory_used_gb   — float
        memory_percent   — int (0-100)
        cpu_count        — int (logical cores)
        os_version       — str  (e.g. "14.4.1")
    """
    info: Dict[str, Any] = {}

    # --- CPU core count ---
    ncpu = _run(["sysctl", "-n", "hw.logicalcpu"])
    if ncpu and ncpu.isdigit():
        info["cpu_count"] = int(ncpu)

    # --- Total physical RAM ---
    mem_bytes = _run(["sysctl", "-n", "hw.memsize"])
    total_gb: Optional[float] = None
    if mem_bytes and mem_bytes.isdigit():
        total_gb = int(mem_bytes) / (1024 ** 3)
        info["memory_total_gb"] = round(total_gb, 1)

    # --- Memory pressure via vm_stat ---
    vm = _run(["vm_stat"], timeout=5)
    if vm and total_gb:
        page_size = 4096  # default; read from output if present
        ps_match = re.search(r"page size of (\d+) bytes", vm)
        if ps_match:
            page_size = int(ps_match.group(1))

        def _pages(key: str) -> int:
            m = re.search(rf"{re.escape(key)}:\s+(\d+)", vm)
            return int(m.group(1)) if m else 0

        free = _pages("Pages free")
        inactive = _pages("Pages inactive")
        # "used" = total - free - inactive (rough approximation)
        free_gb = (free + inactive) * page_size / (1024 ** 3)
        used_gb = max(total_gb - free_gb, 0)
        info["memory_used_gb"] = round(used_gb, 1)
        info["memory_percent"] = int(min((used_gb / total_gb) * 100, 100))

    # --- OS version ---
    osv = _run(["sw_vers", "-productVersion"])
    if osv:
        info["os_version"] = osv

    return info


@_require_macos(default=list)
def get_recent_files() -> List[str]:
    """
    Return up to 10 recently opened file names via AppleScript.

    This queries the Finder's recent items list, which reflects the
    system-wide "Recent Items" menu (no Accessibility permission needed).
    """
    script = """
tell application "System Events"
    tell appearance preferences
        set recentCount to recent documents limit
    end tell
end tell
-- Use Finder recent items instead (more reliable)
tell application "Finder"
    set recents to name of every item of recent documents
    set output to ""
    repeat with i from 1 to (count recents)
        if i <= 10 then
            set output to output & (item i of recents) & linefeed
        end if
    end repeat
    return output
end tell
"""
    output = _osascript(script, timeout=8)
    if output:
        return [line.strip() for line in output.splitlines() if line.strip()]
    return []


# ---------------------------------------------------------------------------
# Convenience: single snapshot dict (mirrors daemon's state shape)
# ---------------------------------------------------------------------------

def snapshot() -> Dict[str, Any]:
    """
    Return a single dict with all macOS system state fields.

    Safe to call on any platform — returns empty/None values on non-macOS.
    """
    return {
        "applications": get_open_applications(),
        "active_window": get_active_window_title() or "",
        "monitors": get_screen_info(),
        "system": get_system_info(),
        "clipboard_preview": (get_clipboard_text() or ""),
        "recent_files": get_recent_files(),
        "platform": "macos" if IS_MACOS else platform.system().lower(),
    }


# ---------------------------------------------------------------------------
# CLI smoke-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if not IS_MACOS:
        print("Not running on macOS — all values will be empty.")

    data = snapshot()
    print(json.dumps(data, indent=2))
    sys.exit(0)
