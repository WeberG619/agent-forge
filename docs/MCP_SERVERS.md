# MCP Servers Guide

MCP (Model Context Protocol) servers give Claude new capabilities by providing tools that Claude can call.

## Core Servers

### claude-memory

Long-term memory that persists across sessions.

**Tools:** `memory_store`, `memory_recall`, `memory_semantic_search`, `memory_store_correction`, `memory_smart_context`, and more.

**Use case:** Claude remembers your corrections, project decisions, and preferences.

**Setup:**
```bash
pip install -r mcp-servers/claude-memory/requirements.txt
```

### voice-mcp

Text-to-speech using Microsoft Edge TTS with Windows SAPI fallback.

**Tools:** `speak`, `speak_summary`, `list_voices`, `stop_speaking`

**Voices:** andrew, adam, guy, davis, jenny, aria, amanda, michelle

**Setup:**
```bash
pip install -r mcp-servers/voice-mcp/requirements.txt
```

## Windows-Only Servers

These servers require Windows Python (not WSL Python) because they use COM automation.

### windows-browser

Browser automation via Edge CDP (Chrome DevTools Protocol).

**Tools:** `browser_open`, `browser_navigate`, `browser_screenshot`, `browser_type`, `browser_send_keys`, `browser_scroll`, `browser_search`

**Note:** Uses Tab + Enter navigation. Direct clicking by coordinates is unreliable.

### excel-mcp

Full Excel automation — read, write, format, charts, formulas, pivot tables.

**Tools:** 80+ tools for complete Excel control.

**Requires:** Microsoft Excel, xlwings, Windows Python

### word-mcp

Word document automation.

**Requires:** Microsoft Word, pywin32, Windows Python

### powerpoint-mcp

PowerPoint automation.

**Requires:** Microsoft PowerPoint, pywin32, Windows Python

## Windows Server Pattern

Windows MCP servers must run through PowerShell because they need Windows Python (not WSL Python):

```json
{
  "command": "powershell.exe",
  "args": [
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-Command", "cd 'C:\\path\\to\\server'; python server.py"
  ]
}
```

## Adding Your Own MCP Server

1. Create a directory in `mcp-servers/my-server/`
2. Create `server.py` using the MCP Python SDK
3. Create `requirements.txt`
4. Add to `settings.local.json`:

```json
{
  "mcpServers": {
    "my-server": {
      "command": "python3",
      "args": ["/path/to/my-server/server.py"],
      "disabled": false
    }
  }
}
```

5. Restart Claude Code

## Troubleshooting

### Server not starting
- Check `claude code mcp` for server status
- Verify Python path and dependencies
- Check for port conflicts

### Windows servers failing
- Ensure you're using Windows Python, not WSL Python
- Check COM permissions (run Excel/Word at least once manually)
- Verify `powershell.exe` is accessible from WSL
