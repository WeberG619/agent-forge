# Agent Forge

**Production-grade agent framework for Claude Code.**
17 sub-agents. Persistent memory. Desktop automation. Common sense engine.

[![GitHub stars](https://img.shields.io/github/stars/WeberG619/agent-forge?style=flat-square)](https://github.com/WeberG619/agent-forge/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/WeberG619/agent-forge?style=flat-square)](https://github.com/WeberG619/agent-forge/network/members)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg?style=flat-square)](https://www.gnu.org/licenses/gpl-3.0)
[![Python 3.8+](https://img.shields.io/badge/Python-3.8+-3776AB.svg?style=flat-square)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg?style=flat-square)](#requirements)

Built by a BIM automation specialist who needed AI agents that actually work in real professional workflows.

---

## Quick Start

```bash
git clone https://github.com/WeberG619/agent-forge.git
cd agent-forge
./install.sh
```

Restart Claude Code. You now have memory, 17 sub-agents, 22 slash commands, safety hooks, and a common sense engine.

---

## What It Looks Like

```
you: Open the project spreadsheet, pull the cost data, and build a summary deck

Claude Code ─── delegating to orchestrator agent
  ├─ memory_smart_recall("project spreadsheet, cost data")
  │   └─ Found: project_costs.xlsx on D:\Projects\TAJ
  │
  ├─ launching sub-agent: excel-automation
  │   ├─ open_workbook("D:\Projects\TAJ\project_costs.xlsx")
  │   ├─ read_range("Sheet1", "A1:F48")
  │   └─ ✓ Extracted 48 line items, $2.4M total
  │
  ├─ launching sub-agent: powerpoint-builder
  │   ├─ create_presentation()
  │   ├─ add_slide("Cost Summary", table_data)
  │   ├─ add_slide("Budget vs Actual", chart_data)
  │   └─ save_as("TAJ_Cost_Summary.pptx")
  │
  ├─ memory_store("TAJ cost summary created", project="TAJ")
  └─ voice: "Done. 3-slide deck saved. Total budget is 2.4 million, 12% under estimate."

✓ Task complete in 34 seconds
```

---

## Features

### Core Intelligence
- **Strong Agent Framework** -- 5-phase execution: Orient, Investigate, Execute, Verify, Report
- **Common Sense Engine** -- pre-action safety checks against past mistakes, blocks destructive operations
- **Persistent Memory** -- corrections, decisions, facts, and preferences survive across sessions
- **17 Sub-Agents** -- code analysis, architecture, ML, DevOps, full-stack, C#, Python, and more

### Desktop Automation
- **Excel** -- read, write, charts, formulas, pivot tables via COM automation
- **Word / PowerPoint** -- document and presentation generation
- **Browser** -- Edge CDP control: navigate, screenshot, type, scroll, click
- **System Bridge** -- real-time awareness of open apps, monitors, clipboard, recent files

### Developer Workflow
- **22 Slash Commands** -- `/commit`, `/delegate`, `/review-and-fix`, `/prime`, `/fix-and-commit`, etc.
- **Safety Hooks** -- pre-commit guards, MCP seatbelts, secret detection
- **8 Claude.ai Skills** -- idea validation, product design, marketing, competitive analysis

### Integrations
- **Voice/TTS** -- Claude speaks summaries and announcements via Edge TTS
- **SQLite** -- structured data storage via MCP
- **Financial** -- stock analysis, portfolio tracking, market data
- **AI Render** -- Flux Pro photorealistic rendering from text prompts

---

## Architecture

```
 You
  │
  ▼
┌──────────────────────────────────────────────────────┐
│  Claude Code                                         │
│                                                      │
│  ┌──────────────────────────────────────────┐        │
│  │  Agent Forge                              │       │
│  │                                           │       │
│  │  ┌─────────────┐  ┌──────────────────┐   │       │
│  │  │ Strong Agent │  │  Common Sense    │   │       │
│  │  │  Framework   │  │    Engine        │   │       │
│  │  └──────┬──────┘  └────────┬─────────┘   │       │
│  │         │                  │              │       │
│  │  ┌──────┴──────────────────┴─────────┐   │       │
│  │  │        Memory System              │   │       │
│  │  │  corrections · facts · decisions  │   │       │
│  │  └──────────────────────────────────-┘   │       │
│  └──────────────┬────────────────────────────┘       │
│                 │                                     │
│    ┌────────────┼────────────┐                       │
│    ▼            ▼            ▼                        │
│ 17 Agents   22 Commands   Hooks                      │
└────┬────────────┬────────────┬───────────────────────┘
     │            │            │
     ▼            ▼            ▼
  MCP Servers  System Bridge  Voice/TTS
  (Excel, Word, Browser,      (Edge TTS)
   SQLite, Financial,
   AI Render)
```

---

## How It Compares

Scored on real-world capability depth across 12 categories ([full interactive comparison](docs/comparison-openclaw.html)):

| Category | Agent Forge | OpenClaw |
|---|:---:|:---:|
| Desktop Automation | **10**/10 | 6/10 |
| Memory System | **10**/10 | 5/10 |
| Sub-Agent System | **10**/10 | 4/10 |
| Safety / Common Sense | **10**/10 | 3/10 |
| Developer Workflow | **10**/10 | 5/10 |
| BIM / CAD / Engineering | **10**/10 | 0/10 |
| **Total (12 categories)** | **99/120** | **58/120** |

---

## Configuration Tiers

| Tier | What's Included |
|---|---|
| **Minimal** | Framework + commands + agent definitions. No MCP servers. |
| **Developer** | Framework + memory + voice + git hooks. Good for most developers. |
| **Power User** | Everything. Desktop automation, system bridge, all MCP servers. |

See [`examples/`](examples/) for ready-to-use configurations for each tier.

## Requirements

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) (CLI or VS Code extension)
- Claude Pro or Max subscription
- Python 3.8+
- Windows 10/11 (for desktop automation features) or macOS/Linux (core features)

## Documentation

- [Quick Start Guide](docs/QUICK_START.md)
- [Architecture Deep Dive](docs/ARCHITECTURE.md)
- [Creating Custom Agents](docs/CREATING_AGENTS.md)
- [Creating Skills](docs/CREATING_SKILLS.md)
- [Hook System](docs/HOOKS.md)
- [MCP Server Reference](docs/MCP_SERVERS.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)

## Uninstall

```bash
./uninstall.sh
```

## Contributing

Contributions welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

GPL-3.0 -- see [LICENSE](LICENSE) for details.

## Credits

Built by [Weber Gouin](https://github.com/WeberG619) at BIM Ops Studio.

Powered by [Claude Code](https://claude.com/claude-code) by Anthropic.

---

If this helped you, [star the repo](https://github.com/WeberG619/agent-forge). It helps others find it.

---

*Agent Forge is an independent community project. It is not affiliated with, endorsed by, or officially connected to Anthropic, PBC. "Claude" and "Claude Code" are trademarks of Anthropic.*
