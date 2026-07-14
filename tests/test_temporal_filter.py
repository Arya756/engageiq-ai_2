"""Tests for temporal filtering of engagement scores."""

import pytest
from src.scoring.temporal_filter import TemporalFilter


def test_cold_start_raw_scores():
    """Before the buffer fills, the filter must return raw input scores."""
    tf = TemporalFilter(window_size=10)
    
    # Feeding varying values. Because buffer is not full, it returns raw scores.
    assert tf.smooth(50.0) == 50.0
    assert tf.smooth(60.0) == 60.0
    assert tf.smooth(70.0) == 70.0
    assert tf.smooth(20.0) == 20.0


def test_stable_input():
    """Stable input should output approximately the same value once the buffer is full."""
    tf = TemporalFilter(window_size=30)
    for _ in range(30):
        smoothed = tf.smooth(85.0)
    assert abs(smoothed - 85.0) < 0.1


def test_single_anomaly_natural_suppression():
    """A single frame anomaly is naturally suppressed by the moving average window."""
    tf = TemporalFilter(window_size=30, max_step=5.0)
    # Fill the buffer
    for _ in range(30):
        tf.smooth(85.0)
    
    # Inject one frame of anomaly (nose scratch)
    smoothed = tf.smooth(10.0)
    # Natural average is (29*85 + 10)/30 = 82.5.
    # The drop is 85.0 - 82.5 = 2.5, which is <= 5.0 (so no step clamping is triggered).
    assert abs(smoothed - 82.5) < 0.1
    assert 85.0 - smoothed <= 5.0


def test_max_step_clamping():
    """If an anomaly drops the average faster than max_step allows, the drop is clamped."""
    # Use a small window size so a single 0.0 drop heavily affects the average
    tf = TemporalFilter(window_size=5, max_step=2.0)
    for _ in range(5):
        tf.smooth(85.0)
        
    # Inject a 0.0 score.
    # Natural average would be: (85.0 * 4 + 0.0) / 5 = 68.0.
    # But max_step limits the drop to 2.0, so the score is clamped at 85.0 - 2.0 = 83.0.
    smoothed = tf.smooth(0.0)
    assert abs(smoothed - 83.0) < 0.1


def test_upward_change_no_clamp():
    """Upward score increases should not be clamped by max_step."""
    tf = TemporalFilter(window_size=5, max_step=2.0)
    for _ in range(5):
        tf.smooth(50.0)
        
    # Inject a higher score of 100.0.
    # Average increases to (50.0 * 4 + 100.0) / 5 = 60.0.
    # The increase is 10.0 points. Since max_step only limits downward drops,
    # the upward shift is fully allowed.
    smoothed = tf.smooth(100.0)
    assert abs(smoothed - 60.0) < 0.1


def test_sustained_change():
    """A sustained change is fully reflected in the smoothed output within 3 seconds (45 frames)."""
    tf = TemporalFilter(window_size=30, max_step=5.0)
    # Start high
    for _ in range(30):
        tf.smooth(85.0)
        
    # Sustained low scores for 45 frames
    for _ in range(45):
        smoothed = tf.smooth(25.0)
        
    # The average should be exactly 25.0 since the buffer is entirely 25.0
    assert abs(smoothed - 25.0) < 0.1


def test_first_full_window_uses_average_not_last_raw_score():
    """The first complete window output should be the average of buffered scores."""
    tf = TemporalFilter(window_size=5, max_step=2.0)
    tf.smooth(80.0)
    tf.smooth(90.0)
    tf.smooth(85.0)
    tf.smooth(95.0)
    expected = (80.0 + 90.0 + 85.0 + 95.0 + 75.0) / 5
    assert tf.smooth(75.0) == pytest.approx(expected)


def test_reset_functionality():
    """Calling reset() returns the filter back to a cold-start state."""
    tf = TemporalFilter(window_size=5)
    for _ in range(5):
        tf.smooth(85.0)
        
    # Reset filter
    tf.reset()
    assert len(tf._buffer) == 0
    assert tf._last_smoothed is None
    
    # Should act like a cold start again and return raw scores
    assert tf.smooth(50.0) == 50.0


def test_invalid_configurations():
    """Initializing with invalid parameters should raise ValueErrors."""
    with pytest.raises(ValueError):
        TemporalFilter(window_size=0)
    with pytest.raises(ValueError):
        TemporalFilter(window_size=-5)
    with pytest.raises(ValueError):
        TemporalFilter(max_step=-1.0)
