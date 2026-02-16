---
description: Execute formal workflow pipelines with checkpoints and validation
allowed-tools: Read, Bash, Task, mcp__claude-memory__memory_store, mcp__claude-memory__memory_recall, mcp__voice__speak
---

# Pipeline Executor

Execute formal workflow pipelines with phases, checkpoints, and validation.

## Usage

```
/pipeline <pipeline-name> [options]
/pipeline --list
```

**Options:**
- `--dry-run` - Preview execution without making changes
- `--auto-approve` - Skip checkpoint approval prompts
- `--resume` - Resume from last saved state
- `--list` - Show all available pipelines

## How Pipelines Work

A pipeline is a sequence of phases, each containing steps and checkpoints:

```
Phase 1: Setup
  ├── Step 1.1: Read configuration
  ├── Step 1.2: Validate inputs
  └── Checkpoint: "Configuration looks correct?"

Phase 2: Execute
  ├── Step 2.1: Process data
  ├── Step 2.2: Transform results
  └── Checkpoint: "Results look correct?"

Phase 3: Finalize
  ├── Step 3.1: Save outputs
  └── Step 3.2: Generate report
```

## Creating Custom Pipelines

Create a JSON file in `{{INSTALL_DIR}}/pipelines/`:

```json
{
  "name": "my-pipeline",
  "description": "What this pipeline does",
  "phases": [
    {
      "name": "Phase 1",
      "steps": [
        {"action": "read_file", "target": "config.json"},
        {"action": "validate", "rules": ["required_fields"]}
      ],
      "checkpoint": {
        "message": "Configuration validated. Proceed?",
        "requires_approval": true
      }
    }
  ]
}
```

## Checkpoint Handling

When a checkpoint requires approval:
- Show the checkpoint message to the user
- Ask for their decision (proceed/adjust/stop)
- If not using `--auto-approve`, wait for response

## Rules

- Always pause at checkpoints marked `requires_approval: true`
- Store pipeline outcomes in memory for future reference
- On failure, save state for `--resume` capability
