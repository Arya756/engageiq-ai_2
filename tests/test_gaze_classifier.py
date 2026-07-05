"""
Tests for src.detection.gaze_classifier.

Covers the 5 gaze states, the priority order between them, the
"head straight but iris glancing away" scenario the module exists to
catch, and threshold configurability.
"""

import pytest

from src.detection.gaze_classifier import (
    GazeState,
    GazeThresholds,
    classify_gaze,
    compute_ear,
    compute_iris_ratio,
)

# -------------------------------------------------------------------------
# One test per gaze state (acceptance criteria: at least 5 tests)
# -------------------------------------------------------------------------


def test_frontal_gaze_is_at_screen():
    state = classify_gaze(pitch=0, yaw=0, iris_ratio=0.5)
    assert state == GazeState.AT_SCREEN


def test_yaw_right_beyond_threshold_is_away_right():
    state = classify_gaze(pitch=0, yaw=25, iris_ratio=0.8)
    assert state == GazeState.AWAY_RIGHT


def test_yaw_left_beyond_threshold_is_away_left():
    state = classify_gaze(pitch=0, yaw=-25, iris_ratio=0.2)
    assert state == GazeState.AWAY_LEFT


def test_pitch_below_threshold_is_looking_down():
    state = classify_gaze(pitch=-30, yaw=0, iris_ratio=0.5)
    assert state == GazeState.LOOKING_DOWN


def test_low_ear_is_eyes_closed():
    state = classify_gaze(pitch=0, yaw=0, iris_ratio=0.5, ear=0.1)
    assert state == GazeState.EYES_CLOSED


# -------------------------------------------------------------------------
# Priority ordering between states
# -------------------------------------------------------------------------


def test_eyes_closed_takes_priority_over_looking_down():
    state = classify_gaze(pitch=-30, yaw=0, iris_ratio=0.5, ear=0.05)
    assert state == GazeState.EYES_CLOSED


def test_looking_down_takes_priority_over_yaw():
    state = classify_gaze(pitch=-30, yaw=25, iris_ratio=0.8)
    assert state == GazeState.LOOKING_DOWN


# -------------------------------------------------------------------------
# The core scenario: head pose alone would say "at screen", but iris
# reveals the student is actually looking elsewhere.
# -------------------------------------------------------------------------


def test_head_straight_but_iris_glancing_right_is_away_right():
    state = classify_gaze(pitch=0, yaw=0, iris_ratio=0.9)
    assert state == GazeState.AWAY_RIGHT


def test_head_straight_but_iris_glancing_left_is_away_left():
    state = classify_gaze(pitch=0, yaw=0, iris_ratio=0.1)
    assert state == GazeState.AWAY_LEFT


# -------------------------------------------------------------------------
# Edge cases / config
# -------------------------------------------------------------------------


def test_boundary_yaw_exactly_at_threshold_is_not_away():
    # Threshold is exclusive (> not >=) by design.
    state = classify_gaze(pitch=0, yaw=20, iris_ratio=0.5)
    assert state == GazeState.AT_SCREEN


def test_ear_none_skips_eyes_closed_check():
    state = classify_gaze(pitch=0, yaw=0, iris_ratio=0.5, ear=None)
    assert state == GazeState.AT_SCREEN


def test_custom_thresholds_are_respected():
    strict = GazeThresholds(yaw_threshold_deg=5.0)
    state = classify_gaze(pitch=0, yaw=10, iris_ratio=0.5, thresholds=strict)
    assert state == GazeState.AWAY_RIGHT


@pytest.mark.parametrize(
    "pitch,yaw,iris_ratio,ear,expected",
    [
        (0, 0, 0.5, None, GazeState.AT_SCREEN),
        (0, 30, 0.8, None, GazeState.AWAY_RIGHT),
        (0, -30, 0.2, None, GazeState.AWAY_LEFT),
        (-40, 0, 0.5, None, GazeState.LOOKING_DOWN),
        (0, 0, 0.5, 0.05, GazeState.EYES_CLOSED),
    ],
)
def test_all_five_states_parametrized(pitch, yaw, iris_ratio, ear, expected):
    assert classify_gaze(pitch, yaw, iris_ratio, ear) == expected


# -------------------------------------------------------------------------
# Landmark helpers (compute_iris_ratio / compute_ear)
# -------------------------------------------------------------------------


def _flat_landmark_list(overrides: dict, count: int = 478):
    """478 landmarks at the origin, with specific indices overridden."""
    landmarks = [(0.0, 0.0) for _ in range(count)]
    for idx, xy in overrides.items():
        landmarks[idx] = xy
    return landmarks


def test_compute_iris_ratio_centered():
    landmarks = _flat_landmark_list(
        {
            33: (0.0, 0.0),
            133: (10.0, 0.0),
            468: (5.0, 0.0),  # centered between corners
            362: (0.0, 0.0),
            263: (10.0, 0.0),
            473: (5.0, 0.0),
        }
    )
    ratio = compute_iris_ratio(landmarks)
    assert ratio == pytest.approx(0.5)


def test_compute_iris_ratio_returns_none_without_full_landmark_set():
    # Only 468 points available -- no iris landmarks (468-477) present.
    landmarks = [(0.0, 0.0) for _ in range(468)]
    assert compute_iris_ratio(landmarks) is None


def test_compute_ear_open_eye_shape():
    # A wide, tall eye contour -> higher EAR than a nearly-flat one.
    open_eye = _flat_landmark_list(
        {
            33: (0.0, 5.0),
            160: (3.0, 2.0),
            158: (7.0, 2.0),
            133: (10.0, 5.0),
            153: (7.0, 8.0),
            144: (3.0, 8.0),
            362: (0.0, 5.0),
            385: (3.0, 2.0),
            387: (7.0, 2.0),
            263: (10.0, 5.0),
            373: (7.0, 8.0),
            380: (3.0, 8.0),
        }
    )
    closed_eye = _flat_landmark_list(
        {
            33: (0.0, 5.0),
            160: (3.0, 4.9),
            158: (7.0, 4.9),
            133: (10.0, 5.0),
            153: (7.0, 5.1),
            144: (3.0, 5.1),
            362: (0.0, 5.0),
            385: (3.0, 4.9),
            387: (7.0, 4.9),
            263: (10.0, 5.0),
            373: (7.0, 5.1),
            380: (3.0, 5.1),
        }
    )
    assert compute_ear(open_eye) > compute_ear(closed_eye)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
