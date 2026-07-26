"""
Nudge Decision Engine — Updated to respect student preferences.

Now checks:
  - Is the student actually distracted for long enough?
  - Are we in the quiet hours window? (No nudges during quiet time)
  - Has enough cooldown time passed since the last nudge?
  - Have we reached the max nudges allowed per session?
  - What nudge type worked best before? (Learning feedback loop)
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class NudgeDecision:
    """A simple container holding the final decision of the agent."""

    should_nudge: bool
    nudge_type: Optional[str]
    reason: str


# Maps each sensitivity level to the cooldown time in seconds
# "less" = wait 10 minutes before nudging again
# "normal" = wait 5 minutes (the default)
# "more" = wait only 3 minutes (most aggressive)
SENSITIVITY_TO_COOLDOWN = {
    "less": 600,
    "normal": 300,
    "more": 180,
}


def _is_in_quiet_hours(quiet_start: Optional[str], quiet_end: Optional[str]) -> bool:
    """
    Checks if the current time falls inside the student's quiet hours window.

    For example, if quiet_start="22:00" and quiet_end="08:00",
    this returns True anytime between 10 PM and 8 AM the next morning.
    Returns False if quiet hours are not set.
    """
    # If quiet hours are not configured, we are never in quiet time
    if not quiet_start or not quiet_end:
        return False

    # Get the current local time (hour and minute only)
    now = datetime.now().time()

    try:
        # Parse the "HH:MM" strings into actual time objects
        start = datetime.strptime(quiet_start, "%H:%M").time()
        end = datetime.strptime(quiet_end, "%H:%M").time()
    except ValueError:
        # If the format is wrong, don't block nudges — just skip quiet hours
        return False

    # Handle two cases:
    # Case 1: Normal window within the same day (e.g., 09:00 to 17:00)
    if start <= end:
        return start <= now <= end

    # Case 2: Window crosses midnight (e.g., 22:00 to 08:00)
    # In this case, quiet time is active if we are AFTER start OR BEFORE end
    return now >= start or now <= end


class NudgeDecisionEngine:
    """
    Engine that decides whether to nudge a student based on:
    - How long they have been distracted
    - Their personal preference settings (quiet hours, sensitivity)
    - Cooldown between nudges
    - Max nudges per session
    - Which nudge type has worked best for them before (learning loop)
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
        # The three different ways we can nudge a student
        self.nudge_options = ["gentle_reminder", "focus_check", "take_a_break"]

    def should_nudge(
        self,
        current_state: str,
        state_duration: int,
        last_nudge_time: Optional[int],
        session_nudge_count: int,
        effectiveness_history: List[Dict[str, Any]],
        # These are the student's personal preference settings
        sensitivity: str = "normal",
        quiet_hours_start: Optional[str] = None,
        quiet_hours_end: Optional[str] = None,
    ) -> NudgeDecision:
        """
        Evaluates the student's current situation and decides whether to nudge.
        Now respects the student's quiet hours and sensitivity preferences.
        """
        # Rule 1: Is the student actually distracted or drowsy?
        disengaged_states = ["distracted", "drowsy"]
        if current_state.lower() not in disengaged_states:
            return NudgeDecision(False, None, "Student is not distracted.")

        # Rule 2: Has the distraction lasted long enough to act on?
        if state_duration < self.sustained_distraction_seconds:
            return NudgeDecision(False, None, "Distraction duration too short.")

        # Rule 3: Are we in the student's quiet hours? If so, skip the nudge.
        if _is_in_quiet_hours(quiet_hours_start, quiet_hours_end):
            return NudgeDecision(False, None, "Currently in quiet hours.")

        # Rule 4: Have we hit the maximum nudges allowed this session?
        if session_nudge_count >= self.max_nudges:
            return NudgeDecision(False, None, "Max nudges reached for this session.")

        # Rule 5: Look up the cooldown based on the student's sensitivity setting.
        # If the setting is not recognized, fall back to the default (300 seconds).
        effective_cooldown = SENSITIVITY_TO_COOLDOWN.get(
            sensitivity, self.cooldown_seconds
        )

        # Rule 6: Are we still waiting in the cooldown period?
        if last_nudge_time is not None:
            if last_nudge_time < effective_cooldown:
                return NudgeDecision(False, None, "In cooldown period.")

        # All checks passed! Now pick the best nudge type using past history.
        nudge_type = self._select_best_nudge(effectiveness_history)

        return NudgeDecision(True, nudge_type, "Sustained distraction detected.")

    def _select_best_nudge(self, effectiveness_history: List[Dict[str, Any]]) -> str:
        """
        Learning Feedback Loop:
        Calculates the success rate for each nudge type
        and picks the one that worked best in the past.
        """
        if not effectiveness_history:
            # No history yet, use the default (gentle_reminder)
            return self.nudge_options[0]

        # Track how many times each nudge type was used and how often it worked
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
                # Haven't tried this type yet — give it a fair baseline chance
                success_rate = 0.5
            else:
                success_rate = stats[option]["successes"] / tries

            if success_rate > best_rate:
                best_rate = success_rate
                best_type = option

        return best_type
