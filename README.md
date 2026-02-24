<p align="center">
  <img src="assets/cadre-ai-logo.png" alt="Cadre AI" width="400">
</p>

<p align="center">
  <strong>Your AI agent squad for Claude Code.</strong><br>
  17 specialized agents. Persistent memory. Desktop automation. Common sense engine.
</p>

<p align="center">
  <a href="https://github.com/WeberG619/cadre-ai/stargazers"><img src="https://img.shields.io/github/stars/WeberG619/cadre-ai?style=flat-square" alt="Stars"></a>
  <a href="https://github.com/WeberG619/cadre-ai/network/members"><img src="https://img.shields.io/github/forks/WeberG619/cadre-ai?style=flat-square" alt="Forks"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-green.svg?style=flat-square" alt="License: MIT"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.8+-3776AB.svg?style=flat-square" alt="Python 3.8+"></a>
  <a href="#requirements"><img src="https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg?style=flat-square" alt="Platform"></a>
</p>

---

## Quick Start

```bash
git clone https://github.com/WeberG619/cadre-ai.git
cd cadre-ai
./install.sh
```

Restart Claude Code. That's it. You now have memory, 17 sub-agents, 22 slash commands, safety hooks, and a common sense engine.

**[Full Getting Started Guide](docs/QUICK_START.md)** — 5-minute walkthrough with examples for each feature.

---

## What It Does

You give Claude Code a complex task. Cadre breaks it down, dispatches specialized agents, remembers context from past sessions, checks its own work against a common sense engine, and reports back.

```
you: Open the project spreadsheet, pull the cost data, and build a summary deck

Claude Code ─── delegating to orchestrator agent
  ├─ memory_smart_recall("project spreadsheet, cost data")
  │   └─ Found: project_costs.xlsx on D:\Projects
  │
  ├─ launching sub-agent: excel-automation
  │   ├─ open_workbook("project_costs.xlsx")
  │   ├─ read_range("Sheet1", "A1:F48")
  │   └─ ✓ Extracted 48 line items, $2.4M total
  │
  ├─ launching sub-agent: powerpoint-builder
  │   ├─ create_presentation()
  │   ├─ add_slide("Cost Summary", table_data)
  │   ├─ add_slide("Budget vs Actual", chart_data)
  │   └─ save_as("Cost_Summary.pptx")
  │
  ├─ memory_store("cost summary created")
  └─ voice: "Done. 3-slide deck saved."

✓ Task complete in 34 seconds
```

---

## Features

**Core Intelligence**
- **Strong Agent Framework** — 5-phase execution: Orient, Investigate, Execute, Verify, Report
- **Common Sense Engine** — pre-action safety checks against past mistakes, blocks destructive operations
- **Persistent Memory** — corrections, decisions, and preferences survive across sessions
- **17 Sub-Agents** — code analysis, architecture, ML, DevOps, full-stack, C#, Python, and more

**Desktop Automation**
- **Excel** — read, write, charts, formulas, pivot tables via COM automation
- **Word / PowerPoint** — document and presentation generation
- **Browser** — Edge CDP control: navigate, screenshot, type, scroll, click
- **System Bridge** — real-time awareness of open apps, monitors, clipboard, recent files

**Developer Workflow**
- **22 Slash Commands** — `/commit`, `/delegate`, `/review-and-fix`, `/prime`, `/fix-and-commit`, and more
- **Safety Hooks** — pre-commit guards, MCP seatbelts, secret detection
- **8 Claude.ai Skills** — idea validation, product design, marketing, competitive analysis

**Integrations**
- **Voice/TTS** — Claude speaks summaries and announcements via Edge TTS
- **SQLite** — structured data storage via MCP
- **Financial** — stock analysis, portfolio tracking, market data
- **AI Render** — Flux Pro photorealistic rendering from text prompts

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
│  │  Cadre                                    │       │
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

## Configuration Tiers

| Tier | What's Included |
|---|---|
| **Minimal** | Framework + commands + agent definitions. No MCP servers. |
| **Developer** | Framework + memory + voice + git hooks. Good for most developers. |
| **Power User** | Everything. Desktop automation, system bridge, all MCP servers. |

See [`examples/`](examples/) for ready-to-use configurations for each tier.

---

## Requirements

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) (CLI or VS Code extension)
- Claude Pro or Max subscription
- Python 3.8+
- Windows 10/11 (for desktop automation features) or macOS/Linux (core features)

## Documentation

- [Getting Started Guide](docs/QUICK_START.md)
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

MIT — see [LICENSE](LICENSE) for details.

## Credits

Built by [Weber Gouin](https://github.com/WeberG619) at BIM Ops Studio.

Powered by [Claude Code](https://claude.com/claude-code) by Anthropic.

---

If this helped you, [star the repo](https://github.com/WeberG619/cadre-ai) — it helps others find it.

---

*Cadre is an independent community project. Not affiliated with or endorsed by Anthropic, PBC. "Claude" and "Claude Code" are trademarks of Anthropic.*
