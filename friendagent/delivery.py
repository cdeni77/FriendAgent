"""Deliver outbound messages the way a person messages.

Text is split into bubbles (double-texting) with typing pauses; voice and photo
messages are sent as media. Accepts either a plain string (treated as one text
message) or a list of OutboundMessage from the agent.
"""
from __future__ import annotations

import logging
import time
from typing import Union

from . import humanize
from .channels.base import Channel
from .channels.router import EMAIL, parse_address
from .config import Config
from .outbound import PHOTO, TEXT, VOICE, OutboundMessage

log = logging.getLogger("friendagent.delivery")


def deliver(
    channel: Channel,
    user_id: str,
    messages: Union[str, list[OutboundMessage]],
    cfg: Config,
) -> None:
    if isinstance(messages, str):
        messages = [OutboundMessage.text_msg(messages)]

    for i, msg in enumerate(messages):
        if i > 0:
            time.sleep(humanize.inter_bubble_delay(msg.text or "", cfg))
        if msg.kind == TEXT:
            _deliver_text(channel, user_id, msg.text, cfg)
        elif msg.kind in (VOICE, PHOTO):
            if msg.media_path:
                channel.send_media(user_id, msg.media_path, caption=msg.text)
            elif msg.text:
                _deliver_text(channel, user_id, msg.text, cfg)


def _deliver_text(channel: Channel, user_id: str, text: str, cfg: Config) -> None:
    kind, _ = parse_address(user_id)
    bubbles = humanize.split_bubbles(text, cfg)
    if kind == EMAIL or len(bubbles) <= 1:
        channel.send(user_id, "\n\n".join(bubbles))
        return
    for j, bubble in enumerate(bubbles):
        if j > 0:
            time.sleep(humanize.inter_bubble_delay(bubble, cfg))
        channel.send(user_id, bubble)
    log.info("Delivered %d text bubbles to %s", len(bubbles), user_id)
