"""
API routes for Student Nudge Preferences.

Provides two endpoints:
  GET  /api/preferences/{user_id}  → fetch a student's current settings
  PUT  /api/preferences/{user_id}  → update a student's settings
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.api.schemas.preferences import PreferencesResponse, PreferencesUpdate
from src.config.database import get_db
from src.models.user import User

# All routes here will start with /api/preferences
router = APIRouter(
    prefix="/api/preferences",
    tags=["Preferences"],
)

# Valid sensitivity options the student is allowed to choose from
VALID_SENSITIVITY_OPTIONS = ["less", "normal", "more"]


@router.get("/{user_id}", response_model=PreferencesResponse)
def get_preferences(user_id: int, db: Session = Depends(get_db)):
    """
    Fetch the current nudge preferences for a student.
    Returns all settings including channel toggles, quiet hours, and sensitivity.
    """
    # Look up the student in the database by their ID
    user = db.query(User).filter(User.id == user_id).first()

    # If no student was found with that ID, return a 404 error
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")

    # Build and return the response with the student's current preferences
    return PreferencesResponse(
        user_id=user.id,
        notification_enabled=user.notification_enabled,
        overlay_enabled=user.overlay_enabled,
        audio_enabled=user.audio_enabled,
        quiet_hours_start=user.quiet_hours_start,
        quiet_hours_end=user.quiet_hours_end,
        sensitivity=user.sensitivity,
    )


@router.put("/{user_id}", response_model=PreferencesResponse)
def update_preferences(
    user_id: int,
    body: PreferencesUpdate,
    db: Session = Depends(get_db),
):
    """
    Update the nudge preferences for a student.
    Only the fields that are sent in the request body will be updated.
    """
    # Look up the student in the database
    user = db.query(User).filter(User.id == user_id).first()

    # If no student was found, return a 404 error
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")

    # Validate sensitivity value if it was included in the request
    if body.sensitivity is not None:
        if body.sensitivity not in VALID_SENSITIVITY_OPTIONS:
            raise HTTPException(
                status_code=400,
                detail=f"sensitivity must be one of: {VALID_SENSITIVITY_OPTIONS}",
            )

    # Update only the fields that the student actually sent in the request.
    # We skip any field that is None (meaning they didn't send it).
    if body.notification_enabled is not None:
        user.notification_enabled = body.notification_enabled

    if body.overlay_enabled is not None:
        user.overlay_enabled = body.overlay_enabled

    if body.audio_enabled is not None:
        user.audio_enabled = body.audio_enabled

    if body.quiet_hours_start is not None:
        user.quiet_hours_start = body.quiet_hours_start

    if body.quiet_hours_end is not None:
        user.quiet_hours_end = body.quiet_hours_end

    if body.sensitivity is not None:
        user.sensitivity = body.sensitivity

    # Save all changes to the database
    db.commit()
    db.refresh(user)

    # Return the student's full updated preferences
    return PreferencesResponse(
        user_id=user.id,
        notification_enabled=user.notification_enabled,
        overlay_enabled=user.overlay_enabled,
        audio_enabled=user.audio_enabled,
        quiet_hours_start=user.quiet_hours_start,
        quiet_hours_end=user.quiet_hours_end,
        sensitivity=user.sensitivity,
    )
