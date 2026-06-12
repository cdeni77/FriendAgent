"""Channel interface: anything that can deliver a message to her."""
from __future__ import annotations

from abc import ABC, abstractmethod


class Channel(ABC):
    @abstractmethod
    def send(self, to: str, text: str) -> None:
        """Deliver a message to the recipient address `to`."""
        raise NotImplementedError
