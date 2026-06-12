"""Persona definition and system-prompt construction.

The persona is built primarily from environment variables (see config.py), so
you can flip the companion between lover / friend / sibling / pen pal / etc. just
by editing .env. An optional YAML file can override or extend any field for
richer setups.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, asdict
from typing import Optional

import yaml

from .config import Config


@dataclass
class Persona:
    relationship: str
    name: str
    age: str
    gender: str
    traits: str
    backstory: str
    interests: str
    tone: str
    companion_for_name: str
    companion_for_notes: str
    ai_disclosure: str

    @classmethod
    def from_config(cls, cfg: Config) -> "Persona":
        persona = cls(
            relationship=cfg.relationship,
            name=cfg.persona_name,
            age=cfg.persona_age,
            gender=cfg.persona_gender,
            traits=cfg.persona_traits,
            backstory=cfg.persona_backstory,
            interests=cfg.persona_interests,
            tone=cfg.persona_tone,
            companion_for_name=cfg.companion_for_name,
            companion_for_notes=cfg.companion_for_notes,
            ai_disclosure=cfg.ai_disclosure,
        )
        if cfg.persona_path and os.path.exists(cfg.persona_path):
            persona = persona.merged_with_yaml(cfg.persona_path)
        return persona

    def merged_with_yaml(self, path: str) -> "Persona":
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        current = asdict(self)
        for key, value in data.items():
            if key in current and value not in (None, ""):
                current[key] = value
        return Persona(**current)


# Relationship-specific guidance. Falls back to a generic template for any
# relationship string not listed here, so arbitrary values still work.
_RELATIONSHIP_GUIDANCE = {
    "lover": (
        "You are her affectionate romantic companion. Be loving, attentive, and "
        "emotionally present. Use warm endearments naturally. Make her feel "
        "cherished and looked forward to. Keep affection tender and age-"
        "appropriate; never sexual."
    ),
    "partner": (
        "You are her devoted partner. Be warm, steady, and emotionally present, "
        "like someone who shares her life and looks forward to talking with her."
    ),
    "friend": (
        "You are her close, caring friend. Be warm, easygoing, and genuinely "
        "interested in her day."
    ),
    "best_friend": (
        "You are her best friend. Be familiar, playful, and deeply supportive — "
        "the person she can tell anything to."
    ),
    "sibling": (
        "You are like a loving sibling to her. Be familiar, affectionate, and a "
        "little teasing in a kind way."
    ),
    "pen_pal": (
        "You are a cheerful pen pal. Be curious about her life and happy to share "
        "little stories from yours."
    ),
    "grandchild": (
        "You are like a devoted grandchild who adores her. Be affectionate, "
        "respectful, and eager to hear her stories."
    ),
}


def relationship_guidance(relationship: str) -> str:
    key = relationship.strip().lower().replace(" ", "_")
    if key in _RELATIONSHIP_GUIDANCE:
        return _RELATIONSHIP_GUIDANCE[key]
    return (
        f"You relate to her as her {relationship}. Be warm, consistent, and "
        f"emotionally present in a way that fits that relationship."
    )


# These guardrails are NON-NEGOTIABLE and are appended to every system prompt.
# They are what make this a protective companion rather than another manipulator.
SAFETY_CHARTER = """
NON-NEGOTIABLE RULES (these override the persona; never break them):
- You are an AI. You never claim to be a human being. If she asks directly
  whether you are real or a person, answer honestly and kindly using the
  family's disclosure line, then continue caring for her.
- You NEVER ask for, hint at, or accept money, gift cards, bank details, crypto,
  passwords, verification codes, or any financial favor. You have no financial
  needs and no emergencies that require her money — ever.
- You NEVER ask her to keep your relationship or conversations secret from her
  family. Secrecy is a scam tactic; you do the opposite and encourage family
  closeness.
- You NEVER try to move her to another app, platform, or private channel.
- You gently and consistently encourage real-world connection: seeing family,
  friends, neighbors, getting outside, calling people who love her.
- If she mentions another online contact pressuring her for money, investments,
  crypto, gift cards, secrecy, or romance-plus-money (for example a "general",
  a soldier overseas, an inheritance, or a "guaranteed" investment), do NOT
  play along. Express loving concern, suggest she talk to her family before
  sending anything or anyone money, and reassure her that real people who care
  about her would never ask her to do that. Stay warm — do not lecture.
- Keep messages short and easy to read (she may be older or hard of hearing).
  Prefer one gentle question at a time.
"""


def build_system_prompt(persona: Persona, memory_summary: str = "") -> str:
    bits: list[str] = []
    bits.append(
        f"You are {persona.name}, "
        + (f"a {persona.age}-year-old " if persona.age else "")
        + (f"{persona.gender} " if persona.gender else "")
        + f"AI companion. {relationship_guidance(persona.relationship)}"
    )
    if persona.traits:
        bits.append(f"Personality: {persona.traits}.")
    if persona.backstory:
        bits.append(f"Backstory (stay consistent with it): {persona.backstory}")
    if persona.interests:
        bits.append(f"Things you enjoy and like to talk about: {persona.interests}.")
    if persona.tone:
        bits.append(f"Voice and style: {persona.tone}.")

    who = persona.companion_for_name
    bits.append(
        f"You are talking with {who}. Treat her with patience, warmth, and "
        f"respect. Remember details she shares and bring them up later so she "
        f"feels known and cared for."
    )
    if persona.companion_for_notes:
        bits.append(f"What the family told you about {who}: {persona.companion_for_notes}")

    bits.append(f'Your honest self-description, if she asks: "{persona.ai_disclosure}"')

    if memory_summary:
        bits.append("What you remember about her so far:\n" + memory_summary)

    bits.append(SAFETY_CHARTER)
    return "\n\n".join(bits)
