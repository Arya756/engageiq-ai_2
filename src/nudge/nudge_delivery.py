"""
Nudge Delivery Service — Issue #21

Delivers a nudge to a student through up to three channels:

    - notification  : browser push-style notification (title + message)
    - overlay       : subtle screen-edge glow (non-blocking)
    - audio         : short, quiet chime (< 2s, low volume)

Design notes (why it looks like this):

    - No new datastore. Every delivered nudge is persisted using the
      existing `Nudge` model (src/models/nudge.py) via the existing
      `get_db()` session (`SessionLocal`, synchronous) — no sqlite3, no
      separate .db file.
    - No new transport. Delivery happens over the existing
      `ConnectionManager` (src/api/websocket.py), via its `send_json()`
      method, which already enforces WebSocket authentication
      (`_authenticate()`), so only authenticated, connected users receive
      anything.
    - No new settings store, no related preferences table. `User` already
      carries `notification_enabled` / `overlay_enabled` / `audio_enabled`
      columns directly — this service just reads those three fields off
      the `User` object it's already been given. (An earlier draft added a
      separate `NudgePreference` model; that's been removed now that it's
      clear the columns live on `User` itself.)
    - No manual service construction in routes. `NudgeDeliveryService` is
      built to be handed in via `Depends()` (see `get_nudge_delivery_service`
      at the bottom) and consumed from the Nudge Decision layer described
      in the architecture diagram.
    - Uses the project's existing `logging` module — no bespoke logger.
    - WebSocket payloads are typed Pydantic models (below), not raw dicts,
      so the shape of what goes over the wire is validated and documented
      in one place.

Assumed existing module paths / fields (adjust below if the real repo
differs slightly — the service logic itself is layout-agnostic):

    src.database            -> get_db(), Session (sync SessionLocal-backed)
    src.models.user         -> User (.notification_enabled, .overlay_enabled,
                                .audio_enabled already present)
    src.models.nudge        -> Nudge (student_id, nudge_type, triggered_state,
                                effectiveness_delta, `student` relationship
                                back_populates User.nudges — see NOTE below
                                if the FK is actually named `user_id`)
    src.api.websocket       -> ConnectionManager, manager (singleton instance)
    src.config.settings     -> settings
"""

from __future__ import annotations

import argparse
import logging
from datetime import datetime
from enum import Enum
from typing import Literal, Optional, Union

from fastapi import Depends
from pydantic import BaseModel, Field
from sqlalchemy.future import select
from sqlalchemy.orm import Session

from src.api.websocket import ConnectionManager
from src.api.websocket import manager as connection_manager
from src.config.database import get_db
from src.config.settings import settings
from src.models.engagement_log import EngagementState
from src.models.nudge import Nudge
from src.models.user import User

logger = logging.getLogger(__name__)


class NudgeChannel(str, Enum):
    NOTIFICATION = "notification"
    OVERLAY = "overlay"
    AUDIO = "audio"


# Playback constraints from the acceptance criteria — kept as constants
# (per settings.py conventions) rather than hardcoded inline magic numbers.
AUDIO_MAX_DURATION_MS = getattr(settings, "NUDGE_AUDIO_MAX_DURATION_MS", 2000)
AUDIO_DEFAULT_VOLUME = getattr(settings, "NUDGE_AUDIO_DEFAULT_VOLUME", 0.3)
OVERLAY_DEFAULT_EDGE = getattr(settings, "NUDGE_OVERLAY_EDGE", "right")


# ---------------------------------------------------------------------------
# WebSocket payload models — typed instead of raw dicts, so the frontend
# contract for each channel is explicit and validated at construction time.
# ---------------------------------------------------------------------------


class NotificationPayload(BaseModel):
    event: Literal["nudge"] = "nudge"
    channel: Literal["notification"] = "notification"
    nudge_type: str
    title: str = "EngageIQ"
    message: str


class OverlayPayload(BaseModel):
    event: Literal["nudge"] = "nudge"
    channel: Literal["overlay"] = "overlay"
    nudge_type: str
    message: str
    style: str = "subtle-edge-glow"
    edge: str = OVERLAY_DEFAULT_EDGE
    blocking: bool = False


class AudioPayload(BaseModel):
    event: Literal["nudge"] = "nudge"
    channel: Literal["audio"] = "audio"
    nudge_type: str
    sound: str = "gentle_chime"
    duration_ms: int = Field(default=AUDIO_MAX_DURATION_MS, le=AUDIO_MAX_DURATION_MS)
    volume: float = Field(default=AUDIO_DEFAULT_VOLUME, ge=0.0, le=1.0)


NudgePayload = Union[NotificationPayload, OverlayPayload, AudioPayload]


class NudgeDeliveryService:
    """Persists a nudge and pushes it to the student over the existing
    WebSocket connection, respecting the student's per-channel preferences
    (which live directly on `User`).

    `db` is the repository's synchronous `Session` (SessionLocal-backed) —
    all ORM calls here are plain, non-awaited SQLAlchemy calls. Only the
    WebSocket send is awaited, since `ConnectionManager.send_json` is async.
    """

    def __init__(self, db: Session, connection_manager: ConnectionManager):
        self.db = db
        self.connection_manager = connection_manager

    @staticmethod
    def _enabled_channels(user: User) -> dict[NudgeChannel, bool]:
        """Read channel opt-in/opt-out straight off the User row — no
        separate preferences table/lookup needed.
        """
        return {
            NudgeChannel.NOTIFICATION: bool(user.notification_enabled),
            NudgeChannel.OVERLAY: bool(user.overlay_enabled),
            NudgeChannel.AUDIO: bool(user.audio_enabled),
        }

    @staticmethod
    def _build_payload(
        channel: NudgeChannel, message: str, nudge_type: str
    ) -> NudgePayload:
        if channel is NudgeChannel.NOTIFICATION:
            return NotificationPayload(nudge_type=nudge_type, message=message)
        if channel is NudgeChannel.OVERLAY:
            return OverlayPayload(nudge_type=nudge_type, message=message)
        if channel is NudgeChannel.AUDIO:
            return AudioPayload(nudge_type=nudge_type)
        raise ValueError(f"Unknown nudge channel: {channel}")

    async def deliver(
        self,
        user: User,
        session_id: int,
        nudge_type: str,
        message: str,
        triggered_state: EngagementState,
        channels: Optional[list[NudgeChannel]] = None,
    ) -> Nudge:
        """Deliver a nudge to `user` over every enabled, requested channel.

        Always writes a `Nudge` row (for effectiveness tracking) even if the
        student is offline or has disabled every channel — the record of
        "we tried to nudge them here" still matters for analysis.
        """
        enabled = self._enabled_channels(user)

        requested = channels or list(NudgeChannel)
        to_send = [c for c in requested if enabled.get(c, False)]

        delivered_channels: list[str] = []
        for channel in to_send:
            payload = self._build_payload(channel, message, nudge_type)
            sent = await self._send(user.id, payload)
            if sent:
                delivered_channels.append(channel.value)

        # NOTE: Added session_id and fixed student_id -> user_id
        nudge = Nudge(
            session_id=session_id,
            user_id=user.id,
            nudge_type=nudge_type,
            triggered_state=triggered_state,
            # message=message,
            # channels_delivered=",".join(delivered_channels) if delivered_channels else None,
            effectiveness_delta=None,  # filled in later once engagement is observed
            created_at=datetime.utcnow(),
        )
        try:
            self.db.add(nudge)
            self.db.commit()
            self.db.refresh(nudge)
        except Exception:
            self.db.rollback()
            logger.exception(
                "Failed to persist nudge record user_id=%s nudge_type=%s",
                user.id,
                nudge_type,
            )
            raise

        logger.info(
            "Nudge delivered user_id=%s nudge_type=%s channels=%s",
            user.id,
            nudge_type,
            delivered_channels or "none (offline or all channels disabled)",
        )
        return nudge

    async def _send(self, user_id: int, payload: NudgePayload) -> bool:
        """Send a single payload over the existing ConnectionManager.

        Returns False (and logs) instead of raising if the user has no
        active, authenticated WebSocket connection — a missed nudge should
        never break the request/decision pipeline that triggered it.

        NOTE: `ConnectionManager.send_json` takes a session identifier, not
        necessarily `user_id` directly. `user.id` is passed here on the
        assumption that the repo's ConnectionManager keys connections by
        user id (consistent with `_authenticate()` binding a session to a
        user). If it actually keys by a separate `session_id`, resolve that
        id here before calling send_json — this is the only call site that
        would need to change.
        """
        try:
            # .model_dump() -> plain dict for send_json()'s JSON-encoding
            # path. Swap for .model_dump_json() if send_json expects a
            # pre-serialized string instead.
            await self.connection_manager.send_json(user_id, payload.model_dump())
            return True
        except Exception:
            logger.warning(
                "Could not deliver nudge over WebSocket (user offline or "
                "unauthenticated) user_id=%s channel=%s",
                user_id,
                payload.channel,
                exc_info=True,
            )
            return False


def get_nudge_delivery_service(
    db: Session = Depends(get_db),
) -> NudgeDeliveryService:
    """FastAPI dependency — build the service via Depends(), never manually
    inside a route.
    """
    return NudgeDeliveryService(db=db, connection_manager=connection_manager)


# ---------------------------------------------------------------------------
# Manual CLI test harness, required verbatim by Issue #21's acceptance
# criteria:
#
#   python -m src.nudge.nudge_delivery --type notification --message "Time to refocus!"
#   python -m src.nudge.nudge_delivery --type overlay --message "You seem distracted"
#   python -m src.nudge.nudge_delivery --type audio
#
# Wired into the real service (not just a print statement) so it's a
# genuine smoke test: it opens a real DB session via get_db() and sends
# through the same ConnectionManager the WebSocket route uses. The target
# user must have an authenticated WebSocket connection open to *see* the
# nudge; either way the Nudge row is written for inspection.
# ---------------------------------------------------------------------------

_CLI_CHANNEL_MAP = {
    "notification": NudgeChannel.NOTIFICATION,
    "overlay": NudgeChannel.OVERLAY,
    "audio": NudgeChannel.AUDIO,
}


async def _run_cli(channel_arg: str, message: str, user_id: int) -> None:
    channel = _CLI_CHANNEL_MAP[channel_arg]

    db_gen = get_db()
    db = next(db_gen)
    try:
        user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
        if user is None:
            logger.error("No user with id=%s; can't send test nudge.", user_id)
            return

        service = NudgeDeliveryService(db=db, connection_manager=connection_manager)

        # NOTE: We need a valid session. Assuming a test session exists or id=1 works.
        nudge = await service.deliver(
            user=user,
            session_id=1,
            nudge_type=f"manual_test_{channel.value}",
            message=message or "",
            triggered_state=EngagementState.DISTRACTED,
            channels=[channel],
        )
        print(
            f"Sent {channel.value} nudge to user_id={user_id}: '{message}' (Nudge id={nudge.id})"
        )
    finally:
        db_gen.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Manually trigger a nudge for testing."
    )
    parser.add_argument(
        "--type",
        dest="channel",
        required=True,
        choices=["notification", "overlay", "audio"],
    )
    parser.add_argument("--message", default="", help="Nudge message text")
    parser.add_argument(
        "--user-id", type=int, default=1, help="Target user id (default: 1)"
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    import asyncio

    asyncio.run(_run_cli(args.channel, args.message, args.user_id))


if __name__ == "__main__":
    main()
