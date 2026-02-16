#!/usr/bin/env python3
"""
Proactive Scheduler - Central orchestrator for all autonomous features.

Runs as a long-lived daemon that coordinates:
- Morning briefing (configurable time)
- Evening summary (configurable time)
- Weekly overview on Mondays
- Weekly recap on Fridays
- Calendar reminders (periodic)
- Email alert pushing (periodic)
- Smart notifications (periodic)
- Service health monitoring (periodic)
- Tracker state persistence (periodic)

Configuration (environment variables):
    PROACTIVE_BRIEFING_TIME     - Morning briefing time HH:MM (default: "07:00")
    PROACTIVE_EVENING_TIME      - Evening summary time HH:MM (default: "18:00")
    PROACTIVE_WEEKLY_OVERVIEW   - Weekly overview time HH:MM (default: "07:15")
    PROACTIVE_WEEKLY_RECAP      - Weekly recap time HH:MM (default: "17:00")
    PROACTIVE_LOG_DIR           - Directory for log files (default: ./logs)
    PROACTIVE_STATE_FILE        - System state JSON path (optional)
    PROACTIVE_ALERTS_FILE       - Email alerts JSON path (optional)
"""

import argparse
import logging
import os
import signal
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

# Ensure this package is importable
sys.path.insert(0, str(Path(__file__).parent))

from tracker_state import TrackerState
from calendar_monitor import CalendarMonitor
from email_monitor import EmailMonitor
from smart_notify import SmartNotifier
from morning_briefing import generate_briefing

# Setup logging
LOG_DIR = Path(os.getenv("PROACTIVE_LOG_DIR", str(Path(__file__).parent / "logs")))
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "proactive.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, mode="a"),
    ],
)
logger = logging.getLogger("scheduler")

# Schedule configuration (override via environment variables)
BRIEFING_TIME = os.getenv("PROACTIVE_BRIEFING_TIME", "07:00")
EVENING_TIME = os.getenv("PROACTIVE_EVENING_TIME", "18:00")
WEEKLY_OVERVIEW_TIME = os.getenv("PROACTIVE_WEEKLY_OVERVIEW", "07:15")  # Monday
WEEKLY_RECAP_TIME = os.getenv("PROACTIVE_WEEKLY_RECAP", "17:00")       # Friday

# Loop intervals (seconds)
SMART_NOTIFY_INTERVAL = 30
CALENDAR_INTERVAL = 60
EMAIL_INTERVAL = 60
HEALTH_INTERVAL = 300
STATE_SAVE_INTERVAL = 60

# Services to health-check (configure by adding entries here or via subclass)
# Each entry: {"pidfile": "/path/to/pidfile"}
HEALTH_CHECK_SERVICES = {}


class ProactiveScheduler:
    """Central orchestrator for all proactive features."""

    def __init__(self, health_services: dict = None):
        self.tracker = TrackerState()
        self.calendar_monitor = CalendarMonitor(self.tracker)
        self.email_monitor = EmailMonitor(self.tracker)
        self.notifier = SmartNotifier(self.tracker)
        self.health_services = health_services or HEALTH_CHECK_SERVICES
        self.running = True

    def stop(self):
        """Signal all threads to stop."""
        self.running = False

    # ---- Daily routines ----

    def run_morning_briefing(self):
        """Run the morning briefing."""
        if self.tracker.already_ran_today("last_briefing_date"):
            logger.info("Morning briefing already ran today, skipping")
            return

        logger.info("Running morning briefing...")
        try:
            briefing = generate_briefing()
            from notify_channels import notify_all
            notify_all(briefing, voice=True)
            self.tracker.set_last_date("last_briefing_date")
            logger.info("Morning briefing sent successfully")
        except Exception as e:
            logger.error(f"Morning briefing failed: {e}")

    def run_evening_summary(self):
        """Run the evening summary."""
        if self.tracker.already_ran_today("last_evening_date"):
            logger.info("Evening summary already ran today, skipping")
            return

        logger.info("Running evening summary...")
        try:
            from evening_summary import generate_evening_summary
            summary = generate_evening_summary()
            from notify_channels import notify_telegram_only
            notify_telegram_only(summary)
            self.tracker.set_last_date("last_evening_date")
            logger.info("Evening summary sent successfully")
        except Exception as e:
            logger.error(f"Evening summary failed: {e}")

    # ---- Weekly routines ----

    def run_weekly_overview(self):
        """Run Monday morning weekly overview."""
        if self.tracker.already_ran_today("last_weekly_overview_date"):
            logger.info("Weekly overview already ran today, skipping")
            return

        logger.info("Running weekly overview...")
        try:
            from weekly_routines import generate_weekly_overview
            overview = generate_weekly_overview()
            from notify_channels import notify_telegram_only
            notify_telegram_only(overview)
            self.tracker.set_last_date("last_weekly_overview_date")
            logger.info("Weekly overview sent successfully")
        except Exception as e:
            logger.error(f"Weekly overview failed: {e}")

    def run_weekly_recap(self):
        """Run Friday afternoon weekly recap."""
        if self.tracker.already_ran_today("last_weekly_recap_date"):
            logger.info("Weekly recap already ran today, skipping")
            return

        logger.info("Running weekly recap...")
        try:
            from weekly_routines import generate_weekly_recap
            recap = generate_weekly_recap()
            from notify_channels import notify_telegram_only
            notify_telegram_only(recap)
            self.tracker.set_last_date("last_weekly_recap_date")
            logger.info("Weekly recap sent successfully")
        except Exception as e:
            logger.error(f"Weekly recap failed: {e}")

    # ---- Health monitoring ----

    def check_service_health(self):
        """Check if monitored services are running via PID files."""
        for name, config in self.health_services.items():
            pidfile = Path(config["pidfile"])
            alive = False

            if pidfile.exists():
                try:
                    pid = int(pidfile.read_text().strip())
                    # Check if process is running
                    os.kill(pid, 0)
                    alive = True
                except (ValueError, ProcessLookupError, PermissionError):
                    alive = False

            if alive:
                self.tracker.reset_service_failures(name)
            else:
                self.tracker.record_service_failure(name)
                fail_count = self.tracker.get_service_failure_count(name)

                if fail_count == 2:
                    # Alert on 2nd consecutive failure (not first - might be restarting)
                    logger.warning(f"Service {name} appears down (failure #{fail_count})")
                    if self.tracker.check_cooldown(f"health_alert_{name}", 30):
                        try:
                            from notify_channels import notify_telegram_only
                            notify_telegram_only(f"Service alert: {name} appears down (checked {fail_count} times)")
                            self.tracker.record_cooldown(f"health_alert_{name}")
                        except Exception as e:
                            logger.error(f"Failed to send health alert: {e}")

    # ---- Thread loops ----

    def _smart_notify_loop(self):
        """Smart notification loop."""
        logger.info("Smart notify thread started")
        while self.running:
            try:
                self.notifier.run_once()
            except Exception as e:
                logger.error(f"Smart notify error: {e}")
            try:
                time.sleep(SMART_NOTIFY_INTERVAL)
            except InterruptedError:
                pass

    def _calendar_loop(self):
        """Calendar monitor loop."""
        logger.info("Calendar monitor thread started")
        while self.running:
            try:
                self.calendar_monitor.check()
            except Exception as e:
                logger.error(f"Calendar monitor error: {e}")
            try:
                time.sleep(CALENDAR_INTERVAL)
            except InterruptedError:
                pass

    def _email_loop(self):
        """Email monitor loop."""
        logger.info("Email monitor thread started")
        while self.running:
            try:
                self.email_monitor.check()
            except Exception as e:
                logger.error(f"Email monitor error: {e}")
            try:
                time.sleep(EMAIL_INTERVAL)
            except InterruptedError:
                pass

    def _health_loop(self):
        """Health check loop."""
        logger.info("Health monitor thread started")
        while self.running:
            try:
                self.check_service_health()
            except Exception as e:
                logger.error(f"Health check error: {e}")
            try:
                time.sleep(HEALTH_INTERVAL)
            except InterruptedError:
                pass

    def _schedule_loop(self):
        """Main schedule loop - handles daily/weekly timed events + state saving."""
        logger.info("Schedule loop started")
        last_save = time.time()

        while self.running:
            try:
                now = datetime.now()
                current_time = now.strftime("%H:%M")
                weekday = now.weekday()  # 0=Monday, 4=Friday

                # Daily: morning briefing
                if current_time == BRIEFING_TIME:
                    self.run_morning_briefing()

                # Daily: evening summary
                if current_time == EVENING_TIME:
                    self.run_evening_summary()

                # Monday: weekly overview
                if weekday == 0 and current_time == WEEKLY_OVERVIEW_TIME:
                    self.run_weekly_overview()

                # Friday: weekly recap
                if weekday == 4 and current_time == WEEKLY_RECAP_TIME:
                    self.run_weekly_recap()

                # Save tracker state periodically
                if time.time() - last_save >= STATE_SAVE_INTERVAL:
                    self.tracker.save()
                    last_save = time.time()

            except Exception as e:
                logger.error(f"Schedule loop error: {e}")

            # Sleep 30s to ensure we don't miss minute boundaries
            try:
                time.sleep(30)
            except InterruptedError:
                pass

    # ---- Start/Stop ----

    def start(self):
        """Start all monitor threads and the main schedule loop."""
        logger.info("=" * 60)
        logger.info("PROACTIVE SCHEDULER STARTING")
        logger.info("=" * 60)
        logger.info(f"Morning briefing: {BRIEFING_TIME}")
        logger.info(f"Evening summary: {EVENING_TIME}")
        logger.info(f"Calendar reminders: every {CALENDAR_INTERVAL}s")
        logger.info(f"Email alerts: every {EMAIL_INTERVAL}s")
        logger.info(f"Smart notifications: every {SMART_NOTIFY_INTERVAL}s")
        logger.info(f"Health checks: every {HEALTH_INTERVAL}s")
        logger.info(f"Log file: {LOG_FILE}")
        logger.info("=" * 60)

        # Start monitor threads (all daemon threads - die with main)
        threads = [
            threading.Thread(target=self._smart_notify_loop, name="smart-notify", daemon=True),
            threading.Thread(target=self._calendar_loop, name="calendar", daemon=True),
            threading.Thread(target=self._email_loop, name="email", daemon=True),
            threading.Thread(target=self._health_loop, name="health", daemon=True),
        ]

        for t in threads:
            t.start()
            logger.info(f"  Thread started: {t.name}")

        # Run the main schedule loop (blocking)
        try:
            self._schedule_loop()
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        except Exception as e:
            logger.error(f"Scheduler crashed with: {type(e).__name__}: {e}")
        finally:
            self.running = False
            self.tracker.save()
            logger.info("Scheduler stopped. State saved.")


def main():
    """Entry point with CLI flags."""
    parser = argparse.ArgumentParser(description="Proactive Scheduler - Central Orchestrator")
    parser.add_argument("--briefing-now", action="store_true", help="Run morning briefing now")
    parser.add_argument("--test-calendar", action="store_true", help="Run one calendar monitor cycle")
    parser.add_argument("--test-email", action="store_true", help="Run one email monitor cycle")
    parser.add_argument("--test-evening", action="store_true", help="Run evening summary now")
    parser.add_argument("--test-health", action="store_true", help="Run one health check cycle")
    parser.add_argument("--test-weekly", choices=["overview", "recap"], help="Run weekly routine")
    parser.add_argument("--test", action="store_true", help="Run one smart notify cycle")
    args = parser.parse_args()

    tracker = TrackerState()

    if args.briefing_now:
        briefing = generate_briefing()
        print(briefing)
        from notify_channels import notify_all
        notify_all(briefing, voice=True)
        tracker.set_last_date("last_briefing_date")
        tracker.save()
        return

    if args.test_calendar:
        monitor = CalendarMonitor(tracker)
        monitor.check()
        tracker.save()
        print("Calendar check complete.")
        return

    if args.test_email:
        monitor = EmailMonitor(tracker)
        monitor.check()
        tracker.save()
        print("Email check complete.")
        return

    if args.test_evening:
        from evening_summary import generate_evening_summary
        summary = generate_evening_summary()
        print(summary)
        from notify_channels import notify_telegram_only
        notify_telegram_only(summary)
        tracker.save()
        return

    if args.test_health:
        scheduler = ProactiveScheduler()
        scheduler.check_service_health()
        tracker.save()
        print("Health check complete.")
        return

    if args.test_weekly:
        if args.test_weekly == "overview":
            from weekly_routines import generate_weekly_overview
            result = generate_weekly_overview()
        else:
            from weekly_routines import generate_weekly_recap
            result = generate_weekly_recap()
        print(result)
        from notify_channels import notify_telegram_only
        notify_telegram_only(result)
        tracker.save()
        return

    if args.test:
        notifier = SmartNotifier(tracker)
        notifier.run_once()
        tracker.save()
        return

    # Normal operation - run as daemon
    scheduler = ProactiveScheduler()

    def handle_signal(signum, frame):
        logger.info(f"Received signal {signum}")
        scheduler.stop()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    scheduler.start()


if __name__ == "__main__":
    main()
