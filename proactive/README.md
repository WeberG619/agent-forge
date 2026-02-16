# Proactive Scheduler System

A modular daemon that orchestrates autonomous monitoring and notification tasks for Claude Code power users.

## Overview

The proactive system runs as a background daemon with multiple monitoring threads:

| Component | File | Purpose |
|-----------|------|---------|
| **Scheduler** | `scheduler.py` | Central orchestrator -- runs all monitors and timed routines |
| **Morning Briefing** | `morning_briefing.py` | Daily briefing with weather, calendar, email, system status |
| **Evening Summary** | `evening_summary.py` | End-of-day recap with calendar review and tomorrow preview |
| **Weekly Routines** | `weekly_routines.py` | Monday overview and Friday recap generators |
| **Calendar Monitor** | `calendar_monitor.py` | Meeting reminders N minutes before events |
| **Email Monitor** | `email_monitor.py` | Priority email alerts with tiered notification |
| **Smart Notify** | `smart_notify.py` | Rule-based system event notifications |
| **Notify Channels** | `notify_channels.py` | Multi-channel delivery (Telegram, voice, console) |
| **Tracker State** | `tracker_state.py` | Thread-safe persistent state (prevents duplicates/spam) |

## Quick Start

```bash
# Run the full daemon
python proactive/scheduler.py

# Test individual components
python proactive/scheduler.py --briefing-now
python proactive/scheduler.py --test-evening
python proactive/scheduler.py --test-calendar
python proactive/scheduler.py --test-email
python proactive/scheduler.py --test-weekly overview
python proactive/scheduler.py --test-weekly recap
python proactive/scheduler.py --test  # one smart-notify cycle
```

## Configuration

All configuration is via environment variables. No hardcoded paths or credentials.

### Notification Channels

```bash
# Telegram (required for push notifications)
export TELEGRAM_BOT_TOKEN="your-bot-token-here"
export TELEGRAM_CHAT_ID="your-chat-id-here"

# Voice TTS (optional)
export PROACTIVE_VOICE_COMMAND="python3 /path/to/your/speak.py"
```

### Schedule Times

```bash
export PROACTIVE_BRIEFING_TIME="07:00"     # Morning briefing (HH:MM)
export PROACTIVE_EVENING_TIME="18:00"      # Evening summary (HH:MM)
export PROACTIVE_WEEKLY_OVERVIEW="07:15"   # Monday overview (HH:MM)
export PROACTIVE_WEEKLY_RECAP="17:00"      # Friday recap (HH:MM)
```

### Data Sources

```bash
export PROACTIVE_STATE_FILE="/path/to/system_state.json"    # System state
export PROACTIVE_ALERTS_FILE="/path/to/email_alerts.json"   # Email alerts
export PROACTIVE_LOG_DIR="/path/to/logs"                    # Log directory
```

### Calendar & Location

```bash
export PROACTIVE_TIMEZONE="America/New_York"       # Your timezone
export PROACTIVE_REMINDER_MINUTES="15"             # Minutes before meeting to remind
export PROACTIVE_CACHE_REFRESH="10"                # Minutes between calendar refreshes
export PROACTIVE_WEATHER_LOCATION="New York"       # City for weather briefing
```

### Email Priority Contacts

```bash
# Comma-separated lists of priority domains and addresses
export PROACTIVE_PRIORITY_DOMAINS="important-client.com,partner-firm.com"
export PROACTIVE_PRIORITY_EMAILS="vip@example.com,boss@company.com"
```

## Architecture

```
scheduler.py (main daemon)
    |
    +-- _schedule_loop (30s tick)
    |       Morning briefing, evening summary, weekly routines
    |
    +-- _calendar_loop (60s) --> calendar_monitor.py
    +-- _email_loop (60s)    --> email_monitor.py
    +-- _smart_notify_loop (30s) --> smart_notify.py
    +-- _health_loop (300s)  --> PID-based service monitoring
    |
    +-- tracker_state.py (shared thread-safe state)
    +-- notify_channels.py (delivery layer)
```

### State Management

`TrackerState` provides thread-safe persistent state that prevents:
- Duplicate calendar reminders (tracks reminded event IDs)
- Duplicate email alerts (tracks notified email IDs)
- Notification spam (cooldown timers per rule)
- Double-runs on restart (date guards for daily/weekly routines)

State is saved atomically to `tracker_state.json` every 60 seconds.

### Notification Tiers

The email monitor uses three tiers:
1. **Priority contacts** (configured domains/addresses) -- all channels + voice
2. **Urgent emails** (`urgent_response` category) -- all channels + voice
3. **Needs response** (`needs_response` category) -- silent notification only

### Calendar Integration

The calendar monitor expects a `calendar_client` module with:
- `get_today_events()` -- returns a list of Google Calendar-style event dicts
- `format_event(event)` -- returns `{"start": str, "summary": str, "location": str}`
- `get_service()` -- returns a Google Calendar API service object

If no calendar client is available, calendar features degrade gracefully with log warnings.

## Extending

### Custom Notification Rules

```python
from proactive.smart_notify import SmartNotifier, NotificationRule

notifier = SmartNotifier()
notifier.add_rule(NotificationRule(
    name="disk_space_low",
    trigger="system_status",
    condition=lambda e: e.get('disk_percent', 0) > 90,
    action="notify_all",
    message_template="Disk usage at {disk_percent}%!",
    cooldown_minutes=60
))
```

### Custom Health Checks

```python
from proactive.scheduler import ProactiveScheduler

scheduler = ProactiveScheduler(health_services={
    "my-service": {"pidfile": "/var/run/my-service.pid"},
    "web-server": {"pidfile": "/tmp/web.pid"},
})
scheduler.start()
```

## Dependencies

- Python 3.9+ (uses `zoneinfo`)
- No pip packages required for core functionality
- Optional: `calendar_client` module for Google Calendar integration
- Optional: Telegram bot token for push notifications
- Optional: TTS command for voice notifications
