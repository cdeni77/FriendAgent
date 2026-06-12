"""Twilio WhatsApp channel for sending proactive messages.

Incoming WhatsApp messages are handled by the FastAPI webhook in app.py; this
class handles the outbound direction (check-ins, and any out-of-band sends).
"""
from __future__ import annotations

import logging

from ..config import Config
from .base import Channel

log = logging.getLogger("friendagent.channel.whatsapp")


class TwilioWhatsAppChannel(Channel):
    def __init__(self, cfg: Config):
        if not (cfg.twilio_account_sid and cfg.twilio_auth_token and cfg.twilio_whatsapp_from):
            raise ValueError(
                "Twilio WhatsApp not configured: set TWILIO_ACCOUNT_SID, "
                "TWILIO_AUTH_TOKEN, and TWILIO_WHATSAPP_FROM."
            )
        from twilio.rest import Client

        self.cfg = cfg
        self._client = Client(cfg.twilio_account_sid, cfg.twilio_auth_token)

    def send(self, to: str, text: str) -> None:
        to_addr = to if to.startswith("whatsapp:") else f"whatsapp:{to}"
        self._client.messages.create(
            to=to_addr,
            from_=self.cfg.twilio_whatsapp_from,
            body=text,
        )
        log.info("Sent WhatsApp message to %s", to_addr)

    def send_media(self, to: str, media_path: str, caption: str = "") -> None:
        import os

        if not self.cfg.public_base_url:
            log.warning("No FRIENDAGENT_PUBLIC_BASE_URL set; sending caption only")
            if caption:
                self.send(to, caption)
            return
        to_addr = to if to.startswith("whatsapp:") else f"whatsapp:{to}"
        url = f"{self.cfg.public_base_url.rstrip('/')}/media/{os.path.basename(media_path)}"
        self._client.messages.create(
            to=to_addr,
            from_=self.cfg.twilio_whatsapp_from,
            body=caption or None,
            media_url=[url],
        )
        log.info("Sent WhatsApp media to %s (%s)", to_addr, url)
