"""Shared fixtures: config, a valid episode, and a fake Claude client.

No test calls a real API: the fake client replays scripted responses and checks
the conversation follows the Messages API rules.
"""
import copy
import datetime as dt
import sys
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from podcast import generate  # noqa: E402

PARIS = ZoneInfo("Europe/Paris")
TUESDAY = dt.datetime(2026, 10, 20, 7, 0, tzinfo=PARIS)
FRIDAY = dt.datetime(2026, 10, 23, 7, 0, tzinfo=PARIS)
SATURDAY = dt.datetime(2026, 10, 24, 7, 0, tzinfo=PARIS)


@pytest.fixture
def cfg():
    return yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))


def text(n: int, word: str = "lorem") -> str:
    """A spoken text of exactly n words."""
    return " ".join([word] * (n - 1)) + "."


SOURCE = {"title": "Example: an article", "url": "https://example.com/a"}


def make_episode(**overrides) -> dict:
    """A valid episode close to the target length; override any field."""
    ep = {
        "title": "Sovereign clouds go local",
        "summary": "Microsoft widens its sovereign cloud, and Mistral's weights are still pending.",
        "headlines": ["Microsoft's sovereign cloud goes local", "Mistral weights still pending",
                      "GDPR omnibus stalls"],
        "story_of_the_day": {"theme": "Sovereignty and Europe", "facts": text(130),
                             "read": "The read here: " + text(107), "sources": [SOURCE]},
        "segments": [
            {"theme": t, "facts": text(45), "read": "Why it matters: " + text(32),
             "sources": [{"title": f"Source for {t}", "url": f"https://example.com/{i}"}]}
            for i, t in enumerate(("Models and vendors", "Platform", "Regulation", "Retail and agents"))
        ],
        "number_of_the_day": {"text": text(30), "source": {"title": "Numbers", "url": "https://example.com/n"}},
        "what_to_watch": text(60),
        "question": text(25),
    }
    ep.update(copy.deepcopy(overrides))
    return ep


@pytest.fixture
def episode():
    return make_episode()


# --- Fake Claude client -------------------------------------------------------

def text_block(t):
    return SimpleNamespace(type="text", text=t)


def submit_block(ep, id_="toolu_1"):
    return SimpleNamespace(type="tool_use", name="submit_episode", id=id_, input=ep)


def reply(*blocks, stop_reason=None):
    if stop_reason is None:
        stop_reason = "tool_use" if any(b.type == "tool_use" for b in blocks) else "end_turn"
    return SimpleNamespace(content=list(blocks), stop_reason=stop_reason)


class FakeClient:
    """Replays responses and enforces the API rule that a tool_use is answered by a tool_result."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        msgs = kw["messages"]
        for prev, nxt in zip(msgs, msgs[1:]):
            if prev["role"] != "assistant":
                continue
            uses = {b.id for b in prev["content"] if getattr(b, "type", "") == "tool_use"}
            answered = {c["tool_use_id"] for c in nxt["content"]
                        if isinstance(c, dict) and c.get("type") == "tool_result"} \
                if isinstance(nxt["content"], list) else set()
            assert uses <= answered, "a tool_use was not answered with a tool_result"
        self.calls.append(copy.deepcopy(kw))
        assert self.responses, "unexpected extra API call"
        return self.responses.pop(0)


@pytest.fixture
def fake_claude(monkeypatch):
    """fake_claude([reply(...), ...]) installs a FakeClient and returns it."""
    def install(responses):
        client = FakeClient(responses)

        def factory(**kw):
            client.init_kwargs = kw
            return client
        monkeypatch.setattr(generate.anthropic, "Anthropic", factory)
        return client
    return install
