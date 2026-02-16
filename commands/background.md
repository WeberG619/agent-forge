# Background - Delegate Work to Background Agent

## Purpose
Delegate long-running or independent tasks to background agents

## Variables
- PROMPT: The task description for the background agent
- MODEL: Model to use (default: claude-3-5-sonnet)
- REPORT_FILE: Where to save results

## Workflow
1. Create report directory: agents/background/
2. Generate session ID from timestamp
3. Create report file: agents/background/{task}_{timestamp}.md
4. Launch background agent with:
   ```
   claude --model {MODEL} \
         --yolo \
         --output agents/background/{task}_{timestamp}.md \
         "{PROMPT}"
   ```

## Report Format
Background agent will write:
- Task summary
- Actions taken
- Results/outputs
- Any errors or blockers