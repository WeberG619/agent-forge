#!/usr/bin/env python3
"""
Approval System for Autonomous Agent
======================================
Allows autonomous services to request user approval before taking
sensitive actions. Sends notifications with Approve/Edit/Cancel options.
Auto-proceeds or auto-cancels after configurable timeout.

Supports multiple notification backends:
- Telegram (if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID env vars are set)
- Console/log fallback

Usage from any service:
    from core.approval_system import request_approval, check_approval, ApprovalStatus

    # Request approval (sends notification immediately)
    approval_id = request_approval(
        action="send_email",
        description="Reply to client about the project timeline",
        details="Draft: Hi, the project should be ready by March 1...",
        timeout_minutes=10
    )

    # Check result (poll or wait)
    status = check_approval(approval_id)
    # Returns: ApprovalStatus.PENDING / APPROVED / CANCELLED / EDITED / TIMED_OUT
"""

import json
import os
import time
import uuid
import urllib.request
import urllib.parse
import logging
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path

logger = logging.getLogger("approval_system")

# Config from environment variables
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Approvals storage - relative to this file's parent (autonomous-agent/)
BASE_DIR = Path(__file__).parent.parent
APPROVALS_FILE = BASE_DIR / "data" / "pending_approvals.json"
APPROVALS_FILE.parent.mkdir(parents=True, exist_ok=True)


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    CANCELLED = "cancelled"
    EDITED = "edited"
    TIMED_OUT = "timed_out"


def _load_approvals() -> dict:
    """Load pending approvals from file."""
    if APPROVALS_FILE.exists():
        try:
            return json.loads(APPROVALS_FILE.read_text())
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def _save_approvals(approvals: dict):
    """Save approvals to file."""
    APPROVALS_FILE.write_text(json.dumps(approvals, indent=2, default=str))


def request_approval(
    action: str,
    description: str,
    details: str = "",
    timeout_minutes: int = 10,
    auto_approve: bool = True,
) -> str:
    """
    Request approval via notification. Returns an approval_id to check later.

    Args:
        action: Short action name (e.g., "send_email", "submit_proposal")
        description: What the system wants to do
        details: Full details (draft text, etc.)
        timeout_minutes: Minutes to wait before auto-proceeding
        auto_approve: If True, auto-approve on timeout. If False, auto-cancel.

    Returns:
        approval_id: Unique ID to check status with check_approval()
    """
    approval_id = str(uuid.uuid4())[:8]
    expires_at = datetime.now() + timedelta(minutes=timeout_minutes)

    # Store the approval request
    approvals = _load_approvals()
    approvals[approval_id] = {
        "action": action,
        "description": description,
        "details": details,
        "status": ApprovalStatus.PENDING,
        "created_at": datetime.now().isoformat(),
        "expires_at": expires_at.isoformat(),
        "timeout_minutes": timeout_minutes,
        "auto_approve": auto_approve,
        "edit_text": None,
        "responded_at": None,
    }
    _save_approvals(approvals)

    # Build notification message
    timeout_action = "proceed" if auto_approve else "cancel"
    msg = "*Approval Required*\n\n"
    msg += f"*Action:* {action}\n"
    msg += f"*What:* {description}\n"
    if details:
        # Truncate details (max ~3000 chars)
        detail_text = details[:2000]
        if len(details) > 2000:
            detail_text += "\n...(truncated)"
        msg += f"\n```\n{detail_text}\n```\n"
    msg += f"\nWill auto-{timeout_action} in {timeout_minutes} min if no response."

    # Send via available channel
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        # Send with inline keyboard buttons
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "Approve", "callback_data": f"approve:{approval_id}"},
                    {"text": "Edit", "callback_data": f"edit:{approval_id}"},
                    {"text": "Cancel", "callback_data": f"cancel:{approval_id}"},
                ]
            ]
        }
        _send_telegram_with_keyboard(msg, keyboard)
    else:
        # Console fallback
        logger.info(f"APPROVAL REQUIRED [{approval_id}]: {action} - {description}")
        logger.info(f"  Auto-{timeout_action} in {timeout_minutes} min")
        logger.info(f"  Use: handle_callback('{approval_id}', 'approve') to approve")

    logger.info(f"Approval requested: {approval_id} - {action}: {description}")
    return approval_id


def check_approval(approval_id: str) -> ApprovalStatus:
    """
    Check the status of an approval request.
    Also handles timeout logic.
    """
    approvals = _load_approvals()
    approval = approvals.get(approval_id)

    if not approval:
        return ApprovalStatus.CANCELLED  # Unknown = treat as cancelled

    # If already resolved, return status
    if approval["status"] != ApprovalStatus.PENDING:
        return ApprovalStatus(approval["status"])

    # Check timeout
    expires_at = datetime.fromisoformat(approval["expires_at"])
    if datetime.now() >= expires_at:
        if approval["auto_approve"]:
            approval["status"] = ApprovalStatus.TIMED_OUT
            approval["responded_at"] = datetime.now().isoformat()
            _save_approvals(approvals)

            # Notify that we're proceeding
            _send_notification(
                f"*Auto-approved* (no response in {approval['timeout_minutes']} min)\n"
                f"Action: {approval['action']}\n"
                f"Proceeding with: {approval['description']}"
            )
            logger.info(f"Approval {approval_id} auto-approved (timeout)")
            return ApprovalStatus.TIMED_OUT
        else:
            approval["status"] = ApprovalStatus.CANCELLED
            approval["responded_at"] = datetime.now().isoformat()
            _save_approvals(approvals)

            _send_notification(
                f"*Auto-cancelled* (no response in {approval['timeout_minutes']} min)\n"
                f"Action: {approval['action']}"
            )
            logger.info(f"Approval {approval_id} auto-cancelled (timeout)")
            return ApprovalStatus.CANCELLED

    return ApprovalStatus.PENDING


def wait_for_approval(approval_id: str, poll_interval: int = 5) -> ApprovalStatus:
    """
    Block until approval is resolved (approved, cancelled, edited, or timed out).

    Args:
        approval_id: The approval to wait for
        poll_interval: Seconds between checks

    Returns:
        Final ApprovalStatus
    """
    while True:
        status = check_approval(approval_id)
        if status != ApprovalStatus.PENDING:
            return status
        time.sleep(poll_interval)


def get_edit_text(approval_id: str) -> str | None:
    """Get the edited text if status is EDITED."""
    approvals = _load_approvals()
    approval = approvals.get(approval_id)
    if approval:
        return approval.get("edit_text")
    return None


def handle_callback(approval_id: str, action: str, edit_text: str = None):
    """
    Called when a user responds to an approval request.
    Updates the approval status.

    Args:
        approval_id: The approval to update
        action: "approve", "cancel", or "edit"
        edit_text: Modified text (only for "edit" action)
    """
    approvals = _load_approvals()
    approval = approvals.get(approval_id)

    if not approval:
        logger.warning(f"Unknown approval: {approval_id}")
        return

    if approval["status"] != ApprovalStatus.PENDING:
        logger.info(f"Approval {approval_id} already resolved: {approval['status']}")
        return

    approval["responded_at"] = datetime.now().isoformat()

    if action == "approve":
        approval["status"] = ApprovalStatus.APPROVED
        logger.info(f"Approval {approval_id} APPROVED by user")
    elif action == "cancel":
        approval["status"] = ApprovalStatus.CANCELLED
        logger.info(f"Approval {approval_id} CANCELLED by user")
    elif action == "edit":
        approval["status"] = ApprovalStatus.EDITED
        approval["edit_text"] = edit_text
        logger.info(f"Approval {approval_id} EDITED by user")

    _save_approvals(approvals)


def cleanup_old_approvals(max_age_hours: int = 24):
    """Remove approvals older than max_age_hours."""
    approvals = _load_approvals()
    cutoff = datetime.now() - timedelta(hours=max_age_hours)
    cleaned = {
        k: v for k, v in approvals.items() if datetime.fromisoformat(v["created_at"]) > cutoff
    }
    if len(cleaned) < len(approvals):
        logger.info(f"Cleaned {len(approvals) - len(cleaned)} old approvals")
        _save_approvals(cleaned)


# ============================================
# NOTIFICATION HELPERS
# ============================================


def _send_notification(message: str) -> bool:
    """Send a notification via the best available channel."""
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        return _send_telegram(message)
    else:
        logger.info(f"[NOTIFICATION] {message}")
        return True


def _send_telegram(message: str) -> bool:
    """Send a plain text message to Telegram."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    for parse_mode in ("Markdown", None):
        try:
            params = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
            if parse_mode:
                params["parse_mode"] = parse_mode
            data = urllib.parse.urlencode(params).encode()
            req = urllib.request.Request(url, data=data, method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read())
                if result.get("ok"):
                    return True
        except urllib.error.HTTPError as e:
            if e.code == 400 and parse_mode:
                continue
            logger.error(f"Telegram send failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return False
    return False


def _send_telegram_with_keyboard(message: str, keyboard: dict) -> bool:
    """Send a Telegram message with inline keyboard buttons."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    for parse_mode in ("Markdown", None):
        try:
            payload = {
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "reply_markup": json.dumps(keyboard),
            }
            if parse_mode:
                payload["parse_mode"] = parse_mode
            data = urllib.parse.urlencode(payload).encode()
            req = urllib.request.Request(url, data=data, method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read())
                if result.get("ok"):
                    return True
        except urllib.error.HTTPError as e:
            if e.code == 400 and parse_mode:
                continue
            logger.error(f"Telegram keyboard send failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Telegram keyboard send failed: {e}")
            return False
    return False


# ============================================
# CLI for testing
# ============================================

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) > 1 and sys.argv[1] == "test":
        print("Sending test approval request...")
        aid = request_approval(
            action="send_email",
            description="Reply to client about the project timeline",
            details="Hi,\n\nThe project should be ready by March 1. I'll send the updated documents by end of week.\n\nBest regards",
            timeout_minutes=2,
        )
        print(f"Approval ID: {aid}")
        print("Waiting for response...")
        status = wait_for_approval(aid)
        print(f"Result: {status}")
        if status == ApprovalStatus.EDITED:
            print(f"Edit text: {get_edit_text(aid)}")

    elif len(sys.argv) > 1 and sys.argv[1] == "check":
        aid = sys.argv[2] if len(sys.argv) > 2 else ""
        status = check_approval(aid)
        print(f"Status: {status}")

    elif len(sys.argv) > 1 and sys.argv[1] == "approve":
        aid = sys.argv[2] if len(sys.argv) > 2 else ""
        handle_callback(aid, "approve")
        print(f"Approved: {aid}")

    elif len(sys.argv) > 1 and sys.argv[1] == "cleanup":
        cleanup_old_approvals()
        print("Cleaned up old approvals")

    else:
        print("Usage:")
        print("  python approval_system.py test       - Send test approval")
        print("  python approval_system.py check ID   - Check approval status")
        print("  python approval_system.py approve ID - Approve manually")
        print("  python approval_system.py cleanup    - Remove old approvals")
