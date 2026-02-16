# Hooks Guide

Claude Code hooks are scripts that run at specific points in the session lifecycle. They add safety, automation, and intelligence.

## Hook Types

| Type | When It Runs | Use For |
|------|-------------|---------|
| `SessionStart` | When Claude Code starts | Start background services, load state |
| `PreToolUse` | Before a tool executes | Validate parameters, block dangerous operations |
| `PostToolUse` | After a tool executes | Auto-format code, log actions |
| `UserPromptSubmit` | When user sends a message | Detect corrections, auto-checkpoint |
| `Stop` | When Claude Code exits | Save session state, cleanup |

## Included Hooks

### Pre-commit Guard (`hooks/pre-tool-use/pre_commit_guard.py`)

Runs before every `git commit` to check staged files for:
- Hardcoded passwords, API keys, secrets, tokens
- Sensitive files (.env, credentials.json)

**Behavior:** Blocks the commit if sensitive files are staged. Warns (but allows) if patterns are found in code.

### Correction Detection (`hooks/user-prompt/detect_correction.py`)

Analyzes every user message for correction patterns like:
- "No, that's wrong"
- "Actually, you should..."
- "You forgot to..."

**Behavior:** Outputs a reminder for Claude to capture the correction using `memory_store_correction()`.

### Auto-format (`hooks/post-tool-use/auto_format.sh`)

After file edits, runs the appropriate formatter:
- Python → black
- JS/TS → prettier
- C# → dotnet format
- Go → gofmt
- Rust → rustfmt

**Behavior:** Only runs if the formatter is installed. Silently skips if not available.

### Session Start (`hooks/session-start/start_services.sh`)

Starts background services:
- System bridge daemon (if installed)

### Session Save (`hooks/stop/session_save.py`)

Saves session state to disk for resume capability.

## Creating Custom Hooks

### 1. Create the script

```python
#!/usr/bin/env python3
"""My custom hook."""
import json
import sys
import os

def main():
    # Read hook input from stdin
    stdin_data = sys.stdin.read()
    hook_input = json.loads(stdin_data) if stdin_data.strip() else {}

    # Available environment variables:
    # CLAUDE_TOOL_NAME - name of the tool being called
    # CLAUDE_TOOL_INPUT - JSON string of tool parameters
    # CLAUDE_FILE_PATH - file path (for Edit/Write hooks)

    tool_name = hook_input.get('tool_name', '')
    tool_input = hook_input.get('tool_input', {})

    # Your logic here

    # Exit codes:
    # 0 = success (allow the action)
    # 2 = block (prevent the action, message shown to Claude)
    sys.exit(0)

if __name__ == "__main__":
    main()
```

### 2. Register in settings.json

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /path/to/my_hook.py",
            "timeout": 10,
            "statusMessage": "Running my hook..."
          }
        ]
      }
    ]
  }
}
```

### 3. Matcher patterns

- `"Bash"` — matches Bash tool calls
- `"mcp__*"` — matches all MCP tool calls
- `"mcp__excel-mcp__*"` — matches specific MCP server
- `"Edit"` — matches file edit operations
- `"*"` — matches everything

## Hook Best Practices

1. **Keep hooks fast** — timeout is typically 5-10 seconds
2. **Fail gracefully** — if your hook errors, exit 0 (allow) rather than breaking Claude
3. **Log to files** — don't pollute stdout/stderr with debug info
4. **Use exit code 2** — only for genuine blocking conditions
5. **Test independently** — run your hook script standalone before registering
