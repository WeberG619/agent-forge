#!/usr/bin/env python3
"""
Tracker State - Thread-safe persistent state for proactive monitors.

Tracks:
- Reminded calendar event IDs (prevent duplicate reminders)
- Notified email IDs (prevent duplicate email alerts)
- Service failure counts (for health monitoring)
- Cooldowns (prevent notification spam)
- Last run dates (prevent double sends on restart)
"""

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


# Default state file location: alongside this module
STATE_FILE = Path(__file__).parent / "tracker_state.json"


class TrackerState:
    """Thread-safe persistent state manager."""

    def __init__(self, state_file: Optional[Path] = None):
        self._lock = threading.Lock()
        self._state_file = state_file or STATE_FILE
        self._state: Dict[str, Any] = {
            "reminded_events": {},      # event_id -> reminded_at ISO timestamp
            "notified_emails": {},      # email_id -> notified_at ISO timestamp
            "service_failures": {},     # service_name -> {"count": N, "last_failure": ISO}
            "cooldowns": {},            # key -> last_triggered ISO timestamp
            "last_briefing_date": None, # "YYYY-MM-DD"
            "last_evening_date": None,  # "YYYY-MM-DD"
            "last_weekly_overview_date": None,  # "YYYY-MM-DD"
            "last_weekly_recap_date": None,     # "YYYY-MM-DD"
        }
        self._load()

    def _load(self):
        """Load state from disk."""
        if self._state_file.exists():
            try:
                with open(self._state_file, "r") as f:
                    saved = json.load(f)
                # Merge with defaults (new keys get default values)
                for key, default in self._state.items():
                    if key not in saved:
                        saved[key] = default
                self._state = saved
            except (json.JSONDecodeError, IOError) as e:
                print(f"[TrackerState] Could not load state file, using defaults: {e}")

    def save(self):
        """Atomically save state to disk via temp file."""
        with self._lock:
            tmp_file = self._state_file.with_suffix(".tmp")
            try:
                with open(tmp_file, "w") as f:
                    json.dump(self._state, f, indent=2)
                # Atomic rename
                os.replace(str(tmp_file), str(self._state_file))
            except IOError as e:
                print(f"[TrackerState] Save failed: {e}")

    # --- Calendar reminder tracking ---

    def is_event_reminded(self, event_id: str) -> bool:
        """Check if we already sent a reminder for this event."""
        with self._lock:
            return event_id in self._state["reminded_events"]

    def mark_event_reminded(self, event_id: str):
        """Mark an event as reminded."""
        with self._lock:
            self._state["reminded_events"][event_id] = datetime.now().isoformat()

    def clean_old_events(self, max_age_hours: float = 1.0):
        """Remove reminded event IDs older than max_age_hours."""
        with self._lock:
            cutoff = datetime.now().timestamp() - (max_age_hours * 3600)
            to_remove = []
            for eid, ts in self._state["reminded_events"].items():
                try:
                    event_ts = datetime.fromisoformat(ts).timestamp()
                    if event_ts < cutoff:
                        to_remove.append(eid)
                except (ValueError, TypeError):
                    to_remove.append(eid)
            for eid in to_remove:
                del self._state["reminded_events"][eid]

    # --- Email notification tracking ---

    def is_email_notified(self, email_id: str) -> bool:
        """Check if we already sent a notification for this email."""
        with self._lock:
            return email_id in self._state["notified_emails"]

    def mark_email_notified(self, email_id: str):
        """Mark an email as notified."""
        with self._lock:
            self._state["notified_emails"][email_id] = datetime.now().isoformat()

    def clean_old_emails(self, max_age_hours: float = 48.0):
        """Remove notified email IDs older than max_age_hours."""
        with self._lock:
            cutoff = datetime.now().timestamp() - (max_age_hours * 3600)
            to_remove = []
            for eid, ts in self._state["notified_emails"].items():
                try:
                    event_ts = datetime.fromisoformat(ts).timestamp()
                    if event_ts < cutoff:
                        to_remove.append(eid)
                except (ValueError, TypeError):
                    to_remove.append(eid)
            for eid in to_remove:
                del self._state["notified_emails"][eid]

    # --- Service health tracking ---

    def record_service_failure(self, service_name: str):
        """Record a service failure."""
        with self._lock:
            if service_name not in self._state["service_failures"]:
                self._state["service_failures"][service_name] = {"count": 0, "last_failure": None}
            entry = self._state["service_failures"][service_name]
            entry["count"] = entry.get("count", 0) + 1
            entry["last_failure"] = datetime.now().isoformat()

    def get_service_failure_count(self, service_name: str) -> int:
        """Get failure count for a service."""
        with self._lock:
            return self._state["service_failures"].get(service_name, {}).get("count", 0)

    def reset_service_failures(self, service_name: str):
        """Reset failure count for a service (after successful check)."""
        with self._lock:
            if service_name in self._state["service_failures"]:
                self._state["service_failures"][service_name]["count"] = 0

    # --- Cooldown management ---

    def check_cooldown(self, key: str, minutes: float) -> bool:
        """Check if cooldown has expired. Returns True if action is allowed."""
        with self._lock:
            last = self._state["cooldowns"].get(key)
            if not last:
                return True
            try:
                elapsed = (datetime.now() - datetime.fromisoformat(last)).total_seconds() / 60
                return elapsed >= minutes
            except (ValueError, TypeError):
                return True

    def record_cooldown(self, key: str):
        """Record that an action was taken (start cooldown)."""
        with self._lock:
            self._state["cooldowns"][key] = datetime.now().isoformat()

    # --- Date guards for daily/weekly routines ---

    def get_last_date(self, key: str) -> Optional[str]:
        """Get last run date for a routine (e.g., 'last_briefing_date')."""
        with self._lock:
            return self._state.get(key)

    def set_last_date(self, key: str, date_str: Optional[str] = None):
        """Set last run date. Defaults to today."""
        with self._lock:
            self._state[key] = date_str or datetime.now().strftime("%Y-%m-%d")

    def already_ran_today(self, key: str) -> bool:
        """Check if a routine already ran today."""
        with self._lock:
            last = self._state.get(key)
            if not last:
                return False
            return last == datetime.now().strftime("%Y-%m-%d")


if __name__ == "__main__":
    # Quick test
    state = TrackerState()
    print(f"State file: {state._state_file}")
    print(f"Current state: {json.dumps(state._state, indent=2)}")

    # Test cooldown
    print(f"\nCooldown test (should be True): {state.check_cooldown('test', 5)}")
    state.record_cooldown("test")
    print(f"Cooldown test (should be False): {state.check_cooldown('test', 5)}")
    print(f"Cooldown test 0 min (should be True): {state.check_cooldown('test', 0)}")

    # Test event tracking
    state.mark_event_reminded("event123")
    print(f"\nEvent reminded (should be True): {state.is_event_reminded('event123')}")
    print(f"Event reminded (should be False): {state.is_event_reminded('event456')}")

    state.save()
    print(f"\nState saved to {state._state_file}")
