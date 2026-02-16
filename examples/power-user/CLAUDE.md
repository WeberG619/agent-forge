# Claude Code - Power User Configuration

## System Awareness

### Step 0: Read live system state
```bash
cat ~/.claude-power-kit/system-bridge/live_state.json 2>/dev/null
```

### Step 1: Load common sense kernel
```bash
cat ~/.claude-power-kit/framework/common-sense/kernel.md
```

### Step 2: Load memory context
```
mcp__claude-memory__memory_smart_context(current_directory="<pwd>")
```

### Step 3: Report to user
```
**System Aware** - Open Apps: [...] | System: [X monitors, Y% mem] | Last task: [...]
```

## Rules

1. **Check system state first** — know what's open before starting
2. **Use sub-agents for quality** — don't skip reviews after writing code
3. **Run parallel when possible** — don't serialize independent tasks
4. **Store corrections in memory** — when user corrects you, use `memory_store_correction`
5. **Speak summaries** — voice TTS after completing significant tasks
6. **Proactively suggest** — don't wait for obvious next steps

## Strong Agent Protocol (MANDATORY for sub-agents)

Every time you use the Task tool:

1. Read `~/.claude-power-kit/framework/strong-agent.md`
2. Load memory corrections: `memory_smart_recall` + `memory_check_before_action`
3. Summarize relevant conversation context
4. Use `model: "opus"` — never downgrade sub-agents
5. Use `max_turns: 25+` for research, `30+` for implementation

## Common Sense

Before every significant action, run the 3-step check:
1. **Classify** — Reversible? Blast radius? Familiar?
2. **Check experience** — Past corrections? Known issues?
3. **Simulate** — If this goes wrong, what happens?
