---
description: Review code quality, fix issues found, commit and push
---

# Review and Fix Pipeline

Autonomous code review, fix, and commit workflow.

## Instructions

The user will point to a file or project. Follow this pipeline:

### Step 1: Review
Spawn a code-reviewer agent on the target code. Look for:
- Bugs and logic errors
- Type issues
- Missing error handling at boundaries
- Security concerns (if applicable)

### Step 2: Present Findings
Show a brief list of issues found, categorized by severity (high/medium/low).

### Step 3: Fix (if issues found)
- Fix all high and medium severity issues
- Skip low severity unless user asks

### Step 4: Verify
- Build or test to confirm fixes don't break anything

### Step 5: Commit and Push
- Commit with message describing what was fixed
- Push to origin only if user approves

### Rules
- Run review and fix in one flow
- Only stop to ask if there are architectural decisions to make
- Low severity issues: note them but don't fix unless asked
