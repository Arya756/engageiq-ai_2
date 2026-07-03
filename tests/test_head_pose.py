"""
Tests for src.detection.head_pose.

These tests generate synthetic facial landmarks by projecting the canonical
3D face model with a known camera matrix and known head pose. Since the
ground truth is known exactly, we can verify that estimate_head_pose()
recovers the expected pitch, yaw and roll.
"""

import cv2
import numpy as np
import pytest

from src.detection.head_pose import (
    LANDMARK_INDICES,
    MODEL_POINTS_3D,
    estimate_head_pose,
)

FRAME_SHAPE = (480, 640, 3)
NUM_LANDMARKS = 468
ANGLE_TOLERANCE_DEG = 2.0


# -------------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------------


def _camera_matrix(frame_shape=FRAME_SHAPE):
    """Camera matrix matching the implementation."""
    h, w = frame_shape[:2]

    return np.array(
        [
            [w, 0, w / 2],
            [0, w, h / 2],
            [0, 0, 1],
        ],
        dtype=np.float64,
    )


def _rotation_vector_from_euler(pitch_deg, yaw_deg, roll_deg):
    """
    Convert Euler angles into an OpenCV rotation vector.

    Rotation order matches head_pose.py:
        R = Rz(yaw) @ Ry(pitch) @ Rx(roll)
    """

    pitch, yaw, roll = np.radians([pitch_deg, yaw_deg, roll_deg])

    cx, sx = np.cos(roll), np.sin(roll)
    cy, sy = np.cos(pitch), np.sin(pitch)
    cz, sz = np.cos(yaw), np.sin(yaw)

    rx = np.array(
        [
            [1, 0, 0],
            [0, cx, -sx],
            [0, sx, cx],
        ]
    )

    ry = np.array(
        [
            [cy, 0, sy],
            [0, 1, 0],
            [-sy, 0, cy],
        ]
    )

    rz = np.array(
        [
            [cz, -sz, 0],
            [sz, cz, 0],
            [0, 0, 1],
        ]
    )

    rotation_matrix = rz @ ry @ rx

    rvec, _ = cv2.Rodrigues(rotation_matrix)

    return rvec


def _synthetic_landmarks(
    pitch=0,
    yaw=0,
    roll=0,
    frame_shape=FRAME_SHAPE,
):
    """
    Generate a synthetic 468-landmark array representing
    a face with a known pose.
    """

    camera_matrix = _camera_matrix(frame_shape)

    rvec = _rotation_vector_from_euler(
        pitch,
        yaw,
        roll,
    )

    tvec = np.array(
        [
            [0.0],
            [0.0],
            [700.0],
        ]
    )

    projected, _ = cv2.projectPoints(
        MODEL_POINTS_3D,
        rvec,
        tvec,
        camera_matrix,
        np.zeros((4, 1)),
    )

    projected = projected.reshape(-1, 2)

    landmarks = [(0.0, 0.0, 0.0)] * NUM_LANDMARKS

    for i, landmark_idx in enumerate(LANDMARK_INDICES):
        landmarks[landmark_idx] = (
            float(projected[i, 0]),
            float(projected[i, 1]),
            0.0,
        )

    return landmarks


# -------------------------------------------------------------------------
# Pose estimation tests
# -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "pitch,yaw,roll",
    [
        (0, 0, 0),
        (0, 30, 0),
        (0, -30, 0),
        (-45, 0, 0),
        (0, 0, 20),
        (15, 20, -10),
    ],
)
def test_pose_accuracy(pitch, yaw, roll):

    landmarks = _synthetic_landmarks(
        pitch=pitch,
        yaw=yaw,
        roll=roll,
    )

    pose = estimate_head_pose(
        landmarks,
        FRAME_SHAPE,
    )

    assert pose is not None

    est_pitch, est_yaw, est_roll = pose

    assert est_pitch == pytest.approx(
        pitch,
        abs=ANGLE_TOLERANCE_DEG,
    )

    assert est_yaw == pytest.approx(
        yaw,
        abs=ANGLE_TOLERANCE_DEG,
    )

    assert est_roll == pytest.approx(
        roll,
        abs=ANGLE_TOLERANCE_DEG,
    )


# -------------------------------------------------------------------------
# Error handling
# -------------------------------------------------------------------------


def test_returns_none_when_landmarks_missing():

    landmarks = [(0.0, 0.0, 0.0)] * 100

    assert (
        estimate_head_pose(
            landmarks,
            FRAME_SHAPE,
        )
        is None
    )


def test_returns_none_when_reference_point_nan():

    landmarks = _synthetic_landmarks()

    landmarks[LANDMARK_INDICES[0]] = (
        float("nan"),
        float("nan"),
        0.0,
    )

    assert (
        estimate_head_pose(
            landmarks,
            FRAME_SHAPE,
        )
        is None
    )


def test_returns_none_for_degenerate_points():
    """
    All six landmarks collapse to one point.
    solvePnP should fail gracefully.
    """

    landmarks = [(100.0, 100.0, 0.0)] * NUM_LANDMARKS

    pose = estimate_head_pose(
        landmarks,
        FRAME_SHAPE,
    )

    assert pose is None


# -------------------------------------------------------------------------
# Output format
# -------------------------------------------------------------------------


def test_returns_float_tuple():

    pose = estimate_head_pose(
        _synthetic_landmarks(
            pitch=10,
            yaw=15,
            roll=5,
        ),
        FRAME_SHAPE,
    )

    assert pose is not None

    assert len(pose) == 3

    assert all(isinstance(value, float) for value in pose)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
