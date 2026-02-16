# Quick Start Guide

Get Claude Power Kit running in 5 minutes.

## 1. Clone and Install

```bash
git clone https://github.com/WeberG619/claude-power-kit.git
cd claude-power-kit
./install.sh
```

The installer will:
- Ask your name and timezone
- Let you choose which components to install
- Copy framework files, agents, commands, and skills
- Generate your CLAUDE.md configuration
- Set up MCP servers and hooks

## 2. Restart Claude Code

Close and reopen Claude Code (CLI or VS Code). The new configuration loads automatically.

## 3. Try It Out

### Smart commits
```
/commit
```
Claude analyzes staged changes and generates a conventional commit message.

### Explore a codebase
```
/prime
```
Claude reads your project structure, dependencies, and key files.

### Memory
```
/memory
```
Store knowledge that persists across sessions. Claude remembers your corrections, decisions, and preferences.

### Voice
```
/voice
```
Hear Claude speak summaries aloud (requires voice MCP server).

### Delegate to sub-agents
```
/delegate code-analyzer "Analyze src/ for performance issues"
```
Launch specialized agents for focused tasks.

## 4. Customize

Edit `~/.claude/CLAUDE.md` to add your own rules and preferences.

Create custom slash commands in `~/.claude/commands/`.

See [CREATING_AGENTS.md](CREATING_AGENTS.md) and [HOOKS.md](HOOKS.md) for advanced customization.

## Troubleshooting

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for common issues.
