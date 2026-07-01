"""MediaPipe Face Landmarker integration for 478-landmark face detection (Tasks API)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

LANDMARK_COUNT = 468
_DEFAULT_MODEL_PATH = os.environ.get(
    "FACE_LANDMARKER_MODEL",
    str(Path(__file__).parent / "face_landmarker.task"),
)


@dataclass
class DetectedFace:
    """Face-level Face Landmarker output."""

    landmarks: list[tuple[float, float, float]]
    confidence: float


@dataclass
class FaceMeshResult:
    """Container for zero or more detected faces."""

    faces: list[DetectedFace] = field(default_factory=list)


class FaceMeshDetector:
    """Detects facial landmarks using MediaPipe Face Landmarker (Tasks API)."""

    def __init__(
        self,
        max_faces: int = 1,
        min_detection_confidence: float = 0.5,
        model_path: str = _DEFAULT_MODEL_PATH,
    ):
        self.max_faces = max_faces
        self.min_detection_confidence = min_detection_confidence
        self.model_path = model_path
        self._landmarker = None

    def _init_landmarker(self):
        """Initialize MediaPipe Face Landmarker lazily."""
        try:
            from mediapipe.tasks.python import BaseOptions
            from mediapipe.tasks.python.vision import (
                FaceLandmarker,
                FaceLandmarkerOptions,
                RunningMode,
            )
        except ImportError as exc:
            raise RuntimeError(
                "MediaPipe >=0.10 is required for FaceMeshDetector. "
                "Install with: pip install mediapipe"
            ) from exc

        if not Path(self.model_path).exists():
            raise FileNotFoundError(
                f"Face Landmarker model not found at '{self.model_path}'. "
                "Download face_landmarker.task from "
                "https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker"
                " and place it next to this file, or set FACE_LANDMARKER_MODEL."
            )

        options = FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=self.model_path),
            running_mode=RunningMode.IMAGE,
            num_faces=self.max_faces,
            min_face_detection_confidence=self.min_detection_confidence,
            min_face_presence_confidence=self.min_detection_confidence,
            min_tracking_confidence=0.5,
            output_face_blendshapes=False,
            output_facial_transformation_matrixes=False,
        )
        self._landmarker = FaceLandmarker.create_from_options(options)

    def detect(self, frame: np.ndarray | None) -> FaceMeshResult:
        """Detect face landmarks in a BGR frame."""
        if frame is None or getattr(frame, "size", 0) == 0:
            return FaceMeshResult()

        shape = getattr(frame, "shape", ())
        if len(shape) != 3 or shape[2] < 3:
            raise ValueError("Expected a color frame with shape (H, W, 3).")

        if self._landmarker is None:
            self._init_landmarker()

        import mediapipe as mp

        bgr_frame = frame[:, :, :3]
        rgb_frame = np.ascontiguousarray(bgr_frame[:, :, ::-1])
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

        results = self._landmarker.detect(mp_image)
        detected_faces: list[DetectedFace] = []

        face_landmarks_list = getattr(results, "face_landmarks", None) or []
        scores_list = getattr(results, "face_blendshapes", None) or []

        for i, face_landmarks in enumerate(face_landmarks_list):
            confidence = self._extract_confidence(face_landmarks, scores_list, i)
            if confidence < self.min_detection_confidence:
                continue

            landmarks = [
                (float(lm.x), float(lm.y), float(lm.z)) for lm in face_landmarks
            ]

            if len(landmarks) < LANDMARK_COUNT:
                continue

            detected_faces.append(
                DetectedFace(
                    landmarks=landmarks[:LANDMARK_COUNT],
                    confidence=confidence,
                )
            )

        return FaceMeshResult(faces=detected_faces)

    def _extract_confidence(self, face_landmarks, scores_list, index: int) -> float:
        """Derive a confidence score from landmark visibility/presence."""
        scores = []

        for lm in face_landmarks:
            for attr in ("visibility", "presence"):
                value = getattr(lm, attr, None)
                if isinstance(value, (int, float)) and value > 0:
                    scores.append(float(value))

        if scores:
            return max(0.0, min(1.0, sum(scores) / len(scores)))

        # Fallback: use blendshape scores if available
        if index < len(scores_list):
            blendshapes = scores_list[index]
            bs_scores = [
                float(bs.score)
                for bs in blendshapes
                if isinstance(getattr(bs, "score", None), (int, float))
            ]
            if bs_scores:
                return max(0.0, min(1.0, sum(bs_scores) / len(bs_scores)))

        return self.min_detection_confidence

    def close(self):
        """Release MediaPipe resources."""
        if self._landmarker is not None:
            self._landmarker.close()
            self._landmarker = None


def _draw_faces(frame: np.ndarray, faces: list[DetectedFace]) -> np.ndarray:
    """Overlay landmark dots and confidence labels on a frame."""
    import cv2

    height, width = frame.shape[:2]

    for face in faces:
        for x, y, _ in face.landmarks:
            pixel_x = int(round(x * width))
            pixel_y = int(round(y * height))

            if 0 <= pixel_x < width and 0 <= pixel_y < height:
                cv2.circle(
                    frame,
                    (pixel_x, pixel_y),
                    1,
                    (0, 255, 0),
                    -1,
                    lineType=cv2.LINE_AA,
                )

        if face.landmarks:
            label_x = int(round(face.landmarks[0][0] * width))
            label_y = max(10, int(round(face.landmarks[0][1] * height)) - 10)

            cv2.putText(
                frame,
                f"{face.confidence:.2f}",
                (label_x, label_y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                (0, 255, 0),
                1,
                cv2.LINE_AA,
            )

    return frame


def _run_demo(
    camera_index: int = 0, max_faces: int = 1, model_path: str = _DEFAULT_MODEL_PATH
):
    """Run a live webcam demo."""
    import cv2

    capture = cv2.VideoCapture(camera_index)
    if not capture.isOpened():
        raise ConnectionError(f"Could not open webcam source {camera_index}")

    detector = FaceMeshDetector(max_faces=max_faces)
    detector = FaceMeshDetector(max_faces=max_faces, model_path=model_path)

    try:
        while True:
            grabbed, frame = capture.read()
            if not grabbed:
                break

            result = detector.detect(frame)
            overlay = _draw_faces(frame, result.faces)

            cv2.putText(
                overlay,
                f"Faces: {len(result.faces)}",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 255, 0),
                2,
                cv2.LINE_AA,
            )

            cv2.imshow("EngageIQ Face Mesh", overlay)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        detector.close()
        capture.release()
        cv2.destroyAllWindows()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Run the EngageIQ Face Mesh demo.")
    parser.add_argument("--demo", action="store_true", help="Open a webcam preview.")
    parser.add_argument(
        "--camera",
        type=int,
        default=0,
        help="Webcam index to use for the demo.",
    )
    parser.add_argument(
        "--max-faces",
        type=int,
        default=1,
        help="Maximum number of faces to track.",
    )
    parser.add_argument(
        "--model",
        default=_DEFAULT_MODEL_PATH,
        help="Path to face_landmarker.task model file.",
    )

    args = parser.parse_args()

    if args.demo:
        _run_demo(
            camera_index=args.camera, max_faces=args.max_faces, model_path=args.model
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
