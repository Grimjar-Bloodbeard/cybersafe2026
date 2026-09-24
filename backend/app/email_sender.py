"""The project's one outbound email identity - a Gmail account + App
Password (never a real Gmail login password - see .env.example), shared by
the weekly registration digest and the team dashboard's passkey enrollment
links. One sender, one place that knows how to talk to SMTP, rather than
duplicating this in every script that needs to send a real email.
"""
from __future__ import annotations

import os
import smtplib
from email.mime.text import MIMEText

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465

SENDER_EMAIL = os.environ.get("DIGEST_SENDER_EMAIL", "")
SENDER_APP_PASSWORD = os.environ.get("DIGEST_SENDER_APP_PASSWORD", "")


def send_email(to: str | list[str], subject: str, body: str) -> bool:
    """Returns False (and prints why) instead of raising when credentials
    aren't configured - matches scripts/weekly_registration_digest.py's
    existing "print instead of silently failing" behavior, so a missing
    .env value is obvious immediately rather than a swallowed exception.
    """
    if not (SENDER_EMAIL and SENDER_APP_PASSWORD):
        print(
            "Email not sent: DIGEST_SENDER_EMAIL / DIGEST_SENDER_APP_PASSWORD "
            "aren't both set in .env yet."
        )
        return False

    recipients = [to] if isinstance(to, str) else to
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = SENDER_EMAIL
    msg["To"] = ", ".join(recipients)

    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
        server.login(SENDER_EMAIL, SENDER_APP_PASSWORD)
        server.sendmail(SENDER_EMAIL, recipients, msg.as_string())
    return True
