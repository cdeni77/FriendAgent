import os
import tempfile
import time

from friendagent.memory import Memory
from friendagent.outbound import OutboundMessage, PHOTO, TEXT, VOICE, deserialize, serialize


def _mem():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    return Memory(path), path


def test_serialize_round_trip():
    msgs = [
        OutboundMessage.text_msg("Good morning my love"),
        OutboundMessage.voice_msg("hello dear", "/tmp/a.mp3"),
        OutboundMessage.photo_msg("in the garden", "/tmp/b.png"),
    ]
    back = deserialize(serialize(msgs))
    assert [m.kind for m in back] == [TEXT, VOICE, PHOTO]
    assert back[1].media_path == "/tmp/a.mp3"
    assert back[2].text == "in the garden"


def test_enqueue_and_due():
    mem, path = _mem()
    try:
        past = time.time() - 10
        future = time.time() + 10_000
        sid_due = mem.enqueue_send("sms:+1", past, serialize([OutboundMessage.text_msg("hi")]))
        mem.enqueue_send("sms:+1", future, serialize([OutboundMessage.text_msg("later")]))
        due = mem.due_sends()
        assert [d[0] for d in due] == [sid_due]  # only the past-due one
    finally:
        mem.close(); os.remove(path)


def test_claim_is_exactly_once():
    mem, path = _mem()
    try:
        sid = mem.enqueue_send("sms:+1", time.time() - 1, serialize([OutboundMessage.text_msg("hi")]))
        assert mem.claim_send(sid) is True
        assert mem.claim_send(sid) is False  # second claim fails -> no double send
        assert mem.due_sends() == []          # claimed = done
    finally:
        mem.close(); os.remove(path)
