---
description: Smart git commit with auto-generated message based on staged changes
---

# Git Commit Workflow

## Current State
```bash
git status --short
```

## Recent Commits (for style reference)
```bash
git log --oneline -5
```

## Staged Diff
```bash
git diff --cached --stat
```

## Instructions

Based on the staged changes above:

1. **Analyze** what was changed (features, fixes, refactors)
2. **Generate** a concise commit message following the repo's style
3. **Stage** any unstaged related files if appropriate (ask first for new files)
4. **Commit** with the generated message

### Commit Message Format
```
<type>: <brief description>

<optional body explaining why>

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
```

Types: feat, fix, refactor, docs, style, test, chore

### Rules
- Do NOT push unless explicitly asked
- Do NOT amend commits that have been pushed
- Ask before staging untracked files
- Keep message under 72 chars for subject line
