import dataclasses

from friendagent import humanize
from friendagent.config import load_config


def _cfg(**kw):
    return dataclasses.replace(load_config(), **kw)


def test_explicit_delimiter_splits():
    c = _cfg(multi_message_enabled=True, max_bubbles=3)
    text = "Good morning! [[next]] How did you sleep? [[next]] The roses look lovely today."
    bubbles = humanize.split_bubbles(text, c)
    assert bubbles == [
        "Good morning!",
        "How did you sleep?",
        "The roses look lovely today.",
    ]


def test_disabled_returns_single():
    c = _cfg(multi_message_enabled=False)
    text = "One. Two. Three."
    assert humanize.split_bubbles(text, c) == ["One. Two. Three."]


def test_never_splits_when_prob_zero():
    c = _cfg(multi_message_enabled=True, multi_bubble_prob=0.0)
    text = "First sentence. Second sentence. Third one."
    assert humanize.split_bubbles(text, c) == [text]


def test_always_splits_when_prob_one():
    c = _cfg(multi_message_enabled=True, multi_bubble_prob=1.0, max_bubbles=3)
    text = "First sentence. Second sentence. Third one."
    bubbles = humanize.split_bubbles(text, c)
    assert len(bubbles) >= 2


def test_max_bubbles_cap_merges_overflow():
    c = _cfg(multi_message_enabled=True, max_bubbles=2)
    text = "A. [[next]] B. [[next]] C. [[next]] D."
    bubbles = humanize.split_bubbles(text, c)
    assert len(bubbles) == 2
    assert bubbles[0] == "A."
    assert "B." in bubbles[1] and "D." in bubbles[1]


def test_inter_bubble_delay_within_bounds():
    c = _cfg(inter_bubble_min_sec=2, inter_bubble_max_sec=10, typing_cps=10)
    for _ in range(20):
        d = humanize.inter_bubble_delay("a short bubble", c)
        assert 2 <= d <= 10
