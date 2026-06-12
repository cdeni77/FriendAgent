"""One-time: design a custom ElevenLabs voice from a text description.

    python scripts/design_voice.py "warm man in his early 70s, gentle, unhurried, slight Southern lilt"

Prints candidate voice previews, saves your chosen one, and gives you the
voice_id to drop into .env as FRIENDAGENT_VOICE_ID. Needs ELEVENLABS_API_KEY.
"""
from __future__ import annotations

import base64
import os
import sys

import requests

API = "https://api.elevenlabs.io/v1"


def main() -> int:
    key = os.getenv("ELEVENLABS_API_KEY")
    if not key:
        print("Set ELEVENLABS_API_KEY first.")
        return 1
    if len(sys.argv) < 2:
        print('Usage: python scripts/design_voice.py "<voice description>"')
        return 1
    description = sys.argv[1]
    headers = {"xi-api-key": key, "content-type": "application/json"}

    # 1. Design — returns several previews, each with a generated_voice_id.
    sample_text = (
        "Good morning, my dear. I was just thinking about you and hoping you "
        "slept well. The garden looks lovely today."
    )
    resp = requests.post(
        f"{API}/text-to-voice/design",
        headers=headers,
        json={"voice_description": description, "text": sample_text},
        timeout=60,
    )
    resp.raise_for_status()
    previews = resp.json().get("previews", [])
    if not previews:
        print("No previews returned.")
        return 1

    os.makedirs("media_out", exist_ok=True)
    for i, p in enumerate(previews):
        audio = p.get("audio_base_64") or p.get("audio_base64") or ""
        if audio:
            path = f"media_out/voice_preview_{i}.mp3"
            with open(path, "wb") as fh:
                fh.write(base64.b64decode(audio))
            print(f"[{i}] generated_voice_id={p['generated_voice_id']}  sample -> {path}")
        else:
            print(f"[{i}] generated_voice_id={p['generated_voice_id']}")

    choice = input("\nListen to the samples, then enter the number to save: ").strip()
    try:
        chosen = previews[int(choice)]
    except (ValueError, IndexError):
        print("No valid choice; nothing saved.")
        return 1

    # 2. Create — persist the chosen preview as a permanent voice.
    name = input("Name this voice (e.g. 'Sam'): ").strip() or "FriendAgent Voice"
    create = requests.post(
        f"{API}/text-to-voice",
        headers=headers,
        json={
            "voice_name": name,
            "voice_description": description,
            "generated_voice_id": chosen["generated_voice_id"],
        },
        timeout=60,
    )
    create.raise_for_status()
    voice_id = create.json().get("voice_id")
    print(f"\nSaved! Add this to your .env:\n  FRIENDAGENT_VOICE_ID={voice_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
