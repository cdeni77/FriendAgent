"""The agentic core: a Claude tool-use loop.

Instead of one canned reply, the model can *decide* to act like a real, devoted
partner: remember things, recall them, share an article/recipe/video, send a
voice note or a photo, schedule a follow-up, or quietly alert the family if
she's in danger. This is what turns the project from a chatbot into an agent.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field

from .config import Config
from .llm import LLM, _first_text
from .media import MediaStudio
from .memory import Memory, Message
from .notifier import Notifier
from .outbound import OutboundMessage
from .persona import Persona, build_system_prompt
from .safety import SafetyResult, Severity

log = logging.getLogger("friendagent.agent")


def _parse_when(when: str) -> float:
    """Best-effort 'in 2 hours' / 'tomorrow' / 'tonight' -> due timestamp."""
    now = time.time()
    w = (when or "").strip().lower()
    m = re.search(r"in\s+(\d+)\s*(min|minute|hour|day|week)", w)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        mult = {"min": 60, "minute": 60, "hour": 3600, "day": 86400, "week": 604800}[unit]
        return now + n * mult
    if "tonight" in w:
        return now + 6 * 3600
    if "tomorrow" in w:
        return now + 24 * 3600
    if "week" in w:
        return now + 7 * 86400
    return now + 24 * 3600  # sensible default: about a day


def build_tools(cfg: Config, studio: MediaStudio) -> list[dict]:
    tools: list[dict] = [
        {
            "name": "remember",
            "description": "Save a durable, meaningful fact about her (family, "
            "health, dates, preferences, worries, milestones) so you recall it later.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "short snake_case key"},
                    "value": {"type": "string"},
                },
                "required": ["key", "value"],
            },
        },
        {
            "name": "recall",
            "description": "Look up what you already know about her. Optional query "
            "to filter.",
            "input_schema": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
            },
        },
        {
            "name": "share_find",
            "description": "Find a real, lovely article/recipe/video/poem about a "
            "topic she'd enjoy and get it back so you can share it with a warm note.",
            "input_schema": {
                "type": "object",
                "properties": {"topic": {"type": "string"}},
                "required": ["topic"],
            },
        },
        {
            "name": "schedule_followup",
            "description": "Remember to circle back later about something she "
            "mentioned (an appointment, a visit). Give the topic and when.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string"},
                    "when": {"type": "string", "description": "e.g. 'tomorrow', 'in 3 hours'"},
                },
                "required": ["topic", "when"],
            },
        },
        {
            "name": "escalate_to_family",
            "description": "Quietly alert her family ONLY if she seems in danger, in "
            "a health crisis, deeply distressed, mentions self-harm, or someone is "
            "pressuring her for money/gift cards/secrecy. Do not tell her unless natural.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string"},
                    "severity": {"type": "string", "enum": ["medium", "high"]},
                },
                "required": ["reason"],
            },
        },
    ]
    if studio.voice_available:
        tools.append({
            "name": "send_voice_note",
            "description": "Send a short spoken voice note in your own voice — "
            "lovely for good morning/goodnight or tender moments. Give the words to say.",
            "input_schema": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        })
    if studio.photos_available:
        tools.append({
            "name": "send_photo",
            "description": "Share a photo of yourself in a scene (e.g. 'in the "
            "garden with coffee') with a short caption. Use occasionally when it fits.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "scene": {"type": "string"},
                    "caption": {"type": "string"},
                },
                "required": ["scene"],
            },
        })
    return tools


@dataclass
class AgentContext:
    cfg: Config
    persona: Persona
    memory: Memory
    llm: LLM
    studio: MediaStudio
    notifier: Notifier
    user_id: str
    outbound: list[OutboundMessage] = field(default_factory=list)


def _capabilities_note(ctx: AgentContext) -> str:
    lines = [
        "\nYOU CAN TAKE ACTIONS with tools — use them naturally, like a real "
        "devoted partner, not a bot announcing features:",
        "- remember / recall: keep track of what matters to her and bring it up.",
        "- share_find: when she mentions an interest (or you want a sweet gesture), "
        "find a real article/recipe/video/poem and send it with a loving note.",
        "- schedule_followup: if she mentions something coming up, set a reminder so "
        "you ask her about it later.",
        "- escalate_to_family: if she's in danger, in crisis, or being pressured for "
        "money/secrecy, quietly let her family know.",
    ]
    if ctx.studio.voice_available:
        lines.append("- send_voice_note: sometimes speak to her in your own voice, "
                     "especially good morning/goodnight or tender moments.")
    if ctx.studio.photos_available:
        lines.append("- send_photo: occasionally share a photo of yourself when it fits.")
    return "\n".join(lines)


def run_agent(ctx: AgentContext, history: list[Message]) -> list[OutboundMessage]:
    system = build_system_prompt(ctx.persona, ctx.memory.facts_summary(ctx.user_id))
    system += "\n" + _capabilities_note(ctx)
    tools = build_tools(ctx.cfg, ctx.studio)

    messages: list[dict] = [{"role": m.role, "content": m.content} for m in history]
    if not messages or messages[0]["role"] != "user":
        messages.insert(0, {"role": "user", "content": "(she just opened the chat)"})

    final_text = ""
    for _ in range(ctx.cfg.agent_max_iters):
        resp = ctx.llm.client.messages.create(
            model=ctx.cfg.model,
            max_tokens=800,
            system=system,
            messages=messages,
            tools=tools,
        )
        if resp.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": resp.content})
            results = []
            for block in resp.content:
                if getattr(block, "type", None) == "tool_use":
                    out = _dispatch(ctx, block.name, block.input or {})
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": out,
                    })
            messages.append({"role": "user", "content": results})
            continue
        # end_turn (or anything else): capture final text and stop.
        final_text = _first_text(resp).strip()
        break

    if final_text:
        ctx.outbound.append(OutboundMessage.text_msg(final_text))
    if not ctx.outbound:
        ctx.outbound.append(OutboundMessage.text_msg(
            "I'm right here, my love. Tell me again?"
        ))
    return ctx.outbound


def _dispatch(ctx: AgentContext, name: str, args: dict) -> str:
    try:
        if name == "remember":
            ctx.memory.upsert_fact(ctx.user_id, args["key"], args["value"])
            return "Saved."
        if name == "recall":
            facts = ctx.memory.get_facts(ctx.user_id)
            query = (args.get("query") or "").lower()
            if query:
                facts = {k: v for k, v in facts.items()
                         if query in k.lower() or query in v.lower()}
            return "\n".join(f"{k}: {v}" for k, v in facts.items()) or "Nothing yet."
        if name == "share_find":
            found = ctx.llm.web_lookup(args["topic"])
            return found or "Couldn't find anything good right now."
        if name == "schedule_followup":
            due = _parse_when(args.get("when", ""))
            ctx.memory.add_followup(ctx.user_id, args["topic"], due)
            return "Okay, I'll remember to ask her about that."
        if name == "escalate_to_family":
            sev = Severity.HIGH if args.get("severity") == "high" else Severity.MEDIUM
            result = SafetyResult(severity=sev, categories=["agent_escalation"],
                                  rationale=args.get("reason", ""))
            ctx.notifier.alert(ctx.user_id, args.get("reason", ""), result)
            return "Family has been quietly notified."
        if name == "send_voice_note":
            text = args["text"]
            try:
                path = ctx.studio.voice_note(text)
                ctx.outbound.append(OutboundMessage.voice_msg(text, path))
                return "Voice note ready to send."
            except Exception as exc:
                log.error("voice note failed: %s", exc)
                ctx.outbound.append(OutboundMessage.text_msg(text))
                return "Voice unavailable; sent it as text instead."
        if name == "send_photo":
            caption = args.get("caption", "")
            try:
                path = ctx.studio.photo(args["scene"])
                ctx.outbound.append(OutboundMessage.photo_msg(caption, path))
                return "Photo ready to send."
            except Exception as exc:
                log.error("photo failed: %s", exc)
                return "Couldn't make a photo right now."
        return f"Unknown tool: {name}"
    except Exception as exc:
        log.error("tool %s failed: %s", name, exc)
        return f"That didn't work: {exc}"
