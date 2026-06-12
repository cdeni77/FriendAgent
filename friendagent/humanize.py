"""Human-like response timing.

She knows it's an AI, but instant, robotic replies still feel off. This computes
a natural delay before the companion answers: a short "noticing" pause plus
"typing" time proportional to the reply length, with jitter and sane caps. It
also respects quiet hours so the agent never messages her in the middle of the
night — replies that land during quiet hours are deferred to the morning.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Optional

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore

from .config import Config


def _parse_quiet(spec: str) -> Optional[tuple[int, int]]:
    """Parse 'HH:MM-HH:MM' into (start_minute, end_minute) of the day."""
    spec = (spec or "").strip()
    if not spec or "-" not in spec:
        return None
    start_s, end_s = spec.split("-", 1)
    try:
        sh, sm = (int(x) for x in start_s.split(":"))
        eh, em = (int(x) for x in end_s.split(":"))
    except ValueError:
        return None
    return sh * 60 + sm, eh * 60 + em


def _now(cfg: Config) -> datetime:
    if ZoneInfo is not None:
        try:
            return datetime.now(ZoneInfo(cfg.timezone))
        except Exception:
            pass
    return datetime.now()


def seconds_until_active(cfg: Config, now: Optional[datetime] = None) -> float:
    """If we're currently inside quiet hours, seconds until they end; else 0."""
    window = _parse_quiet(cfg.quiet_hours)
    if window is None:
        return 0.0
    now = now or _now(cfg)
    start, end = window
    minute_of_day = now.hour * 60 + now.minute
    wraps = start > end  # e.g. 22:00 -> 08:00 spans midnight

    in_quiet = (start <= minute_of_day < end) if not wraps else (
        minute_of_day >= start or minute_of_day < end
    )
    if not in_quiet:
        return 0.0

    # Compute the next datetime at `end`.
    end_h, end_m = divmod(end, 60)
    target = now.replace(hour=end_h % 24, minute=end_m, second=0, microsecond=0)
    if target <= now:
        target = target + timedelta(days=1)
    return max(0.0, (target - now).total_seconds())


def _active_reply_seconds(reply_text: str, cfg: Config) -> float:
    """Time for an 'at the phone' reply: noticing + typing + a little jitter."""
    notice = random.uniform(cfg.read_min_sec, cfg.read_max_sec)
    typing = len(reply_text) / max(cfg.typing_cps, 1.0)
    jitter = random.uniform(0, cfg.reply_jitter_sec)
    return notice + typing + jitter


def compute_delay(reply_text: str, cfg: Config, now: Optional[datetime] = None) -> float:
    """Seconds to wait before sending `reply_text`.

    Models a real person's variable availability as a mixture:
      * with probability `quick_reply_prob`, she's "at her phone" and replies
        quickly (capped at `quick_max_delay_sec` — usually a few minutes);
      * otherwise she's "busy/away" and replies after a long, random gap drawn
        from [`long_delay_min_sec`, `long_delay_max_sec`] (minutes to hours).
    Quiet hours always win: a reply due overnight is deferred to the morning.
    """
    if not cfg.humanize_timing:
        return 0.0

    active = _active_reply_seconds(reply_text, cfg)
    if random.random() < cfg.quick_reply_prob:
        delay = min(active, cfg.quick_max_delay_sec)
    else:
        # "Busy" — a long gap, plus the time to actually read and type once back.
        delay = random.uniform(cfg.long_delay_min_sec, cfg.long_delay_max_sec) + active

    delay = min(max(delay, cfg.min_reply_delay_sec), cfg.max_reply_delay_sec)

    # Never message her during quiet hours — defer to when they end.
    defer = seconds_until_active(cfg, now)
    return max(delay, defer)
