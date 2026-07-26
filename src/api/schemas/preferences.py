"""
Pydantic schemas for the Student Nudge Preferences API.

These schemas define the shape of the data that goes IN and comes OUT
of the /api/preferences endpoints. Think of them as a strict contract
for the API.
"""

from typing import Optional

from pydantic import BaseModel, ConfigDict


class PreferencesUpdate(BaseModel):
    """
    The data the student sends when they CHANGE their preferences.
    All fields are Optional — so a student can update just one setting
    without needing to send all of them.
    """

    # Toggle: should the system send browser pop-up notifications?
    notification_enabled: Optional[bool] = None

    # Toggle: should the system show the on-screen visual glow/overlay?
    overlay_enabled: Optional[bool] = None

    # Toggle: should the system play an audio chime?
    audio_enabled: Optional[bool] = None

    # Quiet hours: if the current time is between these two values,
    # the system will NOT send any nudges.
    # Format is 24-hour time as a string, e.g. "22:00" or "08:00"
    quiet_hours_start: Optional[str] = None
    quiet_hours_end: Optional[str] = None

    # Sensitivity controls how long the student must be distracted before
    # a nudge fires, and changes the cooldown period between nudges:
    #   "less"   → 10-minute cooldown (600 seconds)
    #   "normal" → 5-minute cooldown (300 seconds) — the default
    #   "more"   → 3-minute cooldown (180 seconds)
    sensitivity: Optional[str] = None


class PreferencesResponse(BaseModel):
    """
    The data we SEND BACK to the frontend after a GET or successful PUT.
    This tells the frontend the student's current, saved preferences.
    """

    user_id: int
    notification_enabled: bool
    overlay_enabled: bool
    audio_enabled: bool
    quiet_hours_start: Optional[str] = None
    quiet_hours_end: Optional[str] = None
    sensitivity: str

    # This tells Pydantic to read data from a SQLAlchemy model object directly
    model_config = ConfigDict(from_attributes=True)
