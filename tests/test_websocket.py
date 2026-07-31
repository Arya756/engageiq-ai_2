"""Tests for src/api/websocket.py (issue #5).

Covers the three required cases: connection (with auth), frame
processing (engagement score returned), and disconnect handling
(graceful cleanup, no crash).
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone

import jwt
import numpy as np
import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.api.websocket import manager
from src.config.settings import settings

client = TestClient(app)


def make_token(sub: str = "student-123", expired: bool = False) -> str:
    """Build a JWT matching the contract verify_session_token expects."""
    now = datetime.now(timezone.utc)
    exp = now - timedelta(minutes=5) if expired else now + timedelta(hours=1)
    payload = {"sub": sub, "iat": now, "exp": exp}
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def make_frame_message(timestamp: float = 1.0) -> str:
    """Build a fake 640x480x3 frame, base64-encoded, as the browser would send."""
    frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    frame_b64 = base64.b64encode(frame.tobytes()).decode()
    return json.dumps({"frame": frame_b64, "timestamp": timestamp})


class TestConnection:
    def test_connects_with_valid_token(self):
        """A valid session token should be accepted and registered in the manager."""
        token = make_token(sub="student-123")
        with client.websocket_connect(f"/ws/session/test-session-1?token={token}"):
            assert manager.is_connected("test-session-1")

    def test_rejects_missing_token(self):
        """No token query param should close the connection rather than accept it."""
        with pytest.raises(Exception):
            with client.websocket_connect("/ws/session/test-session-2") as ws:
                ws.receive_text()

    def test_rejects_expired_token(self):
        """An expired JWT should be rejected at connect time."""
        token = make_token(sub="student-123", expired=True)
        with pytest.raises(Exception):
            with client.websocket_connect(
                f"/ws/session/test-session-3?token={token}"
            ) as ws:
                ws.receive_text()


class TestFrameProcessing:
    def test_sends_engagement_score_after_frame(self):
        """Sending a frame should return a JSON message with an engagement_score."""
        token = make_token(sub="student-123")
        with client.websocket_connect(
            f"/ws/session/test-session-4?token={token}"
        ) as ws:
            ws.send_text(make_frame_message(timestamp=1.0))
            response = json.loads(ws.receive_text())

        assert "engagement_score" in response
        assert isinstance(response["engagement_score"], (int, float))
        assert response["session_id"] == "test-session-4"
        assert response["timestamp"] == 1.0

    def test_engagement_score_within_valid_range(self):
        """Score should be within the documented 0-100 range given 0-100 inputs."""
        token = make_token(sub="student-123")
        with client.websocket_connect(
            f"/ws/session/test-session-5?token={token}"
        ) as ws:
            ws.send_text(make_frame_message())
            response = json.loads(ws.receive_text())

        assert 0.0 <= response["engagement_score"] <= 1.0

    def test_malformed_message_returns_error_not_crash(self):
        """A bad payload should get an error response, not kill the connection."""
        token = make_token(sub="student-123")
        with client.websocket_connect(
            f"/ws/session/test-session-6?token={token}"
        ) as ws:
            ws.send_text(json.dumps({"not_a_frame": True}))
            response = json.loads(ws.receive_text())
            assert "error" in response

            # Connection should still be alive afterwards.
            ws.send_text(make_frame_message())
            response2 = json.loads(ws.receive_text())
            assert "engagement_score" in response2


class TestDisconnect:
    def test_cleans_up_on_disconnect(self):
        """Closing the connection should remove it from the ConnectionManager."""
        token = make_token(sub="student-123")
        with client.websocket_connect(f"/ws/session/test-session-7?token={token}"):
            assert manager.is_connected("test-session-7")

        assert not manager.is_connected("test-session-7")

    def test_multiple_concurrent_sessions_independent(self):
        """Two sessions connecting concurrently shouldn't interfere with each other."""
        token_a = make_token(sub="student-a")
        token_b = make_token(sub="student-b")

        with client.websocket_connect(f"/ws/session/session-a?token={token_a}") as ws_a:
            with client.websocket_connect(f"/ws/session/session-b?token={token_b}"):
                assert manager.is_connected("session-a")
                assert manager.is_connected("session-b")

                ws_a.send_text(make_frame_message())
                resp_a = json.loads(ws_a.receive_text())
                assert resp_a["session_id"] == "session-a"

            # session-b closed, session-a should remain connected.
            assert manager.is_connected("session-a")
            assert not manager.is_connected("session-b")

        assert not manager.is_connected("session-a")
