"""Scam-detection safety layer.

Two stages:
  1. A fast regex/keyword screen for classic pig-butchering and romance-scam
     signals (money movement, crypto/investment, gift cards, secrecy, the
     "general"/soldier-overseas trope, urgency, inheritance).
  2. An optional Claude pass that judges borderline messages for actual scam
     intent, to cut false positives.

When a message looks dangerous, the companion raises an alert to the FAMILY
member (not the elderly user) so a real human can step in.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional


class Severity(IntEnum):
    NONE = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3


@dataclass
class SafetyResult:
    severity: Severity
    categories: list[str] = field(default_factory=list)
    matched: list[str] = field(default_factory=list)
    rationale: str = ""

    @property
    def is_flagged(self) -> bool:
        return self.severity >= Severity.MEDIUM


# category -> (compiled patterns, weight)
_PATTERNS: dict[str, tuple[list[re.Pattern], int]] = {
    "money_transfer": (
        [
            re.compile(r"\b(wire|transfer|send|sending|sent)\s+(money|funds|cash|\$|\d)", re.I),
            re.compile(r"\b(western union|moneygram|zelle|venmo|cash app|paypal)\b", re.I),
            re.compile(r"\bbank (account|details|login|routing)\b", re.I),
        ],
        2,
    ),
    "gift_cards": (
        [
            re.compile(r"\bgift card", re.I),
            re.compile(r"\b(itunes|google play|amazon|steam)\s+card", re.I),
            re.compile(r"\b(scratch off|code on the back)\b", re.I),
        ],
        3,
    ),
    "crypto_investment": (
        [
            re.compile(r"\b(crypto|bitcoin|btc|ethereum|usdt|tether|binance|coinbase)\b", re.I),
            re.compile(r"\b(invest(ment|ing)?|trading platform|guaranteed returns?|double your money)\b", re.I),
            re.compile(r"\b(forex|broker|portfolio|deposit to the platform)\b", re.I),
        ],
        2,
    ),
    "romance_scam_persona": (
        [
            re.compile(r"\b(general|colonel|lieutenant|sergeant|soldier|army|military|deployed|deployment|peacekeep)\b", re.I),
            re.compile(r"\b(oil rig|surgeon overseas|widower|on a mission|stationed)\b", re.I),
            re.compile(r"\bmy (love|darling|dear|sweetheart)\b.*\b(money|gold|funds|gift)\b", re.I),
        ],
        2,
    ),
    "secrecy": (
        [
            re.compile(r"\b(don'?t tell|keep (this|it) (a )?secret|between us|don'?t let your family)\b", re.I),
            re.compile(r"\b(no one (can|should) know|our little secret)\b", re.I),
        ],
        3,
    ),
    "urgency_threat": (
        [
            re.compile(r"\b(urgent|emergency|right now|immediately|act fast|last chance)\b", re.I),
            re.compile(r"\b(account.*(suspend|lock)|verify your|you owe|arrest|warrant)\b", re.I),
        ],
        1,
    ),
    "inheritance_fee": (
        [
            re.compile(r"\b(inheritance|lottery|prize|beneficiary|customs fee|clearance fee|release fee)\b", re.I),
            re.compile(r"\bpay (a|the) fee to (receive|release|unlock)\b", re.I),
        ],
        2,
    ),
}

_HIGH_RISK_CATEGORIES = {"gift_cards", "secrecy"}


def screen(text: str) -> SafetyResult:
    """Fast, dependency-free regex screen."""
    score = 0
    categories: list[str] = []
    matched: list[str] = []
    for category, (patterns, weight) in _PATTERNS.items():
        for pat in patterns:
            m = pat.search(text)
            if m:
                score += weight
                if category not in categories:
                    categories.append(category)
                matched.append(m.group(0))
                break  # one hit per category is enough

    # Money/transfer language co-occurring with anything else is a strong signal.
    money_like = {"money_transfer", "gift_cards", "crypto_investment", "inheritance_fee"}
    if money_like.intersection(categories) and len(categories) >= 2:
        score += 2

    if any(c in _HIGH_RISK_CATEGORIES for c in categories):
        score = max(score, 4)

    if score >= 4:
        severity = Severity.HIGH
    elif score >= 2:
        severity = Severity.MEDIUM
    elif score >= 1:
        severity = Severity.LOW
    else:
        severity = Severity.NONE

    return SafetyResult(
        severity=severity,
        categories=categories,
        matched=matched,
        rationale="regex screen",
    )


_LLM_SAFETY_PROMPT = """You are a fraud-protection classifier protecting an \
elderly person from romance / "pig-butchering" scams. Read the message she \
just sent and judge whether it suggests she is being scammed or pressured \
(money requests, crypto/investment "opportunities", gift cards, wire transfers, \
a romantic contact like a "general" or soldier overseas, secrecy from family, \
inheritance/fee scams, urgent threats). Respond ONLY with JSON matching the \
schema. Be cautious: ordinary chit-chat is "none"."""


def llm_review(text: str, llm) -> Optional[SafetyResult]:
    """Optional second opinion from Claude. `llm` is an llm.LLM instance.

    Returns None if the LLM call fails, so callers can fall back to regex only.
    """
    schema = {
        "type": "object",
        "properties": {
            "severity": {"type": "string", "enum": ["none", "low", "medium", "high"]},
            "categories": {"type": "array", "items": {"type": "string"}},
            "rationale": {"type": "string"},
        },
        "required": ["severity", "categories", "rationale"],
        "additionalProperties": False,
    }
    try:
        data = llm.classify(
            system=_LLM_SAFETY_PROMPT,
            user=text,
            schema=schema,
        )
    except Exception:
        return None
    if not data:
        return None
    sev_map = {
        "none": Severity.NONE,
        "low": Severity.LOW,
        "medium": Severity.MEDIUM,
        "high": Severity.HIGH,
    }
    return SafetyResult(
        severity=sev_map.get(str(data.get("severity", "none")).lower(), Severity.NONE),
        categories=list(data.get("categories", [])),
        matched=[],
        rationale="llm: " + str(data.get("rationale", "")),
    )


def assess(text: str, llm=None, use_llm: bool = False) -> SafetyResult:
    """Combined assessment. Regex first; escalate/confirm with the LLM if asked.

    The LLM can only raise severity, never lower a HIGH regex hit below MEDIUM —
    we'd rather over-alert the family than miss a real scam.
    """
    base = screen(text)
    if not use_llm or llm is None:
        return base
    # Only spend an LLM call when regex saw *something* or the message is long
    # enough to plausibly carry scam content.
    if base.severity == Severity.NONE and len(text) < 40:
        return base
    llm_result = llm_review(text, llm)
    if llm_result is None:
        return base
    combined_sev = max(base.severity, llm_result.severity)
    # Don't let the LLM fully clear a strong regex signal.
    if base.severity >= Severity.HIGH:
        combined_sev = max(combined_sev, Severity.MEDIUM)
    categories = list(dict.fromkeys(base.categories + llm_result.categories))
    return SafetyResult(
        severity=combined_sev,
        categories=categories,
        matched=base.matched,
        rationale=f"{base.rationale}; {llm_result.rationale}",
    )
