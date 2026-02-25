#!/usr/bin/env python3
"""
Calendar Monitor - Sends meeting reminders before events.

Called periodically by the scheduler. Caches today's events and refreshes
from the calendar API at a configurable interval.

Configuration:
    PROACTIVE_TIMEZONE         - Local timezone (default: "UTC")
    PROACTIVE_REMINDER_MINUTES - Minutes before event to remind (default: 15)
    PROACTIVE_CACHE_REFRESH    - Minutes between cache refreshes (default: 10)

Requires a calendar_client module with:
    - get_today_events() -> list of event dicts
    - Each event dict must have: id, summary, start.dateTime, location (optional)
"""

import os
import logging
from datetime import datetime
from typing import List, Dict, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger("calendar_monitor")

# Configuration via environment
LOCAL_TZ = ZoneInfo(os.getenv("PROACTIVE_TIMEZONE", "UTC"))
REMINDER_MINUTES = int(os.getenv("PROACTIVE_REMINDER_MINUTES", "15"))
CACHE_REFRESH_MINUTES = int(os.getenv("PROACTIVE_CACHE_REFRESH", "10"))


class CalendarMonitor:
    """Monitors calendar and sends reminders before meetings."""

    def __init__(self, tracker_state):
        self.tracker = tracker_state
        self._cached_events: List[Dict] = []
        self._last_cache_refresh: Optional[datetime] = None

    def _refresh_cache(self):
        """Refresh today's events from the calendar API."""
        try:
            from calendar_client import get_today_events

            raw_events = get_today_events()

            self._cached_events = []
            for event in raw_events:
                start_raw = event.get("start", {}).get("dateTime")
                if not start_raw:
                    # All-day event - skip for reminders
                    continue

                # Parse the event start time
                start_dt = datetime.fromisoformat(start_raw)
                # Ensure timezone-aware in local TZ
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=LOCAL_TZ)
                else:
                    start_dt = start_dt.astimezone(LOCAL_TZ)

                self._cached_events.append(
                    {
                        "id": event.get("id", ""),
                        "summary": event.get("summary", "(No title)"),
                        "start_dt": start_dt,
                        "location": event.get("location", ""),
                        "start_raw": start_raw,
                    }
                )

            self._last_cache_refresh = datetime.now(LOCAL_TZ)
            logger.info(f"Calendar cache refreshed: {len(self._cached_events)} timed events today")

        except ImportError:
            logger.warning("calendar_client module not available - calendar monitoring disabled")
        except Exception as e:
            logger.error(f"Failed to refresh calendar cache: {e}")

    def _needs_refresh(self) -> bool:
        """Check if cache needs refreshing."""
        if not self._last_cache_refresh:
            return True
        elapsed = (datetime.now(LOCAL_TZ) - self._last_cache_refresh).total_seconds() / 60
        return elapsed >= CACHE_REFRESH_MINUTES

    def check(self):
        """Main check method - called periodically by the scheduler."""
        # Refresh cache if needed
        if self._needs_refresh():
            self._refresh_cache()

        now = datetime.now(LOCAL_TZ)

        # Clean old reminded events
        self.tracker.clean_old_events(max_age_hours=1.0)

        for event in self._cached_events:
            event_id = event["id"]
            start_dt = event["start_dt"]

            # How many minutes until this event?
            delta = (start_dt - now).total_seconds() / 60

            # Send reminder if event is 0-N minutes away and not yet reminded
            if 0 <= delta <= REMINDER_MINUTES and not self.tracker.is_event_reminded(event_id):
                minutes_left = int(delta)
                self._send_reminder(event, minutes_left)
                self.tracker.mark_event_reminded(event_id)

    def _send_reminder(self, event: Dict, minutes_left: int):
        """Send a meeting reminder via configured notification channels."""
        summary = event["summary"]
        start_dt = event["start_dt"]
        location = event.get("location", "")

        time_str = start_dt.strftime("%I:%M %p")

        if minutes_left <= 1:
            urgency = "NOW"
        elif minutes_left <= 5:
            urgency = f"in {minutes_left} minutes"
        else:
            urgency = f"in {minutes_left} minutes"

        message = f"Meeting {urgency}: {summary} at {time_str}"
        if location:
            message += f"\nLocation: {location}"

        logger.info(f"Sending calendar reminder: {message}")

        try:
            from notify_channels import notify_all

            notify_all(message, voice=True)
        except ImportError:
            print(f"REMINDER: {message}")
        except Exception as e:
            logger.error(f"Failed to send calendar reminder: {e}")


if __name__ == "__main__":
    # Manual test
    from tracker_state import TrackerState

    logging.basicConfig(level=logging.INFO)

    state = TrackerState()
    monitor = CalendarMonitor(state)
    print("Running calendar monitor check...")
    monitor.check()
    print(f"Cached events: {len(monitor._cached_events)}")
    for ev in monitor._cached_events:
        now = datetime.now(LOCAL_TZ)
        delta = (ev["start_dt"] - now).total_seconds() / 60
        print(f"  {ev['summary']} at {ev['start_dt'].strftime('%I:%M %p')} ({int(delta)} min away)")
    state.save()
    print("Done.")
