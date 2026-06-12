"""Local terminal chat — the easiest way to test the agent end to end.

    python -m friendagent.cli

Talk to the companion in your terminal. Try a scammy line like
"the general asked me to send gift cards" to watch the safety alert fire.
"""
from __future__ import annotations

import logging
import sys

from . import delivery
from .companion import Companion
from .channels.console import ConsoleChannel

LOCAL_USER = "console-user"


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    companion = Companion()
    channel = ConsoleChannel(companion.persona.name)

    print(
        f"Chatting with {companion.persona.name} "
        f"(relationship: {companion.persona.relationship}). "
        "Type 'exit' to quit, '/checkin' for a proactive message.\n"
    )
    # Open with a proactive hello.
    delivery.deliver(channel, LOCAL_USER, companion.proactive_checkin(LOCAL_USER, "morning"), companion.cfg)

    try:
        while True:
            try:
                text = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not text:
                continue
            if text.lower() in {"exit", "quit"}:
                break
            if text == "/checkin":
                delivery.deliver(channel, LOCAL_USER, companion.proactive_checkin(LOCAL_USER), companion.cfg)
                continue
            reply = companion.handle_message(LOCAL_USER, text)
            delivery.deliver(channel, LOCAL_USER, reply, companion.cfg)
    finally:
        companion.close()
        print("\nGoodbye.")


if __name__ == "__main__":
    sys.exit(main())
