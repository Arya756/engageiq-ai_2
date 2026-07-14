"""Course-specific engagement scoring weight profiles."""

from dataclasses import dataclass
from enum import Enum


class CourseType(str, Enum):
    """Supported course types."""

    THEORY = "theory"
    LAB = "lab"
    SEMINAR = "seminar"
    DISCUSSION = "discussion"


@dataclass(frozen=True)
class ScoringWeights:
    """Weights for engagement score components."""

    gaze: float
    pose: float
    expression: float
    alertness: float


SCORING_WEIGHT_PROFILES = {
    CourseType.THEORY: ScoringWeights(
        gaze=0.30,
        pose=0.20,
        expression=0.25,
        alertness=0.25,
    ),
    CourseType.LAB: ScoringWeights(
        gaze=0.40,
        pose=0.20,
        expression=0.15,
        alertness=0.25,
    ),
    CourseType.SEMINAR: ScoringWeights(
        gaze=0.20,
        pose=0.20,
        expression=0.35,
        alertness=0.25,
    ),
    CourseType.DISCUSSION: ScoringWeights(
        gaze=0.20,
        pose=0.15,
        expression=0.40,
        alertness=0.25,
    ),
}
