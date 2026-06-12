"""Email channel — talk to her over email via SMTP (outbound).

Inbound email is delivered to the FastAPI webhook in app.py (compatible with
SendGrid Inbound Parse / Mailgun routes). This class only sends.
"""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from ..config import Config
from .base import Channel

log = logging.getLogger("friendagent.channel.email")


class EmailChannel(Channel):
    def __init__(self, cfg: Config, persona_name: str = "Your friend"):
        if not (cfg.smtp_host and cfg.smtp_from):
            raise ValueError(
                "Email channel not configured: set SMTP_HOST and SMTP_FROM "
                "(and SMTP_USER/SMTP_PASSWORD if your server requires auth)."
            )
        self.cfg = cfg
        self.persona_name = persona_name

    def send(self, to: str, text: str, subject: str | None = None) -> None:
        cfg = self.cfg
        msg = EmailMessage()
        msg["Subject"] = subject or f"A note from {self.persona_name}"
        msg["From"] = cfg.smtp_from
        msg["To"] = to
        msg.set_content(text)
        with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=20) as smtp:
            smtp.starttls()
            if cfg.smtp_user and cfg.smtp_password:
                smtp.login(cfg.smtp_user, cfg.smtp_password)
            smtp.send_message(msg)
        log.info("Sent email to %s", to)
