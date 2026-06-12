import dataclasses

from friendagent import delivery
from friendagent.channels.base import Channel
from friendagent.config import load_config


class FakeChannel(Channel):
    def __init__(self):
        self.sent: list[tuple[str, str]] = []

    def send(self, to: str, text: str) -> None:
        self.sent.append((to, text))


def _cfg(**kw):
    return dataclasses.replace(load_config(), **kw)


def test_chat_channel_sends_multiple_bubbles():
    ch = FakeChannel()
    cfg = _cfg(
        multi_message_enabled=True,
        max_bubbles=3,
        inter_bubble_min_sec=0,
        inter_bubble_max_sec=0,
    )
    delivery.deliver(ch, "sms:+14155550123", "Hi! [[next]] How are you? [[next]] Miss you.", cfg)
    assert [t for _, t in ch.sent] == ["Hi!", "How are you?", "Miss you."]
    assert all(to == "sms:+14155550123" for to, _ in ch.sent)


def test_email_is_single_message():
    ch = FakeChannel()
    cfg = _cfg(multi_message_enabled=True)
    delivery.deliver(ch, "email:gran@example.com", "Hi! [[next]] How are you?", cfg)
    assert len(ch.sent) == 1
    assert "Hi!" in ch.sent[0][1] and "How are you?" in ch.sent[0][1]
