from src.reports.rate_limiter import EmailRateLimiter


def test_rate_limiter_allows_until_limit():
    limiter = EmailRateLimiter(
        max_emails=3,
        window_seconds=60,
    )

    assert limiter.allow() is True
    assert limiter.allow() is True
    assert limiter.allow() is True


def test_rate_limiter_blocks_after_limit():
    limiter = EmailRateLimiter(
        max_emails=2,
        window_seconds=60,
    )

    assert limiter.allow() is True
    assert limiter.allow() is True
    assert limiter.allow() is False
