"""Tests for difficulty correlator."""

import pytest

from src.analytics.difficulty_correlator import DifficultyCorrelator


def test_find_difficult_segments():
    """Detect common difficult lecture segments across sessions."""
    dc = DifficultyCorrelator()

    dc.add_session(
        session_id=1,
        timeline={
            10: 78,
            11: 80,
            12: 75,
            13: 72,
            14: 52,
            15: 48,
            16: 55,
        },
    )

    dc.add_session(
        session_id=2,
        timeline={
            10: 82,
            11: 79,
            12: 77,
            13: 70,
            14: 48,
            15: 45,
            16: 50,
        },
    )

    difficult = dc.find_difficult_segments(min_sessions=2)

    minutes = {segment.minute for segment in difficult}

    assert 14 in minutes
    assert 15 in minutes
    assert 16 in minutes


def test_min_sessions_filter():
    """Ignore segments that do not appear in enough sessions."""
    dc = DifficultyCorrelator()

    dc.add_session(
        1,
        {
            10: 80,
            11: 80,
            12: 80,
            13: 40,
        },
    )

    dc.add_session(
        2,
        {
            10: 80,
            11: 80,
            12: 80,
            13: 80,
        },
    )

    difficult = dc.find_difficult_segments(min_sessions=2)

    assert difficult == []


def test_results_sorted_by_severity():
    """Return segments sorted by severity."""
    dc = DifficultyCorrelator()

    dc.add_session(
        1,
        {
            10: 80,
            11: 80,
            12: 40,
            13: 20,
        },
    )

    dc.add_session(
        2,
        {
            10: 80,
            11: 80,
            12: 45,
            13: 15,
        },
    )

    difficult = dc.find_difficult_segments()

    severities = [segment.severity for segment in difficult]

    assert severities == sorted(severities, reverse=True)


def test_empty_sessions():
    """Return an empty list when no sessions are available."""
    dc = DifficultyCorrelator()

    assert dc.find_difficult_segments() == []


def test_invalid_min_sessions():
    """Reject invalid min_sessions values."""
    dc = DifficultyCorrelator()

    with pytest.raises(ValueError):
        dc.find_difficult_segments(min_sessions=0)
