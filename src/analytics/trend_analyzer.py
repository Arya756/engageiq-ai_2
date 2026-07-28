"""
TrendAnalyzer — Issue #25

Pure, framework-agnostic helpers for rolling averages and week-over-week
trend comparison. Deliberately has no database or FastAPI dependency: it
operates on plain scores (and optionally timestamps) so it can be reused
by `RiskIdentifier` here, by the teacher dashboard (#33), the intervention
agent (#29), and the weekly report (#28) alike, without any of them
needing to construct SQLAlchemy sessions just to compute an average.

Anywhere a caller has real per-session timestamps (e.g. from the existing
`EngagementLog` model), they can build `ScoredSession` objects and get the
7-day / 30-day rolling windows and week-over-week comparison used by the
acceptance criteria. Anywhere a caller only has an ordered list of scores
(no timestamps), the plain list-based helpers still work as an
*approximation* — see `split_first_second_half` for the caveat.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, NamedTuple, Optional, Sequence, Tuple

# Engagement scores are assumed to sit on a 0-100 scale, matching the rest
# of the scoring pipeline (e.g. EngagementLog). If the real scale differs,
# update these two constants rather than the validation logic below.
SCORE_MIN = 0.0
SCORE_MAX = 100.0


@dataclass(frozen=True)
class ScoredSession:
    """A single engagement score with the timestamp it was recorded at.

    Intentionally minimal and independent of the `EngagementLog` model —
    callers map their own rows into this before handing them to
    `TrendAnalyzer`, e.g.:

        sessions = [
            ScoredSession(score=log.engagement_score, timestamp=log.created_at)
            for log in engagement_logs
        ]

    Multiple sessions sharing the exact same timestamp are allowed (e.g.
    two engagement events logged in the same second) — each is counted
    individually in every average below. If the real data model guarantees
    unique timestamps per student, that's enforced upstream, not here.
    """

    score: float
    timestamp: datetime

    def __post_init__(self) -> None:
        TrendAnalyzer.validate_scores([self.score])


class WeekOverWeekResult(NamedTuple):
    """Named, not positional, so callers can't accidentally swap the two
    averages when reading the result of `week_over_week()`. Still a real
    tuple under the hood (so `current, previous = week_over_week(...)`
    keeps working), just with named-attribute access on top for safety.
    """

    current_week_avg: Optional[float]
    previous_week_avg: Optional[float]


class TrendAnalyzer:
    """Rolling-average and week-over-week trend utilities."""

    @staticmethod
    def validate_scores(scores: Sequence[float]) -> None:
        """Shared range check used by every list-based helper below, and
        reusable by callers like `RiskIdentifier` that accept raw,
        un-validated scores directly (rather than going through
        `ScoredSession`, which validates on construction). Raises
        ValueError on the first out-of-range score instead of silently
        producing a wrong average.
        """
        for score in scores:
            if not (SCORE_MIN <= score <= SCORE_MAX):
                raise ValueError(
                    f"score {score} is outside the expected range [{SCORE_MIN}, {SCORE_MAX}]"
                )

    # -- Plain list-based helpers (no timestamps required) -----------------

    @staticmethod
    def rolling_average(scores: Sequence[float], window: int) -> Optional[float]:
        """Average of the most recent `window` scores only (the *latest*
        rolling average, not the full series of rolling averages — see
        `rolling_average_series` if a caller needs the average at every
        point in the history, e.g. for a sparkline on the dashboard).

        `scores` is assumed to be ordered oldest-first (chronological) and
        each score must fall within [SCORE_MIN, SCORE_MAX] (raises
        ValueError otherwise). Returns None if fewer than `window` scores
        are available yet — there isn't a meaningful rolling average until
        then.
        """
        if window <= 0:
            raise ValueError("window must be a positive integer")
        TrendAnalyzer.validate_scores(scores)
        if len(scores) < window:
            return None
        recent = scores[-window:]
        return sum(recent) / len(recent)

    @staticmethod
    def rolling_average_series(
        scores: Sequence[float], window: int
    ) -> List[Optional[float]]:
        """Rolling average ending at every index in `scores`, with leading
        `None` entries for the first `window - 1` positions where fewer
        than `window` scores have accumulated yet.

        Returns a list the same length as `scores`, where entry `i` is the
        average of `scores[max(0, i-window+1):i+1]`. Useful for anything
        that wants a trend line rather than just the latest value (e.g. a
        dashboard chart), without duplicating this windowing logic.
        Each score must fall within [SCORE_MIN, SCORE_MAX] (raises
        ValueError otherwise).
        """
        if window <= 0:
            raise ValueError("window must be a positive integer")
        TrendAnalyzer.validate_scores(scores)
        result: List[Optional[float]] = []
        for i in range(len(scores)):
            if i + 1 < window:
                result.append(None)
            else:
                chunk = scores[i + 1 - window : i + 1]
                result.append(sum(chunk) / len(chunk))
        return result

    @staticmethod
    def split_first_second_half(
        scores: Sequence[float],
    ) -> Tuple[List[float], List[float]]:
        """Split an ordered score list at the midpoint.

        APPROXIMATION ONLY. This is the declining-trend fallback used when
        no timestamps are available: the first half stands in for
        "previous week" and the second half for "current week." It does
        NOT represent real calendar weeks and should not be treated as
        equivalent to `week_over_week()`. Prefer passing real timestamps
        (via `ScoredSession` + `week_over_week`) whenever they exist —
        this fallback exists only so a caller with a bare list of scores
        and no dates can still get a directional signal. Each score must
        fall within [SCORE_MIN, SCORE_MAX] (raises ValueError otherwise).
        """
        TrendAnalyzer.validate_scores(scores)
        midpoint = len(scores) // 2
        return list(scores[:midpoint]), list(scores[midpoint:])

    @staticmethod
    def percent_decline(previous: float, current: float) -> float:
        """Percentage drop from `previous` to `current`. Positive means a
        decline; negative or zero means flat/improving.

        If `previous` is 0, this returns 0.0 rather than raising — a zero
        baseline makes "percent change" undefined, and in this codebase a
        genuine all-zero previous week is itself a low-engagement signal
        that `RiskIdentifier`'s threshold check already catches, so
        silently reporting "no decline" here rather than raising keeps
        that upstream check as the source of truth instead of throwing on
        an edge case the rest of the pipeline already handles.
        """
        if previous == 0:
            return 0.0
        return ((previous - current) / previous) * 100

    # -- Timestamp-based helpers (rolling 7-day / 30-day windows) ----------

    @staticmethod
    def _window_bounds(as_of: datetime, days: int) -> Tuple[datetime, datetime]:
        """Inclusive [start, end] bounds spanning exactly `days` calendar
        days and ending at `as_of`.

        `days=7` means [as_of - 6 days, as_of] — seven distinct calendar
        days total. (Using `as_of - timedelta(days=7)` as the start would
        include an eighth day, since both ends of the range are
        inclusive — that off-by-one is deliberately avoided here.)
        """
        if days <= 0:
            raise ValueError("days must be a positive integer")
        start = as_of - timedelta(days=days - 1)
        return start, as_of

    @classmethod
    def rolling_window(
        cls, sessions: Sequence[ScoredSession], as_of: datetime, days: int
    ) -> List[ScoredSession]:
        """Sessions falling within the trailing `days`-day window ending at
        (and including) `as_of`.

        `sessions` does not need to be pre-sorted — this method sorts a
        local copy by timestamp before filtering. That's a deliberate
        correctness-over-performance choice: this analytics module is used
        for periodic batch jobs (dashboard refreshes, weekly reports), not
        a request-per-millisecond hot path, so the small extra cost of
        sorting on every call is worth not silently producing wrong
        results if a caller's data isn't already ordered (e.g. a DB query
        without an explicit `ORDER BY`). If a future caller has a proven
        performance need and can *guarantee* chronological input, sorting
        here could be dropped in favor of documenting that requirement
        instead — this is a call worth revisiting if that changes.

        Multiple sessions with identical timestamps are all included.
        """
        start, end = cls._window_bounds(as_of, days)
        ordered = sorted(sessions, key=lambda s: s.timestamp)
        return [s for s in ordered if start <= s.timestamp <= end]

    @classmethod
    def rolling_window_average(
        cls, sessions: Sequence[ScoredSession], as_of: datetime, days: int
    ) -> Optional[float]:
        """Average score across the trailing `days`-day window. None if no
        sessions fall inside the window.
        """
        window = cls.rolling_window(sessions, as_of, days)
        if not window:
            return None
        return sum(s.score for s in window) / len(window)

    @classmethod
    def week_over_week(
        cls, sessions: Sequence[ScoredSession], as_of: datetime
    ) -> WeekOverWeekResult:
        """Compare the trailing 7-day window ending at `as_of` ("current
        week") against the 7-day window immediately before it ("previous
        week"), as two adjacent, non-overlapping windows.

        Returns a `WeekOverWeekResult(current_week_avg, previous_week_avg)`
        — access by name (`result.current_week_avg`) rather than by
        position wherever possible, to avoid ever swapping the two.
        """
        current_start, _current_end = cls._window_bounds(as_of, 7)
        current_week_avg = cls.rolling_window_average(sessions, as_of, 7)

        previous_end = current_start - timedelta(days=1)
        previous_week_avg = cls.rolling_window_average(sessions, previous_end, 7)

        return WeekOverWeekResult(
            current_week_avg=current_week_avg, previous_week_avg=previous_week_avg
        )
