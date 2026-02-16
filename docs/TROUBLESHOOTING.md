# Troubleshooting

Common issues and solutions for Agent Forge.

## Installation Issues

### "Python 3 not found"

Install Python 3.8+:
```bash
# Ubuntu/Debian
sudo apt install python3

# macOS
brew install python3

# Windows
# Download from python.org
```

### Installer fails with permission error

```bash
chmod +x install.sh
./install.sh
```

### Settings not loading after install

1. Make sure you restarted Claude Code
2. Check that `~/.claude/CLAUDE.md` exists
3. Check that `~/.claude/settings.json` exists
4. Verify MCP server paths in `~/.claude/settings.local.json`

## MCP Server Issues

### Memory server not starting

```bash
# Check if dependencies are installed
pip install -r ~/.agent-forge/mcp-servers/claude-memory/requirements.txt

# Test the server manually
python3 ~/.agent-forge/mcp-servers/claude-memory/src/server.py
```

### Voice not working

1. Ensure Edge TTS dependencies are installed:
   ```bash
   pip install edge-tts
   ```
2. Check internet connectivity (Edge TTS requires internet)
3. On Windows, SAPI fallback should work offline

### Windows MCP servers failing

1. Make sure you're using **Windows Python**, not WSL Python
2. Install Python on Windows (from python.org), not just in WSL
3. Run the target application (Excel, Word) at least once manually
4. Check that `powershell.exe` is accessible from WSL:
   ```bash
   powershell.exe -Command "echo test"
   ```

## Hook Issues

### Pre-commit guard blocking everything

The guard blocks commits if sensitive files are staged. To fix:
```bash
# Unstage the sensitive file
git reset HEAD .env

# Or if it's a false positive, check the file manually
git diff --cached
```

### Hooks timing out

Increase the timeout in `~/.claude/settings.json`:
```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

### Hooks causing errors

Disable a specific hook by removing it from settings.json, or disable all hooks temporarily:
```json
{
  "hooks": {}
}
```

## System Bridge Issues

### Daemon not starting

```bash
# Check if already running
python3 ~/.agent-forge/system-bridge/daemon.py --status

# Start in foreground for debugging
python3 ~/.agent-forge/system-bridge/daemon.py --console

# Check logs
cat ~/.agent-forge/system-bridge/daemon.log
```

### live_state.json not updating

1. Check daemon is running: `cat ~/.agent-forge/system-bridge/daemon.pid`
2. Check health: `cat ~/.agent-forge/system-bridge/health.json`
3. On WSL, ensure PowerShell is accessible

## General Issues

### Claude doesn't seem to use the new config

1. Run `/compact` to clear context
2. Start a new session
3. Check that CLAUDE.md is being read: ask Claude "What does your CLAUDE.md say?"

### Slash commands not showing up

Commands must be in `~/.claude/commands/` with a `.md` extension. Check:
```bash
ls ~/.claude/commands/
```

### Context window filling up fast

The Power Kit adds context overhead. To reduce:
1. Remove MCP servers you don't use from settings.local.json
2. Simplify CLAUDE.md — remove sections you don't need
3. Use `/compact` when context gets large

## Uninstalling

```bash
cd /path/to/agent-forge
./uninstall.sh
```

This removes all Power Kit files and optionally restores your backup configuration.
