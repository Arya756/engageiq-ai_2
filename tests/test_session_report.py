"""Tests for session report generator — Issue #27."""

import pytest
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.config.settings import PrivacyMode, UserRole
from src.models import Base
from src.models.course import Course, CourseEnrollment
from src.models.engagement_log import EngagementLog, EngagementState
from src.models.report import Report
from src.models.session import Session as SessionModel
from src.models.user import User
from src.reports.session_report import (
    DistractionMoment,
    SessionReportData,
    SessionReportGenerator,
    StateDistributionEntry,
)


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture()
def seeded(db):
    teacher = User(
        name="Teacher",
        email="teacher@test.com",
        role=UserRole.TEACHER,
        privacy_mode=PrivacyMode.SHARE_WITH_TEACHER,
        google_id="g_teacher",
        is_active=True,
    )
    db.add(teacher)
    db.commit()

    course = Course(teacher_id=teacher.id, name="Intro CS", code="CS100")
    db.add(course)
    db.commit()

    students = []
    for i in range(3):
        s = User(
            name=f"Student {i}",
            email=f"s{i}@test.com",
            role=UserRole.STUDENT,
            privacy_mode=PrivacyMode.SHARE_WITH_TEACHER,
            google_id=f"g_s{i}",
            is_active=True,
        )
        db.add(s)
        db.commit()
        db.add(CourseEnrollment(course_id=course.id, user_id=s.id, is_active=True))
        students.append(s)
    db.commit()

    now = datetime(2025, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
    session_row = SessionModel(
        course_id=course.id,
        title="Lecture 1",
        start_time=now,
        end_time=now + timedelta(hours=1),
        status="completed",
    )
    db.add(session_row)
    db.commit()

    scores = [0.85, 0.72, 0.60, 0.90, 0.45, 0.80]
    for i, score in enumerate(scores):
        for student in students:
            db.add(
                EngagementLog(
                    session_id=session_row.id,
                    user_id=student.id,
                    timestamp=now + timedelta(minutes=i * 10),
                    engagement_score=score,
                    state=EngagementState.ENGAGED if score > 0.7 else EngagementState.PASSIVE,
                )
            )
    db.commit()

    return {
        "db": db,
        "session_id": session_row.id,
        "students": students,
        "course": course,
    }


class TestSessionReportData:

    def test_to_json_safe_dict_scales_overall_average(self, seeded):
        gen = SessionReportGenerator(seeded["db"])
        report = gen.generate(seeded["session_id"])
        d = report.to_json_safe_dict()
        assert d["overall_average"] >= 1.0, "overall_average should be on 0-100 scale"

    def test_to_json_safe_dict_scales_engaged_pct(self, seeded):
        gen = SessionReportGenerator(seeded["db"])
        report = gen.generate(seeded["session_id"])
        d = report.to_json_safe_dict()
        assert d["engaged_pct"] >= 1.0, "engaged_pct should be on 0-100 scale"

    def test_to_json_safe_dict_scales_timeline_averages(self, seeded):
        gen = SessionReportGenerator(seeded["db"])
        report = gen.generate(seeded["session_id"])
        d = report.to_json_safe_dict()
        for point in d["timeline"]:
            assert point["average"] >= 1.0 or point["average"] == 0.0, (
                f"timeline average {point['average']} should be on 0-100 scale"
            )

    def test_to_json_safe_dict_scales_class_average(self, seeded):
        gen = SessionReportGenerator(seeded["db"])
        student = seeded["students"][0]
        report = gen.generate(seeded["session_id"], user_id=student.id)
        d = report.to_json_safe_dict()
        assert d["class_average"] is not None
        assert d["class_average"] >= 1.0, "class_average should be on 0-100 scale"

    def test_to_json_safe_dict_scales_class_timeline(self, seeded):
        gen = SessionReportGenerator(seeded["db"])
        student = seeded["students"][0]
        report = gen.generate(seeded["session_id"], user_id=student.id)
        d = report.to_json_safe_dict()
        assert d["class_timeline"] is not None
        for point in d["class_timeline"]:
            assert point["average"] >= 1.0 or point["average"] == 0.0


class TestSessionReportGenerator:

    def test_generate_class_scope(self, seeded):
        gen = SessionReportGenerator(seeded["db"])
        report = gen.generate(seeded["session_id"])
        assert report.scope == "class"
        assert report.user_id is None
        assert report.has_data is True
        assert 0.0 <= report.overall_average <= 1.0
        assert 0.0 <= report.engaged_pct <= 1.0

    def test_generate_student_scope(self, seeded):
        gen = SessionReportGenerator(seeded["db"])
        student = seeded["students"][0]
        report = gen.generate(seeded["session_id"], user_id=student.id)
        assert report.scope == "student"
        assert report.user_id == student.id
        assert report.class_average is not None
        assert report.class_timeline is not None

    def test_generate_nonexistent_session(self, seeded):
        gen = SessionReportGenerator(seeded["db"])
        with pytest.raises(ValueError, match="not found"):
            gen.generate(99999)

    def test_state_distribution_sums_to_100(self, seeded):
        gen = SessionReportGenerator(seeded["db"])
        report = gen.generate(seeded["session_id"])
        total = sum(s.percentage for s in report.state_distribution)
        assert abs(total - 100.0) < 0.5

    def test_render_html_returns_string(self, seeded):
        gen = SessionReportGenerator(seeded["db"])
        report = gen.generate(seeded["session_id"])
        html = gen.render_html(report)
        assert isinstance(html, str)
        assert "<canvas" in html

    def test_save_report_class(self, seeded):
        gen = SessionReportGenerator(seeded["db"])
        report = gen.generate(seeded["session_id"])
        row = gen.save_report(report)
        assert row.report_type == "session_summary"
        assert row.user_id is None

    def test_save_report_student(self, seeded):
        gen = SessionReportGenerator(seeded["db"])
        student = seeded["students"][0]
        report = gen.generate(seeded["session_id"], user_id=student.id)
        row = gen.save_report(report)
        assert row.report_type == "student_personal"
        assert row.user_id == student.id

    def test_duration_minutes(self, seeded):
        gen = SessionReportGenerator(seeded["db"])
        report = gen.generate(seeded["session_id"])
        assert report.duration_minutes == pytest.approx(60.0, abs=0.1)


class TestDistractionMoment:

    def test_to_json_safe_scales_values(self):
        m = DistractionMoment(
            minute=5,
            timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
            value=0.45,
            baseline=0.72,
            drop_pct=0.375,
        )
        d = m.to_json_safe()
        assert d["value"] == 45.0
        assert d["baseline"] == 72.0
        assert isinstance(d["timestamp"], str)
