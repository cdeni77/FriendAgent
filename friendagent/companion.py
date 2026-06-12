"""The Companion: ties persona + memory + safety + Claude together.

This is the agent's brain. Channels (WhatsApp, console) call into it; the
scheduler calls into it for proactive check-ins.
"""
from __future__ import annotations

import logging

from .config import Config, load_config
from .llm import LLM
from .memory import Memory
from .notifier import Notifier
from .persona import Persona, build_system_prompt
from . import safety

log = logging.getLogger("friendagent.companion")

# How often (in message count) to refresh long-term facts from the conversation.
_FACT_REFRESH_EVERY = 6
# How many recent turns to send to the model as context.
_HISTORY_WINDOW = 24


class Companion:
    def __init__(self, cfg: Config | None = None):
        self.cfg = cfg or load_config()
        self.memory = Memory(self.cfg.db_path)
        self.llm = LLM(self.cfg.model, self.cfg.anthropic_api_key)
        self.persona = Persona.from_config(self.cfg)
        self.notifier = Notifier(self.cfg)

    # ---- main entry point ----------------------------------------------
    def handle_message(self, user_id: str, text: str) -> str:
        """Process an incoming message from her and return the reply text.

        Side effects: persists the exchange, runs the safety check (alerting the
        family on red flags), and periodically refreshes long-term memory.
        """
        # 1. Safety screen on what she sent (or relayed from a scammer).
        result = safety.assess(
            text,
            llm=self.llm,
            use_llm=self.cfg.llm_safety_check,
        )
        if result.is_flagged:
            log.warning(
                "Flagged message from %s (%s): %s",
                user_id, result.severity.name, result.categories,
            )
            self.notifier.alert(user_id, text, result)

        # 2. Record her message.
        self.memory.add_message(user_id, "user", text)

        # 3. Build context + generate the companion's reply.
        history = self.memory.recent_messages(user_id, limit=_HISTORY_WINDOW)
        system_prompt = build_system_prompt(
            self.persona, self.memory.facts_summary(user_id)
        )
        try:
            reply = self.llm.reply(system_prompt, history)
        except Exception as exc:
            log.error("LLM reply failed: %s", exc)
            reply = (
                "I'm having a little trouble finding my words right now, "
                "but I'm here. Tell me again in a moment?"
            )

        # 4. Record the reply and maybe refresh memory.
        self.memory.add_message(user_id, "assistant", reply)
        self._maybe_refresh_facts(user_id)
        return reply

    # ---- proactive check-in --------------------------------------------
    _OCCASION_HINTS = {
        "morning": (
            "It's morning. Send a warm good-morning text to start her day."
        ),
        "evening": (
            "It's evening. Send a warm message asking how her day went."
        ),
        "spontaneous": (
            "Reach out unprompted, just because you were thinking of her — a "
            "little 'thinking of you' or a follow-up on something she mentioned."
        ),
    }

    def proactive_checkin(self, user_id: str, occasion: str | None = None) -> str:
        """Generate and store a warm, unprompted message to send her.

        `occasion` ("morning", "evening", "spontaneous") shapes the opener.
        """
        system_prompt = build_system_prompt(
            self.persona, self.memory.facts_summary(user_id)
        )
        recent = self.memory.recent_messages(user_id, limit=8)
        context = "\n".join(f"{m.role}: {m.content}" for m in recent)
        instruction = self._OCCASION_HINTS.get(
            occasion or "",
            "Write a short, warm check-in message to start a conversation now, "
            "unprompted.",
        )
        instruction += (
            " Reference something she's mentioned before if you can, and ask one "
            "gentle question. Keep it short — a sentence or two."
        )
        if context:
            instruction += "\n\nRecent conversation for context:\n" + context
        try:
            msg = self.llm.generate(system_prompt, instruction)
        except Exception as exc:
            log.error("LLM check-in failed: %s", exc)
            msg = "Hi! I was just thinking of you. How is your day going?"
        self.memory.add_message(user_id, "assistant", msg)
        return msg

    # ---- helpers --------------------------------------------------------
    def _maybe_refresh_facts(self, user_id: str) -> None:
        count = self.memory.message_count(user_id)
        if count == 0 or count % _FACT_REFRESH_EVERY != 0:
            return
        try:
            recent = self.memory.recent_messages(user_id, limit=_HISTORY_WINDOW)
            facts = self.llm.extract_facts(recent)
            for key, value in facts.items():
                self.memory.upsert_fact(user_id, key, value)
            if facts:
                log.info("Refreshed %d facts for %s", len(facts), user_id)
        except Exception as exc:
            log.error("Fact refresh failed: %s", exc)

    def close(self) -> None:
        self.memory.close()
