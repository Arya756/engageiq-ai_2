import pytest

from src.nudge.effectiveness_tracker import EffectivenessTracker


def test_issue_snippet_notification_effective():
    # Exactly the issue's own worked example.
    tracker = EffectivenessTracker(measurement_window=60)

    tracker.record_nudge(nudge_type="notification", timestamp=0, pre_score=35)
    tracker.record_post_score(timestamp=30, score=55)
    tracker.record_post_score(timestamp=60, score=65)
    result = tracker.evaluate_last_nudge()

    assert result.effective is True
    assert result.delta == pytest.approx(25.0)


def test_issue_snippet_audio_not_effective():
    tracker = EffectivenessTracker(measurement_window=60)
    tracker.record_nudge(nudge_type="notification", timestamp=0, pre_score=35)
    tracker.record_post_score(timestamp=30, score=55)
    tracker.record_post_score(timestamp=60, score=65)
    tracker.evaluate_last_nudge()

    tracker.record_nudge(nudge_type="audio", timestamp=120, pre_score=30)
    tracker.record_post_score(timestamp=150, score=32)
    result = tracker.evaluate_last_nudge()

    assert result.effective is False
    assert result.delta == pytest.approx(2.0)


def test_issue_snippet_success_rate():
    tracker = EffectivenessTracker(measurement_window=60)
    tracker.record_nudge(nudge_type="notification", timestamp=0, pre_score=35)
    tracker.record_post_score(timestamp=30, score=55)
    tracker.record_post_score(timestamp=60, score=65)
    tracker.evaluate_last_nudge()

    stats = tracker.get_stats()
    assert stats["notification"].success_rate == pytest.approx(1.0)


def test_effective_boundary_exactly_10_points_counts_as_effective():
    tracker = EffectivenessTracker(measurement_window=60)
    tracker.record_nudge(nudge_type="overlay", timestamp=0, pre_score=40)
    tracker.record_post_score(timestamp=30, score=50)  # exactly +10
    result = tracker.evaluate_last_nudge()

    assert result.delta == pytest.approx(10.0)
    assert result.effective is True


def test_score_outside_window_is_excluded():
    tracker = EffectivenessTracker(measurement_window=60)
    tracker.record_nudge(nudge_type="notification", timestamp=0, pre_score=35)
    tracker.record_post_score(timestamp=90, score=90)  # outside the 60s window
    result = tracker.evaluate_last_nudge()

    # No in-window samples -> nothing to evaluate.
    assert result is None


def test_no_post_scores_recorded_returns_none():
    tracker = EffectivenessTracker(measurement_window=60)
    tracker.record_nudge(nudge_type="notification", timestamp=0, pre_score=35)
    result = tracker.evaluate_last_nudge()
    assert result is None


def test_evaluate_with_no_pending_nudge_returns_none():
    tracker = EffectivenessTracker(measurement_window=60)
    assert tracker.evaluate_last_nudge() is None


def test_multiple_nudge_types_tracked_independently():
    tracker = EffectivenessTracker(measurement_window=60)

    tracker.record_nudge(nudge_type="notification", timestamp=0, pre_score=35)
    tracker.record_post_score(timestamp=30, score=60)  # +25, effective
    tracker.evaluate_last_nudge()

    tracker.record_nudge(nudge_type="audio", timestamp=100, pre_score=30)
    tracker.record_post_score(timestamp=130, score=31)  # +1, not effective
    tracker.evaluate_last_nudge()

    tracker.record_nudge(nudge_type="audio", timestamp=200, pre_score=30)
    tracker.record_post_score(timestamp=230, score=45)  # +15, effective
    tracker.evaluate_last_nudge()

    stats = tracker.get_stats()
    assert stats["notification"].attempts == 1
    assert stats["notification"].success_rate == pytest.approx(1.0)
    assert stats["audio"].attempts == 2
    assert stats["audio"].successes == 1
    assert stats["audio"].success_rate == pytest.approx(0.5)


def test_average_of_multiple_post_scores_in_window():
    tracker = EffectivenessTracker(measurement_window=60)
    tracker.record_nudge(nudge_type="notification", timestamp=0, pre_score=40)
    tracker.record_post_score(timestamp=10, score=50)
    tracker.record_post_score(timestamp=20, score=60)
    tracker.record_post_score(timestamp=30, score=40)
    result = tracker.evaluate_last_nudge()

    # avg of [50, 60, 40] = 50; delta = 50 - 40 = 10
    assert result.post_score_avg == pytest.approx(50.0)
    assert result.delta == pytest.approx(10.0)
    assert result.sample_count == 3


def test_to_decision_history_matches_decision_agent_shape():
    tracker = EffectivenessTracker(measurement_window=60)
    tracker.record_nudge(nudge_type="notification", timestamp=0, pre_score=35)
    tracker.record_post_score(timestamp=30, score=60)
    tracker.evaluate_last_nudge()

    tracker.record_nudge(nudge_type="audio", timestamp=100, pre_score=30)
    tracker.record_post_score(timestamp=130, score=31)
    tracker.evaluate_last_nudge()

    history = tracker.to_decision_history()

    assert history == [
        {"type": "notification", "success": True},
        {"type": "audio", "success": False},
    ]
    # Directly usable by NudgeDecisionEngine.should_nudge(effectiveness_history=...)
    for entry in history:
        assert set(entry.keys()) == {"type", "success"}


def test_custom_effective_threshold():
    tracker = EffectivenessTracker(measurement_window=60, effective_threshold=20.0)
    tracker.record_nudge(nudge_type="notification", timestamp=0, pre_score=35)
    tracker.record_post_score(timestamp=30, score=50)  # +15, below custom threshold
    result = tracker.evaluate_last_nudge()

    assert result.delta == pytest.approx(15.0)
    assert result.effective is False


def test_db_persistence_mode_writes_delta_back_to_nudge_row():
    """DB mode: evaluate_last_nudge() should persist the computed delta
    onto the Nudge row, and get_stats()/to_decision_history() should read
    from the DB (per-student, across sessions) rather than only in-memory
    state."""

    class FakeNudgeRow:
        def __init__(self, id, user_id, nudge_type, effectiveness_delta, created_at):
            self.id = id
            self.user_id = user_id
            self.nudge_type = nudge_type
            self.effectiveness_delta = effectiveness_delta
            self.created_at = created_at

    class FakeQuery:
        def __init__(self, rows):
            self._rows = rows

        def filter(self, *args, **kwargs):
            return self

        def all(self):
            return self._rows

    class FakeDB:
        def __init__(self, rows):
            self._rows = rows
            self.committed = False

        def get(self, model, nudge_id):
            for row in self._rows:
                if row.id == nudge_id:
                    return row
            return None

        def commit(self):
            self.committed = True

        def query(self, model):
            return FakeQuery(self._rows)

    # A prior session already has one persisted, effective notification nudge.
    existing_row = FakeNudgeRow(
        id=1,
        user_id=42,
        nudge_type="notification",
        effectiveness_delta=25.0,
        created_at=None,
    )
    new_row = FakeNudgeRow(
        id=2,
        user_id=42,
        nudge_type="audio",
        effectiveness_delta=None,
        created_at=None,
    )
    fake_db = FakeDB([existing_row, new_row])

    tracker = EffectivenessTracker(measurement_window=60, student_id=42, db=fake_db)
    tracker.record_nudge(nudge_type="audio", timestamp=0, pre_score=30, nudge_id=2)
    tracker.record_post_score(timestamp=30, score=32)
    result = tracker.evaluate_last_nudge()

    assert result.delta == pytest.approx(2.0)
    assert new_row.effectiveness_delta == pytest.approx(2.0)  # persisted
    assert fake_db.committed is True

    stats = tracker.get_stats()
    # Both the pre-existing session's nudge and this session's nudge show up.
    assert stats["notification"].attempts == 1
    assert stats["audio"].attempts == 1


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
