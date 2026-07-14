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
        gaze_score=100,
        pose_score=100,
        expression_score=100,
        alertness_score=100,
    )

    assert score == pytest.approx(100.0)


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
        gaze_score=100,
        pose_score=50,
        expression_score=80,
        alertness_score=40,
    )

    expected = 100 * 0.30 + 50 * 0.20 + 80 * 0.25 + 40 * 0.25

    assert score == pytest.approx(expected)


def test_missing_expression():
    score = compute_engagement_score(
        gaze_score=90,
        pose_score=85,
        expression_score=None,
        alertness_score=95,
    )

    expected = 90 * (0.30 / 0.75) + 85 * (0.20 / 0.75) + 95 * (0.25 / 0.75)

    assert score == pytest.approx(expected)


def test_missing_gaze():
    score = compute_engagement_score(
        gaze_score=None,
        pose_score=80,
        expression_score=90,
        alertness_score=100,
    )

    expected = 80 * (0.20 / 0.70) + 90 * (0.25 / 0.70) + 100 * (0.25 / 0.70)

    assert score == pytest.approx(expected)


def test_missing_pose():
    score = compute_engagement_score(
        gaze_score=90,
        pose_score=None,
        expression_score=80,
        alertness_score=100,
    )

    expected = 90 * (0.30 / 0.80) + 80 * (0.25 / 0.80) + 100 * (0.25 / 0.80)

    assert score == pytest.approx(expected)


def test_missing_alertness():
    score = compute_engagement_score(
        gaze_score=90,
        pose_score=80,
        expression_score=70,
        alertness_score=None,
    )

    expected = 90 * (0.30 / 0.75) + 80 * (0.20 / 0.75) + 70 * (0.25 / 0.75)

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
        gaze_score=100,
        pose_score=100,
        expression_score=100,
        alertness_score=100,
    )

    assert score == pytest.approx(100.0)
