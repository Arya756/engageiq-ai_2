"""Yawn detection using Mouth Aspect Ratio (MAR).

MAR works analogously to EAR but for the mouth:
- Computes ratio of vertical mouth opening to horizontal mouth width
- Normal speech: MAR 0.2-0.5, duration < 0.5 seconds
- Yawn: MAR > 0.6, sustained for 2+ seconds
"""

from __future__ import annotations

import math
import time


def compute_mar(mouth_landmarks: list[tuple[float, float]]) -> float:
    """Compute Mouth Aspect Ratio from lip landmarks.

    Supports two input formats:
    - Full face mesh (468+ landmarks): uses MediaPipe indexes 61, 291, 13, 14
    - 4-point subset in order: [left_corner, top_lip, right_corner, bottom_lip]

    MAR = vertical_opening / horizontal_width

    A closed mouth gives MAR ~0.0-0.3
    Speech gives MAR ~0.3-0.5 (brief)
    A yawn gives MAR ~0.6+ (sustained)

    Args:
        mouth_landmarks: List of (x, y) tuples representing lip landmarks.
            Either full face mesh (468+) or 4-point subset.

    Returns:
        MAR value as float >= 0.0.
        Above 0.6 indicates open mouth (potential yawn).
    """
    if not mouth_landmarks or len(mouth_landmarks) < 4:
        return 0.0

    try:
        if len(mouth_landmarks) >= 292:
            # Full face mesh passed — use MediaPipe mouth landmark indexes
            left = mouth_landmarks[61]
            top = mouth_landmarks[13]
            right = mouth_landmarks[291]
            bottom = mouth_landmarks[14]
        else:
            # 4-point subset: [left, top, right, bottom]
            left = mouth_landmarks[0]
            top = mouth_landmarks[1]
            right = mouth_landmarks[2]
            bottom = mouth_landmarks[3]

        vertical_dist = math.sqrt((top[0] - bottom[0]) ** 2 + (top[1] - bottom[1]) ** 2)
        horizontal_dist = math.sqrt(
            (left[0] - right[0]) ** 2 + (left[1] - right[1]) ** 2
        )

        if horizontal_dist == 0.0:
            return 0.0

        return vertical_dist / horizontal_dist

    except (IndexError, TypeError, ValueError):
        return 0.0


class YawnDetector:
    """Detects yawns from sustained mouth opening and tracks frequency.

    Distinguishes yawns from speech by requiring sustained mouth opening
    above the MAR threshold for at least `yawn_duration` seconds.
    Normal speech opens and closes rapidly (< 0.5 seconds) and will
    not trigger yawn detection.

    Example:
        detector = YawnDetector(mar_threshold=0.6, yawn_duration=2.0)
        is_yawning = detector.update(mar=0.75, timestamp=time.time())
        is_tired = detector.is_fatigued()
    """

    FATIGUE_YAWN_COUNT = 3

    def __init__(self, mar_threshold: float = 0.6, yawn_duration: float = 2.0):
        """Initialize YawnDetector.

        Args:
            mar_threshold: MAR value above which mouth is considered open.
                Default 0.6 distinguishes yawns from normal speech.
            yawn_duration: Seconds of sustained opening required to
                count as a yawn. Default 1.5s filters out speech.
        """
        self.mar_threshold = mar_threshold
        self.yawn_duration = yawn_duration
        self.yawn_count = 0
        self._yawn_timestamps: list[float] = []

        # Internal state for tracking ongoing yawn
        self._is_yawning = False
        self._yawn_start_time = 0.0
        self._yawn_recorded = False

    def update(self, mar: float, timestamp: float) -> bool:
        """Update detector with new MAR reading.

        Call this once per frame with the current MAR value and timestamp.
        Internally tracks how long the mouth has been open. A yawn is
        confirmed only after sustained opening > yawn_duration seconds,
        which filters out brief speech movements.

        Args:
            mar: Current Mouth Aspect Ratio (from compute_mar).
            timestamp: Current time in seconds (e.g. time.time()).

        Returns:
            True if a new yawn was just confirmed at this update.
            Returns False for all frames during speech or closed mouth.
        """
        yawn_detected = False

        if mar >= self.mar_threshold:
            if not self._is_yawning:
                # Mouth just opened — start timing
                self._is_yawning = True
                self._yawn_start_time = timestamp
                self._yawn_recorded = False
            else:
                duration = timestamp - self._yawn_start_time
                if duration >= self.yawn_duration and not self._yawn_recorded:
                    self._yawn_timestamps.append(timestamp)
                    self.yawn_count += 1
                    self._yawn_recorded = True
                    yawn_detected = True
        else:
            # Mouth closed — reset tracking
            self._is_yawning = False
            self._yawn_recorded = False

        return yawn_detected

    def record_yawn(self, timestamp: float) -> None:
        """Manually record a yawn at the given timestamp.

        Useful for testing and for external systems that detect yawns
        through other means and want to feed into fatigue tracking.

        Args:
            timestamp: Time in seconds when the yawn occurred.
        """
        self.yawn_count += 1
        self._yawn_timestamps.append(timestamp)

    def is_fatigued(
        self,
        window_seconds: float = 600.0,
        current_time: float | None = None,
    ) -> bool:
        """Check if fatigue is detected based on yawn frequency.

        Fatigue is triggered when 3 or more yawns occur within
        the given time window (default 10 minutes / 600 seconds).

        Args:
            window_seconds: Time window to count yawns in. Default 600s
                (10 minutes) as per the issue spec.
            current_time: Reference time for the window. If None, uses
                the latest recorded yawn timestamp. Pass time.time() for
                real-time use.

        Returns:
            True if 3+ yawns occurred within the window.
        """
        if not self._yawn_timestamps:
            return False

        reference = (
            current_time if current_time is not None else self._yawn_timestamps[-1]
        )
        cutoff = reference - window_seconds
        recent = sum(1 for t in self._yawn_timestamps if t >= cutoff)
        return recent >= self.FATIGUE_YAWN_COUNT

    def reset(self) -> None:
        """Reset all yawn tracking state."""
        self.yawn_count = 0
        self._yawn_timestamps.clear()
        self._is_yawning = False
        self._yawn_start_time = 0.0
        self._yawn_recorded = False


def _run_demo(camera_index: int = 0) -> None:
    """Run live webcam demo showing MAR and yawn detection."""
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

    print("Yawn Demo running. Yawn naturally to trigger detection. Press Q to quit.")

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

                current_time = time.time()
                yawn_detector.update(mar, current_time)

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
    """Entry point for the yawn detection demo."""
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
