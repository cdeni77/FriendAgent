"""Console channel — prints messages. Used by the local CLI and tests."""
from __future__ import annotations

from .base import Channel


class ConsoleChannel(Channel):
    def __init__(self, persona_name: str = "Companion"):
        self.persona_name = persona_name

    def send(self, to: str, text: str) -> None:
        print(f"\n{self.persona_name}: {text}\n")
