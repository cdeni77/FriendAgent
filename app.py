"""FastAPI app exposing inbound webhooks for WhatsApp, SMS, and email.

Run:
    uvicorn app:app --host 0.0.0.0 --port 8000

Twilio (WhatsApp + SMS) — set the number's inbound webhook to:
    https://<host>/webhooks/twilio/whatsapp
    https://<host>/webhooks/twilio/sms

Email — point an inbound-parse service (SendGrid Inbound Parse, Mailgun route,
etc.) at:
    https://<host>/webhooks/email/inbound

Generated voice notes / photos are served from /media/<file> so Twilio can fetch
them — set FRIENDAGENT_PUBLIC_BASE_URL to this server's public URL.

Replies are sent back over the same channel after a human-like delay (the agent
"notices" the message and "types"), as one or several texts plus any voice/photo.
"""
from __future__ import annotations

import asyncio
import logging
import os

from fastapi import FastAPI, Form, Request, Response
from fastapi.responses import FileResponse

from friendagent import delivery, humanize
from friendagent.channels.email import EmailChannel
from friendagent.channels.router import ChannelRouter
from friendagent.companion import Companion
from friendagent.outbound import OutboundMessage, TEXT

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("friendagent.app")

app = FastAPI(title="FriendAgent")
companion = Companion()
router = ChannelRouter(companion.cfg, companion.persona.name)


def _twiml(message: str = "") -> Response:
    from xml.sax.saxutils import escape

    inner = f"<Message>{escape(message)}</Message>" if message else ""
    body = f"<?xml version='1.0' encoding='UTF-8'?><Response>{inner}</Response>"
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


def _initial_delay_seconds(outbound: list[OutboundMessage]) -> float:
    first_text = next((m.text for m in outbound if m.kind == TEXT and m.text), "")
    return humanize.compute_delay(first_text or "x" * 40, companion.cfg)


async def _reply_after_delay(user_id: str, text: str, deliver_fn) -> None:
    """Generate a reply, wait a human-like amount, then deliver it."""
    try:
        outbound = await asyncio.to_thread(companion.handle_message, user_id, text)
        delay = _initial_delay_seconds(outbound)
        if delay > 0:
            log.info("Replying to %s in %.0fs (%d parts)", user_id, delay, len(outbound))
            await asyncio.sleep(delay)
        await asyncio.to_thread(deliver_fn, outbound)
    except Exception as exc:
        log.error("Delayed reply to %s failed: %s", user_id, exc)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model": companion.cfg.model}


@app.get("/media/{filename}")
def media(filename: str):
    path = os.path.join(companion.cfg.media_dir, os.path.basename(filename))
    if not os.path.exists(path):
        return Response(status_code=404)
    return FileResponse(path)


@app.post("/webhooks/twilio/whatsapp")
async def whatsapp_webhook(request: Request, Body: str = Form(""), From: str = Form("")):
    form = dict(await request.form())
    if not _validate_twilio(request, form):
        return Response(status_code=403)
    user_id = From or "whatsapp:unknown"
    log.info("Inbound WhatsApp from %s: %s", user_id, Body)
    if companion.cfg.humanize_timing:
        asyncio.create_task(_reply_after_delay(
            user_id, Body or "",
            lambda outs: delivery.deliver(router, user_id, outs, companion.cfg),
        ))
        return _twiml()
    outbound = await asyncio.to_thread(companion.handle_message, user_id, Body or "")
    return _twiml(_join_text(outbound))


@app.post("/webhooks/twilio/sms")
async def sms_webhook(request: Request, Body: str = Form(""), From: str = Form("")):
    form = dict(await request.form())
    if not _validate_twilio(request, form):
        return Response(status_code=403)
    user_id = f"sms:{From}" if From and not From.startswith("sms:") else (From or "sms:unknown")
    log.info("Inbound SMS from %s: %s", user_id, Body)
    if companion.cfg.humanize_timing:
        asyncio.create_task(_reply_after_delay(
            user_id, Body or "",
            lambda outs: delivery.deliver(router, user_id, outs, companion.cfg),
        ))
        return _twiml()
    outbound = await asyncio.to_thread(companion.handle_message, user_id, Body or "")
    return _twiml(_join_text(outbound))


@app.post("/webhooks/email/inbound")
async def email_webhook(request: Request):
    form = dict(await request.form())
    sender = _extract_email(form.get("from") or form.get("sender") or form.get("From") or "")
    subject = form.get("subject") or form.get("Subject") or ""
    text = (
        form.get("text") or form.get("body-plain")
        or form.get("stripped-text") or form.get("plain") or ""
    )
    if not sender:
        log.warning("Inbound email with no usable sender; ignoring")
        return Response(status_code=200)

    user_id = f"email:{sender}"
    reply_subject = subject if subject.lower().startswith("re:") else f"Re: {subject or 'Hello'}"
    log.info("Inbound email from %s (subject=%r)", user_id, subject)

    def _send_email(outbound: list[OutboundMessage]) -> None:
        body = _join_text(outbound)
        if body:
            EmailChannel(companion.cfg, companion.persona.name).send(
                sender, body, subject=reply_subject
            )

    asyncio.create_task(_reply_after_delay(user_id, text, _send_email))
    return Response(status_code=200)


def _join_text(outbound: list[OutboundMessage]) -> str:
    return "\n\n".join(m.text for m in outbound if m.text)


def _extract_email(value: str) -> str:
    import re

    m = re.search(r"[^@<\s]+@[^@>\s]+", value or "")
    return m.group(0) if m else ""
