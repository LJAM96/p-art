"""Scheduler for automated P-Art runs."""

import logging
import threading
import time
from typing import Callable, Optional
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

log = logging.getLogger("p-art")


class ArtworkScheduler:
    """Schedule automated artwork updates."""

    def __init__(self, enabled: bool = False, cron_schedule: str = "0 2 * * *"):
        self.enabled = enabled
        self.cron_schedule = cron_schedule
        self.scheduler: Optional[BackgroundScheduler] = None
        self._job_id = "artwork_update"

    def start(self, callback: Callable):
        """Start the scheduler with the given callback."""
        if not self.enabled:
            log.info("Scheduler is disabled")
            return

        if self.scheduler and self.scheduler.running:
            log.warning("Scheduler is already running")
            return

        try:
            self.scheduler = BackgroundScheduler()

            # Parse cron schedule
            trigger = CronTrigger.from_crontab(self.cron_schedule)

            # Add job
            self.scheduler.add_job(
                callback,
                trigger=trigger,
                id=self._job_id,
                name="Artwork Update",
                replace_existing=True
            )

            self.scheduler.start()
            log.info(f"Scheduler started with schedule: {self.cron_schedule}")
            next_run = self.get_next_run_time()
            if next_run:
                log.info(f"Next run scheduled for: {next_run}")

        except Exception as e:
            log.error(f"Failed to start scheduler: {e}")
            self.scheduler = None

    def stop(self):
        """Stop the scheduler."""
        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown()
            log.info("Scheduler stopped")
        self.scheduler = None

    def get_next_run_time(self) -> Optional[str]:
        """Get the next scheduled run time."""
        if not self.scheduler or not self.scheduler.running:
            return None

        job = self.scheduler.get_job(self._job_id)
        if job and job.next_run_time:
            return job.next_run_time.strftime("%Y-%m-%d %H:%M:%S")
        return None

    def reschedule(self, new_cron_schedule: str):
        """Update the schedule."""
        self.cron_schedule = new_cron_schedule

        if self.scheduler and self.scheduler.running:
            try:
                trigger = CronTrigger.from_crontab(new_cron_schedule)
                self.scheduler.reschedule_job(
                    self._job_id,
                    trigger=trigger
                )
                log.info(f"Scheduler rescheduled to: {new_cron_schedule}")
                next_run = self.get_next_run_time()
                if next_run:
                    log.info(f"Next run scheduled for: {next_run}")
            except Exception as e:
                log.error(f"Failed to reschedule: {e}")

    def run_now(self, callback: Callable):
        """Run the job immediately (off-schedule)."""
        log.info("Running artwork update immediately (off-schedule)")
        thread = threading.Thread(target=callback, daemon=True)
        thread.start()
