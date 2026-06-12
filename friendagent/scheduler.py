"""Proactive outreach: scheduled check-ins + occasional spontaneous messages.

Run it as its own process:

    python -m friendagent.scheduler

What it does:
  * Daily check-ins at FRIENDAGENT_CHECKIN_TIMES, each with random jitter so
    they don't land at the exact same minute every day. Morning/evening times
    get a fitting "good morning" / "how was your day" opener.
  * Spontaneous outreach: every so often it may reach out unprompted ("thinking
    of you"), so the agent isn't purely reactive. Quiet hours are respected.

Contacts are everyone the agent has talked to, plus FRIENDAGENT_SEED_CONTACTS
(channel-prefixed addresses, e.g. whatsapp:+1..., sms:+1..., email:gran@x.com).
"""
from __future__ import annotations

import logging
import os
import random

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from . import delivery, humanize
from .channels.router import ChannelRouter
from .companion import Companion

log = logging.getLogger("friendagent.scheduler")


def _contacts(companion: Companion) -> list[str]:
    seeded = [c.strip() for c in os.getenv("FRIENDAGENT_SEED_CONTACTS", "").split(",") if c.strip()]
    known = companion.memory.known_user_ids()
    return [c for c in dict.fromkeys(seeded + known) if c != "console-user"]


def _occasion_for_hour(hour: int) -> str | None:
    if 4 <= hour < 12:
        return "morning"
    if 17 <= hour <= 23:
        return "evening"
    return None


def run_checkins(companion: Companion, router: ChannelRouter, occasion: str | None) -> None:
    for user_id in _contacts(companion):
        try:
            msg = companion.proactive_checkin(user_id, occasion=occasion)
            delivery.deliver(router, user_id, msg, companion.cfg)
            log.info("Check-in (%s) sent to %s", occasion or "general", user_id)
        except Exception as exc:
            log.error("Check-in to %s failed: %s", user_id, exc)


def run_due_followups(companion: Companion, router: ChannelRouter) -> None:
    """Send any scheduled follow-ups whose time has come (respecting quiet hours)."""
    if humanize.seconds_until_active(companion.cfg) > 0:
        return
    for followup_id, user_id, topic in companion.memory.due_followups():
        try:
            msg = companion.followup_message(user_id, topic)
            delivery.deliver(router, user_id, msg, companion.cfg)
            companion.memory.mark_followup_done(followup_id)
            log.info("Follow-up sent to %s about %r", user_id, topic)
        except Exception as exc:
            log.error("Follow-up to %s failed: %s", user_id, exc)


def maybe_spontaneous(companion: Companion, router: ChannelRouter) -> None:
    cfg = companion.cfg
    if not cfg.spontaneous_enabled:
        return
    # Respect quiet hours — don't surprise her at night.
    if humanize.seconds_until_active(cfg) > 0:
        return
    for user_id in _contacts(companion):
        if random.random() >= cfg.spontaneous_prob:
            continue
        try:
            msg = companion.proactive_checkin(user_id, occasion="spontaneous")
            delivery.deliver(router, user_id, msg, cfg)
            log.info("Spontaneous message sent to %s", user_id)
        except Exception as exc:
            log.error("Spontaneous message to %s failed: %s", user_id, exc)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    companion = Companion()
    cfg = companion.cfg
    router = ChannelRouter(cfg, companion.persona.name)

    scheduler = BlockingScheduler(timezone=cfg.timezone)
    jitter = int(cfg.checkin_jitter_sec)
    for t in cfg.checkin_times:
        hour, minute = (int(x) for x in t.split(":"))
        scheduler.add_job(
            run_checkins,
            CronTrigger(hour=hour, minute=minute, jitter=jitter),
            args=[companion, router, _occasion_for_hour(hour)],
            id=f"checkin-{t}",
        )
        log.info("Scheduled check-in ~%s (±%ds) (%s)", t, jitter, cfg.timezone)

    if cfg.spontaneous_enabled:
        scheduler.add_job(
            maybe_spontaneous,
            IntervalTrigger(minutes=cfg.spontaneous_interval_min),
            args=[companion, router],
            id="spontaneous",
        )
        log.info(
            "Spontaneous outreach every %dmin (p=%.2f per contact)",
            cfg.spontaneous_interval_min, cfg.spontaneous_prob,
        )

    # Check for due follow-ups frequently so "ask her about X later" lands on time.
    scheduler.add_job(
        run_due_followups,
        IntervalTrigger(minutes=15),
        args=[companion, router],
        id="followups",
    )
    log.info("Follow-up checks every 15min")

    log.info("Scheduler running. Ctrl-C to stop.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        companion.close()


if __name__ == "__main__":
    main()
