"""Public corrections (podcast/corrections.py): on the site, in the feed, read in the next episode."""
import json
import xml.etree.ElementTree as ET

import pytest
import yaml

from conftest import ROOT, TUESDAY
from podcast import corrections, feed, generate

TEXT = "The episode of October nineteenth gave a two-week discount. Mistral set it at one week."


def published(day="2026-10-19"):
    return [{"date": day, "title": "T", "summary": "S", "guid": "g", "published_at": f"{day}T04:05:00+02:00",
             "audio_url": "https://a", "audio_bytes": 1, "duration_seconds": 1, "sources": []}]


def test_a_correction_is_attached_to_its_episode_and_waits_to_be_read():
    eps = published()
    corrections.add(eps, "2026-10-19", "  " + TEXT + "  ", TUESDAY.date())
    assert eps[0]["corrections"] == [{"added": "2026-10-20", "text": TEXT, "aired_in": None}]
    assert corrections.pending(eps) == [{"episode": "2026-10-19", "added": "2026-10-20", "text": TEXT, "aired_in": None}]
    corrections.mark_aired(eps, corrections.pending(eps), "2026-10-21")
    assert corrections.pending(eps) == [] and eps[0]["corrections"][0]["aired_in"] == "2026-10-21"


@pytest.mark.parametrize("text,reason", [
    ("Too short.", "words"),
    ("We said the discount lasted two weeks, but it lasted one week only in fact.", "first person"),
    ("See [the source] for the right figure of the Mistral discount, which was one week.", "cannot be read aloud"),
])
def test_a_correction_is_spoken_as_written_so_it_follows_the_voice_rules(text, reason):
    with pytest.raises(ValueError, match=reason):
        corrections.add(published(), "2026-10-19", text, TUESDAY.date())


def test_a_correction_needs_a_published_episode():
    with pytest.raises(ValueError, match="No published episode on 2026-10-18"):
        corrections.add(published(), "2026-10-18", TEXT, TUESDAY.date())


def test_forbidden_terms_are_refused(monkeypatch):
    monkeypatch.setenv("FORBIDDEN_TERMS", "Acme")
    with pytest.raises(ValueError, match="forbidden term"):
        corrections.add(published(), "2026-10-19", TEXT + " Acme agrees.", TUESDAY.date())


def test_the_corrected_episode_says_so_in_its_description(cfg):
    eps = published()
    corrections.add(eps, "2026-10-19", TEXT, TUESDAY.date())
    item = ET.fromstring(feed.build_feed(cfg, eps, "https://s/")).find("channel/item")
    assert f"Correction (2026-10-20): {TEXT}" in item.find("description").text


def test_a_correction_is_read_by_the_host_before_the_number_of_the_day(cfg):
    from conftest import make_episode
    ep = make_episode(corrections=[{"episode": "2026-10-19", "text": TEXT}])
    parts = generate.assemble_parts(ep, cfg, TUESDAY)
    i = next(i for i, (_, t) in enumerate(parts) if t.startswith("A correction."))
    assert parts[i] == ("host", f"A correction.\n\n{TEXT}") and parts[i + 1][1].startswith("The number of the day.")


def test_workflow_adds_it_without_any_paid_service_and_never_beside_an_episode_run():
    wf = yaml.safe_load((ROOT / ".github/workflows/correction.yml").read_text(encoding="utf-8"))
    daily = yaml.safe_load((ROOT / ".github/workflows/daily-episode.yml").read_text(encoding="utf-8"))
    assert wf["concurrency"]["group"] == daily["concurrency"]["group"]  # both write data/episodes.json
    steps = wf["jobs"]["correction"]["steps"]
    add = next(s for s in steps if s.get("name") == "Add the correction")
    assert set(add["env"]) == {"FORBIDDEN_TERMS", "EPISODE_DATE", "TEXT", "GITHUB_REPOSITORY"}
    assert add["run"] == 'python -m podcast.corrections add "$EPISODE_DATE" "$TEXT"'  # inputs never in the shell
    text = (ROOT / ".github/workflows/correction.yml").read_text(encoding="utf-8")
    assert "ANTHROPIC" not in text and "ELEVENLABS" not in text
