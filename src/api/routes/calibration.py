"""
src/api/routes/calibration.py

API endpoints for the per-student calibration system (Issue #19).

    POST /api/calibrate/{user_id}   - submit a batch of collected frame
                                       samples (or a manual resting_ear),
                                       compute + persist a new baseline,
                                       and return the resulting thresholds.
    GET  /api/calibrate/{user_id}   - fetch the student's current
                                       thresholds, falling back to
                                       defaults if they've never
                                       calibrated.
    DELETE /api/calibrate/{user_id} - clear calibration so the next
                                       session starts fresh (re-calibrate).

The route handlers stay thin: all baseline/threshold logic lives in
CalibrationManager (src/scoring/calibration.py); this module is only
responsible for request validation and translating to/from HTTP.
"""

from __future__ import annotations

from dataclasses import asdict
from enum import Enum
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

from src.scoring.calibration import (
    CalibrationManager,
    CalibrationRepository,
    FrameSample,
)

# --------------------------------------------------------------------------
# Dependency
# --------------------------------------------------------------------------


def get_repository() -> CalibrationRepository:
    """FastAPI dependency: provides a CalibrationRepository instance."""
    return CalibrationRepository()


# --------------------------------------------------------------------------
# Request/response schemas
# --------------------------------------------------------------------------


class Expression(str, Enum):
    neutral = "neutral"
    happy = "happy"
    confused = "confused"
    surprised = "surprised"
    bored = "bored"


class FrameSampleIn(BaseModel):
    ear: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    pitch: Optional[float] = Field(default=None, ge=-90.0, le=90.0)
    yaw: Optional[float] = Field(default=None, ge=-90.0, le=90.0)
    roll: Optional[float] = Field(default=None, ge=-90.0, le=90.0)
    expression: Optional[Expression] = None
    face_detected: bool = True
    timestamp: Optional[float] = Field(
        default=None,
        description=(
            "Unix seconds when this frame was captured. Strongly "
            "recommended: without timestamps on every sample, the "
            "server cannot verify the batch actually covers the "
            "required calibration window and falls back to a weaker, "
            "sample-count-only check."
        ),
    )


class CalibrationRequest(BaseModel):
    """Provide exactly one of `samples` (collected client-side over the
    30-second window) or `resting_ear` (quick manual calibration) - not
    both. `skip=True` ignores any of these and just falls back to
    defaults.

    When submitting `samples`, each one should carry a `timestamp` so
    the server can confirm the batch spans at least
    MIN_DURATION_COVERAGE_RATIO * CALIBRATION_DURATION_SECONDS
    (24s of an intended 30s window, by default). Batches that don't
    cover enough of the window - or that couldn't be verified at all -
    fall back to default thresholds with a warning."""

    samples: Optional[List[FrameSampleIn]] = None
    resting_ear: Optional[float] = None
    skip: bool = False

    @model_validator(mode="after")
    def validate_request(self) -> "CalibrationRequest":
        if self.skip:
            return self
        if self.samples and self.resting_ear is not None:
            raise ValueError("Provide either 'samples' or 'resting_ear', not both.")
        if not self.samples and self.resting_ear is None:
            raise ValueError("Provide 'samples', 'resting_ear', or set 'skip=True'.")
        return self


class ThresholdsOut(BaseModel):
    ear_threshold: float
    yaw_tolerance: float
    pitch_tolerance: float
    roll_tolerance: float
    expression_baseline: Dict[str, float]
    neutral_pitch: float
    neutral_yaw: float
    neutral_roll: float
    is_default: bool


class BaselineOut(BaseModel):
    resting_ear: float
    ear_std: float
    neutral_pitch: float
    neutral_yaw: float
    neutral_roll: float
    expression_distribution: Dict[str, float]
    sample_count: int
    captured_at: float


class CalibrationResponse(BaseModel):
    user_id: str
    is_calibrated: bool
    thresholds: ThresholdsOut
    baseline: Optional[BaselineOut] = None
    warning: Optional[str] = None


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _to_response(
    user_id: str, manager: CalibrationManager, warning: Optional[str] = None
) -> CalibrationResponse:
    """Build the API response purely from CalibrationManager's public
    `baseline` / `thresholds` properties - never from its private
    `_baseline` / `_thresholds` attributes."""
    baseline = manager.baseline
    return CalibrationResponse(
        user_id=user_id,
        is_calibrated=manager.is_calibrated,
        thresholds=ThresholdsOut(**asdict(manager.thresholds)),
        baseline=BaselineOut(**asdict(baseline)) if baseline else None,
        warning=warning,
    )


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------

router = APIRouter(prefix="/api/calibrate", tags=["calibration"])


@router.post("/{user_id}", response_model=CalibrationResponse)
def calibrate_student(
    user_id: str,
    body: CalibrationRequest,
    repository: CalibrationRepository = Depends(get_repository),
) -> CalibrationResponse:
    """Run or update calibration for a student.

    - `skip=True`                        -> fall back to default thresholds.
    - `resting_ear` provided              -> quick manual calibration.
    - `samples` provided                  -> full 30s-session calibration
                                              from collected frames
                                              (recommended path).
    - both `samples` and `resting_ear`    -> 400 (caught by model_validator).
    - none of the above                   -> 400 (caught by model_validator).
    """
    manager = CalibrationManager(user_id=user_id, repository=repository)
    warning = None

    try:
        if body.skip:
            manager.skip()
            warning = (
                "Calibration skipped. Using default thresholds, which may be "
                "less accurate for this student."
            )
        elif body.resting_ear is not None:
            manager.calibrate_ear(body.resting_ear)
        elif body.samples:
            manager.start_session()
            for s in body.samples:
                manager.add_sample(
                    FrameSample(
                        ear=s.ear,
                        pitch=s.pitch,
                        yaw=s.yaw,
                        roll=s.roll,
                        expression=s.expression,
                        face_detected=s.face_detected,
                        timestamp=s.timestamp,
                    )
                )
            manager.finish_session()
            if manager.thresholds.is_default:
                warning = (
                    "Calibration fell back to default thresholds: either too few "
                    "valid frames were captured (face not detected / invalid "
                    "measurements), or the samples didn't cover enough of the "
                    "required calibration window. Please try recalibrating."
                )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except RuntimeError as exc:
        # e.g. samples submitted after the session window already closed.
        raise HTTPException(status_code=409, detail=str(exc))
    except OSError as exc:
        # Persistence failure: still return the computed thresholds for
        # this session, but tell the caller they weren't saved.
        raise HTTPException(
            status_code=500,
            detail=f"Calibration computed but could not be saved: {exc}",
        )

    return _to_response(user_id, manager, warning)


@router.get("/{user_id}", response_model=CalibrationResponse)
def get_calibration(
    user_id: str,
    repository: CalibrationRepository = Depends(get_repository),
) -> CalibrationResponse:
    """Return the student's current thresholds. If they've never
    calibrated (or their record failed to load), returns safe defaults
    rather than a 404, since scoring should always have *some*
    thresholds to work with."""
    manager = CalibrationManager(user_id=user_id, repository=repository)
    warning = None
    if not manager.is_calibrated:
        warning = "No calibration on file for this student; using default thresholds."
    return _to_response(user_id, manager, warning)


@router.delete("/{user_id}", response_model=CalibrationResponse)
def recalibrate_student(
    user_id: str,
    repository: CalibrationRepository = Depends(get_repository),
) -> CalibrationResponse:
    """Clear existing calibration so the student can re-calibrate from
    scratch on their next session."""
    manager = CalibrationManager(user_id=user_id, repository=repository)
    manager.recalibrate()
    return _to_response(
        user_id,
        manager,
        warning="Calibration cleared. Defaults will be used until the student recalibrates.",
    )
