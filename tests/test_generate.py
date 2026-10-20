"""The generation loop with Claude: tool submission, corrections, truncation, headers."""
import pytest

from conftest import TUESDAY, make_episode, reply, submit_block, text_block
from podcast import generate


def last_user_content(call):
    return call["messages"][-1]["content"]


def test_valid_submission_on_first_attempt(cfg, fake_claude):
    client = fake_claude([reply(text_block("Research done."), submit_block(make_episode()))])
    ep = generate.generate_episode(cfg, TUESDAY, [])
    assert len(client.calls) == 1
    assert ep["title"] == "Sovereign clouds go local"
    assert ep["script"].startswith("Good morning, it's Tuesday, October 20.")
    assert {"web_search", "submit_episode"} <= {t["name"] for t in client.calls[0]["tools"]}


def test_episode_is_submitted_through_the_tool_not_as_text(cfg, fake_claude):
    # Regression (2026-10-20): free-text JSON was malformed (unescaped quotes).
    # Text answers are refused and the model is asked to call the tool.
    client = fake_claude([reply(text_block('{"title": "broken "json"}')),
                          reply(submit_block(make_episode()))])
    generate.generate_episode(cfg, TUESDAY, [])
    assert "call the submit_episode tool" in last_user_content(client.calls[1])


def is_light(call):
    """A light correction: one user message, only the submit tool, forced."""
    return (len(call["messages"]) == 1 and [t["name"] for t in call["tools"]] == ["submit_episode"]
            and call.get("tool_choice") == {"type": "tool", "name": "submit_episode"})


def test_wording_errors_are_fixed_in_a_light_correction(cfg, fake_claude):
    # Learning (2026-10-20): correction rounds replayed every search result, about 3x the cost.
    bad = make_episode(headlines=["one, two", "b c", "d e"])
    client = fake_claude([reply(submit_block(bad, "toolu_a")), reply(submit_block(make_episode(), "toolu_b"))])
    generate.generate_episode(cfg, TUESDAY, [])
    light = client.calls[1]
    assert is_light(light)
    prompt = light["messages"][0]["content"]
    assert "must not contain a comma" in prompt and '"one, two"' in prompt


def test_missing_source_goes_back_to_the_research_conversation(cfg, fake_claude):
    # Without web search, a light correction could invent a source: never allowed.
    bad = make_episode()
    bad["segments"][0]["sources"] = []
    client = fake_claude([reply(submit_block(bad, "toolu_a")), reply(submit_block(make_episode(), "toolu_b"))])
    generate.generate_episode(cfg, TUESDAY, [])
    full = client.calls[1]
    assert not is_light(full)
    assert "web_search" in [t["name"] for t in full["tools"]]
    result = last_user_content(full)[0]
    assert result["tool_use_id"] == "toolu_a" and "has no source" in result["content"]


def test_too_short_episode_goes_back_to_research(cfg, fake_claude):
    short = make_episode()
    short["segments"] = short["segments"][:2]
    short["story_of_the_day"]["facts"] = "Short facts."
    short["story_of_the_day"]["read"] = "Short read."
    client = fake_claude([reply(submit_block(short, "toolu_a")), reply(submit_block(make_episode(), "toolu_b"))])
    generate.generate_episode(cfg, TUESDAY, [])
    assert not is_light(client.calls[1])


def test_failed_light_correction_resumes_the_research_conversation(cfg, fake_claude):
    # The pending tool call of the research conversation must be the one answered,
    # not the light correction's (that would be rejected by the API).
    bad = make_episode(headlines=["one, two", "b c", "d e"])
    client = fake_claude([reply(submit_block(bad, "toolu_full")),
                          reply(submit_block({"title": "t"}, "toolu_light"), stop_reason="max_tokens"),
                          reply(submit_block(make_episode(), "toolu_full2"))])
    generate.generate_episode(cfg, TUESDAY, [])
    assert is_light(client.calls[1]) and not is_light(client.calls[2])
    assert last_user_content(client.calls[2])[0]["tool_use_id"] == "toolu_full"


def test_two_correction_rounds_then_give_up(cfg, fake_claude):
    bad = make_episode(question="What should we do " + "x " * 20)
    client = fake_claude([reply(submit_block(bad, f"toolu_{i}")) for i in range(3)])
    with pytest.raises(SystemExit, match="nothing published"):
        generate.generate_episode(cfg, TUESDAY, [])
    assert [is_light(c) for c in client.calls] == [False, True, True]


def test_truncated_response_is_named_as_such(cfg, fake_claude):
    # Regression (2026-10-20): the first attempt was cut off by max_tokens and only
    # reported "Missing field", which does not tell the model what went wrong.
    partial = {"title": "t", "summary": "s", "headlines": ["a b", "c d", "e f"]}
    client = fake_claude([reply(submit_block(partial, "toolu_cut"), stop_reason="max_tokens"),
                          reply(submit_block(make_episode(), "toolu_ok"))])
    generate.generate_episode(cfg, TUESDAY, [])
    result = last_user_content(client.calls[1])[0]
    assert result["tool_use_id"] == "toolu_cut"  # still answered with a tool_result
    assert "cut off by the output length limit" in result["content"]


def test_truncated_text_without_tool_call(cfg, fake_claude):
    client = fake_claude([reply(text_block("I found"), stop_reason="max_tokens"),
                          reply(submit_block(make_episode()))])
    generate.generate_episode(cfg, TUESDAY, [])
    assert "cut off" in last_user_content(client.calls[1])


def test_pause_turn_is_continued(cfg, fake_claude):
    client = fake_claude([reply(text_block("Searching..."), stop_reason="pause_turn"),
                          reply(submit_block(make_episode()))])
    generate.generate_episode(cfg, TUESDAY, [])
    assert len(client.calls) == 2
    assert client.calls[1]["messages"][-1]["role"] == "assistant"  # continuation, no new user turn


def test_max_tokens_leaves_room_for_the_episode(cfg):
    # Regression (2026-10-20): 8000 output tokens were not enough after long web searches.
    assert cfg["generation"]["max_tokens"] >= 16000


def test_workspace_header(cfg, fake_claude, monkeypatch):
    # Regression (2026-10-14): a key not scoped to a workspace needs the anthropic-workspace-id header.
    monkeypatch.setenv("ANTHROPIC_WORKSPACE_ID", "wrkspc_test")
    client = fake_claude([reply(submit_block(make_episode()))])
    generate.generate_episode(cfg, TUESDAY, [])
    assert client.init_kwargs["default_headers"] == {"anthropic-workspace-id": "wrkspc_test"}


def test_no_workspace_header_by_default(cfg, fake_claude, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_WORKSPACE_ID", raising=False)
    client = fake_claude([reply(submit_block(make_episode()))])
    generate.generate_episode(cfg, TUESDAY, [])
    assert client.init_kwargs["default_headers"] is None


def test_private_context_is_appended_to_the_system_prompt(cfg, fake_claude, monkeypatch):
    monkeypatch.setenv("EDITORIAL_CONTEXT", "Written for a test audience.")
    client = fake_claude([reply(submit_block(make_episode()))])
    generate.generate_episode(cfg, TUESDAY, [])
    system = client.calls[0]["system"]
    assert "Private editorial context (never mention or quote)" in system
    assert system.endswith("Written for a test audience.\n")
    assert "{target_words}" not in system


def test_user_message_variants(cfg):
    import datetime as dt
    monday = TUESDAY - dt.timedelta(days=1)
    friday = TUESDAY + dt.timedelta(days=3)
    assert "It is Monday" in generate.build_user_message(cfg, monday, [])
    assert "It is Friday" in generate.build_user_message(cfg, friday, [])
    msg = generate.build_user_message(cfg, TUESDAY, ["previous script"])
    assert "Tuesday, October 20, 2026" in msg and "previous script" in msg
