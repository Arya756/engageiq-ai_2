"""
Drowsiness detection using EAR (Eye Aspect Ratio).

Basic idea: when eyes close, the EAR value drops. If it stays low
for too long, we say the person is drowsy.
"""

import math


def compute_ear(eye_landmarks: list[tuple[float, float]]) -> float:
    """Work out the Eye Aspect Ratio (EAR) from 6 points around the eye.

    Args:
        eye_landmarks: A list of 6 (x, y) points around the eye.
                       Order is usually: [p1, p2, p3, p4, p5, p6]
                       - p1 and p4 are the left and right corners of the eye
                       - p2/p6 and p3/p5 are the top and bottom points

    Returns:
        The EAR as a number. If it's below 0.25, the eye is probably closed.
    """
    if len(eye_landmarks) != 6:
        raise ValueError("Exactly 6 landmarks are required to compute EAR.")

    # Distance between the top and bottom points (two pairs)
    vertical_1 = math.hypot(
        eye_landmarks[1][0] - eye_landmarks[5][0],
        eye_landmarks[1][1] - eye_landmarks[5][1],
    )
    vertical_2 = math.hypot(
        eye_landmarks[2][0] - eye_landmarks[4][0],
        eye_landmarks[2][1] - eye_landmarks[4][1],
    )

    # Distance between the left and right corners of the eye
    horizontal = math.hypot(
        eye_landmarks[0][0] - eye_landmarks[3][0],
        eye_landmarks[0][1] - eye_landmarks[3][1],
    )

    # Just in case, don't divide by zero
    if horizontal == 0:
        return 0.0

    ear = (vertical_1 + vertical_2) / (2.0 * horizontal)
    return ear


class DrowsinessDetector:
    """Keeps track of how long the eyes have been closed and flags drowsiness."""

    def __init__(self, ear_threshold: float = 0.25, drowsy_duration: float = 1.5):
        # If EAR goes below this, we count the eye as closed
        self.ear_threshold = ear_threshold
        # How many seconds the eyes need to stay closed before we call it "drowsy"
        self.drowsy_duration = drowsy_duration
        # Remembers when the eyes first closed (None means eyes are open)
        self._closed_start = None

    def update(self, ear: float, timestamp: float) -> bool:
        """Feed in the latest EAR reading and check if the person looks drowsy.

        Args:
            ear: The current Eye Aspect Ratio.
            timestamp: The current time in seconds.

        Returns:
            True if the eyes have been closed longer than drowsy_duration.
        """
        if ear < self.ear_threshold:
            # Eyes look closed. Start the timer if it's not already running.
            if self._closed_start is None:
                self._closed_start = timestamp

            # If eyes have stayed closed long enough, flag it as drowsy
            if (timestamp - self._closed_start) >= self.drowsy_duration:
                return True
        else:
            # Eyes are open again, so reset the timer
            self._closed_start = None

        return False


if __name__ == "__main__":
    import argparse
    import time

    import cv2

    from src.detection.face_mesh import FaceMeshDetector

    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true", help="Run webcam demo")
    args = parser.parse_args()

    if args.demo:
        detector = FaceMeshDetector()
        drowsiness_detector = DrowsinessDetector(
            ear_threshold=0.25, drowsy_duration=1.5
        )

        cap = cv2.VideoCapture(0)
        print("Starting Drowsiness Detection demo. Press 'q' to quit.")
        print("Close your eyes for 1.5+ seconds to trigger DROWSY state.")

        # These numbers are the standard MediaPipe eye landmark positions
        LEFT_EYE = [33, 160, 158, 133, 153, 144]
        RIGHT_EYE = [362, 385, 387, 263, 373, 380]

        while cap.isOpened():
            success, frame = cap.read()
            if not success:
                continue

            # Flip so it feels like a mirror
            frame = cv2.flip(frame, 1)

            # Run face detection on this frame
            result = detector.detect(frame)

            # Only continue if we actually found a face
            if result.faces:
                # Just use the first face we see
                face = result.faces[0]
                h, w, _ = frame.shape

                # Convert the normalized landmark points into actual pixel positions
                left_eye = [
                    (face.landmarks[i][0] * w, face.landmarks[i][1] * h)
                    for i in LEFT_EYE
                ]
                right_eye = [
                    (face.landmarks[i][0] * w, face.landmarks[i][1] * h)
                    for i in RIGHT_EYE
                ]

                # Draw small dots on the eye points so we can see them on screen
                for pt in left_eye + right_eye:
                    # cv2.circle needs whole numbers for pixel positions
                    cv2.circle(frame, (int(pt[0]), int(pt[1])), 2, (0, 255, 255), -1)

                # Get the EAR for each eye and average them
                left_ear = compute_ear(left_eye)
                right_ear = compute_ear(right_eye)
                avg_ear = (left_ear + right_ear) / 2.0

                # Check if this counts as drowsy yet
                is_drowsy = drowsiness_detector.update(avg_ear, time.time())

                # Show the EAR value on screen, green if open, red if closed
                color = (
                    (0, 0, 255)
                    if avg_ear < drowsiness_detector.ear_threshold
                    else (0, 255, 0)
                )
                cv2.putText(
                    frame,
                    f"EAR: {avg_ear:.3f}",
                    (30, 50),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1,
                    color,
                    2,
                )

                # Show a big warning if the person is drowsy
                if is_drowsy:
                    cv2.putText(
                        frame,
                        "DROWSY!",
                        (30, 100),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        1.5,
                        (0, 0, 255),
                        3,
                    )

            cv2.imshow("Drowsiness Demo", frame)
            if cv2.waitKey(5) & 0xFF == ord("q"):
                break

        cap.release()
        cv2.destroyAllWindows()
