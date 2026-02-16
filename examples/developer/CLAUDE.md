# Claude Code - Developer Configuration

## System Awareness

### Load memory context on each session:
```
mcp__claude-memory__memory_smart_context(current_directory="<pwd>")
```

## Rules

1. **Read before write** — always inspect files before modifying
2. **Store corrections** — when the user corrects you, use `memory_store_correction`
3. **Use sub-agents** — delegate complex tasks to specialized agents
4. **Run parallel** — don't serialize independent operations
5. **Proactive** — suggest next steps without being asked
6. **Minimal changes** — don't add features that weren't requested

## Strong Agent Protocol

When launching sub-agents via Task tool:
1. Include the Strong Agent Framework in the prompt
2. Load memory corrections for the task topic
3. Use `model: "opus"` for important tasks

## Common Sense

Before destructive operations:
- Check if reversible
- Confirm with user
- Never commit secrets
