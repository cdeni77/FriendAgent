"""Deliver a reply as one or more 'texts', the way a person messages.

Splits a reply into bubbles (double-texting), sends them in sequence with a
short typing pause between each. Email is always sent as a single message —
multiple emails in a row would be odd.
"""
from __future__ import annotations

import logging
import time

from . import humanize
from .channels.base import Channel
from .channels.router import EMAIL, parse_address
from .config import Config

log = logging.getLogger("friendagent.delivery")


def deliver(channel: Channel, user_id: str, text: str, cfg: Config) -> None:
    """Send `text` to `user_id` via `channel`, bubbling for chat channels."""
    kind, _ = parse_address(user_id)
    bubbles = humanize.split_bubbles(text, cfg)

    if kind == EMAIL or len(bubbles) <= 1:
        channel.send(user_id, "\n\n".join(bubbles))
        return

    for i, bubble in enumerate(bubbles):
        if i > 0:
            time.sleep(humanize.inter_bubble_delay(bubble, cfg))
        channel.send(user_id, bubble)
    log.info("Delivered %d bubbles to %s", len(bubbles), user_id)
