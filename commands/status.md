---
description: Show status of repos, system state, and open apps
---

# Full Status Check

## Git Repos
Show the state of git repos in the current workspace:

```bash
echo "=== $(basename $(pwd)) ===" && echo "Branch: $(git branch --show-current)" && git status --short
```

## System State
If the system bridge is installed, read the live state:
```bash
cat {{INSTALL_DIR}}/system-bridge/live_state.json 2>/dev/null || echo "System bridge not running"
```

## Summary
Present a concise summary:
- Each repo: branch, clean/dirty, ahead/behind
- Open apps and active window (if system bridge running)
- System resources (if available)
- Any items needing attention
