import os
import tempfile
import time
import types

from friendagent import agent
from friendagent.agent import AgentContext, _dispatch, _parse_when, build_tools, run_agent
from friendagent.config import load_config
from friendagent.memory import Memory, Message
from friendagent.outbound import PHOTO, TEXT, VOICE
from friendagent.persona import Persona


class FakeStudio:
    def __init__(self, voice=True, photos=True):
        self.voice_available = voice
        self.photos_available = photos

    def voice_note(self, text):
        return "/tmp/voice_test.mp3"

    def photo(self, scene):
        return "/tmp/photo_test.png"


class FakeNotifier:
    def __init__(self):
        self.alerts = []

    def alert(self, user_id, text, result):
        self.alerts.append((user_id, text, result))


class FakeLLM:
    def __init__(self, scripted=None):
        self.client = types.SimpleNamespace(
            messages=types.SimpleNamespace(create=self._create)
        )
        self._scripted = scripted or []
        self._i = 0

    def _create(self, **kwargs):
        resp = self._scripted[self._i]
        self._i += 1
        return resp

    def web_lookup(self, topic):
        return f"A lovely piece about {topic}\nhttp://example.com/x"


def _text_block(text):
    return types.SimpleNamespace(type="text", text=text)


def _tool_block(name, inp, id="t1"):
    return types.SimpleNamespace(type="tool_use", name=name, input=inp, id=id)


def _resp(stop_reason, content):
    return types.SimpleNamespace(stop_reason=stop_reason, content=content)


def _ctx(llm=None, studio=None, notifier=None):
    cfg = load_config()
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    mem = Memory(path)
    persona = Persona.from_config(cfg)
    ctx = AgentContext(
        cfg=cfg, persona=persona, memory=mem, llm=llm or FakeLLM(),
        studio=studio or FakeStudio(), notifier=notifier or FakeNotifier(),
        user_id="sms:+1",
    )
    return ctx, path


def test_build_tools_gates_media():
    cfg = load_config()
    no_media = [t["name"] for t in build_tools(cfg, FakeStudio(voice=False, photos=False))]
    assert "send_voice_note" not in no_media and "send_photo" not in no_media
    with_media = [t["name"] for t in build_tools(cfg, FakeStudio(voice=True, photos=True))]
    assert "send_voice_note" in with_media and "send_photo" in with_media


def test_dispatch_remember_and_recall():
    ctx, path = _ctx()
    try:
        assert _dispatch(ctx, "remember", {"key": "flower", "value": "roses"}) == "Saved."
        out = _dispatch(ctx, "recall", {"query": "flower"})
        assert "roses" in out
    finally:
        ctx.memory.close(); os.remove(path)


def test_dispatch_share_find_uses_web_lookup():
    ctx, path = _ctx()
    try:
        out = _dispatch(ctx, "share_find", {"topic": "gardening"})
        assert "example.com" in out
    finally:
        ctx.memory.close(); os.remove(path)


def test_dispatch_voice_queues_outbound():
    ctx, path = _ctx()
    try:
        _dispatch(ctx, "send_voice_note", {"text": "good morning my love"})
        assert any(m.kind == VOICE for m in ctx.outbound)
    finally:
        ctx.memory.close(); os.remove(path)


def test_dispatch_escalate_alerts_family():
    notifier = FakeNotifier()
    ctx, path = _ctx(notifier=notifier)
    try:
        _dispatch(ctx, "escalate_to_family", {"reason": "mentioned chest pain", "severity": "high"})
        assert len(notifier.alerts) == 1
    finally:
        ctx.memory.close(); os.remove(path)


def test_dispatch_schedule_followup_persists():
    ctx, path = _ctx()
    try:
        _dispatch(ctx, "schedule_followup", {"topic": "doctor visit", "when": "in 1 hour"})
        due = ctx.memory.due_followups(now_ts=time.time() + 10**9)
        assert any("doctor" in topic for _, _, topic in due)
    finally:
        ctx.memory.close(); os.remove(path)


def test_parse_when():
    now = time.time()
    assert _parse_when("in 2 hours") > now + 7000
    assert _parse_when("tomorrow") > now + 80000
    assert _parse_when("") > now  # default future


def test_run_agent_executes_tool_then_replies():
    scripted = [
        _resp("tool_use", [_tool_block("remember", {"key": "pet", "value": "a cat named Mittens"})]),
        _resp("end_turn", [_text_block("Aw, Mittens sounds lovely, my dear.")]),
    ]
    ctx, path = _ctx(llm=FakeLLM(scripted))
    try:
        out = run_agent(ctx, [Message("user", "I have a cat named Mittens", 0.0)])
        assert out[-1].kind == TEXT
        assert "Mittens" in out[-1].text
        assert ctx.memory.get_facts("sms:+1").get("pet")
    finally:
        ctx.memory.close(); os.remove(path)
