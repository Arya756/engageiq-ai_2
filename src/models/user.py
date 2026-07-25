from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from src.models.course import Course, CourseEnrollment
    from src.models.engagement_log import EngagementLog
    from src.models.nudge import Nudge
    from src.models.report import Report

from sqlalchemy import Boolean, DateTime
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.config.settings import PrivacyMode, UserRole
from src.models.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)

    password: Mapped[Optional[str]] = mapped_column(
        "password",
        String,
        nullable=True,
    )

    role: Mapped[Optional[UserRole]] = mapped_column(
        SQLEnum(UserRole),
        nullable=True,
    )

    privacy_mode: Mapped[Optional[PrivacyMode]] = mapped_column(
        SQLEnum(PrivacyMode),
        nullable=True,
    )

    avatar_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    google_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    auth_provider: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="google",
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    taught_courses: Mapped[List["Course"]] = relationship(
        "Course", back_populates="teacher", cascade="all, delete-orphan"
    )
    enrollments: Mapped[List["CourseEnrollment"]] = relationship(
        "CourseEnrollment", back_populates="student", cascade="all, delete-orphan"
    )
    engagement_logs: Mapped[List["EngagementLog"]] = relationship(
        "EngagementLog", back_populates="student", cascade="all, delete-orphan"
    )
    nudges: Mapped[List["Nudge"]] = relationship(
        "Nudge", back_populates="student", cascade="all, delete-orphan"
    )
    reports: Mapped[List["Report"]] = relationship(
        "Report", back_populates="user", cascade="all, delete-orphan"
    )

    notification_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    overlay_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    audio_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
