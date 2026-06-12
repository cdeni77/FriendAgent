from friendagent.media.transcribe import compose_inbound_text


def test_text_only():
    assert compose_inbound_text("hello there", "") == "hello there"


def test_voice_only():
    out = compose_inbound_text("", "good morning sweetheart")
    assert "voice note" in out and "good morning sweetheart" in out


def test_both_combined():
    out = compose_inbound_text("see photo", "and here is what I said")
    assert "see photo" in out and "and here is what I said" in out


def test_empty():
    assert compose_inbound_text("", "") == ""
