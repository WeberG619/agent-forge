---
description: Fix an issue, test/build, commit and push - all in one flow
---

# Fix and Commit Pipeline

Autonomous workflow: fix the issue, verify, commit, push.

## Instructions

The user will describe what needs fixing. Follow this pipeline WITHOUT stopping for confirmation between steps:

### Step 1: Understand
- Read the relevant files
- Identify what needs to change

### Step 2: Fix
- Make the code changes
- Keep changes minimal and focused

### Step 3: Verify
- If Python: run the relevant tests or import check
- If C#: run dotnet build
- If Node: run npm test or npm run build
- If config/docs: skip verification

### Step 4: Commit
- Stage only the files you changed
- Generate a commit message (feat/fix/chore)
- Commit with Co-Authored-By tag

### Step 5: Push
- Push to origin only if user approves
- If it's a submodule, also update and push the parent repo

### Step 6: Report
Show what was done in a brief summary.

### Rules
- Do NOT stop between steps unless something fails
- If build/test fails, fix it and retry (up to 2 attempts)
- If you can't fix it after 2 attempts, stop and explain
- Never force push
