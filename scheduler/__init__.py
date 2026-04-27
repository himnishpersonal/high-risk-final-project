"""
APScheduler initialization and configuration.
"""

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from scheduler.jobs import (
    phase_flip_job,
    daily_checkin_job,
    close_monitoring_windows_job
)

logger = structlog.get_logger()

scheduler: AsyncIOScheduler = None


def start_scheduler():
    global scheduler
    
    if scheduler is not None:
        logger.warning("scheduler_already_running")
        return
    
    scheduler = AsyncIOScheduler()
    
    scheduler.add_job(
        phase_flip_job,
        trigger=CronTrigger(hour=0, minute=5),
        id="phase_flip",
        name="Phase Flip (pre_op → post_op)",
        replace_existing=True
    )
    logger.info("scheduled_job_added", job="phase_flip", schedule="00:05")
    
    scheduler.add_job(
        daily_checkin_job,
        trigger=CronTrigger(hour=8, minute=0),
        id="daily_checkin",
        name="Daily Check-ins",
        replace_existing=True
    )
    logger.info("scheduled_job_added", job="daily_checkin", schedule="08:00")
    
    scheduler.add_job(
        close_monitoring_windows_job,
        trigger=CronTrigger(hour=0, minute=10),
        id="close_monitoring",
        name="Close Monitoring Windows",
        replace_existing=True
    )
    logger.info("scheduled_job_added", job="close_monitoring", schedule="00:10")
    
    scheduler.start()
    logger.info("scheduler_started", jobs_count=len(scheduler.get_jobs()))


def stop_scheduler():
    global scheduler
    
    if scheduler is None:
        logger.warning("scheduler_not_running")
        return
    
    scheduler.shutdown(wait=False)
    logger.info("scheduler_stopped")
    scheduler = None


def get_scheduler() -> AsyncIOScheduler:
    return scheduler
