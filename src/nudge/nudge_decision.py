from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class NudgeDecision:
    """A simple container holding the final decision of the agent."""

    should_nudge: bool
    nudge_type: Optional[str]
    reason: str


class NudgeDecisionEngine:
    """
    Engine that decides whether to nudge a student based on time,
    cooldowns, and maximum session limits, with a learning loop.
    """

    def __init__(
        self,
        cooldown_seconds: int = 300,
        max_nudges: int = 5,
        sustained_distraction_seconds: int = 30,
    ):
        self.cooldown_seconds = cooldown_seconds
        self.max_nudges = max_nudges
        self.sustained_distraction_seconds = sustained_distraction_seconds
        # Available nudge options
        self.nudge_options = ["gentle_reminder", "focus_check", "take_a_break"]

    def should_nudge(
        self,
        current_state: str,
        state_duration: int,
        last_nudge_time: Optional[int],
        session_nudge_count: int,
        effectiveness_history: List[Dict[str, Any]],
    ) -> NudgeDecision:
        """
        Evaluates the student's current situation and makes a decision.
        """
        # Rule 1: Is the student actually distracted?
        disengaged_states = ["distracted", "drowsy"]
        if current_state.lower() not in disengaged_states:
            return NudgeDecision(False, None, "Student is not distracted.")

        # Rule 2: Has the distraction lasted long enough?
        if state_duration < self.sustained_distraction_seconds:
            return NudgeDecision(False, None, "Distraction duration too short.")

        # Rule 3: Have we reached the max limit?
        if session_nudge_count >= self.max_nudges:
            return NudgeDecision(False, None, "Max nudges reached for this session.")

        # Rule 4: Are we in the cooldown period?
        if last_nudge_time is not None:
            if last_nudge_time < self.cooldown_seconds:
                return NudgeDecision(False, None, "In cooldown period.")

        # If we pass all rules, select the best nudge type using the feedback loop
        nudge_type = self._select_best_nudge(effectiveness_history)

        return NudgeDecision(True, nudge_type, "Sustained distraction detected.")

    def _select_best_nudge(self, effectiveness_history: List[Dict[str, Any]]) -> str:
        """
        Learning Feedback Loop: Calculates the success rate for each nudge type
        and selects the one with the highest success rate.
        """
        if not effectiveness_history:
            return self.nudge_options[0]  # Default to first option (gentle_reminder)

        # Track total tries and successful outcomes per nudge type
        stats = {option: {"tries": 0, "successes": 0} for option in self.nudge_options}

        for record in effectiveness_history:
            n_type = record.get("type")
            success = record.get("success", False)
            if n_type in stats:
                stats[n_type]["tries"] += 1
                if success:
                    stats[n_type]["successes"] += 1

        best_type = self.nudge_options[0]
        best_rate = -1.0

        for option in self.nudge_options:
            tries = stats[option]["tries"]
            if tries == 0:
                # If we haven't tried this option yet, give it a baseline chance (e.g., 0.5)
                # to encourage exploring other nudges
                success_rate = 0.5
            else:
                success_rate = stats[option]["successes"] / tries

            if success_rate > best_rate:
                best_rate = success_rate
                best_type = option

        return best_type
