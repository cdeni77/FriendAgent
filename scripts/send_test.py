"""End-to-end smoke test of the media path.

    python scripts/send_test.py whatsapp:+1YOURNUMBER

Generates a real voice note (ElevenLabs) and an optional photo, then sends them
to the given address over the right channel — so you can confirm voice/photos
actually arrive. Needs the relevant keys set in .env, plus a reachable
FRIENDAGENT_PUBLIC_BASE_URL (for Twilio to fetch the media) and the web server
running to serve /media.

For WhatsApp/SMS this requires the media file to be reachable at
PUBLIC_BASE_URL/media/<file>; run `uvicorn app:app` alongside this.
"""
from __future__ import annotations

import sys

from friendagent.config import load_config
from friendagent.channels.router import ChannelRouter
from friendagent.media import MediaStudio


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python scripts/send_test.py <whatsapp:+1...|sms:+1...|email:...>")
        return 1
    to = sys.argv[1]
    cfg = load_config()
    studio = MediaStudio(cfg)
    router = ChannelRouter(cfg, "Test")

    print(f"Sending a test text to {to} ...")
    router.send(to, "Hi love, just testing that I can reach you. ❤️")

    if studio.voice_available:
        print("Generating + sending a voice note ...")
        path = studio.voice_note("Good morning, my dear. I was thinking of you.")
        router.send_media(to, path, caption="a little hello")
    else:
        print("Voice not configured (set FRIENDAGENT_VOICE_ENABLED, ELEVENLABS_API_KEY, FRIENDAGENT_VOICE_ID) — skipping.")

    if studio.photos_available:
        print("Generating + sending a photo ...")
        path = studio.photo("smiling in a sunny garden with a cup of coffee")
        router.send_media(to, path, caption="from the garden today")
    else:
        print("Photos not configured (set FRIENDAGENT_PHOTOS_ENABLED, OPENAI_API_KEY, FRIENDAGENT_REFERENCE_IMAGE_PATH) — skipping.")

    print("Done. Check the recipient device.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
