"""Spoken script assembly: fixed opening, transitions and sign-off."""
from conftest import FRIDAY, TUESDAY, make_episode
from podcast import generate


def test_fixed_opening_with_ai_disclosure(cfg):
    script = generate.assemble(make_episode(), cfg, TUESDAY)
    assert script.startswith(
        "Good morning, it's Tuesday, October 20. This is Signal in the AI Fog, your daily briefing on "
        "enterprise AI in production, written and read by AI. Today: Microsoft's sovereign cloud goes local, "
        "Mistral weights still pending, and GDPR omnibus stalls.")


def test_order_of_parts(cfg):
    script = generate.assemble(make_episode(), cfg, TUESDAY)
    markers = ["First, the story of the day.", "Next, Models and vendors.", "Next, Platform.",
               "Next, Regulation.", "Next, Retail and agents.", "The number of the day.",
               "What to watch.", "And a question for your team.", "That's it for today."]
    positions = [script.index(m) for m in markers]
    assert positions == sorted(positions)


def test_sign_off_depends_on_the_day(cfg):
    assert generate.assemble(make_episode(), cfg, TUESDAY).endswith("See you tomorrow.")
    assert generate.assemble(make_episode(), cfg, FRIDAY).endswith("See you on Monday.")


def test_headline_punctuation_is_not_doubled(cfg):
    # A headline ending with a period would be read as "...and C..".
    ep = make_episode(headlines=["First story.", "Second story", "Third story!"])
    assert "Today: First story, Second story, and Third story." in generate.assemble(ep, cfg, TUESDAY)


def test_sources_are_collected_once(episode):
    episode["segments"][0]["sources"].append(episode["story_of_the_day"]["sources"][0])
    urls = [s["url"] for s in generate.collect_sources(episode)]
    assert len(urls) == len(set(urls))
    assert urls[0] == episode["story_of_the_day"]["sources"][0]["url"]


def test_clean_for_tts():
    assert generate.clean_for_tts("A [Intro] **bold**  claim, see https://x.com") == "A bold claim, see"
