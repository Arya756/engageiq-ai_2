"""Multi-signal engagement scorer."""

from src.config.scoring_weights import SCORING_WEIGHT_PROFILES
from src.config.settings import settings


def compute_engagement_score(
    gaze_score: float | None,
    pose_score: float | None,
    expression_score: float | None,
    alertness_score: float | None,
) -> float:
    """Compute weighted engagement score from multiple CV signals."""

    weights = SCORING_WEIGHT_PROFILES[settings.course_type]

    signals = {
        "gaze": (gaze_score, weights.gaze),
        "pose": (pose_score, weights.pose),
        "expression": (expression_score, weights.expression),
        "alertness": (alertness_score, weights.alertness),
    }

    available = {
        name: (score, weight)
        for name, (score, weight) in signals.items()
        if score is not None
    }

    if not available:
        return 0.0

    total_weight = sum(weight for _, weight in available.values())

    score = 0.0

    for value, weight in available.values():
        normalized_weight = weight / total_weight
        score += value * normalized_weight

    return float(score)
