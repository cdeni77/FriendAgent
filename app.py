"""FastAPI app exposing inbound webhooks for WhatsApp, SMS, and email.

Run:
    uvicorn app:app --host 0.0.0.0 --port 8000

Twilio (WhatsApp + SMS) — set the number's inbound webhook to:
    https://<host>/webhooks/twilio/whatsapp
    https://<host>/webhooks/twilio/sms

Email — point an inbound-parse service (SendGrid Inbound Parse, Mailgun route,
etc.) at:
    https://<host>/webhooks/email/inbound

Outbound replies go back over the same channel the message arrived on.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Form, Request, Response

from friendagent.channels.email import EmailChannel
from friendagent.companion import Companion

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("friendagent.app")

app = FastAPI(title="FriendAgent")
companion = Companion()


def _twiml(message: str) -> Response:
    """Reply in the same Twilio thread (works for both WhatsApp and SMS)."""
    from xml.sax.saxutils import escape

    body = (
        "<?xml version='1.0' encoding='UTF-8'?>"
        f"<Response><Message>{escape(message)}</Message></Response>"
    )
    return Response(content=body, media_type="application/xml")


def _validate_twilio(request: Request, form: dict) -> bool:
    cfg = companion.cfg
    if not cfg.twilio_validate_signature:
        return True
    if not cfg.twilio_auth_token:
        return False
    try:
        from twilio.request_validator import RequestValidator

        validator = RequestValidator(cfg.twilio_auth_token)
        signature = request.headers.get("X-Twilio-Signature", "")
        return validator.validate(str(request.url), form, signature)
    except Exception as exc:  # pragma: no cover
        log.error("Twilio signature validation error: %s", exc)
        return False


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model": companion.cfg.model}


@app.post("/webhooks/twilio/whatsapp")
async def whatsapp_webhook(request: Request, Body: str = Form(""), From: str = Form("")):
    form = dict(await request.form())
    if not _validate_twilio(request, form):
        return Response(status_code=403)
    # From already looks like "whatsapp:+1..."
    user_id = From or "whatsapp:unknown"
    log.info("Inbound WhatsApp from %s: %s", user_id, Body)
    reply = companion.handle_message(user_id, Body or "")
    return _twiml(reply)


@app.post("/webhooks/twilio/sms")
async def sms_webhook(request: Request, Body: str = Form(""), From: str = Form("")):
    form = dict(await request.form())
    if not _validate_twilio(request, form):
        return Response(status_code=403)
    # Normalize to an "sms:" address so routing/memory is unambiguous.
    user_id = f"sms:{From}" if From and not From.startswith("sms:") else (From or "sms:unknown")
    log.info("Inbound SMS from %s: %s", user_id, Body)
    reply = companion.handle_message(user_id, Body or "")
    return _twiml(reply)


@app.post("/webhooks/email/inbound")
async def email_webhook(request: Request):
    """Generic inbound-email handler (SendGrid Inbound Parse / Mailgun).

    Reads common field names for the sender, subject, and plaintext body, then
    replies by sending an email back.
    """
    form = dict(await request.form())
    sender = form.get("from") or form.get("sender") or form.get("From") or ""
    sender = _extract_email(sender)
    subject = form.get("subject") or form.get("Subject") or ""
    text = (
        form.get("text")
        or form.get("body-plain")
        or form.get("stripped-text")
        or form.get("plain")
        or ""
    )
    if not sender:
        log.warning("Inbound email with no usable sender; ignoring")
        return Response(status_code=200)

    user_id = f"email:{sender}"
    log.info("Inbound email from %s (subject=%r)", user_id, subject)
    reply = companion.handle_message(user_id, text)

    try:
        channel = EmailChannel(companion.cfg, companion.persona.name)
        reply_subject = subject if subject.lower().startswith("re:") else f"Re: {subject or 'Hello'}"
        channel.send(sender, reply, subject=reply_subject)
    except Exception as exc:
        log.error("Failed to send email reply: %s", exc)
    return Response(status_code=200)


def _extract_email(value: str) -> str:
    """Pull a bare address out of 'Name <addr@x.com>' style headers."""
    import re

    m = re.search(r"[^@<\s]+@[^@>\s]+", value or "")
    return m.group(0) if m else ""
