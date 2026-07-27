"""
RiskIdentifier — Issue #25

Flags students whose engagement is consistently low or trending downward
across multiple sessions, so a teacher can intervene before a single bad
session becomes a pattern.

Two independent signals feed `at_risk`:

    1. Consistently low: each of the last `consecutive_sessions` sessions,
       individually, scored below `threshold`. (Not a rolling *average*
       below threshold — a single strong session in that window means the
       student is not flagged on this signal. See the note on
       `_check_consistently_low` below for why this reading of the
       acceptance criteria was chosen.)
    2. Declining trend: the current week's average is more than
       `decline_threshold_pct` percent below the previous week's average
       (using real 7-day windows if timestamps are supplied, or a
       first-half/second-half split of the given scores otherwise — see
       `TrendAnalyzer.split_first_second_half` for why that fallback is
       only an approximation).

Either signal alone is enough to flag a student — a clear downward trend
is worth a teacher's attention even before the raw average crosses the
threshold, per the feature's own motivation ("80 to 70 to 60 ... heading
there").

This module is deliberately pure/framework-agnostic (no SQLAlchemy, no
FastAPI) so it's easy to unit test and easy for #33 (dashboard), #29
(intervention agent), and #28 (weekly report) to reuse directly. A thin
DB-facing wrapper (pulling scores out of the existing `EngagementLog`
model via `get_db()`) can sit in front of this later — e.g.
`identify_at_risk_students(db: Session) -> list[RiskEvaluation]` — without
this class needing to change.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from enum import Enum
from typing import List, Optional, Sequence, Tuple

from pydantic import BaseModel, Field

from src.analytics.trend_analyzer import (
    SCORE_MAX,
    SCORE_MIN,
    ScoredSession,
    TrendAnalyzer,
)

DEFAULT_THRESHOLD = 50.0
DEFAULT_CONSECUTIVE_SESSIONS = 3
DEFAULT_DECLINE_THRESHOLD_PCT = 10.0


class RiskReasonCode(str, Enum):
    """Machine-readable reason codes, so downstream consumers (dashboard,
    intervention agent) can filter/branch on `code` instead of pattern
    matching human-readable strings.
    """

    CONSECUTIVE_LOW = "CONSECUTIVE_LOW"
    DECLINING_TREND = "DECLINING_TREND"


class RiskReason(BaseModel):
    code: RiskReasonCode
    message: str


class RiskEvaluation(BaseModel):
    """Result of evaluating one student. `student_id` is anonymized unless
    the student has opted in to being identified for targeted help.
    """

    student_id: str
    at_risk: bool
    declining_trend: bool
    reasons: List[RiskReason] = Field(default_factory=list)
    average_score: Optional[float] = None
    consecutive_low_sessions: int = 0
    rolling_consecutive_avg: Optional[float] = None
    rolling_7day_avg: Optional[float] = None
    rolling_30day_avg: Optional[float] = None


class RiskIdentifier:
    """Evaluates a single student's session scores against the low/declining
    engagement criteria above.
    """

    def __init__(
        self,
        threshold: float = DEFAULT_THRESHOLD,
        consecutive_sessions: int = DEFAULT_CONSECUTIVE_SESSIONS,
        decline_threshold_pct: float = DEFAULT_DECLINE_THRESHOLD_PCT,
    ):
        if threshold < SCORE_MIN:
            raise ValueError(f"threshold must be >= {SCORE_MIN}")
        if threshold > SCORE_MAX:
            raise ValueError(
                f"threshold must be <= {SCORE_MAX} (the max possible score)"
            )
        if consecutive_sessions < 1:
            raise ValueError("consecutive_sessions must be >= 1")
        if decline_threshold_pct <= 0:
            raise ValueError("decline_threshold_pct must be > 0")
        if decline_threshold_pct > 100:
            # Scores live on a [SCORE_MIN, SCORE_MAX] scale, so a week-over-week
            # drop can never exceed 100% of the previous average -- a
            # threshold above that could never trigger and almost certainly
            # indicates a mistake (e.g. confusing a percentage with points).
            raise ValueError("decline_threshold_pct must be <= 100")

        self.threshold = threshold
        self.consecutive_sessions = consecutive_sessions
        self.decline_threshold_pct = decline_threshold_pct

    def evaluate(
        self,
        student_id: str,
        session_scores: Sequence[float],
        session_dates: Optional[Sequence[datetime]] = None,
        opted_in: bool = False,
    ) -> RiskEvaluation:
        """Evaluate one student's engagement pattern.

        `session_scores` must be ordered oldest-first (chronological) and
        each score must fall within [SCORE_MIN, SCORE_MAX] -- both are
        validated up front and raise ValueError if violated.
        `session_dates`, if given, must be the same length as
        `session_scores`, also chronologically ordered (oldest first), and
        lets rolling 7-day/30-day windows and a real week-over-week
        comparison be computed instead of the no-timestamp fallback (a
        first-half/second-half split).
        `opted_in` controls whether the real `student_id` is returned or a
        stable anonymized id — see `_resolve_id`. Anonymized is the
        default, matching the "at-risk list uses anonymized IDs" criterion.
        """
        anon_id = self._resolve_id(student_id, opted_in)

        if not session_scores:
            return RiskEvaluation(
                student_id=anon_id,
                at_risk=False,
                declining_trend=False,
                reasons=[],
                average_score=None,
                consecutive_low_sessions=0,
                rolling_consecutive_avg=None,
                rolling_7day_avg=None,
                rolling_30day_avg=None,
            )

        TrendAnalyzer.validate_scores(session_scores)
        self._validate_dates(session_scores, session_dates)

        reasons: List[RiskReason] = []

        is_low, rolling_consecutive_avg = self._check_consistently_low(session_scores)
        if is_low:
            reasons.append(self._consecutive_low_reason(rolling_consecutive_avg))

        consecutive_low_sessions = self._trailing_low_streak(session_scores)

        (
            declining_trend,
            previous_avg,
            current_avg,
            rolling_7day_avg,
            rolling_30day_avg,
        ) = self._check_declining_trend(session_scores, session_dates)
        if declining_trend:
            reasons.append(self._declining_trend_reason(previous_avg, current_avg))

        return RiskEvaluation(
            student_id=anon_id,
            at_risk=is_low or declining_trend,
            declining_trend=declining_trend,
            reasons=reasons,
            average_score=sum(session_scores) / len(session_scores),
            consecutive_low_sessions=consecutive_low_sessions,
            rolling_consecutive_avg=rolling_consecutive_avg,
            rolling_7day_avg=rolling_7day_avg,
            rolling_30day_avg=rolling_30day_avg,
        )

    # -- Signal 1: consistently low -----------------------------------------

    def _check_consistently_low(
        self, session_scores: Sequence[float]
    ) -> Tuple[bool, Optional[float]]:
        """ "Consistently low" is read here as: each of the last
        `consecutive_sessions` sessions, individually, scored below
        `threshold` — not a rolling *average* below threshold. E.g. with
        threshold=50 and consecutive_sessions=3, scores [40, 40, 60] are
        NOT flagged on this signal, because the most recent session (60)
        is above threshold, even though the 3-session average (46.7) is
        below it. If the project intends the average-based reading
        instead, swap the `all(...)` check below for
        `TrendAnalyzer.rolling_average(...) < threshold`.

        The rolling average is still computed and returned alongside the
        boolean (as `rolling_consecutive_avg`) purely for display/
        debugging — it does not drive `at_risk` under this reading.
        """
        rolling_avg = TrendAnalyzer.rolling_average(
            session_scores, self.consecutive_sessions
        )

        if len(session_scores) < self.consecutive_sessions:
            return False, rolling_avg

        recent = session_scores[-self.consecutive_sessions :]
        is_low = all(score < self.threshold for score in recent)
        return is_low, rolling_avg

    def _consecutive_low_reason(
        self, rolling_consecutive_avg: Optional[float]
    ) -> RiskReason:
        avg_str = (
            f"{rolling_consecutive_avg:.1f}"
            if rolling_consecutive_avg is not None
            else "n/a"
        )
        return RiskReason(
            code=RiskReasonCode.CONSECUTIVE_LOW,
            message=(
                f"last {self.consecutive_sessions} sessions were each below "
                f"threshold ({self.threshold}); rolling average {avg_str}"
            ),
        )

    def _trailing_low_streak(self, session_scores: Sequence[float]) -> int:
        """Count how many of the most recent sessions, in a row, were
        individually below threshold. Informational only.
        """
        streak = 0
        for score in reversed(session_scores):
            if score < self.threshold:
                streak += 1
            else:
                break
        return streak

    # -- Signal 2: declining trend -------------------------------------------

    def _check_declining_trend(
        self,
        session_scores: Sequence[float],
        session_dates: Optional[Sequence[datetime]],
    ) -> Tuple[
        bool, Optional[float], Optional[float], Optional[float], Optional[float]
    ]:
        """Returns (declining, previous_avg, current_avg, rolling_7day_avg,
        rolling_30day_avg). The last two are only populated when
        `session_dates` is provided.
        """
        if session_dates:
            sessions = [
                ScoredSession(score=score, timestamp=date)
                for score, date in zip(session_scores, session_dates)
            ]
            as_of = max(session_dates)
            rolling_7day_avg = TrendAnalyzer.rolling_window_average(sessions, as_of, 7)
            rolling_30day_avg = TrendAnalyzer.rolling_window_average(
                sessions, as_of, 30
            )
            week = TrendAnalyzer.week_over_week(sessions, as_of)
            current_avg, previous_avg = week.current_week_avg, week.previous_week_avg
        else:
            # APPROXIMATION: no timestamps available, so we fall back to a
            # first-half/second-half split rather than real calendar
            # weeks. See TrendAnalyzer.split_first_second_half for the
            # caveat. rolling_7day_avg/rolling_30day_avg are left as None
            # in this branch since there's no timestamp data to compute
            # them from.
            rolling_7day_avg = None
            rolling_30day_avg = None
            previous_half, current_half = TrendAnalyzer.split_first_second_half(
                session_scores
            )
            previous_avg = (
                sum(previous_half) / len(previous_half) if previous_half else None
            )
            current_avg = (
                sum(current_half) / len(current_half) if current_half else None
            )

        declining = self._is_declining(previous_avg, current_avg)
        return declining, previous_avg, current_avg, rolling_7day_avg, rolling_30day_avg

    def _is_declining(
        self, previous_avg: Optional[float], current_avg: Optional[float]
    ) -> bool:
        if previous_avg is None or current_avg is None or previous_avg == 0:
            return False
        pct_drop = TrendAnalyzer.percent_decline(previous_avg, current_avg)
        return pct_drop > self.decline_threshold_pct

    def _declining_trend_reason(
        self, previous_avg: Optional[float], current_avg: Optional[float]
    ) -> RiskReason:
        pct_drop = TrendAnalyzer.percent_decline(previous_avg, current_avg)
        return RiskReason(
            code=RiskReasonCode.DECLINING_TREND,
            message=(
                f"current avg ({current_avg:.1f}) is {pct_drop:.1f}% below "
                f"previous ({previous_avg:.1f})"
            ),
        )

    # -- Validation / anonymization ------------------------------------------

    @staticmethod
    def _validate_dates(
        session_scores: Sequence[float], session_dates: Optional[Sequence[datetime]]
    ) -> None:
        if session_dates is None:
            return
        if len(session_dates) != len(session_scores):
            raise ValueError("session_dates must be the same length as session_scores")
        for earlier, later in zip(session_dates, session_dates[1:]):
            if earlier > later:
                raise ValueError(
                    "session_dates must be in chronological order (oldest first), "
                    f"but {earlier!r} comes before {later!r}"
                )

    @staticmethod
    def _resolve_id(student_id: str, opted_in: bool) -> str:
        """Students are anonymized by default; only a student who has
        opted in to being identified for targeted help gets their real id
        surfaced here.

        NOTE: this hash is a lightweight placeholder. If the repo already
        has a shared anonymization utility (e.g. near `User.privacy_mode`),
        swap this out for that instead of keeping two schemes side by
        side — the important part is that opted-out students never appear
        with an identifiable id anywhere the result of `evaluate()` ends
        up (dashboard, reports, intervention agent).
        """
        if opted_in:
            return student_id
        if student_id.startswith("anon_"):
            return student_id
        digest = hashlib.sha256(student_id.encode("utf-8")).hexdigest()[:10]
        return f"anon_{digest}"
