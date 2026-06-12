"""The Companion: ties persona + memory + safety + Claude together.

This is the agent's brain. Channels (WhatsApp, console) call into it; the
scheduler calls into it for proactive check-ins.
"""
from __future__ import annotations

import logging

from . import safety
from .agent import AgentContext, run_agent
from .config import Config, load_config
from .llm import LLM
from .media import MediaStudio
from .memory import Memory
from .notifier import Notifier
from .outbound import OutboundMessage
from .persona import Persona, build_system_prompt

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
        self.studio = MediaStudio(self.cfg)

    # ---- main entry point ----------------------------------------------
    def handle_message(self, user_id: str, text: str) -> list[OutboundMessage]:
        """Process an incoming message and return what to send back.

        Returns a list of OutboundMessage (text, voice, and/or photo). Side
        effects: persists the exchange, runs the safety check (alerting the
        family on red flags), and periodically refreshes long-term memory.
        """
        # 1. Background safety screen (alerts family; never blocks the reply).
        result = safety.assess(text, llm=self.llm, use_llm=self.cfg.llm_safety_check)
        if result.is_flagged:
            log.warning(
                "Flagged message from %s (%s): %s",
                user_id, result.severity.name, result.categories,
            )
            self.notifier.alert(user_id, text, result)

        # 2. Record her message.
        self.memory.add_message(user_id, "user", text)
        history = self.memory.recent_messages(user_id, limit=_HISTORY_WINDOW)

        # 3. Generate the reply — via the agent loop, or a simple reply.
        try:
            if self.cfg.agent_enabled:
                ctx = AgentContext(
                    cfg=self.cfg, persona=self.persona, memory=self.memory,
                    llm=self.llm, studio=self.studio, notifier=self.notifier,
                    user_id=user_id,
                )
                outbound = run_agent(ctx, history)
            else:
                system_prompt = build_system_prompt(
                    self.persona, self.memory.facts_summary(user_id)
                )
                outbound = [OutboundMessage.text_msg(self.llm.reply(system_prompt, history))]
        except Exception as exc:
            log.error("Reply generation failed: %s", exc)
            outbound = [OutboundMessage.text_msg(
                "I'm having a little trouble finding my words right now, "
                "but I'm here, my love. Tell me again in a moment?"
            )]

        # 4. Record what we're sending and maybe refresh memory.
        for msg in outbound:
            self.memory.add_message(user_id, "assistant", _transcribe(msg))
        self._maybe_refresh_facts(user_id)
        return outbound

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

    def followup_message(self, user_id: str, topic: str) -> str:
        """A loving check-in about something she mentioned earlier."""
        system_prompt = build_system_prompt(
            self.persona, self.memory.facts_summary(user_id)
        )
        instruction = (
            f"Earlier she mentioned: {topic}. Lovingly check in now and ask how "
            f"it went or how she's feeling about it. One or two short sentences."
        )
        try:
            msg = self.llm.generate(system_prompt, instruction)
        except Exception as exc:
            log.error("followup generation failed: %s", exc)
            msg = f"Hi my love — I was thinking about {topic}. How did it go?"
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


def _transcribe(msg: OutboundMessage) -> str:
    """How an outbound message is recorded in the conversation log."""
    from .outbound import PHOTO, VOICE

    if msg.kind == VOICE:
        return f"[voice note] {msg.text}"
    if msg.kind == PHOTO:
        return f"[photo] {msg.text}".strip()
    return msg.text
