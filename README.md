# FriendAgent

A warm, **transparent** AI companion for an elderly family member who is lonely
and being targeted by a romance / "pig-butchering" scammer (e.g. a fake
"general").

This is **not** a tool that pretends to be a human. The companion is an AI that
the family sets up openly. Its two jobs are:

1. **Companionship** — give a lonely person someone friendly to talk to every
   day, with a persona and personality you configure. Loneliness is the opening
   scammers exploit; a real, consistent presence helps close it.
2. **Quiet protection** — the companion never asks for money, never moves the
   conversation to other apps, and gently counters scam narratives. A safety
   layer watches her messages for classic pig-butchering red flags (money
   requests, crypto/investment "opportunities", the fake general, secrecy,
   gift cards, wire transfers) and **alerts you, the family member**, so a real
   human can step in.

> Design principle: we do not deceive the person we're trying to protect.
> The companion is honest about being an AI. The only thing kept quiet is the
> safety monitoring, and even that should be disclosed to her and consented to
> wherever the law (and decency) requires it. See `docs/CONSENT.md`.

---

## Architecture

```
        WhatsApp (Twilio)   SMS (Twilio)   Email (SMTP/inbound parse)   Console
                │               │                    │                     │
                ▼               ▼                    ▼                     ▼
                ┌───────────────────────────────────────────────────────────┐
                │                       Channels + Router                     │
                │  twilio_whatsapp.py  sms.py  email.py  console.py  router.py│
                └───────────────────────────┬───────────────────────────────┘
                                             │
                                             ▼
                                ┌────────────────────────┐
                                │      Companion          │  orchestrator
                                │   (companion.py)        │
                                └─┬─────────┬─────────┬───┘
                                  │         │         │
                  ┌───────────────┘    ┌────┘     └─────────────┐
                  ▼                    ▼                          ▼
            ┌───────────┐       ┌────────────┐            ┌────────────┐
            │  Persona  │       │   Memory   │            │   Safety   │
            │persona.py │       │ memory.py  │            │ safety.py  │
            │  (YAML)   │       │ (SQLite)   │            │ + alerts   │
            └───────────┘       └────────────┘            └─────┬──────┘
                  │                                             │ red flag
                  ▼                                             ▼
            ┌───────────┐                               ┌──────────────┐
            │   Claude  │                               │  Notifier    │
            │  (llm.py) │                               │ (you get a   │
            │ opus-4-8  │                               │   message)   │
            └───────────┘                               └──────────────┘

      Scheduler (scheduler.py) → proactive daily check-ins
```

## Quick start (local, no phone needed)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # add your ANTHROPIC_API_KEY
cp config/persona.example.yaml config/persona.yaml   # edit the persona
python -m friendagent.cli       # chat with the companion in your terminal
```

The console chat exercises the exact same companion, memory, and safety code the
WhatsApp path uses — try typing something a scammer would say (e.g. *"The general
asked me to buy gift cards"*) and watch the safety alert fire.

## Going live (WhatsApp, SMS, and email)

The agent talks to her over **WhatsApp, SMS, and email** — all three. Each
contact is addressed by a channel-prefixed string so replies and proactive
check-ins go back over the right channel:

```
whatsapp:+14155550123     sms:+14155550123     email:grandma@example.com
```

1. **Run the webhook server** (handles inbound on all channels):
   ```bash
   uvicorn app:app --host 0.0.0.0 --port 8000
   ```
   Expose it publicly (e.g. `ngrok http 8000`).

2. **WhatsApp + SMS (Twilio):** create a Twilio account, enable the WhatsApp
   sandbox or sender (https://www.twilio.com/docs/whatsapp) and an SMS number.
   Fill in `TWILIO_*` in `.env`. Point the inbound webhooks at:
   - WhatsApp → `https://<host>/webhooks/twilio/whatsapp`
   - SMS → `https://<host>/webhooks/twilio/sms`

3. **Email (SMTP out + inbound parse in):** set `SMTP_*` in `.env` for sending.
   For receiving, point an inbound-email service (SendGrid Inbound Parse, Mailgun
   route, etc.) at `https://<host>/webhooks/email/inbound`.

4. **Daily check-ins:** list who to reach in `FRIENDAGENT_SEED_CONTACTS` (using
   the prefixed addresses above), then run:
   ```bash
   python -m friendagent.scheduler
   ```

You only need credentials for the channels you actually use — the router builds
each one lazily.

## Configuration

Everything is driven by environment variables (`.env`) and `config/persona.yaml`.
See `.env.example` and `config/persona.example.yaml` for the full set, both
heavily commented.

## Safety & ethics

Read `docs/CONSENT.md` before deploying. Short version: tell your grandma she has
an AI friend the family set up, and (where required) that messages are screened
for scams to keep her safe. Don't run covert surveillance on an adult without a
good-faith basis and, ideally, her awareness.

## Tests

```bash
pytest
```
