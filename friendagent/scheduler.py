"""Proactive daily check-ins.

Runs a blocking scheduler that, at the configured times, sends every known
contact a warm unprompted message over whatever channel that contact uses
(WhatsApp, SMS, or email). Run it as its own process:

    python -m friendagent.scheduler

Contacts are everyone the agent has talked to (from memory). For a brand-new
deployment, seed FRIENDAGENT_SEED_CONTACTS with channel-prefixed addresses, e.g.

    FRIENDAGENT_SEED_CONTACTS=whatsapp:+14155550123,sms:+14155550123,email:grandma@example.com

Each contact is reached over the channel encoded in its address.
"""
from __future__ import annotations

import logging
import os

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from .channels.router import ChannelRouter
from .companion import Companion

log = logging.getLogger("friendagent.scheduler")


def _contacts(companion: Companion) -> list[str]:
    seeded = [c.strip() for c in os.getenv("FRIENDAGENT_SEED_CONTACTS", "").split(",") if c.strip()]
    known = companion.memory.known_user_ids()
    # De-dupe while preserving order; skip non-routable console users.
    contacts = [c for c in dict.fromkeys(seeded + known) if c != "console-user"]
    return contacts


def run_checkins(companion: Companion, router: ChannelRouter) -> None:
    for user_id in _contacts(companion):
        try:
            msg = companion.proactive_checkin(user_id)
            router.send(user_id, msg)
            log.info("Check-in sent to %s", user_id)
        except Exception as exc:
            log.error("Check-in to %s failed: %s", user_id, exc)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    companion = Companion()
    router = ChannelRouter(companion.cfg, companion.persona.name)

    scheduler = BlockingScheduler(timezone=companion.cfg.timezone)
    for t in companion.cfg.checkin_times:
        hour, minute = t.split(":")
        scheduler.add_job(
            run_checkins,
            CronTrigger(hour=int(hour), minute=int(minute)),
            args=[companion, router],
            id=f"checkin-{t}",
        )
        log.info("Scheduled daily check-in at %s (%s)", t, companion.cfg.timezone)

    log.info("Scheduler running. Ctrl-C to stop.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        companion.close()


if __name__ == "__main__":
    main()
