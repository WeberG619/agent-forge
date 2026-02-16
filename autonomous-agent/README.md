# Autonomous Agent for Claude Code

A persistent background agent that watches, thinks, acts, and reports. This system makes Claude Code proactive rather than reactive by running continuously in the background.

## Architecture

```
autonomous-agent/
  run_agent.py           - Main entry point (start/stop/status)
  agent_control.py       - CLI to control the agent and manage tasks
  config.json.example    - Example configuration for triggers
  requirements.txt       - Python dependencies
  core/
    agent.py             - Main agent loop (orchestrates all components)
    task_queue.py         - SQLite-backed persistent task queue
    task_executor.py      - Parallel task executor via Claude Code CLI
    decision_engine.py    - Trigger rules and decision framework
    notifier.py           - Notification routing (Telegram, console)
    context_builder.py    - Briefing and summary builder
    autonomous_triggers.py - Self-acting trigger system (folder watch, email, etc.)
    agent_dispatcher.py   - Routes events to specialized agent prompts
    approval_system.py    - Human-in-the-loop approval gates
    unified_memory.py     - SQLite-backed memory for corrections and patterns
```

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure (optional)

Copy the example config and customize:

```bash
cp config.json.example config.json
```

Set environment variables for notifications:

```bash
# Telegram (optional - get these from @BotFather)
export TELEGRAM_BOT_TOKEN="your-bot-token"
export TELEGRAM_CHAT_ID="your-chat-id"

# System state file (optional - path to a JSON file with system info)
export AGENT_STATE_FILE="/path/to/live_state.json"

# Calendar command (optional - CLI tool to fetch calendar events)
export AGENT_CALENDAR_COMMAND="python3 /path/to/calendar_client.py"

# Briefing schedule (optional - 24-hour format)
export AGENT_BRIEFING_HOUR="7"   # Morning briefing at 7 AM
export AGENT_SUMMARY_HOUR="18"   # Evening summary at 6 PM
```

### 3. Run the agent

```bash
# Foreground (see logs in real-time)
python run_agent.py

# Background daemon
python run_agent.py --daemon

# Check status
python run_agent.py --status

# Stop
python run_agent.py --stop
```

### 4. Queue background tasks

```bash
# Add a task
python agent_control.py task "Research the latest Python 3.13 features and summarize"

# Add a high-priority task
python agent_control.py task "Fix the bug in main.py" -p 1

# List tasks
python agent_control.py tasks

# Check status
python agent_control.py status

# Pause/resume
python agent_control.py pause
python agent_control.py resume
```

## Core Components

### Task Queue

SQLite-backed queue that persists across restarts. Tasks have priorities (1 = highest, 10 = lowest) and are processed in order. The executor runs up to 3 tasks in parallel by default.

### Decision Engine

A rules-based system with configurable triggers. Each trigger has:
- A condition function (evaluates system state)
- An action function (produces a decision)
- A cooldown period (prevents spam)

Add custom triggers:

```python
from core.decision_engine import DecisionEngine, Trigger, Decision, ActionType, Priority

engine = DecisionEngine(config)
engine.add_trigger(Trigger(
    name="my_custom_trigger",
    condition=lambda state: state.get("some_value") > threshold,
    action=lambda state: Decision(
        action=ActionType.NOTIFY,
        priority=Priority.MEDIUM,
        title="Something happened",
        message="Details here"
    ),
    cooldown_minutes=30
))
```

### Notification System

Routes notifications through available channels:
1. **Telegram** (if configured via env vars)
2. **Console/log** (always available as fallback)

Respects quiet hours (10 PM - 7 AM by default) and minimum notification gaps.

### Autonomous Triggers

The self-acting trigger system watches for:
- **New files** in configured folders
- **Priority emails** from configured senders
- **Work session** detection (when dev tools open)
- **Learned patterns** from historical activity

Configure via `config.json`:

```json
{
    "watch_folders": [
        {
            "path": "/path/to/watch",
            "patterns": ["*.pdf", "*.xlsx"],
            "action": "notify_new_client_file"
        }
    ],
    "priority_senders": [
        {
            "email": "important@example.com",
            "name": "Important Person",
            "priority": "high"
        }
    ]
}
```

### Agent Dispatcher

Routes trigger events to specialized agent prompts. Define your agents in the `AGENT_REGISTRY`:

```python
AGENT_REGISTRY = {
    "my-agent": {
        "description": "Does something useful",
        "triggers": ["my_trigger"],
        "prompt_template": "Do this: {task_details}",
        "timeout": 300,
        "priority": "medium"
    }
}
```

### Approval System

Human-in-the-loop gates for sensitive actions:

```python
from core.approval_system import request_approval, check_approval, wait_for_approval

# Request approval
approval_id = request_approval(
    action="send_email",
    description="Reply to client about timeline",
    details="Draft email content here...",
    timeout_minutes=10,
    auto_approve=True  # Auto-proceed if no response
)

# Wait for response (blocking)
status = wait_for_approval(approval_id)

# Or poll
status = check_approval(approval_id)
```

### Unified Memory

SQLite-backed memory system for persistent context:

```python
from core.unified_memory import get_memory

memory = get_memory()

# Store memories
memory.store("Important project note", category="project", importance=8)

# Store corrections (self-improvement)
memory.store_correction(
    what_claude_said="Did X",
    what_was_wrong="Should have done Y",
    correct_approach="Always do Y first"
)

# Check before action
corrections = memory.check_before_action("planned action description")

# Get smart context
context = memory.get_smart_context(current_project="my-project")
```

## How It Works

1. **Watch Loop** - Reads system state every 30 seconds, detects changes
2. **Trigger Evaluation** - Checks all triggers against current state
3. **Decision Making** - Produces decisions with priorities
4. **Notification Filtering** - Respects quiet hours and notification gaps
5. **Task Execution** - Processes queued tasks via Claude Code CLI in parallel
6. **Pattern Learning** - Logs activity and detects recurring patterns
7. **Proactive Actions** - Morning briefings, evening summaries

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `TELEGRAM_BOT_TOKEN` | Telegram bot token | (none - console only) |
| `TELEGRAM_CHAT_ID` | Telegram chat ID | (none - console only) |
| `AGENT_STATE_FILE` | Path to system state JSON | (none) |
| `AGENT_CALENDAR_COMMAND` | Calendar CLI command | (none) |
| `AGENT_BRIEFING_HOUR` | Morning briefing hour (24h) | 7 |
| `AGENT_SUMMARY_HOUR` | Evening summary hour (24h) | 18 |

## Data Storage

All data is stored locally in the `autonomous-agent/` directory:

- `queues/tasks.db` - Task queue (SQLite)
- `memory/unified.db` - Memory system (SQLite)
- `data/pending_approvals.json` - Approval states
- `logs/agent.log` - Agent log
- `logs/executions.log` - Task execution log
- `results/` - Task execution results
