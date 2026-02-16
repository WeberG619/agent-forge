# Agent Forge

> Turn Claude Code into an autonomous agent with memory, voice, desktop control, and a common sense engine.

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

---

## What You Get

- **Long-term memory** that persists across sessions — Claude remembers your corrections, decisions, and project context
- **17 specialized sub-agents** for code analysis, architecture, ML, DevOps, and more
- **Common sense engine** that prevents destructive mistakes before they happen
- **Voice output** — hear Claude speak summaries and announcements via Edge TTS
- **Desktop automation** — control Excel, Word, PowerPoint, and browser via MCP
- **20+ slash commands** for power workflows (`/commit`, `/delegate`, `/review-and-fix`, etc.)
- **System bridge** — Claude sees your open apps, monitors, clipboard, and recent files in real-time
- **8 Claude.ai Skills** — idea validation, product design, marketing, and more
- **Extensible** — add your own agents, skills, hooks, and MCP servers

## Quick Start

```bash
git clone https://github.com/WeberG619/agent-forge.git
cd agent-forge
./install.sh
```

Restart Claude Code. That's it.

## Requirements

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) (CLI or VS Code extension)
- Claude Pro or Max subscription
- Python 3.8+
- Windows 10/11 (for desktop automation features) or macOS/Linux (core features)

## What's Inside

```
agent-forge/
├── framework/           # Core agent intelligence
│   ├── strong-agent.md  # 5-phase sub-agent execution framework
│   ├── agent-preamble.md # Context injection template
│   └── common-sense/    # Decision loop + safety corrections
├── agents/              # 17 ready-to-use sub-agent definitions
├── skills/              # 8 Claude.ai skill files
├── commands/            # 20+ slash commands
├── hooks/               # Safety hooks (pre-commit guard, MCP seatbelt, etc.)
├── system-bridge/       # Live system state monitoring daemon
├── mcp-servers/         # MCP server source code
├── templates/           # User config templates
├── examples/            # Minimal, developer, and power-user configs
└── docs/                # Full documentation
```

## Components

### Core (always installed)

| Component | Description |
|-----------|-------------|
| **Strong Agent Framework** | 5-phase execution methodology for sub-agents (Orient → Investigate → Execute → Verify → Report) |
| **Common Sense Engine** | Pre-action safety checks against past mistakes. Blocks destructive operations, warns on risky ones. |
| **Slash Commands** | `/commit`, `/delegate`, `/prime`, `/review-and-fix`, `/fix-and-commit`, and more |
| **Agent Definitions** | Pre-built system prompts for 17 specialized sub-agents |

### Optional

| Component | Platform | Description |
|-----------|----------|-------------|
| **Memory System** | All | Long-term memory MCP server — corrections, facts, decisions persist across sessions |
| **Voice/TTS** | All (best on Windows) | Edge TTS with SAPI fallback — Claude speaks summaries aloud |
| **Browser Automation** | Windows | Edge CDP WebSocket control — navigate, screenshot, type, scroll |
| **Excel MCP** | Windows | Full Excel automation via COM — read, write, charts, formulas |
| **Word MCP** | Windows | Word document automation via COM |
| **PowerPoint MCP** | Windows | PowerPoint automation via COM |
| **System Bridge** | Windows | Real-time monitoring daemon — open apps, monitors, clipboard, recent files |
| **SQLite Server** | All | SQLite database MCP for structured data |
| **AI Render** | All | Flux Pro photorealistic rendering |
| **Financial MCP** | All | Stock market analysis and portfolio tracking |

## How It Works

### The Common Sense Engine

Before every significant action, Claude runs a 3-step check:

1. **Classify** — Is this reversible? Does it affect shared systems?
2. **Check experience** — Have I made this mistake before? Does a correction exist?
3. **Simulate** — If this goes wrong, what happens?

Pre-loaded with 15 universal safety corrections (git secrets, force-push protection, data loss prevention, etc.) and learns new ones from your feedback.

### The Strong Agent Framework

Sub-agents follow a structured 5-phase methodology:

1. **Load Context** — Check memory for relevant corrections and past decisions
2. **Orient** — Parse the task, assess scope, rate confidence
3. **Investigate** — Read files, search patterns, map dependencies
4. **Execute** — Make changes in small steps, match existing style
5. **Report** — Summarize results, store learnings in memory

### Memory System

Claude remembers across sessions:
- **Corrections** — mistakes it made and how to avoid them
- **Decisions** — architectural choices and their rationale
- **Facts** — project-specific knowledge
- **Preferences** — your coding style and workflow preferences

## Customization

### Add your own agent

Create `~/.claude/agents/my-agent.md`:

```markdown
name: my-agent
description: Specialized agent for my use case

You are a specialized agent for [domain].
Your responsibilities:
1. ...
2. ...
```

### Add your own slash command

Create `~/.claude/commands/my-command.md`:

```markdown
---
description: What this command does
---

# My Command

Instructions for Claude when user runs /my-command...
```

### Add your own hook

See [docs/HOOKS.md](docs/HOOKS.md) for the full hook system guide.

## Examples

Three example configurations are included:

- **`examples/minimal/`** — Just the framework and commands. No MCP servers.
- **`examples/developer/`** — Framework + memory + voice + git hooks. Good for most developers.
- **`examples/power-user/`** — Everything enabled. Desktop automation, system bridge, all MCP servers.

## Uninstall

```bash
./uninstall.sh
```

Removes all installed files and restores your original Claude Code configuration (backup is created during install).

## Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

GPL-3.0 — see [LICENSE](LICENSE) for details.

## Credits

Built by [Weber Gouin](https://github.com/WeberG619) at BIM Ops Studio.

Powered by [Claude Code](https://claude.com/claude-code) by Anthropic.
