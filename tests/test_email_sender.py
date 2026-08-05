from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.reports.email_sender import EmailSender


@patch("src.reports.email_sender.rate_limiter")
@patch("src.reports.email_sender.settings")
def test_send_email_without_sendgrid(mock_settings, mock_rate_limiter, tmp_path):
    mock_rate_limiter.allow.return_value = True
    mock_settings.sendgrid_api_key = ""

    sender = EmailSender()

    html = "<h1>Report</h1>"

    filename = tmp_path / "report.html"

    result = sender._send_email(
        to="teacher@example.com",
        subject="Test",
        html=html,
        fallback_filename=str(filename),
    )

    assert Path(result).exists()
    assert filename.read_text() == html

    sender.close()


@patch("src.reports.email_sender.rate_limiter")
def test_rate_limit_exceeded(mock_rate_limiter):
    mock_rate_limiter.allow.return_value = False

    sender = EmailSender()

    with pytest.raises(RuntimeError):
        sender._send_email(
            to="teacher@example.com",
            subject="Test",
            html="<h1>Report</h1>",
            fallback_filename="report.html",
        )

    sender.close()


@patch("src.reports.email_sender.SendGridAPIClient")
@patch("src.reports.email_sender.rate_limiter")
@patch("src.reports.email_sender.settings")
def test_send_email_with_sendgrid(
    mock_settings,
    mock_rate_limiter,
    mock_client,
):
    mock_rate_limiter.allow.return_value = True

    mock_settings.sendgrid_api_key = "dummy-key"
    mock_settings.email_from = "noreply@example.com"

    response = MagicMock()
    response.status_code = 202

    mock_client.return_value.send.return_value = response

    sender = EmailSender()

    result = sender._send_email(
        to="teacher@example.com",
        subject="Test",
        html="<h1>Report</h1>",
        fallback_filename="report.html",
    )

    assert result == "sent"

    mock_client.return_value.send.assert_called_once()

    sender.close()


def test_render_template():
    sender = EmailSender()

    html = """
    <html>
        <body>
            <h1>Hello</h1>
        </body>
    </html>
    """

    rendered = sender._render_template(
        "email_session.html",
        html,
    )

    assert "Session Engagement Report" in rendered
    assert "<h1>Hello</h1>" in rendered

    sender.close()