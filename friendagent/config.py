"""Central configuration, loaded from environment variables.

Everything the agent needs is read once here so the rest of the code never
touches os.environ directly. Call load_config() to get a frozen Config.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # python-dotenv is optional at runtime
    pass


def _bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _list(name: str, default: Optional[list[str]] = None) -> list[str]:
    val = os.getenv(name)
    if not val:
        return list(default or [])
    return [part.strip() for part in val.split(",") if part.strip()]


@dataclass(frozen=True)
class Config:
    # Claude
    anthropic_api_key: Optional[str]
    model: str

    # Persona (the personality knobs you set in env)
    relationship: str
    persona_name: str
    persona_age: str
    persona_gender: str
    persona_traits: str
    persona_backstory: str
    persona_interests: str
    persona_tone: str
    companion_for_name: str
    companion_for_notes: str
    ai_disclosure: str
    persona_path: Optional[str]

    # Data
    db_path: str

    # Proactive check-ins
    checkin_times: list[str] = field(default_factory=list)
    timezone: str = "UTC"

    # Safety / alerts
    alert_email: Optional[str] = None
    alert_sms_to: Optional[str] = None
    llm_safety_check: bool = True

    # SMTP
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from: Optional[str] = None

    # Twilio
    twilio_account_sid: Optional[str] = None
    twilio_auth_token: Optional[str] = None
    twilio_whatsapp_from: Optional[str] = None
    twilio_sms_from: Optional[str] = None
    twilio_validate_signature: bool = False


def load_config() -> Config:
    return Config(
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        model=os.getenv("FRIENDAGENT_MODEL", "claude-opus-4-8"),
        relationship=os.getenv("FRIENDAGENT_RELATIONSHIP", "friend"),
        persona_name=os.getenv("FRIENDAGENT_PERSONA_NAME", "Sam"),
        persona_age=os.getenv("FRIENDAGENT_PERSONA_AGE", ""),
        persona_gender=os.getenv("FRIENDAGENT_PERSONA_GENDER", ""),
        persona_traits=os.getenv(
            "FRIENDAGENT_PERSONA_TRAITS", "warm, patient, a good listener"
        ),
        persona_backstory=os.getenv("FRIENDAGENT_PERSONA_BACKSTORY", ""),
        persona_interests=os.getenv("FRIENDAGENT_PERSONA_INTERESTS", ""),
        persona_tone=os.getenv(
            "FRIENDAGENT_PERSONA_TONE", "warm and easygoing; short, clear messages"
        ),
        companion_for_name=os.getenv("FRIENDAGENT_COMPANION_FOR_NAME", "my friend"),
        companion_for_notes=os.getenv("FRIENDAGENT_COMPANION_FOR_NOTES", ""),
        ai_disclosure=os.getenv(
            "FRIENDAGENT_AI_DISCLOSURE",
            "I'm an AI companion your family set up so you always have "
            "someone friendly to talk to.",
        ),
        persona_path=os.getenv("FRIENDAGENT_PERSONA_PATH", "config/persona.yaml"),
        db_path=os.getenv("FRIENDAGENT_DB_PATH", "friendagent.db"),
        checkin_times=_list("FRIENDAGENT_CHECKIN_TIMES", ["09:30", "18:00"]),
        timezone=os.getenv("FRIENDAGENT_TIMEZONE", "UTC"),
        alert_email=os.getenv("FRIENDAGENT_ALERT_EMAIL"),
        alert_sms_to=os.getenv("FRIENDAGENT_ALERT_SMS_TO"),
        llm_safety_check=_bool("FRIENDAGENT_LLM_SAFETY_CHECK", True),
        smtp_host=os.getenv("SMTP_HOST"),
        smtp_port=int(os.getenv("SMTP_PORT", "587")),
        smtp_user=os.getenv("SMTP_USER"),
        smtp_password=os.getenv("SMTP_PASSWORD"),
        smtp_from=os.getenv("SMTP_FROM"),
        twilio_account_sid=os.getenv("TWILIO_ACCOUNT_SID"),
        twilio_auth_token=os.getenv("TWILIO_AUTH_TOKEN"),
        twilio_whatsapp_from=os.getenv("TWILIO_WHATSAPP_FROM"),
        twilio_sms_from=os.getenv("TWILIO_SMS_FROM"),
        twilio_validate_signature=_bool("TWILIO_VALIDATE_SIGNATURE", False),
    )
