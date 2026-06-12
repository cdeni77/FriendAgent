"""Transcribe inbound voice notes (e.g. WhatsApp audio she sends).

Downloads the media from Twilio (authenticated) and transcribes it with
OpenAI's Whisper API. Lazy imports; returns "" on any failure so the caller
can degrade gracefully.
"""
from __future__ import annotations

import logging
import os
import time

from ..config import Config

log = logging.getLogger("friendagent.media.transcribe")


def transcribe_twilio_media(media_url: str, content_type: str, cfg: Config) -> str:
    if not cfg.openai_api_key:
        log.warning("Inbound voice note but OPENAI_API_KEY unset; cannot transcribe")
        return ""
    try:
        import requests  # lazy

        auth = None
        if cfg.twilio_account_sid and cfg.twilio_auth_token:
            auth = (cfg.twilio_account_sid, cfg.twilio_auth_token)
        resp = requests.get(media_url, auth=auth, timeout=60)
        resp.raise_for_status()

        ext = "ogg" if "ogg" in (content_type or "") else "mp3"
        os.makedirs(cfg.media_dir, exist_ok=True)
        path = os.path.join(cfg.media_dir, f"inbound_{int(time.time() * 1000)}.{ext}")
        with open(path, "wb") as fh:
            fh.write(resp.content)

        from openai import OpenAI  # lazy

        client = OpenAI(api_key=cfg.openai_api_key)
        with open(path, "rb") as fh:
            result = client.audio.transcriptions.create(model="whisper-1", file=fh)
        text = (result.text or "").strip()
        log.info("Transcribed inbound voice note (%d chars)", len(text))
        return text
    except Exception as exc:
        log.error("Voice-note transcription failed: %s", exc)
        return ""


def compose_inbound_text(body: str, transcript: str) -> str:
    """Combine a typed body and/or a voice-note transcript into the user text."""
    body = (body or "").strip()
    transcript = (transcript or "").strip()
    if transcript and body:
        return f"{body}\n(voice note): {transcript}"
    if transcript:
        return f"(she sent a voice note): {transcript}"
    return body
