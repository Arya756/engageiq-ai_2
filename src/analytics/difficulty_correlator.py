"""Map engagement dips to lecture segments to identify difficult topics."""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass

from src.analytics.class_aggregator import ClassAggregator


@dataclass
class DifficultySegment:
    """Represents a lecture segment that is consistently difficult."""

    minute: int
    avg_drop: float
    session_count: int
    severity: float


class DifficultyCorrelator:
    """Tracks engagement dips across multiple lecture sessions."""

    def __init__(self) -> None:
        self._sessions: dict[int, dict[int, float]] = {}

    def add_session(
        self,
        session_id: int,
        timeline: dict[int, float],
    ) -> None:
        """Store a session timeline."""
        self._sessions[session_id] = timeline

    def find_difficult_segments(
        self,
        min_sessions: int = 2,
        threshold: float = 0.15,
    ) -> list[DifficultySegment]:
        """Find lecture segments that consistently show engagement drops."""
        if min_sessions < 1:
            raise ValueError("min_sessions must be at least 1.")

        aggregator = ClassAggregator()

        minute_drops: dict[int, list[float]] = defaultdict(list)

        for timeline in self._sessions.values():
            if not timeline:
                continue

            dips = aggregator.detect_dips(
                timeline,
                threshold=threshold,
            )

            for dip in dips:
                drop = (dip.session_avg - dip.class_avg) / dip.session_avg
                minute_drops[dip.minute].append(drop)

        difficult_segments: list[DifficultySegment] = []

        for minute, drops in minute_drops.items():
            if len(drops) < min_sessions:
                continue

            avg_drop = statistics.mean(drops)
            severity = len(drops) * avg_drop

            difficult_segments.append(
                DifficultySegment(
                    minute=minute,
                    avg_drop=avg_drop,
                    session_count=len(drops),
                    severity=severity,
                )
            )

        difficult_segments.sort(
            key=lambda segment: segment.severity,
            reverse=True,
        )

        return difficult_segments
