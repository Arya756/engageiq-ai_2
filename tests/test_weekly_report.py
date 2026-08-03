import subprocess
import sys
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, create_autospec

import pytest
from sqlalchemy.orm import Session as DBSession

from src.models.course import Course
from src.models.engagement_log import EngagementLog
from src.models.report import Report
from src.models.session import Session as SessionModel
from src.reports.weekly_report import (
    AtRiskSummary,
    WeekComparison,
    WeeklyReportData,
    WeeklyReportGenerator,
    WeekSummary,
)


# -------------------------------------------------------------------
# Database Mocking Helper
# -------------------------------------------------------------------
def setup_db_mock(mock_db, course, sessions_curr, sessions_prev, logs_curr, logs_prev):
    """
    Helper to cleanly mock SQLAlchemy's fluent query API.
    Maintains mock state so side_effect iterators aren't reset on subsequent queries,
    ensuring current week and previous week queries return distinct data.
    """
    mock_db.get.return_value = course

    # Create distinct mocks for Session and EngagementLog queries
    session_query_mock = MagicMock()
    session_query_mock.filter.return_value.order_by.return_value.all.side_effect = [
        sessions_curr,
        sessions_prev,
    ]

    log_query_mock = MagicMock()
    log_query_mock.filter.return_value.order_by.return_value.all.side_effect = [
        logs_curr,
        logs_prev,
    ]

    enrollment_query_mock = MagicMock()
    enrollment_query_mock.filter.return_value.count.return_value = 0

    def db_query_side_effect(model_class):
        if model_class == SessionModel:
            return session_query_mock
        elif model_class == EngagementLog:
            return log_query_mock
        elif model_class.__name__ == "CourseEnrollment":
            return enrollment_query_mock
        return MagicMock()

    mock_db.query.side_effect = db_query_side_effect


# -------------------------------------------------------------------
# Validation Tests (Routed through public API)
# -------------------------------------------------------------------
def test_generate_invalid_iso_week():
    mock_db = create_autospec(DBSession, instance=True)
    gen = WeeklyReportGenerator(mock_db)

    # Invalid ISO Weeks should raise ValueError during generation
    for bad_week in ["2026-24", "W24", "abc"]:
        with pytest.raises(ValueError, match="Invalid ISO week"):
            gen.generate(1, bad_week)


def test_generate_invalid_course():
    mock_db = create_autospec(DBSession, instance=True)
    mock_db.get.return_value = None
    gen = WeeklyReportGenerator(mock_db)

    with pytest.raises(ValueError, match="Course 1 not found"):
        gen.generate(1, "2026-W24")


# -------------------------------------------------------------------
# End-to-End Generate Tests
# -------------------------------------------------------------------
def test_generate_end_to_end():
    mock_db = create_autospec(DBSession, instance=True)
    mock_course = Course(id=1, name="Test Course", code="TEST101")

    session_curr = SessionModel(id=1, title="L1", start_time=datetime(2026, 6, 8, 9))
    session_prev = SessionModel(id=2, title="L0", start_time=datetime(2026, 6, 1, 9))

    log_curr = EngagementLog(
        session_id=1,
        user_id=1,
        engagement_score=0.8,
        timestamp=datetime(2026, 6, 8, 9, 10),
    )
    log_prev = EngagementLog(
        session_id=2,
        user_id=1,
        engagement_score=0.9,
        timestamp=datetime(2026, 6, 1, 9, 10),
    )

    setup_db_mock(
        mock_db, mock_course, [session_curr], [session_prev], [log_curr], [log_prev]
    )

    gen = WeeklyReportGenerator(mock_db)
    report = gen.generate(1, "2026-W24")

    # Verify Report Metadata
    assert report.course_id == 1
    assert report.course_name == "Test Course"

    # Verify natural calculation populated the dataclasses
    assert report.week_summary.average_engagement > 0.0
    assert len(report.lecture_curves) == 1

    # Verify Temporal Patterns
    mon_pattern = next(d for d in report.day_pattern if d.day_name == "Monday")
    assert mon_pattern.average > 0.0

    morning_pattern = next(t for t in report.time_pattern if t.period == "Morning")
    assert morning_pattern.average > 0.0

    # Week-over-week logic shouldn't be strictly coupled to hardcoded mock numbers
    assert report.week_comparison.trend == "down"


def test_generate_empty_week():
    mock_db = create_autospec(DBSession, instance=True)
    mock_course = Course(id=1, name="Empty Course", code="EMP101")

    # No sessions, no logs
    setup_db_mock(mock_db, mock_course, [], [], [], [])

    gen = WeeklyReportGenerator(mock_db)
    report = gen.generate(1, "2026-W24")

    assert report.has_data is False
    assert report.week_summary.lecture_count == 0
    assert report.week_summary.student_count == 0
    assert not report.lecture_curves
    assert report.week_comparison.trend == "no_data"
    assert report.difficult_segments == []
    assert report.at_risk.count == 0


def test_timezone_mismatch_regression():
    """Ensure naive and aware datetimes can safely be subtracted in timelines."""
    mock_db = create_autospec(DBSession, instance=True)
    mock_course = Course(id=1, name="Timezone Course", code="TZ101")

    # Mix naive session with an aware log
    session_naive = SessionModel(id=1, title="L1", start_time=datetime(2026, 6, 8, 9))
    log_aware = EngagementLog(
        session_id=1,
        user_id=1,
        engagement_score=0.8,
        timestamp=datetime(2026, 6, 8, 9, 10, tzinfo=timezone.utc),
    )

    setup_db_mock(mock_db, mock_course, [session_naive], [], [log_aware], [])

    gen = WeeklyReportGenerator(mock_db)

    # Should not raise TypeError during generation
    report = gen.generate(1, "2026-W24")
    assert report.has_data is True
    assert len(report.lecture_curves) == 1


# -------------------------------------------------------------------
# Serialization & Persistence
# -------------------------------------------------------------------
def test_to_json_safe_dict():
    mock_db = create_autospec(DBSession, instance=True)
    mock_course = Course(id=1, name="Test", code="TST")

    # Intentionally using aware datetimes here to test the timezone normalization fix
    session_curr = SessionModel(
        id=1, title="L1", start_time=datetime(2026, 6, 8, 9, tzinfo=timezone.utc)
    )

    score1 = 0.825
    score2 = 0.200
    log_curr1 = EngagementLog(
        session_id=1,
        user_id=1,
        engagement_score=score1,
        timestamp=datetime(2026, 6, 8, 9, 1, tzinfo=timezone.utc),
    )
    log_curr2 = EngagementLog(
        session_id=1,
        user_id=1,
        engagement_score=score2,
        timestamp=datetime(2026, 6, 8, 9, 5, tzinfo=timezone.utc),
    )

    prev_score = 0.900
    session_prev = SessionModel(
        id=2, title="L0", start_time=datetime(2026, 6, 1, 9, tzinfo=timezone.utc)
    )
    log_prev = EngagementLog(
        session_id=2,
        user_id=1,
        engagement_score=prev_score,
        timestamp=datetime(2026, 6, 1, 9, 1, tzinfo=timezone.utc),
    )

    setup_db_mock(
        mock_db,
        mock_course,
        [session_curr],
        [session_prev],
        [log_curr1, log_curr2],
        [log_prev],
    )

    gen = WeeklyReportGenerator(mock_db)
    report = gen.generate(1, "2026-W24")
    data = report.to_json_safe_dict()

    assert data["week_start"] == "2026-06-08T00:00:00"

    # Dynamically check aggregation calculations rather than hardcoding magic numbers
    expected_avg = round((score1 + score2) / 2 * 100, 1)
    assert data["week_summary"]["average_engagement"] == pytest.approx(expected_avg)

    # Sort timeline securely before asserting indices
    timeline = sorted(data["lecture_curves"][0]["timeline"], key=lambda x: x["minute"])
    assert len(timeline) == 2
    assert timeline[0]["minute"] == 1
    assert timeline[0]["average"] == pytest.approx(score1 * 100, 0.1)
    assert timeline[1]["minute"] == 5
    assert timeline[1]["average"] == pytest.approx(score2 * 100, 0.1)

    assert data["week_comparison"]["trend"] == "down"

    # Risk identifier blends historical logs with current logs
    expected_risk_avg = round((prev_score + ((score1 + score2) / 2)) / 2 * 100, 1)
    assert len(data["at_risk"]["entries"]) == 1
    assert data["at_risk"]["entries"][0]["average_score"] == pytest.approx(
        expected_risk_avg
    )


def test_save_report_success():
    mock_db = create_autospec(DBSession, instance=True)
    gen = WeeklyReportGenerator(mock_db)

    # Use a dummy payload for save test
    report_mock = MagicMock()
    report_mock.to_json_safe_dict.return_value = {"mock": "data"}

    row = gen.save_report(report_mock)

    assert isinstance(row, Report)
    assert row.report_type == "weekly_summary"
    assert row.content_json == {"mock": "data"}
    mock_db.add.assert_called_once_with(row)
    mock_db.commit.assert_called_once()
    mock_db.refresh.assert_called_once_with(row)


def test_save_report_failure():
    mock_db = create_autospec(DBSession, instance=True)
    gen = WeeklyReportGenerator(mock_db)

    mock_db.commit.side_effect = Exception("DB error")

    report_mock = MagicMock()
    report_mock.to_json_safe_dict.return_value = {}

    with pytest.raises(Exception, match="DB error"):
        gen.save_report(report_mock)


# -------------------------------------------------------------------
# Output Formatting Tests (HTML/PDF)
# -------------------------------------------------------------------
def test_render_html():
    mock_db = create_autospec(DBSession, instance=True)
    gen = WeeklyReportGenerator(mock_db)

    # Avoid MagicMock and use genuine dataclasses to ensure true rendering safety, utilizing explicit kwargs
    report = WeeklyReportData(
        course_id=1,
        iso_week="2026-W24",
        week_start=datetime(2026, 6, 8),
        week_end=datetime(2026, 6, 15),
        course_name="Jinja Testing Course",
        course_code="JINJA101",
        has_data=False,
        week_summary=WeekSummary(
            iso_week="2026-W24",
            week_start=datetime(2026, 6, 8),
            week_end=datetime(2026, 6, 15),
            course_name="Jinja Testing Course",
            course_code="JINJA101",
            lecture_count=0,
            student_count=0,
            average_engagement=0.0,
            engaged_pct=0.0,
            highest_lecture=None,
            lowest_lecture=None,
            has_data=False,
        ),
        lecture_curves=[],
        day_pattern=[],
        time_pattern=[],
        week_comparison=WeekComparison(
            current_week_avg=None,
            previous_week_avg=None,
            delta=None,
            delta_pct=None,
            trend="no_data",
        ),
        at_risk=AtRiskSummary(count=0, total_students=0, entries=[]),
        difficult_segments=[],
    )

    html = gen.render_html(report)
    assert isinstance(html, str)

    # Assert concrete structural and variable content
    assert "Jinja Testing Course" in html
    assert "2026-W24" in html
    assert "<html" in html.lower()


def test_render_pdf(monkeypatch):
    mock_db = create_autospec(DBSession, instance=True)
    gen = WeeklyReportGenerator(mock_db)
    report_mock = MagicMock()

    monkeypatch.setattr(
        gen, "render_html", lambda r: "<html><body>Report</body></html>"
    )

    weasy_mock = MagicMock()
    weasy_mock.return_value.write_pdf.return_value = b"%PDF-1.4 mock pdf bytes"

    mock_weasyprint = MagicMock()
    mock_weasyprint.HTML = weasy_mock
    monkeypatch.setitem(sys.modules, "weasyprint", mock_weasyprint)

    pdf_bytes = gen.render_pdf(report_mock)
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes == b"%PDF-1.4 mock pdf bytes"


# -------------------------------------------------------------------
# Performance & Infrastructure
# -------------------------------------------------------------------
@pytest.mark.slow
def test_performance_load():
    """Acceptance criteria: generate under acceptable limits for realistic load."""
    mock_db = create_autospec(DBSession, instance=True)
    mock_course = Course(id=1, name="Large Course", code="LC101")

    session_curr = SessionModel(id=1, title="L1", start_time=datetime(2026, 6, 8, 9))
    logs_curr = [
        EngagementLog(
            session_id=1,
            user_id=i % 100,
            engagement_score=0.5,
            timestamp=datetime(2026, 6, 8, 9, i % 60),
        )
        for i in range(5000)
    ]

    setup_db_mock(mock_db, mock_course, [session_curr], [], logs_curr, [])
    gen = WeeklyReportGenerator(mock_db)

    start = time.perf_counter()
    report = gen.generate(1, "2026-W24")
    duration = time.perf_counter() - start

    # Verifying it completes gracefully within 10 seconds, but marked slow
    assert duration < 10.0
    assert report.has_data is True


def test_cli_smoke():
    """Verify the CLI is correctly wired up and executable."""
    result = subprocess.run(
        [sys.executable, "-m", "src.reports.weekly_report", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "usage:" in result.stdout.lower()
