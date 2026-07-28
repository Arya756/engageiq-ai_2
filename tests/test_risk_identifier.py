"""
Tests for src/analytics/risk_identifier.py and src/analytics/trend_analyzer.py
(Issue #25)

Pure unit tests -- neither module has a DB/FastAPI dependency, so nothing
here needs a session or event loop.
"""

from datetime import datetime, timedelta

import pytest

from src.analytics.risk_identifier import RiskIdentifier, RiskReasonCode
from src.analytics.trend_analyzer import ScoredSession, TrendAnalyzer

# ---------------------------------------------------------------------------
# RiskIdentifier — "consistently low" signal
# ---------------------------------------------------------------------------


def test_flags_three_consecutive_low_sessions():
    ri = RiskIdentifier(threshold=50, consecutive_sessions=3)

    result = ri.evaluate(student_id="anon_42", session_scores=[40, 35, 30])

    assert result.at_risk is True
    assert result.consecutive_low_sessions == 3
    assert any(r.code == RiskReasonCode.CONSECUTIVE_LOW for r in result.reasons)


def test_healthy_student_is_not_flagged():
    ri = RiskIdentifier(threshold=50, consecutive_sessions=3)

    # High and essentially flat -- no low streak, no meaningful decline.
    result = ri.evaluate(student_id="anon_10", session_scores=[90, 88, 85, 82])

    assert result.at_risk is False
    assert result.declining_trend is False
    assert result.reasons == []


def test_one_low_session_mixed_with_good_ones_is_not_consistently_low():
    """The key acceptance-criteria interpretation: "3+ consecutive
    sessions" below threshold means each of the last 3 sessions
    individually, not a 3-session rolling *average* below threshold. A
    single strong recent session should clear the flag even if the
    average of the last 3 is still under threshold.
    """
    ri = RiskIdentifier(threshold=50, consecutive_sessions=3)

    # Last 3 scores: 40, 40, 60 -> average 46.7 (< 50) but NOT every
    # individual session is below threshold, so this must not be flagged
    # as "consistently low."
    result = ri.evaluate(student_id="anon_9", session_scores=[40, 40, 60])

    assert result.rolling_consecutive_avg == pytest.approx(46.666666, rel=1e-4)
    assert not any(r.code == RiskReasonCode.CONSECUTIVE_LOW for r in result.reasons)


def test_only_most_recent_session_low_is_not_consistently_low():
    ri = RiskIdentifier(threshold=50, consecutive_sessions=3, decline_threshold_pct=90)

    # decline_threshold_pct=90 keeps the (approximate, no-timestamp)
    # declining-trend signal from also firing here, so this isolates the
    # "consistently low" signal specifically: only the most recent
    # session is below threshold, so it must not count as a 3-in-a-row streak.
    result = ri.evaluate(student_id="anon_11", session_scores=[90, 88, 85, 40])

    assert result.consecutive_low_sessions == 1
    assert not any(r.code == RiskReasonCode.CONSECUTIVE_LOW for r in result.reasons)
    assert result.at_risk is False


def test_fewer_sessions_than_window_cannot_be_flagged_as_consistently_low():
    ri = RiskIdentifier(threshold=50, consecutive_sessions=3)

    result = ri.evaluate(student_id="anon_2", session_scores=[10, 20])

    assert not any(r.code == RiskReasonCode.CONSECUTIVE_LOW for r in result.reasons)
    assert result.rolling_consecutive_avg is None


# ---------------------------------------------------------------------------
# RiskIdentifier — declining trend signal
# ---------------------------------------------------------------------------


def test_detects_declining_trend_without_timestamps():
    ri = RiskIdentifier(threshold=50, consecutive_sessions=3)

    result = ri.evaluate(student_id="anon_44", session_scores=[80, 75, 70, 65, 60])

    assert result.declining_trend is True
    assert result.at_risk is True  # declining trend alone is enough to flag
    assert any(r.code == RiskReasonCode.DECLINING_TREND for r in result.reasons)


def test_declining_trend_without_crossing_the_threshold():
    """A student can be trending down sharply while still scoring well
    above the raw threshold -- this is exactly the "80 -> 70 -> 60" case
    from the issue's motivation, and should be flagged even though no
    individual score is anywhere near `threshold`.
    """
    ri = RiskIdentifier(threshold=20, consecutive_sessions=3, decline_threshold_pct=10)

    result = ri.evaluate(student_id="anon_45", session_scores=[80, 75, 70, 65, 60])

    assert result.declining_trend is True
    assert result.at_risk is True
    assert not any(r.code == RiskReasonCode.CONSECUTIVE_LOW for r in result.reasons)


def test_stable_scores_are_not_flagged_as_declining():
    ri = RiskIdentifier(threshold=50, consecutive_sessions=3)

    result = ri.evaluate(student_id="anon_11b", session_scores=[70, 71, 69, 70, 72])

    assert result.declining_trend is False
    assert result.at_risk is False


def test_rolling_7day_and_30day_windows_with_timestamps():
    ri = RiskIdentifier(threshold=50, consecutive_sessions=3)

    now = datetime(2026, 7, 27, 12, 0, 0)
    dates = [
        now - timedelta(days=21),
        now - timedelta(days=20),
        now - timedelta(days=19),
        now - timedelta(days=2),
        now - timedelta(days=1),
        now,
    ]
    scores = [80, 78, 82, 40, 35, 30]

    result = ri.evaluate(
        student_id="anon_7", session_scores=scores, session_dates=dates
    )

    assert result.rolling_7day_avg == pytest.approx(35.0)
    assert result.rolling_30day_avg == pytest.approx(sum(scores) / len(scores))
    assert result.at_risk is True


def test_declining_trend_uses_real_week_over_week_with_timestamps():
    ri = RiskIdentifier(threshold=10, consecutive_sessions=3, decline_threshold_pct=10)

    now = datetime(2026, 7, 27, 12, 0, 0)
    dates = [now - timedelta(days=10 - i) for i in range(10)]
    scores = [82, 80, 78, 79, 81, 80, 62, 60, 58, 61]

    result = ri.evaluate(
        student_id="anon_5", session_scores=scores, session_dates=dates
    )

    assert result.declining_trend is True


# ---------------------------------------------------------------------------
# RiskIdentifier — anonymization, validation, edge cases
# ---------------------------------------------------------------------------


def test_students_are_anonymized_by_default():
    ri = RiskIdentifier(threshold=50)

    result = ri.evaluate(
        student_id="alex.johnson@school.edu", session_scores=[40, 35, 30]
    )

    assert result.student_id != "alex.johnson@school.edu"
    assert result.student_id.startswith("anon_")


def test_opted_in_students_are_identified():
    ri = RiskIdentifier(threshold=50)

    result = ri.evaluate(
        student_id="alex.johnson@school.edu",
        session_scores=[40, 35, 30],
        opted_in=True,
    )

    assert result.student_id == "alex.johnson@school.edu"


def test_empty_session_history_does_not_flag_or_crash():
    ri = RiskIdentifier(threshold=50)

    result = ri.evaluate(student_id="anon_1", session_scores=[])

    assert result.at_risk is False
    assert result.declining_trend is False
    assert result.average_score is None
    assert result.reasons == []


def test_mismatched_dates_length_raises():
    ri = RiskIdentifier(threshold=50)

    with pytest.raises(ValueError):
        ri.evaluate(
            student_id="anon_1",
            session_scores=[40, 35, 30],
            session_dates=[datetime(2026, 7, 1), datetime(2026, 7, 2)],
        )


def test_invalid_constructor_args_raise():
    with pytest.raises(ValueError):
        RiskIdentifier(threshold=-1)
    with pytest.raises(ValueError):
        RiskIdentifier(consecutive_sessions=0)
    with pytest.raises(ValueError):
        RiskIdentifier(decline_threshold_pct=0)


def test_threshold_above_score_max_raises():
    with pytest.raises(ValueError):
        RiskIdentifier(threshold=150)


def test_decline_threshold_pct_above_100_raises():
    with pytest.raises(ValueError):
        RiskIdentifier(decline_threshold_pct=150)


def test_evaluate_rejects_out_of_range_scores_even_without_dates():
    ri = RiskIdentifier(threshold=50)

    with pytest.raises(ValueError):
        ri.evaluate(student_id="anon_1", session_scores=[120, -5, 60])


def test_evaluate_rejects_unsorted_session_dates():
    ri = RiskIdentifier(threshold=50)

    with pytest.raises(ValueError):
        ri.evaluate(
            student_id="anon_1",
            session_scores=[40, 35, 30],
            session_dates=[
                datetime(2026, 7, 10),
                datetime(2026, 7, 1),  # out of order
                datetime(2026, 7, 15),
            ],
        )


def test_empty_session_history_sets_all_optional_fields_explicitly():
    ri = RiskIdentifier(threshold=50)

    result = ri.evaluate(student_id="anon_1", session_scores=[])

    assert result.average_score is None
    assert result.rolling_consecutive_avg is None
    assert result.rolling_7day_avg is None
    assert result.rolling_30day_avg is None
    assert result.consecutive_low_sessions == 0
    assert result.reasons == []


# ---------------------------------------------------------------------------
# TrendAnalyzer
# ---------------------------------------------------------------------------


def test_rolling_average_returns_none_before_enough_data():
    assert TrendAnalyzer.rolling_average([90, 85], window=3) is None


def test_rolling_average_empty_scores_returns_none():
    assert TrendAnalyzer.rolling_average([], window=3) is None


def test_rolling_average_uses_most_recent_window():
    assert TrendAnalyzer.rolling_average([90, 40, 30, 20], window=3) == pytest.approx(
        30.0
    )


def test_rolling_average_invalid_window_raises():
    with pytest.raises(ValueError):
        TrendAnalyzer.rolling_average([1, 2, 3], window=0)
    with pytest.raises(ValueError):
        TrendAnalyzer.rolling_average([1, 2, 3], window=-1)


def test_rolling_average_series_matches_rolling_average_at_each_point():
    scores = [90, 40, 30, 20]
    series = TrendAnalyzer.rolling_average_series(scores, window=3)

    assert series == [None, None, pytest.approx(160 / 3), pytest.approx(30.0)]
    # Sanity check against the single-value helper at the final index.
    assert series[-1] == pytest.approx(TrendAnalyzer.rolling_average(scores, window=3))


def test_percent_decline_handles_zero_previous():
    assert TrendAnalyzer.percent_decline(0, 10) == 0.0


def test_percent_decline_positive_for_a_drop():
    assert TrendAnalyzer.percent_decline(100, 80) == pytest.approx(20.0)


def test_rolling_window_average_exactly_seven_day_boundary():
    """A session exactly 6 days before `as_of` is inside a 7-day window;
    exactly 7 days before is not (7 days back is the *8th* distinct
    calendar day counting inclusively, which is outside the window).
    """
    now = datetime(2026, 7, 27)
    sessions = [
        ScoredSession(score=50, timestamp=now - timedelta(days=6)),
        ScoredSession(score=90, timestamp=now - timedelta(days=7)),
    ]

    avg = TrendAnalyzer.rolling_window_average(sessions, now, days=7)

    assert avg == pytest.approx(50.0)  # only the day-6 session is included


def test_rolling_window_average_exactly_thirty_day_boundary():
    now = datetime(2026, 7, 27)
    sessions = [
        ScoredSession(score=50, timestamp=now - timedelta(days=29)),
        ScoredSession(score=90, timestamp=now - timedelta(days=30)),
    ]

    avg = TrendAnalyzer.rolling_window_average(sessions, now, days=30)

    assert avg == pytest.approx(50.0)  # only the day-29 session is included


def test_rolling_window_handles_unsorted_input():
    now = datetime(2026, 7, 27)
    # Deliberately out of chronological order.
    sessions = [
        ScoredSession(score=10, timestamp=now),
        ScoredSession(score=90, timestamp=now - timedelta(days=20)),
        ScoredSession(score=30, timestamp=now - timedelta(days=1)),
    ]

    window = TrendAnalyzer.rolling_window(sessions, now, days=7)

    assert {s.score for s in window} == {10, 30}


def test_week_over_week_result_fields_are_named_not_positional():
    now = datetime(2026, 7, 27)
    sessions = [
        ScoredSession(score=40, timestamp=now - timedelta(days=1)),
        ScoredSession(score=80, timestamp=now - timedelta(days=8)),
    ]

    result = TrendAnalyzer.week_over_week(sessions, now)

    assert result.current_week_avg == pytest.approx(40.0)
    assert result.previous_week_avg == pytest.approx(80.0)


def test_scored_session_validates_score_range():
    with pytest.raises(ValueError):
        ScoredSession(score=150, timestamp=datetime(2026, 7, 27))
    with pytest.raises(ValueError):
        ScoredSession(score=-5, timestamp=datetime(2026, 7, 27))


# -- Score-range validation on the plain list-based helpers too ------------


def test_rolling_average_rejects_out_of_range_scores():
    with pytest.raises(ValueError):
        TrendAnalyzer.rolling_average([120, 50, 60], window=2)
    with pytest.raises(ValueError):
        TrendAnalyzer.rolling_average([-10, 50, 60], window=2)


def test_rolling_average_series_rejects_out_of_range_scores():
    with pytest.raises(ValueError):
        TrendAnalyzer.rolling_average_series([50, 200, 60], window=2)


def test_split_first_second_half_rejects_out_of_range_scores():
    with pytest.raises(ValueError):
        TrendAnalyzer.split_first_second_half([50, -1, 60, 70])


# -- rolling_average_series: dedicated edge-case coverage -------------------


def test_rolling_average_series_empty_input():
    assert TrendAnalyzer.rolling_average_series([], window=3) == []


def test_rolling_average_series_window_larger_than_input():
    assert TrendAnalyzer.rolling_average_series([50, 60], window=5) == [None, None]


def test_rolling_average_series_window_of_one_equals_scores_themselves():
    scores = [10, 20, 30]
    assert TrendAnalyzer.rolling_average_series(scores, window=1) == [
        pytest.approx(10.0),
        pytest.approx(20.0),
        pytest.approx(30.0),
    ]


def test_rolling_average_series_invalid_window_raises():
    with pytest.raises(ValueError):
        TrendAnalyzer.rolling_average_series([10, 20, 30], window=0)


# -- Window boundary specifics (the reason _window_bounds() exists) ---------


def test_session_exactly_six_days_before_is_included_in_seven_day_window():
    now = datetime(2026, 7, 27)
    sessions = [ScoredSession(score=42, timestamp=now - timedelta(days=6))]

    window = TrendAnalyzer.rolling_window(sessions, now, days=7)

    assert len(window) == 1


def test_session_exactly_seven_days_before_is_excluded_from_seven_day_window():
    now = datetime(2026, 7, 27)
    sessions = [ScoredSession(score=42, timestamp=now - timedelta(days=7))]

    window = TrendAnalyzer.rolling_window(sessions, now, days=7)

    assert window == []


def test_previous_week_window_does_not_overlap_current_week_window():
    now = datetime(2026, 7, 27)
    # One session in each of the two adjacent 7-day windows, plus one
    # sitting exactly on the boundary between them.
    current_week_session = ScoredSession(score=10, timestamp=now - timedelta(days=2))
    boundary_session = ScoredSession(
        score=99, timestamp=now - timedelta(days=6) - timedelta(days=1)
    )  # last day of the *previous* window, first day outside current
    previous_week_session = ScoredSession(score=90, timestamp=now - timedelta(days=10))

    sessions = [current_week_session, boundary_session, previous_week_session]

    result = TrendAnalyzer.week_over_week(sessions, now)

    current_window = TrendAnalyzer.rolling_window(sessions, now, days=7)
    current_start, _ = TrendAnalyzer._window_bounds(now, 7)
    previous_window = TrendAnalyzer.rolling_window(
        sessions, current_start - timedelta(days=1), days=7
    )

    assert set(current_window).isdisjoint(set(previous_window))
    assert result.current_week_avg == pytest.approx(
        sum(s.score for s in current_window) / len(current_window)
    )
    assert result.previous_week_avg == pytest.approx(
        sum(s.score for s in previous_window) / len(previous_window)
    )
