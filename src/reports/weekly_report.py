"""Weekly engagement trend report generator (Issue #28).

Aggregates a course's engagement data for one ISO calendar week and produces
a report covering: a week summary, per-lecture engagement curves, day-of-week
and time-of-day patterns, a week-over-week comparison, an anonymized at-risk
summary, and difficult segments ranked across all lectures in the week.

Reuses existing analytics rather than re-implementing them:
    - `ClassAggregator` (#24)         -> per-lecture timelines, snapshot stats, dip detection
    - `TrendAnalyzer`   (#25)         -> percent-change math for the week-over-week delta
    - `RiskIdentifier`  (#25)         -> anonymized at-risk student evaluation
    - `DifficultyCorrelator` (#30)    -> ranking dips into "difficult segments" across lectures

Data flow (see #28 checklist): DB -> load records once -> aggregate ->
WeeklyReportData -> HTML -> PDF. Calculations never happen in the template;
the template only displays fields already computed here.

Charts are rendered as plain server-side SVG (not Chart.js/canvas) because
WeasyPrint, used for PDF export, does not execute JavaScript -- an SVG
string embedded in the HTML renders identically in both the browser and
the PDF.
"""

from __future__ import annotations

import argparse
import logging
import re
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.orm import Session as DBSession

from src.analytics.class_aggregator import ClassAggregator, ClassStats
from src.analytics.difficulty_correlator import DifficultyCorrelator, DifficultySegment
from src.analytics.risk_identifier import RiskEvaluation, RiskIdentifier
from src.analytics.trend_analyzer import TrendAnalyzer
from src.models.course import Course, CourseEnrollment
from src.models.engagement_log import EngagementLog
from src.models.report import Report
from src.models.session import Session as SessionModel

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
TEMPLATE_NAME = "weekly_report.html"

# Matches ClassAggregator/RiskIdentifier's own dip-detection default so a
# minute is treated as "difficult" consistently everywhere it's evaluated.
DIP_THRESHOLD = 0.15
# A single week may only have a handful of lectures, so unlike
# DifficultyCorrelator's own default (min_sessions=2), a dip that shows up
# in even one lecture this week is worth surfacing to the teacher.
MIN_SESSIONS_FOR_DIFFICULT_SEGMENT = 1
TOP_DIFFICULT_SEGMENTS = 3

# Time-of-day buckets. Boundaries are in local hour-of-day (0-23)
MORNING_START_HOUR = 5
AFTERNOON_START_HOUR = 12
EVENING_START_HOUR = 17

WEEKDAY_NAMES = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]

_ISO_WEEK_RE = re.compile(r"^\d{4}-W\d{2}$")


def friendly_date(value):
    """Jinja filter to format dates cleanly for the report display."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value[:10]
    return value.strftime("%Y-%m-%d")


def friendly_datetime(value):
    """Jinja filter to format datetimes cleanly for the report display."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value[:16].replace("T", " ")
    return value.strftime("%Y-%m-%d %H:%M")


def minute_range(minute):
    """Jinja filter to format a single minute into a range (e.g., 5 -> 05:00 - 06:00)."""
    if minute is None:
        return ""
    try:
        m = int(minute)
        return f"{m:02d}:00 - {m+1:02d}:00"
    except (ValueError, TypeError):
        return str(minute)


# --------------------------------------------------------------------------
# Report data model
# --------------------------------------------------------------------------


@dataclass
class LectureRef:
    """Lightweight pointer to a single lecture."""
    session_id: int
    title: str
    average: float


@dataclass
class WeekSummary:
    iso_week: str
    week_start: datetime
    week_end: datetime
    course_name: str
    course_code: str
    lecture_count: int
    student_count: int
    average_engagement: float
    engaged_pct: float
    highest_lecture: Optional[LectureRef]
    lowest_lecture: Optional[LectureRef]
    has_data: bool


@dataclass
class LectureCurve:
    """Per-lecture engagement curve for the week's overlaid line chart."""
    session_id: int
    title: str
    start_time: datetime
    average: float
    student_count: int
    has_data: bool
    timeline: Dict[int, float] = field(default_factory=dict)  # minute -> avg (0-1)


@dataclass
class DayPatternEntry:
    day_name: str
    average: float
    log_count: int
    session_count: int


@dataclass
class TimePatternEntry:
    period: str  # "Morning" | "Afternoon" | "Evening"
    average: float
    log_count: int


@dataclass
class WeekComparison:
    current_week_avg: Optional[float]
    previous_week_avg: Optional[float]
    delta: Optional[float]  # current - previous, 0-1 scale
    delta_pct: Optional[float]  # signed; positive = improvement
    trend: str  # "up" | "down" | "flat" | "no_data"


@dataclass
class AtRiskEntry:
    student_id: str  # already anonymized by RiskIdentifier
    average_score: Optional[float]
    reasons: List[str] = field(default_factory=list)


@dataclass
class AtRiskSummary:
    count: int
    total_students: int
    entries: List[AtRiskEntry] = field(default_factory=list)


@dataclass
class DifficultSegmentEntry:
    rank: int
    lecture_title: str
    session_id: int
    minute: int
    avg_drop_pct: float
    session_count: int
    severity: float


@dataclass
class WeeklyReportData:
    course_id: int
    iso_week: str
    week_start: datetime
    week_end: datetime
    course_name: str
    course_code: str
    has_data: bool
    week_summary: WeekSummary
    lecture_curves: List[LectureCurve]
    day_pattern: List[DayPatternEntry]
    time_pattern: List[TimePatternEntry]
    week_comparison: WeekComparison
    at_risk: AtRiskSummary
    difficult_segments: List[DifficultSegmentEntry]
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_json_safe_dict(self) -> dict:
        """JSON-safe form for DB persistence and template embedding."""
        def pct(value: Optional[float]) -> Optional[float]:
            return round(value * 100, 1) if value is not None else None

        def lecture_ref(ref: Optional[LectureRef]) -> Optional[dict]:
            if ref is None:
                return None
            d = asdict(ref)
            d["average"] = pct(ref.average)
            return d

        return {
            "course_id": self.course_id,
            "iso_week": self.iso_week,
            "week_start": self.week_start.isoformat(),
            "week_end": self.week_end.isoformat(),
            "course_name": self.course_name,
            "course_code": self.course_code,
            "has_data": self.has_data,
            "week_summary": {
                "iso_week": self.week_summary.iso_week,
                "week_start": self.week_summary.week_start.isoformat(),
                "week_end": self.week_summary.week_end.isoformat(),
                "course_name": self.week_summary.course_name,
                "course_code": self.week_summary.course_code,
                "lecture_count": self.week_summary.lecture_count,
                "student_count": self.week_summary.student_count,
                "average_engagement": pct(self.week_summary.average_engagement),
                "engaged_pct": pct(self.week_summary.engaged_pct),
                "highest_lecture": lecture_ref(self.week_summary.highest_lecture),
                "lowest_lecture": lecture_ref(self.week_summary.lowest_lecture),
                "has_data": self.week_summary.has_data,
            },
            "lecture_curves": [
                {
                    "session_id": c.session_id,
                    "title": c.title,
                    "start_time": c.start_time.isoformat(),
                    "average": pct(c.average),
                    "student_count": c.student_count,
                    "has_data": c.has_data,
                    "timeline": [
                        {"minute": m, "average": pct(v)}
                        for m, v in sorted(c.timeline.items())
                    ],
                }
                for c in self.lecture_curves
            ],
            "day_pattern": [
                {
                    "day_name": d.day_name,
                    "average": pct(d.average),
                    "log_count": d.log_count,
                    "session_count": d.session_count,
                }
                for d in self.day_pattern
            ],
            "time_pattern": [
                {
                    "period": t.period,
                    "average": pct(t.average),
                    "log_count": t.log_count,
                }
                for t in self.time_pattern
            ],
            "week_comparison": {
                "current_week_avg": pct(self.week_comparison.current_week_avg),
                "previous_week_avg": pct(self.week_comparison.previous_week_avg),
                "delta": (
                    pct(self.week_comparison.delta)
                    if self.week_comparison.delta is not None
                    else None
                ),
                "delta_pct": (
                    round(self.week_comparison.delta_pct, 1)
                    if self.week_comparison.delta_pct is not None
                    else None
                ),
                "trend": self.week_comparison.trend,
            },
            "at_risk": {
                "count": self.at_risk.count,
                "total_students": self.at_risk.total_students,
                "entries": [
                    {
                        "student_id": e.student_id,
                        "average_score": pct(e.average_score),
                        "reasons": e.reasons,
                    }
                    for e in self.at_risk.entries
                ],
            },
            "difficult_segments": [asdict(s) for s in self.difficult_segments],
            "generated_at": self.generated_at.isoformat(),
        }


# --------------------------------------------------------------------------
# Generator
# --------------------------------------------------------------------------


class WeeklyReportGenerator:
    """Builds and renders weekly reports for a course + ISO week."""

    def __init__(self, db: DBSession):
        self.db = db
        self.aggregator = ClassAggregator()
        self._jinja_env = Environment(
            loader=FileSystemLoader(str(TEMPLATE_DIR)),
            autoescape=select_autoescape(["html"]),
        )
        self._jinja_env.filters["friendly_date"] = friendly_date
        self._jinja_env.filters["friendly_datetime"] = friendly_datetime
        self._jinja_env.filters["minute_range"] = minute_range

    # ---- validation -----------------------------------------------------
    
    def _validate_inputs(self, course_id: int, iso_week: str) -> None:
        """Ensure inputs are structurally valid before hitting the DB."""
        if not isinstance(course_id, int) or course_id <= 0:
            raise ValueError("course_id must be a positive integer")
            
        if not iso_week or not _ISO_WEEK_RE.match(iso_week):
            raise ValueError(
                f"Invalid ISO week '{iso_week}': expected format 'YYYY-Www', e.g. '2026-W24'"
            )

    # ---- data assembly --------------------------------------------------

    def generate(self, course_id: int, iso_week: str) -> WeeklyReportData:
        self._validate_inputs(course_id, iso_week)
        
        start = time.perf_counter()
        week_start, week_end = self._parse_iso_week(iso_week)

        course = self.db.get(Course, course_id)
        if course is None:
            raise ValueError(f"Course {course_id} not found")

        sessions = self._load_sessions(course_id, week_start, week_end)
        logs = self._load_logs([s.id for s in sessions])
        logs_by_session = self._group_logs_by_session(logs)

        prev_start, prev_end = week_start - timedelta(days=7), week_start
        prev_sessions = self._load_sessions(course_id, prev_start, prev_end)
        prev_logs = self._load_logs([s.id for s in prev_sessions])

        week_summary = self._week_summary(
            course, iso_week, week_start, week_end, sessions, logs, logs_by_session
        )
        lecture_curves = self._lecture_curves(sessions, logs_by_session)
        day_pattern = self._day_patterns(logs)
        time_pattern = self._time_patterns(logs)
        week_comparison = self._week_comparison(logs, prev_logs)
        at_risk = self._at_risk_summary(sessions, logs, prev_sessions, prev_logs)
        difficult_segments = self._difficult_segments(sessions, logs_by_session)

        report = WeeklyReportData(
            course_id=course_id,
            iso_week=iso_week,
            week_start=week_start,
            week_end=week_end,
            course_name=course.name,
            course_code=course.code,
            has_data=bool(logs),
            week_summary=week_summary,
            lecture_curves=lecture_curves,
            day_pattern=day_pattern,
            time_pattern=time_pattern,
            week_comparison=week_comparison,
            at_risk=at_risk,
            difficult_segments=difficult_segments,
        )

        elapsed = time.perf_counter() - start
        logger.info(
            "weekly_report generated course_id=%s week=%s sessions=%d logs=%d elapsed=%.2fs",
            course_id,
            iso_week,
            len(sessions),
            len(logs),
            elapsed,
        )
        return report

    # ---- loading -------------------------------------------------------

    def _load_sessions(
        self, course_id: int, week_start: datetime, week_end: datetime
    ) -> List[SessionModel]:
        return (
            self.db.query(SessionModel)
            .filter(
                SessionModel.course_id == course_id,
                SessionModel.start_time >= week_start,
                SessionModel.start_time < week_end,
            )
            .order_by(SessionModel.start_time)
            .all()
        )

    def _load_logs(self, session_ids: Sequence[int]) -> List[EngagementLog]:
        if not session_ids:
            return []
        logs = (
            self.db.query(EngagementLog)
            .filter(EngagementLog.session_id.in_(session_ids))
            .order_by(EngagementLog.timestamp)
            .all()
        )
        return [log for log in logs if log.timestamp is not None]

    @staticmethod
    def _group_logs_by_session(
        logs: Sequence[EngagementLog],
    ) -> Dict[int, List[EngagementLog]]:
        grouped: Dict[int, List[EngagementLog]] = defaultdict(list)
        for log in logs:
            grouped[log.session_id].append(log)
        return grouped

    # ---- week summary -----------------------------------------------------

    def _week_summary(
        self,
        course: Course,
        iso_week: str,
        week_start: datetime,
        week_end: datetime,
        sessions: List[SessionModel],
        logs: List[EngagementLog],
        logs_by_session: Dict[int, List[EngagementLog]],
    ) -> WeekSummary:
        stats: ClassStats = self.aggregator.aggregate(
            [log.engagement_score for log in logs]
        )

        student_count = len({log.user_id for log in logs})
        if student_count == 0:
            student_count = (
                self.db.query(CourseEnrollment)
                .filter(CourseEnrollment.course_id == course.id)
                .count()
            )

        highest: Optional[LectureRef] = None
        lowest: Optional[LectureRef] = None
        for session in sessions:
            session_logs = logs_by_session.get(session.id, [])
            if not session_logs:
                continue
            session_stats = self.aggregator.aggregate(
                [log.engagement_score for log in session_logs]
            )
            ref = LectureRef(
                session_id=session.id,
                title=session.title,
                average=session_stats.average,
            )
            if highest is None or ref.average > highest.average:
                highest = ref
            if lowest is None or ref.average < lowest.average:
                lowest = ref

        return WeekSummary(
            iso_week=iso_week,
            week_start=week_start,
            week_end=week_end,
            course_name=course.name,
            course_code=course.code,
            lecture_count=len(sessions),
            student_count=student_count,
            average_engagement=stats.average,
            engaged_pct=stats.engaged_pct,
            highest_lecture=highest,
            lowest_lecture=lowest,
            has_data=bool(logs),
        )

    # ---- per-lecture engagement curves -------------------------------------

    def _lecture_curves(
        self,
        sessions: List[SessionModel],
        logs_by_session: Dict[int, List[EngagementLog]],
    ) -> List[LectureCurve]:
        curves: List[LectureCurve] = []
        for session in sessions:
            session_logs = logs_by_session.get(session.id, [])
            timeline = self._session_timeline(session, session_logs)
            stats = self.aggregator.aggregate(
                [log.engagement_score for log in session_logs]
            )
            curves.append(
                LectureCurve(
                    session_id=session.id,
                    title=session.title,
                    start_time=session.start_time,
                    average=stats.average,
                    student_count=len({log.user_id for log in session_logs}),
                    has_data=bool(session_logs),
                    timeline=timeline,
                )
            )
        return curves

    @staticmethod
    def _session_timeline(
        session: SessionModel, session_logs: Sequence[EngagementLog]
    ) -> Dict[int, float]:
        aggregator = ClassAggregator()
        buckets: Dict[int, List[float]] = defaultdict(list)
        
        sess_ts = session.start_time.replace(tzinfo=None) if session.start_time.tzinfo else session.start_time
        
        for log in session_logs:
            log_ts = log.timestamp.replace(tzinfo=None) if log.timestamp.tzinfo else log.timestamp
            minute = int((log_ts - sess_ts).total_seconds() // 60)
            buckets[minute].append(log.engagement_score)
            
        for minute, scores in buckets.items():
            aggregator.update_timeline(minute, scores)
        return aggregator.get_timeline()

    # ---- day-of-week / time-of-day patterns --------------------------------

    def _day_patterns(self, logs: List[EngagementLog]) -> List[DayPatternEntry]:
        by_day: Dict[str, List[EngagementLog]] = defaultdict(list)
        for log in logs:
            by_day[WEEKDAY_NAMES[log.timestamp.weekday()]].append(log)

        entries: List[DayPatternEntry] = []
        for day_name in WEEKDAY_NAMES:
            day_logs = by_day.get(day_name, [])
            stats = self.aggregator.aggregate(
                [log.engagement_score for log in day_logs]
            )
            entries.append(
                DayPatternEntry(
                    day_name=day_name,
                    average=stats.average,
                    log_count=len(day_logs),
                    session_count=len({log.session_id for log in day_logs}),
                )
            )
        return entries

    def _time_patterns(self, logs: List[EngagementLog]) -> List[TimePatternEntry]:
        by_period: Dict[str, List[EngagementLog]] = defaultdict(list)
        for log in logs:
            by_period[self._period_for_hour(log.timestamp.hour)].append(log)

        entries: List[TimePatternEntry] = []
        for period in ("Morning", "Afternoon", "Evening"):
            period_logs = by_period.get(period, [])
            stats = self.aggregator.aggregate(
                [log.engagement_score for log in period_logs]
            )
            entries.append(
                TimePatternEntry(
                    period=period, average=stats.average, log_count=len(period_logs)
                )
            )
        return entries

    @staticmethod
    def _period_for_hour(hour: int) -> str:
        if MORNING_START_HOUR <= hour < AFTERNOON_START_HOUR:
            return "Morning"
        if AFTERNOON_START_HOUR <= hour < EVENING_START_HOUR:
            return "Afternoon"
        return "Evening"

    # ---- week-over-week comparison -----------------------------------------

    def _week_comparison(
        self, logs: List[EngagementLog], prev_logs: List[EngagementLog]
    ) -> WeekComparison:
        current_stats = self.aggregator.aggregate(
            [log.engagement_score for log in logs]
        )
        previous_stats = self.aggregator.aggregate(
            [log.engagement_score for log in prev_logs]
        )

        current_avg: Optional[float] = current_stats.average if logs else None
        previous_avg: Optional[float] = previous_stats.average if prev_logs else None

        if current_avg is None or previous_avg is None:
            return WeekComparison(
                current_week_avg=current_avg,
                previous_week_avg=previous_avg,
                delta=None,
                delta_pct=None,
                trend="no_data",
            )

        delta = current_avg - previous_avg
        delta_pct = -TrendAnalyzer.percent_decline(previous_avg, current_avg)

        if delta > 1e-9:
            trend = "up"
        elif delta < -1e-9:
            trend = "down"
        else:
            trend = "flat"

        return WeekComparison(
            current_week_avg=current_avg,
            previous_week_avg=previous_avg,
            delta=delta,
            delta_pct=delta_pct,
            trend=trend,
        )

    # ---- at-risk summary (anonymized) --------------------------------------

    def _at_risk_summary(
        self,
        sessions: List[SessionModel],
        logs: List[EngagementLog],
        prev_sessions: List[SessionModel],
        prev_logs: List[EngagementLog],
    ) -> AtRiskSummary:
        ordered_sessions = sorted(
            list(prev_sessions) + list(sessions), key=lambda s: s.start_time
        )
        all_logs = list(prev_logs) + list(logs)

        by_student: Dict[int, Dict[int, List[float]]] = defaultdict(
            lambda: defaultdict(list)
        )
        for log in all_logs:
            by_student[log.user_id][log.session_id].append(log.engagement_score)

        identifier = RiskIdentifier()
        entries: List[AtRiskEntry] = []
        for user_id, sessions_scores in by_student.items():
            scores: List[float] = []
            dates: List[datetime] = []
            for session in ordered_sessions:
                session_scores = sessions_scores.get(session.id)
                if not session_scores:
                    continue
                scores.append(sum(session_scores) / len(session_scores))
                dates.append(session.start_time)
            if not scores:
                continue

            evaluation: RiskEvaluation = identifier.evaluate(
                student_id=str(user_id), session_scores=scores, session_dates=dates
            )
            if evaluation.at_risk:
                entries.append(
                    AtRiskEntry(
                        student_id=evaluation.student_id,
                        average_score=evaluation.average_score,
                        reasons=[r.message for r in evaluation.reasons],
                    )
                )

        entries.sort(key=lambda e: (e.average_score is None, e.average_score))

        total_students = len({log.user_id for log in logs}) or len(by_student)
        return AtRiskSummary(
            count=len(entries), total_students=total_students, entries=entries
        )

    # ---- difficult segments (ranked across all lectures) -------------------

    def _difficult_segments(
        self,
        sessions: List[SessionModel],
        logs_by_session: Dict[int, List[EngagementLog]],
    ) -> List[DifficultSegmentEntry]:
        correlator = DifficultyCorrelator()
        dip_sources: Dict[int, List[Tuple[SessionModel, float]]] = defaultdict(list)

        for session in sessions:
            timeline = self._session_timeline(
                session, logs_by_session.get(session.id, [])
            )
            if not timeline:
                continue
            correlator.add_session(session.id, timeline)
            for dip in self.aggregator.detect_dips(timeline, threshold=DIP_THRESHOLD):
                drop = (
                    (dip.session_avg - dip.class_avg) / dip.session_avg
                    if dip.session_avg
                    else 0.0
                )
                dip_sources[dip.minute].append((session, drop))

        segments: List[DifficultySegment] = correlator.find_difficult_segments(
            min_sessions=MIN_SESSIONS_FOR_DIFFICULT_SEGMENT, threshold=DIP_THRESHOLD
        )[:TOP_DIFFICULT_SEGMENTS]

        entries: List[DifficultSegmentEntry] = []
        for rank, segment in enumerate(segments, start=1):
            candidates = dip_sources.get(segment.minute, [])
            if candidates:
                worst_session, _ = max(candidates, key=lambda c: c[1])
                title, session_id = worst_session.title, worst_session.id
            else:
                title, session_id = "Unknown lecture", -1
            entries.append(
                DifficultSegmentEntry(
                    rank=rank,
                    lecture_title=title,
                    session_id=session_id,
                    minute=segment.minute,
                    avg_drop_pct=round(segment.avg_drop * 100, 1),
                    session_count=segment.session_count,
                    severity=round(segment.severity, 3),
                )
            )
        return entries

    # ---- ISO week validation ------------------------------------------------

    @staticmethod
    def _parse_iso_week(iso_week: str) -> Tuple[datetime, datetime]:
        try:
            week_start = datetime.strptime(f"{iso_week}-1", "%G-W%V-%u")
        except ValueError as exc:
            raise ValueError(f"Invalid ISO week '{iso_week}': {exc}") from exc
        return week_start, week_start + timedelta(days=7)

    # ---- rendering ----------------------------------------------------------

    def render_html(self, report: WeeklyReportData) -> str:
        template = self._jinja_env.get_template(TEMPLATE_NAME)
        data = report.to_json_safe_dict()
        return template.render(
            report=data,
            lecture_curves_svg=_lecture_curves_svg(report.lecture_curves),
            day_pattern_svg=_bar_chart_svg(
                labels=[d.day_name[:3] for d in report.day_pattern],
                values=[round(d.average * 100, 1) for d in report.day_pattern],
            ),
            time_pattern_svg=_bar_chart_svg(
                labels=[t.period for t in report.time_pattern],
                values=[round(t.average * 100, 1) for t in report.time_pattern],
            ),
        )

    def render_pdf(self, report: WeeklyReportData) -> bytes:
        from weasyprint import HTML  # noqa: WPS433

        html = self.render_html(report)
        return HTML(string=html, base_url=str(TEMPLATE_DIR)).write_pdf()

    # ---- persistence ---------------------------------------------------

    def save_report(self, report: WeeklyReportData) -> Report:
        row = Report(
            session_id=None,
            user_id=None,
            report_type="weekly_summary",
            content_json=report.to_json_safe_dict(),
        )
        try:
            self.db.add(row)
            self.db.commit()
            self.db.refresh(row)
            return row
        except Exception:
            self.db.rollback()
            raise

    # ---- convenience -----------------------------------------------------

    def generate_and_render(self, course_id: int, iso_week: str) -> str:
        report = self.generate(course_id, iso_week)
        return self.render_html(report)


# --------------------------------------------------------------------------
# Server-side SVG chart builders (PDF-safe: no JS execution required)
# --------------------------------------------------------------------------

_CHART_WIDTH = 640
_CHART_HEIGHT = 220
_CHART_PAD_LEFT = 36
_CHART_PAD_BOTTOM = 24
_CHART_PAD_TOP = 12
_CHART_PAD_RIGHT = 12
_LINE_COLORS = ["#3b82f6", "#f97316", "#22c55e", "#a855f7", "#ef4444", "#0ea5e9"]


def _chart_frame(width: int, height: int) -> str:
    x0, y0 = _CHART_PAD_LEFT, height - _CHART_PAD_BOTTOM
    x1, y1 = width - _CHART_PAD_RIGHT, _CHART_PAD_TOP
    lines = [
        f'<line x1="{x0}" y1="{y0}" x2="{x1}" y2="{y0}" stroke="#e2e8f0" stroke-width="1"/>'
    ]
    for pct in (0, 50, 100):
        y = y0 - (y0 - y1) * (pct / 100)
        grid_line = (
            f'<line x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}" '
            f'stroke="#f1f5f9" stroke-width="1"/>'
        )
        grid_label = (
            f'<text x="4" y="{y + 4:.1f}" font-size="10" fill="#94a3b8">{pct}</text>'
        )
        lines.append(grid_line + grid_label)
    return "".join(lines)


def _lecture_curves_svg(lecture_curves: List[LectureCurve]) -> str:
    plottable = [c for c in lecture_curves if c.has_data and c.timeline]
    if not plottable:
        return ""

    width, height = _CHART_WIDTH, _CHART_HEIGHT
    x0, y0 = _CHART_PAD_LEFT, height - _CHART_PAD_BOTTOM
    x1, y1 = width - _CHART_PAD_RIGHT, _CHART_PAD_TOP
    max_minute = max(max(c.timeline.keys()) for c in plottable) or 1

    def coords(minute: int, value: float) -> Tuple[float, float]:
        x = x0 + (x1 - x0) * (minute / max_minute)
        y = y0 - (y0 - y1) * min(max(value, 0.0), 1.0)
        return x, y

    parts = [
        '<svg viewBox="0 0 %d %d" xmlns="http://www.w3.org/2000/svg" font-family="sans-serif">'
        % (width, height)
    ]
    parts.append(_chart_frame(width, height))

    legend_x = x0
    for idx, curve in enumerate(plottable):
        color = _LINE_COLORS[idx % len(_LINE_COLORS)]
        points = " ".join(
            f"{x:.1f},{y:.1f}"
            for x, y in (coords(m, v) for m, v in sorted(curve.timeline.items()))
        )
        parts.append(
            f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2"/>'
        )
        label = curve.title if len(curve.title) <= 18 else curve.title[:16] + "\u2026"
        legend_dot = (
            f'<circle cx="{legend_x + 5}" cy="{height - 6}" r="4" fill="{color}"/>'
        )
        legend_text = (
            f'<text x="{legend_x + 13}" y="{height - 2}" font-size="10" '
            f'fill="#475569">{label}</text>'
        )
        parts.append(legend_dot + legend_text)
        legend_x += 24 + len(label) * 6

    parts.append("</svg>")
    return "".join(parts)


def _bar_chart_svg(labels: List[str], values: List[float]) -> str:
    if not labels:
        return ""

    width, height = _CHART_WIDTH, _CHART_HEIGHT
    x0, y0 = _CHART_PAD_LEFT, height - _CHART_PAD_BOTTOM
    x1, y1 = width - _CHART_PAD_RIGHT, _CHART_PAD_TOP
    plot_width = x1 - x0
    n = len(labels)
    slot_width = plot_width / n
    bar_width = slot_width * 0.55

    parts = [
        '<svg viewBox="0 0 %d %d" xmlns="http://www.w3.org/2000/svg" font-family="sans-serif">'
        % (width, height)
    ]
    parts.append(_chart_frame(width, height))

    for i, (label, value) in enumerate(zip(labels, values)):
        slot_x = x0 + i * slot_width
        bar_x = slot_x + (slot_width - bar_width) / 2
        bar_height = (y0 - y1) * (min(max(value, 0.0), 100.0) / 100.0)
        bar_y = y0 - bar_height
        color = "#94a3b8" if value == 0 else "#3b82f6"
        parts.append(
            f'<rect x="{bar_x:.1f}" y="{bar_y:.1f}" width="{bar_width:.1f}" '
            f'height="{bar_height:.1f}" fill="{color}" rx="3"/>'
            f'<text x="{slot_x + slot_width / 2:.1f}" y="{y0 + 14}" font-size="10" '
            f'text-anchor="middle" fill="#475569">{label}</text>'
        )

    parts.append("</svg>")
    return "".join(parts)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _main() -> None:
    parser = argparse.ArgumentParser(description="Generate a weekly engagement report.")
    parser.add_argument("--course-id", type=int, required=True)
    parser.add_argument("--week", required=True, help="ISO week, e.g. 2026-W24")
    parser.add_argument("--output", default="weekly.html")
    parser.add_argument(
        "--pdf", action="store_true", help="Also write a .pdf next to --output."
    )
    parser.add_argument("--save", action="store_true", help="Persist as a Report row.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    from src.config.database import SessionLocal

    db = SessionLocal()
    try:
        generator = WeeklyReportGenerator(db)
        report = generator.generate(args.course_id, args.week)
        html = generator.render_html(report)

        output_path = Path(args.output)
        output_path.write_text(html, encoding="utf-8")
        print(
            f"Report written to {output_path} (course_id={args.course_id}, week={args.week})"
        )

        if args.pdf:
            pdf_bytes = generator.render_pdf(report)
            pdf_path = output_path.with_suffix(".pdf")
            pdf_path.write_bytes(pdf_bytes)
            print(f"PDF written to {pdf_path}")

        if args.save:
            row = generator.save_report(report)
            print(f"Saved Report id={row.id} (report_type={row.report_type})")
    finally:
        db.close()


if __name__ == "__main__":
    _main()