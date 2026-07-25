"""
Tests for src/nudge/nudge_delivery.py (Issue #21)

Uses pytest + pytest-asyncio, per the existing test suite. The DB session
is a plain sync `Session` mock (matching the repo's SessionLocal-backed
sessions) and `ConnectionManager.send_json` is mocked as async. Channel
preferences live directly on `User` (`notification_enabled`,
`overlay_enabled`, `audio_enabled`), so no separate preferences lookup is
mocked -- tests just set those attributes on the mock user.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.nudge.nudge_delivery import NudgeChannel, NudgeDeliveryService


def make_user(user_id=42, notification=True, overlay=True, audio=True):
    u = MagicMock()
    u.id = user_id
    u.notification_enabled = notification
    u.overlay_enabled = overlay
    u.audio_enabled = audio
    return u


@pytest.fixture
def user():
    return make_user()


@pytest.fixture
def db_session():
    """A minimal sync Session stand-in with the methods the service calls."""
    session = MagicMock()
    session.add = MagicMock()
    session.commit = MagicMock()
    session.refresh = MagicMock()
    session.rollback = MagicMock()
    return session


@pytest.fixture
def connection_manager():
    cm = MagicMock()
    cm.send_json = AsyncMock()
    return cm


@pytest.mark.asyncio
async def test_delivers_over_all_enabled_channels(user, db_session, connection_manager):
    service = NudgeDeliveryService(db=db_session, connection_manager=connection_manager)

    await service.deliver(
        user=user,
        nudge_type="focus_drift",
        message="You seem distracted",
        triggered_state="low_engagement",
    )

    assert connection_manager.send_json.await_count == 3
    sent_channels = {
        call.args[1]["channel"] for call in connection_manager.send_json.await_args_list
    }
    assert sent_channels == {"notification", "overlay", "audio"}


@pytest.mark.asyncio
async def test_respects_disabled_channels(db_session, connection_manager):
    user = make_user(notification=True, overlay=False, audio=False)
    service = NudgeDeliveryService(db=db_session, connection_manager=connection_manager)

    await service.deliver(user=user, nudge_type="focus_drift", message="hi")

    assert connection_manager.send_json.await_count == 1
    sent_channel = connection_manager.send_json.await_args_list[0].args[1]["channel"]
    assert sent_channel == "notification"


@pytest.mark.asyncio
async def test_always_persists_a_nudge_row_even_if_offline(
    user, db_session, connection_manager
):
    connection_manager.send_json.side_effect = ConnectionError("user offline")

    service = NudgeDeliveryService(db=db_session, connection_manager=connection_manager)
    await service.deliver(user=user, nudge_type="focus_drift", message="hi")

    # Delivery attempts fail, but the effectiveness-tracking row is still saved.
    assert db_session.add.called
    assert db_session.commit.call_count == 1
    saved_nudge = db_session.add.call_args.args[0]
    assert saved_nudge.channels_delivered is None
    assert saved_nudge.student_id == user.id


@pytest.mark.asyncio
async def test_audio_payload_respects_duration_and_volume_limits(
    user, db_session, connection_manager
):
    service = NudgeDeliveryService(db=db_session, connection_manager=connection_manager)

    await service.deliver(
        user=user,
        nudge_type="focus_drift",
        message="",
        channels=[NudgeChannel.AUDIO],
    )

    payload = connection_manager.send_json.await_args_list[0].args[1]
    assert payload["channel"] == "audio"
    assert payload["duration_ms"] <= 2000
    assert 0 <= payload["volume"] <= 1


@pytest.mark.asyncio
async def test_overlay_payload_is_non_blocking(user, db_session, connection_manager):
    service = NudgeDeliveryService(db=db_session, connection_manager=connection_manager)

    await service.deliver(
        user=user,
        nudge_type="focus_drift",
        message="You seem distracted",
        channels=[NudgeChannel.OVERLAY],
    )

    payload = connection_manager.send_json.await_args_list[0].args[1]
    assert payload["channel"] == "overlay"
    assert payload["blocking"] is False


@pytest.mark.asyncio
async def test_rolls_back_on_commit_failure(user, db_session, connection_manager):
    db_session.commit.side_effect = RuntimeError("db is down")

    service = NudgeDeliveryService(db=db_session, connection_manager=connection_manager)

    with pytest.raises(RuntimeError):
        await service.deliver(user=user, nudge_type="focus_drift", message="hi")

    assert db_session.rollback.call_count == 1
