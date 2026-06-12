import dataclasses
from datetime import datetime

from friendagent import humanize
from friendagent.config import load_config

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None


def _cfg(**kw):
    return dataclasses.replace(load_config(), **kw)


def test_no_timing_returns_zero():
    assert humanize.compute_delay("hello there", _cfg(humanize_timing=False)) == 0.0


def test_quick_band_stays_within_quick_cap():
    # Force the quick band every time and check it never exceeds the cap.
    c = _cfg(
        humanize_timing=True,
        quiet_hours="",
        quick_reply_prob=1.0,
        quick_max_delay_sec=120,
        min_reply_delay_sec=2,
    )
    for _ in range(50):
        d = humanize.compute_delay("a short little reply", c)
        assert 2 <= d <= 120


def test_busy_band_produces_long_delays():
    # Force the busy band; replies should be in the configured long range.
    c = _cfg(
        humanize_timing=True,
        quiet_hours="",
        quick_reply_prob=0.0,
        long_delay_min_sec=600,
        long_delay_max_sec=3600,
    )
    for _ in range(50):
        d = humanize.compute_delay("hey there", c)
        assert d >= 600


def test_mixture_yields_both_quick_and_slow():
    c = _cfg(
        humanize_timing=True,
        quiet_hours="",
        quick_reply_prob=0.5,
        quick_max_delay_sec=240,
        long_delay_min_sec=600,
        long_delay_max_sec=7200,
    )
    delays = [humanize.compute_delay("hi", c) for _ in range(200)]
    assert any(d <= 240 for d in delays), "expected some quick replies"
    assert any(d >= 600 for d in delays), "expected some hours-long replies"


def test_quiet_hours_defers_to_morning():
    if ZoneInfo is None:
        return
    c = _cfg(humanize_timing=True, quiet_hours="22:00-08:00", timezone="UTC")
    night = datetime(2026, 1, 1, 3, 0, tzinfo=ZoneInfo("UTC"))
    d = humanize.compute_delay("hi", c, now=night)
    assert d >= 5 * 3600 - 120  # ~5 hours until 08:00


def test_daytime_quick_reply_not_deferred():
    if ZoneInfo is None:
        return
    c = _cfg(
        humanize_timing=True,
        quiet_hours="22:00-08:00",
        timezone="UTC",
        quick_reply_prob=1.0,
        quick_max_delay_sec=120,
    )
    day = datetime(2026, 1, 1, 12, 0, tzinfo=ZoneInfo("UTC"))
    assert humanize.compute_delay("hi", c, now=day) <= 120
