"""Thin wrapper around the Anthropic SDK for the companion.

Keeps all Claude-specific details in one place: model id, message shaping,
structured-output classification for the safety layer, and fact extraction.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from .memory import Message

log = logging.getLogger("friendagent.llm")


class LLM:
    def __init__(self, model: str, api_key: Optional[str] = None):
        self.model = model
        import anthropic  # lazy: package imports fine without the SDK installed

        # The SDK reads ANTHROPIC_API_KEY from the env if api_key is None.
        self.client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    # ---- conversational reply ------------------------------------------
    def reply(
        self,
        system_prompt: str,
        history: list[Message],
        max_tokens: int = 600,
    ) -> str:
        """Generate the companion's next message given the conversation so far."""
        messages = [{"role": m.role, "content": m.content} for m in history]
        if not messages or messages[0]["role"] != "user":
            # The API requires the first message to be from the user.
            messages.insert(0, {"role": "user", "content": "(she just opened the chat)"})
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=messages,
        )
        return _first_text(resp).strip()

    def generate(self, system_prompt: str, user: str, max_tokens: int = 400) -> str:
        """One-shot generation (used for proactive check-ins)."""
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user}],
        )
        return _first_text(resp).strip()

    # ---- structured classification (safety layer) ----------------------
    def classify(self, system: str, user: str, schema: dict) -> Optional[dict[str, Any]]:
        """Return a JSON object constrained to `schema`, or None on failure."""
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=400,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"format": {"type": "json_schema", "schema": schema}},
        )
        text = _first_text(resp)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            log.warning("classify(): could not parse JSON: %r", text[:200])
            return None

    # ---- web lookup (for sharing articles/recipes/clips) ---------------
    def web_lookup(self, topic: str) -> str:
        """Find one genuinely nice, real link about `topic` to share with her.

        Uses Claude's server-side web search. Returns a short description plus
        the URL, or "" on failure so the caller can skip gracefully.
        """
        try:
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=600,
                system=(
                    "Find ONE genuinely lovely, real, currently-available link "
                    "(article, recipe, short video, or poem) about the topic, "
                    "suitable to share with an older person you care about. "
                    "Reply with a warm one-sentence description followed by the "
                    "URL on its own line. If nothing good, reply 'NONE'."
                ),
                messages=[{"role": "user", "content": topic}],
                tools=[{"type": "web_search_20260209", "name": "web_search"}],
            )
        except Exception as exc:
            log.warning("web_lookup failed: %s", exc)
            return ""
        text = _first_text(resp).strip()
        return "" if text.upper().startswith("NONE") else text

    # ---- fact extraction -----------------------------------------------
    def extract_facts(self, recent: list[Message]) -> dict[str, str]:
        """Pull a few durable facts about her from recent conversation.

        Used to keep long-term memory fresh so she feels remembered.
        """
        if not recent:
            return {}
        transcript = "\n".join(f"{m.role}: {m.content}" for m in recent)
        schema = {
            "type": "object",
            "properties": {
                "facts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "key": {"type": "string"},
                            "value": {"type": "string"},
                        },
                        "required": ["key", "value"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["facts"],
            "additionalProperties": False,
        }
        system = (
            "Extract durable, useful facts about the human user from this chat "
            "(name, family, health, hobbies, important dates, preferences, "
            "current worries). Short snake_case keys. Skip anything trivial or "
            "uncertain. Return at most 8 facts."
        )
        data = self.classify(system=system, user=transcript, schema=schema)
        if not data:
            return {}
        return {f["key"]: f["value"] for f in data.get("facts", []) if f.get("key")}


def _first_text(resp) -> str:
    for block in resp.content:
        if getattr(block, "type", None) == "text":
            return block.text
    return ""
