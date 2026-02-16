#!/bin/bash
# Session Start Hook - Start background services for Claude Power Kit
# This runs when a new Claude Code session starts.

INSTALL_DIR="${CLAUDE_POWER_KIT_DIR:-$HOME/.claude-power-kit}"

# Start system bridge daemon (if not already running)
if [ -f "$INSTALL_DIR/system-bridge/daemon.py" ]; then
    PIDFILE="$INSTALL_DIR/system-bridge/daemon.pid"
    if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
        # Already running
        true
    else
        # Detect platform and start accordingly
        if command -v powershell.exe &>/dev/null; then
            # WSL/Windows - run daemon via Windows Python
            powershell.exe -ExecutionPolicy Bypass -Command "
                Start-Process pythonw -ArgumentList '$INSTALL_DIR/system-bridge/daemon.py' -WindowStyle Hidden
            " 2>/dev/null &
        elif [[ "$(uname)" == "Darwin" ]]; then
            # macOS
            python3 "$INSTALL_DIR/system-bridge/daemon.py" &
        else
            # Linux
            python3 "$INSTALL_DIR/system-bridge/daemon.py" &
        fi
    fi
fi

echo "Success"
