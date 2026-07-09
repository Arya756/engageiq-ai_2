import numpy as np
import pytest

from src.detection.expression import (
    Expression,
    ExpressionClassifier,
)


def make_face():
    return np.zeros((224, 224, 3), dtype=np.uint8)


class FakeFER:
    def __init__(self, emotions):
        self.emotions = emotions

    def detect_emotions(self, frame):
        return [
            {
                "emotions": self.emotions,
            }
        ]


@pytest.fixture
def classifier():
    clf = ExpressionClassifier()
    return clf


def test_engaged_expression(classifier):
    classifier._model = FakeFER(
        {
            "happy": 0.95,
            "neutral": 0.02,
            "sad": 0.01,
            "surprise": 0.01,
            "fear": 0.00,
            "angry": 0.00,
            "disgust": 0.01,
        }
    )

    result = classifier.classify(make_face())

    assert result.expression == Expression.ENGAGED
    assert result.confidence == pytest.approx(0.95)


def test_confused_expression(classifier):
    classifier._model = FakeFER(
        {
            "happy": 0.01,
            "neutral": 0.02,
            "sad": 0.01,
            "surprise": 0.90,
            "fear": 0.03,
            "angry": 0.02,
            "disgust": 0.01,
        }
    )

    result = classifier.classify(make_face())

    assert result.expression == Expression.CONFUSED
    assert result.confidence == pytest.approx(0.90)


def test_bored_expression(classifier):
    classifier._model = FakeFER(
        {
            "happy": 0.01,
            "neutral": 0.03,
            "sad": 0.91,
            "surprise": 0.01,
            "fear": 0.01,
            "angry": 0.02,
            "disgust": 0.01,
        }
    )

    result = classifier.classify(make_face())

    assert result.expression == Expression.BORED
    assert result.confidence == pytest.approx(0.91)


def test_neutral_expression(classifier):
    classifier._model = FakeFER(
        {
            "happy": 0.02,
            "neutral": 0.94,
            "sad": 0.01,
            "surprise": 0.01,
            "fear": 0.01,
            "angry": 0.00,
            "disgust": 0.01,
        }
    )

    result = classifier.classify(make_face())

    assert result.expression == Expression.NEUTRAL
    assert result.confidence == pytest.approx(0.94)


def test_low_confidence_returns_neutral(classifier):
    classifier._model = FakeFER(
        {
            "happy": 0.25,
            "neutral": 0.30,
            "sad": 0.20,
            "surprise": 0.15,
            "fear": 0.05,
            "angry": 0.03,
            "disgust": 0.02,
        }
    )

    result = classifier.classify(make_face())

    assert result.expression == Expression.NEUTRAL
    assert result.confidence == pytest.approx(0.30)
