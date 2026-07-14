"""Yawn detection using Mouth Aspect Ratio (MAR) plus hand-over-mouth support.

This module provides:
- MAR computation from lip landmarks
- hand-over-mouth overlap detection
- jaw and eye motion helpers for hidden yawns
- a live webcam demo for rapid verification
"""

from __future__ import annotations

import math
import time
from typing import Iterable

MOUTH_LEFT = 61
MOUTH_RIGHT = 291
MOUTH_TOP = 13
MOUTH_BOTTOM = 14
CHIN = 152
EYE_A_EAR_POINTS = (33, 160, 158, 133, 153, 144)
EYE_B_EAR_POINTS = (362, 385, 387, 263, 373, 380)


def _distance(point_a: tuple[float, float], point_b: tuple[float, float]) -> float:
    return math.hypot(point_a[0] - point_b[0], point_a[1] - point_b[1])


def _normalize_bbox(
    bbox: list[float] | tuple[float, float, float, float],
    frame_size: tuple[int, int] | None = None,
) -> tuple[float, float, float, float] | None:
    if not bbox or len(bbox) != 4:
        return None

    x_min, y_min, x_max, y_max = bbox
    if frame_size is not None and max(abs(v) for v in bbox) <= 1.0:
        width, height = frame_size
        x_min *= width
        x_max *= width
        y_min *= height
        y_max *= height

    return x_min, y_min, x_max, y_max


def _mouth_bbox_from_landmarks(
    landmarks: list[tuple[float, float] | tuple[float, float, float]],
    padding: float = 0.25,
) -> tuple[float, float, float, float] | None:
    if not landmarks or len(landmarks) <= max(
        MOUTH_LEFT, MOUTH_RIGHT, MOUTH_TOP, MOUTH_BOTTOM
    ):
        return None

    left = landmarks[MOUTH_LEFT]
    right = landmarks[MOUTH_RIGHT]
    top = landmarks[MOUTH_TOP]
    bottom = landmarks[MOUTH_BOTTOM]

    x_min = min(left[0], right[0], top[0], bottom[0])
    x_max = max(left[0], right[0], top[0], bottom[0])
    y_min = min(left[1], right[1], top[1], bottom[1])
    y_max = max(left[1], right[1], top[1], bottom[1])

    width = x_max - x_min
    height = y_max - y_min
    if width <= 0 or height <= 0:
        return None

    pad_x = width * padding
    pad_y = height * padding
    return x_min - pad_x, y_min - pad_y, x_max + pad_x, y_max + pad_y


def _intersection_area(
    bbox_a: tuple[float, float, float, float],
    bbox_b: tuple[float, float, float, float],
) -> float:
    x_min = max(bbox_a[0], bbox_b[0])
    y_min = max(bbox_a[1], bbox_b[1])
    x_max = min(bbox_a[2], bbox_b[2])
    y_max = min(bbox_a[3], bbox_b[3])

    if x_max <= x_min or y_max <= y_min:
        return 0.0
    return (x_max - x_min) * (y_max - y_min)


def is_hand_over_mouth(
    hand_bboxes: Iterable[list[float] | tuple[float, float, float, float] | dict],
    face_landmarks: list[tuple[float, float, float]],
    frame_size: tuple[int, int] | None = None,
    mouth_padding: float = 0.25,
    min_overlap_ratio: float = 0.15,
) -> bool:
    """Return True if any hand bbox overlaps the mouth region."""
    mouth_bbox = _mouth_bbox_from_landmarks(face_landmarks, padding=mouth_padding)
    if mouth_bbox is None:
        return False

    if frame_size is not None and max(abs(v) for v in mouth_bbox) <= 1.0:
        width, height = frame_size
        mouth_bbox = (
            mouth_bbox[0] * width,
            mouth_bbox[1] * height,
            mouth_bbox[2] * width,
            mouth_bbox[3] * height,
        )

    mouth_area = max(
        0.0, (mouth_bbox[2] - mouth_bbox[0]) * (mouth_bbox[3] - mouth_bbox[1])
    )
    if mouth_area == 0.0:
        return False

    for raw_bbox in hand_bboxes:
        if isinstance(raw_bbox, dict):
            raw_bbox = (
                raw_bbox.get("bbox")
                or raw_bbox.get("box")
                or raw_bbox.get("bbox_xyxy")
                or raw_bbox.get("xyxy")
            )
        if not raw_bbox:
            continue

        hand_bbox = _normalize_bbox(raw_bbox, frame_size=frame_size)
        if hand_bbox is None:
            continue

        overlap = _intersection_area(mouth_bbox, hand_bbox)
        if overlap / mouth_area >= min_overlap_ratio:
            return True

    return False


def compute_mar(mouth_landmarks: list[tuple[float, float]]) -> float:
    """Compute Mouth Aspect Ratio from lip landmarks.

    Supports two input formats:
    - Full face mesh (468+ landmarks): uses MediaPipe indexes 61, 291, 13, 14
    - 4-point subset in order: [left_corner, top_lip, right_corner, bottom_lip]

    MAR = vertical_opening / horizontal_width

    A closed mouth gives MAR ~0.0-0.3
    Speech gives MAR ~0.3-0.5 (brief)
    A yawn gives MAR ~0.6+ (sustained)
    """ 
    if not mouth_landmarks or len(mouth_landmarks) < 4:
        return 0.0

    try:
        if len(mouth_landmarks) >= 292: 
            left = mouth_landmarks[61]
            top = mouth_landmarks[13]
            right = mouth_landmarks[291]
            bottom = mouth_landmarks[14]
        else: 
            left = mouth_landmarks[0]
            top = mouth_landmarks[1]
            right = mouth_landmarks[2]
            bottom = mouth_landmarks[3]

        vertical_dist = _distance((top[0], top[1]), (bottom[0], bottom[1]))
        horizontal_dist = _distance((left[0], left[1]), (right[0], right[1]))
        if horizontal_dist == 0.0:
            return 0.0
        return vertical_dist / horizontal_dist 

    except (IndexError, TypeError, ValueError):
        return 0.0


def compute_eye_aspect_ratio(
    landmarks: list[tuple[float, float, float]]
) -> float:
    """Compute average EAR for both eyes from face landmarks."""
    if not landmarks or len(landmarks) <= max(EYE_A_EAR_POINTS + EYE_B_EAR_POINTS):
        return 0.0

    def _ear(points: tuple[int, int, int, int, int, int]) -> float:
        p1, p2, p3, p4, p5, p6 = (landmarks[i] for i in points)
        p1, p2, p3, p4, p5, p6 = [tuple(pt[:2]) for pt in (p1, p2, p3, p4, p5, p6)]
        vertical = _distance(p2, p6) + _distance(p3, p5)
        horizontal = 2.0 * _distance(p1, p4)
        if horizontal == 0.0:
            return 0.0
        return vertical / horizontal

    return (_ear(EYE_A_EAR_POINTS) + _ear(EYE_B_EAR_POINTS)) / 2.0


def compute_jaw_ratio(
    landmarks: list[tuple[float, float, float]]
) -> float:
    """Compute jaw drop ratio relative to mouth width."""
    if not landmarks or len(landmarks) <= max(
        MOUTH_LEFT, MOUTH_RIGHT, MOUTH_TOP, MOUTH_BOTTOM, CHIN
    ):
        return 0.0

    left = landmarks[MOUTH_LEFT]
    right = landmarks[MOUTH_RIGHT]
    top = landmarks[MOUTH_TOP]
    bottom = landmarks[MOUTH_BOTTOM]
    chin = landmarks[CHIN]

    mouth_center = ((top[0] + bottom[0]) / 2.0, (top[1] + bottom[1]) / 2.0)
    jaw_height = max(0.0, chin[1] - mouth_center[1])
    mouth_width = _distance((left[0], left[1]), (right[0], right[1]))
    if mouth_width == 0.0:
        return 0.0
    return jaw_height / mouth_width


def _is_yawn_supported(
    hand_on_mouth: bool,
    jaw_motion: bool,
    head_motion: bool,
    eye_fatigue: bool,
) -> bool:
    """Decide whether auxiliary cues support a yawn.

    Policy:
    - If a hand is detected over the mouth, a single supporting cue
      (jaw_motion or head_motion or eye_fatigue) is sufficient.
    - If no hand is detected (hidden-yawn without hand detector), require
      at least two supporting cues to reduce false positives.
    """
    supports = sum(bool(v) for v in (jaw_motion, head_motion, eye_fatigue))
    if hand_on_mouth:
        return supports >= 1
    # No hand available: require two independent supporting cues
    return supports >= 2


class YawnDetector:
    """Tracks yawns and supports hidden-yawn evidence.

    This detector counts a yawn when either:
    - MAR is above threshold for a sustained duration, or
    - hand-over-mouth is present plus an additional yaw-like cue.
    """

    FATIGUE_YAWN_COUNT = 3

    def __init__(self, mar_threshold: float = 0.6, yawn_duration: float = 2.0): 
        self.mar_threshold = mar_threshold
        self.yawn_duration = yawn_duration
        self.yawn_count = 0
        self._yawn_timestamps: list[float] = [] 
        self._is_yawning = False
        self._yawn_start_time = 0.0
        self._yawn_recorded = False
        # Track recent MAR opens to handle brief occlusions (hand covers mouth)
        self._last_mar_open_time: float | None = None
        # Grace period (s) during which a recent MAR-open can act as an occlusion proxy
        self.occlusion_grace: float = 1.5

    def update(
        self,
        mar: float,
        timestamp: float,
        hand_on_mouth: bool = False,
        jaw_motion: bool = False,
        head_motion: bool = False,
        eye_fatigue: bool = False,
    ) -> bool:
        """Update detector with current frame evidence.

        Args:
            mar: Current mouth aspect ratio.
            timestamp: Current time in seconds.
            hand_on_mouth: True if a hand overlaps the mouth region.
            jaw_motion: True if jaw/chin motion supports a yawn.
            head_motion: True if head pose supports a yawn.
            eye_fatigue: True if eye closure/fatigue supports a yawn.

        Returns:
            True when a new yawn is confirmed on this frame.
        """
        yawn_detected = False
        # update last MAR-open timestamp
        if mar >= self.mar_threshold:
            self._last_mar_open_time = timestamp

        mar_recent_open = (
            self._last_mar_open_time is not None
            and (timestamp - self._last_mar_open_time) <= self.occlusion_grace
        )

        # treat recent MAR-open as a proxy for a hand covering the mouth
        effective_hand_on_mouth = hand_on_mouth or mar_recent_open

        support = _is_yawn_supported(
            hand_on_mouth=effective_hand_on_mouth,
            jaw_motion=jaw_motion,
            head_motion=head_motion,
            eye_fatigue=eye_fatigue,
        )

        yawn_open = mar >= self.mar_threshold or support

        if yawn_open:
            if not self._is_yawning: 
                self._is_yawning = True
                self._yawn_start_time = timestamp
                self._yawn_recorded = False
            else:
                duration = timestamp - self._yawn_start_time
                if duration >= self.yawn_duration and not self._yawn_recorded:
                    self.yawn_count += 1
                    self._yawn_timestamps.append(timestamp)
                    self._yawn_recorded = True 
                    yawn_detected = True
        else: 
            self._is_yawning = False
            self._yawn_recorded = False

        return yawn_detected

    def record_yawn(self, timestamp: float) -> None:
        self.yawn_count += 1 
        self._yawn_timestamps.append(timestamp)

    def is_fatigued(
        self,
        window_seconds: float = 600.0,
        current_time: float | None = None,
        ear_values: Iterable[float] | None = None,
        ear_threshold: float = 0.20,
    ) -> bool:
        """Check if fatigue is detected based on yawn frequency and optional EAR data.

        Args:
            window_seconds: Time window to count yawns in (default 600s).
            current_time: Reference time for the window. If None uses last yawn time.
            ear_values: Optional iterable of recent EAR values (most recent first).
            ear_threshold: EAR threshold below which eyes are considered fatigued.

        Returns:
            True if combined evidence meets the fatigue rule (3+ yawns).
        """
        if not self._yawn_timestamps and not ear_values:
            return False

        reference = (
            current_time if current_time is not None else (
                self._yawn_timestamps[-1] if self._yawn_timestamps else time.time()
            )
        )
        cutoff = reference - window_seconds
        recent_yawns = sum(1 for t in self._yawn_timestamps if t >= cutoff)

        # If EAR data present, interpret sustained low EAR as additional evidence.
        ear_evidence = 0
        if ear_values:
            ear_list = list(ear_values)
            if ear_list:
                low_count = sum(1 for v in ear_list if v > 0.0 and v < ear_threshold)
                # If more than half the provided EAR samples are below threshold,
                # treat as one additional 'yawn-equivalent' in the window.
                if low_count >= (len(ear_list) / 2.0):
                    ear_evidence = 1

        total_recent = recent_yawns + ear_evidence
        return total_recent >= self.FATIGUE_YAWN_COUNT

    def reset(self) -> None: 
        self.yawn_count = 0
        self._yawn_timestamps.clear()
        self._is_yawning = False
        self._yawn_start_time = 0.0
        self._yawn_recorded = False


def _run_demo(camera_index: int = 0) -> None:
    try: 
        import cv2

        from src.detection.face_mesh import FaceMeshDetector
    except ImportError as exc:
        raise RuntimeError(
            "OpenCV and FaceMeshDetector are required for the demo."
        ) from exc

    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        raise ConnectionError(f"Could not open webcam {camera_index}")

    detector = FaceMeshDetector()
    yawn_detector = YawnDetector(mar_threshold=0.6, yawn_duration=2.0)

    print("Yawn Demo running. Press Q to quit.")

    try:
        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                break

            h, w = frame.shape[:2]
            result = detector.detect(frame)

            mar = 0.0
            is_yawning_now = False
            fatigued = False

            if result and getattr(result, "faces", None):
                face = result.faces[0]
                px_landmarks = [(lm[0] * w, lm[1] * h) for lm in face.landmarks]
                mar = compute_mar(px_landmarks)

                # Compute additional cues (jaw, eyes, head pose)
                jaw_ratio = compute_jaw_ratio(face.landmarks)
                ear = compute_eye_aspect_ratio(face.landmarks)
                pose = None
                try:
                    from src.detection.head_pose import estimate_head_pose

                    pose = estimate_head_pose(face.landmarks, frame.shape)
                except Exception:
                    pose = None

                jaw_motion = jaw_ratio > 0.08
                eye_fatigue = ear < 0.20 and ear > 0.0
                head_motion = False
                if pose is not None:
                    pitch, yaw, roll = pose
                    head_motion = abs(pitch) >= 10.0

                current_time = time.time()
                # Pass auxiliary cues even when hand detection is not used
                yawn_detector.update(
                    mar,
                    current_time,
                    hand_on_mouth=False,
                    jaw_motion=jaw_motion,
                    head_motion=head_motion,
                    eye_fatigue=eye_fatigue,
                )

                is_yawning_now = yawn_detector._is_yawning and (
                    current_time - yawn_detector._yawn_start_time
                    >= yawn_detector.yawn_duration
                )
                fatigued = yawn_detector.is_fatigued(current_time=current_time)

                for idx in [61, 13, 291, 14]:
                    if idx < len(face.landmarks):
                        lm = face.landmarks[idx]
                        pt = (int(lm[0] * w), int(lm[1] * h))
                        color = (0, 0, 255) if mar > 0.6 else (0, 255, 0)
                        cv2.circle(frame, pt, 3, color, -1)

                # Overlay auxiliary cue states
                cv2.putText(
                    frame,
                    f"jaw:{jaw_ratio:.2f} ear:{ear:.2f} head:{'Y' if head_motion else 'N'}",
                    (15, 60),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (200, 200, 200),
                    2,
                )

            cv2.putText(
                frame,
                f"MAR: {mar:.3f} | Yawns: {yawn_detector.yawn_count}",
                (15, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 255, 255),
                2,
            )

            if is_yawning_now:
                cv2.putText(
                    frame,
                    "YAWNING DETECTED!",
                    (15, 70),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1.0,
                    (0, 0, 255),
                    3,
                )

            if fatigued:
                cv2.putText(
                    frame,
                    "FATIGUE DETECTED!",
                    (15, 110),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1.0,
                    (0, 255, 255),
                    3,
                )

            cv2.imshow("Yawn Detection Demo", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    finally:
        cap.release()
        cv2.destroyAllWindows()
        detector.close()


def main() -> None: 
    import argparse

    parser = argparse.ArgumentParser(description="EngageIQ Yawn Detection Demo.")
    parser.add_argument("--demo", action="store_true", help="Run webcam demo.")
    parser.add_argument("--camera", type=int, default=0, help="Webcam index.")
    args = parser.parse_args()

    if args.demo:
        _run_demo(camera_index=args.camera)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
