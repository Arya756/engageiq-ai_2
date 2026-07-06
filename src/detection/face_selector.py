"""Select and track the primary face from multiple detected faces."""

import time

import cv2
import numpy as np

from src.detection.face_mesh import DetectedFace, FaceMeshDetector


def draw_boxes(frame, faces, selected_index):
    """Draw bounding boxes around detected faces."""

    height, width = frame.shape[:2]

    for i, face in enumerate(faces):
        x1, y1, x2, y2 = face.bbox

        x1 = int(x1 * width)
        y1 = int(y1 * height)
        x2 = int(x2 * width)
        y2 = int(y2 * height)

        color = (0, 255, 0) if i == selected_index else (150, 150, 150)

        cv2.rectangle(
            frame,
            (x1, y1),
            (x2, y2),
            color,
            2,
        )

    return frame


def run_demo():
    """Run face selector demo."""

    detector = FaceMeshDetector(max_faces=5)
    selector = FaceSelector()

    cap = cv2.VideoCapture(0)

    while True:
        ret, frame = cap.read()

        if not ret:
            break

        result = detector.detect(frame)

        selected = selector.select(result.faces)

        frame = draw_boxes(
            frame,
            result.faces,
            selected,
        )

        cv2.imshow("Face Selector", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    detector.close()
    cap.release()
    cv2.destroyAllWindows()


class FaceSelector:
    """Selects the primary face."""

    def __init__(self):
        self.primary_face_index = None
        self.primary_bbox = None
        self.primary_embedding = None
        self.last_seen = None

    def _compute_embedding(self, face: DetectedFace) -> np.ndarray:
        """Compute a simple embedding from facial landmarks."""

        landmarks = np.array(face.landmarks)

        return landmarks.flatten()

    def select(self, faces: list[DetectedFace]) -> int | None:
        """Return the index of the primary face."""

        if not faces:
            if self.last_seen is None:
                return None

            if time.time() - self.last_seen > 5:
                self.primary_face_index = None
                self.primary_bbox = None
                self.primary_embedding = None
                self.last_seen = None

            return None

        if self.primary_bbox is None:
            largest_index = 0
            largest_area = 0.0

            for i, face in enumerate(faces):
                x1, y1, x2, y2 = face.bbox
                area = (x2 - x1) * (y2 - y1)

                if area > largest_area:
                    largest_area = area
                    largest_index = i

            self.primary_face_index = largest_index
            self.primary_bbox = faces[largest_index].bbox
            self.primary_embedding = self._compute_embedding(faces[largest_index])
            self.last_seen = time.time()

            return largest_index

        best_index = None
        best_distance = float("inf")

        for i, face in enumerate(faces):
            embedding = self._compute_embedding(face)

            distance = np.linalg.norm(embedding - self.primary_embedding)

            if distance < best_distance:
                best_distance = distance
                best_index = i

        if best_index is None:
            if self.last_seen is not None and time.time() - self.last_seen > 5:
                self.primary_face_index = None
                self.primary_bbox = None
                self.primary_embedding = None
                return None

            return None

        self.primary_face_index = best_index
        self.primary_bbox = faces[best_index].bbox
        self.primary_embedding = self._compute_embedding(faces[best_index])
        self.last_seen = time.time()

        return best_index


if __name__ == "__main__":
    run_demo()
