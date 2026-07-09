"""Facial expression classifier (engaged, confused, bored, neutral)."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from enum import Enum

import cv2
from fer.fer import FER


class Expression(str, Enum):
    """Supported classroom expressions."""

    ENGAGED = "engaged"
    CONFUSED = "confused"
    BORED = "bored"
    NEUTRAL = "neutral"


@dataclass
class ExpressionResult:
    """Expression classification result."""

    expression: Expression
    confidence: float


class ExpressionClassifier:
    """Classifies facial expressions from cropped face images."""

    def __init__(self, model_path: str | None = None):
        self.model_path = model_path
        self._model = None

    def _load_model(self):
        """Load FER model lazily."""

        if self._model is None:
            self._model = FER(mtcnn=False)

    def predict(self, face_crop) -> tuple[Expression, float]:
        """Predict expression from cropped face image."""
        self._load_model()

        if face_crop is None or getattr(face_crop, "size", 0) == 0:
            return Expression.NEUTRAL, 0.0

        predictions = self._model.detect_emotions(face_crop)

        if not predictions:
            return Expression.NEUTRAL, 0.0

        emotions = predictions[0]["emotions"]

        label = max(emotions, key=emotions.get)
        confidence = float(emotions[label])

        mapping = {
            "happy": Expression.ENGAGED,
            "neutral": Expression.NEUTRAL,
            "sad": Expression.BORED,
            "surprise": Expression.CONFUSED,
            "fear": Expression.CONFUSED,
            "angry": Expression.CONFUSED,
            "disgust": Expression.CONFUSED,
        }

        expression = mapping.get(label, Expression.NEUTRAL)

        if confidence < 0.4:
            return Expression.NEUTRAL, confidence

        return expression, confidence

    def classify(self, face_crop) -> ExpressionResult:
        """Classify a face crop."""

        expression, confidence = self.predict(face_crop)

        return ExpressionResult(
            expression=expression,
            confidence=confidence,
        )


def run_demo():
    """Run expression classifier demo."""

    classifier = ExpressionClassifier()
    cap = cv2.VideoCapture(0)

    if not cap.isOpened():
        raise RuntimeError("Could not open webcam.")

    try:
        while True:
            ret, frame = cap.read()

            if not ret:
                break

            result = classifier.classify(frame)

            cv2.putText(
                frame,
                f"{result.expression.value} ({result.confidence:.2f})",
                (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (0, 255, 0),
                2,
                cv2.LINE_AA,
            )

            cv2.imshow("Expression Classifier", frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    finally:
        cap.release()
        cv2.destroyAllWindows()


def main():
    parser = argparse.ArgumentParser(description="Run expression classifier demo.")

    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run webcam demo.",
    )

    args = parser.parse_args()

    if args.demo:
        run_demo()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
