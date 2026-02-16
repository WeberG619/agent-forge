#!/usr/bin/env python3
"""
Weekly Routines - Weekly overview and recap generators.

Monday morning: Week ahead overview (calendar events by day + pending emails)
Friday afternoon: Weekly recap (event count, next week preview, open items)

Both are designed for silent delivery (e.g., Telegram only, no voice).

Configuration:
    PROACTIVE_ALERTS_FILE  - Path to email alerts JSON (optional)
"""

import json
import os
import sys
import logging
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger("weekly_routines")

ALERTS_FILE = Path(os.getenv(
    "PROACTIVE_ALERTS_FILE",
    str(Path(__file__).parent / "email_alerts.json")
))

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _get_events_for_range(start_dt, end_dt):
    """Get calendar events for a date range.

    Requires a calendar_client module with get_service().
    """
    try:
        from calendar_client import get_service
        service = get_service()

        events_result = service.events().list(
            calendarId="primary",
            timeMin=start_dt.isoformat() + "Z",
            timeMax=end_dt.isoformat() + "Z",
            singleEvents=True,
            orderBy="startTime",
        ).execute()

        return events_result.get("items", [])
    except ImportError:
        logger.warning("calendar_client module not available")
        return []
    except Exception as e:
        logger.error(f"Failed to fetch events: {e}")
        return []


def _get_pending_email_count():
    """Get count of pending email responses."""
    try:
        if ALERTS_FILE.exists():
            with open(ALERTS_FILE, "r") as f:
                alerts = json.load(f)
            urgent = alerts.get("urgent_count", 0)
            needs_response = alerts.get("needs_response_count", 0)
            return urgent, needs_response
    except (json.JSONDecodeError, IOError):
        pass
    return 0, 0


def _format_event_brief(event):
    """Format an event for weekly display."""
    start = event.get("start", {}).get("dateTime", event.get("start", {}).get("date", ""))
    summary = event.get("summary", "(No title)")

    if "T" in start:
        dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        time_str = dt.strftime("%I:%M %p")
        return f"  {time_str} - {summary}"
    else:
        return f"  All day - {summary}"


def generate_weekly_overview() -> str:
    """Generate a weekly overview (intended for Monday mornings)."""
    now = datetime.utcnow()

    # This week: Monday through Sunday
    days_since_monday = now.weekday()
    start_of_week = now - timedelta(days=days_since_monday)
    start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_week = start_of_week + timedelta(days=7)

    events = _get_events_for_range(start_of_week, end_of_week)

    # Group events by day
    days = {}
    for event in events:
        start = event.get("start", {}).get("dateTime", event.get("start", {}).get("date", ""))
        if "T" in start:
            dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        else:
            dt = datetime.fromisoformat(start)
        day_key = dt.strftime("%Y-%m-%d")
        day_name = DAY_NAMES[dt.weekday()]

        if day_key not in days:
            days[day_key] = {"name": day_name, "events": []}
        days[day_key]["events"].append(event)

    # Build the overview
    date_str = datetime.now().strftime("%B %d")
    lines = [f"Week Ahead - Starting {date_str}", ""]

    if not events:
        lines.append("No events scheduled this week.")
    else:
        # Walk through each day of the week
        for i in range(7):
            day_dt = start_of_week + timedelta(days=i)
            day_key = day_dt.strftime("%Y-%m-%d")
            day_name = DAY_NAMES[day_dt.weekday()]

            if day_key in days:
                day_events = days[day_key]["events"]
                lines.append(f"{day_name} ({len(day_events)} events):")
                for event in day_events:
                    lines.append(_format_event_brief(event))
            else:
                lines.append(f"{day_name}: clear")

        lines.append(f"\nTotal: {len(events)} events this week")

    # Add pending emails
    urgent, needs_response = _get_pending_email_count()
    if urgent + needs_response > 0:
        lines.append(f"\nPending emails: {urgent} urgent, {needs_response} need response")

    return "\n".join(lines)


def generate_weekly_recap() -> str:
    """Generate a weekly recap (intended for Friday afternoons)."""
    now = datetime.utcnow()

    # This week (Mon-Fri done)
    days_since_monday = now.weekday()
    start_of_week = now - timedelta(days=days_since_monday)
    start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_today = now.replace(hour=23, minute=59, second=59)

    this_week_events = _get_events_for_range(start_of_week, end_of_today)

    # Next week preview
    next_monday = start_of_week + timedelta(days=7)
    next_friday = next_monday + timedelta(days=5)
    next_week_events = _get_events_for_range(next_monday, next_friday)

    # Build recap
    date_str = datetime.now().strftime("%B %d")
    lines = [f"Weekly Recap - {date_str}", ""]

    # This week summary
    lines.append(f"This week: {len(this_week_events)} events completed")

    # Count meetings by type (simple heuristic)
    meeting_count = sum(1 for e in this_week_events if e.get("start", {}).get("dateTime"))
    allday_count = len(this_week_events) - meeting_count
    if meeting_count > 0:
        lines.append(f"  {meeting_count} timed meetings")
    if allday_count > 0:
        lines.append(f"  {allday_count} all-day events")

    # Next week preview
    lines.append(f"\nNext week: {len(next_week_events)} events scheduled")
    if next_week_events:
        # Group by day for next week
        days = {}
        for event in next_week_events:
            start = event.get("start", {}).get("dateTime", event.get("start", {}).get("date", ""))
            if "T" in start:
                dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
            else:
                dt = datetime.fromisoformat(start)
            day_name = DAY_NAMES[dt.weekday()]
            if day_name not in days:
                days[day_name] = 0
            days[day_name] += 1

        for day, count in days.items():
            lines.append(f"  {day}: {count} event{'s' if count > 1 else ''}")

    # Pending items
    urgent, needs_response = _get_pending_email_count()
    if urgent + needs_response > 0:
        lines.append(f"\nOpen items: {urgent} urgent emails, {needs_response} need response")
    else:
        lines.append("\nAll emails caught up!")

    lines.append("\nHave a great weekend!")

    return "\n".join(lines)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        if command == "overview":
            print(generate_weekly_overview())
        elif command == "recap":
            print(generate_weekly_recap())
        else:
            print(f"Usage: {sys.argv[0]} [overview|recap]")
    else:
        print("=== WEEKLY OVERVIEW ===")
        print(generate_weekly_overview())
        print("\n\n=== WEEKLY RECAP ===")
        print(generate_weekly_recap())
