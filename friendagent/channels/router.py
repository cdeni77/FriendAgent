"""Channel router — one place that knows how to reach a contact.

A contact address carries its channel as a prefix so memory keys and routing
stay consistent across the whole app:

    whatsapp:+14155550123     -> WhatsApp (Twilio)
    sms:+14155550123          -> SMS (Twilio)
    email:grandma@example.com -> Email (SMTP)

Bare values are inferred: anything with "@" is email, a leading "+" / digits is
SMS. The router builds each underlying channel lazily, so you only need creds
for the channels you actually use.
"""
from __future__ import annotations

import logging
import re

from ..config import Config
from .base import Channel
from .email import EmailChannel
from .sms import TwilioSMSChannel
from .twilio_whatsapp import TwilioWhatsAppChannel

log = logging.getLogger("friendagent.channel.router")

WHATSAPP = "whatsapp"
SMS = "sms"
EMAIL = "email"

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def parse_address(address: str) -> tuple[str, str]:
    """Return (channel, raw_destination) for a contact address."""
    addr = address.strip()
    for prefix, channel in (("whatsapp:", WHATSAPP), ("sms:", SMS), ("email:", EMAIL)):
        if addr.lower().startswith(prefix):
            dest = addr[len(prefix):]
            # WhatsApp's Twilio API wants the "whatsapp:" prefix on the number.
            return channel, (f"whatsapp:{dest}" if channel == WHATSAPP else dest)
    # Infer from shape.
    if _EMAIL_RE.match(addr):
        return EMAIL, addr
    if addr.startswith("whatsapp:"):
        return WHATSAPP, addr
    return SMS, addr  # default: treat as a phone number for SMS


class ChannelRouter(Channel):
    def __init__(self, cfg: Config, persona_name: str = "Your friend"):
        self.cfg = cfg
        self.persona_name = persona_name
        self._cache: dict[str, Channel] = {}

    def _channel(self, channel: str) -> Channel:
        if channel not in self._cache:
            if channel == WHATSAPP:
                self._cache[channel] = TwilioWhatsAppChannel(self.cfg)
            elif channel == SMS:
                self._cache[channel] = TwilioSMSChannel(self.cfg)
            elif channel == EMAIL:
                self._cache[channel] = EmailChannel(self.cfg, self.persona_name)
            else:
                raise ValueError(f"Unknown channel: {channel}")
        return self._cache[channel]

    def send(self, to: str, text: str) -> None:
        channel, dest = parse_address(to)
        self._channel(channel).send(dest, text)
        log.info("Routed message to %s via %s", dest, channel)

    def send_media(self, to: str, media_path: str, caption: str = "") -> None:
        channel, dest = parse_address(to)
        self._channel(channel).send_media(dest, media_path, caption)
        log.info("Routed media to %s via %s", dest, channel)
