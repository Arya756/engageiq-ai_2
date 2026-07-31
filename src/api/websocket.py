"""WebSocket endpoint for real-time frame streaming.

Browser -> (base64 frame + timestamp over WebSocket) -> this endpoint
       -> src.ingestion.frame_extractor (preprocessing, owned by #4)
       -> src.scoring.engagement_score (weighted score, already implemented)
       -> (engagement score + nudge events back over WebSocket) -> Browser

This module is intentionally written against the *contract* of
``src.ingestion.frame_extractor`` rather than a finished implementation:
that module is still a stub (TODO) pending a teammate's work on #4. Once
#4 lands a real ``preprocess_frame`` (or equivalent), only the small
adapter call in ``_run_pipeline`` below should need updating -- the rest
of the connection-handling, auth, and broadcast logic is independent of
that detail.
"""

from __future__ import annotations

import base64
import json
import logging
from typing import Optional

import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from src.scoring.engagement_score import compute_engagement_score
from src.utils.auth import InvalidSessionToken, verify_session_token

logger = logging.getLogger(__name__)

router = APIRouter()


class ConnectionManager:
    """Tracks active WebSocket connections, keyed by session_id.

    Supports multiple concurrent connections (one per student) and gives
    the rest of the app (teacher dashboard #33, nudge delivery #21) a
    single place to push messages to a given session without needing to
    know about the raw WebSocket object.
    """

    def __init__(self) -> None:
        self._connections: dict[str, WebSocket] = {}

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections[session_id] = websocket
        logger.info(
            "session %s connected (%d active)", session_id, len(self._connections)
        )

    def disconnect(self, session_id: str) -> None:
        self._connections.pop(session_id, None)
        logger.info(
            "session %s disconnected (%d active)", session_id, len(self._connections)
        )

    async def send_json(self, session_id: str, payload: dict) -> None:
        """Push a message (engagement update, nudge event, ...) to one session."""
        ws = self._connections.get(session_id)
        if ws is not None:
            await ws.send_text(json.dumps(payload))

    def is_connected(self, session_id: str) -> bool:
        return session_id in self._connections


# Module-level singleton so #33 (dashboard) and #21 (nudge delivery) can
# import `manager` and push to a session_id without re-plumbing the
# WebSocket connections themselves.
manager = ConnectionManager()


def _decode_frame(frame_b64: str) -> np.ndarray:
    """Decode a base64-encoded raw frame into a numpy array.

    Assumes the browser sends raw uint8 RGB bytes for a 640x480x3 frame,
    matching settings.webcam_resolution. If the frame ingestion format
    changes (e.g. to JPEG bytes) under #4, this is the only place that
    needs to change.
    """
    try:
        raw = base64.b64decode(frame_b64)
        frame = np.frombuffer(raw, dtype=np.uint8)
        frame = frame.reshape((480, 640, 3))
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Could not decode frame: {exc}") from exc
    return frame


def _run_pipeline(frame: np.ndarray) -> float:
    """Preprocess a frame and compute an engagement score.

    NOTE: ``src.ingestion.frame_extractor`` is currently a stub (#4 is
    in progress on a teammate's branch). Until it lands, this falls back
    to neutral placeholder signal scores so the endpoint is testable
    end-to-end. Replace the placeholder block below with calls into the
    real preprocessing + detection pipeline once #4 merges.
    """
    try:
        from src.ingestion import frame_extractor

        preprocess = getattr(frame_extractor, "preprocess_frame", None)
    except ImportError:
        preprocess = None

    if preprocess is not None:
        # Expected future contract: returns the four 0-100 signal scores
        # that compute_engagement_score consumes.
        gaze_score, pose_score, expression_score, alertness_score = preprocess(frame)
    else:
        # Placeholder until #4 lands.
        gaze_score = pose_score = expression_score = alertness_score = 0.50

    return compute_engagement_score(
        gaze_score=gaze_score,
        pose_score=pose_score,
        expression_score=expression_score,
        alertness_score=alertness_score,
    )


async def _authenticate(websocket: WebSocket) -> Optional[str]:
    """Verify the session token query param. Returns the subject, or None."""
    token = websocket.query_params.get("token")
    try:
        return verify_session_token(token)
    except InvalidSessionToken as exc:
        logger.warning("rejected websocket connection: %s", exc)
        return None


@router.websocket("/ws/session/{session_id}")
async def websocket_session(websocket: WebSocket, session_id: str) -> None:
    """Stream frames from the browser and return live engagement scores.

    Protocol:
        Client -> Server: {"frame": "<base64>", "timestamp": <float>}
        Server -> Client: {"session_id": str, "timestamp": float,
                           "engagement_score": float}
        Server -> Client (on error): {"error": str}
    """
    subject = await _authenticate(websocket)
    if subject is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await manager.connect(session_id, websocket)

    try:
        while True:
            raw_message = await websocket.receive_text()

            try:
                message = json.loads(raw_message)
                frame_b64 = message["frame"]
                timestamp = message["timestamp"]
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                await websocket.send_text(json.dumps({"error": f"bad message: {exc}"}))
                continue

            try:
                frame = _decode_frame(frame_b64)
                engagement_score = _run_pipeline(frame)
            except ValueError as exc:
                await websocket.send_text(json.dumps({"error": str(exc)}))
                continue

            await websocket.send_text(
                json.dumps(
                    {
                        "session_id": session_id,
                        "timestamp": timestamp,
                        "engagement_score": engagement_score,
                    }
                )
            )

    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(session_id)
