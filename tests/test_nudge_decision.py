from src.nudge.nudge_decision import NudgeDecisionEngine


def test_first_distraction_triggers_nudge():
    """Test that a distraction longer than the 30-second threshold triggers a nudge."""
    engine = NudgeDecisionEngine(sustained_distraction_seconds=30)
    decision = engine.should_nudge(
        current_state="distracted",
        state_duration=35,  # Over the 30s threshold
        last_nudge_time=None,
        session_nudge_count=0,
        effectiveness_history=[],
    )
    assert decision.should_nudge is True
    assert decision.nudge_type == "gentle_reminder"


def test_distraction_too_short():
    """Test that we do NOT nudge if the distraction is very brief."""
    engine = NudgeDecisionEngine(sustained_distraction_seconds=30)
    decision = engine.should_nudge(
        current_state="distracted",
        state_duration=10,  # Only 10 seconds (Too short)
        last_nudge_time=None,
        session_nudge_count=0,
        effectiveness_history=[],
    )
    assert decision.should_nudge is False
    assert decision.reason == "Distraction duration too short."


def test_cooldown_prevents_nudge():
    """Test that we wait for the 5-minute cooldown before nudging again."""
    engine = NudgeDecisionEngine(cooldown_seconds=300)
    decision = engine.should_nudge(
        current_state="distracted",
        state_duration=35,
        last_nudge_time=120,  # Only 120 seconds have passed (cooldown is 300)
        session_nudge_count=1,
        effectiveness_history=[],
    )
    assert decision.should_nudge is False
    assert decision.reason == "In cooldown period."


def test_max_nudges_prevents_nudge():
    """Test that we stop nudging entirely after reaching the max limit."""
    engine = NudgeDecisionEngine(max_nudges=5)
    decision = engine.should_nudge(
        current_state="distracted",
        state_duration=35,
        last_nudge_time=600,  # Passed cooldown
        session_nudge_count=5,  # Reached the max limit of 5
        effectiveness_history=[],
    )
    assert decision.should_nudge is False
    assert decision.reason == "Max nudges reached for this session."


def test_uses_effectiveness_history():
    """Test that it intelligently picks a nudge type that worked previously."""
    engine = NudgeDecisionEngine()
    decision = engine.should_nudge(
        current_state="distracted",
        state_duration=35,
        last_nudge_time=None,
        session_nudge_count=0,
        # Update this line to use a dictionary instead of a plain string:
        effectiveness_history=[{"type": "take_a_break", "success": True}],
    )
    assert decision.should_nudge is True
    assert decision.nudge_type == "take_a_break"


def test_not_distracted():
    """Test that we do NOT nudge if the user is engaged and focusing."""
    engine = NudgeDecisionEngine()
    decision = engine.should_nudge(
        current_state="engaged",
        state_duration=500,
        last_nudge_time=None,
        session_nudge_count=0,
        effectiveness_history=[],
    )
    assert decision.should_nudge is False
    assert decision.reason == "Student is not distracted."
