#!/usr/bin/env python3
"""
Decision Engine for Autonomous Agent
=====================================
Rules and triggers for when to take action.

Provides a framework for defining trigger rules that evaluate system state
and produce actionable decisions. Users can add custom triggers for their
own workflows.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime, timedelta
from enum import Enum
import re


class ActionType(Enum):
    NOTIFY = "notify"           # Send notification
    PREPARE = "prepare"         # Prepare context/briefing
    EXECUTE = "execute"         # Execute a command
    QUEUE = "queue"             # Queue for later
    LOG = "log"                 # Just log, no action


class Priority(Enum):
    CRITICAL = 1   # Immediate notification
    HIGH = 2       # Soon, bypass some filters
    MEDIUM = 3     # Normal
    LOW = 4        # Can wait, subject to quiet hours


@dataclass
class Decision:
    """A decision about what action to take."""
    action: ActionType
    priority: Priority
    title: str
    message: str
    data: Optional[Dict] = None


@dataclass
class Trigger:
    """A trigger rule that can fire decisions."""
    name: str
    condition: Callable[[Dict], bool]
    action: Callable[[Dict], Decision]
    cooldown_minutes: int = 30  # Don't fire again within this time
    last_fired: Optional[datetime] = None


class DecisionEngine:
    """
    Evaluates system state against rules and decides what actions to take.

    Add custom triggers for your own workflow needs:

        engine = DecisionEngine(config)
        engine.add_trigger(Trigger(
            name="my_trigger",
            condition=lambda state: state.get("some_value") > threshold,
            action=lambda state: Decision(
                action=ActionType.NOTIFY,
                priority=Priority.MEDIUM,
                title="Something happened",
                message="Details here"
            ),
            cooldown_minutes=30
        ))
    """

    def __init__(self, config: Dict):
        self.config = config
        self.triggers: List[Trigger] = []
        self._setup_default_triggers()

    def _setup_default_triggers(self):
        """Set up default trigger rules."""

        # High memory trigger
        self.triggers.append(Trigger(
            name="high_memory",
            condition=lambda s: s.get("system", {}).get("memory_percent", 0) > 85,
            action=lambda s: Decision(
                action=ActionType.NOTIFY,
                priority=Priority.MEDIUM,
                title="High Memory Usage",
                message=f"Memory at {s.get('system', {}).get('memory_percent', 0)}%. Consider closing unused apps.",
                data={"memory": s.get("system", {})}
            ),
            cooldown_minutes=60
        ))

        # Urgent email keywords
        self.triggers.append(Trigger(
            name="urgent_email",
            condition=self._has_urgent_email,
            action=self._make_urgent_email_decision,
            cooldown_minutes=15
        ))

    # ==========================================
    # CONDITION HELPERS
    # ==========================================

    def _has_urgent_email(self, state: Dict) -> bool:
        """Check for urgent emails."""
        email = state.get("email", {})
        alerts = email.get("alerts", [])
        urgent_keywords = self.config.get("urgent_email_keywords", [])

        for alert in alerts:
            subject = alert.get("subject", "").lower()
            if any(kw in subject for kw in urgent_keywords):
                return True
        return False

    def _make_urgent_email_decision(self, state: Dict) -> Decision:
        """Create decision for urgent email."""
        email = state.get("email", {})
        alerts = email.get("alerts", [])

        urgent_emails = []
        for alert in alerts:
            subject = alert.get("subject", "")
            if any(kw in subject.lower() for kw in self.config.get("urgent_email_keywords", [])):
                urgent_emails.append(f"  {alert.get('from', '?').split('<')[0]}: {subject[:50]}")

        return Decision(
            action=ActionType.NOTIFY,
            priority=Priority.HIGH,
            title="Urgent Email Detected",
            message="\n".join(urgent_emails),
            data={"emails": urgent_emails}
        )

    # ==========================================
    # EVALUATION
    # ==========================================

    def evaluate(self, state: Dict) -> List[Decision]:
        """
        Evaluate all triggers against current state.
        Returns list of decisions to act on.
        """
        decisions = []
        now = datetime.now()

        for trigger in self.triggers:
            # Check cooldown
            if trigger.last_fired:
                cooldown_delta = timedelta(minutes=trigger.cooldown_minutes)
                if now - trigger.last_fired < cooldown_delta:
                    continue

            # Check condition
            try:
                if trigger.condition(state):
                    decision = trigger.action(state)
                    decisions.append(decision)
                    trigger.last_fired = now
            except Exception as e:
                # Log but don't crash on trigger errors
                print(f"Trigger error ({trigger.name}): {e}")

        return decisions

    def add_trigger(self, trigger: Trigger):
        """Add a custom trigger."""
        self.triggers.append(trigger)

    def remove_trigger(self, name: str):
        """Remove a trigger by name."""
        self.triggers = [t for t in self.triggers if t.name != name]

    def list_triggers(self) -> List[str]:
        """List all trigger names."""
        return [t.name for t in self.triggers]

    # ==========================================
    # SMART DECISIONS
    # ==========================================

    def should_notify(self, priority: Priority, state: Dict) -> bool:
        """
        Decide if we should send a notification based on context.
        """
        hour = datetime.now().hour
        quiet_start = self.config.get("quiet_hours_start", 22)
        quiet_end = self.config.get("quiet_hours_end", 7)

        # Always notify for critical
        if priority == Priority.CRITICAL:
            return True

        # Check quiet hours
        in_quiet = False
        if quiet_start > quiet_end:
            in_quiet = hour >= quiet_start or hour < quiet_end
        else:
            in_quiet = quiet_start <= hour < quiet_end

        if in_quiet and priority.value > Priority.HIGH.value:
            return False

        return True

    def determine_channel(self, decision: Decision, state: Dict) -> str:
        """
        Determine which channel to use for notification.
        Override this to customize notification routing.
        """
        if decision.priority == Priority.CRITICAL:
            return "all"
        elif decision.priority == Priority.HIGH:
            return "primary"
        return "default"
