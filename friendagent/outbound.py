"""What the companion wants to send back — text, a voice note, or a photo.

The agent loop produces a list of these; the delivery layer renders each one
over the right channel (with bubbling for text, media URLs for voice/photos).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Optional

TEXT = "text"
VOICE = "voice"
PHOTO = "photo"


@dataclass
class OutboundMessage:
    kind: str                      # TEXT | VOICE | PHOTO
    text: str = ""                 # text body, voice transcript, or photo caption
    media_path: Optional[str] = None  # local file for voice/photo

    @classmethod
    def text_msg(cls, text: str) -> "OutboundMessage":
        return cls(kind=TEXT, text=text)

    @classmethod
    def voice_msg(cls, transcript: str, path: str) -> "OutboundMessage":
        return cls(kind=VOICE, text=transcript, media_path=path)

    @classmethod
    def photo_msg(cls, caption: str, path: str) -> "OutboundMessage":
        return cls(kind=PHOTO, text=caption, media_path=path)


def serialize(messages: list[OutboundMessage]) -> str:
    return json.dumps([asdict(m) for m in messages])


def deserialize(payload: str) -> list[OutboundMessage]:
    return [OutboundMessage(**d) for d in json.loads(payload)]
