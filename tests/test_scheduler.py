from unittest.mock import MagicMock, patch

from src.reports import scheduler


@patch("src.reports.scheduler.scheduler.add_job")
def test_schedule_session_email(add_job):
    scheduler.schedule_session_email(
        to="teacher@example.com",
        session_id=1,
        delay_minutes=5,
    )

    add_job.assert_called_once()

    _, kwargs = add_job.call_args

    assert kwargs["args"] == ["teacher@example.com", 1]
    assert kwargs["replace_existing"] is True
    assert kwargs["id"] == "session-1-teacher@example.com"


@patch("src.reports.scheduler.scheduler.add_job")
def test_schedule_weekly_email(add_job):
    scheduler.schedule_weekly_email(
        to="teacher@example.com",
        course_id=5,
        week="2026-W31",
    )

    add_job.assert_called_once()

    _, kwargs = add_job.call_args

    assert kwargs["args"] == [
        "teacher@example.com",
        5,
        "2026-W31",
    ]
    assert kwargs["replace_existing"] is True
    assert kwargs["id"] == "weekly-5-teacher@example.com"


@patch("src.reports.scheduler.EmailSender")
def test_send_session_email(mock_sender):
    instance = MagicMock()
    mock_sender.return_value = instance

    scheduler.send_session_email(
        "teacher@example.com",
        1,
    )

    instance.session_email.assert_called_once_with(
        to="teacher@example.com",
        session_id=1,
    )

    instance.close.assert_called_once()


@patch("src.reports.scheduler.EmailSender")
def test_send_weekly_email(mock_sender):
    instance = MagicMock()
    mock_sender.return_value = instance

    scheduler.send_weekly_email(
        "teacher@example.com",
        5,
        "2026-W31",
    )

    instance.weekly_email.assert_called_once_with(
        to="teacher@example.com",
        course_id=5,
        week="2026-W31",
    )

    instance.close.assert_called_once()
