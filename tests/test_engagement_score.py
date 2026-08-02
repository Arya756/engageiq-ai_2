import pytest

from src.config.scoring_weights import CourseType
from src.config.settings import settings
from src.scoring.engagement_score import compute_engagement_score


@pytest.fixture(autouse=True)
def reset_course_type():
    original = settings.course_type
    settings.course_type = CourseType.THEORY
    yield
    settings.course_type = original


def test_all_high_scores():
    score = compute_engagement_score(
        gaze_score=1.0,
        pose_score=1.0,
        expression_score=1.0,
        alertness_score=1.0,
    )

    assert score == pytest.approx(1.0)


def test_all_low_scores():
    score = compute_engagement_score(
        gaze_score=0,
        pose_score=0,
        expression_score=0,
        alertness_score=0,
    )

    assert score == pytest.approx(0.0)


def test_mixed_scores():
    score = compute_engagement_score(
        gaze_score=1.0,
        pose_score=0.50,
        expression_score=0.80,
        alertness_score=0.40,
    )

    expected = 1.0 * 0.30 + 0.50 * 0.20 + 0.80 * 0.25 + 0.40 * 0.25

    assert score == pytest.approx(expected)


def test_missing_expression():
    score = compute_engagement_score(
        gaze_score=0.90,
        pose_score=0.85,
        expression_score=None,
        alertness_score=0.95,
    )

    expected = 0.90 * (0.30 / 0.75) + 0.85 * (0.20 / 0.75) + 0.95 * (0.25 / 0.75)

    assert score == pytest.approx(expected)


def test_missing_gaze():
    score = compute_engagement_score(
        gaze_score=None,
        pose_score=0.80,
        expression_score=0.90,
        alertness_score=1.00,
    )

    expected = 0.80 * (0.20 / 0.70) + 0.90 * (0.25 / 0.70) + 1.00 * (0.25 / 0.70)

    assert score == pytest.approx(expected)


def test_missing_pose():
    score = compute_engagement_score(
        gaze_score=0.90,
        pose_score=None,
        expression_score=0.80,
        alertness_score=1.00,
    )

    expected = 0.90 * (0.30 / 0.80) + 0.80 * (0.25 / 0.80) + 1.00 * (0.25 / 0.80)

    assert score == pytest.approx(expected)


def test_missing_alertness():
    score = compute_engagement_score(
        gaze_score=0.90,
        pose_score=0.80,
        expression_score=0.70,
        alertness_score=None,
    )

    expected = 0.90 * (0.30 / 0.75) + 0.80 * (0.20 / 0.75) + 0.70 * (0.25 / 0.75)

    assert score == pytest.approx(expected)


def test_all_signals_missing():
    score = compute_engagement_score(
        gaze_score=None,
        pose_score=None,
        expression_score=None,
        alertness_score=None,
    )

    assert score == pytest.approx(0.0)


def test_lab_profile():
    settings.course_type = CourseType.LAB

    score = compute_engagement_score(
        gaze_score=1.0,
        pose_score=1.0,
        expression_score=1.0,
        alertness_score=1.0,
    )

    assert score == pytest.approx(1.0)
