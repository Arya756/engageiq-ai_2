"""Application settings and configuration."""

from enum import Enum

from pydantic_settings import BaseSettings

from src.config.scoring_weights import CourseType


class UserRole(str, Enum):
    STUDENT = "student"
    TEACHER = "teacher"


class PrivacyMode(str, Enum):
    LOCAL_ONLY = "local_only"
    SHARE_WITH_TEACHER = "share_with_teacher"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    database_url: str = "postgresql://localhost:5432/engageiq_dev"

    # LLM
    llm_provider: str = "groq"
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    # Webcam
    webcam_index: int = 0
    webcam_fps: int = 15
    webcam_resolution: str = "640x480"

    # Engagement scoring weights
    gaze_weight: float = 0.30
    pose_weight: float = 0.20
    expression_weight: float = 0.25
    alertness_weight: float = 0.25

    # Course type
    course_type: CourseType = CourseType.THEORY

    # Gaze classifier thresholds (see src/detection/gaze_classifier.py)
    gaze_yaw_threshold_deg: float = 20.0
    gaze_pitch_down_threshold_deg: float = -25.0
    gaze_ear_threshold: float = 0.2
    gaze_iris_left_threshold: float = 0.35
    gaze_iris_right_threshold: float = 0.65

    # Nudge settings
    nudge_cooldown_seconds: int = 300
    max_nudges_per_session: int = 5
    nudge_trigger_duration_seconds: int = 30

    # Privacy
    default_privacy_mode: PrivacyMode = PrivacyMode.LOCAL_ONLY

    # Application
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    debug: bool = True
    secret_key: str = "change_this_in_production"

    # Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:5173"

    # Authentication
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440
    refresh_token_expire_days: int = 7

    # Frontend
    frontend_url: str = "http://localhost:5173"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
