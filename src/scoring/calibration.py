"""
src/scoring/calibration.py

Per-student calibration system (Issue #19).

Reuses the outputs of the existing EAR (#12) and head-pose (#9/#16)
detectors instead of re-implementing any computer-vision logic. This
module is only responsible for:

    1. Collecting a short stream of per-frame measurements
       (EAR, head pose, expression) while the student looks naturally
       at the screen for ~30 seconds.
    2. Filtering out invalid/missing-face frames.
    3. Computing robust baseline statistics from the valid samples.
    4. Deriving personalized detection thresholds from those baselines.
    5. Persisting/loading calibration data per student.
    6. Falling back to safe defaults when calibration is missing,
       skipped, interrupted, or fails.

It intentionally does NOT talk to a camera directly. A caller (a CLI
demo, a websocket handler, a batch job, etc.) feeds it frames via
`add_sample()`, so the same class works for live video, recorded
video, or unit tests.
"""

from __future__ import annotations

import json
import logging
import math
import statistics
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from src.config.settings import calibration_storage_dir

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Defaults (used whenever a student has no calibration, or calibration
# fails / is skipped). These match the fixed thresholds used before #19.
# --------------------------------------------------------------------------

DEFAULT_EAR_THRESHOLD = 0.25
DEFAULT_EAR_RATIO = 0.8  # calibrated_threshold = resting_ear * this ratio
DEFAULT_YAW_TOLERANCE = 20.0  # degrees, off-screen gaze tolerance
DEFAULT_PITCH_TOLERANCE = 15.0
DEFAULT_ROLL_TOLERANCE = 15.0
DEFAULT_EXPRESSION_DISTRIBUTION = {
    "neutral": 1.0,
    "happy": 0.0,
    "confused": 0.0,
    "surprised": 0.0,
    "bored": 0.0,
}

# The only expression labels the baseline/distribution will accept.
# Anything else (typos, a classifier version mismatch, a stray "unknown")
# is treated as an unlabeled frame rather than silently corrupting the
# expression baseline - the frame's EAR/pose data is still used, just
# not its expression label.
SUPPORTED_EXPRESSIONS = frozenset(DEFAULT_EXPRESSION_DISTRIBUTION.keys())

CALIBRATION_DURATION_SECONDS = 30
MIN_VALID_SAMPLES = 30  # guard against a mostly-empty/interrupted session

# Plausible measurement ranges. Samples outside these are treated as
# invalid (sensor glitch / tracking failure) rather than trusted.
EAR_RANGE = (0.0, 1.0)
PITCH_RANGE = (-180.0, 180.0)  # degrees, nose up/down (widened for solvePnP domain)
YAW_RANGE = (-180.0, 180.0)  # degrees, nose left/right
ROLL_RANGE = (-180.0, 180.0)  # degrees, head tilt

# --------------------------------------------------------------------------
# Session-duration enforcement.
#
# The 30-second window is enforced two different ways depending on how
# samples arrive:
#
#   * Live/streaming collection (add_sample() called in real time, e.g.
#     from the CLI demo or a websocket handler): `add_sample()` refuses
#     new samples once `duration_seconds` has actually elapsed on the
#     wall clock (see `is_session_complete()`), so a session can't run
#     short or long.
#
#   * Batch collection (the HTTP API receives an already-collected list
#     of samples in one request, so there is no live wall clock to
#     check): duration is instead verified from each `FrameSample`'s
#     optional `timestamp`. The span between the earliest and latest
#     valid sample must cover at least `MIN_DURATION_COVERAGE_RATIO` of
#     `duration_seconds`, or the session is rejected as too short and
#     falls back to defaults. If callers don't supply timestamps at all,
#     we can't verify duration and fall back to the `MIN_VALID_SAMPLES`
#     count as a (documented, weaker) proxy instead.
# --------------------------------------------------------------------------
MIN_DURATION_COVERAGE_RATIO = 0.8


# --------------------------------------------------------------------------
# Data classes
# --------------------------------------------------------------------------


@dataclass
class FrameSample:
    """A single frame's measurements, as produced by the upstream CV
    modules (#9 head pose, #12 EAR, expression classifier)."""

    ear: Optional[float] = None
    pitch: Optional[float] = None
    yaw: Optional[float] = None
    roll: Optional[float] = None
    expression: Optional[str] = None
    face_detected: bool = True
    # Optional capture time (unix seconds). Used to verify session
    # duration for batch-collected samples; see MIN_DURATION_COVERAGE_RATIO.
    timestamp: Optional[float] = None

    def is_valid(self) -> bool:
        if not self.face_detected:
            return False
        for value in (self.ear, self.pitch, self.yaw, self.roll):
            if value is None:
                return False
            if isinstance(value, float) and math.isnan(value):
                return False
        if not (EAR_RANGE[0] < self.ear < EAR_RANGE[1]):
            return False
        if not (PITCH_RANGE[0] <= self.pitch <= PITCH_RANGE[1]):
            return False
        if not (YAW_RANGE[0] <= self.yaw <= YAW_RANGE[1]):
            return False
        if not (ROLL_RANGE[0] <= self.roll <= ROLL_RANGE[1]):
            return False
        return True


@dataclass
class CalibrationBaseline:
    """Raw baseline statistics captured during the 30-second session."""

    resting_ear: float
    ear_std: float
    neutral_pitch: float
    neutral_yaw: float
    neutral_roll: float
    expression_distribution: Dict[str, float]
    sample_count: int
    captured_at: float = field(default_factory=time.time)


@dataclass
class CalibratedThresholds:
    """Thresholds consumed by the scoring engine.

    Gaze/head-pose checks must NOT compare a live reading against a
    fixed absolute angle (e.g. "yaw within +/-20 of 0"). They must
    compare against *this student's own resting pose*
    (`neutral_pitch`/`neutral_yaw`/`neutral_roll`) plus/minus the
    tolerance - use `is_gaze_within_bounds()` rather than
    re-implementing that comparison in the scoring engine.
    """

    ear_threshold: float
    yaw_tolerance: float
    pitch_tolerance: float
    roll_tolerance: float
    expression_baseline: Dict[str, float]
    neutral_pitch: float = 0.0
    neutral_yaw: float = 0.0
    neutral_roll: float = 0.0
    is_default: bool = False  # True when falling back to global defaults

    def is_gaze_within_bounds(self, pitch: float, yaw: float, roll: float) -> bool:
        """True if a live head-pose reading falls within this student's
        calibrated tolerance of their own natural resting pose."""

        def _angle_diff(a: float, b: float) -> float:
            return abs((a - b + 180.0) % 360.0 - 180.0)

        return (
            _angle_diff(pitch, self.neutral_pitch) <= self.pitch_tolerance
            and _angle_diff(yaw, self.neutral_yaw) <= self.yaw_tolerance
            and _angle_diff(roll, self.neutral_roll) <= self.roll_tolerance
        )


# --------------------------------------------------------------------------
# Persistence layer
# --------------------------------------------------------------------------


class CalibrationRepository:
    """Persists calibration data per student.

    Default implementation stores one JSON file per user under
    `storage_dir`, which is enough to satisfy "persists across
    sessions" for local dev / demo use, and keeps this module free of
    a hard dependency on the DB layer (#3/#7). In production this can
    be swapped for a SQLAlchemy-backed implementation by passing a
    `db_session` and overriding `save`/`load`, since callers only
    depend on this class's public interface.
    """

    def __init__(self, storage_dir: str = calibration_storage_dir):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        # Guards read-modify-write access to a given file so concurrent
        # requests for the same (or different) students don't race each
        # other. A single lock is coarse but cheap and correct; swap for
        # per-key locks if this becomes a bottleneck.
        self._lock = threading.Lock()

    def _path_for(self, user_id: str) -> Path:
        safe_id = "".join(c for c in str(user_id) if c.isalnum() or c in "-_")
        return self.storage_dir / f"{safe_id}.json"

    def save(self, user_id: str, baseline: CalibrationBaseline) -> None:
        path = self._path_for(user_id)
        tmp_path = path.with_suffix(".json.tmp")

        with self._lock:
            try:
                with open(tmp_path, "w") as f:
                    json.dump(asdict(baseline), f, indent=2)

                tmp_path.replace(path)

            except OSError as exc:
                logger.error(
                    "Failed to persist calibration for %s: %s",
                    user_id,
                    exc,
                )
                raise

    def load(self, user_id: str) -> Optional[CalibrationBaseline]:
        path = self._path_for(user_id)
        with self._lock:
            if not path.exists():
                return None
            try:
                with open(path, "r") as f:
                    data = json.load(f)
                return CalibrationBaseline(**data)
            except (OSError, json.JSONDecodeError, TypeError) as exc:
                logger.error("Failed to load calibration for %s: %s", user_id, exc)
                return None

    def delete(self, user_id: str) -> bool:
        path = self._path_for(user_id)
        with self._lock:
            try:
                if path.exists():
                    path.unlink()
                return True
            except OSError as exc:
                logger.error("Failed to delete calibration for %s: %s", user_id, exc)
                return False


# --------------------------------------------------------------------------
# Core manager
# --------------------------------------------------------------------------


class CalibrationManager:
    """Collects a calibration session and turns it into personalized
    detection thresholds for a single student.

    Typical lifecycle:

        cm = CalibrationManager(user_id="student_123")
        cm.start_session()
        while collecting:
            cm.add_sample(FrameSample(ear=..., pitch=..., yaw=..., roll=..., expression=...))
        thresholds = cm.finish_session()   # computes, persists, returns thresholds

    For quick/manual testing you can also skip frame collection and
    call `calibrate_ear()` directly with a known resting EAR value.
    """

    def __init__(
        self,
        user_id: Optional[str] = None,
        repository: Optional[CalibrationRepository] = None,
        duration_seconds: int = CALIBRATION_DURATION_SECONDS,
        min_valid_samples: int = MIN_VALID_SAMPLES,
        min_duration_coverage_ratio: float = MIN_DURATION_COVERAGE_RATIO,
        ear_ratio: float = DEFAULT_EAR_RATIO,
        yaw_tolerance: float = DEFAULT_YAW_TOLERANCE,
        pitch_tolerance: float = DEFAULT_PITCH_TOLERANCE,
        roll_tolerance: float = DEFAULT_ROLL_TOLERANCE,
    ):
        self.user_id = user_id
        self.repository = repository or CalibrationRepository()
        self.duration_seconds = duration_seconds
        self.min_valid_samples = min_valid_samples
        self.min_duration_coverage_ratio = min_duration_coverage_ratio
        self.ear_ratio = ear_ratio
        self.default_yaw_tolerance = yaw_tolerance
        self.default_pitch_tolerance = pitch_tolerance
        self.default_roll_tolerance = roll_tolerance

        self._samples: List[FrameSample] = []
        self._session_start: Optional[float] = None
        self._session_active: bool = False
        self._baseline: Optional[CalibrationBaseline] = None
        self._thresholds: CalibratedThresholds = self._default_thresholds()

        # If this student already has a calibration on record, load it
        # immediately so scoring can use it before/without recalibrating.
        if self.user_id:
            existing = self.repository.load(self.user_id)
            if existing:
                self._baseline = existing
                self._thresholds = self._thresholds_from_baseline(existing)

    # ---- public read-only accessors --------------------------------------
    #
    # External code (API routes, the scoring engine, demos, tests) should
    # always go through these rather than touching `_thresholds` /
    # `_baseline` directly, so the internal representation stays free to
    # change.

    @property
    def baseline(self) -> Optional[CalibrationBaseline]:
        """The raw captured baseline, or None if never calibrated."""
        return self._baseline

    @property
    def thresholds(self) -> CalibratedThresholds:
        """The currently active thresholds (calibrated or default)."""
        return self._thresholds

    @property
    def ear_threshold(self) -> float:
        return self._thresholds.ear_threshold

    @property
    def yaw_tolerance(self) -> float:
        return self._thresholds.yaw_tolerance

    @property
    def pitch_tolerance(self) -> float:
        return self._thresholds.pitch_tolerance

    @property
    def expression_baseline(self) -> Dict[str, float]:
        return self._thresholds.expression_baseline

    @property
    def is_calibrated(self) -> bool:
        return self._baseline is not None

    # ---- session-based collection ---------------------------------------

    def start_session(self) -> None:
        """Begin a new calibration session.

        Raises:
            RuntimeError:
                If another calibration session is already active.
        """
        if self._session_active:
            raise RuntimeError(
                "Calibration session already in progress. "
                "Finish or cancel it before starting a new one."
            )

        self._samples = []
        self._session_start = time.time()
        self._session_active = True

    def add_sample(self, sample: FrameSample) -> None:
        """Feed one frame's measurements into the current session.
        Invalid frames (no face, NaN/None, out-of-range values) are
        recorded as skipped rather than raising, so a few bad frames
        don't abort the whole calibration.

        Raises RuntimeError if no session is active, or if the session's
        wall-clock duration has already elapsed (live/streaming callers
        must call finish_session() and, if desired, start_session()
        again rather than keep feeding samples past the window)."""
        if not self._session_active or self._session_start is None:
            raise RuntimeError(
                "No active calibration session. Call start_session() first, "
                "or finish_session() was already called for this session."
            )
        if self.is_session_complete():
            raise RuntimeError(
                f"Calibration session duration ({self.duration_seconds}s) has "
                "already elapsed; call finish_session() instead of adding more samples."
            )
        self._samples.append(sample)

    def time_remaining(self) -> float:
        if self._session_start is None:
            return float(self.duration_seconds)
        elapsed = time.time() - self._session_start
        return max(0.0, self.duration_seconds - elapsed)

    def is_session_complete(self) -> bool:
        return self._session_start is not None and self.time_remaining() <= 0

    def finish_session(self) -> CalibratedThresholds:
        """Compute baseline stats from collected samples, persist them,
        and return the resulting thresholds. Falls back to defaults
        (with a warning) if the session was interrupted, produced too
        few valid samples, or didn't cover enough of the required
        `duration_seconds` window (see MIN_DURATION_COVERAGE_RATIO
        docs above). Closes the session: no further add_sample() calls
        are accepted until start_session() is called again."""
        valid = [s for s in self._samples if s.is_valid()]
        total = len(self._samples)
        logger.info(
            "Calibration session for %s: %d/%d frames valid",
            self.user_id,
            len(valid),
            total,
        )
        # Session is over the moment we're finishing it, regardless of
        # outcome below - no more samples belong to it.
        self._session_active = False

        if len(valid) < self.min_valid_samples:
            logger.warning(
                "Calibration for %s had only %d valid samples (need >= %d). "
                "Falling back to default thresholds.",
                self.user_id,
                len(valid),
                self.min_valid_samples,
            )
            self._baseline = None
            self._thresholds = self._default_thresholds()
            return self._thresholds

        duration_ok, observed_span = self._check_duration_coverage(valid)
        if not duration_ok:
            logger.warning(
                "Calibration for %s only covered %.1fs of the required "
                "%ds window (%.0f%% minimum). Falling back to default "
                "thresholds.",
                self.user_id,
                observed_span,
                self.duration_seconds,
                self.min_duration_coverage_ratio * 100,
            )
            self._baseline = None
            self._thresholds = self._default_thresholds()
            return self._thresholds

        baseline = self._compute_baseline(valid)
        self._baseline = baseline
        self._thresholds = self._thresholds_from_baseline(baseline)

        if self.user_id:
            try:
                self.repository.save(self.user_id, baseline)
            except OSError:
                logger.warning(
                    "Calibration computed successfully but " "could not be persisted."
                )

        return self._thresholds

    def _check_duration_coverage(
        self, valid: List[FrameSample]
    ) -> "tuple[bool, float]":
        """Verify the collected samples actually span (close to) the
        required calibration window.

        - Live sessions (`_session_start` set by start_session() and
          samples fed in real time): checked against the wall clock.
        - Batch sessions with per-sample `timestamp`s: checked against
          the min/max timestamp among valid samples.
        - Batch sessions with no timestamps at all: duration can't be
          verified; we accept the session (already gated by
          `min_valid_samples`) but this is a strictly weaker guarantee -
          documented above and callers are encouraged to always send
          timestamps.
        """
        timestamps = [s.timestamp for s in valid if s.timestamp is not None]
        if timestamps:
            span = max(timestamps) - min(timestamps)
        elif self._session_start is not None:
            span = time.time() - self._session_start
        else:
            # No way to verify; don't block on it, but make it visible.
            logger.info(
                "Calibration for %s: no timestamps and no live session clock; "
                "duration coverage could not be verified.",
                self.user_id,
            )
            return True, float(self.duration_seconds)

        required = self.duration_seconds * self.min_duration_coverage_ratio
        return span >= required, span

    def skip(self) -> CalibratedThresholds:
        """Explicitly skip calibration for this session. Always safe:
        falls back to global default thresholds."""
        logger.info(
            "Calibration skipped for %s; using default thresholds.", self.user_id
        )
        self._session_active = False
        self._thresholds = self._default_thresholds()
        return self._thresholds

    def recalibrate(self) -> None:
        """Clear any stored calibration for this student and reset to
        defaults, ready for a fresh start_session()/add_sample() cycle."""
        if self.user_id:
            self.repository.delete(self.user_id)
        self._baseline = None
        self._samples = []
        self._session_start = None
        self._session_active = False
        self._thresholds = self._default_thresholds()

    # ---- direct/manual calibration (used by simple demos & tests) -------

    def calibrate_ear(self, resting_ear: float) -> float:
        """Directly set the resting EAR baseline without running a full
        frame-collection session (handy for tests / quick scripts)."""
        if resting_ear is None or (
            isinstance(resting_ear, float) and math.isnan(resting_ear)
        ):
            raise ValueError("resting_ear must be a valid number")
        if not (EAR_RANGE[0] < resting_ear < EAR_RANGE[1]):
            raise ValueError(
                f"resting_ear {resting_ear} is out of the plausible EAR range {EAR_RANGE}"
            )

        baseline = CalibrationBaseline(
            resting_ear=resting_ear,
            ear_std=0.0,
            neutral_pitch=0.0,
            neutral_yaw=0.0,
            neutral_roll=0.0,
            expression_distribution=dict(DEFAULT_EXPRESSION_DISTRIBUTION),
            sample_count=1,
        )
        self._baseline = baseline
        self._thresholds = self._thresholds_from_baseline(baseline)

        if self.user_id:
            self.repository.save(self.user_id, baseline)

        return self._thresholds.ear_threshold

    # ---- internals --------------------------------------------------------

    def _default_thresholds(self) -> CalibratedThresholds:
        return CalibratedThresholds(
            ear_threshold=DEFAULT_EAR_THRESHOLD,
            yaw_tolerance=self.default_yaw_tolerance,
            pitch_tolerance=self.default_pitch_tolerance,
            roll_tolerance=self.default_roll_tolerance,
            expression_baseline=dict(DEFAULT_EXPRESSION_DISTRIBUTION),
            is_default=True,
        )

    @staticmethod
    def _filter_outliers(values: List[float]) -> List[float]:
        """Median/IQR-based outlier rejection so a handful of glitchy
        frames (blink caught mid-frame, momentary tracking jump, etc.)
        don't skew the baseline. Falls back to the raw values when
        there are too few points for IQR to be meaningful."""
        if len(values) < 5:
            return values
        ordered = sorted(values)
        q1 = statistics.median(ordered[: len(ordered) // 2])
        q3 = statistics.median(ordered[(len(ordered) + 1) // 2 :])
        iqr = q3 - q1
        if iqr == 0:
            return values
        lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        filtered = [v for v in values if lower <= v <= upper]
        return filtered or values  # never return an empty list

    @classmethod
    def _compute_baseline(cls, valid: List[FrameSample]) -> CalibrationBaseline:
        ears = cls._filter_outliers([s.ear for s in valid])
        pitches = cls._filter_outliers([s.pitch for s in valid])
        yaws = cls._filter_outliers([s.yaw for s in valid])
        rolls = cls._filter_outliers([s.roll for s in valid])

        raw_expressions = [s.expression for s in valid if s.expression is not None]
        expressions = [e for e in raw_expressions if e in SUPPORTED_EXPRESSIONS]
        unsupported_count = len(raw_expressions) - len(expressions)
        if unsupported_count:
            logger.warning(
                "Ignored %d frame(s) with unsupported expression labels "
                "(expected one of %s).",
                unsupported_count,
                sorted(SUPPORTED_EXPRESSIONS),
            )

        resting_ear = statistics.median(ears)
        ear_std = statistics.pstdev(ears) if len(ears) > 1 else 0.0

        distribution: Dict[str, float] = {}
        if expressions:
            for label in expressions:
                distribution[label] = distribution.get(label, 0) + 1
            n = len(expressions)
            distribution = {k: v / n for k, v in distribution.items()}

            total = sum(distribution.values())

            distribution = {k: v / total for k, v in distribution.items()}
        else:
            distribution = dict(DEFAULT_EXPRESSION_DISTRIBUTION)

        return CalibrationBaseline(
            resting_ear=resting_ear,
            ear_std=ear_std,
            neutral_pitch=statistics.median(pitches),
            neutral_yaw=statistics.median(yaws),
            neutral_roll=statistics.median(rolls),
            expression_distribution=distribution,
            sample_count=len(valid),
        )

    def _thresholds_from_baseline(
        self, baseline: CalibrationBaseline
    ) -> CalibratedThresholds:
        # EAR: e.g. resting_ear 0.22 -> threshold ~0.176 (not the fixed 0.25),
        # resting_ear 0.35 -> threshold ~0.28.
        ear_threshold = round(baseline.resting_ear * self.ear_ratio, 4)

        # Gaze tolerances keep the default *width*, but are recentred on
        # this student's own natural head pose (neutral_pitch/yaw/roll)
        # rather than assumed to be zero/straight-ahead. Callers should
        # use `CalibratedThresholds.is_gaze_within_bounds()` rather than
        # comparing pitch/yaw/roll to an absolute angle directly.
        return CalibratedThresholds(
            ear_threshold=ear_threshold,
            yaw_tolerance=self.default_yaw_tolerance,
            pitch_tolerance=self.default_pitch_tolerance,
            roll_tolerance=self.default_roll_tolerance,
            expression_baseline=baseline.expression_distribution,
            neutral_pitch=baseline.neutral_pitch,
            neutral_yaw=baseline.neutral_yaw,
            neutral_roll=baseline.neutral_roll,
            is_default=False,
        )

    # ---- serialization helpers for the API layer ---------------------------

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "is_calibrated": self.is_calibrated,
            "baseline": asdict(self.baseline) if self.baseline else None,
            "thresholds": asdict(self.thresholds),
        }


# --------------------------------------------------------------------------
# CLI demo:  python -m src.scoring.calibration --demo
# --------------------------------------------------------------------------

# Standard MediaPipe face-mesh eye landmark indices (478-point topology).
_LEFT_EYE_INDICES = [33, 160, 158, 133, 153, 144]
_RIGHT_EYE_INDICES = [362, 385, 387, 263, 373, 380]


def _run_demo(camera_index: int = 0, user_id: str = "demo_student") -> None:
    """Live webcam calibration demo.

    Opens the webcam, runs the existing detectors on every frame, feeds
    measurements into CalibrationManager for 30 seconds, then prints the
    resulting thresholds and saves them to disk.
    """
    import cv2

    from src.detection.drowsiness import compute_ear
    from src.detection.face_mesh import FaceMeshDetector
    from src.detection.head_pose import estimate_head_pose

    # --- initialise detectors ------------------------------------------------
    face_detector = FaceMeshDetector()
    # ExpressionClassifier uses FER internally, which requires OpenCV's Haar
    # cascade file and pkg_resources. If either is absent the classifier is
    # skipped; expression records as None for the session (still valid for
    # EAR + head-pose calibration).
    expression_classifier = None
    try:
        from src.detection.expression import ExpressionClassifier

        expression_classifier = ExpressionClassifier()
    except Exception as _exc:
        print(
            f"[warn] ExpressionClassifier unavailable ({_exc}); "
            "expression data will not be collected this session."
        )

    # --- open webcam ---------------------------------------------------------
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        print(f"Could not open webcam (index {camera_index}).")
        return

    # --- start calibration session -------------------------------------------
    cm = CalibrationManager(user_id=user_id)
    cm.start_session()

    print(f"Look naturally at the screen for {CALIBRATION_DURATION_SECONDS} seconds...")
    print("Press 'q' to abort early.\n")

    try:
        while not cm.is_session_complete():
            ret, frame = cap.read()
            if not ret:
                logger.warning("Webcam read failed; skipping frame.")
                continue

            h, w = frame.shape[:2]
            now = time.time()

            # --- detect face --------------------------------------------------
            result = face_detector.detect(frame)

            if result.faces:
                face = result.faces[0]
                landmarks = face.landmarks

                # EAR: extract the 6 (x,y) pixel points for each eye
                left_eye = [
                    (landmarks[i][0] * w, landmarks[i][1] * h)
                    for i in _LEFT_EYE_INDICES
                ]
                right_eye = [
                    (landmarks[i][0] * w, landmarks[i][1] * h)
                    for i in _RIGHT_EYE_INDICES
                ]
                ear = (compute_ear(left_eye) + compute_ear(right_eye)) / 2.0

                # Head pose
                pose = estimate_head_pose(landmarks, frame.shape)
                if pose is None:
                    # Landmark geometry degenerate this frame; skip it
                    print(f"EAR={ear:.3f}, Pose=None (Head pose failed)")
                    if cm.is_session_complete():
                        break
                    cm.add_sample(FrameSample(face_detected=True, timestamp=now))
                    _draw_overlay(frame, cm.time_remaining(), ear=None, pose=None)
                    cv2.imshow("Calibration", frame)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        break
                    continue

                pitch, yaw, roll = pose

                # Expression: crop face from bbox (normalised -> pixels)
                x1, y1, x2, y2 = face.bbox
                fx1 = max(0, int(x1 * w))
                fy1 = max(0, int(y1 * h))
                fx2 = min(w, int(x2 * w))
                fy2 = min(h, int(y2 * h))
                face_crop = frame[fy1:fy2, fx1:fx2]

                expression_label: Optional[str] = None
                if expression_classifier is not None and face_crop.size > 0:
                    try:
                        expr, _conf = expression_classifier.predict(face_crop)
                        # expr is an Expression enum; its .value is a plain string
                        raw = expr.value if hasattr(expr, "value") else str(expr)
                        # Map to SUPPORTED_EXPRESSIONS used by CalibrationManager
                        _expr_map = {
                            "engaged": "happy",
                            "happy": "happy",
                            "neutral": "neutral",
                            "bored": "bored",
                            "confused": "confused",
                        }
                        expression_label = _expr_map.get(raw, "neutral")
                    except Exception as _exc:
                        # Haar cascade missing or FER inference failure;
                        # log once then skip expression for this frame.
                        logger.debug("Expression prediction failed: %s", _exc)
                        expression_label = None

                print(
                    f"EAR={ear:.3f}, "
                    f"Pitch={pitch:.1f}, "
                    f"Yaw={yaw:.1f}, "
                    f"Roll={roll:.1f}, "
                    f"Expression={expression_label}"
                )
                if cm.is_session_complete():
                    break
                cm.add_sample(
                    FrameSample(
                        ear=ear,
                        pitch=pitch,
                        yaw=yaw,
                        roll=roll,
                        expression=expression_label,
                        face_detected=True,
                        timestamp=now,
                    )
                )
                _draw_overlay(
                    frame, cm.time_remaining(), ear=ear, pose=(pitch, yaw, roll)
                )

            else:
                # No face this frame — record it so the manager can track it
                if cm.is_session_complete():
                    break
                cm.add_sample(FrameSample(face_detected=False, timestamp=now))
                _draw_overlay(
                    frame,
                    cm.time_remaining(),
                    ear=None,
                    pose=None,
                    label="No face detected",
                )

            cv2.imshow("Calibration", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                print("Aborted by user.")
                break

    finally:
        face_detector.close()
        cap.release()
        cv2.destroyAllWindows()

    # --- finish and report ---------------------------------------------------
    thresholds = cm.finish_session()
    baseline = cm.baseline

    if baseline is None:
        print(
            "\nCalibration did not produce enough valid data. Using default thresholds."
        )
        print(f"  ear_threshold : {thresholds.ear_threshold:.3f} (default)")
        return

    print("\nCalibration complete:\n")
    print(f"  resting EAR baseline : {baseline.resting_ear:.3f}")
    print(
        f"  neutral head pose    : "
        f"pitch={baseline.neutral_pitch:.2f}, "
        f"yaw={baseline.neutral_yaw:.2f}, "
        f"roll={baseline.neutral_roll:.2f}"
    )
    print(f"  expression baseline  : {baseline.expression_distribution}")
    print("\nCalibrated thresholds:")
    print(
        f"  ear_threshold   : {thresholds.ear_threshold:.3f}"
        f"  (default was {DEFAULT_EAR_THRESHOLD})"
    )
    print(f"  yaw_tolerance   : {thresholds.yaw_tolerance:.1f} deg")
    print(f"  pitch_tolerance : {thresholds.pitch_tolerance:.1f} deg")
    print(f"\nSaved to: {cm.repository._path_for(cm.user_id)}")


def _draw_overlay(
    frame,
    remaining: float,
    *,
    ear: Optional[float],
    pose: Optional[tuple],
    label: str = "",
) -> None:
    """Draw calibration progress HUD onto the frame in-place."""
    import cv2

    cv2.putText(
        frame,
        f"Calibrating: {remaining:.1f}s remaining",
        (20, 40),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.0,
        (0, 255, 0),
        2,
        cv2.LINE_AA,
    )
    if ear is not None:
        cv2.putText(
            frame,
            f"EAR: {ear:.3f}",
            (20, 80),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 255),
            2,
            cv2.LINE_AA,
        )
    if pose is not None:
        pitch, yaw, roll = pose
        cv2.putText(
            frame,
            f"P:{pitch:.1f} Y:{yaw:.1f} R:{roll:.1f}",
            (20, 115),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 255),
            2,
            cv2.LINE_AA,
        )
    if label:
        cv2.putText(
            frame,
            label,
            (20, 150),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 0, 255),
            2,
            cv2.LINE_AA,
        )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Per-student calibration demo")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run a live 30s webcam calibration",
    )
    parser.add_argument(
        "--camera",
        type=int,
        default=0,
        help="Webcam index to use (default: 0)",
    )
    parser.add_argument(
        "--user-id",
        default="demo_student",
        help="Student ID to save calibration under (default: demo_student)",
    )
    args = parser.parse_args()

    if args.demo:
        _run_demo(camera_index=args.camera, user_id=args.user_id)
    else:
        parser.print_help()
