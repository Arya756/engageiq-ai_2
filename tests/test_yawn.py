"""Tests for yawn detection — Issue 13.

Run: pytest tests/test_yawn.py -v
"""

from src.detection.yawn import (
    YawnDetector,
    compute_eye_aspect_ratio,
    compute_jaw_ratio,
    compute_mar,
    is_hand_over_mouth,
)

# ── Helpers ────────────────────────────────────────────────────────────────────


def make_4point_landmarks(vertical: float, horizontal: float = 1.0):
    """Create a 4-point mouth landmark set with controlled MAR.

    Order: [left_corner, top_lip, right_corner, bottom_lip]
    Expected MAR ≈ vertical / horizontal
    """
    half_h = horizontal / 2.0
    half_v = vertical / 2.0
    return [
        (-half_h, 0.0),  # left corner
        (0.0, -half_v),  # top lip
        (half_h, 0.0),  # right corner
        (0.0, half_v),  # bottom lip
    ]


# ── compute_mar tests ──────────────────────────────────────────────────────────


class TestComputeMAR:
    """Tests for the compute_mar function."""

    def test_yawn_mar_above_threshold(self):
        """Wide open mouth should produce MAR > 0.6."""
        landmarks = make_4point_landmarks(vertical=0.8, horizontal=1.0)
        mar = compute_mar(landmarks)
        assert mar > 0.6, f"Expected MAR > 0.6 for yawn, got {mar:.3f}"

    def test_closed_mouth_mar_below_threshold(self):
        """Closed mouth should produce MAR < 0.3."""
        landmarks = make_4point_landmarks(vertical=0.1, horizontal=1.0)
        mar = compute_mar(landmarks)
        assert mar < 0.3, f"Expected MAR < 0.3 for closed mouth, got {mar:.3f}"

    def test_speech_mar_between_thresholds(self):
        """Normal speech opening should produce MAR between 0.2 and 0.5."""
        landmarks = make_4point_landmarks(vertical=0.35, horizontal=1.0)
        mar = compute_mar(landmarks)
        assert 0.2 <= mar <= 0.5, f"Expected speech MAR 0.2-0.5, got {mar:.3f}"

    def test_mar_returns_float(self):
        """compute_mar should always return a float."""
        landmarks = make_4point_landmarks(vertical=0.5)
        mar = compute_mar(landmarks)
        assert isinstance(mar, float)

    def test_mar_is_non_negative(self):
        """MAR should always be >= 0."""
        landmarks = make_4point_landmarks(vertical=0.0)
        mar = compute_mar(landmarks)
        assert mar >= 0.0

    def test_mar_returns_zero_for_empty_input(self):
        """compute_mar should return 0.0 for empty input."""
        assert compute_mar([]) == 0.0

    def test_mar_returns_zero_for_too_few_landmarks(self):
        """compute_mar should return 0.0 if fewer than 4 landmarks."""
        assert compute_mar([(0.0, 0.0), (0.1, 0.1)]) == 0.0

    def test_mar_increases_with_mouth_opening(self):
        """MAR should increase as vertical opening increases."""
        mar_closed = compute_mar(make_4point_landmarks(vertical=0.1))
        mar_open = compute_mar(make_4point_landmarks(vertical=0.8))
        assert mar_open > mar_closed


def make_face_landmarks():
    """Create a minimal 468-point face landmark list for detector tests."""
    landmarks = [(0.0, 0.0, 0.0)] * 468
    landmarks[61] = (0.2, 0.5, 0.0)
    landmarks[291] = (0.8, 0.5, 0.0)
    landmarks[13] = (0.5, 0.45, 0.0)
    landmarks[14] = (0.5, 0.55, 0.0)
    landmarks[152] = (0.5, 0.9, 0.0)

    # Left eye landmarks
    landmarks[33] = (0.3, 0.3, 0.0)
    landmarks[160] = (0.325, 0.285, 0.0)
    landmarks[158] = (0.375, 0.285, 0.0)
    landmarks[133] = (0.4, 0.3, 0.0)
    landmarks[153] = (0.375, 0.315, 0.0)
    landmarks[144] = (0.325, 0.315, 0.0)

    # Right eye landmarks
    landmarks[362] = (0.6, 0.3, 0.0)
    landmarks[385] = (0.625, 0.285, 0.0)
    landmarks[387] = (0.675, 0.285, 0.0)
    landmarks[263] = (0.7, 0.3, 0.0)
    landmarks[373] = (0.675, 0.315, 0.0)
    landmarks[380] = (0.625, 0.315, 0.0)
    return landmarks


# ── YawnDetector.update() tests ────────────────────────────────────────────────


class TestYawnDetectorUpdate:
    """Tests for YawnDetector.update() method."""

    def test_yawn_detected_after_sustained_opening(self):
        """Sustained mouth opening > yawn_duration should be detected as yawn."""
        detector = YawnDetector(mar_threshold=0.6, yawn_duration=2.0)

        assert detector.update(mar=0.75, timestamp=0.0) is False
        assert detector.update(mar=0.75, timestamp=1.0) is False
        result = detector.update(mar=0.75, timestamp=2.5)
        assert result is True, "Should detect yawn after 2.5s sustained opening"

    def test_speech_does_not_trigger_yawn(self):
        """Brief mouth opening (speech) should NOT trigger yawn detection."""
        detector = YawnDetector(mar_threshold=0.6, yawn_duration=2.0)

        detector.update(mar=0.75, timestamp=0.0)
        detector.update(mar=0.75, timestamp=0.3)
        # Mouth closes before yawn_duration
        detector.update(mar=0.1, timestamp=0.4)

        assert detector.yawn_count == 0, "Brief opening should not count as yawn"

    def test_yawn_count_increments(self):
        """Yawn count should increment by 1 per detected yawn."""
        detector = YawnDetector(mar_threshold=0.6, yawn_duration=2.0)

        detector.update(mar=0.75, timestamp=0.0)
        detector.update(mar=0.75, timestamp=2.5)
        assert detector.yawn_count == 1

        # Second yawn
        detector.update(mar=0.1, timestamp=3.0)  # mouth closes
        detector.update(mar=0.75, timestamp=4.0)
        detector.update(mar=0.75, timestamp=6.5)
        assert detector.yawn_count == 2

    def test_no_yawn_on_closed_mouth(self):
        """Closed mouth frames should never trigger yawn."""
        detector = YawnDetector(mar_threshold=0.6, yawn_duration=2.0)
        for t in range(10):
            result = detector.update(mar=0.1, timestamp=float(t))
            assert result is False
        assert detector.yawn_count == 0

    def test_yawn_only_counted_once_per_opening(self):
        """A single sustained opening should only count as one yawn."""
        detector = YawnDetector(mar_threshold=0.6, yawn_duration=2.0)

        for t in range(10):
            detector.update(mar=0.75, timestamp=float(t))

        assert detector.yawn_count == 1, "Long opening should count as only 1 yawn"

    def test_hidden_yawn_requires_hand_and_support_cue(self):
        """Hand-over-mouth plus jaw motion should trigger a yawn."""
        detector = YawnDetector(mar_threshold=0.9, yawn_duration=2.0)

        assert (
            detector.update(
                mar=0.2,
                timestamp=0.0,
                hand_on_mouth=True,
                jaw_motion=True,
            )
            is False
        )
        assert (
            detector.update(
                mar=0.2,
                timestamp=1.0,
                hand_on_mouth=True,
                jaw_motion=True,
            )
            is False
        )
        result = detector.update(
            mar=0.2,
            timestamp=2.5,
            hand_on_mouth=True,
            jaw_motion=True,
        )
        assert result is True
        assert detector.yawn_count == 1

    def test_hand_over_mouth_without_support_does_not_trigger(self):
        """Hand-over-mouth alone should not count as yawn."""
        detector = YawnDetector(mar_threshold=0.9, yawn_duration=2.0)

        for t in range(5):
            assert (
                detector.update(
                    mar=0.2,
                    timestamp=float(t),
                    hand_on_mouth=True,
                )
                is False
            )
        assert detector.yawn_count == 0

    def test_hidden_yawn_without_hand_requires_two_supports(self):
        """Hidden yawn without hand should require two supporting cues."""
        detector = YawnDetector(mar_threshold=0.95, yawn_duration=2.0)

        # single support shouldn't trigger
        for t in range(3):
            assert (
                detector.update(
                    mar=0.2,
                    timestamp=float(t),
                    jaw_motion=True,
                    head_motion=False,
                    eye_fatigue=False,
                )
                is False
            )

        # two supports sustained should trigger
        assert (
            detector.update(
                mar=0.2,
                timestamp=0.0,
                jaw_motion=True,
                head_motion=True,
            )
            is False
        )
        assert (
            detector.update(
                mar=0.2,
                timestamp=1.0,
                jaw_motion=True,
                head_motion=True,
            )
            is False
        )
        result = detector.update(
            mar=0.2,
            timestamp=2.5,
            jaw_motion=True,
            head_motion=True,
        )
        assert result is True
        assert detector.yawn_count == 1

    def test_cover_after_open_with_single_support_triggers_due_to_occlusion_grace(self):
        """Open mouth then cover (MAR drops) with one support should still count.

        Sequence:
        - t=0 open (MAR >= threshold)
        - t=1 cover (MAR low) with jaw_motion=True
        - t=2.5 still covered with jaw_motion=True -> yawn counted
        """
        detector = YawnDetector(mar_threshold=0.6, yawn_duration=2.0)
        detector.occlusion_grace = 1.5

        # initial sustained opening starts the timer
        assert detector.update(mar=0.75, timestamp=0.0) is False
        assert detector.update(mar=0.75, timestamp=1.0) is False

        # cover now: MAR drops but jaw motion present; occlusion_grace should proxy hand
        assert detector.update(mar=0.2, timestamp=1.0, jaw_motion=True) is False

        # later, still covered + jaw motion -> should register yawn (duration from t=0)
        result = detector.update(mar=0.2, timestamp=2.5, jaw_motion=True)
        assert result is True
        assert detector.yawn_count == 1


# ── YawnDetector.record_yawn() tests ──────────────────────────────────────────


class TestRecordYawn:
    """Tests for YawnDetector.record_yawn() method."""

    def test_record_yawn_increments_count(self):
        """record_yawn should increment yawn_count."""
        detector = YawnDetector()
        detector.record_yawn(timestamp=60.0)
        assert detector.yawn_count == 1

    def test_record_yawn_stores_timestamp(self):
        """record_yawn should store timestamp for fatigue calculation."""
        detector = YawnDetector()
        detector.record_yawn(timestamp=60.0)
        assert 60.0 in detector._yawn_timestamps


# ── is_fatigued tests ──────────────────────────────────────────────────────────


class TestIsFatigued:
    """Tests for YawnDetector.is_fatigued() method."""

    def test_fatigued_after_3_yawns_in_window(self):
        """3 yawns within 10 minutes should trigger fatigue."""
        detector = YawnDetector()
        detector.record_yawn(timestamp=60.0)
        detector.record_yawn(timestamp=300.0)
        detector.record_yawn(timestamp=540.0)

        assert detector.is_fatigued(window_seconds=600.0) is True

    def test_not_fatigued_with_only_2_yawns(self):
        """2 yawns should not trigger fatigue."""
        detector = YawnDetector()
        detector.record_yawn(timestamp=60.0)
        detector.record_yawn(timestamp=300.0)

        assert detector.is_fatigued(window_seconds=600.0) is False

    def test_not_fatigued_when_yawns_outside_window(self):
        """Yawns outside the time window should not count."""
        detector = YawnDetector()
        # 3 yawns but first one is outside the 600s window
        detector.record_yawn(timestamp=0.0)
        detector.record_yawn(timestamp=500.0)
        detector.record_yawn(timestamp=550.0)

        # Reference time = 550, cutoff = 550 - 600 = -50
        # All 3 are within window actually — use current_time to control
        assert (
            detector.is_fatigued(window_seconds=100.0, current_time=600.0) is False
        )  # only 500 and 550 are within last 100s = 2 yawns

    def test_not_fatigued_with_no_yawns(self):
        """No yawns recorded should return False."""
        detector = YawnDetector()
        assert detector.is_fatigued() is False

    def test_fatigue_with_current_time_param(self):
        """is_fatigued should use current_time param when provided."""
        detector = YawnDetector()
        detector.record_yawn(timestamp=60.0)
        detector.record_yawn(timestamp=300.0)
        detector.record_yawn(timestamp=540.0)

        # All 3 within 600s window from t=600
        assert detector.is_fatigued(window_seconds=600.0, current_time=600.0) is True

        # None within 10s window from t=600
        assert detector.is_fatigued(window_seconds=10.0, current_time=600.0) is False

    def test_is_fatigued_combines_ear_data(self):
        """EAR data should contribute to fatigue decision as additional evidence."""
        detector = YawnDetector()
        # Two yawns recorded within window
        detector.record_yawn(timestamp=100.0)
        detector.record_yawn(timestamp=200.0)

        # Provide EAR samples (recent first) with majority below threshold
        ear_samples = [0.18, 0.17, 0.16, 0.22]

        # Without EAR evidence this would be only 2 yawns -> not fatigued
        assert detector.is_fatigued(window_seconds=1000.0) is False

        # With EAR samples indicating fatigue, should now report fatigued
        assert (
            detector.is_fatigued(
                window_seconds=1000.0, current_time=300.0, ear_values=ear_samples
            )
            is True
        )


class TestHiddenYawnHelpers:
    """Tests for hidden yawn helper methods."""

    def test_is_hand_over_mouth_detects_overlap(self):
        face_landmarks = make_face_landmarks()
        hand_bbox = [0.45, 0.45, 0.65, 0.65]

        assert (
            is_hand_over_mouth(
                hand_bboxes=[hand_bbox],
                face_landmarks=face_landmarks,
                frame_size=(1000, 1000),
            )
            is True
        )

    def test_is_hand_over_mouth_rejects_non_overlapping_hand(self):
        face_landmarks = make_face_landmarks()
        hand_bbox = [0.0, 0.0, 0.1, 0.1]

        assert (
            is_hand_over_mouth(
                hand_bboxes=[hand_bbox],
                face_landmarks=face_landmarks,
                frame_size=(1000, 1000),
            )
            is False
        )

    def test_compute_jaw_ratio_returns_positive_for_lowered_chin(self):
        landmarks = make_face_landmarks()
        ratio = compute_jaw_ratio(landmarks)
        assert ratio > 0.0

    def test_compute_eye_aspect_ratio_returns_valid_value(self):
        landmarks = make_face_landmarks()
        ear = compute_eye_aspect_ratio(landmarks)
        assert 0.0 < ear < 0.5


# ── Threshold edge case tests ──────────────────────────────────────────────────


class TestThresholdEdgeCases:
    """Tests for threshold boundary conditions."""

    def test_mar_exactly_at_threshold_triggers(self):
        """MAR exactly at threshold should be considered open."""
        detector = YawnDetector(mar_threshold=0.6, yawn_duration=2.0)
        detector.update(mar=0.6, timestamp=0.0)
        result = detector.update(mar=0.6, timestamp=2.5)
        assert result is True

    def test_mar_just_below_threshold_does_not_trigger(self):
        """MAR just below threshold should not count as open."""
        detector = YawnDetector(mar_threshold=0.6, yawn_duration=2.0)
        for t in range(5):
            result = detector.update(mar=0.59, timestamp=float(t))
            assert result is False
        assert detector.yawn_count == 0

    def test_custom_threshold_respected(self):
        """Custom MAR threshold should be used instead of default."""
        detector = YawnDetector(mar_threshold=0.4, yawn_duration=2.0)
        detector.update(mar=0.45, timestamp=0.0)
        result = detector.update(mar=0.45, timestamp=2.5)
        assert result is True

    def test_custom_duration_respected(self):
        """Custom yawn_duration should be used instead of default."""
        detector = YawnDetector(mar_threshold=0.6, yawn_duration=1.0)
        detector.update(mar=0.75, timestamp=0.0)
        result = detector.update(mar=0.75, timestamp=1.5)
        assert result is True


# ── reset tests ────────────────────────────────────────────────────────────────


class TestReset:
    """Tests for YawnDetector.reset() method."""

    def test_reset_clears_yawn_count(self):
        """reset() should clear yawn count and timestamps."""
        detector = YawnDetector()
        detector.record_yawn(60.0)
        detector.record_yawn(120.0)
        detector.record_yawn(180.0)

        assert detector.yawn_count == 3
        detector.reset()
        assert detector.yawn_count == 0
        assert detector.is_fatigued() is False

    def test_reset_clears_tracking_state(self):
        """reset() should clear internal yawn tracking state."""
        detector = YawnDetector()
        detector.update(mar=0.75, timestamp=0.0)
        detector.reset()
        assert detector._is_yawning is False
        assert detector._yawn_recorded is False
