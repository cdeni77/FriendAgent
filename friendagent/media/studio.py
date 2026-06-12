"""MediaStudio — one entry point for generating voice notes and photos.

Injected into the agent so it can be swapped for a fake in tests.
"""
from __future__ import annotations

from ..config import Config
from . import images, voice


class MediaStudio:
    def __init__(self, cfg: Config):
        self.cfg = cfg

    @property
    def voice_available(self) -> bool:
        return bool(self.cfg.voice_enabled and self.cfg.elevenlabs_api_key and self.cfg.voice_id)

    @property
    def photos_available(self) -> bool:
        return bool(
            self.cfg.photos_enabled
            and self.cfg.openai_api_key
            and self.cfg.reference_image_path
        )

    def voice_note(self, text: str) -> str:
        return voice.synthesize(text, self.cfg)

    def photo(self, scene: str) -> str:
        return images.generate(scene, self.cfg)
