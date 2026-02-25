#!/usr/bin/env python3
"""
Morning Briefing Generator

Generates a daily briefing combining weather, calendar, email status,
and system state. Designed to run at a configurable time each morning.

Data sources are pluggable -- each getter function returns a string.
If a source is unavailable, it degrades gracefully with a fallback message.

Configuration:
    PROACTIVE_WEATHER_LOCATION  - City for weather (default: "New York")
    PROACTIVE_STATE_FILE        - Path to system state JSON (optional)
    PROACTIVE_ALERTS_FILE       - Path to email alerts JSON (optional)
"""

import json
import os
import logging
import urllib.request
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("morning_briefing")

# Configurable paths via environment variables
ALERTS_FILE = Path(
    os.getenv("PROACTIVE_ALERTS_FILE", str(Path(__file__).parent / "email_alerts.json"))
)
STATE_FILE = Path(
    os.getenv("PROACTIVE_STATE_FILE", str(Path(__file__).parent / "system_state.json"))
)
WEATHER_LOCATION = os.getenv("PROACTIVE_WEATHER_LOCATION", "New York")


def get_calendar_events() -> str:
    """Get today's calendar events.

    Attempts to import a calendar_client module. If unavailable,
    returns a placeholder message. To integrate your calendar,
    provide a module with get_today_events() and format_event() functions.
    """
    try:
        from calendar_client import get_today_events, format_event

        events = get_today_events()

        if not events:
            return "No calendar events today."

        lines = []
        for event in events:
            formatted = format_event(event)
            lines.append(f"  {formatted['start']} - {formatted['summary']}")
            if formatted.get("location"):
                lines.append(f"    Location: {formatted['location']}")

        return "\n".join(lines)
    except ImportError:
        return "Calendar integration not configured."
    except Exception as e:
        logger.error(f"Calendar fetch failed: {e}")
        return f"Could not fetch calendar: {e}"


def get_weather() -> str:
    """Get weather from wttr.in (free, no API key needed).

    Uses the PROACTIVE_WEATHER_LOCATION env var for location.
    Retries with fallback URL formats.
    """
    location = WEATHER_LOCATION.replace(" ", "+")
    urls = [
        f"https://wttr.in/{location}?format=3",
        f"https://wttr.in/{location}?format=%l:+%c+%t+%w",
        f"https://wttr.in/{location}?format=4",
    ]
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "curl/7.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                weather = resp.read().decode().strip()
                if weather and len(weather) > 3:
                    return weather
        except Exception as e:
            logger.debug(f"Weather fetch failed for {url}: {e}")
            continue
    return "Weather unavailable"


def get_email_summary() -> str:
    """Get email summary from a system state file.

    Reads from the state file specified by PROACTIVE_STATE_FILE.
    Expected JSON structure: {"email": {"unread_count": N, "urgent_count": N, ...}}
    """
    try:
        if STATE_FILE.exists():
            state = json.loads(STATE_FILE.read_text())
            email = state.get("email", {})
            unread = email.get("unread_count", 0)
            urgent = email.get("urgent_count", 0)
            needs_response = email.get("needs_response_count", 0)

            summary = []
            if unread > 0:
                summary.append(f"{unread} unread emails")
            if urgent > 0:
                summary.append(f"{urgent} urgent")
            if needs_response > 0:
                summary.append(f"{needs_response} need response")

            return ", ".join(summary) if summary else "Inbox clear"
        return "Email status unavailable"
    except Exception as e:
        return f"Could not fetch email status: {e}"


def get_email_priorities() -> str:
    """Get specific priority emails from an alerts file.

    Reads from the alerts file specified by PROACTIVE_ALERTS_FILE.
    Expected JSON structure: {"alerts": [{"category": ..., "from": ..., "subject": ...}, ...]}
    """
    try:
        if ALERTS_FILE.exists():
            with open(ALERTS_FILE, "r") as f:
                alerts = json.load(f)

            items = alerts.get("alerts", [])
            if not items:
                return None

            lines = []
            for alert in items[:5]:  # Top 5
                category = alert.get("category", "")
                sender = alert.get("from", "")
                subject = alert.get("subject", "")

                # Shorten sender
                if "<" in sender:
                    sender = sender.split("<")[0].strip().strip('"')

                tag = "URGENT" if category == "urgent_response" else "REPLY"
                lines.append(f"  [{tag}] {sender}: {subject[:50]}")

            return "\n".join(lines)
    except (json.JSONDecodeError, IOError):
        pass
    return None


def get_system_status() -> str:
    """Get system status from the state file.

    Reads application list from the state file. Override this
    function to customize which apps are reported.
    """
    try:
        if STATE_FILE.exists():
            state = json.loads(STATE_FILE.read_text())
            apps = state.get("applications", [])

            if not apps:
                return "No monitored applications running"

            app_names = []
            for app in apps[:5]:  # Show top 5
                name = app.get("name", app.get("ProcessName", ""))
                title = app.get("title", app.get("MainWindowTitle", ""))
                if name:
                    app_names.append(f"{name}" + (f": {title}" if title else ""))

            return ", ".join(app_names) if app_names else "No monitored apps running"
        return "System status unavailable"
    except Exception as e:
        return f"Could not fetch system status: {e}"


def generate_briefing(greeting: str = "Good morning") -> str:
    """Generate the full morning briefing.

    Args:
        greeting: The greeting prefix (e.g., "Good morning", "Hello").
    """
    now = datetime.now()
    day_name = now.strftime("%A, %B %d, %Y")

    calendar = get_calendar_events()
    weather = get_weather()
    email = get_email_summary()
    priorities = get_email_priorities()
    system = get_system_status()

    briefing = f"""{greeting}! Here's your briefing for {day_name}.

WEATHER:
  {weather}

CALENDAR:
{calendar}

EMAIL STATUS:
  {email}"""

    if priorities:
        briefing += f"""

PRIORITY EMAILS:
{priorities}"""

    briefing += f"""

SYSTEM STATUS:
  {system}

Have a productive day!"""

    return briefing


def main():
    """Run the morning briefing."""
    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("GENERATING MORNING BRIEFING")
    print("=" * 60)

    briefing = generate_briefing()
    print(briefing)

    # Send via notification channels
    try:
        from notify_channels import notify_all

        results = notify_all(briefing, voice=True)
        print(f"Notification results: {results}")
    except ImportError:
        print("(Notification channels not available, printed to console only)")

    return briefing


if __name__ == "__main__":
    main()
