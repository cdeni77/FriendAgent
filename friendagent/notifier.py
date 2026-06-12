"""Alert the family member when the safety layer flags something.

Channels (used if configured): console log (always), email via SMTP, SMS via
Twilio. Failures in one channel never block the others.
"""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from typing import Optional

from .config import Config
from .safety import SafetyResult

log = logging.getLogger("friendagent.notifier")


class Notifier:
    def __init__(self, cfg: Config):
        self.cfg = cfg

    def alert(self, user_id: str, message_text: str, result: SafetyResult) -> None:
        subject = f"[FriendAgent] Possible scam contact — severity {result.severity.name}"
        body = (
            "FriendAgent flagged a message your relative sent or received as a "
            "possible scam.\n\n"
            f"From/conversation: {user_id}\n"
            f"Severity: {result.severity.name}\n"
            f"Categories: {', '.join(result.categories) or 'n/a'}\n"
            f"Why: {result.rationale}\n\n"
            f"Message:\n{message_text}\n\n"
            "Suggested next step: call her, talk it through gently, and make sure "
            "no money, gift cards, or account details are sent to anyone."
        )
        log.warning("SAFETY ALERT (%s): %s", result.severity.name, body)
        self._email(subject, body)
        self._sms(body)

    # ---- email ----------------------------------------------------------
    def _email(self, subject: str, body: str) -> None:
        cfg = self.cfg
        if not (cfg.alert_email and cfg.smtp_host and cfg.smtp_from):
            return
        try:
            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = cfg.smtp_from
            msg["To"] = cfg.alert_email
            msg.set_content(body)
            with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=15) as smtp:
                smtp.starttls()
                if cfg.smtp_user and cfg.smtp_password:
                    smtp.login(cfg.smtp_user, cfg.smtp_password)
                smtp.send_message(msg)
            log.info("Alert email sent to %s", cfg.alert_email)
        except Exception as exc:  # never let alerting crash the agent
            log.error("Failed to send alert email: %s", exc)

    # ---- sms ------------------------------------------------------------
    def _sms(self, body: str) -> None:
        cfg = self.cfg
        if not (cfg.alert_sms_to and cfg.twilio_account_sid and cfg.twilio_sms_from):
            return
        try:
            from twilio.rest import Client

            client = Client(cfg.twilio_account_sid, cfg.twilio_auth_token)
            client.messages.create(
                to=cfg.alert_sms_to,
                from_=cfg.twilio_sms_from,
                body=body[:1500],
            )
            log.info("Alert SMS sent to %s", cfg.alert_sms_to)
        except Exception as exc:
            log.error("Failed to send alert SMS: %s", exc)
