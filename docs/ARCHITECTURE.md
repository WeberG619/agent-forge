# Architecture

How Cadre works under the hood.

## System Overview

```
┌─────────────────────────────────────────────────┐
│                  Claude Code                     │
│                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐      │
│  │ CLAUDE.md│  │ Commands │  │  Hooks   │      │
│  │ (config) │  │ (slash)  │  │ (safety) │      │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘      │
│       │              │              │             │
│  ┌────▼──────────────▼──────────────▼─────┐      │
│  │          Claude's Context              │      │
│  │  ┌─────────────┐  ┌──────────────┐    │      │
│  │  │ Strong Agent│  │ Common Sense │    │      │
│  │  │  Framework  │  │   Engine     │    │      │
│  │  └─────────────┘  └──────────────┘    │      │
│  └────────────────────┬──────────────────┘      │
│                       │                          │
│  ┌────────────────────▼──────────────────┐      │
│  │           MCP Servers                  │      │
│  │  ┌────────┐ ┌───────┐ ┌────────────┐ │      │
│  │  │ Memory │ │ Voice │ │  Browser   │ │      │
│  │  └────────┘ └───────┘ └────────────┘ │      │
│  └────────────────────────────────────────┘      │
│                                                  │
│  ┌────────────────────────────────────────┐      │
│  │         System Bridge Daemon           │      │
│  │    (open apps, clipboard, monitors)    │      │
│  └────────────────────────────────────────┘      │
└─────────────────────────────────────────────────┘
```

## Components

### CLAUDE.md

The main configuration file. Loaded by Claude Code at the start of every session. Contains:
- System awareness instructions (read system state, load memory)
- Rules and constraints
- Strong Agent Protocol for sub-agent delegation
- User identity and preferences

### Strong Agent Framework

A 5-phase execution methodology injected into every sub-agent:

1. **Load Context** — Check memory for corrections and relevant context
2. **Orient** — Parse task, assess scope, rate confidence
3. **Investigate** — Read files, search patterns, map dependencies
4. **Execute** — Make changes in small steps, match style
5. **Report** — Summarize results, store learnings

This ensures every sub-agent operates with consistent quality and safety standards.

### Common Sense Engine

A pre-action safety system with three components:

- **kernel.md** — Decision loop (classify → check experience → simulate)
- **seeds.json** — 15 universal safety corrections (git secrets, force-push, data loss, etc.)
- **sense.py** — Python library for programmatic pre-action checks

### Hooks

Claude Code hooks that run at specific lifecycle points:

| Hook | When | Purpose |
|------|------|---------|
| `pre_commit_guard.py` | Before `git commit` | Check staged files for secrets |
| `detect_correction.py` | Every user message | Detect when user is correcting Claude |
| `start_services.sh` | Session start | Start system bridge daemon |
| `auto_format.sh` | After file edit | Auto-format code |
| `session_save.py` | Session end | Save session state for resume |

### MCP Servers

Model Context Protocol servers that give Claude new capabilities:

| Server | Capability |
|--------|-----------|
| **claude-memory** | Long-term memory — corrections, facts, decisions |
| **voice-mcp** | Text-to-speech via Edge TTS |
| **windows-browser** | Browser automation via Edge CDP |
| **excel-mcp** | Excel automation via COM |
| **word-mcp** | Word automation via COM |
| **powerpoint-mcp** | PowerPoint automation via COM |

### System Bridge

A background daemon that writes `live_state.json` every 10 seconds with:
- Open applications and window titles
- Active/focused window
- System resources (CPU, memory)
- Clipboard contents
- Recent files
- Monitor configuration

Claude reads this file to proactively understand what the user is working on.

## Data Flow

1. **Session Start** → Hooks fire → System bridge starts → Memory loads context
2. **User Message** → Correction detection hook → Claude processes with full context
3. **Sub-agent Launch** → Strong Agent Framework loads → Memory checked → Task executed
4. **Pre-action** → Common sense engine checks → Corrections recalled → Go/no-go decision
5. **Session End** → State saved → Memory updated → Ready for next session
