"""Tests for class-level engagement aggregation — Issue 24."""

import pytest

from src.analytics.class_aggregator import (
    ClassAggregator,
    ClassStats,
    EngagementDip,
    TimelineEntry,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def make_agg() -> ClassAggregator:
    return ClassAggregator()


# ── aggregate() tests ─────────────────────────────────────────────────────────


def test_aggregate_normal_class():
    """Standard 10-student snapshot produces correct statistics."""
    agg = make_agg()
    scores = [0.80, 0.70, 0.90, 0.60, 0.85, 0.75, 0.65, 0.80, 0.70, 0.90]
    stats = agg.aggregate(scores)

    assert abs(stats.average - 0.765) < 0.001
    assert abs(stats.median - 0.775) < 0.001
    assert stats.min_score == 0.60
    assert stats.max_score == 0.90
    assert stats.student_count == 10


def test_aggregate_returns_classstats_instance():
    """aggregate() must always return a ClassStats instance."""
    agg = make_agg()
    assert isinstance(agg.aggregate([0.70, 0.80]), ClassStats)


def test_aggregate_all_engaged():
    """When all students score > 0.70, engaged_pct must be 1.0."""
    agg = make_agg()
    assert agg.aggregate([0.80, 0.85, 0.90, 0.75, 0.95]).engaged_pct == 1.0


def test_aggregate_none_engaged():
    """When no students score > 0.70, engaged_pct must be 0.0."""
    agg = make_agg()
    assert agg.aggregate([0.60, 0.55, 0.40, 0.65, 0.30]).engaged_pct == 0.0


def test_aggregate_score_at_threshold_not_engaged():
    """Score exactly at 0.70 must NOT count as engaged (strictly > 0.70)."""
    agg = make_agg()
    assert agg.aggregate([0.70]).engaged_pct == 0.0


def test_aggregate_excludes_none_scores():
    """Disconnected students (None) must be excluded from all calculations."""
    agg = make_agg()
    stats = agg.aggregate([0.80, None, 0.90, None, 0.70])
    assert stats.student_count == 3
    assert abs(stats.average - 0.80) < 0.001


def test_aggregate_skips_non_numeric_junk():
    """Non-numeric junk values must be skipped, not raise ValueError."""
    agg = make_agg()
    stats = agg.aggregate([0.80, "N/A", 0.90, "error", {}])
    assert stats.student_count == 2
    assert abs(stats.average - 0.85) < 0.001


def test_aggregate_skips_bool_values():
    """Bool values (True/False) must be skipped, not treated as 1.0 or 0.0.

    bool is a subclass of int in Python, so without an explicit guard,
    float(True)==1.0 and float(False)==0.0 would silently corrupt scores.
    """
    agg = make_agg()
    stats = agg.aggregate([0.80, True, 0.90, False])
    # Only 0.80 and 0.90 are valid — bools must be excluded
    assert stats.student_count == 2
    assert abs(stats.average - 0.85) < 0.001


def test_aggregate_all_junk_returns_zeros():
    """All-junk input must return zero-value ClassStats without crashing."""
    agg = make_agg()
    stats = agg.aggregate(["N/A", None, True, "error"])
    assert stats.average == 0.0
    assert stats.student_count == 0


def test_aggregate_all_none_returns_zeros():
    """All-None input returns zero-value ClassStats without crashing."""
    agg = make_agg()
    stats = agg.aggregate([None, None, None])
    assert stats.average == 0.0
    assert stats.student_count == 0


def test_aggregate_empty_list_returns_zeros():
    """Empty list returns zero stats without crashing."""
    agg = make_agg()
    stats = agg.aggregate([])
    assert stats.average == 0.0
    assert stats.student_count == 0


def test_aggregate_single_student():
    """Single student score works and std_dev is 0.0."""
    agg = make_agg()
    stats = agg.aggregate([0.85])
    assert stats.average == 0.85
    assert stats.std_dev == 0.0
    assert stats.student_count == 1


def test_aggregate_returns_float_types():
    """All numeric stats fields must be floats."""
    agg = make_agg()
    stats = agg.aggregate([0.80, 0.90])
    assert isinstance(stats.average, float)
    assert isinstance(stats.median, float)
    assert isinstance(stats.std_dev, float)
    assert isinstance(stats.engaged_pct, float)


# ── update_timeline() tests ───────────────────────────────────────────────────


def test_update_timeline_stores_average():
    """update_timeline() must store the correct class average per minute."""
    agg = make_agg()
    agg.update_timeline(10, [0.80, 0.70, 0.90])
    agg.update_timeline(11, [0.60, 0.70, 0.80])
    timeline = agg.get_timeline()
    assert abs(timeline[10] - 0.80) < 0.001
    assert abs(timeline[11] - 0.70) < 0.001


def test_update_timeline_returns_timeline_entry():
    """update_timeline() must return a TimelineEntry instance."""
    agg = make_agg()
    entry = agg.update_timeline(1, [0.80, 0.90])
    assert isinstance(entry, TimelineEntry)
    assert entry.minute == 1


def test_update_timeline_excludes_none():
    """Disconnected students (None) must be excluded from the average."""
    agg = make_agg()
    entry = agg.update_timeline(5, [0.80, None, 0.60])
    assert entry.student_count == 2
    assert abs(entry.average - 0.70) < 0.001


def test_update_timeline_skips_non_numeric_junk():
    """Non-numeric junk in scores must be skipped, not raise ValueError."""
    agg = make_agg()
    entry = agg.update_timeline(5, [0.80, "N/A", 0.60])
    assert entry.student_count == 2
    assert abs(entry.average - 0.70) < 0.001


def test_update_timeline_skips_bool_values():
    """Bool values in scores must be skipped, not treated as 1.0 or 0.0."""
    agg = make_agg()
    entry = agg.update_timeline(5, [0.80, True, 0.60, False])
    assert entry.student_count == 2
    assert abs(entry.average - 0.70) < 0.001


def test_update_timeline_all_none_not_stored():
    """A fully disconnected minute must NOT be stored in the internal timeline."""
    agg = make_agg()
    entry = agg.update_timeline(7, [None, None])
    assert entry.average == 0.0
    assert entry.student_count == 0
    assert 7 not in agg.get_timeline()


def test_update_timeline_all_junk_not_stored():
    """A minute with only junk values must NOT be stored in the timeline."""
    agg = make_agg()
    entry = agg.update_timeline(9, ["N/A", True, None])
    assert entry.student_count == 0
    assert 9 not in agg.get_timeline()


def test_disconnected_minute_does_not_corrupt_session_average():
    """A fully disconnected minute must not drag down the session average."""
    agg = make_agg()
    agg.update_timeline(10, [0.80, 0.80])
    agg.update_timeline(11, [None, None])  # wifi outage
    agg.update_timeline(12, [0.80, 0.80])
    timeline = agg.get_timeline()

    assert 11 not in timeline
    assert sorted(timeline.keys()) == [10, 12]
    assert agg.detect_dips(timeline, threshold=0.15) == []


def test_update_timeline_overwrites_same_minute():
    """Calling update_timeline() twice for the same minute overwrites the value."""
    agg = make_agg()
    agg.update_timeline(5, [0.80])
    agg.update_timeline(5, [0.50])
    assert abs(agg.get_timeline()[5] - 0.50) < 0.001


# ── get_timeline() tests ──────────────────────────────────────────────────────


def test_get_timeline_sorted_by_minute():
    """get_timeline() must return minutes in ascending order."""
    agg = make_agg()
    agg.update_timeline(3, [0.80])
    agg.update_timeline(1, [0.70])
    agg.update_timeline(2, [0.75])
    assert list(agg.get_timeline().keys()) == [1, 2, 3]


def test_get_timeline_empty_before_any_updates():
    """get_timeline() returns empty dict if update_timeline() was never called."""
    agg = make_agg()
    assert agg.get_timeline() == {}


# ── reset_timeline() tests ────────────────────────────────────────────────────


def test_reset_timeline_clears_all_data():
    """reset_timeline() must clear all stored minute data."""
    agg = make_agg()
    agg.update_timeline(1, [0.80])
    agg.update_timeline(2, [0.75])
    agg.reset_timeline()
    assert agg.get_timeline() == {}


def test_reset_timeline_allows_fresh_start():
    """After reset, new updates must work normally."""
    agg = make_agg()
    agg.update_timeline(1, [0.80])
    agg.reset_timeline()
    agg.update_timeline(1, [0.50])
    assert abs(agg.get_timeline()[1] - 0.50) < 0.001


# ── detect_dips() tests ───────────────────────────────────────────────────────


def test_detect_dips_finds_correct_minutes():
    """Minutes 14 and 15 should be flagged as dips in the example timeline."""
    agg = make_agg()
    timeline = {
        10: 0.78,
        11: 0.80,
        12: 0.75,
        13: 0.72,
        14: 0.52,
        15: 0.48,
        16: 0.55,
        17: 0.60,
        18: 0.70,
    }
    dip_minutes = [d.minute for d in agg.detect_dips(timeline, threshold=0.15)]
    assert 14 in dip_minutes
    assert 15 in dip_minutes


def test_detect_dips_stable_class_no_dips():
    """A stable class with no significant drops should return no dips."""
    agg = make_agg()
    timeline = {1: 0.80, 2: 0.82, 3: 0.79, 4: 0.81, 5: 0.80}
    assert agg.detect_dips(timeline, threshold=0.15) == []


def test_detect_dips_empty_timeline():
    """Empty timeline must return empty list without crashing."""
    agg = make_agg()
    assert agg.detect_dips({}, threshold=0.15) == []


def test_detect_dips_raises_on_threshold_above_one():
    """Passing threshold > 1.0 (e.g. 15 instead of 0.15) must raise ValueError."""
    agg = make_agg()
    with pytest.raises(ValueError, match="fraction"):
        agg.detect_dips({1: 0.80, 2: 0.50}, threshold=15)


def test_detect_dips_raises_on_zero_threshold():
    """Passing threshold=0.0 must raise ValueError."""
    agg = make_agg()
    with pytest.raises(ValueError):
        agg.detect_dips({1: 0.80}, threshold=0.0)


def test_detect_dips_raises_on_negative_threshold():
    """Passing a negative threshold must raise ValueError."""
    agg = make_agg()
    with pytest.raises(ValueError):
        agg.detect_dips({1: 0.80}, threshold=-0.1)


def test_detect_dips_threshold_boundary_one_allowed():
    """threshold=1.0 (100% drop) must be accepted as a valid extreme sentinel."""
    agg = make_agg()
    # Deliberate boundary: 1.0 is inclusive — flags only a complete collapse
    dips = agg.detect_dips({1: 0.80, 2: 0.80, 3: 0.0}, threshold=1.0)
    assert isinstance(dips, list)


def test_detect_dips_returns_engagement_dip_objects():
    """Each dip must be an EngagementDip with correct attributes."""
    agg = make_agg()
    dips = agg.detect_dips({1: 0.80, 2: 0.80, 3: 0.30}, threshold=0.15)
    for dip in dips:
        assert isinstance(dip, EngagementDip)
        assert hasattr(dip, "minute")
        assert hasattr(dip, "class_avg")
        assert hasattr(dip, "session_avg")


def test_detect_dips_threshold_sensitivity():
    """Raising threshold suppresses borderline dips."""
    agg = make_agg()
    timeline = {1: 0.70, 2: 0.80, 3: 0.60}
    assert all(d.minute != 3 for d in agg.detect_dips(timeline, threshold=0.15))
    assert any(d.minute == 3 for d in agg.detect_dips(timeline, threshold=0.10))


def test_detect_dips_above_average_not_flagged():
    """Minutes above the session average must never be flagged as dips."""
    agg = make_agg()
    dip_minutes = [
        d.minute for d in agg.detect_dips({1: 0.60, 2: 0.90, 3: 0.90}, threshold=0.15)
    ]
    assert 2 not in dip_minutes
    assert 3 not in dip_minutes


# ── Integration: timeline → detect_dips ──────────────────────────────────────


def test_timeline_feeds_detect_dips_end_to_end():
    """Timeline built via update_timeline() can be passed directly to detect_dips()."""
    agg = make_agg()
    agg.update_timeline(10, [0.78, 0.80])
    agg.update_timeline(11, [0.80, 0.82])
    agg.update_timeline(12, [None, None])  # outage — must not affect baseline
    agg.update_timeline(14, [0.40, 0.45])  # real dip
    agg.update_timeline(15, [0.42, 0.44])  # still low

    timeline = agg.get_timeline()
    dips = agg.detect_dips(timeline, threshold=0.15)
    dip_minutes = [d.minute for d in dips]

    assert 14 in dip_minutes
    assert 15 in dip_minutes
    assert 10 not in dip_minutes
    assert 12 not in dip_minutes  # outage minute absent
