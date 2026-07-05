"""Gaze direction classifier combining head pose with iris position.

Head pose alone tells you which way the head is pointing, not where the
eyes are looking -- a student can face the screen while glancing at a
phone off to the side. This module fuses head pose (pitch, yaw) with
MediaPipe iris landmarks to classify gaze into 5 discrete states used
downstream by the engagement scorer (#16) and the state machine (#17).

Closes #9
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Sequence, Tuple

from src.config.settings import settings


class GazeState(str, Enum):
    AT_SCREEN = "at_screen"
    AWAY_LEFT = "away_left"
    AWAY_RIGHT = "away_right"
    LOOKING_DOWN = "looking_down"
    EYES_CLOSED = "eyes_closed"

    def __str__(self) -> str:  # print(state) -> "at_screen", not "GazeState.AT_SCREEN"
        return self.value


# ---------------------------------------------------------------------------
# Configurable thresholds
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class GazeThresholds:
    """Thresholds driving `classify_gaze`, overridable per acceptance
    criteria ("All thresholds configurable in settings")."""

    yaw_threshold_deg: float = 20.0
    pitch_down_threshold_deg: float = -25.0
    ear_threshold: float = 0.2
    # Horizontal iris ratio: 0.0 = fully toward one corner, 1.0 = fully
    # toward the other, 0.5 = centered.
    iris_left_threshold: float = 0.35
    iris_right_threshold: float = 0.65

    @classmethod
    def from_settings(cls) -> "GazeThresholds":
        """Build thresholds from `src/config/settings.py`, falling back to
        the defaults above for any field not defined there."""
        defaults = cls()
        return cls(
            yaw_threshold_deg=getattr(
                settings, "gaze_yaw_threshold_deg", defaults.yaw_threshold_deg
            ),
            pitch_down_threshold_deg=getattr(
                settings,
                "gaze_pitch_down_threshold_deg",
                defaults.pitch_down_threshold_deg,
            ),
            ear_threshold=getattr(
                settings, "gaze_ear_threshold", defaults.ear_threshold
            ),
            iris_left_threshold=getattr(
                settings, "gaze_iris_left_threshold", defaults.iris_left_threshold
            ),
            iris_right_threshold=getattr(
                settings, "gaze_iris_right_threshold", defaults.iris_right_threshold
            ),
        )


DEFAULT_THRESHOLDS = GazeThresholds.from_settings()


# ---------------------------------------------------------------------------
# Core classification
# ---------------------------------------------------------------------------
def classify_gaze(
    pitch: float,
    yaw: float,
    iris_ratio: float = 0.5,
    ear: Optional[float] = None,
    thresholds: Optional[GazeThresholds] = None,
) -> GazeState:
    """Classify gaze direction from head pose + iris position.

    Args:
        pitch: Head pitch in degrees. Negative = looking down.
        yaw: Head yaw in degrees. Positive = turned right, negative = left.
        iris_ratio: Horizontal iris position within the eye, averaged
            across both eyes: 0.0 (left corner) to 1.0 (right corner),
            0.5 = centered. Defaults to centered when not available.
        ear: Eye Aspect Ratio. Below `thresholds.ear_threshold` means the
            eyes are closed. Optional -- if omitted, the eyes-closed check
            is skipped (e.g. when EAR wasn't computed for this frame).
        thresholds: Optional `GazeThresholds` override. Defaults to
            `DEFAULT_THRESHOLDS`, which is populated from settings.

    Returns:
        The classified `GazeState`.

    Priority order (highest first):
        1. EYES_CLOSED  - EAR below threshold. Can't be looking anywhere
           useful with eyes shut.
        2. LOOKING_DOWN - pitch below threshold, e.g. looking at a phone
           in the lap.
        3. AWAY_LEFT / AWAY_RIGHT - triggered by EITHER head yaw beyond
           threshold OR iris drifting toward a corner beyond threshold.
           Combining both signals is what catches "head straight, eyes
           glancing sideways" in addition to a fully turned head.
        4. AT_SCREEN - default when nothing above fires.
    """
    t = thresholds or DEFAULT_THRESHOLDS

    if ear is not None and ear < t.ear_threshold:
        return GazeState.EYES_CLOSED

    if pitch < t.pitch_down_threshold_deg:
        return GazeState.LOOKING_DOWN

    right_by_yaw = yaw > t.yaw_threshold_deg
    left_by_yaw = yaw < -t.yaw_threshold_deg
    right_by_iris = iris_ratio > t.iris_right_threshold
    left_by_iris = iris_ratio < t.iris_left_threshold

    if right_by_yaw or right_by_iris:
        return GazeState.AWAY_RIGHT
    if left_by_yaw or left_by_iris:
        return GazeState.AWAY_LEFT

    return GazeState.AT_SCREEN


# ---------------------------------------------------------------------------
# MediaPipe landmark helpers (468-point mesh + 10 iris points, indices
# 468-477, present when the Face Landmarker model outputs the full
# 478-point set)
# ---------------------------------------------------------------------------
EYE_A_CORNERS = (33, 133)  # outer, inner corner of one eye
EYE_B_CORNERS = (362, 263)  # outer, inner corner of the other eye

EYE_A_IRIS_CENTER = 468
EYE_A_IRIS_BOUNDARY = (469, 470, 471, 472)
EYE_B_IRIS_CENTER = 473
EYE_B_IRIS_BOUNDARY = (474, 475, 476, 477)

# 6-point EAR landmarks per eye: (outer, top1, top2, inner, bottom2, bottom1)
EYE_A_EAR_POINTS = (33, 160, 158, 133, 153, 144)
EYE_B_EAR_POINTS = (362, 385, 387, 263, 373, 380)

MIN_LANDMARKS_FOR_IRIS = 478


def _iris_ratio_for_eye(
    landmarks: Sequence[Tuple[float, float]],
    corners: Tuple[int, int],
    iris_center_id: int,
) -> float:
    outer = landmarks[corners[0]]
    inner = landmarks[corners[1]]
    iris_x = landmarks[iris_center_id][0]

    eye_width = inner[0] - outer[0]
    if eye_width == 0:
        return 0.5
    ratio = (iris_x - outer[0]) / eye_width
    return max(0.0, min(1.0, ratio))


def compute_iris_ratio(landmarks: Sequence[Tuple[float, float]]) -> Optional[float]:
    """Average horizontal iris ratio across both eyes.

    Requires the full 478-landmark output (indices 468-477 = iris points).
    Returns None if only the base 468-point mesh is available, since iris
    position can't be computed without those points.
    """
    if len(landmarks) < MIN_LANDMARKS_FOR_IRIS:
        return None
    ratio_a = _iris_ratio_for_eye(landmarks, EYE_A_CORNERS, EYE_A_IRIS_CENTER)
    ratio_b = _iris_ratio_for_eye(landmarks, EYE_B_CORNERS, EYE_B_IRIS_CENTER)
    return (ratio_a + ratio_b) / 2.0


def _ear_for_eye(
    landmarks: Sequence[Tuple[float, float]],
    points: Tuple[int, int, int, int, int, int],
) -> float:
    p1, p2, p3, p4, p5, p6 = (landmarks[i] for i in points)
    vertical = math.dist(p2, p6) + math.dist(p3, p5)
    horizontal = 2.0 * math.dist(p1, p4)
    if horizontal == 0:
        return 0.3  # neutral / open default
    return vertical / horizontal


def compute_ear(landmarks: Sequence[Tuple[float, float]]) -> float:
    """Average Eye Aspect Ratio across both eyes (standard 6-point EAR)."""
    ear_a = _ear_for_eye(landmarks, EYE_A_EAR_POINTS)
    ear_b = _ear_for_eye(landmarks, EYE_B_EAR_POINTS)
    return (ear_a + ear_b) / 2.0


# ---------------------------------------------------------------------------
# Live webcam demo
# ---------------------------------------------------------------------------
_DEMO_COLORS_BGR = {
    GazeState.AT_SCREEN: (0, 200, 0),  # green
    GazeState.AWAY_LEFT: (0, 0, 220),  # red
    GazeState.AWAY_RIGHT: (0, 0, 220),  # red
    GazeState.LOOKING_DOWN: (0, 200, 220),  # yellow
    GazeState.EYES_CLOSED: (160, 160, 160),  # gray
}


def _run_demo() -> None:
    """Open the webcam, run head pose + iris tracking each frame, classify
    gaze, and overlay a color-coded label. Press 'q' to quit.

    Note: this uses the FaceMeshDetector from src.detection.face_mesh
    directly for landmarks, and src.detection.head_pose for pitch/yaw.
    It requires the Face Landmarker model to output the full 478-point
    set (iris landmarks 468-477) -- if only 468 points are available,
    iris_ratio falls back to 0.5 (centered) and gaze relies on head pose
    alone for that frame.
    """
    import cv2

    from src.detection.face_mesh import FaceMeshDetector
    from src.detection.head_pose import estimate_head_pose

    detector = FaceMeshDetector()
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Could not open webcam.")
        return

    print("Press 'q' to quit.")
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            h, w = frame.shape[:2]
            result = detector.detect(frame)

            state = GazeState.EYES_CLOSED
            label = "no_face"

            if result.faces:
                landmarks = result.faces[0].landmarks
                px_landmarks = [(x * w, y * h) for x, y, _ in landmarks]

                pose = estimate_head_pose(landmarks, frame.shape)
                pitch, yaw = (pose[0], pose[1]) if pose is not None else (0.0, 0.0)

                iris_ratio = compute_iris_ratio(px_landmarks)
                if iris_ratio is None:
                    iris_ratio = 0.5

                ear = compute_ear(px_landmarks)

                state = classify_gaze(
                    pitch=pitch, yaw=yaw, iris_ratio=iris_ratio, ear=ear
                )
                label = (
                    f"{state.value} (pitch={pitch:.1f} yaw={yaw:.1f} "
                    f"iris={iris_ratio:.2f} ear={ear:.2f})"
                )

            color = _DEMO_COLORS_BGR.get(state, (255, 255, 255))
            cv2.rectangle(frame, (0, 0), (w, 50), color, -1)
            cv2.putText(
                frame,
                label,
                (10, 32),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 0, 0),
                2,
            )
            cv2.imshow("Gaze Classifier Demo (q to quit)", frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        detector.close()
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Gaze classifier demo")
    parser.add_argument("--demo", action="store_true", help="Run live webcam demo")
    args = parser.parse_args()

    if args.demo:
        _run_demo()
    else:
        parser.print_help()
