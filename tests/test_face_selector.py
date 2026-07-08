import time

from src.detection.face_mesh import DetectedFace
from src.detection.face_selector import FaceSelector


def make_face(x1, y1, x2, y2):
    return DetectedFace(
        landmarks=[],
        confidence=0.9,
        bbox=[x1, y1, x2, y2],
    )


def test_single_face():
    selector = FaceSelector()

    faces = [make_face(0.1, 0.1, 0.4, 0.4)]

    assert selector.select(faces) == 0


def test_multiple_faces_selects_largest():
    selector = FaceSelector()

    faces = [
        make_face(0.1, 0.1, 0.3, 0.3),
        make_face(0.2, 0.2, 0.7, 0.8),
        make_face(0.5, 0.5, 0.6, 0.6),
    ]

    assert selector.select(faces) == 1


def test_no_faces():
    selector = FaceSelector()

    assert selector.select([]) is None


def test_tracking_persistence():
    selector = FaceSelector()

    faces = [
        make_face(0.1, 0.1, 0.5, 0.5),
        make_face(0.6, 0.2, 0.8, 0.4),
    ]

    first = selector.select(faces)
    second = selector.select(faces)

    assert first == second == 0


def test_face_disappears_after_timeout():
    selector = FaceSelector()

    faces = [make_face(0.1, 0.1, 0.4, 0.4)]

    selector.select(faces)

    selector.last_seen = time.time() - 6

    assert selector.select([]) is None
    assert selector.primary_embedding is None
