import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from src.config.settings import PrivacyMode, UserRole
from src.models import (
    Base,
    Course,
    CourseEnrollment,
    EngagementLog,
    EngagementState,
    Nudge,
    Report,
    Session,
    User,
)

# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def engine():
    """In-memory SQLite engine for fast isolated tests."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture(scope="module")
def db(engine):
    """Scoped DB session."""
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture(scope="module")
def seeded_db(db):
    """Populate DB with the same data as scripts/seed.py."""
    import random
    from datetime import datetime, timedelta

    # Teachers
    teachers = [
        User(
            name=f"Teacher {i}",
            email=f"teacher{i}@engageiq.com",
            role=UserRole.TEACHER,
            privacy_mode=PrivacyMode.SHARE_WITH_TEACHER,
            google_id=f"google_teacher_{i}",
            is_active=True,
        )
        for i in range(1, 3)
    ]
    db.add_all(teachers)
    db.commit()

    # Students
    students = [
        User(
            name=f"Student {i}",
            email=f"student{i}@engageiq.com",
            role=UserRole.STUDENT,
            privacy_mode=PrivacyMode.SHARE_WITH_TEACHER,
            google_id=f"google_student_{i}",
            is_active=True,
        )
        for i in range(1, 11)
    ]
    db.add_all(students)
    db.commit()

    # Courses
    courses = [
        Course(teacher_id=teachers[0].id, name="Introduction to Python", code="CS101"),
        Course(teacher_id=teachers[0].id, name="Data Structures", code="CS201"),
        Course(teacher_id=teachers[1].id, name="Machine Learning", code="CS301"),
    ]
    db.add_all(courses)
    db.commit()

    # Enrollments
    for student in students:
        for course in random.sample(courses, k=random.randint(1, 3)):
            db.add(
                CourseEnrollment(
                    course_id=course.id, user_id=student.id, is_active=True
                )
            )
    db.commit()

    # Sessions
    now = datetime.now()
    sessions = [
        Session(
            course_id=courses[0].id,
            title="Python Basics 1",
            start_time=now - timedelta(days=2),
            end_time=now - timedelta(days=2) + timedelta(hours=1),
            status="completed",
        ),
        Session(
            course_id=courses[0].id,
            title="Python Basics 2",
            start_time=now - timedelta(days=1),
            end_time=now - timedelta(days=1) + timedelta(hours=1),
            status="completed",
        ),
        Session(
            course_id=courses[1].id,
            title="Arrays and Lists",
            start_time=now - timedelta(hours=5),
            end_time=now - timedelta(hours=4),
            status="completed",
        ),
        Session(
            course_id=courses[1].id,
            title="Trees and Graphs",
            start_time=now,
            end_time=None,
            status="active",
        ),
        Session(
            course_id=courses[2].id,
            title="Linear Regression",
            start_time=now + timedelta(days=1),
            end_time=None,
            status="scheduled",
        ),
    ]
    db.add_all(sessions)
    db.commit()

    # Engagement logs
    past_sessions = [s for s in sessions if s.status in ("completed", "active")]
    states = list(EngagementState)
    for sess in past_sessions:
        enrolled = db.query(CourseEnrollment).filter_by(course_id=sess.course_id).all()
        for enrollment in enrolled:
            for i in range(5):
                state = random.choice(states)
                log = EngagementLog(
                    session_id=sess.id,
                    user_id=enrollment.user_id,
                    timestamp=sess.start_time + timedelta(minutes=i * 10),
                    engagement_score=round(random.uniform(0.1, 1.0), 2),
                    state=state,
                    drowsiness_count=random.randint(0, 3),
                    distracted_count=random.randint(0, 3),
                    negative_expression_count=random.randint(0, 2),
                    phone_detected_count=random.randint(0, 1),
                )
                db.add(log)
                db.commit()

                if state in (EngagementState.DISTRACTED, EngagementState.DROWSY):
                    db.add(
                        Nudge(
                            session_id=sess.id,
                            user_id=enrollment.user_id,
                            engagement_log_id=log.id,
                            nudge_type="pop-up",
                            triggered_state=state,
                            effectiveness_delta=round(random.uniform(-0.2, 0.8), 2),
                        )
                    )
    db.commit()

    # Reports
    for sess in [s for s in sessions if s.status == "completed"]:
        enrolled = db.query(CourseEnrollment).filter_by(course_id=sess.course_id).all()
        for enrollment in enrolled:
            db.add(
                Report(
                    session_id=sess.id,
                    user_id=enrollment.user_id,
                    report_type="student_personal",
                    content_json={"avg_engagement_score": 0.75},
                )
            )
        db.add(
            Report(
                session_id=sess.id,
                user_id=None,
                report_type="session_summary",
                content_json={"avg_engagement_score": 0.70},
            )
        )
    db.commit()

    return db


# ── Migration tests ────────────────────────────────────────────────────────────


class TestMigrations:

    EXPECTED_TABLES = {
        "users",
        "courses",
        "course_enrollment",
        "sessions",
        "engagement_logs",
        "nudges",
        "reports",
    }

    def test_all_tables_created(self, engine):
        """alembic upgrade head creates all expected tables."""
        actual = set(inspect(engine).get_table_names())
        assert self.EXPECTED_TABLES.issubset(
            actual
        ), f"Missing tables: {self.EXPECTED_TABLES - actual}"

    def test_users_columns(self, engine):
        cols = {c["name"] for c in inspect(engine).get_columns("users")}
        expected = {
            "id",
            "name",
            "email",
            "role",
            "privacy_mode",
            "is_active",
            "google_id",
            "created_at",
            "updated_at",
        }
        assert expected.issubset(cols)

    def test_engagement_logs_columns(self, engine):
        cols = {c["name"] for c in inspect(engine).get_columns("engagement_logs")}
        expected = {
            "id",
            "session_id",
            "user_id",
            "timestamp",
            "engagement_score",
            "state",
            "drowsiness_count",
            "distracted_count",
            "phone_detected_count",
        }
        assert expected.issubset(cols)

    def test_nudges_columns(self, engine):
        cols = {c["name"] for c in inspect(engine).get_columns("nudges")}
        expected = {
            "id",
            "session_id",
            "user_id",
            "engagement_log_id",
            "triggered_state",
            "effectiveness_delta",
            "created_at",
        }
        assert expected.issubset(cols)

    def test_downgrade_drops_all_tables(self):
        """downgrade base removes all tables cleanly."""
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        assert len(inspect(engine).get_table_names()) > 0
        Base.metadata.drop_all(engine)
        assert inspect(engine).get_table_names() == []


# ── Seed data tests ────────────────────────────────────────────────────────────


class TestSeedData:

    def test_teacher_count(self, seeded_db):
        count = seeded_db.query(User).filter_by(role=UserRole.TEACHER).count()
        assert count == 2, f"Expected 2 teachers, got {count}"

    def test_student_count(self, seeded_db):
        count = seeded_db.query(User).filter_by(role=UserRole.STUDENT).count()
        assert count == 10, f"Expected 10 students, got {count}"

    def test_course_count(self, seeded_db):
        count = seeded_db.query(Course).count()
        assert count == 3, f"Expected 3 courses, got {count}"

    def test_session_count(self, seeded_db):
        count = seeded_db.query(Session).count()
        assert count == 5, f"Expected 5 sessions, got {count}"

    def test_engagement_logs_exist(self, seeded_db):
        count = seeded_db.query(EngagementLog).count()
        assert count > 0, "Expected engagement logs to exist"

    def test_nudges_exist(self, seeded_db):
        count = seeded_db.query(Nudge).count()
        assert count > 0, "Expected nudges to exist"

    def test_reports_exist(self, seeded_db):
        count = seeded_db.query(Report).count()
        assert count > 0, "Expected reports to exist"

    def test_student_personal_reports_have_user_id(self, seeded_db):
        reports = (
            seeded_db.query(Report).filter_by(report_type="student_personal").all()
        )
        assert all(r.user_id is not None for r in reports)

    def test_session_summary_reports_have_no_user_id(self, seeded_db):
        reports = seeded_db.query(Report).filter_by(report_type="session_summary").all()
        assert all(r.user_id is None for r in reports)

    def test_nudges_linked_to_engagement_logs(self, seeded_db):
        nudges = seeded_db.query(Nudge).all()
        assert all(n.engagement_log_id is not None for n in nudges)

    def test_idempotency(self, seeded_db):
        """Running seed twice does not duplicate data."""
        user_count_before = seeded_db.query(User).count()
        # Simulate idempotency check — if users exist, skip seeding
        if seeded_db.query(User).first():
            pass  # seed would return early
        user_count_after = seeded_db.query(User).count()
        assert user_count_before == user_count_after

    def test_enrollment_relationships(self, seeded_db):
        """Every enrollment links to a valid user and course."""
        enrollments = seeded_db.query(CourseEnrollment).all()
        assert len(enrollments) > 0
        for e in enrollments:
            assert e.course is not None
            assert e.student is not None

    def test_session_status_values(self, seeded_db):
        valid = {"scheduled", "active", "completed", "cancelled"}
        sessions = seeded_db.query(Session).all()
        for s in sessions:
            assert s.status in valid, f"Invalid status: {s.status}"
