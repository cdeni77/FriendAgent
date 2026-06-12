"""Twilio SMS channel — talk to her over plain text messages."""
from __future__ import annotations

import logging

from ..config import Config
from .base import Channel

log = logging.getLogger("friendagent.channel.sms")


class TwilioSMSChannel(Channel):
    def __init__(self, cfg: Config):
        if not (cfg.twilio_account_sid and cfg.twilio_auth_token and cfg.twilio_sms_from):
            raise ValueError(
                "Twilio SMS not configured: set TWILIO_ACCOUNT_SID, "
                "TWILIO_AUTH_TOKEN, and TWILIO_SMS_FROM."
            )
        from twilio.rest import Client

        self.cfg = cfg
        self._client = Client(cfg.twilio_account_sid, cfg.twilio_auth_token)

    def send(self, to: str, text: str) -> None:
        # SMS segments long; Twilio splits automatically, but keep it sane.
        self._client.messages.create(
            to=to,
            from_=self.cfg.twilio_sms_from,
            body=text,
        )
        log.info("Sent SMS to %s", to)

    def send_media(self, to: str, media_path: str, caption: str = "") -> None:
        import os

        if not self.cfg.public_base_url:
            log.warning("No FRIENDAGENT_PUBLIC_BASE_URL set; sending caption only")
            if caption:
                self.send(to, caption)
            return
        url = f"{self.cfg.public_base_url.rstrip('/')}/media/{os.path.basename(media_path)}"
        # MMS — media is delivered as a picture/audio message.
        self._client.messages.create(
            to=to,
            from_=self.cfg.twilio_sms_from,
            body=caption or None,
            media_url=[url],
        )
        log.info("Sent MMS to %s (%s)", to, url)
