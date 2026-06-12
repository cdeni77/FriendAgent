"""Channel interface: anything that can deliver a message to her."""
from __future__ import annotations

from abc import ABC, abstractmethod


class Channel(ABC):
    @abstractmethod
    def send(self, to: str, text: str) -> None:
        """Deliver a message to the recipient address `to`."""
        raise NotImplementedError

    def send_media(self, to: str, media_path: str, caption: str = "") -> None:
        """Deliver a media file (voice/photo). Default: send the caption as text.

        Channels that support media (WhatsApp, SMS/MMS) override this.
        """
        if caption:
            self.send(to, caption)
