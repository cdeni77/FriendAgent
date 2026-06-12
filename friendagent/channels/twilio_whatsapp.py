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
