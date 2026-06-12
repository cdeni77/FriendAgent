"""Photos of the persona, generated from a fixed reference image.

To keep it the *same person* every time, we condition on a locked reference
portrait (reference_image_path) plus a fixed appearance description, and only
vary the scene/pose. Default backend is OpenAI image edits (gpt-image-1).
"""
from __future__ import annotations

import base64
import logging
import os
import time

from ..config import Config

log = logging.getLogger("friendagent.media.images")


def _prompt(scene: str, cfg: Config) -> str:
    appearance = cfg.persona_appearance or "the same person as in the reference image"
    return (
        f"A natural, candid photo of {appearance}. Keep the face and identity "
        f"identical to the reference image. Scene: {scene}. Warm, realistic "
        f"lighting; looks like a real personal photo."
    )


def generate(scene: str, cfg: Config) -> str:
    """Generate a photo of the persona in `scene`; return its local path."""
    if cfg.image_provider != "openai":
        raise ValueError(f"Unsupported image provider: {cfg.image_provider}")
    if not cfg.openai_api_key:
        raise ValueError("OPENAI_API_KEY is not set.")
    if not cfg.reference_image_path or not os.path.exists(cfg.reference_image_path):
        raise ValueError(
            "FRIENDAGENT_REFERENCE_IMAGE_PATH must point at the locked reference "
            "portrait so every photo is the same person."
        )

    from openai import OpenAI  # lazy

    client = OpenAI(api_key=cfg.openai_api_key)
    os.makedirs(cfg.media_dir, exist_ok=True)

    with open(cfg.reference_image_path, "rb") as ref:
        result = client.images.edit(
            model=cfg.image_model,
            image=ref,
            prompt=_prompt(scene, cfg),
            size=cfg.image_size,
        )

    b64 = result.data[0].b64_json
    path = os.path.join(cfg.media_dir, f"photo_{int(time.time() * 1000)}.png")
    with open(path, "wb") as fh:
        fh.write(base64.b64decode(b64))
    log.info("Generated photo -> %s", path)
    return path
