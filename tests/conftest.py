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
SHOW = "shows/signal-in-the-ai-fog"  # the first show, whose behaviour the engine must keep
sys.path.insert(0, str(ROOT))

from engine import generate  # noqa: E402

PARIS = ZoneInfo("Europe/Paris")
TUESDAY = dt.datetime(2026, 10, 20, 7, 0, tzinfo=PARIS)
FRIDAY = dt.datetime(2026, 10, 23, 7, 0, tzinfo=PARIS)
SATURDAY = dt.datetime(2026, 10, 24, 7, 0, tzinfo=PARIS)


@pytest.fixture
def cfg():
    return yaml.safe_load((ROOT / SHOW / "show.yaml").read_text(encoding="utf-8"))


def text(n: int, word: str = "lorem") -> str:
    """A spoken text of exactly n words."""
    return " ".join([word] * (n - 1)) + "."


SOURCE = {"title": "Example: an article", "url": "https://example.com/a", "primary": True}


def make_episode(**overrides) -> dict:
    """A valid episode close to the target length; override any field."""
    ep = {
        "title": "Sovereign clouds go local",
        "summary": "Microsoft widens its sovereign cloud, and Mistral's weights are still pending.",
        "headlines": ["Microsoft's sovereign cloud goes local", "Mistral weights still pending",
                      "GDPR omnibus stalls"],
        "story_of_the_day": {"theme": "Sovereignty and Europe", "facts": text(130),
                             "read": "The read here: " + text(107), "label": "confirmed",
                             "topics": ["Microsoft", "Sovereign cloud"], "sources": [SOURCE]},
        "segments": [
            {"theme": t, "facts": text(45), "read": "Why it matters: " + text(32), "label": "reported",
             "topics": [f"Topic {i}"],
             "sources": [{"title": f"Source for {t}", "url": f"https://example.com/{i}", "primary": False}]}
            for i, t in enumerate(("Models and vendors", "Platform", "Regulation", "Retail and agents"))
        ],
        "number_of_the_day": {"text": text(30), "source": {"title": "Numbers", "url": "https://example.com/n",
                                                           "primary": True}},
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


def reply(*blocks, stop_reason=None, usage=None):
    if stop_reason is None:
        stop_reason = "tool_use" if any(b.type == "tool_use" for b in blocks) else "end_turn"
    return SimpleNamespace(content=list(blocks), stop_reason=stop_reason, usage=usage)


def usage(input_tokens=0, output_tokens=0, cache_write=0, cache_read=0, searches=0):
    """The shape of a Messages API usage object."""
    return SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens,
                           cache_creation_input_tokens=cache_write, cache_read_input_tokens=cache_read,
                           server_tool_use=SimpleNamespace(web_search_requests=searches))


FORCED_TOOL_CHOICE_REJECTED = {"claude-sonnet-5-5", "claude-opus-5-5", "claude-fable-5-1", "claude-mythos-5-1"}


class FakeClient:
    """Replays responses and enforces the API rule that a tool_use is answered by a tool_result."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        # Regression (2026-10-21): these models answer a forced tool_choice with HTTP 400, which
        # the light correction sent. The fake API refuses it the same way.
        forced = (kw.get("tool_choice") or {}).get("type") in ("any", "tool")
        assert not (forced and kw["model"] in FORCED_TOOL_CHOICE_REJECTED), \
            f"{kw['model']} rejects a forced tool_choice (HTTP 400)"
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


@pytest.fixture(autouse=True)
def offline_factcheck(monkeypatch):
    """The suite never reaches the web: fact-check pages cannot be fetched unless a test fakes them.
    Learning (2026-10-21): the first fact-check wiring fetched example.com from the tests."""
    import requests
    from engine import factcheck

    def no_network(*args, **kwargs):
        raise requests.ConnectionError("offline test suite")
    monkeypatch.setattr(factcheck.requests, "get", no_network)
