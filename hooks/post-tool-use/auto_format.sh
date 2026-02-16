#!/bin/bash
# Post-Tool-Use Hook - Auto-format code after edits
# Runs after Edit or Write tool use.
# Detects file type and runs appropriate formatter.

FILE_PATH="${CLAUDE_FILE_PATH:-}"

if [ -z "$FILE_PATH" ]; then
    exit 0
fi

# Get file extension
EXT="${FILE_PATH##*.}"

case "$EXT" in
    py)
        # Python - format with black if available
        if command -v black &>/dev/null; then
            black --quiet "$FILE_PATH" 2>/dev/null
        fi
        ;;
    js|ts|jsx|tsx)
        # JavaScript/TypeScript - format with prettier if available
        if command -v prettier &>/dev/null; then
            prettier --write "$FILE_PATH" 2>/dev/null
        fi
        ;;
    cs)
        # C# - format with dotnet format if available
        if command -v dotnet &>/dev/null; then
            dotnet format --include "$FILE_PATH" 2>/dev/null
        elif command -v powershell.exe &>/dev/null; then
            powershell.exe -Command "dotnet format --include '$FILE_PATH'" 2>/dev/null
        fi
        ;;
    go)
        # Go - format with gofmt
        if command -v gofmt &>/dev/null; then
            gofmt -w "$FILE_PATH" 2>/dev/null
        fi
        ;;
    rs)
        # Rust - format with rustfmt
        if command -v rustfmt &>/dev/null; then
            rustfmt "$FILE_PATH" 2>/dev/null
        fi
        ;;
esac

exit 0
