"""Session engagement report generator (Issue #27).

Two scopes from one generator:
    scope="class"   (user_id=None) -> teacher report, anonymized, class-wide.
    scope="student" (user_id=<id>) -> that student's own report, with the
                                       class average attached as a benchmark.

Used by #32 (student dashboard) and #33 (teacher dashboard) via the same
generate()/render_html() calls, just with/without user_id.
All stats reuse ClassAggregator (#24) - no aggregation logic duplicated here.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.orm import Session as DBSession

from src.analytics.class_aggregator import ClassAggregator, ClassStats, EngagementDip
from src.models.course import Course, CourseEnrollment
from src.models.engagement_log import EngagementLog, EngagementState
from src.models.report import Report
from src.models.session import Session as SessionModel

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
TEMPLATE_NAME = "session_report.html"
TOP_DISTRACTION_COUNT = 3
DIP_THRESHOLD = 0.15  # matches ClassAggregator.detect_dips default


@dataclass
class DistractionMoment:
    """One flagged dip. Field names are scope-neutral (value/baseline)
    since this is shared by both class and student reports."""

    minute: int
    timestamp: datetime
    value: float
    baseline: float
    drop_pct: float

    def to_json_safe(self) -> dict:
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        d["value"] = round(self.value * 100, 1)
        d["baseline"] = round(self.baseline * 100, 1)
        return d


@dataclass
class StateDistributionEntry:
    """% of frames spent in one engagement state, for this scope."""

    state: str
    count: int
    percentage: float


@dataclass
class SessionReportData:
    """Report data for either scope.

    scope="class": no individual student ever appears; class_average
        fields stay None (would just duplicate overall_average).
    scope="student": overall_average/timeline/etc. are the student's
        own data; class_average/class_timeline are the anonymized
        class-wide benchmark.
    """

    session_id: int
    scope: str  # "class" | "student"
    user_id: Optional[int]
    course_name: str
    course_code: str
    title: str
    status: str
    start_time: datetime
    end_time: Optional[datetime]
    duration_minutes: float
    student_count: int
    has_data: bool  # False if this scope has zero logs
    overall_average: float
    engaged_pct: float
    timeline: Dict[int, float] = field(default_factory=dict)
    state_distribution: List[StateDistributionEntry] = field(default_factory=list)
    distraction_moments: List[DistractionMoment] = field(default_factory=list)
    class_average: Optional[float] = None
    class_engaged_pct: Optional[float] = None
    class_timeline: Optional[Dict[int, float]] = None
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_json_safe_dict(self) -> dict:
        """JSON-safe form for DB persistence and template embedding."""
        return {
            "session_id": self.session_id,
            "scope": self.scope,
            "user_id": self.user_id,
            "course_name": self.course_name,
            "course_code": self.course_code,
            "title": self.title,
            "status": self.status,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_minutes": round(self.duration_minutes, 1),
            "student_count": self.student_count,
            "has_data": self.has_data,
            "overall_average": round(self.overall_average * 100, 1),
            "engaged_pct": round(self.engaged_pct * 100, 1),
            "timeline": [
                {"minute": m, "average": round(v * 100, 1)}
                for m, v in sorted(self.timeline.items())
            ],
            "state_distribution": [asdict(s) for s in self.state_distribution],
            "distraction_moments": [d.to_json_safe() for d in self.distraction_moments],
            "class_average": (
                round(self.class_average * 100, 1) if self.class_average is not None else None
            ),
            "class_engaged_pct": (
                round(self.class_engaged_pct * 100, 1)
                if self.class_engaged_pct is not None
                else None
            ),
            "class_timeline": (
                [
                    {"minute": m, "average": round(v * 100, 1)}
                    for m, v in sorted(self.class_timeline.items())
                ]
                if self.class_timeline is not None
                else None
            ),
            "generated_at": self.generated_at.isoformat(),
        }


class SessionReportGenerator:
    """Builds and renders session reports for either scope.

    Usage:
        gen = SessionReportGenerator(db)
        gen.generate(session_id)               # teacher/class report
        gen.generate(session_id, user_id=42)    # student's own report
    """

    def __init__(self, db: DBSession):
        self.db = db
        # Shared instance is safe: aggregate()/detect_dips() are pure
        # and don't touch ClassAggregator's internal timeline state.
        self.aggregator = ClassAggregator()
        self._jinja_env = Environment(
            loader=FileSystemLoader(str(TEMPLATE_DIR)),
            autoescape=select_autoescape(["html"]),
        )

    # ---- data assembly ------------------------------------------------

    def generate(
        self, session_id: int, user_id: Optional[int] = None
    ) -> SessionReportData:
        session_row = self.db.get(SessionModel, session_id)
        if session_row is None:
            raise ValueError(f"Session {session_id} not found")

        course = self.db.get(Course, session_row.course_id)

        all_logs: List[EngagementLog] = (
            self.db.query(EngagementLog)
            .filter(EngagementLog.session_id == session_id)
            .order_by(EngagementLog.timestamp)
            .all()
        )

        student_count = len({log.user_id for log in all_logs})
        if student_count == 0:
            # No logs yet -- fall back to enrollment count.
            student_count = (
                self.db.query(CourseEnrollment)
                .filter(CourseEnrollment.course_id == session_row.course_id)
                .count()
            )

        # Class-wide stats: needed directly for scope="class", and as
        # the comparison benchmark for scope="student".
        class_stats: ClassStats = self.aggregator.aggregate(
            [log.engagement_score for log in all_logs]
        )

        scope = "class" if user_id is None else "student"
        scoped_logs = (
            all_logs
            if scope == "class"
            else [log for log in all_logs if log.user_id == user_id]
        )
        has_data = bool(scoped_logs)

        scoped_stats: ClassStats = (
            class_stats
            if scope == "class"
            else self.aggregator.aggregate(
                [log.engagement_score for log in scoped_logs]
            )
        )

        timeline = self._build_timeline(scoped_logs, session_row.start_time)
        distraction_moments = self._top_distraction_moments(
            timeline, session_row.start_time
        )
        state_distribution = self._state_distribution(scoped_logs)
        duration_minutes = self._duration_minutes(session_row, all_logs)

        class_average: Optional[float] = None
        class_engaged_pct: Optional[float] = None
        class_timeline: Optional[Dict[int, float]] = None
        if scope == "student":
            class_average = class_stats.average
            class_engaged_pct = class_stats.engaged_pct
            class_timeline = self._build_timeline(all_logs, session_row.start_time)

        return SessionReportData(
            session_id=session_id,
            scope=scope,
            user_id=user_id,
            course_name=course.name if course else "Unknown course",
            course_code=course.code if course else "",
            title=session_row.title,
            status=session_row.status,
            start_time=session_row.start_time,
            end_time=session_row.end_time,
            duration_minutes=duration_minutes,
            student_count=student_count,
            has_data=has_data,
            overall_average=scoped_stats.average,
            engaged_pct=scoped_stats.engaged_pct,
            timeline=timeline,
            state_distribution=state_distribution,
            distraction_moments=distraction_moments,
            class_average=class_average,
            class_engaged_pct=class_engaged_pct,
            class_timeline=class_timeline,
        )

    # ---- helpers --------------------------------------------------------

    @staticmethod
    def _duration_minutes(
        session_row: SessionModel, logs: List[EngagementLog]
    ) -> float:
        if session_row.end_time is not None:
            return (
                session_row.end_time - session_row.start_time
            ).total_seconds() / 60.0
        if logs:
            return (logs[-1].timestamp - session_row.start_time).total_seconds() / 60.0
        return 0.0

    @staticmethod
    def _build_timeline(
        logs: List[EngagementLog], start_time: datetime
    ) -> Dict[int, float]:
        """Bucket logs into session-relative minutes. Uses a fresh
        ClassAggregator each call so building two timelines per
        generate() (personal + class) never share state."""
        aggregator = ClassAggregator()
        buckets: Dict[int, List[float]] = {}
        for log in logs:
            minute = int((log.timestamp - start_time).total_seconds() // 60)
            buckets.setdefault(minute, []).append(log.engagement_score)
        for minute, scores in buckets.items():
            aggregator.update_timeline(minute, scores)
        return aggregator.get_timeline()

    def _top_distraction_moments(
        self, timeline: Dict[int, float], start_time: datetime
    ) -> List[DistractionMoment]:
        """detect_dips uses the timeline's own mean as baseline, so this
        works unchanged for both a personal timeline and a class one."""
        dips: List[EngagementDip] = self.aggregator.detect_dips(
            timeline, threshold=DIP_THRESHOLD
        )

        def _severity(dip: EngagementDip) -> float:
            return (
                (dip.session_avg - dip.class_avg) / dip.session_avg
                if dip.session_avg
                else 0.0
            )

        ranked = sorted(dips, key=_severity, reverse=True)[:TOP_DISTRACTION_COUNT]
        moments = [
            DistractionMoment(
                minute=dip.minute,
                timestamp=start_time + timedelta(minutes=dip.minute),
                value=dip.class_avg,
                baseline=dip.session_avg,
                drop_pct=_severity(dip),
            )
            for dip in ranked
        ]
        moments.sort(key=lambda m: m.minute)  # chronological for display
        return moments

    @staticmethod
    def _state_distribution(logs: List[EngagementLog]) -> List[StateDistributionEntry]:
        if not logs:
            return [
                StateDistributionEntry(state=s.value, count=0, percentage=0.0)
                for s in EngagementState
            ]
        counts = {s: 0 for s in EngagementState}
        for log in logs:
            counts[log.state] = counts.get(log.state, 0) + 1
        total = len(logs)
        return [
            StateDistributionEntry(
                state=state.value,
                count=count,
                percentage=round((count / total) * 100, 1),
            )
            for state, count in counts.items()
        ]

    # ---- rendering ------------------------------------------------------

    def render_html(self, report: SessionReportData) -> str:
        """Self-contained HTML: inline CSS, Chart.js via CDN, chart data
        embedded as JSON so charts draw client-side (fast, no server-side
        image rendering)."""
        template = self._jinja_env.get_template(TEMPLATE_NAME)
        data = report.to_json_safe_dict()
        return template.render(
            report=data,
            timeline_json=json.dumps(data["timeline"]),
            state_distribution_json=json.dumps(data["state_distribution"]),
            class_timeline_json=(
                json.dumps(data["class_timeline"])
                if data["class_timeline"] is not None
                else "null"
            ),
        )

    # ---- persistence ------------------------------------------------------

    def save_report(self, report: SessionReportData) -> Report:
        """Persists as a Report row using the convention already asserted
        in tests/test_migrations.py:
            scope="class"   -> report_type="session_summary",    user_id=None
            scope="student" -> report_type="student_personal", user_id=<id>
        """
        report_type = (
            "student_personal" if report.scope == "student" else "session_summary"
        )
        row = Report(
            session_id=report.session_id,
            user_id=report.user_id,
            report_type=report_type,
            content_json=report.to_json_safe_dict(),
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    # ---- convenience --------------------------------------------------

    def generate_and_render(
        self, session_id: int, user_id: Optional[int] = None
    ) -> str:
        report = self.generate(session_id, user_id=user_id)
        return self.render_html(report)


# CLI:
#   Teacher report:  python -m src.reports.session_report --session-id 1 --output report.html
#   Student report:  python -m src.reports.session_report --session-id 1 --user-id 7 --output my_report.html
def _main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a session engagement report."
    )
    parser.add_argument("--session-id", type=int, required=True)
    parser.add_argument(
        "--user-id", type=int, default=None, help="Student's personal report if set."
    )
    parser.add_argument("--output", default="report.html")
    parser.add_argument("--save", action="store_true", help="Persist as a Report row.")
    args = parser.parse_args()

    from src.config.database import SessionLocal

    db = SessionLocal()
    try:
        start = time.perf_counter()
        generator = SessionReportGenerator(db)
        report = generator.generate(args.session_id, user_id=args.user_id)
        html = generator.render_html(report)
        elapsed = time.perf_counter() - start

        Path(args.output).write_text(html, encoding="utf-8")
        print(f"Report written to {args.output} ({elapsed:.2f}s, scope={report.scope})")

        if args.save:
            row = generator.save_report(report)
            print(f"Saved Report id={row.id} (report_type={row.report_type})")
    finally:
        db.close()


if __name__ == "__main__":
    _main()
