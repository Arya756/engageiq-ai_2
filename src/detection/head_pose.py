"""Head pose estimation using MediaPipe landmarks + OpenCV solvePnP."""

from typing import Optional

import cv2
import numpy as np

# ---------------------------------------------------------------------------
# MediaPipe Face Mesh landmark indices for the 6 reference points we use.
# Standard indices in the 468-point topology.
# ---------------------------------------------------------------------------
NOSE_TIP = 1
CHIN = 152
LEFT_EYE_LEFT_CORNER = 33
RIGHT_EYE_RIGHT_CORNER = 263
LEFT_MOUTH_CORNER = 61
RIGHT_MOUTH_CORNER = 291

LANDMARK_INDICES = [
    NOSE_TIP,
    CHIN,
    LEFT_EYE_LEFT_CORNER,
    RIGHT_EYE_RIGHT_CORNER,
    LEFT_MOUTH_CORNER,
    RIGHT_MOUTH_CORNER,
]

# Generic 3D face model (in mm), same order as LANDMARK_INDICES.
# Widely-used canonical model, nose tip at the origin.
MODEL_POINTS_3D = np.array(
    [
        (0.0, 0.0, 0.0),  # Nose tip
        (0.0, -330.0, -65.0),  # Chin
        (-225.0, 170.0, -135.0),  # Left eye left corner
        (225.0, 170.0, -135.0),  # Right eye right corner
        (-150.0, -150.0, -125.0),  # Left mouth corner
        (150.0, -150.0, -125.0),  # Right mouth corner
    ],
    dtype=np.float64,
)


def _get_camera_matrix(frame_shape: tuple) -> np.ndarray:
    """Approximate camera intrinsics from frame size (no calibration file)."""
    height, width = frame_shape[0], frame_shape[1]
    focal_length = width
    center = (width / 2, height / 2)
    return np.array(
        [
            [focal_length, 0, center[0]],
            [0, focal_length, center[1]],
            [0, 0, 1],
        ],
        dtype=np.float64,
    )


def _extract_2d_points(landmarks: list, frame_shape: tuple) -> Optional[np.ndarray]:
    """Pull the 6 reference points out of the 468 landmarks and convert to
    pixel coordinates.

    `landmarks` is a list of (x, y, z) tuples. Coordinates are treated as
    normalized [0, 1] (MediaPipe's default output) if they never exceed
    ~1.5 in magnitude, otherwise treated as already-in-pixels.
    """
    if landmarks is None:
        return None
    if len(landmarks) <= max(LANDMARK_INDICES):
        return None  # too few landmarks visible -> can't build the 6-point set

    height, width = frame_shape[0], frame_shape[1]

    try:
        ref_points = [landmarks[idx] for idx in LANDMARK_INDICES]
    except IndexError:
        return None

    xy = np.array([(p[0], p[1]) for p in ref_points], dtype=np.float64)
    if np.isnan(xy).any():
        return None  # occluded reference point

    is_normalized = np.max(np.abs(xy)) <= 1.5
    if is_normalized:
        xy[:, 0] *= width
        xy[:, 1] *= height

    # Degenerate configuration guard: if the 6 reference points are all
    # (near-)identical, solvePnP will not fail cleanly -- it can return a
    # "successful" but meaningless pose. Reject that case explicitly.
    spread_x = np.ptp(xy[:, 0])
    spread_y = np.ptp(xy[:, 1])
    MIN_SPREAD_PIXELS = 5.0
    if spread_x < MIN_SPREAD_PIXELS and spread_y < MIN_SPREAD_PIXELS:
        return None

    return xy


def _rotation_vector_to_euler(
    rotation_vector: np.ndarray,
) -> tuple[float, float, float]:
    """Convert solvePnP's rotation vector to pitch/yaw/roll in degrees."""
    rotation_matrix, _ = cv2.Rodrigues(rotation_vector)

    sy = np.sqrt(rotation_matrix[0, 0] ** 2 + rotation_matrix[1, 0] ** 2)
    singular = sy < 1e-6

    if not singular:
        pitch = np.arctan2(-rotation_matrix[2, 0], sy)
        yaw = np.arctan2(rotation_matrix[1, 0], rotation_matrix[0, 0])
        roll = np.arctan2(rotation_matrix[2, 1], rotation_matrix[2, 2])
    else:
        pitch = np.arctan2(-rotation_matrix[2, 0], sy)
        yaw = np.arctan2(-rotation_matrix[1, 2], rotation_matrix[1, 1])
        roll = 0.0

    return (
        float(np.degrees(pitch)),
        float(np.degrees(yaw)),
        float(np.degrees(roll)),
    )


def estimate_head_pose(
    landmarks: list, frame_shape: tuple
) -> Optional[tuple[float, float, float]]:
    """Estimate head pose from facial landmarks.

    Args:
        landmarks: List of 468 (x, y, z) landmark tuples from FaceMeshDetector.
        frame_shape: Shape of the input frame (height, width, channels).

    Returns:
        Tuple of (pitch, yaw, roll) in degrees, or None if pose could not be
        estimated (too few landmarks visible, an occluded reference point,
        or solvePnP failing to converge).

        Note: the return type is widened to Optional here vs. the original
        stub's `tuple[float, float, float]`, since the acceptance criteria
        requires graceful None handling on occlusion.
    """
    image_points = _extract_2d_points(landmarks, frame_shape)
    if image_points is None:
        return None

    camera_matrix = _get_camera_matrix(frame_shape)
    dist_coeffs = np.zeros((4, 1))  # assume no lens distortion

    success, rotation_vector, _translation_vector = cv2.solvePnP(
        MODEL_POINTS_3D,
        image_points,
        camera_matrix,
        dist_coeffs,
        flags=cv2.SOLVEPNP_ITERATIVE,
    )
    if not success:
        return None

    pitch, yaw, roll = _rotation_vector_to_euler(rotation_vector)
    if not all(np.isfinite([pitch, yaw, roll])):
        return None
    return pitch, yaw, roll


def _solve_pnp(landmarks: list, frame_shape: tuple):
    """Internal helper used by the demo to get both the angles and the
    rotation/translation vectors needed to draw the axis gizmo."""
    image_points = _extract_2d_points(landmarks, frame_shape)
    if image_points is None:
        return None

    camera_matrix = _get_camera_matrix(frame_shape)
    dist_coeffs = np.zeros((4, 1))

    success, rotation_vector, translation_vector = cv2.solvePnP(
        MODEL_POINTS_3D,
        image_points,
        camera_matrix,
        dist_coeffs,
        flags=cv2.SOLVEPNP_ITERATIVE,
    )
    if not success:
        return None

    pitch, yaw, roll = _rotation_vector_to_euler(rotation_vector)
    return (
        pitch,
        yaw,
        roll,
        rotation_vector,
        translation_vector,
        camera_matrix,
        image_points[0],
    )


def _draw_axes(
    frame,
    rotation_vector,
    translation_vector,
    camera_matrix,
    nose_tip_2d,
    axis_length=100.0,
):
    """Draw a 3-axis gizmo (red=yaw/X, green=pitch/Y, blue=roll/Z) on the nose tip."""
    axis_points_3d = np.array(
        [(axis_length, 0, 0), (0, axis_length, 0), (0, 0, axis_length), (0, 0, 0)],
        dtype=np.float64,
    )
    dist_coeffs = np.zeros((4, 1))
    projected, _ = cv2.projectPoints(
        axis_points_3d, rotation_vector, translation_vector, camera_matrix, dist_coeffs
    )
    projected = projected.reshape(-1, 2)
    origin = tuple(np.round(projected[3]).astype(int))
    x_axis = tuple(np.round(projected[0]).astype(int))
    y_axis = tuple(np.round(projected[1]).astype(int))
    z_axis = tuple(np.round(projected[2]).astype(int))

    cv2.line(frame, origin, x_axis, (0, 0, 255), 3)  # red = X / yaw
    cv2.line(frame, origin, y_axis, (0, 255, 0), 3)  # green = Y / pitch
    cv2.line(frame, origin, z_axis, (255, 0, 0), 3)  # blue = Z / roll
    return frame


def _run_demo() -> None:
    """Webcam demo: draws 3D axes on the nose tip, prints live pitch/yaw/roll."""
    from src.detection.face_mesh import FaceMeshDetector  # local import, demo only

    detector = FaceMeshDetector()
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Could not open webcam.")
        return

    print("Press 'q' to quit.")
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            result = detector.detect(frame)
            if result is not None and result.faces:
                landmarks = result.faces[0].landmarks
                solved = _solve_pnp(landmarks, frame.shape)
                if solved is not None:
                    pitch, yaw, roll, rvec, tvec, cam_mtx, nose_tip_2d = solved
                    _draw_axes(frame, rvec, tvec, cam_mtx, nose_tip_2d)
                    text = f"Pitch: {pitch:.1f}  Yaw: {yaw:.1f}  Roll: {roll:.1f}"
                    cv2.putText(
                        frame,
                        text,
                        (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        (0, 255, 255),
                        2,
                    )
                else:
                    cv2.putText(
                        frame,
                        "Pose unavailable (occluded)",
                        (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        (0, 0, 255),
                        2,
                    )
            else:
                cv2.putText(
                    frame,
                    "No face detected",
                    (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 0, 255),
                    2,
                )

            cv2.imshow("Head Pose Demo", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Head pose estimation demo")
    parser.add_argument("--demo", action="store_true", help="Run live webcam demo")
    args = parser.parse_args()

    if args.demo:
        _run_demo()
    else:
        parser.print_help()
