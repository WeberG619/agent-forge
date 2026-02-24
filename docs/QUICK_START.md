# Getting Started with Cadre

Get Cadre running in 5 minutes. By the end, Claude Code will have persistent memory, 17 specialized sub-agents, safety hooks, and a common sense engine.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| [Claude Code](https://docs.anthropic.com/en/docs/claude-code) | CLI or VS Code extension |
| Claude Pro or Max subscription | Required for Claude Code |
| Python 3.8+ | `python3 --version` to check |
| Git | `git --version` to check |
| Node.js *(optional)* | Only needed for some MCP servers |

**Platform:** Windows (WSL), macOS, or Linux. Desktop automation features (Excel, browser control) require Windows/WSL.

---

## Step 1: Install

```bash
git clone https://github.com/WeberG619/cadre-ai.git
cd cadre-ai
./install.sh
```

The interactive installer walks you through setup:

```
╔══════════════════════════════════════════╗
║     Cadre Installer v1.0.0              ║
╚══════════════════════════════════════════╝

Pre-flight checks...
[✓] Python 3 found (3.11)
[✓] Git found
[✓] Claude Code directory found (~/.claude/)
[✓] Platform: WSL (Windows Subsystem for Linux)

Your name: Alex
Timezone [America/New_York]:
Install directory [~/.cadre-ai]:
```

### Choose your tier

The installer lets you pick which components to include:

| Component | Minimal | Developer | Power User |
|---|:---:|:---:|:---:|
| Core framework + agents | Y | Y | Y |
| Slash commands (22) | Y | Y | Y |
| Skills (8) | Y | Y | Y |
| Memory system | - | Y | Y |
| Voice/TTS | - | Y | Y |
| Safety hooks | - | Y | Y |
| Browser automation | - | - | Y |
| Desktop automation (Excel, Word) | - | - | Y |
| System bridge | - | - | Y |

**First time?** Start with **Developer** tier. You can always add more later by re-running `./install.sh`.

Pre-built example configs for each tier are in [`examples/`](../examples/).

---

## Step 2: Restart Claude Code

Close and reopen Claude Code. The new configuration loads automatically from `~/.claude/`.

Verify it worked:

```
you: What agents do you have available?
```

Claude should list the 17 sub-agents (code-analyzer, architect, DevOps, ML engineer, etc).

---

## Step 3: Your first 5 minutes

### Explore a codebase

```
/prime
```

Claude reads your project structure, key files, and dependencies. After priming, it has full context for follow-up tasks.

### Smart commits

```
# Stage some changes first
git add .

/commit
```

Claude analyzes the diff, writes a conventional commit message, and commits. No more "fix stuff" messages.

### Persistent memory

```
/memory
```

Store facts, decisions, and preferences that survive across sessions:

```
you: Remember that our API uses snake_case for all endpoints
```

Next session, Claude already knows. Corrections are stored automatically — if you correct Claude, it won't make the same mistake twice.

### Delegate to specialists

```
you: Review this PR for security issues
```

Claude routes the task to the right sub-agent (security reviewer, in this case) using the Strong Agent Framework — a 5-phase execution protocol: Orient, Investigate, Execute, Verify, Report.

```
you: /delegate code-analyzer "Find performance bottlenecks in src/"
```

Or delegate explicitly to any of the 17 agents.

### Voice summaries *(Developer tier+)*

```
/voice
```

Claude speaks task summaries aloud. Useful when you're heads-down in another window.

---

## Step 4: Understand the system

### How sub-agents work

When Claude delegates a task, it doesn't just spawn a generic helper. Each sub-agent gets:

1. **Strong Agent Framework** — a structured 5-phase methodology (orient, investigate, execute, verify, report)
2. **Memory context** — past corrections and relevant knowledge loaded automatically
3. **Common sense checks** — pre-action safety validation against known pitfalls

```
you: Refactor the auth module to use JWT

Claude Code ─── launching sub-agent: code-architect
  ├─ ORIENT: Parse task, assess scope (multi-file), plan approach
  ├─ INVESTIGATE: Read auth module, find all callers, check for tests
  ├─ EXECUTE: Modify files one at a time, matching existing style
  ├─ VERIFY: Re-read changes, run tests, check for regressions
  └─ REPORT: Summary of changes, files modified, test results
```

### How the common sense engine works

Before destructive or risky operations, Cadre runs a 3-step check:

1. **Classify** — Is this reversible? What's the blast radius?
2. **Check experience** — Any past corrections related to this action?
3. **Simulate** — If this goes wrong, what happens?

This prevents things like accidental `git push --force` on main, deleting production files, or committing secrets.

### How memory works

Memory persists in a local SQLite database via the claude-memory MCP server. Three types:

| Type | Example | Stored by |
|---|---|---|
| **Facts** | "API uses snake_case" | You, via `/memory` |
| **Corrections** | "Don't use --force on main" | Automatically, when you correct Claude |
| **Decisions** | "Chose PostgreSQL over MySQL for X reason" | Claude, during task execution |

At session start, Claude loads relevant context based on your current directory and task.

---

## Step 5: Customize

### Add your own rules

Edit `~/.claude/CLAUDE.md`. This file controls Claude's behavior globally:

```markdown
## My Rules
1. Always use TypeScript, never plain JavaScript
2. Run tests before committing
3. Use conventional commits (feat:, fix:, chore:)
```

### Create custom slash commands

Add a markdown file to `~/.claude/commands/`:

```bash
# ~/.claude/commands/deploy.md
Deploy the current branch to staging:
1. Run the test suite
2. Build the project
3. Push to the staging branch
4. Report the deployment URL
```

Now `/deploy` is available in Claude Code.

### Create custom agents

See [Creating Agents](CREATING_AGENTS.md) for how to define new sub-agents with specific capabilities and instructions.

### Configure hooks

See [Hook System](HOOKS.md) for how to add pre-commit guards, correction detection, session persistence, and other automation triggers.

---

## Project structure

```
cadre-ai/
├── framework/
│   ├── strong-agent.md          # 5-phase agent execution protocol
│   ├── agent-preamble.md        # Context injected into every sub-agent
│   └── common-sense/
│       ├── kernel.md            # Common sense rules
│       ├── seeds.json           # Pre-loaded corrections
│       ├── sense.py             # Safety check engine
│       └── inject.py            # Injects checks into agent prompts
├── agents/                      # 17 sub-agent definitions
├── commands/                    # 22 slash commands
├── skills/                      # 8 Claude.ai skill files
├── hooks/
│   ├── pre-tool-use/            # Runs before tool execution
│   ├── post-tool-use/           # Runs after tool execution
│   ├── user-prompt/             # Runs on user input (correction detection)
│   ├── session-start/           # Runs on startup (load services)
│   └── stop/                    # Runs on exit (save state)
├── mcp-servers/                 # MCP server implementations
├── system-bridge/               # Live system state monitoring
├── examples/
│   ├── minimal/                 # Bare-bones config
│   ├── developer/               # Recommended starting point
│   └── power-user/              # Full-featured config
├── templates/                   # CLAUDE.md template for installer
├── install.sh                   # Interactive installer
└── uninstall.sh                 # Clean removal
```

---

## Uninstall

```bash
cd cadre-ai
./uninstall.sh
```

Removes all installed files and restores your previous configuration from the backup created during install.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| "MCP server failed to start" | Check `python3` is on your PATH. Run `python3 ~/.cadre-ai/mcp-servers/claude-memory/src/server.py` manually to see errors. |
| Commands not showing up | Restart Claude Code. Check that `~/.claude/commands/` has `.md` files. |
| Memory not persisting | Ensure claude-memory MCP is in your `settings.json` or `settings.local.json`. |
| Hooks not firing | Check `~/.claude/settings.json` has the hooks block. See [Hook System](HOOKS.md). |
| Sub-agents are slow | Large `max_turns` values increase quality but take longer. Reduce for faster results. |
| Desktop automation fails | Windows/WSL only. Ensure the target app (Excel, browser) is open and accessible. |

For more, see [Troubleshooting](TROUBLESHOOTING.md).

---

## Next steps

- [Architecture Deep Dive](ARCHITECTURE.md) — understand how the pieces fit together
- [Creating Agents](CREATING_AGENTS.md) — build your own specialized agents
- [Creating Skills](CREATING_SKILLS.md) — make Claude.ai skills
- [MCP Server Reference](MCP_SERVERS.md) — all available integrations

---

*Questions? Open an [issue](https://github.com/WeberG619/cadre-ai/issues) or check existing discussions.*
