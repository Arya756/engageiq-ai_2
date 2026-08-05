"""Simple in-memory email rate limiter."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta


class EmailRateLimiter:
    """Limit email delivery to 10 emails per minute."""

    def __init__(self, max_emails: int = 10, window_seconds: int = 60):
        self.max_emails = max_emails
        self.window = timedelta(seconds=window_seconds)
        self.timestamps: deque[datetime] = deque()

    def allow(self) -> bool:
        """Return True if another email may be sent."""

        now = datetime.now()

        while self.timestamps and now - self.timestamps[0] > self.window:
            self.timestamps.popleft()

        if len(self.timestamps) >= self.max_emails:
            return False

        self.timestamps.append(now)
        return True


rate_limiter = EmailRateLimiter()
