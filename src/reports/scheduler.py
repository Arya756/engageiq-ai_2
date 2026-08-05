"""Background scheduler for automated report emails."""

from __future__ import annotations

from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from src.reports.email_sender import EmailSender

scheduler = BackgroundScheduler()


def start_scheduler() -> None:
    """Start the scheduler."""
    if not scheduler.running:
        scheduler.start()


def shutdown_scheduler() -> None:
    """Stop the scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)


def send_session_email(
    to: str,
    session_id: int,
) -> None:
    """Background task for session report."""

    sender = EmailSender()

    try:
        sender.session_email(
            to=to,
            session_id=session_id,
        )
    finally:
        sender.close()


def send_weekly_email(
    to: str,
    course_id: int,
    week: str,
) -> None:
    """Background task for weekly report."""

    sender = EmailSender()

    try:
        sender.weekly_email(
            to=to,
            course_id=course_id,
            week=week,
        )
    finally:
        sender.close()


def schedule_session_email(
    to: str,
    session_id: int,
    delay_minutes: int = 5,
) -> None:
    """Schedule a session report email."""

    scheduler.add_job(
        send_session_email,
        trigger=DateTrigger(
            run_date=datetime.now() + timedelta(minutes=delay_minutes),
        ),
        args=[to, session_id],
        id=f"session-{session_id}-{to}",
        replace_existing=True,
    )


def schedule_weekly_email(
    to: str,
    course_id: int,
    week: str,
) -> None:
    """Schedule weekly report emails."""

    scheduler.add_job(
        send_weekly_email,
        trigger=CronTrigger(
            day_of_week="mon",
            hour=8,
            minute=0,
        ),
        args=[to, course_id, week],
        id=f"weekly-{course_id}-{to}",
        replace_existing=True,
    )
