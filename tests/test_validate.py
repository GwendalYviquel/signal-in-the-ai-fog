"""Episode validation: what blocks an episode, and what only warns."""
import pytest

from conftest import SOURCE, make_episode, text
from engine import generate


def errors_of(ep, cfg):
    return generate.validate(ep, cfg)[0]


def test_valid_episode_passes(episode, cfg):
    errors, warnings = generate.validate(episode, cfg)
    assert errors == []
    assert warnings == []


@pytest.mark.parametrize("field", ["title", "summary", "headlines", "story_of_the_day", "segments",
                                   "number_of_the_day", "what_to_watch", "question"])
def test_missing_field_is_an_error(cfg, field):
    # Regression (2026-10-20): a truncated submission arrived with only the first fields.
    ep = make_episode()
    del ep[field]
    assert f"Missing field: {field}" in errors_of(ep, cfg)


# --- Headlines ------------------------------------------------------------------

def test_exactly_three_headlines(cfg):
    assert any("Expected 3 headlines" in e for e in errors_of(make_episode(headlines=["a b", "c d"]), cfg))


def test_headline_with_comma_is_rejected(cfg):
    # Regression (2026-10-20): "Mistral Large 4 is live in preview, weights still pending"
    # made "Today: A, B, and C" unreadable.
    ep = make_episode(headlines=["Mistral Large 4 live, weights pending", "b c", "d e"])
    assert any("must not contain a comma" in e for e in errors_of(ep, cfg))


def test_headline_too_long_is_rejected_with_its_count(cfg):
    # Learning (2026-10-20): "Gemini four Argon goes live with a price cliff" failed at 9 words
    # without saying so; the limit is now 10 and the error gives the count.
    assert not errors_of(make_episode(headlines=["Gemini four Argon goes live with a price cliff", "b", "c"]), cfg)
    ep = make_episode(headlines=["one two three four five six seven eight nine ten eleven", "b c", "d e"])
    assert "Headline has 11 words, max 10: 'one two three four five six seven eight nine ten eleven'" in errors_of(ep, cfg)


def test_headline_numbers_must_be_spelled_out(cfg):
    # Regression (2026-10-20): "1,000 tokens per second" was rejected for its comma;
    # numbers without separators, or in words, pass.
    assert errors_of(make_episode(headlines=["Mercury 3 passes 1,000 tokens", "b c", "d e"]), cfg)
    assert not errors_of(make_episode(headlines=["Mercury 3 passes 1000 tokens", "b c", "d e"]), cfg)
    assert not errors_of(make_episode(headlines=["Mercury 3 passes one thousand tokens", "b c", "d e"]), cfg)


# --- Themes and sources -----------------------------------------------------------

def test_unknown_story_theme(cfg):
    ep = make_episode()
    ep["story_of_the_day"]["theme"] = "Gossip"
    assert any("Unknown theme for the story" in e for e in errors_of(ep, cfg))


def test_segments_must_follow_theme_order(cfg):
    ep = make_episode()
    ep["segments"].reverse()
    assert any("theme order" in e for e in errors_of(ep, cfg))


def test_segment_theme_used_twice(cfg):
    ep = make_episode()
    ep["segments"][1]["theme"] = ep["segments"][0]["theme"]
    assert any("theme order" in e for e in errors_of(ep, cfg))


def test_segment_count_bounds(cfg):
    ep = make_episode()
    ep["segments"] = ep["segments"][:1]
    assert any("segments, got 1" in e for e in errors_of(ep, cfg))


def test_every_story_needs_a_source(cfg):
    ep = make_episode()
    ep["segments"][2]["sources"] = []
    ep["story_of_the_day"]["sources"] = [{"title": "No link", "url": "not a url"}]
    errs = errors_of(ep, cfg)
    assert "The story of the day has no source" in errs
    assert any("has no source" in e and "Regulation" in e for e in errs)


# --- Spoken text --------------------------------------------------------------------

@pytest.mark.parametrize("bad", ["Timestral [1] ships", "a **bold** claim", "see https://x.com now",
                                 "a <cite>tag</cite>", "an_underscore", "a {brace}"])
def test_unspeakable_characters_are_rejected_with_the_extract(cfg, bad):
    # Regression (2026-10-20): the error did not say which characters were wrong,
    # so the correction round could not fix them.
    ep = make_episode()
    ep["segments"][1]["facts"] = bad + " " + text(40)
    errs = [e for e in errors_of(ep, cfg) if e.startswith("Markdown, brackets or links in segment facts")]
    assert errs and bad.split()[0] in errs[0]


@pytest.mark.parametrize("phrase,blocked", [("we think", True), ("Our view", True), ("for us", True),
                                            ("rolling out in the US", False), ("users and uses", False)])
def test_first_person(cfg, phrase, blocked):
    ep = make_episode(question=f"Question about {phrase} " + text(20))
    assert any("First person" in e for e in errors_of(ep, cfg)) == blocked


def test_forbidden_terms_in_spoken_and_published_text(cfg, monkeypatch):
    monkeypatch.setenv("FORBIDDEN_TERMS", "Acme Corp, Widget")
    ep = make_episode(title="What Widget did")
    ep["what_to_watch"] = "Watch acme corp closely. " + text(55)
    ep["segments"][0]["sources"][0]["title"] = "Widget announces"
    errs = errors_of(ep, cfg)
    assert "Forbidden term in title" in errs
    assert "Forbidden term in source title" in errs
    assert "Forbidden term in what_to_watch" in errs


def test_no_forbidden_terms_configured(cfg, monkeypatch):
    monkeypatch.delenv("FORBIDDEN_TERMS", raising=False)
    assert generate._forbidden_terms() == []
    assert errors_of(make_episode(), cfg) == []


# --- Length ---------------------------------------------------------------------------

def test_part_length_only_warns(cfg):
    ep = make_episode()
    ep["segments"][0]["read"] = "Why it matters: " + text(58)
    errors, warnings = generate.validate(ep, cfg)
    assert errors == []
    assert any(w.startswith("segment read: ") for w in warnings)


def test_total_length_far_from_target_is_an_error(cfg):
    ep = make_episode()
    ep["story_of_the_day"]["facts"] = text(900)
    assert any(e.startswith("Episode is too long") for e in errors_of(ep, cfg))


def test_unknown_segment_theme_lists_the_valid_ones(cfg):
    ep = make_episode()
    ep["segments"][0]["theme"] = "Models & Vendors"  # close but not exact
    errs = errors_of(ep, cfg)
    assert any(e.startswith("Unknown segment theme; use exactly: Models and vendors, ") for e in errs)


def test_segment_needs_both_layers(cfg):
    ep = make_episode()
    ep["segments"][1]["read"] = ""
    assert "Segment 'Platform' needs both facts and read" in errors_of(ep, cfg)


def test_every_story_has_a_known_reliability_label(cfg):
    ep = make_episode()
    ep["segments"][0]["label"] = "rumour"
    del ep["story_of_the_day"]["label"]
    errs = errors_of(ep, cfg)
    assert any("Label of the story of the day" in e for e in errs)
    assert any("Label of the segment 'Models and vendors'" in e and "'rumour'" in e for e in errs)


@pytest.mark.parametrize("topics,message", [([], "needs 1 to 3 topics"), (["A", "B", "C", "D"], "needs 1 to 3 topics"),
                                            (["One two three four five"], "1 to 4 words"),
                                            (["Platform"], "is a theme name")])
def test_topics_are_short_subjects_not_themes(cfg, topics, message):
    ep = make_episode()
    ep["story_of_the_day"]["topics"] = topics
    assert any(message in e for e in errors_of(ep, cfg))


def test_topics_are_published_so_forbidden_terms_are_checked(cfg, monkeypatch):
    monkeypatch.setenv("FORBIDDEN_TERMS", "Acme")
    ep = make_episode()
    ep["segments"][1]["topics"] = ["Acme stores"]
    assert "Forbidden term in topic" in errors_of(ep, cfg)


def test_follow_up_is_optional_but_needs_a_source_and_spoken_text(cfg):
    assert errors_of(make_episode(follow_up={"text": text(40), "source": SOURCE}), cfg) == []
    errs = errors_of(make_episode(follow_up={"text": "See [link] " + text(40), "source": {"title": "S", "url": ""}}), cfg)
    assert "The follow-up has no source" in errs and any("in follow_up" in e for e in errs)


def test_follow_up_without_source_goes_back_to_research():
    # A light correction cannot search the web: it would have to invent the source.
    assert generate._needs_research(["The follow-up has no source"])


def test_an_avoided_site_is_dropped_when_the_story_has_other_sources(cfg):
    # Learning (2026-10-21): content aggregators (Lindy, mer.vin, AI Weekly) sat beside the primary sources.
    ep = make_episode()
    ep["story_of_the_day"]["sources"].append({"title": "Lindy: rewrite", "url": "https://www.lindy.ai/blog/x", "primary": False})
    errs = errors_of(ep, cfg)
    assert any("avoided site in the story of the day: https://www.lindy.ai/blog/x (drop it" in e for e in errs)
    assert not generate._needs_research(errs)  # dropping a source needs no research


def test_a_story_left_with_only_avoided_sites_goes_back_to_research(cfg):
    ep = make_episode()
    ep["segments"][0]["sources"] = [{"title": "AI Weekly", "url": "https://aiweekly.co/alerts/x", "primary": False}]
    errs = errors_of(ep, cfg)
    assert any("has no source outside the avoided sites" in e for e in errs) and generate._needs_research(errs)


def test_confirmed_needs_a_primary_source(cfg):
    ep = make_episode()
    ep["segments"][0]["label"] = "confirmed"  # its only source is press
    assert any("labelled confirmed but cites no primary source" in e for e in errors_of(ep, cfg))


def test_every_source_says_whether_it_is_primary(cfg):
    ep = make_episode()
    del ep["number_of_the_day"]["source"]["primary"]
    assert any("Source without primary true or false in the number of the day" in e for e in errors_of(ep, cfg))


def test_episodes_rebuilt_after_publication_predate_the_source_rules(cfg):
    ep = make_episode(labelled_after_publication="2026-10-21")
    ep["segments"][0]["sources"] = [{"title": "Lindy", "url": "https://lindy.ai/x"}]
    assert errors_of(ep, cfg) == []
