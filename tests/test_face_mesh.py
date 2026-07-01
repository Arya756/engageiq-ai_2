import sys
import time
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest

from src.detection.face_mesh import LANDMARK_COUNT, FaceMeshDetector


def make_landmarks(count: int, confidence: float):
    denominator = max(count, 1)
    return [
        SimpleNamespace(
            x=index / denominator,
            y=index / denominator,
            z=index / denominator,
            visibility=confidence,
            presence=confidence,
        )
        for index in range(count)
    ]


def make_result(*faces):
    return SimpleNamespace(face_landmarks=list(faces), face_blendshapes=[])


def make_frame():
    return np.zeros((480, 640, 3), dtype=np.uint8)


@pytest.fixture
def install_fake_mediapipe(monkeypatch):
    def _install(result):
        created_landmarkers = []

        fake_mp = ModuleType("mediapipe")
        fake_mp.__path__ = []

        class ImageFormat:
            SRGB = object()

        class Image:
            def __init__(self, image_format, data):
                self.image_format = image_format
                self.data = data

        fake_mp.ImageFormat = ImageFormat
        fake_mp.Image = Image

        fake_tasks = ModuleType("mediapipe.tasks")
        fake_tasks.__path__ = []

        fake_python = ModuleType("mediapipe.tasks.python")
        fake_python.__path__ = []

        class BaseOptions:
            def __init__(self, model_asset_path=None, model_asset_buffer=None):
                self.model_asset_path = model_asset_path
                self.model_asset_buffer = model_asset_buffer

        fake_python.BaseOptions = BaseOptions

        fake_vision = ModuleType("mediapipe.tasks.python.vision")
        fake_vision.__path__ = []

        class RunningMode:
            IMAGE = "IMAGE"

        class FaceLandmarkerOptions:
            def __init__(
                self,
                *,
                base_options,
                running_mode,
                num_faces,
                min_face_detection_confidence,
                min_face_presence_confidence,
                min_tracking_confidence,
                output_face_blendshapes,
                output_facial_transformation_matrixes,
            ):
                self.base_options = base_options
                self.running_mode = running_mode
                self.num_faces = num_faces
                self.min_face_detection_confidence = min_face_detection_confidence
                self.min_face_presence_confidence = min_face_presence_confidence
                self.min_tracking_confidence = min_tracking_confidence
                self.output_face_blendshapes = output_face_blendshapes
                self.output_facial_transformation_matrixes = (
                    output_facial_transformation_matrixes
                )

        class FakeLandmarker:
            def __init__(self, options):
                self.options = options
                self.detect_calls = []
                self.closed = False

            def detect(self, mp_image):
                self.detect_calls.append(mp_image)
                return result

            def close(self):
                self.closed = True

        class FaceLandmarker:
            @staticmethod
            def create_from_options(options):
                landmarker = FakeLandmarker(options)
                created_landmarkers.append(landmarker)
                return landmarker

        fake_vision.FaceLandmarker = FaceLandmarker
        fake_vision.FaceLandmarkerOptions = FaceLandmarkerOptions
        fake_vision.RunningMode = RunningMode

        fake_tasks.python = fake_python
        fake_python.vision = fake_vision
        fake_mp.tasks = fake_tasks

        monkeypatch.setitem(sys.modules, "mediapipe", fake_mp)
        monkeypatch.setitem(sys.modules, "mediapipe.tasks", fake_tasks)
        monkeypatch.setitem(sys.modules, "mediapipe.tasks.python", fake_python)
        monkeypatch.setitem(sys.modules, "mediapipe.tasks.python.vision", fake_vision)

        return fake_mp, created_landmarkers

    return _install


def test_lazy_initialization_and_single_face(install_fake_mediapipe, tmp_path):
    fake_result = make_result(make_landmarks(478, 0.93))
    fake_mp, created_landmarkers = install_fake_mediapipe(fake_result)

    model_path = tmp_path / "face_landmarker.task"
    model_path.write_bytes(b"fake-model")

    detector = FaceMeshDetector(model_path=str(model_path))
    assert detector._landmarker is None

    frame = make_frame()
    result = detector.detect(frame)

    assert len(created_landmarkers) == 1
    landmarker = created_landmarkers[0]
    assert detector._landmarker is landmarker
    assert landmarker.options.base_options.model_asset_path == str(model_path)
    assert landmarker.options.running_mode == "IMAGE"
    assert landmarker.options.num_faces == 1
    assert landmarker.options.min_face_detection_confidence == pytest.approx(0.5)
    assert landmarker.options.min_face_presence_confidence == pytest.approx(0.5)
    assert len(landmarker.detect_calls) == 1

    mp_image = landmarker.detect_calls[0]
    assert mp_image.image_format is fake_mp.ImageFormat.SRGB
    assert np.array_equal(mp_image.data, frame[:, :, ::-1])

    assert len(result.faces) == 1
    assert len(result.faces[0].landmarks) == LANDMARK_COUNT
    assert result.faces[0].confidence == pytest.approx(0.93)


def test_no_face_returns_empty_result(install_fake_mediapipe, tmp_path):
    fake_result = make_result()
    _, created_landmarkers = install_fake_mediapipe(fake_result)

    model_path = tmp_path / "face_landmarker.task"
    model_path.write_bytes(b"fake-model")

    detector = FaceMeshDetector(model_path=str(model_path))
    result = detector.detect(make_frame())

    assert len(created_landmarkers) == 1
    assert result.faces == []


def test_multiple_faces_are_returned(install_fake_mediapipe, tmp_path):
    fake_result = make_result(
        make_landmarks(478, 0.95),
        make_landmarks(478, 0.88),
    )
    _, created_landmarkers = install_fake_mediapipe(fake_result)

    model_path = tmp_path / "face_landmarker.task"
    model_path.write_bytes(b"fake-model")

    detector = FaceMeshDetector(model_path=str(model_path), max_faces=2)
    result = detector.detect(make_frame())

    assert len(created_landmarkers) == 1
    assert len(result.faces) == 2
    assert all(len(face.landmarks) == LANDMARK_COUNT for face in result.faces)
    assert result.faces[0].confidence == pytest.approx(0.95)
    assert result.faces[1].confidence == pytest.approx(0.88)


def test_confidence_threshold_filters_low_confidence_faces(
    install_fake_mediapipe,
    tmp_path,
):
    fake_result = make_result(
        make_landmarks(478, 0.95),
        make_landmarks(478, 0.30),
    )
    _, created_landmarkers = install_fake_mediapipe(fake_result)

    model_path = tmp_path / "face_landmarker.task"
    model_path.write_bytes(b"fake-model")

    detector = FaceMeshDetector(
        model_path=str(model_path),
        max_faces=2,
        min_detection_confidence=0.8,
    )
    result = detector.detect(make_frame())

    assert len(created_landmarkers) == 1
    assert len(result.faces) == 1
    assert result.faces[0].confidence == pytest.approx(0.95)


def test_detector_returns_empty_for_none_or_empty_frame():
    detector = FaceMeshDetector()

    assert detector.detect(None).faces == []
    assert detector.detect(np.array([], dtype=np.uint8)).faces == []


def test_short_landmark_result_is_ignored(install_fake_mediapipe, tmp_path):
    fake_result = make_result(make_landmarks(467, 0.95))
    _, created_landmarkers = install_fake_mediapipe(fake_result)

    model_path = tmp_path / "face_landmarker.task"
    model_path.write_bytes(b"fake-model")

    detector = FaceMeshDetector(model_path=str(model_path))
    result = detector.detect(make_frame())

    assert len(created_landmarkers) == 1
    assert result.faces == []


def test_mocked_detection_is_fast_enough(install_fake_mediapipe, tmp_path):
    fake_result = make_result(make_landmarks(478, 0.95))
    _, created_landmarkers = install_fake_mediapipe(fake_result)

    model_path = tmp_path / "face_landmarker.task"
    model_path.write_bytes(b"fake-model")

    detector = FaceMeshDetector(model_path=str(model_path))
    frame = make_frame()

    detector.detect(frame)

    start = time.perf_counter()
    for _ in range(50):
        detector.detect(frame)
    elapsed = time.perf_counter() - start

    fps = 50 / elapsed
    assert len(created_landmarkers) == 1
    assert fps >= 25
