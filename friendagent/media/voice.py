"""Voice notes via ElevenLabs.

One fixed voice_id is used for every note, so the companion always sounds like
the same person. We call the REST API directly with `requests` (lazy import) to
avoid a hard dependency when voice is disabled.
"""
from __future__ import annotations

import logging
import os
import time

from ..config import Config

log = logging.getLogger("friendagent.media.voice")

_API = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"


def synthesize(text: str, cfg: Config) -> str:
    """Generate an mp3 for `text` and return its local file path."""
    if not cfg.elevenlabs_api_key:
        raise ValueError("ELEVENLABS_API_KEY is not set.")
    if not cfg.voice_id:
        raise ValueError("FRIENDAGENT_VOICE_ID is not set (pick one fixed voice).")

    import requests  # lazy

    os.makedirs(cfg.media_dir, exist_ok=True)
    url = _API.format(voice_id=cfg.voice_id)
    payload = {
        "text": text,
        "model_id": cfg.voice_model,
        # Tuned for a warm, steady, affectionate delivery.
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.8, "style": 0.3},
    }
    headers = {
        "xi-api-key": cfg.elevenlabs_api_key,
        "accept": "audio/mpeg",
        "content-type": "application/json",
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=60)
    resp.raise_for_status()

    path = os.path.join(cfg.media_dir, f"voice_{int(time.time() * 1000)}.mp3")
    with open(path, "wb") as fh:
        fh.write(resp.content)
    log.info("Synthesized voice note -> %s", path)
    return path
