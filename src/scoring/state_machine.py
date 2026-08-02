"""
Engagement State Machine (Issue #17)
=====================================

Converts three input signals into one of 5 discrete, actionable states:

    ENGAGED -> PASSIVE -> DISTRACTED     (score-driven partition)
    CONFUSED                              (override: expression classifier)
    DROWSY                                (override: drowsiness detector, low score only)

Inputs to `update()`:
    - score:        continuous engagement score, 0-1 (Issue #16)
    - is_drowsy:     boolean output of the drowsiness detector (Issue #12)
    - is_confused:   boolean output of the expression classifier (Issue #14)

Classification order per reading:
    1. is_confused=True                          -> CONFUSED   (any score)
    2. is_drowsy=True and score <= DROWSY cutoff  -> DROWSY
    3. otherwise                                  -> score mapped into the
                                                       ENGAGED / PASSIVE / DISTRACTED
                                                       partition (must cover
                                                       [0, 1] with no gaps
                                                       or overlaps)

A transition is only *confirmed* (updates `current_state`, gets logged to
history, and fires subscriber events) once the incoming instantaneous state
has been produced continuously for at least that state's `min_duration_s`
hysteresis window. A brief flicker that reverts before the window elapses is
discarded and the machine stays in its current state.

Exception: the very first reading a machine ever sees is confirmed
immediately, with no hysteresis wait (e.g. score=0.85 on frame 1 -> ENGAGED
right away). Hysteresis only applies to *subsequent* transitions.

This module has no external dependencies beyond the standard library so it
can be dropped into any pipeline that calls `update(score, is_drowsy,
is_confused, timestamp)` on each new reading.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class EngagementState(Enum):
    """The 5 actionable engagement states."""

    ENGAGED = "engaged"
    PASSIVE = "passive"
    CONFUSED = "confused"
    DISTRACTED = "distracted"
    DROWSY = "drowsy"


# States that own a contiguous slice of the 0-1 score axis and together
# must partition it with no gaps or overlaps. CONFUSED and DROWSY are
# *overrides* layered on top of this partition (see _instantaneous_state)
# and are intentionally excluded here.
_PARTITION_ORDER: List[EngagementState] = [
    EngagementState.ENGAGED,
    EngagementState.PASSIVE,
    EngagementState.DISTRACTED,
]
_PARTITION_STATES = frozenset(_PARTITION_ORDER)

# Floating point tolerance used when checking that partition boundaries
# touch (rather than gap or overlap), to accommodate configs that use
# "off by a hair" boundaries like max_score=0.69999 / min_score=0.70.
_BOUNDARY_EPS = 0.0001


@dataclass(frozen=True)
class StateConfig:
    """
    Hysteresis duration required to confirm a state, plus (for partition
    states) the score range it owns.

    - Partition states (ENGAGED, PASSIVE, DISTRACTED) MUST set min_score
      and max_score; together these ranges must cover [0, 100] with no
      gaps or overlaps.
    - CONFUSED is a pure override: it applies at any score when
      is_confused=True, so min_score/max_score are left as None.
    - DROWSY is a conditional override: it only applies when is_drowsy=True
      AND score <= max_score. min_score is unused/ignored for DROWSY;
      only max_score (the cutoff) matters.
    """

    min_duration_s: float
    min_score: Optional[float] = None
    max_score: Optional[float] = None

    def contains(self, score: float) -> bool:
        if self.min_score is None or self.max_score is None:
            return False
        return self.min_score <= score <= self.max_score


ENGAGED_MIN_SCORE = 0.70
ENGAGED_MAX_SCORE = 1.0

PASSIVE_MIN_SCORE = 0.40
PASSIVE_MAX_SCORE = 0.69999

DISTRACTED_MIN_SCORE = 0.0
DISTRACTED_MAX_SCORE = 0.39999

DROWSY_MAX_SCORE = 0.30

ENGAGED_DURATION = 0.0
PASSIVE_DURATION = 30.0
DISTRACTED_DURATION = 15.0
DROWSY_DURATION = 10.0
CONFUSED_DURATION = 20.0

DEFAULT_STATE_CONFIG: Dict[EngagementState, StateConfig] = {
    EngagementState.ENGAGED: StateConfig(
        min_duration_s=ENGAGED_DURATION,
        min_score=ENGAGED_MIN_SCORE,
        max_score=ENGAGED_MAX_SCORE,
    ),
    EngagementState.PASSIVE: StateConfig(
        min_duration_s=PASSIVE_DURATION,
        min_score=PASSIVE_MIN_SCORE,
        max_score=PASSIVE_MAX_SCORE,
    ),
    EngagementState.DISTRACTED: StateConfig(
        min_duration_s=DISTRACTED_DURATION,
        min_score=DISTRACTED_MIN_SCORE,
        max_score=DISTRACTED_MAX_SCORE,
    ),
    EngagementState.DROWSY: StateConfig(
        min_duration_s=DROWSY_DURATION,
        max_score=DROWSY_MAX_SCORE,
    ),
    EngagementState.CONFUSED: StateConfig(
        min_duration_s=CONFUSED_DURATION,
    ),
}


@dataclass
class StateTransitionEvent:
    """Emitted whenever a transition is confirmed. Subscribe via `.subscribe()`."""

    timestamp: datetime
    from_state: Optional[EngagementState]
    to_state: EngagementState
    score: float
    time_in_previous_state_s: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "from_state": self.from_state.value if self.from_state else None,
            "to_state": self.to_state.value,
            "score": self.score,
            "time_in_previous_state_s": self.time_in_previous_state_s,
        }


@dataclass
class HistoryEntry:
    """One row of the state history log (every sample, not just confirmed transitions)."""

    timestamp: datetime
    instantaneous_state: EngagementState
    confirmed_state: EngagementState
    score: float

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "instantaneous_state": self.instantaneous_state.value,
            "confirmed_state": self.confirmed_state.value,
            "score": self.score,
        }


EventListener = Callable[[StateTransitionEvent], None]


class EngagementStateMachine:
    """
    Finite state machine that turns a stream of (score, is_drowsy,
    is_confused) readings into debounced, actionable engagement states.

    Usage:
        fsm = EngagementStateMachine()
        fsm.subscribe(lambda evt: print(evt.to_dict()))
        fsm.update(score=0.82, is_drowsy=False, is_confused=False, timestamp=some_datetime)
        fsm.current_state  # -> EngagementState.ENGAGED (confirmed immediately, first reading)
    """

    def __init__(
        self,
        state_config: Optional[Dict[EngagementState, StateConfig]] = None,
        initial_state: Optional[EngagementState] = None,
        max_history: int = 10_000,
        passive_min: Optional[float] = None,
        engaged_min: Optional[float] = None,
        drowsy_max_score: Optional[float] = None,
        hysteresis_seconds: Optional[Dict[EngagementState, float]] = None,
    ):
        if max_history <= 0:
            raise ValueError("max_history must be > 0")

        self.state_config = (
            dict(state_config) if state_config else dict(DEFAULT_STATE_CONFIG)
        )

        if passive_min is not None or engaged_min is not None:
            p_min = passive_min if passive_min is not None else PASSIVE_MIN_SCORE
            e_min = engaged_min if engaged_min is not None else ENGAGED_MIN_SCORE

            dist_cfg = self.state_config[EngagementState.DISTRACTED]
            self.state_config[EngagementState.DISTRACTED] = StateConfig(
                min_duration_s=dist_cfg.min_duration_s,
                min_score=DISTRACTED_MIN_SCORE,
                max_score=p_min - 0.00001,
            )

            pass_cfg = self.state_config[EngagementState.PASSIVE]
            self.state_config[EngagementState.PASSIVE] = StateConfig(
                min_duration_s=pass_cfg.min_duration_s,
                min_score=p_min,
                max_score=e_min - 0.00001,
            )

            eng_cfg = self.state_config[EngagementState.ENGAGED]
            self.state_config[EngagementState.ENGAGED] = StateConfig(
                min_duration_s=eng_cfg.min_duration_s,
                min_score=e_min,
                max_score=ENGAGED_MAX_SCORE,
            )

        if drowsy_max_score is not None:
            drowsy_cfg = self.state_config[EngagementState.DROWSY]
            self.state_config[EngagementState.DROWSY] = StateConfig(
                min_duration_s=drowsy_cfg.min_duration_s, max_score=drowsy_max_score
            )

        if hysteresis_seconds is not None:
            for state, secs in hysteresis_seconds.items():
                cfg = self.state_config[state]
                self.state_config[state] = StateConfig(
                    min_duration_s=secs,
                    min_score=cfg.min_score,
                    max_score=cfg.max_score,
                )

        self._validate_config()

        # `None` means "no reading processed yet". The FIRST call to
        # update() confirms its instantaneous state immediately (no
        # hysteresis wait). If `initial_state` is supplied explicitly, it's
        # considered already confirmed as of construction time; the
        # `_state_since` clock starts ticking on the first update() call.
        self.current_state: Optional[EngagementState] = initial_state
        self._state_since: Optional[datetime] = None

        # Hysteresis bookkeeping: the state a *pending* transition is
        # trying to reach, and when it first started being produced.
        self._candidate_state: Optional[EngagementState] = None
        self._candidate_since: Optional[datetime] = None

        self._listeners: List[EventListener] = []
        self._history: List[HistoryEntry] = []
        self._max_history = max_history

        self._last_score: Optional[float] = None
        self._last_update: Optional[datetime] = None

    # ------------------------------------------------------------------ #
    # Configuration / validation
    # ------------------------------------------------------------------ #
    def _validate_config(self) -> None:
        missing = [s for s in EngagementState if s not in self.state_config]
        if missing:
            raise ValueError(
                f"state_config is missing entries for: {[s.value for s in missing]}"
            )

        for state, cfg in self.state_config.items():
            if cfg.min_duration_s < 0:
                raise ValueError(f"{state}: min_duration_s must be >= 0")
            if state in _PARTITION_STATES:
                if cfg.min_score is None or cfg.max_score is None:
                    raise ValueError(
                        f"{state}: partition states must set min_score and max_score"
                    )
                if cfg.min_score > cfg.max_score:
                    raise ValueError(f"{state}: min_score must be <= max_score")

        # Partition states must cover [0, 100] with no gaps or overlaps.
        ordered = sorted(
            ((s, self.state_config[s]) for s in _PARTITION_STATES),
            key=lambda item: item[1].min_score,
        )
        if abs(ordered[0][1].min_score - 0) > _BOUNDARY_EPS:
            raise ValueError(
                f"partition states must start at score 0, got {ordered[0][1].min_score}"
            )
        if abs(ordered[-1][1].max_score - 1) > _BOUNDARY_EPS:
            raise ValueError(
                f"partition states must end at score 1, got {ordered[-1][1].max_score}"
            )
        for (s1, c1), (s2, c2) in zip(ordered, ordered[1:]):
            gap = c2.min_score - c1.max_score
            if gap < 0:
                raise ValueError(f"{s1} and {s2} score ranges overlap")
            if gap > _BOUNDARY_EPS:
                raise ValueError(
                    f"gap between {s1} ({c1.max_score}) and {s2} ({c2.min_score})"
                )

        # DROWSY's cutoff (if set) should be a real score bound.
        drowsy_cfg = self.state_config[EngagementState.DROWSY]
        if drowsy_cfg.max_score is not None and not (0 <= drowsy_cfg.max_score <= 1):
            raise ValueError("DROWSY max_score (cutoff) must be within [0, 1]")

    # ------------------------------------------------------------------ #
    # Event subscription (for downstream agents)
    # ------------------------------------------------------------------ #
    def subscribe(self, listener: EventListener) -> None:
        """Register a callback invoked with a StateTransitionEvent on every confirmed transition."""
        if listener in self._listeners:
            logger.warning(
                "Listener already subscribed; ignoring duplicate subscribe() call"
            )
            return
        self._listeners.append(listener)

    def unsubscribe(self, listener: EventListener) -> bool:
        """Remove a previously subscribed listener. Returns True if it was found and removed."""
        if listener in self._listeners:
            self._listeners.remove(listener)
            return True
        return False

    def _emit(self, event: StateTransitionEvent) -> None:
        for listener in list(self._listeners):
            try:
                listener(event)
            except Exception:
                logger.exception("Engagement state listener raised an exception")

    # ------------------------------------------------------------------ #
    # Core update loop
    # ------------------------------------------------------------------ #
    def _instantaneous_state(
        self, score: float, is_drowsy: bool, is_confused: bool
    ) -> EngagementState:
        # Overrides take priority over the score partition. CONFUSED
        # (expression classifier) is checked first, then DROWSY
        # (drowsiness detector, only valid at low scores).
        if is_confused:
            return EngagementState.CONFUSED

        if is_drowsy:
            drowsy_cfg = self.state_config[EngagementState.DROWSY]
            if drowsy_cfg.max_score is None or score <= drowsy_cfg.max_score:
                return EngagementState.DROWSY

        return self._score_to_partition_state(score)

    def _score_to_partition_state(self, score: float) -> EngagementState:
        for state in _PARTITION_ORDER:
            if self.state_config[state].contains(score):
                return state
        # Should be unreachable: config validation guarantees full,
        # non-overlapping coverage of [0, 100]. Defensive fallback only.
        logger.warning(
            "Score %.2f matched no partition state; defaulting to DISTRACTED", score
        )
        return EngagementState.DISTRACTED

    def update(
        self,
        score: float,
        is_drowsy: bool = False,
        is_confused: bool = False,
        timestamp: Optional[datetime] = None,
    ) -> EngagementState:
        """
        Feed a new reading into the machine.

        Returns the current *confirmed* state after processing this reading
        (which may be unchanged if hysteresis hasn't been satisfied yet).
        """
        now = timestamp or datetime.now(timezone.utc)
        if self._last_update is not None and now < self._last_update:
            raise ValueError("timestamp must be monotonically non-decreasing")
        if not math.isfinite(score):
            raise ValueError("score must be finite")
        if not (0 <= score <= 1):
            raise ValueError(f"score must be within [0, 1], got {score}")

        instantaneous_state = self._instantaneous_state(score, is_drowsy, is_confused)

        self._last_score = score
        self._last_update = now

        if self._state_since is None:
            # Bootstraps the "time in state" clock, whether current_state
            # was pre-set via the constructor or is about to be confirmed
            # below for the first time.
            self._state_since = now

        if self.current_state is None:
            # Very first reading this machine has ever seen: confirm
            # immediately, no hysteresis wait.
            self._confirm_transition(instantaneous_state, score, now)
            self._log_history(now, instantaneous_state, score)
            return self.current_state

        if instantaneous_state == self.current_state:
            # Reading matches the currently confirmed state -- any pending
            # candidate is stale, drop it.
            self._candidate_state = None
            self._candidate_since = None
        else:
            if instantaneous_state != self._candidate_state:
                # Either there was no pending candidate, or the reading
                # flickered to a *different* state than the one we were timing
                # -- restart the dwell-time clock on this new candidate.
                self._candidate_state = instantaneous_state
                self._candidate_since = now

            # Defensive guard in case it got cleared
            if self._candidate_since is None:
                self._candidate_since = now

            dwell_s = (now - self._candidate_since).total_seconds()
            required_s = self.state_config[instantaneous_state].min_duration_s

            if dwell_s >= required_s:
                self._confirm_transition(instantaneous_state, score, now)

        self._log_history(now, instantaneous_state, score)

        return self.current_state

    def _log_history(
        self, now: datetime, instantaneous_state: EngagementState, score: float
    ) -> None:
        # Use current_state if confirmed, else fall back to the instantaneous
        # reading so the very first sample still has a sensible confirmed_state.
        confirmed = (
            self.current_state
            if self.current_state is not None
            else instantaneous_state
        )
        self._history.append(HistoryEntry(now, instantaneous_state, confirmed, score))
        if len(self._history) > self._max_history:
            self._history.pop(0)

    def _confirm_transition(
        self, new_state: EngagementState, score: float, now: datetime
    ) -> None:
        time_in_previous = (
            (now - self._state_since).total_seconds() if self._state_since else None
        )

        event = StateTransitionEvent(
            timestamp=now,
            from_state=self.current_state,
            to_state=new_state,
            score=score,
            time_in_previous_state_s=time_in_previous,
        )

        logger.info(
            "Engagement transition confirmed: %s -> %s (score=%.1f)",
            event.from_state.value if event.from_state else "None",
            event.to_state.value,
            score,
        )

        self.current_state = new_state
        self._state_since = now
        self._candidate_state = None
        self._candidate_since = None

        self._emit(event)

    # ------------------------------------------------------------------ #
    # Introspection helpers
    # ------------------------------------------------------------------ #
    @property
    def history(self) -> List[dict]:
        """Full sample-level history log (timestamp, instantaneous & confirmed state, score)."""
        return [h.to_dict() for h in self._history]

    @property
    def history_entries(self) -> List[HistoryEntry]:
        """Same as `history`, but as typed HistoryEntry objects rather than dicts."""
        return list(self._history)

    @property
    def pending_candidate(self) -> Optional[Dict[str, object]]:
        """Info about an in-flight (not-yet-confirmed) transition, if any."""
        if self._candidate_state is None or self._candidate_since is None:
            return None
        dwell = (
            (self._last_update - self._candidate_since).total_seconds()
            if self._last_update
            else 0.0
        )
        required = self.state_config[self._candidate_state].min_duration_s
        return {
            "candidate_state": self._candidate_state.value,
            "dwell_s": dwell,
            "required_s": required,
        }

    def time_in_current_state(self, now: Optional[datetime] = None) -> Optional[float]:
        if self._state_since is None:
            return None
        now = now or datetime.now(timezone.utc)
        return (now - self._state_since).total_seconds()

    def reset(self, initial_state: Optional[EngagementState] = None) -> None:
        """
        Reset runtime state.

        Registered listeners remain subscribed.
        Only engagement state, history, pending transitions,
        and cached values are cleared.
        """
        self.current_state = initial_state
        self._state_since = None
        self._candidate_state = None
        self._candidate_since = None
        self._history.clear()
        self._last_score = None
        self._last_update = None
