"""Temporal smoothing and anomaly filtering for engagement scores."""

from collections import deque
from typing import Deque, Optional


class TemporalFilter:
    """Slide window temporal filter for engagement scores.

    Parameters
    ----------
    window_size : int
        Number of frames used for the moving average. Default 30 (~2s @15FPS).
        Must be >= 1.
    max_step : float
        Maximum allowed per-call change downward from the previous smoothed
        value. Prevents a single-frame anomaly from collapsing the score.
        Set to 0 to disable clamping.
    """

    def __init__(self, window_size: int = 30, max_step: float = 0.50):
        if window_size < 1:
            raise ValueError("window_size must be >= 1")
        if max_step < 0:
            raise ValueError("max_step must be >= 0")

        self.window_size: int = window_size
        self.max_step: float = float(max_step)
        self._buffer: Deque[float] = deque(maxlen=window_size)
        self._last_smoothed: Optional[float] = None

    def smooth(self, score: float) -> float:
        """Append `score` and return the filtered (smoothed) output.

        Behavior details:
        - Before the buffer fills, returns the raw score.
        - After buffer fills, returns moving average, but a sudden downward
          jump larger than `max_step` from the previous smoothed value is
          clamped so that the new smoothed >= previous - max_step.
        - The clamp only limits downward jumps; upward changes are reflected
          immediately according to the average.
        """
        # Append new sample to rolling buffer
        self._buffer.append(float(score))

        # Before the window is full: return raw score but do NOT set _last_smoothed.
        if len(self._buffer) < self.window_size:
            return float(score)

        # Compute moving average over full window
        average = sum(self._buffer) / len(self._buffer)

        # If this is the first time the buffer is full, accept the average as the first smoothed value
        if self._last_smoothed is None:
            smoothed = average
        else:
            if self.max_step == 0.0:
                smoothed = average
            else:
                min_allowed = self._last_smoothed - self.max_step
                smoothed = max(average, min_allowed)

        self._last_smoothed = smoothed
        return smoothed

    def reset(self) -> None:
        """Clear internal buffer and last-smoothed state (useful for tests)."""
        self._buffer.clear()
        self._last_smoothed = None

    def __repr__(self) -> str:
        return (
            f"TemporalFilter(window_size={self.window_size}, "
            f"max_step={self.max_step}, buffer_len={len(self._buffer)})"
        )
