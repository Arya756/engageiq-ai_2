"""Email delivery for session and weekly reports."""

from __future__ import annotations

import argparse
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

from src.config.database import SessionLocal
from src.config.settings import settings
from src.models.course import Course
from src.models.session import Session as SessionModel
from src.reports.rate_limiter import rate_limiter
from src.reports.session_report import SessionReportGenerator
from src.reports.weekly_report import WeeklyReportGenerator

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"

env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(["html"]),
)


class EmailSender:
    """Send reports through email or save them locally."""

    def __init__(self):
        self.db = SessionLocal()

    def session_email(self, to: str, session_id: int) -> str:
        session = self.db.get(SessionModel, session_id)
        if session is None:
            raise ValueError(f"Session {session_id} not found")

        course = self.db.get(Course, session.course_id)

        if course and course.teacher and not course.teacher.notification_enabled:

            print("Teacher has disabled email notifications.")
            return "skipped"
        generator = SessionReportGenerator(self.db)
        report_html = generator.generate_and_render(session_id)

        html = self._render_template(
            "email_session.html",
            report_html,
        )

        return self._send_email(
            to=to,
            subject=f"Session Report #{session_id}",
            html=html,
            fallback_filename=f"session_report_{session_id}.html",
        )


    def weekly_email(self, to: str, course_id: int, week: str) -> str:
        course = self.db.get(Course, course_id)
        if course and course.teacher and not course.teacher.notification_enabled:

            print("Teacher has disabled email notifications.")
            return "skipped"
        generator = WeeklyReportGenerator(self.db)
        report_html = generator.generate_and_render(course_id, week)

        html = self._render_template(
            "email_weekly.html",
            report_html,
        )

        return self._send_email(
            to=to,
            subject=f"Weekly Report {week}",
            html=html,
            fallback_filename=f"weekly_report_{course_id}_{week}.html",
        )

    def close(self):
        self.db.close()

    def _save_html(self, html: str, filename: str) -> str:
        output = Path(filename)
        output.write_text(html, encoding="utf-8")
        print(f"Saved HTML to {output.resolve()}")
        return str(output)

    def _send_email(
        self,
        to: str,
        subject: str,
        html: str,
        fallback_filename: str,
    ) -> str:
        """Send report through SendGrid or save HTML."""

        if not rate_limiter.allow():
            raise RuntimeError("Email rate limit exceeded.")

        if not settings.sendgrid_api_key:
            print("No SendGrid key configured.")
            return self._save_html(html, fallback_filename)

        message = Mail(
            from_email=settings.email_from,
            to_emails=to,
            subject=subject,
            html_content=html,
        )

        try:
            client = SendGridAPIClient(settings.sendgrid_api_key)
            response = client.send(message)

            print(f"Email sent successfully ({response.status_code})")
            return "sent"

        except Exception as exc:
            print(f"Email sending failed: {exc}")
            return self._save_html(html, fallback_filename)

    def _render_template(
        self,
        template_name: str,
        report_html: str,
    ) -> str:
        """Render email template."""

        lower = report_html.lower()

        if "<body" in lower:
            start = lower.find("<body")
            start = report_html.find(">", start) + 1

            end = lower.rfind("</body>")

            if end != -1:
                report_html = report_html[start:end]

        template = env.get_template(template_name)

        return template.render(
            report_html=report_html,
        )


def main():
    parser = argparse.ArgumentParser(description="Send engagement reports")

    parser.add_argument("--to", required=True)
    parser.add_argument("--report", choices=["session", "weekly"], required=True)

    parser.add_argument("--session-id", type=int)
    parser.add_argument("--course-id", type=int)
    parser.add_argument("--week")

    args = parser.parse_args()

    sender = EmailSender()

    try:
        if args.report == "session":
            sender.session_email(args.to, args.session_id)

        else:
            sender.weekly_email(
                args.to,
                args.course_id,
                args.week,
            )
    finally:
        sender.close()


if __name__ == "__main__":
    main()
