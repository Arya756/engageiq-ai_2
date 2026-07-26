"""Nudge effectiveness tracker.

Sending nudges without measuring their impact is like prescribing medicine
without checking if the patient gets better. This module closes that
feedback loop: after every nudge, it measures whether the student's
engagement score actually improved in the minutes that followed, tracks a
per-nudge-type success rate, and hands that back to the decision agent
(`src/nudge/nudge_decision.py`) so it can learn which nudge types work
best -- per student, over time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

# Default "effective" threshold and measurement window, per the issue's own
# acceptance criteria. Both are also constructor parameters (matching the
# issue's own test snippet, e.g. `EffectivenessTracker(measurement_window=60)`),
# so nothing here needs touching settings.py to be tunable.
DEFAULT_MEASUREMENT_WINDOW_SECONDS = 60
DEFAULT_EFFECTIVE_THRESHOLD = 10.0


@dataclass
class EffectivenessResult:
    """Outcome of evaluating a single nudge."""

    nudge_type: str
    pre_score: float
    post_score_avg: float
    delta: float
    effective: bool
    sample_count: int
    timestamp: float  # the nudge's own timestamp, for ordering/persistence


@dataclass
class NudgeTypeStats:
    """Aggregated effectiveness for one nudge type."""

    nudge_type: str
    attempts: int
    successes: int
    success_rate: float
    avg_delta: float


class EffectivenessTracker:
    """Measures engagement-score change after each nudge and tracks
    per-type success rate.

    Two ways to use it, both supported by the same instance:

    1. Pure, in-memory (no DB) -- exactly the workflow in the issue's own
       "how to test locally" snippet: `record_nudge`, one or more
       `record_post_score` calls, then `evaluate_last_nudge()`. This is
       fully self-contained and DB-free, so it's cheap to unit test and
       usable standalone by the decision agent within a single session.

    2. Persisted, per-student (pass `db` + `student_id`) -- reuses the
       *existing* `Nudge.effectiveness_delta` column (see
       `src/models/nudge.py`) rather than introducing a new table. When a
       `nudge_id` is supplied to `record_nudge`, `evaluate_last_nudge()`
       writes the computed delta back onto that row. `get_stats()` and
       `to_decision_history()` then read effectiveness across *every*
       past session for that student, not just the current one --
       satisfying "persists history per student across sessions" without
       a second, redundant datastore.
    """

    def __init__(
        self,
        measurement_window: int = DEFAULT_MEASUREMENT_WINDOW_SECONDS,
        effective_threshold: float = DEFAULT_EFFECTIVE_THRESHOLD,
        student_id: Optional[int] = None,
        db: Optional[Any] = None,
    ):
        """
        Args:
            measurement_window: seconds after a nudge during which
                post-nudge engagement scores are collected.
            effective_threshold: minimum average score improvement (in
                engagement-score points) for a nudge to count as
                "effective". Per acceptance criteria: 10+.
            student_id: if given along with `db`, effectiveness deltas are
                persisted to (and stats are read from) that student's
                `Nudge` rows in the database, across all their sessions.
            db: a SQLAlchemy `Session` (see `src.config.database.get_db`).
                Optional -- omit for the pure in-memory mode.
        """
        self.measurement_window = measurement_window
        self.effective_threshold = effective_threshold
        self.student_id = student_id
        self.db = db

        self._pending_nudge: Optional[Dict[str, Any]] = None
        self._score_samples: List[tuple] = []  # [(timestamp, score), ...]
        # This-process history, always kept (used directly when no db is
        # configured; merged with DB-persisted history otherwise).
        self._session_history: List[EffectivenessResult] = []

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------
    def record_nudge(
        self,
        nudge_type: str,
        timestamp: float,
        pre_score: float,
        nudge_id: Optional[int] = None,
    ) -> None:
        """Start tracking a newly-sent nudge.

        Args:
            nudge_type: e.g. "notification", "audio", "overlay", or
                whatever taxonomy the caller uses -- this module is
                agnostic to it, it just needs to be a stable string key.
            timestamp: seconds (session-relative or unix, as long as it's
                consistent with the timestamps passed to
                `record_post_score`).
            pre_score: engagement score immediately before the nudge.
            nudge_id: the persisted `Nudge` row's id, if using DB mode --
                required for `evaluate_last_nudge()` to write the delta
                back to that row.
        """
        self._pending_nudge = {
            "type": nudge_type,
            "timestamp": timestamp,
            "pre_score": pre_score,
            "nudge_id": nudge_id,
        }

    def record_post_score(self, timestamp: float, score: float) -> None:
        """Log an observed engagement score. Whether it counts toward the
        currently-pending nudge's evaluation depends only on whether its
        timestamp falls inside that nudge's measurement window -- decided
        at `evaluate_last_nudge()` time, not here."""
        self._score_samples.append((timestamp, score))

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------
    def evaluate_last_nudge(self) -> Optional[EffectivenessResult]:
        """Evaluate the most recently recorded (and not-yet-evaluated)
        nudge, using post-scores whose timestamps fall within
        `(nudge_timestamp, nudge_timestamp + measurement_window]`.

        Returns:
            The `EffectivenessResult`, or `None` if there's no pending
            nudge, or no post-nudge scores fell inside its window (can't
            evaluate what wasn't observed).
        """
        if self._pending_nudge is None:
            return None

        nudge = self._pending_nudge
        window_start = nudge["timestamp"]
        window_end = nudge["timestamp"] + self.measurement_window

        relevant_scores = [
            score
            for ts, score in self._score_samples
            if window_start < ts <= window_end
        ]
        if not relevant_scores:
            return None

        post_avg = sum(relevant_scores) / len(relevant_scores)
        delta = post_avg - nudge["pre_score"]
        effective = delta >= self.effective_threshold

        result = EffectivenessResult(
            nudge_type=nudge["type"],
            pre_score=nudge["pre_score"],
            post_score_avg=post_avg,
            delta=delta,
            effective=effective,
            sample_count=len(relevant_scores),
            timestamp=nudge["timestamp"],
        )
        self._session_history.append(result)

        if self.db is not None and nudge.get("nudge_id") is not None:
            self._persist_delta(nudge["nudge_id"], delta)

        self._pending_nudge = None
        return result

    def _persist_delta(self, nudge_id: int, delta: float) -> None:
        """Write the computed delta back onto the existing `Nudge` row,
        rather than maintaining a second, parallel history store."""
        from src.models.nudge import Nudge  # local import: DB-mode only

        nudge_row = self.db.get(Nudge, nudge_id)
        if nudge_row is not None:
            nudge_row.effectiveness_delta = delta
            self.db.commit()

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------
    def _all_results(self) -> List[EffectivenessResult]:
        """This-session results, plus DB-persisted results for the
        student across every other session, when DB mode is configured."""
        if self.db is None or self.student_id is None:
            return list(self._session_history)

        from src.models.nudge import Nudge  # local import: DB-mode only

        persisted = (
            self.db.query(Nudge)
            .filter(
                Nudge.user_id == self.student_id,
                Nudge.effectiveness_delta.isnot(None),
            )
            .all()
        )
        results = [
            EffectivenessResult(
                nudge_type=row.nudge_type,
                pre_score=float("nan"),  # not retained on the Nudge row
                post_score_avg=float("nan"),
                delta=row.effectiveness_delta,
                effective=row.effectiveness_delta >= self.effective_threshold,
                sample_count=1,
                timestamp=row.created_at.timestamp() if row.created_at else 0.0,
            )
            for row in persisted
        ]

        # Avoid double-counting: this-session results that already have a
        # nudge_id are the ones just persisted above and are already
        # included in `persisted`. Only fold in ones that were never
        # persisted (e.g. pure in-memory evaluations mixed into a DB-mode
        # tracker, an edge case but cheap to handle correctly).
        persisted_timestamps = {r.timestamp for r in results}
        for r in self._session_history:
            if r.timestamp not in persisted_timestamps:
                results.append(r)

        return results

    def get_stats(self) -> Dict[str, NudgeTypeStats]:
        """Per-nudge-type success rate and average delta, across all
        evaluated nudges (this session, plus DB-persisted history if
        configured)."""
        by_type: Dict[str, List[EffectivenessResult]] = {}
        for result in self._all_results():
            by_type.setdefault(result.nudge_type, []).append(result)

        stats: Dict[str, NudgeTypeStats] = {}
        for nudge_type, results in by_type.items():
            attempts = len(results)
            successes = sum(1 for r in results if r.effective)
            deltas = [r.delta for r in results]
            stats[nudge_type] = NudgeTypeStats(
                nudge_type=nudge_type,
                attempts=attempts,
                successes=successes,
                success_rate=successes / attempts if attempts else 0.0,
                avg_delta=sum(deltas) / len(deltas) if deltas else 0.0,
            )
        return stats

    # ------------------------------------------------------------------
    # Decision-agent integration
    # ------------------------------------------------------------------
    def to_decision_history(self) -> List[Dict[str, Any]]:
        """Effectiveness history in exactly the shape
        `NudgeDecisionEngine.should_nudge()` expects for its
        `effectiveness_history` argument (see `src/nudge/nudge_decision.py`
        and `src/agents/nudge_agent.py`'s `AgentState.effectiveness_history`):

            [{"type": "notification", "success": True}, ...]

        This is the "feeds results back to the decision agent" piece --
        callers pass this list straight into
        `NudgeDecisionEngine.should_nudge(effectiveness_history=...)`.
        """
        return [
            {"type": result.nudge_type, "success": result.effective}
            for result in self._all_results()
        ]


if __name__ == "__main__":
    # Matches the issue's own "how to test locally" snippet, runnable
    # directly: python -m src.nudge.effectiveness_tracker
    tracker = EffectivenessTracker(measurement_window=60)

    tracker.record_nudge(nudge_type="notification", timestamp=0, pre_score=35)
    tracker.record_post_score(timestamp=30, score=55)
    tracker.record_post_score(timestamp=60, score=65)
    result = tracker.evaluate_last_nudge()
    print(f"Notification: effective={result.effective}, delta={result.delta:+.1f}")

    tracker.record_nudge(nudge_type="audio", timestamp=120, pre_score=30)
    tracker.record_post_score(timestamp=150, score=32)
    result = tracker.evaluate_last_nudge()
    print(f"Audio: effective={result.effective}, delta={result.delta:+.1f}")

    stats = tracker.get_stats()
    print(f"Notification rate: {stats['notification'].success_rate:.0%}")
