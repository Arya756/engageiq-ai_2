"""Aggregate student engagement into class-level metrics."""

from __future__ import annotations

import statistics
from dataclasses import dataclass


@dataclass
class ClassStats:
    """Aggregated statistics for a single snapshot of class engagement.

    All student IDs are anonymized before this object is produced.
    """

    average: float
    median: float
    std_dev: float
    min_score: float
    max_score: float
    engaged_pct: float  # fraction (0.0–1.0) of students scoring > 70
    student_count: int  # number of students included (disconnected excluded)


@dataclass
class TimelineEntry:
    """Class engagement snapshot for a single minute of the session."""

    minute: int
    average: float
    student_count: int  # excludes disconnected and non-numeric entries


@dataclass
class EngagementDip:
    """Represents a single detected engagement dip in the session timeline."""

    minute: int
    class_avg: float  # class average at this minute
    session_avg: float  # overall session average used as baseline


class ClassAggregator:
    """Computes class-wide engagement metrics and detects engagement dips.

    Workflow:
        agg = ClassAggregator()

        # Feed per-minute student scores to build the timeline
        agg.update_timeline(10, [80, 75, 90, None])
        agg.update_timeline(11, [None, None])         # wifi outage — skipped
        agg.update_timeline(12, [78, 70, 88, 60])

        # Retrieve the full timeline (outage minutes excluded)
        timeline = agg.get_timeline()   # {10: 81.67, 12: 74.0}

        # Detect dips in the timeline
        dips = agg.detect_dips(timeline, threshold=0.15)

        # Aggregate a one-off score snapshot
        stats = agg.aggregate([80, 70, 90, 60, 85])
    """

    ENGAGED_THRESHOLD: float = 70.0  # score above which a student is "engaged"

    def __init__(self) -> None:
        # Internal minute-by-minute store populated by update_timeline().
        # Only minutes with at least one connected student are stored here.
        self._timeline: dict[int, float] = {}

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _to_float(value: object) -> float | None:
        """Safely convert a value to float.

        Returns None for:
          - None (disconnected student)
          - bool values (True/False) — bool is a subclass of int in Python,
            so float(True)==1.0 and float(False)==0.0. No engagement pipeline
            value should ever be a bool, so treat it as junk rather than
            silently scoring it as 1.0 or 0.0.
          - Any non-numeric type (strings like "N/A", dicts, etc.)

        Args:
            value: Any value from the scores list.

        Returns:
            Float representation, or None if conversion is not possible.
        """
        if value is None:
            return None
        # bool must be checked BEFORE int because bool is a subclass of int.
        # Without this guard, True → 1.0 and float(False) → 0.0 silently.
        if isinstance(value, bool):
            return None
        try:
            return float(value)  # type: ignore[arg-type]
        except (ValueError, TypeError):
            return None

    # ── Snapshot aggregation ──────────────────────────────────────────────────

    def aggregate(self, scores: list) -> ClassStats:
        """Compute class-level engagement statistics from a list of student scores.

        None values (disconnected students), bool values, and non-numeric junk
        (e.g. "N/A", "error") are silently skipped. If no valid scores remain,
        returns a zero-value ClassStats.

        Args:
            scores: List of raw engagement scores (0–100). None, bool, or
                    non-numeric values are excluded gracefully.

        Returns:
            ClassStats with mean, median, std_dev, min, max, engaged_pct, count.
        """
        valid: list[float] = [f for s in scores if (f := self._to_float(s)) is not None]

        if not valid:
            return ClassStats(
                average=0.0,
                median=0.0,
                std_dev=0.0,
                min_score=0.0,
                max_score=0.0,
                engaged_pct=0.0,
                student_count=0,
            )

        avg = statistics.mean(valid)
        med = statistics.median(valid)
        std = statistics.pstdev(valid)  # population std dev
        min_s = min(valid)
        max_s = max(valid)
        engaged = sum(1 for s in valid if s > self.ENGAGED_THRESHOLD)
        engaged_pct = engaged / len(valid)

        return ClassStats(
            average=avg,
            median=med,
            std_dev=std,
            min_score=min_s,
            max_score=max_s,
            engaged_pct=engaged_pct,
            student_count=len(valid),
        )

    # ── Minute-by-minute timeline ─────────────────────────────────────────────

    def update_timeline(
        self,
        minute: int,
        scores: list,
    ) -> TimelineEntry:
        """Record the class average for a given minute (real-time capable).

        Call this once per minute with current scores from all students.
        None, bool, and non-numeric junk values are silently excluded.

        IMPORTANT: Minutes where ALL students are disconnected or invalid
        are NOT stored in the internal timeline. Storing 0.0 for such
        minutes would:
          1. Show a fake engagement dip on the teacher dashboard.
          2. Corrupt the session average used by detect_dips(), masking
             or distorting real dip detection at other minutes.

        Args:
            minute: The session minute number (e.g. 14 for minute 14).
            scores: List of raw engagement scores. None, bool, or non-numeric
                    values are excluded gracefully.

        Returns:
            TimelineEntry for this minute. student_count will be 0 if all
            entries were invalid, and the minute will not appear in
            get_timeline().
        """
        valid: list[float] = [f for s in scores if (f := self._to_float(s)) is not None]
        avg = statistics.mean(valid) if valid else 0.0

        # Only persist minutes with real data to avoid corrupting the timeline
        if valid:
            self._timeline[minute] = avg

        return TimelineEntry(minute=minute, average=avg, student_count=len(valid))

    def get_timeline(self) -> dict[int, float]:
        """Return the full minute-by-minute timeline built via update_timeline().

        Fully-disconnected and all-invalid minutes are not included
        (see update_timeline docs).

        Returns:
            Dict mapping {minute: class_average_score}, sorted by minute.
        """
        return dict(sorted(self._timeline.items()))

    def reset_timeline(self) -> None:
        """Clear the internal timeline (call at the start of a new session)."""
        self._timeline.clear()

    # ── Dip detection ─────────────────────────────────────────────────────────

    def detect_dips(
        self,
        timeline: dict[int, float],
        threshold: float = 0.15,
    ) -> list[EngagementDip]:
        """Detect minutes where class engagement dips below the session average.

        A dip is detected when the class average at a given minute drops more
        than `threshold` below the overall session average.

        Args:
            timeline: Mapping of {minute: class_average_score}. Use
                      get_timeline() to pass the internally built one.
            threshold: Fractional drop from session average required to count
                       as a dip. Must be in the range (0.0, 1.0] — exclusive
                       of 0.0, inclusive of 1.0.
                         - 0.0 is rejected: it would flag every minute below
                           the session average as a dip, which is meaningless.
                         - 1.0 is allowed: flags only minutes that dropped to
                           near zero — an extreme but valid sentinel.
                         - Passing 15 instead of 0.15 raises ValueError to
                           prevent the silent "no dips ever" failure.
                       Default is 0.15 (15%).

        Returns:
            List of EngagementDip in ascending minute order.

        Raises:
            ValueError: If threshold is not in the range (0.0, 1.0].
        """
        if not (0.0 < threshold <= 1.0):
            raise ValueError(
                f"threshold must be a fraction in the range (0.0, 1.0] "
                f"(e.g. 0.15 for 15%). Got {threshold!r}. "
                f"Did you mean {threshold / 100:.4f}?"
            )

        if not timeline:
            return []

        session_avg = statistics.mean(timeline.values())

        dips: list[EngagementDip] = []
        for minute in sorted(timeline.keys()):
            class_avg = timeline[minute]
            if session_avg > 0 and (session_avg - class_avg) / session_avg > threshold:
                dips.append(
                    EngagementDip(
                        minute=minute,
                        class_avg=class_avg,
                        session_avg=session_avg,
                    )
                )

        return dips
