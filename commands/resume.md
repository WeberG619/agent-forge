# Resume Project State

Load the current project context from memory and resume where we left off.

## Instructions

1. First, load context from memory:
```
mcp__claude-memory__memory_smart_context(current_directory="{{CWD}}")
```

2. If project context is found, present:
   - Last session summary
   - Recent decisions and corrections
   - Open questions or pending tasks
   - Suggested next actions

3. If no context exists for the current project, offer to create it:
   - Ask what the project is about
   - Store initial project context in memory

4. If resuming active work:
   - State the last known checkpoint
   - Ask "Continue from here?" before proceeding

## Resume Flow

```
1. /resume
2. Claude loads memory for current directory
3. Claude presents:
   "Resuming [project-name]
    Last session: [summary]
    Next steps:
      1. [action 1]
      2. [action 2]
    Continue?"
4. User: "yes"
5. Claude picks up where it left off
```
