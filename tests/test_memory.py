import os
import tempfile

from friendagent.memory import Memory


def _mem():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    return Memory(path), path


def test_messages_roundtrip_and_order():
    mem, path = _mem()
    try:
        mem.add_message("u1", "user", "hi")
        mem.add_message("u1", "assistant", "hello there")
        mem.add_message("u1", "user", "how are you")
        msgs = mem.recent_messages("u1", limit=10)
        assert [m.content for m in msgs] == ["hi", "hello there", "how are you"]
        assert mem.message_count("u1") == 3
    finally:
        mem.close()
        os.remove(path)


def test_facts_upsert_and_summary():
    mem, path = _mem()
    try:
        mem.upsert_fact("u1", "favorite_flower", "roses")
        mem.upsert_fact("u1", "favorite_flower", "tulips")  # overwrite
        assert mem.get_facts("u1")["favorite_flower"] == "tulips"
        assert "tulips" in mem.facts_summary("u1")
    finally:
        mem.close()
        os.remove(path)


def test_known_user_ids():
    mem, path = _mem()
    try:
        mem.add_message("whatsapp:+1", "user", "hi")
        mem.add_message("email:a@b.com", "user", "hello")
        assert set(mem.known_user_ids()) == {"whatsapp:+1", "email:a@b.com"}
    finally:
        mem.close()
        os.remove(path)
