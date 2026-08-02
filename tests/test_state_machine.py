import math
from datetime import datetime, timezone

import pytest

from src.scoring.state_machine import (
    EngagementState,
    EngagementStateMachine,
)


# ---------------------------------------------------------------------------
# Helpers & Fixtures
# ---------------------------------------------------------------------------
def dt(seconds: float) -> datetime:
    """Helper to generate sequential timestamps easily."""
    return datetime.fromtimestamp(seconds, tz=timezone.utc)


@pytest.fixture
def fsm():
    """Returns a fresh FSM instance for each test."""
    return EngagementStateMachine()


# ---------------------------------------------------------------------------
# 1. Initial state confirmation
# ---------------------------------------------------------------------------
def test_initial_state_confirmation(fsm):
    """Verify the first observation is confirmed immediately and emits event."""
    assert fsm.current_state is None

    events = []
    fsm.subscribe(events.append)

    state = fsm.update(score=0.85, is_drowsy=False, is_confused=False, timestamp=dt(0))

    assert state == EngagementState.ENGAGED
    assert fsm.current_state == EngagementState.ENGAGED
    assert fsm.pending_candidate is None

    # Event verification: None -> ENGAGED
    assert len(events) == 1
    assert events[0].from_state is None
    assert events[0].to_state == EngagementState.ENGAGED


# ---------------------------------------------------------------------------
# 2. Sustained engaged
# ---------------------------------------------------------------------------
def test_sustained_engaged(fsm):
    """Ensure remaining in the same state does not create unnecessary transitions."""
    fsm.update(score=0.90, timestamp=dt(0))
    assert fsm.current_state == EngagementState.ENGAGED

    events = []
    fsm.subscribe(events.append)

    # Feed multiple high scores over time
    fsm.update(score=0.85, timestamp=dt(2))
    fsm.update(score=0.95, timestamp=dt(5))
    fsm.update(score=0.88, timestamp=dt(10))

    assert fsm.current_state == EngagementState.ENGAGED
    assert len(events) == 0
    assert fsm.pending_candidate is None


# ---------------------------------------------------------------------------
# 3. Brief dip (Hysteresis)
# ---------------------------------------------------------------------------
def test_brief_dip_hysteresis(fsm):
    """Verify transient drops do not cause transitions."""
    fsm.update(score=0.90, timestamp=dt(0))
    assert fsm.current_state == EngagementState.ENGAGED

    events = []
    fsm.subscribe(events.append)

    # Dip into DISTRACTED range (score=0.30) for 10 seconds (needs 15s to confirm)
    fsm.update(score=0.30, timestamp=dt(2))
    fsm.update(score=0.30, timestamp=dt(12))

    assert fsm.current_state == EngagementState.ENGAGED
    assert fsm.pending_candidate is not None
    assert fsm.pending_candidate["candidate_state"] == EngagementState.DISTRACTED.value

    # Recover back to ENGAGED
    fsm.update(score=0.85, timestamp=dt(13))

    assert fsm.current_state == EngagementState.ENGAGED
    assert fsm.pending_candidate is None
    assert len(events) == 0


# ---------------------------------------------------------------------------
# 4. Sustained passive
# ---------------------------------------------------------------------------
def test_sustained_passive(fsm):
    """Verify transition to PASSIVE after 30 seconds."""
    fsm.update(score=0.90, timestamp=dt(0))

    events = []
    fsm.subscribe(events.append)

    # Passive range (score=0.55)
    fsm.update(score=0.55, timestamp=dt(5))
    assert fsm.current_state == EngagementState.ENGAGED

    # 29 seconds later (total 29s in passive)
    fsm.update(score=0.55, timestamp=dt(34))
    assert fsm.current_state == EngagementState.ENGAGED

    # 31 seconds elapsed -> should trigger transition
    fsm.update(score=0.55, timestamp=dt(36))

    assert fsm.current_state == EngagementState.PASSIVE
    assert len(events) == 1
    assert events[0].from_state == EngagementState.ENGAGED
    assert events[0].to_state == EngagementState.PASSIVE
    assert fsm.history[-1]["confirmed_state"] == EngagementState.PASSIVE.value


# ---------------------------------------------------------------------------
# 5. Sustained distracted
# ---------------------------------------------------------------------------
def test_sustained_distracted(fsm):
    """Verify transition to DISTRACTED after 15 seconds."""
    fsm.update(score=0.90, timestamp=dt(0))

    # Distracted range (score=30) starts at t=10
    fsm.update(score=0.30, timestamp=dt(10))
    assert fsm.current_state == EngagementState.ENGAGED

    # 14 seconds in
    fsm.update(score=0.30, timestamp=dt(24))
    assert fsm.current_state == EngagementState.ENGAGED

    # 16 seconds elapsed -> should trigger transition
    fsm.update(score=0.30, timestamp=dt(26))
    assert fsm.current_state == EngagementState.DISTRACTED


# ---------------------------------------------------------------------------
# 6. Gradual decline
# ---------------------------------------------------------------------------
def test_gradual_decline(fsm):
    """Verify correct sequential transitions: ENGAGED -> PASSIVE -> DISTRACTED."""
    fsm.update(score=0.90, timestamp=dt(0))
    assert fsm.current_state == EngagementState.ENGAGED

    # Drop to PASSIVE for > 30s
    fsm.update(score=0.55, timestamp=dt(10))
    fsm.update(score=0.55, timestamp=dt(45))
    assert fsm.current_state == EngagementState.PASSIVE

    # Drop to DISTRACTED for > 15s
    fsm.update(score=0.30, timestamp=dt(50))
    fsm.update(score=0.30, timestamp=dt(68))
    assert fsm.current_state == EngagementState.DISTRACTED


# ---------------------------------------------------------------------------
# 7. Drowsy override
# ---------------------------------------------------------------------------
def test_drowsy_override_true(fsm):
    """Case A: Drowsy flag overrides score partition (hysteresis is 10s),
    provided the score is also low enough to be plausible (<= 0.30 by default)."""
    fsm.update(score=0.90, timestamp=dt(0))

    # Score 0.20 (normally Distracted, and <= drowsy_max_score), with
    # is_drowsy=True forces DROWSY
    fsm.update(score=0.20, is_drowsy=True, timestamp=dt(10))

    # 9 seconds elapsed
    fsm.update(score=0.20, is_drowsy=True, timestamp=dt(19))
    assert fsm.current_state == EngagementState.ENGAGED

    # 11 seconds elapsed
    fsm.update(score=0.20, is_drowsy=True, timestamp=dt(21))
    assert fsm.current_state == EngagementState.DROWSY


def test_drowsy_override_false(fsm):
    """Case B: Without flag, even extreme low scores fall back to Distracted."""
    fsm.update(score=0.90, timestamp=dt(0))

    # Score 5 with is_drowsy=False should be considered DISTRACTED
    fsm.update(score=0.05, is_drowsy=False, timestamp=dt(10))

    # Wait past the Distracted 15s hysteresis
    fsm.update(score=0.05, is_drowsy=False, timestamp=dt(26))

    assert fsm.current_state == EngagementState.DISTRACTED


def test_drowsy_flag_gated_by_score(fsm):
    """A high score with is_drowsy=True is treated as noise/mislabeled input
    and must NOT be classified as DROWSY -- it falls back to the score bands."""
    fsm.update(score=0.90, timestamp=dt(0))

    # score=0.90 is well above the default drowsy_max_score (0.30), so the
    # drowsy flag should be ignored and the observation classified as ENGAGED.
    fsm.update(score=0.90, is_drowsy=True, timestamp=dt(5))
    assert fsm.current_state == EngagementState.ENGAGED
    assert fsm.pending_candidate is None

    # Same principle in the PASSIVE band: score=0.55 with is_drowsy=True should
    # start (or need) a PASSIVE candidate, not a DROWSY one.
    fsm.update(score=0.55, is_drowsy=True, timestamp=dt(10))
    fsm.update(score=0.55, is_drowsy=True, timestamp=dt(41))  # >30s -> confirm PASSIVE
    assert fsm.current_state == EngagementState.PASSIVE


def test_drowsy_flag_at_exact_gate_boundary(fsm):
    """score == drowsy_max_score should still count as drowsy (inclusive bound)."""
    fsm.update(score=0.90, timestamp=dt(0))

    fsm.update(score=0.30, is_drowsy=True, timestamp=dt(10))  # == default gate of 0.30
    fsm.update(score=0.30, is_drowsy=True, timestamp=dt(21))  # >10s -> confirm DROWSY
    assert fsm.current_state == EngagementState.DROWSY


# ---------------------------------------------------------------------------
# 8. Confused override
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "score, is_confused", [(0.90, True), (0.55, True), (0.10, True)]
)
def test_confused_override(fsm, score, is_confused):
    """Ensure confusion has highest priority regardless of score (hysteresis is 20s)."""
    fsm.update(score=0.85, timestamp=dt(0))

    fsm.update(score=score, is_confused=is_confused, timestamp=dt(5))

    # 19 seconds elapsed
    fsm.update(score=score, is_confused=is_confused, timestamp=dt(24))
    assert fsm.current_state == EngagementState.ENGAGED

    # 21 seconds elapsed
    fsm.update(score=score, is_confused=is_confused, timestamp=dt(26))
    assert fsm.current_state == EngagementState.CONFUSED


def test_confused_overrides_drowsy(fsm):
    """When both flags are set, confusion wins (highest priority)."""
    fsm.update(score=0.90, timestamp=dt(0))

    fsm.update(score=0.20, is_drowsy=True, is_confused=True, timestamp=dt(10))
    fsm.update(score=0.20, is_drowsy=True, is_confused=True, timestamp=dt(31))

    assert fsm.current_state == EngagementState.CONFUSED


# ---------------------------------------------------------------------------
# 9. Candidate reset
# ---------------------------------------------------------------------------
def test_candidate_reset(fsm):
    """Verify hysteresis timer resets correctly when interrupted."""
    fsm.update(score=0.90, timestamp=dt(0))

    # PASSIVE candidate started at t=10
    fsm.update(score=0.55, timestamp=dt(10))

    # Still PASSIVE candidate, dwelled for 20s
    fsm.update(score=0.55, timestamp=dt(30))
    assert fsm.current_state == EngagementState.ENGAGED

    # Snap back to ENGAGED at t=31 (resets timer)
    fsm.update(score=0.90, timestamp=dt(31))
    assert fsm.pending_candidate is None

    # PASSIVE candidate starts AGAIN at t=40
    fsm.update(score=0.55, timestamp=dt(40))

    # 29s into second attempt -> should still be engaged
    fsm.update(score=0.55, timestamp=dt(69))
    assert fsm.current_state == EngagementState.ENGAGED

    # Transition occurs only after full 30s from second attempt (t=71)
    fsm.update(score=0.55, timestamp=dt(71))
    assert fsm.current_state == EngagementState.PASSIVE


# ---------------------------------------------------------------------------
# 10. Timestamp validation
# ---------------------------------------------------------------------------
def test_timestamp_validation(fsm):
    """Ensure timestamps are monotonic."""
    fsm.update(score=0.85, timestamp=dt(10))

    with pytest.raises(ValueError):
        fsm.update(score=0.85, timestamp=dt(5))


# ---------------------------------------------------------------------------
# 11. Score validation
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("invalid_score", [-1.0, 1.01, math.nan, math.inf, -math.inf])
def test_score_validation(fsm, invalid_score):
    """Verify invalid scores raise a ValueError."""
    with pytest.raises(ValueError):
        fsm.update(score=invalid_score, timestamp=dt(0))


# ---------------------------------------------------------------------------
# 12. Event system
# ---------------------------------------------------------------------------
def test_event_system_dedup_behavioral(fsm):
    """Behavioral counterpart to test_event_system: a duplicate-subscribed
    callback must only be invoked once per transition."""
    calls = []

    def callback(evt):
        calls.append(evt)

    fsm.subscribe(callback)
    fsm.subscribe(callback)

    fsm.update(score=0.90, timestamp=dt(0))  # first observation -> one transition

    assert len(calls) == 1


def test_listener_exception_does_not_break_update_or_other_listeners(fsm):
    """A raising subscriber must not prevent update() from completing or
    prevent other subscribers from receiving the event."""
    calls = []

    def bad_listener(evt):
        raise RuntimeError("boom")

    def good_listener(evt):
        calls.append(evt)

    fsm.subscribe(bad_listener)
    fsm.subscribe(good_listener)

    # Should not raise, despite bad_listener raising internally.
    state = fsm.update(score=0.90, timestamp=dt(0))

    assert state == EngagementState.ENGAGED
    assert len(calls) == 1
    assert calls[0].to_state == EngagementState.ENGAGED


# ---------------------------------------------------------------------------
# 13. History logging
# ---------------------------------------------------------------------------
def test_history_logging():
    """History entries contain required fields and respect max_history limit."""
    fsm = EngagementStateMachine(max_history=3)

    fsm.update(score=0.90, timestamp=dt(0))
    fsm.update(score=0.30, timestamp=dt(5))
    fsm.update(score=0.30, timestamp=dt(6))
    fsm.update(score=0.30, timestamp=dt(7))  # This 4th update pushes out the first

    # Verify history size limit
    assert len(fsm.history) == 3

    latest = fsm.history[-1]

    # Check fields based on standard dict output structure
    assert "timestamp" in latest
    assert "instantaneous_state" in latest
    assert "confirmed_state" in latest
    assert "score" in latest


# ---------------------------------------------------------------------------
# 14. Immediate ENGAGED re-entry
# ---------------------------------------------------------------------------
def test_immediate_engaged_reentry(fsm):
    """By default, ENGAGED has 0s hysteresis: a single observation is enough
    to transition back into ENGAGED from a different confirmed state."""
    fsm.update(score=0.90, timestamp=dt(0))

    # Confirm DISTRACTED first.
    fsm.update(score=0.30, timestamp=dt(10))
    fsm.update(score=0.30, timestamp=dt(30))
    assert fsm.current_state == EngagementState.DISTRACTED

    events = []
    fsm.subscribe(events.append)

    # A single subsequent update with a high score should confirm ENGAGED
    # immediately, with no additional dwell time required.
    fsm.update(score=0.90, timestamp=dt(31))

    assert fsm.current_state == EngagementState.ENGAGED
    assert fsm.pending_candidate is None
    assert len(events) == 1
    assert events[0].from_state == EngagementState.DISTRACTED
    assert events[0].to_state == EngagementState.ENGAGED


# ---------------------------------------------------------------------------
# 15. Configurability
# ---------------------------------------------------------------------------
def test_configurable_score_bands():
    """Score band boundaries (passive_min, engaged_min) must be overridable."""
    fsm = EngagementStateMachine(passive_min=0.50, engaged_min=0.80)

    # score=0.75 would be ENGAGED under defaults, but is PASSIVE under these
    # custom thresholds.
    fsm.update(score=0.90, timestamp=dt(0))
    fsm.update(score=0.75, timestamp=dt(1))
    fsm.update(score=0.75, timestamp=dt(32))  # 31s elapsed, > 30s PASSIVE hysteresis

    assert fsm.current_state == EngagementState.PASSIVE


def test_configurable_drowsy_max_score():
    """drowsy_max_score must be overridable and gate the drowsy flag."""
    fsm = EngagementStateMachine(drowsy_max_score=0.60)

    fsm.update(score=0.90, timestamp=dt(0))

    # score=0.50 would not be drowsy-eligible under the default gate (30), but
    # is eligible under this custom gate (60).
    fsm.update(score=0.50, is_drowsy=True, timestamp=dt(10))
    fsm.update(score=0.50, is_drowsy=True, timestamp=dt(21))  # > 10s DROWSY hysteresis

    assert fsm.current_state == EngagementState.DROWSY


def test_configurable_hysteresis_seconds():
    """hysteresis_seconds overrides must be honored per-state, with
    unspecified states falling back to their defaults."""
    fsm = EngagementStateMachine(hysteresis_seconds={EngagementState.PASSIVE: 5.0})

    fsm.update(score=0.90, timestamp=dt(0))
    fsm.update(score=0.55, timestamp=dt(1))
    fsm.update(score=0.55, timestamp=dt(4))  # 3s elapsed < custom 5s -> still ENGAGED
    assert fsm.current_state == EngagementState.ENGAGED

    fsm.update(score=0.55, timestamp=dt(7))  # 6s elapsed >= custom 5s -> PASSIVE
    assert fsm.current_state == EngagementState.PASSIVE


def test_invalid_configuration_raises():
    """Constructor should reject nonsensical threshold configurations."""
    with pytest.raises(ValueError):
        EngagementStateMachine(passive_min=0.80, engaged_min=0.50)  # passive > engaged

    with pytest.raises(ValueError):
        EngagementStateMachine(max_history=0)

    with pytest.raises(ValueError):
        EngagementStateMachine(drowsy_max_score=1.5)

    with pytest.raises(ValueError):
        EngagementStateMachine(hysteresis_seconds={EngagementState.PASSIVE: -5.0})
