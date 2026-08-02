"""Tests for temporal filtering of engagement scores."""

import pytest

from src.scoring.temporal_filter import TemporalFilter


def test_cold_start_raw_scores():
    """Before the buffer fills, the filter must return raw input scores."""
    tf = TemporalFilter(window_size=10)

    # Feeding varying values. Because buffer is not full, it returns raw scores.
    assert tf.smooth(0.50) == 0.50
    assert tf.smooth(0.60) == 0.60
    assert tf.smooth(0.70) == 0.70
    assert tf.smooth(0.20) == 0.20


def test_stable_input():
    """Stable input should output approximately the same value once the buffer is full."""
    tf = TemporalFilter(window_size=30)
    for _ in range(30):
        smoothed = tf.smooth(0.85)
    assert abs(smoothed - 0.85) < 0.001


def test_single_anomaly_natural_suppression():
    """A single frame anomaly is naturally suppressed by the moving average window."""
    tf = TemporalFilter(window_size=30, max_step=0.05)
    # Fill the buffer
    for _ in range(30):
        tf.smooth(0.85)

    # Inject one frame of anomaly (nose scratch)
    smoothed = tf.smooth(0.10)
    # Natural average is (29*0.85 + 0.10)/30 = 0.825.
    # The drop is 0.85 - 0.825 = 0.025, which is <= 0.05 (so no step clamping is triggered).
    assert abs(smoothed - 0.825) < 0.001
    assert 0.85 - smoothed <= 0.05


def test_max_step_clamping():
    """If an anomaly drops the average faster than max_step allows, the drop is clamped."""
    # Use a small window size so a single 0.0 drop heavily affects the average
    tf = TemporalFilter(window_size=5, max_step=0.02)
    for _ in range(5):
        tf.smooth(0.85)

    # Inject a 0.0 score.
    # Natural average would be: (0.85 * 4 + 0.0) / 5 = 0.68.
    # But max_step limits the drop to 0.02, so the score is clamped at 0.85 - 0.02 = 0.83.
    smoothed = tf.smooth(0.0)
    assert abs(smoothed - 0.83) < 0.001


def test_upward_change_no_clamp():
    """Upward score increases should not be clamped by max_step."""
    tf = TemporalFilter(window_size=5, max_step=0.02)
    for _ in range(5):
        tf.smooth(0.50)

    # Inject a higher score of 1.0.
    # Average increases to (0.50 * 4 + 1.0) / 5 = 0.60.
    # The increase is 0.10. Since max_step only limits downward drops,
    # the upward shift is fully allowed.
    smoothed = tf.smooth(1.0)
    assert abs(smoothed - 0.60) < 0.001


def test_sustained_change():
    """A sustained change is fully reflected in the smoothed output within 3 seconds (45 frames)."""
    tf = TemporalFilter(window_size=30, max_step=0.05)
    # Start high
    for _ in range(30):
        tf.smooth(0.85)

    # Sustained low scores for 45 frames
    for _ in range(45):
        smoothed = tf.smooth(0.25)

    # The average should be exactly 0.25 since the buffer is entirely 0.25
    assert abs(smoothed - 0.25) < 0.001


def test_first_full_window_uses_average_not_last_raw_score():
    """The first complete window output should be the average of buffered scores."""
    tf = TemporalFilter(window_size=5, max_step=0.02)
    tf.smooth(0.80)
    tf.smooth(0.90)
    tf.smooth(0.85)
    tf.smooth(0.95)
    expected = (0.80 + 0.90 + 0.85 + 0.95 + 0.75) / 5
    assert tf.smooth(0.75) == pytest.approx(expected)


def test_reset_functionality():
    """Calling reset() returns the filter back to a cold-start state."""
    tf = TemporalFilter(window_size=5)
    for _ in range(5):
        tf.smooth(0.85)

    # Reset filter
    tf.reset()
    assert len(tf._buffer) == 0
    assert tf._last_smoothed is None

    # Should act like a cold start again and return raw scores
    assert tf.smooth(0.50) == 0.50


def test_invalid_configurations():
    """Initializing with invalid parameters should raise ValueErrors."""
    with pytest.raises(ValueError):
        TemporalFilter(window_size=0)
    with pytest.raises(ValueError):
        TemporalFilter(window_size=-5)
    with pytest.raises(ValueError):
        TemporalFilter(max_step=-0.01)
