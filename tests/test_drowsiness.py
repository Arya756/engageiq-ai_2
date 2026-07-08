from src.detection.drowsiness import DrowsinessDetector, compute_ear


def test_compute_ear_open_eye():
    # Points for an eye that's open wide
    open_eye = [(0.0, 0.3), (0.1, 0.4), (0.3, 0.4), (0.4, 0.3), (0.3, 0.2), (0.1, 0.2)]
    ear = compute_ear(open_eye)

    # An open eye should give a value above the 0.25 cutoff
    assert ear > 0.25


def test_compute_ear_closed_eye():
    # Points for an eye that's basically shut (top and bottom points are close together)
    closed_eye = [
        (0.0, 0.3),
        (0.1, 0.31),
        (0.3, 0.31),
        (0.4, 0.3),
        (0.3, 0.29),
        (0.1, 0.29),
    ]
    ear = compute_ear(closed_eye)

    # A closed eye should give a small value, well under 0.1
    assert ear < 0.1


def test_normal_blink_not_drowsy():
    detector = DrowsinessDetector(ear_threshold=0.25, drowsy_duration=1.5)

    # A quick blink from t=1.0 to t=1.2 (only 0.2s) should NOT count as drowsy
    assert detector.update(ear=0.30, timestamp=0.0) is False  # Eye starts open
    assert detector.update(ear=0.10, timestamp=1.0) is False  # Eye just closed
    assert (
        detector.update(ear=0.10, timestamp=1.2) is False
    )  # Still closed, but barely 0.2s
    assert (
        detector.update(ear=0.30, timestamp=1.3) is False
    )  # Eye opens again, timer resets


def test_sustained_closure_is_drowsy():
    detector = DrowsinessDetector(ear_threshold=0.25, drowsy_duration=1.5)

    # Eyes close at t=1.0 and stay closed well past the 1.5s limit
    assert detector.update(ear=0.30, timestamp=0.0) is False
    assert detector.update(ear=0.10, timestamp=1.0) is False
    assert detector.update(ear=0.10, timestamp=2.0) is False

    # By t=2.5, eyes have been closed for exactly 1.5s, so this should trigger drowsy
    assert detector.update(ear=0.10, timestamp=2.5) is True

    # Should still say drowsy a moment later, since eyes are still closed
    assert detector.update(ear=0.10, timestamp=2.6) is True


def test_threshold_edge_cases():
    detector = DrowsinessDetector(ear_threshold=0.25, drowsy_duration=1.5)

    # EAR keeps dipping just below and just above the threshold, so the timer
    # shouldn't be able to build up cleanly
    assert (
        detector.update(ear=0.20, timestamp=0.0) is False
    )  # Below threshold, timer starts
    assert detector.update(ear=0.20, timestamp=1.0) is False  # Still below, 1.0s so far

    # Eye flutters open for a moment, which should reset the timer
    assert detector.update(ear=0.26, timestamp=1.2) is False  # Above threshold, resets

    # Eye closes again, starting a fresh timer
    assert detector.update(ear=0.20, timestamp=1.3) is False  # Timer starts over
    assert (
        detector.update(ear=0.20, timestamp=2.3) is False
    )  # Only 1.0s since the reset

    # Need to wait past 1.5s from the reset point (1.3s) to count as drowsy.
    # Using 2.81 instead of 2.8 to dodge floating point rounding issues (2.8 - 1.3 comes out to 1.49999...)
    assert detector.update(ear=0.20, timestamp=2.81) is True
